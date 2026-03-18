import json
from pathlib import Path
import re
from functools import lru_cache
from rapidfuzz import fuzz
from typing import Dict, Set, Tuple


BASE_SKILLS = {
    "python", "java", "c++", "c", "javascript", "typescript", "sql", "bash",
    "node.js", "express", "fastapi", "django", "flask", "rest api", "graphql",
    "postgresql", "mysql", "mongodb", "redis",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ci/cd", "jenkins",
    "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow", "keras", "xgboost",
    "machine learning", "deep learning", "neural networks", "nlp", "computer vision", "llm",
    "supervised learning", "unsupervised learning", "model evaluation", "feature engineering",
    "hyperparameter tuning", "classification", "regression", "clustering", "recommendation systems",
    "data pipelines", "model deployment", "model monitoring", "mlops",
    "spark", "hadoop", "airflow", "tableau", "power bi",
    "git", "linux", "statistics", "data science",
}

BASE_ALIASES = {
    "postgres": "postgresql",
    "postgre": "postgresql",
    "node": "node.js",
    "k8s": "kubernetes",
    "google cloud platform": "gcp",
    "amazon web services": "aws",
    "microsoft azure": "azure",
    "powerbi": "power bi",
    "cicd": "ci/cd",
    "ci cd": "ci/cd",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "tensor flow": "tensorflow",
    "py torch": "pytorch",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
    "natural language processing": "nlp",
    "cv": "computer vision",
    "recommender systems": "recommendation systems",
    "recommendation system": "recommendation systems",
    "feature extraction": "feature engineering",
    "model tuning": "hyperparameter tuning",
    "ml ops": "mlops",
    "m.l.ops": "mlops",
    "rest": "rest api",
    "node js": "node.js",
    "react js": "react",
    "next js": "next.js",
    "vue js": "vue.js",
    "express js": "express",
    "mongo db": "mongodb",
    "postgre sql": "postgresql",
    "gen ai": "genai",
    "large language models": "llm",
}

GRAPH_DATA_PATH = Path(__file__).with_name("skill_graph_data.json")
PREF_HINTS = ["nice to have", "preferred", "bonus", "good to have", "plus"]
REQ_HINTS = ["must have", "required", "requirements", "we require", "minimum qualifications", "must possess"]


def _load_graph_terms() -> Tuple[Set[str], Dict[str, str]]:
    skills = set(BASE_SKILLS)
    aliases = dict(BASE_ALIASES)
    if not GRAPH_DATA_PATH.exists():
        return skills, aliases

    raw = json.loads(GRAPH_DATA_PATH.read_text(encoding="utf-8"))
    for concept, payload in raw.items():
        canonical = concept.strip().lower()
        skills.add(canonical)

        label = str(payload.get("label") or "").strip().lower()
        if label and label != canonical:
            aliases[label] = canonical

        for alias in payload.get("aliases", []):
            cleaned = str(alias).strip().lower()
            if cleaned:
                aliases[cleaned] = canonical
                skills.add(cleaned)
    return skills, aliases


SKILLS, ALIASES = _load_graph_terms()


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("|", " ")
    s = s.replace("/", " / ")
    s = s.replace("(", " ").replace(")", " ")
    s = s.replace(",", " ").replace(";", " ")
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


@lru_cache(maxsize=2048)
def _skill_pattern(skill: str) -> re.Pattern[str]:
    escaped = re.escape(skill)
    return re.compile(rf"(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])")


def _contains_skill(text: str, skill: str) -> bool:
    return _skill_pattern(skill).search(text) is not None


@lru_cache(maxsize=256)
def _extract_skills_cached(text: str, fuzzy_threshold: int) -> tuple[tuple[str, ...], tuple[tuple[str, float], ...]]:
    if not text:
        return tuple(), tuple()

    lowered = text.lower()
    lowered = lowered.replace("|", " ")
    lowered = lowered.replace("â€¢", " ")
    lowered = lowered.replace(",", " ")
    lowered = lowered.replace(";", " ")
    found: Dict[str, float] = {}

    for skill in SKILLS:
        if _contains_skill(lowered, skill):
            canonical = ALIASES.get(skill, skill)
            found[canonical] = max(found.get(canonical, 0.0), 1.0)

    for alias, canonical in ALIASES.items():
        if _contains_skill(lowered, alias):
            found[canonical] = max(found.get(canonical, 0.0), 0.96)

    tokens = re.findall(r"[a-zA-Z0-9\+\#\.\/-]+", lowered)
    grams = set(tokens)
    for size in (2, 3, 4):
        for idx in range(len(tokens) - size + 1):
            grams.add(" ".join(tokens[idx:idx + size]))

    for gram in grams:
        normalized = _norm(gram)
        if normalized in SKILLS:
            canonical = ALIASES.get(normalized, normalized)
            found[canonical] = max(found.get(canonical, 0.0), 0.92)
            continue

        if len(normalized) < 4:
            continue

        best_skill = None
        best_score = 0
        for skill in SKILLS:
            if abs(len(skill) - len(normalized)) > 3:
                continue
            score = fuzz.ratio(normalized, skill)
            if score > best_score:
                best_skill = skill
                best_score = score

        if best_skill and best_score >= fuzzy_threshold:
            canonical = ALIASES.get(best_skill, best_skill)
            found[canonical] = max(found.get(canonical, 0.0), (best_score / 100.0) * 0.82)

    return tuple(sorted(found.keys())), tuple(sorted(found.items()))


def extract_skills(text: str, fuzzy_threshold: int = 92) -> Tuple[Set[str], Dict[str, float]]:
    keys, items = _extract_skills_cached(text or "", fuzzy_threshold)
    return set(keys), dict(items)


def split_jd_required_preferred(jd_text: str) -> Tuple[Set[str], Set[str]]:
    if not jd_text:
        return set(), set()

    lowered = jd_text.lower()

    preferred_cut = None
    for hint in PREF_HINTS:
        idx = lowered.find(hint)
        if idx != -1:
            preferred_cut = idx
            break

    required_start = 0
    for hint in REQ_HINTS:
        idx = lowered.find(hint)
        if idx != -1:
            required_start = idx
            break

    required_block = jd_text[required_start:preferred_cut] if preferred_cut is not None else jd_text[required_start:]
    preferred_block = jd_text[preferred_cut:] if preferred_cut is not None else ""

    req, _ = extract_skills(required_block)
    pref, _ = extract_skills(preferred_block) if preferred_block else (set(), {})

    if not req and not pref:
        req, _ = extract_skills(jd_text)

    return req, pref - req


def coverage(resume_skills: Set[str], jd_req: Set[str], jd_pref: Set[str]) -> Tuple[float, float]:
    req_cov = (len(resume_skills & jd_req) / len(jd_req)) if jd_req else 0.0
    pref_cov = (len(resume_skills & jd_pref) / len(jd_pref)) if jd_pref else 0.0
    return req_cov, pref_cov
