from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import formataddr
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, UploadFile, File, Form, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import os
import json
import re
import uuid
import numpy as np
from pydantic import BaseModel

from backend.firebase_admin_client import get_auth_client, get_firestore_client, verify_token
from src.contact_info import extract_emails
from src.parsing import load_uploaded_file
from src.skills import extract_skills, split_jd_required_preferred, coverage
from src.skill_graph import analyze_skill_graph_match, export_skill_graph
from src.embeddings import Embedder, get_cached_embedder
from src.explain import build_hr_explanation
from src.eval import ndcg_at_k
from src.train_embed import build_training_pairs_from_labels, finetune_sentence_transformer
from src.auto_label import auto_label_resumes
from src.ats_evaluator import evaluate_resume_ats
from src.ats_store import load_ats_state, sync_ats_candidates, update_ats_candidate
from src.fraud_detection import detect_resume_fraud
from src.resume_quality import evaluate_resume_quality
from src.resume_sections import split_resume_sections
from src.interview_questions import generate_interview_questions
from src.model_registry import (
    build_versioned_model_id,
    ensure_registry,
    list_models,
    register_trained_model,
    resolve_model,
)


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file(os.path.join("backend", ".env"))

BASELINE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
APP_DATA_ROOT = os.getenv("APP_DATA_ROOT", "").strip()
MODEL_ROOT = os.getenv("MODEL_ROOT", "").strip() or (
    os.path.join(APP_DATA_ROOT, "models") if APP_DATA_ROOT else "models"
)
FINETUNED_ROOT = os.getenv("FINETUNED_ROOT", "").strip() or os.path.join(MODEL_ROOT, "finetuned")
TRAINING_ENABLED = os.getenv("ENABLE_TRAINING", "true").strip().lower() not in {"0", "false", "no"}

MAX_FILE_MB = 12
MIN_TEXT_CHARS = 300
MIN_PDF_TEXT_CHARS = 150
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 160
MAX_TEXT_CHUNKS = 4

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "").strip() or (
    os.path.join(APP_DATA_ROOT, "backend-storage") if APP_DATA_ROOT else os.path.join("backend", "storage")
)

app = FastAPI(title="Resume Screening API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


USERS_COLLECTION = "users"
SETTINGS_COLLECTION = "app_settings"
EMAIL_TEMPLATES_DOC = "email_templates"
SKILL_GRAPH_DOC = "skill_graph"
BOOTSTRAP_ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("BOOTSTRAP_ADMIN_EMAILS", "").split(",")
    if email.strip()
}


def ensure_storage():
    os.makedirs(STORAGE_ROOT, exist_ok=True)


class AdminCreateUserPayload(BaseModel):
    name: str
    email: str
    password: str
    role: str = "hr"


class AdminUpdateUserPayload(BaseModel):
    role: str | None = None
    status: str | None = None


class EmailTemplatePayload(BaseModel):
    acceptanceSubject: str
    acceptanceBody: str
    processingSubject: str
    processingBody: str
    rejectionSubject: str
    rejectionBody: str


class SkillGraphPayload(BaseModel):
    graph: Dict[str, Any]


class CandidateEmailPayload(BaseModel):
    action: str
    candidate: str
    candidateName: str | None = None
    contactEmail: str | None = None
    atsStatus: str
    atsDecision: str
    screeningSkipped: bool = False
    score: float = 0.0
    atsScore: float = 0.0
    recommendation: str | None = None
    recommendationReason: str | None = None
    matchedSkills: List[str] = []
    missingRequired: List[str] = []
    missingPreferred: List[str] = []
    atsReasons: List[str] = []
    explanationSummary: str | None = None
    whyBad: List[str] = []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _serialize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return str(value)


def _user_doc(uid: str):
    return get_firestore_client().collection(USERS_COLLECTION).document(uid)


def _settings_doc(name: str):
    return get_firestore_client().collection(SETTINGS_COLLECTION).document(name)


def _bootstrap_role_for_email(email: str, fallback_role: str = "hr") -> str:
    if email.strip().lower() in BOOTSTRAP_ADMIN_EMAILS:
        return "admin"
    return "admin" if fallback_role == "admin" else "hr"


def _recover_bootstrap_admin_role(profile: Dict[str, Any]) -> Dict[str, Any]:
    email = str(profile.get("email") or "").strip().lower()
    uid = str(profile.get("uid") or "").strip()
    if not uid or email not in BOOTSTRAP_ADMIN_EMAILS or profile.get("role") == "admin":
        return profile

    _user_doc(uid).set({"role": "admin"}, merge=True)
    return {
        **profile,
        "role": "admin",
    }


def ensure_user_profile(*, uid: str, name: str, email: str, role: str = "hr", status: str = "active") -> Dict[str, Any]:
    resolved_role = _bootstrap_role_for_email(email, role)
    payload = {
        "uid": uid,
        "name": name,
        "email": email,
        "role": resolved_role,
        "status": "suspended" if status == "suspended" else "active",
        "suspended": status == "suspended",
        "createdAt": _utc_now_iso(),
    }
    _user_doc(uid).set(payload, merge=True)
    return payload


def load_user_profile(uid: str) -> Dict[str, Any] | None:
    snap = _user_doc(uid).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    return {
        "uid": uid,
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "role": "admin" if data.get("role") == "admin" else "hr",
        "status": "suspended" if data.get("status") == "suspended" or data.get("suspended") else "active",
        "suspended": bool(data.get("suspended")) or data.get("status") == "suspended",
        "createdAt": _serialize_timestamp(data.get("createdAt")),
    }


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Firebase bearer token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user_profile(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    token = _extract_bearer_token(authorization)
    decoded = verify_token(token)
    uid = decoded["uid"]
    profile = load_user_profile(uid)

    if profile is None:
        profile = ensure_user_profile(
            uid=uid,
            name=str(decoded.get("name") or decoded.get("email", "").split("@")[0] or "User"),
            email=str(decoded.get("email") or ""),
            role="hr",
            status="active",
        )
        profile["createdAt"] = _utc_now_iso()

    profile = _recover_bootstrap_admin_role(profile)

    if profile["status"] == "suspended":
        raise HTTPException(status_code=403, detail="Your account has been suspended. Contact admin.")

    return profile


def require_admin(profile: Dict[str, Any] = Depends(get_current_user_profile)) -> Dict[str, Any]:
    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return profile


def ensure_training_enabled() -> None:
    if not TRAINING_ENABLED:
        raise HTTPException(status_code=403, detail="Training features are disabled in this environment")


def safe_session_dir(session_id: str) -> str:
    session_id = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])[:80]
    ensure_storage()
    return os.path.join(STORAGE_ROOT, session_id)


