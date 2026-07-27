import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.auto_label import auto_label_resumes
from src.model_registry import ensure_registry, list_models
from src.parsing import load_uploaded_file

import backend.main as backend_app

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - dependency/runtime guard
    raise RuntimeError(
        "The 'mcp' package is required to run the MCP server. Install dependencies with "
        "'pip install -r requirements.txt'."
    ) from exc


class ResumeInput(BaseModel):
    name: str = Field(..., description="Display name for the resume.")
    text: str = Field(..., description="Extracted plain-text resume content.")


class ScreeningFileResult(BaseModel):
    name: str
    path: str
    chars: int
    warnings: list[dict[str, Any]] = Field(default_factory=list)


mcp = FastMCP(
    "Resume Screening MCP",
    instructions=(
        "Tools for screening resumes against job descriptions, evaluating model quality, "
        "and reading ATS/config state from the local resume-screening-model project."
    ),
    json_response=True,
    stateless_http=True,
)


def _ensure_models_ready() -> None:
    ensure_registry(backend_app.BASELINE_MODEL, backend_app.FINETUNED_ROOT)


def _safe_question_settings() -> dict[str, Any]:
    try:
        return backend_app._load_question_settings()
    except Exception:
        return {"enabled": True, "source": "fallback"}


def _safe_skill_graph() -> dict[str, Any]:
    try:
        return backend_app._load_skill_graph_config()
    except Exception:
        return backend_app.export_skill_graph()


def _read_text_from_path(path: str) -> tuple[str, list[dict[str, Any]]]:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    raw = file_path.read_bytes()
    if not backend_app.bytes_limit_ok(raw):
        return "", [{
            "file": file_path.name,
            "severity": "error",
            "message": f"File too large (> {backend_app.MAX_FILE_MB}MB)",
        }]

    text = (load_uploaded_file(file_path.name, raw) or "").strip()
    warnings: list[dict[str, Any]] = []
    if len(text) < backend_app.MIN_TEXT_CHARS:
        warnings.append({
            "file": file_path.name,
            "severity": "warning",
            "message": "Low extracted text. Resume may be scanned or image-based.",
        })
    if file_path.suffix.lower() == ".pdf" and len(text) < backend_app.MIN_PDF_TEXT_CHARS:
        warnings.append({
            "file": file_path.name,
            "severity": "warning",
            "message": "PDF appears scanned. Upload text-based PDF or DOCX for better results.",
        })
    return text, warnings


def _persist_screening_session(ranked: list[dict[str, Any]], shortlist: list[dict[str, Any]]) -> dict[str, Any]:
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    session_dir = backend_app.safe_session_dir(session_id)
    ats_state = backend_app.sync_ats_candidates(
        session_dir,
        ranked,
        [item["candidate"] for item in shortlist],
    )
    return {
        "session_id": session_id,
        "ats": ats_state,
    }


def _effective_mcp_host() -> str:
    return os.getenv("MCP_HOST", "127.0.0.1")


def _effective_mcp_port() -> int:
    raw = os.getenv("MCP_PORT", "8001")
    return int(raw)


def _document_for_resource(doc_id: str, title: str, uri: str, payload: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": title,
        "text": json.dumps(payload, indent=2),
        "url": uri,
        "metadata": metadata or {},
    }


def _list_ats_session_ids(limit: int = 50) -> list[str]:
    storage_root = Path(backend_app.STORAGE_ROOT)
    if not storage_root.exists():
        return []
    session_ids = [
        entry.name
        for entry in storage_root.iterdir()
        if entry.is_dir() and entry.name.startswith("sess_")
    ]
    session_ids.sort(reverse=True)
    return session_ids[:limit]


def _build_document_index() -> list[dict[str, Any]]:
    docs = [
        _document_for_resource(
            "models",
            "Model Registry",
            "resume-screening://models",
            {"ok": True, **list_models(backend_app.BASELINE_MODEL, backend_app.FINETUNED_ROOT)},
            {"category": "config", "resource": "models"},
        ),
        _document_for_resource(
            "question-settings",
            "Question Settings",
            "resume-screening://question-settings",
            _safe_question_settings(),
            {"category": "config", "resource": "question-settings"},
        ),
        _document_for_resource(
            "skill-graph",
            "Skill Graph",
            "resume-screening://skill-graph",
            _safe_skill_graph(),
            {"category": "config", "resource": "skill-graph"},
        ),
    ]

    for session_id in _list_ats_session_ids():
        session_dir = backend_app.safe_session_dir(session_id)
        try:
            payload = {"ok": True, "session_id": session_id, **backend_app.load_ats_state(session_dir)}
        except Exception:
            continue
        docs.append(
            _document_for_resource(
                f"ats:{session_id}",
                f"ATS Session {session_id}",
                f"resume-screening://ats/{session_id}",
                payload,
                {
                    "category": "ats-session",
                    "resource": "ats",
                    "session_id": session_id,
                    "candidate_count": len(payload.get("candidates", [])),
                },
            )
        )

    return docs


def _tokenize_search_query(query: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_./-]+", (query or "").lower()) if token]


def _score_document(query_tokens: list[str], doc: dict[str, Any]) -> float:
    haystack = " ".join(
        [
            str(doc.get("title", "")).lower(),
            str(doc.get("url", "")).lower(),
            json.dumps(doc.get("metadata", {}), ensure_ascii=True).lower(),
            str(doc.get("text", "")).lower(),
        ]
    )
    score = 0.0
    for token in query_tokens:
        count = haystack.count(token)
        if count:
            score += min(count, 5)
            if token in str(doc.get("title", "")).lower():
                score += 2.0
            if token in str(doc.get("url", "")).lower():
                score += 1.0
    return score


def _snippet_for_query(doc_text: str, query_tokens: list[str], max_chars: int = 600) -> str:
    text = " ".join((doc_text or "").split())
    if not text:
        return ""
    if not query_tokens:
        return text[:max_chars]

    lowered = text.lower()
    best_pos = min(
        (lowered.find(token) for token in query_tokens if lowered.find(token) >= 0),
        default=-1,
    )
    if best_pos < 0:
        return text[:max_chars]

    start = max(best_pos - (max_chars // 3), 0)
    end = min(start + max_chars, len(text))
    return text[start:end]


@mcp.tool()
def server_info() -> dict[str, Any]:
    """Return the MCP server configuration and supported capabilities."""
    return {
        "name": "Resume Screening MCP",
        "backend_module": "backend.main",
        "http_endpoint": f"http://{_effective_mcp_host()}:{_effective_mcp_port()}{mcp.settings.streamable_http_path}",
        "transports": ["stdio", "streamable-http"],
        "tools": [
            "server_info",
            "search",
            "fetch",
            "get_models",
            "screen_text",
            "screen_files",
            "get_ats_state",
            "update_ats_candidate",
            "auto_label_text",
            "evaluate_text",
        ],
        "resources": [
            "resume-screening://models",
            "resume-screening://question-settings",
            "resume-screening://skill-graph",
            "resume-screening://ats/{session_id}",
        ],
    }


@mcp.tool()
def search(query: str, limit: int = 8) -> dict[str, Any]:
    """Search read-only project documents using a ChatGPT-friendly search/fetch pattern."""
    _ensure_models_ready()
    capped_limit = max(1, min(int(limit), 20))
    query_tokens = _tokenize_search_query(query)
    docs = _build_document_index()

    ranked = []
    for doc in docs:
        score = _score_document(query_tokens, doc)
        if query_tokens and score <= 0:
            continue
        ranked.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "text": _snippet_for_query(doc["text"], query_tokens),
                "url": doc["url"],
                "metadata": {
                    **doc.get("metadata", {}),
                    "score": score,
                },
            }
        )

    if not query_tokens:
        ranked = [
            {
                "id": doc["id"],
                "title": doc["title"],
                "text": _snippet_for_query(doc["text"], []),
                "url": doc["url"],
                "metadata": {
                    **doc.get("metadata", {}),
                    "score": 0.0,
                },
            }
            for doc in docs
        ]

    ranked.sort(key=lambda item: (item["metadata"]["score"], item["title"]), reverse=True)
    return {
        "ok": True,
        "query": query,
        "results": ranked[:capped_limit],
    }