def _smtp_config() -> Dict[str, Any]:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587") or "587"),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("SMTP_FROM_EMAIL", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "Resume Screening System").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"},
    }


def _send_email(*, to_email: str, subject: str, body: str) -> None:
    config = _smtp_config()
    required = ("host", "port", "username", "password", "from_email")
    if any(not config[key] for key in required):
        raise HTTPException(status_code=500, detail="SMTP email settings are not configured on the backend")

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = to_email

    with smtplib.SMTP(config["host"], config["port"], timeout=20) as server:
        server.ehlo()
        if config["use_tls"]:
            server.starttls()
            server.ehlo()
        server.login(config["username"], config["password"])
        server.sendmail(config["from_email"], [to_email], message.as_string())


def _default_email_templates() -> Dict[str, str]:
    return {
        "acceptanceSubject": "Interview Selection Update",
        "acceptanceBody": (
            "Hello {{candidateName}},\n\n"
            "Thank you for your application.\n\n"
            "We are pleased to inform you that you have been selected for the next stage of the process.\n"
            "Our team will contact you shortly with the interview date, timings, and further instructions.\n\n"
            "Best regards,\n"
            "Resume Screening System"
        ),
        "processingSubject": "Application Update",
        "processingBody": (
            "Hello {{candidateName}},\n\n"
            "Thank you for your application.\n\n"
            "Your profile is currently under review and still in process. Our team is evaluating applications and it may take some time before we reach out with the next update.\n\n"
            "We appreciate your patience and will contact you once there is further progress.\n\n"
            "Best regards,\n"
            "Resume Screening System"
        ),
        "rejectionSubject": "Application Status Update",
        "rejectionBody": (
            "Hello {{candidateName}},\n\n"
            "Thank you for your interest in this opportunity and for the time you invested in your application.\n\n"
            "After careful consideration, we will not be moving forward with your application for this role.\n\n"
            "We appreciate your interest in our organization and wish you success in your continued job search.\n\n"
            "Best regards,\n"
            "Resume Screening System"
        ),
    }


def _load_email_templates() -> Dict[str, str]:
    defaults = _default_email_templates()
    snap = _settings_doc(EMAIL_TEMPLATES_DOC).get()
    if not snap.exists:
        return defaults
    data = snap.to_dict() or {}
    return {
        key: str(data.get(key) or defaults[key])
        for key in defaults
    }


def _render_email_template(template: str, context: Dict[str, str]) -> str:
    output = template
    for key, value in context.items():
        output = output.replace(f"{{{{{key}}}}}", value)
    return output


def _load_skill_graph_config() -> Dict[str, Any]:
    fallback = export_skill_graph()
    snap = _settings_doc(SKILL_GRAPH_DOC).get()
    if not snap.exists:
        return fallback
    data = snap.to_dict() or {}
    graph = data.get("graph")
    return graph if isinstance(graph, dict) and graph else fallback