@mcp.tool()
def fetch(id: str) -> dict[str, Any]:
    """Fetch a full read-only project document by id or resource URI."""
    _ensure_models_ready()
    normalized = (id or "").strip()
    for doc in _build_document_index():
        if normalized in {doc["id"], doc["url"]}:
            return {
                "ok": True,
                "document": doc,
            }
    return {
        "ok": False,
        "error": f"Document not found: {normalized}",
    }


@mcp.tool()
def get_models() -> dict[str, Any]:
    """List baseline and fine-tuned screening models."""
    _ensure_models_ready()
    return {
        "ok": True,
        **list_models(backend_app.BASELINE_MODEL, backend_app.FINETUNED_ROOT),
    }


@mcp.tool()
def screen_text(
    job_description: str,
    resumes: list[ResumeInput],
    match_style: float = 0.4,
    cutoff: int = 60,
    model_choice: str = "best",
    auto_improve: bool = True,
    persist_session: bool = True,
) -> dict[str, Any]:
    """Screen in-memory resume text against a job description."""
    _ensure_models_ready()
    resumes_data = [{"name": item.name, "text": item.text} for item in resumes]
    result = backend_app.apply_ats_gate(
        jd_text=job_description,
        resumes_data=resumes_data,
        match_style=match_style,
        cutoff=cutoff,
        model_choice=model_choice,
        auto_improve=auto_improve,
    )
    result["ok"] = True
    result["extractionStats"] = {
        "jdChars": len(job_description or ""),
        "resumeChars": {item["name"]: len(item["text"] or "") for item in resumes_data},
    }
    if persist_session:
        result.update(_persist_screening_session(result["ranked"], result["shortlist"]))
    return result


@mcp.tool()
def screen_files(
    job_description_path: str,
    resume_paths: list[str],
    match_style: float = 0.4,
    cutoff: int = 60,
    model_choice: str = "best",
    auto_improve: bool = True,
    persist_session: bool = True,
) -> dict[str, Any]:
    """Screen resumes by reading PDF, DOCX, TXT, or MD files from local disk."""
    _ensure_models_ready()
    jd_text, jd_warnings = _read_text_from_path(job_description_path)
    warnings = list(jd_warnings)

    resumes_data: list[dict[str, str]] = []
    extracted_files: list[ScreeningFileResult] = []
    for path in resume_paths:
        resume_text, file_warnings = _read_text_from_path(path)
        warnings.extend(file_warnings)
        file_path = Path(path).expanduser().resolve()
        resumes_data.append({"name": file_path.name, "text": resume_text})
        extracted_files.append(
            ScreeningFileResult(
                name=file_path.name,
                path=str(file_path),
                chars=len(resume_text),
                warnings=file_warnings,
            )
        )

    result = backend_app.apply_ats_gate(
        jd_text=jd_text,
        resumes_data=resumes_data,
        match_style=match_style,
        cutoff=cutoff,
        model_choice=model_choice,
        auto_improve=auto_improve,
    )
    result["ok"] = True
    result["warnings"] = warnings + result.get("warnings", [])
    result["files"] = {
        "job_description_path": str(Path(job_description_path).expanduser().resolve()),
        "resumes": [item.model_dump() for item in extracted_files],
    }
    result["extractionStats"] = {
        "jdChars": len(jd_text),
        "resumeChars": {item["name"]: len(item["text"]) for item in resumes_data},
    }
    if persist_session:
        result.update(_persist_screening_session(result["ranked"], result["shortlist"]))
    return result


@mcp.tool()
def get_ats_state(session_id: str) -> dict[str, Any]:
    """Read stored ATS state for a screening session."""
    session_dir = backend_app.safe_session_dir(session_id)
    if not os.path.exists(session_dir):
        return {"ok": False, "error": "No ATS session found for this session_id"}
    return {"ok": True, "session_id": session_id, **backend_app.load_ats_state(session_dir)}


@mcp.tool()
def update_ats_candidate(
    session_id: str,
    candidate: str,
    stage: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Update ATS stage or notes for one candidate in a stored session."""
    session_dir = backend_app.safe_session_dir(session_id)
    if not os.path.exists(session_dir):
        return {"ok": False, "error": "No ATS session found for this session_id"}
    try:
        updated = backend_app.update_ats_candidate(
            session_dir,
            candidate=candidate,
            stage=stage,
            notes=notes,
        )
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "session_id": session_id, "candidate_state": updated}


@mcp.tool()
def auto_label_text(job_description: str, resumes: list[ResumeInput]) -> dict[str, Any]:
    """Generate weak labels for resumes against a job description using the baseline embedder."""
    backend_app.ensure_training_enabled()
    _ensure_models_ready()
    resumes_data = [{"name": item.name, "text": item.text} for item in resumes]
    base = backend_app.get_cached_embedder(backend_app.BASELINE_MODEL)
    labels, debug = auto_label_resumes(job_description, resumes_data, base)
    return {
        "ok": True,
        "labels": labels,
        "debug": debug,
    }


@mcp.tool()
def evaluate_text(
    job_description: str,
    resumes: list[ResumeInput],
    labels: list[int],
    k: int = 10,
    model_choice: str = "default",
) -> dict[str, Any]:
    """Evaluate baseline and selected model ranking quality using NDCG@K."""
    backend_app.ensure_training_enabled()
    _ensure_models_ready()
    resumes_data = [{"name": item.name, "text": item.text} for item in resumes]

    names = [item["name"] for item in resumes_data]
    if len(labels) != len(names):
        return {
            "ok": False,
            "error": f"Labels count ({len(labels)}) must match resumes count ({len(names)}).",
        }
    label_map = {names[i]: int(labels[i]) for i in range(len(names))}

    base = backend_app.get_cached_embedder(backend_app.BASELINE_MODEL)
    order_base = backend_app.semantic_rank(job_description, resumes_data, base)
    rels_base = [label_map.get(name, 0) for name in order_base]
    ndcg_base = backend_app.ndcg_at_k(rels_base, min(int(k), len(rels_base)))

    finetuned, loaded = backend_app.get_embedder(model_choice)
    order_ft = backend_app.semantic_rank(job_description, resumes_data, finetuned)
    rels_ft = [label_map.get(name, 0) for name in order_ft]
    ndcg_ft = backend_app.ndcg_at_k(rels_ft, min(int(k), len(rels_ft)))

    return {
        "ok": True,
        "k": int(k),
        "baseline_model": backend_app.BASELINE_MODEL,
        "finetuned_loaded": loaded,
        "evaluation_model": loaded,
        "ndcg_baseline": float(ndcg_base),
        "ndcg_finetuned": float(ndcg_ft),
        "baseline_order": order_base,
        "evaluation_order": order_ft,
    }


@mcp.resource("resume-screening://models")
def models_resource() -> str:
    """Read-only resource exposing model registry metadata."""
    _ensure_models_ready()
    payload = {
        "ok": True,
        **list_models(backend_app.BASELINE_MODEL, backend_app.FINETUNED_ROOT),
    }
    return json.dumps(payload, indent=2)


@mcp.resource("resume-screening://question-settings")
def question_settings_resource() -> str:
    """Read-only resource exposing interview question toggle settings."""
    return json.dumps(_safe_question_settings(), indent=2)


@mcp.resource("resume-screening://skill-graph")
def skill_graph_resource() -> str:
    """Read-only resource exposing the active skill graph."""
    return json.dumps(_safe_skill_graph(), indent=2)


@mcp.resource("resume-screening://ats/{session_id}")
def ats_resource(session_id: str) -> str:
    """Read-only resource exposing ATS state for one saved screening session."""
    session_dir = backend_app.safe_session_dir(session_id)
    payload: dict[str, Any]
    if os.path.exists(session_dir):
        payload = {"ok": True, "session_id": session_id, **backend_app.load_ats_state(session_dir)}
    else:
        payload = {"ok": False, "session_id": session_id, "error": "No ATS session found for this session_id"}
    return json.dumps(payload, indent=2)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT must be either 'stdio' or 'streamable-http'")

    mcp.settings.host = os.getenv("MCP_HOST", "127.0.0.1")
    mcp.settings.port = int(os.getenv("MCP_PORT", "8001"))
    _ensure_models_ready()
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