def _skill_graph_override_or_none(graph_config: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not graph_config:
        return None
    default_graph = export_skill_graph()
    return None if graph_config == default_graph else graph_config


def _validate_skill_graph_payload(graph: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for concept, payload in graph.items():
        if not isinstance(concept, str) or not concept.strip():
            raise HTTPException(status_code=400, detail="Skill graph concept keys must be non-empty strings")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail=f"Skill graph node for '{concept}' must be an object")

        def _list_of_strings(name: str) -> List[str]:
            value = payload.get(name, [])
            if value is None:
                return []
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise HTTPException(status_code=400, detail=f"Skill graph node '{concept}' field '{name}' must be a string list")
            return [item.strip() for item in value]

        cleaned[concept.strip()] = {
            "label": str(payload.get("label") or concept).strip(),
            "aliases": _list_of_strings("aliases"),
            "parents": _list_of_strings("parents"),
            "related": _list_of_strings("related"),
        }
    if not cleaned:
        raise HTTPException(status_code=400, detail="Skill graph cannot be empty")
    return cleaned


def bytes_limit_ok(b: bytes) -> bool:
    return (len(b) / (1024 * 1024)) <= MAX_FILE_MB


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    text = (text or "").strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        chunks.append(text[i:j])
        if j == len(text):
            break
        i = max(0, j - overlap)
    cleaned_chunks = [c.strip() for c in chunks if c.strip()]
    if len(cleaned_chunks) <= MAX_TEXT_CHUNKS:
        return cleaned_chunks

    # Sample across the document so long resumes keep beginning/middle/end coverage.
    sampled = []
    last_index = len(cleaned_chunks) - 1
    for idx in range(MAX_TEXT_CHUNKS):
        position = round(idx * last_index / max(1, MAX_TEXT_CHUNKS - 1))
        sampled.append(cleaned_chunks[position])
    return sampled


def chunked_similarity(embedder: Embedder, a_text: str, b_text: str) -> float:
    a_chunks = split_into_chunks(a_text)
    b_chunks = split_into_chunks(b_text)
    if not a_chunks or not b_chunks:
        return 0.0

    A = np.array(embedder.embed(a_chunks), dtype=np.float32)
    B = np.array(embedder.embed(b_chunks), dtype=np.float32)

    A /= (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    B /= (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)

    sims = A @ B.T
    return float(np.max(sims))


def _normalized_chunk_embeddings(embedder: Embedder, text: str) -> np.ndarray | None:
    chunks = split_into_chunks(text)
    if not chunks:
        return None
    embs = np.array(embedder.embed(chunks), dtype=np.float32)
    embs /= (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-9)
    return embs


def build_chunk_embedding_cache(embedder: Embedder, texts: List[str]) -> Dict[str, np.ndarray | None]:
    unique_texts: List[str] = []
    seen = set()
    for text in texts:
        cleaned = (text or "").strip()
        if cleaned in seen:
            continue
        seen.add(cleaned)
        unique_texts.append(cleaned)

    cache: Dict[str, np.ndarray | None] = {}
    chunk_map: Dict[str, List[str]] = {}
    all_chunks: List[str] = []

    for text in unique_texts:
        chunks = split_into_chunks(text)
        if not chunks:
            cache[text] = None
            continue
        chunk_map[text] = chunks
        all_chunks.extend(chunks)

    if all_chunks:
        all_embeddings = np.array(embedder.embed(all_chunks), dtype=np.float32)
        all_embeddings /= (np.linalg.norm(all_embeddings, axis=1, keepdims=True) + 1e-9)
        cursor = 0
        for text, chunks in chunk_map.items():
            next_cursor = cursor + len(chunks)
            cache[text] = all_embeddings[cursor:next_cursor]
            cursor = next_cursor

    return cache


def chunked_similarity_with_query_embeddings(
    *,
    query_embeddings: np.ndarray | None,
    embedder: Embedder,
    text: str,
    text_embeddings: np.ndarray | None = None,
) -> float:
    if query_embeddings is None:
        return 0.0
    target_embeddings = text_embeddings if text_embeddings is not None else _normalized_chunk_embeddings(embedder, text)
    if target_embeddings is None:
        return 0.0
    sims = query_embeddings @ target_embeddings.T
    return float(np.max(sims))


def _normalize_similarity(score: float) -> float:
    if score <= 0.16:
        return 0.0
    if score >= 0.68:
        return 1.0
    return max(0.0, min(1.0, (score - 0.16) / 0.52))


def read_uploaded(file: UploadFile):
    raw = file.file.read()
    if not bytes_limit_ok(raw):
        return "", [{
            "file": file.filename,
            "severity": "error",
            "message": f"File too large (> {MAX_FILE_MB}MB)"
        }]

    text = (load_uploaded_file(file.filename, raw) or "").strip()
    warnings = []

    if len(text) < MIN_TEXT_CHARS:
        warnings.append({
            "file": file.filename,
            "severity": "warning",
            "message": "Low extracted text. Resume may be scanned or image-based."
        })

    if file.filename.lower().endswith(".pdf") and len(text) < MIN_PDF_TEXT_CHARS:
        warnings.append({
            "file": file.filename,
            "severity": "warning",
            "message": "PDF appears scanned. Upload text-based PDF or DOCX for better results."
        })

    return text, warnings


def match_style_label(style: float) -> str:
    if style <= 0.2:
        return "Flexible"
    if style >= 0.8:
        return "Strict"
    return "Balanced"


def get_embedder(model_choice: str):
    model_path, model_id = resolve_model(
        model_choice=model_choice,
        baseline_name=BASELINE_MODEL,
        finetuned_root=FINETUNED_ROOT,
    )
    return get_cached_embedder(model_path), model_id


def semantic_rank(jd_text: str, resumes_data: list, embedder: Embedder):
    embedding_cache = build_chunk_embedding_cache(embedder, [jd_text, *[r["text"] for r in resumes_data]])
    jd_embeddings = embedding_cache.get((jd_text or "").strip())
    scores = []
    for r in resumes_data:
        s = chunked_similarity_with_query_embeddings(
            query_embeddings=jd_embeddings,
            embedder=embedder,
            text=r["text"],
            text_embeddings=embedding_cache.get((r["text"] or "").strip()),
        )
        scores.append((r["name"], float(s)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scores]


def extract_projects_from_resume(text: str) -> List[str]:
    sections = split_resume_sections(text)
    projects_text = sections.get("projects", "").strip()

    if not projects_text:
        return []

    # split by line/bullet/sentence-ish separators
    raw_parts = re.split(r"\n+|•|- |\u2022|\. ", projects_text)
    cleaned = []
    for part in raw_parts:
        p = part.strip(" -•\t\r\n")
        if len(p) >= 12:
            cleaned.append(p)

    # unique and limited
    seen = set()
    out = []
    for p in cleaned:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
        if len(out) >= 5:
            break
    return out


def extract_project_candidates_from_resume(text: str) -> List[str]:
    sections = split_resume_sections(text)
    projects_text = sections.get("projects", "").strip()
    experience_text = sections.get("experience", "").strip()

    def _split_parts(raw_text: str) -> List[str]:
        raw_parts = re.split(r"\n+|â€¢|- |\u2022|\. ", raw_text)
        cleaned_parts: List[str] = []
        for part in raw_parts:
            p = part.strip(" -â€¢\t\r\n")
            if len(p) >= 12:
                cleaned_parts.append(p)
        return cleaned_parts

    def _looks_like_project_heading(value: str) -> bool:
        lowered = value.lower().strip()
        if len(lowered) < 8 or len(lowered) > 120:
            return False
        if re.search(
            r"\b(built|developed|designed|implemented|created|launched|deployed|engineered|architected|automated|trained|enabled|resolved|utilized|integrated|added|optimized|analyzed|managed|fine-tuned)\b",
            lowered,
        ):
            return False
        if re.search(r"\b(certification|certifications|certificate|networking|tutorials|academy|ibm|deeplearning\.ai|introduction to|course)\b", lowered):
            return False
        if "|" in value:
            return True
        if re.search(r"\b(project|platform|system|application|app|assistant|tracker|solution|detection|analytics)\b", lowered):
            return True
        title_case_words = re.findall(r"[A-Z][A-Za-z0-9+#&.-]*", value)
        return len(title_case_words) >= 2

    def _looks_like_project_line(value: str) -> bool:
        lowered = value.lower()
        action_hit = bool(
            re.search(
                r"\b(built|developed|designed|implemented|created|launched|deployed|engineered|architected|automated)\b",
                lowered,
            )
        )
        context_hit = bool(
            re.search(
                r"\b(project|platform|application|app|system|pipeline|dashboard|api|service|tool|portal|parser|model)\b",
                lowered,
            )
        )
        tech_hit = bool(
            re.search(
                r"\b(using|with|python|react|fastapi|sql|aws|docker|tensorflow|pytorch|node|javascript|typescript)\b",
                lowered,
            )
        )
        return (action_hit and context_hit) or (context_hit and tech_hit)

    cleaned = _split_parts(projects_text)
    heading_candidates = [part for part in cleaned if _looks_like_project_heading(part)]
    if heading_candidates:
        cleaned = heading_candidates
    elif not cleaned and experience_text:
        experience_parts = _split_parts(experience_text)
        heading_candidates = [part for part in experience_parts if _looks_like_project_heading(part)]
        cleaned = heading_candidates or [part for part in experience_parts if _looks_like_project_line(part)]

    seen = set()
    out = []
    for part in cleaned:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
        if len(out) >= 8:
            break
    return out


def extract_experience_years(text: str) -> str:
    text_l = text.lower()
    current_year = datetime.now(timezone.utc).year

    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+of\s+experience",
        r"experience\s+of\s+(\d+(?:\.\d+)?)\+?\s+years?",
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+experience",
    ]

    values = []
    for pat in patterns:
        matches = re.findall(pat, text_l)
        for m in matches:
            try:
                values.append(float(m))
            except Exception:
                pass

    if values:
        best = max(values)
        if best.is_integer():
            return f"{int(best)} years"
        return f"{best:.1f} years"

    # Fallback from date ranges only when the surrounding line looks like work history.
    experience_like_lines = []
    for raw_line in text_l.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.search(
            r"\b(education|degree|bachelor|master|b\.tech|bba|bca|bsc|class 10|class 12|cgpa|percentage|hsc|ssc|cisce|cbse|school|college|university)\b",
            line,
        ):
            continue
        if re.search(
            r"\b(experience|intern|internship|worked|employment|engineer|developer|analyst|manager|consultant|associate|executive|campus ambassador|trainee)\b",
            line,
        ):
            experience_like_lines.append(line)

    experience_text = "\n".join(experience_like_lines)
    year_pairs = re.findall(r"(20\d{2}|19\d{2})\s*[-–to]+\s*(20\d{2}|19\d{2}|present|current)", experience_text)
    total = 0.0
    for a, b in year_pairs[:6]:
        try:
            start = int(a)
            end = current_year if b in ("present", "current") else int(b)
            if end >= start:
                total += min(6, end - start)
        except Exception:
            pass

    if total > 0:
        total = max(1, round(total))
        return f"{int(total)} years (estimated)"

    return "Not clearly mentioned"


def primary_contact_email(text: str) -> str | None:
    emails = extract_emails(text)
    return emails[0] if emails else None


def extract_candidate_name(text: str, fallback_filename: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    blocked = {
        "skills", "experience", "education", "projects", "certifications",
        "technical skills", "achievements", "summary", "objective",
    }
    for line in lines[:12]:
        lowered = line.lower()
        if "@" in line or "http" in lowered or len(line) > 60:
            continue
        if lowered in blocked:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z.'-]*", line)
        if 2 <= len(words) <= 4:
            name = " ".join(words)
            if len(name) >= 5:
                return name

    stem = os.path.splitext(os.path.basename(fallback_filename))[0]
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\bresume\b", "", stem, flags=re.IGNORECASE).strip()
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*", stem)
    return " ".join(words[:4]) or fallback_filename


def build_candidate_intelligence(
    *,
    resume_text: str,
    jd_text: str,
    jd_required: set[str],
    jd_preferred: set[str],
    ats_result: Dict[str, Any],
    graph_config: Dict[str, Any] | None = None,
    generate_questions: bool = True,
) -> Dict[str, Any]:
    graph_override = _skill_graph_override_or_none(graph_config or _load_skill_graph_config())
    graph_analysis = analyze_skill_graph_match(
        resume_text=resume_text,
        jd_text=jd_text,
        jd_required=jd_required,
        jd_preferred=jd_preferred,
        graph_override=graph_override,
    )
    fraud_analysis = detect_resume_fraud(
        resume_text=resume_text,
        normalized_skills=graph_analysis.get("normalizedSkills", []),
        jd_text=jd_text,
    )
    quality_analysis = evaluate_resume_quality(
        resume_text=resume_text,
        ats_score=float(ats_result.get("atsScore", 0.0)),
        ats_status=ats_result.get("atsStatus"),
    )
    resume_skills, _ = extract_skills(resume_text)
    matched_skills = sorted(set(resume_skills) & (jd_required | jd_preferred))
    missing_required = sorted(jd_required - set(resume_skills))
    missing_preferred = sorted(jd_preferred - set(resume_skills))
    candidate_projects = extract_project_candidates_from_resume(resume_text)
    candidate_experience_years = extract_experience_years(resume_text)
    interview_questions = (
        generate_interview_questions(
            {
                "skills": matched_skills,
                "projects": candidate_projects,
                "missingRequired": missing_required,
                "missingPreferred": missing_preferred,
                "experienceYears": candidate_experience_years,
            }
        )
        if generate_questions
        else {
            "skillQuestions": ["Interview questions are generated for shortlisted candidates only."],
            "projectQuestions": [],
            "weaknessQuestions": [],
            "experienceQuestions": [],
        }
    )
    return {
        **graph_analysis,
        **fraud_analysis,
        **quality_analysis,
        "interviewQuestions": interview_questions,
    }


def _default_candidate_intelligence(
    *,
    graph_analysis: Dict[str, Any],
    ats_result: Dict[str, Any],
) -> Dict[str, Any]:
    quality_status = "Strong" if float(ats_result.get("atsScore", 0.0)) >= 75 else "Moderate"
    return {
        **graph_analysis,
        "fraudRiskScore": 0.0,
        "fraudStatus": "Low Risk",
        "fraudReasons": ["Detailed fraud analysis is deferred until candidate review."],
        "fraudRecommendation": "Proceed",
        "resumeQualityScore": round(max(45.0, float(ats_result.get("atsScore", 0.0)) * 0.8), 1),
        "resumeQualityStatus": quality_status,
        "resumeQualityReasons": ["Detailed resume quality analysis is deferred until candidate review."],
        "improvementSuggestions": ["Open the candidate report to generate full quality and fraud insights."],
        "interviewQuestions": {
            "skillQuestions": ["Open the candidate report to generate targeted interview questions."],
            "projectQuestions": [],
            "weaknessQuestions": [],
            "experienceQuestions": [],
        },
    }


def apply_intelligence_to_explanation(
    explanation: Dict[str, Any],
    intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    why_good = list(explanation.get("whyGood", []))
    why_bad = list(explanation.get("whyBad", []))

    graph_notes = intelligence.get("graphSkillNotes", [])
    if graph_notes:
        why_good.extend(graph_notes[:2])

    quality_status = intelligence.get("resumeQualityStatus")
    quality_score = intelligence.get("resumeQualityScore", 0.0)
    if quality_status == "Strong":
        why_good.append(f"Resume structure is recruiter-friendly ({quality_score}/100 quality score).")
    elif quality_status == "Weak":
        why_bad.append("Resume quality is weak enough to reduce confidence in the candidate presentation.")

    fraud_status = intelligence.get("fraudStatus")
    if fraud_status == "High Risk":
        why_bad.insert(0, "High fraud-risk signals were detected and this profile should be verified before moving forward.")
        if explanation.get("recommendation") == "Hire":
            explanation["recommendation"] = "Hold"
            explanation["recommendationReason"] = "Strong fit signals exist, but fraud-risk flags require manual verification first."
    elif fraud_status == "Medium Risk":
        why_bad.append("Some fraud-risk signals were detected and deserve careful recruiter review.")

    explanation["whyGood"] = why_good[:5] or explanation.get("whyGood", [])
    explanation["whyBad"] = why_bad[:5] or explanation.get("whyBad", [])
    return explanation


def score_candidates(
    *,
    jd_text: str,
    resumes_data: List[Dict[str, str]],
    match_style: float,
    cutoff: int,
    model_choice: str,
    auto_improve: bool,
    ats_results_by_candidate: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    warnings: List[Dict[str, Any]] = []
    graph_config = _load_skill_graph_config()
    graph_override = _skill_graph_override_or_none(graph_config)

    embedder, loaded = get_embedder(model_choice)
    section_cache = {
        r["name"]: split_resume_sections(r["text"])
        for r in resumes_data
    }
    embedding_cache = build_chunk_embedding_cache(
        embedder,
        [
            jd_text,
            *[r["text"] for r in resumes_data],
        ],
    )
    jd_embeddings = embedding_cache.get((jd_text or "").strip())

    jd_req, jd_pref = split_jd_required_preferred(jd_text)
    style_value = max(0.0, min(1.0, float(match_style)))
    style_label = match_style_label(style_value)

    # Interpolate between two scoring profiles so the slider has a visible impact.
    flexible_profile = {
        "semantic": 0.52,
        "required": 0.14,
        "preferred": 0.10,
        "experience": 0.10,
        "graph": 0.14,
    }
    strict_profile = {
        "semantic": 0.34,
        "required": 0.34,
        "preferred": 0.06,
        "experience": 0.10,
        "graph": 0.16,
    }

    semantic_w = flexible_profile["semantic"] + (strict_profile["semantic"] - flexible_profile["semantic"]) * style_value
    req_w = flexible_profile["required"] + (strict_profile["required"] - flexible_profile["required"]) * style_value
    pref_w = flexible_profile["preferred"] + (strict_profile["preferred"] - flexible_profile["preferred"]) * style_value
    exp_w = flexible_profile["experience"] + (strict_profile["experience"] - flexible_profile["experience"]) * style_value
    graph_w = flexible_profile["graph"] + (strict_profile["graph"] - flexible_profile["graph"]) * style_value

    results = []
    resume_lookup = {r["name"]: r["text"] for r in resumes_data}

    for r in resumes_data:
        sections = section_cache[r["name"]]
        skills_text = sections.get("skills", "")
        experience_text = sections.get("experience", "")
        projects_text = sections.get("projects", "")

        raw_semantic_score = chunked_similarity_with_query_embeddings(
            query_embeddings=jd_embeddings,
            embedder=embedder,
            text=r["text"],
            text_embeddings=embedding_cache.get((r["text"] or "").strip()),
        )
        semantic_score = _normalize_similarity(raw_semantic_score)

        skills_from_resume, _ = extract_skills(skills_text + " " + r["text"])
        res_skills = skills_from_resume

        req_cov, pref_cov = coverage(res_skills, jd_req, jd_pref)
        exp_signal = 0.0
        if experience_text.strip():
            exp_signal += 0.7
        if projects_text.strip():
            exp_signal += 0.3
        exp_signal = max(exp_signal, min(1.0, (req_cov * 0.7) + (pref_cov * 0.3)))
        ats_result = (ats_results_by_candidate or {}).get(r["name"]) or evaluate_resume_ats(r["text"], jd_text)
        graph_analysis = analyze_skill_graph_match(
            resume_text=r["text"],
            jd_text=jd_text,
            jd_required=jd_req,
            jd_preferred=jd_pref,
            graph_override=graph_override,
        )
        intelligence = _default_candidate_intelligence(graph_analysis=graph_analysis, ats_result=ats_result)
        graph_score = float(graph_analysis.get("graphSkillScore", 0.0)) / 100.0
        ats_signal = float(ats_result.get("atsScore", 0.0)) / 100.0

        score = (
            semantic_w * semantic_score
            + req_w * req_cov
            + pref_w * pref_cov
            + exp_w * exp_signal
            + graph_w * graph_score
        ) * 100.0
        score = (score * 0.82) + (ats_signal * 18.0)
        if req_cov >= 0.5:
            score += 4.0 + (8.0 * style_value)
        elif req_cov >= 0.3:
            score += 2.0 + (4.0 * style_value)
        if semantic_score >= 0.55:
            score += 8.0 - (4.0 * style_value)
        elif semantic_score >= 0.4:
            score += 4.0 - (2.0 * style_value)
        if jd_req:
            if req_cov == 0.0:
                score -= 14.0 + (8.0 * style_value)
            elif req_cov < 0.12:
                score -= 4.0 + (4.0 * style_value)
        score = round(max(0.0, min(100.0, score)), 1)

        matched = sorted(list(res_skills & (jd_req | jd_pref)))
        missing_req = sorted(list(jd_req - res_skills))
        missing_pref = sorted(list(jd_pref - res_skills))

        explanation = build_hr_explanation(
            candidate_name=r["name"],
            score=score,
            match_style_label=style_label,
            jd_required=jd_req,
            jd_preferred=jd_pref,
            matched_skills=matched,
            missing_required=missing_req,
            missing_preferred=missing_pref,
            evidence_pairs=[],  # no evidence in screening view now
            max_points=5
        )
        explanation = apply_intelligence_to_explanation(explanation, intelligence)

        candidate_projects = extract_project_candidates_from_resume(r["text"])
        candidate_experience_years = extract_experience_years(r["text"])
        contact_email = primary_contact_email(r["text"])

        results.append({
            "candidate": r["name"],
            "candidateName": extract_candidate_name(r["text"], r["name"]),
            "score": score,
            "projects": candidate_projects,
            "experienceYears": candidate_experience_years,
            "contactEmail": contact_email,
            "skills": matched,
            "matchedSkills": matched,
            "missingRequired": missing_req,
            "missingPreferred": missing_pref,
            "recommendation": explanation.get("recommendation"),
            "recommendationReason": explanation.get("recommendationReason"),
            "explanation": explanation,
            "interviewQuestions": intelligence.get("interviewQuestions", {}),
            **intelligence,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    shortlist = [r for r in results if r["score"] >= cutoff]
    if not shortlist:
        shortlist = [
            item
            for item in results
            if item.get("atsDecision") != "Reject" and float(item.get("score", 0.0)) >= 32.0
        ][: max(3, min(5, len(results)))]

    top_ranked_names = [
        item["candidate"]
        for item in results
        if item.get("atsDecision") != "Reject"
    ][:5]
    shortlist_names = {item["candidate"] for item in shortlist}
    enrich_names = set(top_ranked_names) | {item["candidate"] for item in shortlist}
    items_to_enrich = [item for item in results if item["candidate"] in enrich_names]
    max_workers = min(4, max(1, len(items_to_enrich)))

    if max_workers == 1:
        for item in items_to_enrich:
            resume_text = resume_lookup.get(item["candidate"], "")
            ats_result = (ats_results_by_candidate or {}).get(item["candidate"]) or {}
            intelligence = build_candidate_intelligence(
                resume_text=resume_text,
                jd_text=jd_text,
                jd_required=jd_req,
                jd_preferred=jd_pref,
                ats_result=ats_result,
                graph_config=graph_config,
                generate_questions=item["candidate"] in shortlist_names,
            )
            item.update(intelligence)
            item["explanation"] = apply_intelligence_to_explanation(item.get("explanation", {}), intelligence)
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="candidate-intel") as executor:
            future_map = {}
            for item in items_to_enrich:
                resume_text = resume_lookup.get(item["candidate"], "")
                ats_result = (ats_results_by_candidate or {}).get(item["candidate"]) or {}
                future = executor.submit(
                    build_candidate_intelligence,
                    resume_text=resume_text,
                    jd_text=jd_text,
                    jd_required=jd_req,
                    jd_preferred=jd_pref,
                    ats_result=ats_result,
                    graph_config=graph_config,
                    generate_questions=item["candidate"] in shortlist_names,
                )
                future_map[future] = item

            for future in as_completed(future_map):
                item = future_map[future]
                intelligence = future.result()
                item.update(intelligence)
                item["explanation"] = apply_intelligence_to_explanation(item.get("explanation", {}), intelligence)

    shortlist = [item for item in results if item["candidate"] in shortlist_names]

    return {
        "modelUsed": loaded,
        "autoImproveTriggered": False,
        "warnings": warnings,
        "ranked": results,
        "shortlist": shortlist,
    }


def build_rejected_candidate(
    *,
    resume_name: str,
    resume_text: str,
    jd_text: str,
    jd_required: set[str],
    jd_preferred: set[str],
    ats_result: Dict[str, Any],
) -> Dict[str, Any]:
    explanation = apply_intelligence_to_explanation(
        {
            "fitLabel": "Rejected by ATS",
            "summary": "This resume did not pass ATS validation and was not sent to the screening model.",
            "whyGood": [],
            "whyBad": ats_result.get("atsReasons", []),
            "recommendation": "Rejected by ATS validation",
            "recommendationReason": "ATS gate rejected the resume before semantic screening.",
        },
        {
            "graphSkillNotes": [],
            "resumeQualityScore": 0.0,
            "resumeQualityStatus": "Weak",
            "fraudStatus": "Low Risk",
        },
    )
    return {
        "candidate": resume_name,
        "candidateName": extract_candidate_name(resume_text, resume_name),
        "score": 0.0,
        "screeningSkipped": True,
        "projects": extract_project_candidates_from_resume(resume_text),
        "experienceYears": extract_experience_years(resume_text),
        "contactEmail": primary_contact_email(resume_text),
        "skills": [],
        "matchedSkills": [],
        "missingRequired": sorted(jd_required),
        "missingPreferred": sorted(jd_preferred),
        "recommendation": explanation.get("recommendation"),
        "recommendationReason": "; ".join(ats_result.get("atsReasons", [])[:2]) or "Resume failed ATS validation.",
        "explanation": explanation,
        "normalizedSkills": [],
        "graphMatchedSkills": [],
        "graphMissingSkills": sorted(jd_required | jd_preferred),
        "graphSkillScore": 0.0,
        "graphSkillNotes": [],
        "fraudRiskScore": 0.0,
        "fraudStatus": "Low Risk",
        "fraudReasons": ["Fraud analysis was skipped because the resume was rejected at the ATS gate."],
        "fraudRecommendation": "Proceed",
        "resumeQualityScore": 0.0,
        "resumeQualityStatus": "Weak",
        "resumeQualityReasons": ["Resume quality analysis was skipped because the resume was rejected at the ATS gate."],
        "improvementSuggestions": ["Fix the ATS issues listed above and resubmit the resume in a clearer format."],
        "interviewQuestions": {
            "skillQuestions": [],
            "projectQuestions": [],
            "weaknessQuestions": [],
            "experienceQuestions": [],
        },
        **ats_result,
    }


def apply_ats_gate(
    *,
    jd_text: str,
    resumes_data: List[Dict[str, str]],
    match_style: float,
    cutoff: int,
    model_choice: str,
    auto_improve: bool,
) -> Dict[str, Any]:
    ats_by_candidate: Dict[str, Dict[str, Any]] = {}
    screenable_resumes: List[Dict[str, str]] = []

    for resume in resumes_data:
        ats_result = evaluate_resume_ats(resume["text"], jd_text)
        ats_by_candidate[resume["name"]] = ats_result
        if ats_result["atsDecision"] != "Reject":
            screenable_resumes.append(resume)

    ranked_results: List[Dict[str, Any]] = []
    shortlist: List[Dict[str, Any]] = []
    model_used = model_choice
    screening_warnings: List[Dict[str, Any]] = []

    if screenable_resumes:
        screened = score_candidates(
            jd_text=jd_text,
            resumes_data=screenable_resumes,
            match_style=match_style,
            cutoff=cutoff,
            model_choice=model_choice,
            auto_improve=auto_improve,
            ats_results_by_candidate=ats_by_candidate,
        )
        ranked_results = screened["ranked"]
        shortlist = screened["shortlist"]
        screening_warnings = screened.get("warnings", [])
        model_used = screened.get("modelUsed", model_choice)

    screened_map = {item["candidate"]: item for item in ranked_results}
    jd_req, jd_pref = split_jd_required_preferred(jd_text)

    final_ranked: List[Dict[str, Any]] = []
    for resume in resumes_data:
        ats_result = ats_by_candidate[resume["name"]]
        screened_candidate = screened_map.get(resume["name"])

        if screened_candidate is None:
            final_ranked.append(
                build_rejected_candidate(
                    resume_name=resume["name"],
                    resume_text=resume["text"],
                    jd_text=jd_text,
                    jd_required=jd_req,
                    jd_preferred=jd_pref,
                    ats_result=ats_result,
                )
            )
            continue

        final_ranked.append(
            {
                **screened_candidate,
                "screeningSkipped": False,
                **ats_result,
            }
        )

    final_ranked.sort(
        key=lambda item: (
            item.get("atsDecision") == "Reject",
            -float(item.get("score", 0.0)),
            -float(item.get("atsScore", 0.0)),
        )
    )
    shortlist_names = {item["candidate"] for item in shortlist}
    final_shortlist = [item for item in final_ranked if item["candidate"] in shortlist_names]

    return {
        "modelUsed": model_used,
        "autoImproveTriggered": False,
        "warnings": screening_warnings,
        "ranked": final_ranked,
        "shortlist": final_shortlist,
        "atsSummary": {
            "pass": sum(1 for item in final_ranked if item.get("atsStatus") == "PASS"),
            "review": sum(1 for item in final_ranked if item.get("atsStatus") == "REVIEW"),
            "fail": sum(1 for item in final_ranked if item.get("atsStatus") == "FAIL"),
            "screened": sum(1 for item in final_ranked if not item.get("screeningSkipped")),
            "rejected": sum(1 for item in final_ranked if item.get("atsDecision") == "Reject"),
        },
    }


def train_and_register_model(
    *,
    jd_text: str,
    resumes_data: List[Dict[str, str]],
    labels: List[int],
    epochs: int,
    batch_size: int,
    pos_threshold: int,
    set_as_default: bool,
) -> Dict[str, Any]:
    if len(labels) != len(resumes_data):
        return {
            "ok": False,
            "error": f"Labels count ({len(labels)}) must match resumes count ({len(resumes_data)})."
        }

    train_examples = build_training_pairs_from_labels(
        jd_text=jd_text,
        resume_texts=[r["text"] for r in resumes_data],
        labels=[int(x) for x in labels],
        pos_threshold=int(pos_threshold)
    )

    if len(train_examples) < 3:
        return {"ok": False, "error": "Not enough positive labels"}

    os.makedirs(FINETUNED_ROOT, exist_ok=True)
    model_id = build_versioned_model_id()
    output_dir = os.path.join(FINETUNED_ROOT, model_id)
    finetune_sentence_transformer(
        base_model_name=BASELINE_MODEL,
        train_examples=train_examples,
        output_dir=output_dir,
        epochs=int(epochs),
        batch_size=int(batch_size),
        warmup_steps=50
    )
    register_trained_model(
        baseline_name=BASELINE_MODEL,
        finetuned_root=FINETUNED_ROOT,
        model_id=model_id,
        model_path=output_dir,
        metrics={
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "train_examples": len(train_examples),
            "pos_threshold": int(pos_threshold),
        },
        set_as_default=bool(set_as_default),
    )
    return {
        "ok": True,
        "model_id": model_id,
        "train_examples": len(train_examples),
        "set_as_default": bool(set_as_default),
    }


@app.on_event("startup")
async def startup_event():
    ensure_registry(BASELINE_MODEL, FINETUNED_ROOT)
    try:
        default_embedder, _ = get_embedder("default")
        _ = default_embedder
    except Exception as exc:
        print(f"Model preload skipped: {exc}")


@app.get("/models")
async def get_models():
    return {
        "ok": True,
        **list_models(BASELINE_MODEL, FINETUNED_ROOT),
    }


@app.get("/auth/me")
async def auth_me(profile: Dict[str, Any] = Depends(get_current_user_profile)):
    return {"ok": True, "profile": profile}


@app.post("/screen")
async def screen_resumes(
    jd: UploadFile = File(...),
    resumes: List[UploadFile] = File(...),
    match_style: float = Form(0.4),
    cutoff: int = Form(60),
    model_choice: str = Form("best"),
    auto_improve: bool = Form(True),
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    jd_text, jd_warn = read_uploaded(jd)
    warnings = list(jd_warn)

    resumes_data = []
    for f in resumes:
        txt, w = read_uploaded(f)
        warnings.extend(w)
        resumes_data.append({"name": f.filename, "text": txt})

    out = apply_ats_gate(
        jd_text=jd_text,
        resumes_data=resumes_data,
        match_style=match_style,
        cutoff=cutoff,
        model_choice=model_choice,
        auto_improve=auto_improve,
    )
    out["warnings"] = warnings + out.get("warnings", [])
    out["ok"] = True
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    out["session_id"] = session_id
    out["extractionStats"] = {
        "jdChars": len(jd_text),
        "resumeChars": {r["name"]: len(r["text"]) for r in resumes_data}
    }
    ats_state = sync_ats_candidates(
        safe_session_dir(session_id),
        out["ranked"],
        [item["candidate"] for item in out["shortlist"]],
    )
    out["ats"] = ats_state
    return out


@app.get("/ats/{session_id}")
async def get_ats_state(
    session_id: str,
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    session_dir = safe_session_dir(session_id)
    if not os.path.exists(session_dir):
        return {"ok": False, "error": "No ATS session found for this session_id"}
    return {"ok": True, "session_id": session_id, **load_ats_state(session_dir)}


@app.post("/ats/update")
async def update_ats_state(
    session_id: str = Form(...),
    candidate: str = Form(...),
    stage: str = Form(...),
    notes: str = Form(""),
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    session_dir = safe_session_dir(session_id)
    if not os.path.exists(session_dir):
        return {"ok": False, "error": "No ATS session found for this session_id"}

    try:
        updated = update_ats_candidate(
            session_dir,
            candidate=candidate,
            stage=stage,
            notes=notes,
        )
    except KeyError as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "session_id": session_id, "candidate_state": updated}


def _email_template_context(payload: CandidateEmailPayload) -> Dict[str, str]:
    recipient_name = (payload.candidateName or payload.candidate or "Candidate").strip()
    experience_reasons = [
        reason
        for reason in (payload.atsReasons + payload.whyBad)
        if "experience" in reason.lower() or "year" in reason.lower()
    ]
    missing = payload.missingRequired or payload.missingPreferred
    gaps_section = ""
    if missing:
        gaps_section = "Areas that did not align closely with the role:\n" + "\n".join(f"- {item}" for item in missing[:8]) + "\n\n"

    experience_section = ""
    if experience_reasons:
        experience_section = "Experience alignment:\n" + "\n".join(f"- {reason}" for reason in experience_reasons[:3]) + "\n\n"

    return {
        "candidateName": recipient_name,
        "candidateEmail": payload.contactEmail or "",
        "gapsSection": gaps_section,
        "experienceSection": experience_section,
        "findingsSection": "",
    }


@app.post("/candidate-email")
async def send_candidate_email(
    payload: CandidateEmailPayload,
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    action = payload.action.strip().lower()
    to_email = (payload.contactEmail or "").strip().lower()
    if action not in {"accept", "reject", "process"}:
        raise HTTPException(status_code=400, detail="Unsupported candidate email action")
    if not to_email:
        raise HTTPException(status_code=400, detail="Candidate email was not found in the resume")

    templates = _load_email_templates()
    context = _email_template_context(payload)

    if action == "accept":
        subject = _render_email_template(templates["acceptanceSubject"], context)
        body = _render_email_template(templates["acceptanceBody"], context)
    elif action == "process":
        subject = _render_email_template(templates["processingSubject"], context)
        body = _render_email_template(templates["processingBody"], context)
    else:
        subject = _render_email_template(templates["rejectionSubject"], context)
        body = _render_email_template(templates["rejectionBody"], context)

    _send_email(to_email=to_email, subject=subject, body=body)
    return {
        "ok": True,
        "sentTo": to_email,
        "sentFrom": _smtp_config().get("from_email"),
        "action": action,
    }


@app.get("/admin/email-templates")
async def get_email_templates(_: Dict[str, Any] = Depends(require_admin)):
    return {"ok": True, "templates": _load_email_templates()}


@app.patch("/admin/email-templates")
async def update_email_templates(
    payload: EmailTemplatePayload,
    _: Dict[str, Any] = Depends(require_admin),
):
    data = payload.model_dump()
    _settings_doc(EMAIL_TEMPLATES_DOC).set(data, merge=True)
    return {"ok": True, "templates": _load_email_templates()}


@app.get("/admin/skill-graph")
async def get_skill_graph(_: Dict[str, Any] = Depends(require_admin)):
    return {"ok": True, "graph": _load_skill_graph_config()}


@app.patch("/admin/skill-graph")
async def update_skill_graph(
    payload: SkillGraphPayload,
    _: Dict[str, Any] = Depends(require_admin),
):
    graph = _validate_skill_graph_payload(payload.graph)
    _settings_doc(SKILL_GRAPH_DOC).set({"graph": graph}, merge=True)
    return {"ok": True, "graph": _load_skill_graph_config()}


@app.get("/admin/users")
async def list_users_endpoint(_: Dict[str, Any] = Depends(require_admin)):
    docs = get_firestore_client().collection(USERS_COLLECTION).stream()
    users = []
    for doc in docs:
        payload = doc.to_dict() or {}
        users.append({
            "uid": doc.id,
            "name": payload.get("name", ""),
            "email": payload.get("email", ""),
            "role": "admin" if payload.get("role") == "admin" else "hr",
            "status": "suspended" if payload.get("status") == "suspended" or payload.get("suspended") else "active",
            "suspended": bool(payload.get("suspended")) or payload.get("status") == "suspended",
            "createdAt": _serialize_timestamp(payload.get("createdAt")),
        })

    users.sort(key=lambda item: ((item.get("name") or item.get("email") or "").lower(), item["uid"]))
    return {"ok": True, "users": users}


@app.post("/admin/users")
async def create_user_endpoint(
    payload: AdminCreateUserPayload,
    admin_profile: Dict[str, Any] = Depends(require_admin),
):
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    auth_client = get_auth_client()
    created = auth_client.create_user(
        email=payload.email.strip(),
        password=payload.password,
        display_name=payload.name.strip(),
        disabled=False,
    )
    profile = ensure_user_profile(
        uid=created.uid,
        name=payload.name.strip(),
        email=payload.email.strip(),
        role="admin" if payload.role == "admin" else "hr",
        status="active",
    )
    return {
        "ok": True,
        "created_by": admin_profile["uid"],
        "user": {**profile, "createdAt": _utc_now_iso()},
    }


@app.patch("/admin/users/{uid}")
async def update_user_endpoint(
    uid: str,
    payload: AdminUpdateUserPayload,
    admin_profile: Dict[str, Any] = Depends(require_admin),
):
    role = None if payload.role is None else ("admin" if payload.role == "admin" else "hr")
    status = None if payload.status is None else ("suspended" if payload.status == "suspended" else "active")

    doc = _user_doc(uid)
    snap = doc.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found")

    if uid == admin_profile["uid"] and status == "suspended":
        raise HTTPException(status_code=400, detail="Admin cannot suspend their own account")

    updates: Dict[str, Any] = {}
    if role is not None:
        updates["role"] = role
    if status is not None:
        updates["status"] = status
        updates["suspended"] = status == "suspended"
        get_auth_client().update_user(uid, disabled=status == "suspended")

    if updates:
        doc.set(updates, merge=True)

    updated = load_user_profile(uid)
    return {"ok": True, "updated_by": admin_profile["uid"], "user": updated}


@app.post("/train")
async def train_finetuned(
    jd: UploadFile = File(...),
    resumes: List[UploadFile] = File(...),
    labels_json: str = Form(...),
    epochs: int = Form(1),
    batch_size: int = Form(16),
    pos_threshold: int = Form(2),
    set_as_default: bool = Form(False),
    _: Dict[str, Any] = Depends(require_admin),
):
    ensure_training_enabled()
    jd_text, _ = read_uploaded(jd)
    resumes_data = [{"name": f.filename, "text": read_uploaded(f)[0]} for f in resumes]
    labels = json.loads(labels_json)
    return train_and_register_model(
        jd_text=jd_text,
        resumes_data=resumes_data,
        labels=labels,
        epochs=int(epochs),
        batch_size=int(batch_size),
        pos_threshold=int(pos_threshold),
        set_as_default=bool(set_as_default),
    )


@app.post("/auto-label")
async def auto_label_endpoint(
    jd: UploadFile = File(...),
    resumes: List[UploadFile] = File(...),
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    ensure_training_enabled()
    jd_text, _ = read_uploaded(jd)
    resumes_data = []

    for r in resumes:
        text, _ = read_uploaded(r)
        resumes_data.append({
            "name": r.filename,
            "text": text
        })

    base = get_cached_embedder(BASELINE_MODEL)
    labels, debug = auto_label_resumes(jd_text, resumes_data, base)

    return {
        "ok": True,
        "labels": labels,
        "debug": debug
    }


@app.post("/evaluate")
async def evaluate_ndcg(
    jd: UploadFile = File(...),
    resumes: List[UploadFile] = File(...),
    labels_json: str = Form(...),
    k: int = Form(10),
    model_choice: str = Form("default"),
    _: Dict[str, Any] = Depends(get_current_user_profile),
):
    ensure_training_enabled()
    jd_text, _ = read_uploaded(jd)
    resumes_data = [{"name": f.filename, "text": read_uploaded(f)[0]} for f in resumes]
    labels = json.loads(labels_json)

    names = [r["name"] for r in resumes_data]
    if len(labels) != len(names):
        return {
            "ok": False,
            "error": f"Labels count ({len(labels)}) must match resumes count ({len(names)})."
        }
    label_map = {names[i]: int(labels[i]) for i in range(len(names))}

    base = get_cached_embedder(BASELINE_MODEL)
    order_base = semantic_rank(jd_text, resumes_data, base)
    rels_base = [label_map.get(n, 0) for n in order_base]
    ndcg_base = ndcg_at_k(rels_base, min(int(k), len(rels_base)))

    ft, loaded = get_embedder(model_choice)
    order_ft = semantic_rank(jd_text, resumes_data, ft)
    rels_ft = [label_map.get(n, 0) for n in order_ft]
    ndcg_ft = ndcg_at_k(rels_ft, min(int(k), len(rels_ft)))

    return {
        "ok": True,
        "k": int(k),
        "baseline_model": BASELINE_MODEL,
        "finetuned_loaded": loaded,
        "evaluation_model": loaded,
        "ndcg_baseline": float(ndcg_base),
        "ndcg_finetuned": float(ndcg_ft),
    }


