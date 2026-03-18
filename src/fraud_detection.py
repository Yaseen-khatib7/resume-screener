from datetime import datetime, timezone
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from src.resume_sections import split_resume_sections
from src.skill_graph import extract_graph_skills
from src.skills import extract_skills


CURRENT_YEAR = datetime.now(timezone.utc).year
DATE_SEP = r"(?:-|to|â€“|â€”|until)"
TREND_TERMS = (
    "ai",
    "genai",
    "generative ai",
    "llm",
    "rag",
    "vector database",
    "vector store",
    "agentic ai",
    "microservices",
    "cloud native",
    "cloud-native",
    "mlops",
    "blockchain",
    "web3",
)
ADVANCED_SKILLS = {
    "langchain",
    "llamaindex",
    "rag",
    "vector database",
    "mlops",
    "kubernetes",
    "terraform",
    "pytorch",
    "transformers",
    "fastapi",
    "microservices",
    "blockchain",
}
GENERIC_COMPANY_TERMS = {
    "confidential company",
    "private company",
    "client project",
    "startup company",
    "organization",
    "company name",
    "self employed company",
}
ROLE_HINTS = {
    "engineer",
    "developer",
    "manager",
    "analyst",
    "consultant",
    "architect",
    "intern",
    "lead",
    "specialist",
    "scientist",
    "administrator",
    "tester",
    "designer",
}
MONTH_INDEX = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
TECH_INTRO_YEARS = {
    "react": 2013,
    "next.js": 2016,
    "nextjs": 2016,
    "fastapi": 2018,
    "langchain": 2022,
    "llamaindex": 2022,
    "rag": 2020,
    "kubernetes": 2014,
    "terraform": 2014,
    "docker": 2013,
    "pytorch": 2016,
    "openai": 2015,
    "genai": 2022,
}

WEIGHTS = {
    "experience": 30.0,
    "skill_stacking": 20.0,
    "buzzword": 20.0,
    "timeline": 20.0,
    "unsupported_claims": 10.0,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clean_lines(text: str) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _claimed_total_years(text: str) -> float | None:
    patterns = (
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+of\s+experience",
        r"experience\s+of\s+(\d+(?:\.\d+)?)\+?\s+years?",
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+experience",
        r"overall\s+experience\s+of\s+(\d+(?:\.\d+)?)",
    )
    values: List[float] = []
    lowered = text.lower()
    for pattern in patterns:
        for match in re.findall(pattern, lowered):
            try:
                values.append(float(match))
            except ValueError:
                continue
    return max(values) if values else None


def _education_year(text: str) -> int | None:
    section = split_resume_sections(text).get("education", "") or text.lower()
    years = [int(value) for value in re.findall(r"(19\d{2}|20\d{2})", section)]
    return max(years) if years else None


def _year_ranges(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    lowered = text.lower()
    pattern = rf"(19\d{{2}}|20\d{{2}})\s*{DATE_SEP}\s*(19\d{{2}}|20\d{{2}}|present|current)"
    for start, end in re.findall(pattern, lowered):
        start_year = int(start)
        end_year = CURRENT_YEAR if end in {"present", "current"} else int(end)
        if end_year >= start_year:
            ranges.append((start_year, end_year))
    return ranges


def _date_ranges_months(text: str) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    lowered = text.lower()
    pattern = re.compile(
        rf"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{{2}}|19\d{{2}})\s*"
        rf"{DATE_SEP}\s*"
        rf"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{{2}}|19\d{{2}})|present|current)"
    )
    for match in pattern.finditer(lowered):
        start_month = MONTH_INDEX[match.group(1)[:3]]
        start_year = int(match.group(2))
        if match.group(3) in {"present", "current"}:
            end_month = 12
            end_year = CURRENT_YEAR
        else:
            end_token = match.group(3).split()
            end_month = MONTH_INDEX[end_token[0][:3]]
            end_year = int(end_token[1])
        ranges.append((start_year * 12 + start_month, end_year * 12 + end_month))
    return ranges


def _tech_year_claims(text: str) -> List[Tuple[str, float]]:
    claims: List[Tuple[str, float]] = []
    pattern = re.compile(r"(\d+(?:\.\d+)?)\+?\s+years?\s+(?:of\s+)?([a-zA-Z0-9+.#/-]+)")
    for years_text, skill in pattern.findall(text.lower()):
        try:
            claims.append((skill.lower(), float(years_text)))
        except ValueError:
            continue
    return claims


def _parse_experience_headers(text: str) -> List[Dict[str, Any]]:
    lines = _clean_lines(split_resume_sections(text).get("experience", ""))
    entries: List[Dict[str, Any]] = []
    date_pattern = re.compile(
        rf"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+)?"
        rf"(19\d{{2}}|20\d{{2}})\s*{DATE_SEP}\s*"
        rf"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+)?"
        rf"(19\d{{2}}|20\d{{2}}|present|current)"
    )
    for line in lines:
        lowered = line.lower()
        match = date_pattern.search(lowered)
        if not match:
            continue
        entries.append(
            {
                "line": line,
                "has_role_hint": any(token in lowered for token in ROLE_HINTS),
                "has_company_hint": bool(re.search(r"\b(at|for|@)\b", lowered))
                or bool(re.search(r"(inc|llc|ltd|corp|technologies|systems|labs|solutions)", lowered)),
                "is_generic_company": any(term in lowered for term in GENERIC_COMPANY_TERMS),
            }
        )
    return entries


def _combine_resume_skills(resume_text: str, normalized_skills: Iterable[str] | None) -> List[str]:
    resume_skills, _ = extract_skills(resume_text)
    graph_skills = extract_graph_skills(resume_text).get("concepts", set())
    combined = sorted(
        {
            str(skill).strip().lower()
            for skill in set(resume_skills) | set(graph_skills) | {str(item).lower() for item in normalized_skills or []}
            if str(skill).strip()
        }
    )
    return combined


def _experience_inconsistency_signal(text: str) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    severity = 0.0
    claimed_years = _claimed_total_years(text)
    year_ranges = _year_ranges(text)
    graduation_year = _education_year(text)

    if claimed_years is None:
        return 0.0, []

    if year_ranges:
        visible_start = min(start for start, _ in year_ranges)
        visible_end = max(end for _, end in year_ranges)
        visible_span = max(0, visible_end - visible_start)
        if claimed_years > visible_span + 2.5:
            severity += 0.6
            reasons.append("Claimed experience appears inconsistent with employment timeline.")
        elif claimed_years > visible_span + 1.5:
            severity += 0.35
            reasons.append("Claimed years of experience appear somewhat higher than the visible work history.")

    if graduation_year:
        possible_post_grad_years = max(0, CURRENT_YEAR - graduation_year + 1)
        if claimed_years > possible_post_grad_years + 2:
            severity += 0.45
            reasons.append("Resume mentions unusually high years of experience compared to detected education timeline.")

    for tech, years in _tech_year_claims(text):
        intro_year = TECH_INTRO_YEARS.get(tech)
        if intro_year and years > (CURRENT_YEAR - intro_year + 1):
            severity += 0.35
            reasons.append(f"{tech.title()} experience appears longer than the technology has realistically existed in market.")
            break

    if claimed_years >= 12 and graduation_year and graduation_year >= CURRENT_YEAR - 6:
        severity += 0.35
        reasons.append("High total experience claims appear difficult to reconcile with recent graduation timing.")

    return _clamp01(severity), reasons


def _skill_stacking_signal(skill_names: Sequence[str], jd_text: str | None) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    severity = 0.0
    skills = {skill.lower() for skill in skill_names}
    total_skills = len(skills)

    if total_skills >= 30:
        severity += 0.7
        reasons.append("Resume contains an unusually broad technology stack.")
    elif total_skills >= 22:
        severity += 0.4
        reasons.append("Skill list appears inflated and may need manual verification.")

    cluster_map = {
        "frontend": {"react", "angular", "vue.js", "svelte", "next.js", "gatsby", "nuxt.js"},
        "mobile": {"flutter", "react native", "android development", "ios development", "swift", "kotlin"},
        "cloud": {"aws", "azure", "gcp", "terraform", "kubernetes"},
        "ai": {"llm engineering", "llm orchestration", "langchain", "llamaindex", "rag", "vector database", "mlops"},
    }
    cluster_hits = sum(1 for values in cluster_map.values() if len(skills & values) >= 3)
    if cluster_hits >= 3:
        severity += 0.35
        reasons.append("Resume spans many unrelated advanced domains at once, which deserves manual review.")

    advanced_count = len(skills & ADVANCED_SKILLS)
    if advanced_count >= 7:
        severity += 0.2
        reasons.append("Resume lists many advanced tools together with limited specialization detail.")

    if jd_text:
        jd_skills, _ = extract_skills(jd_text)
        jd_graph = extract_graph_skills(jd_text).get("concepts", set())
        jd_pool = {item.lower() for item in set(jd_skills) | set(jd_graph)}
        if jd_pool:
            overlap_ratio = len(skills & jd_pool) / max(1, len(jd_pool))
            if overlap_ratio >= 0.55:
                severity -= 0.3
                reasons.append("Most listed skills align closely with this job description, lowering fraud concern.")
            elif overlap_ratio >= 0.35:
                severity -= 0.15
                reasons.append("Skill breadth is materially relevant to this role.")

    return _clamp01(severity), reasons


def _buzzword_signal(text: str) -> Tuple[float, List[str]]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9+#./-]+", lowered)
    hits_by_term: Dict[str, int] = {}
    for term in TREND_TERMS:
        hits_by_term[term] = len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered))

    total_hits = sum(hits_by_term.values())
    density = total_hits / max(1, len(tokens))
    repeated = [term for term, count in hits_by_term.items() if count >= 3]
    severity = 0.0
    reasons: List[str] = []

    if total_hits >= 12 or density >= 0.035:
        severity += 0.7
        reasons.append("High concentration of buzzwords detected with limited contextual balance.")
    elif total_hits >= 7 or density >= 0.025:
        severity += 0.4
        reasons.append("Resume may contain keyword stuffing.")

    if len(repeated) >= 2:
        severity += 0.2
        reasons.append("Some trend-heavy terms are repeated unusually often.")

    return _clamp01(severity), reasons


def _timeline_anomaly_signal(text: str) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    severity = 0.0
    month_ranges = sorted(_date_ranges_months(text))
    parsed_headers = _parse_experience_headers(text)
    malformed_headers = [
        item for item in parsed_headers if not item["has_role_hint"] or not item["has_company_hint"] or item["is_generic_company"]
    ]

    overlap_count = 0
    short_tenure_count = 0
    for idx, (start, end) in enumerate(month_ranges):
        if max(0, end - start) < 3:
            short_tenure_count += 1
        if idx > 0 and start < month_ranges[idx - 1][1] - 2:
            overlap_count += 1

    if overlap_count >= 2:
        severity += 0.6
        reasons.append("Multiple overlapping employment periods detected.")
    elif overlap_count == 1:
        severity += 0.3
        reasons.append("Employment timeline appears inconsistent.")

    if short_tenure_count >= 3:
        severity += 0.2
        reasons.append("Resume shows many very short roles in sequence, which may indicate unreliable timeline reporting.")

    if parsed_headers and len(malformed_headers) >= 2:
        severity += 0.25
        reasons.append("Several work entries have malformed company, role, or date structure.")
    elif split_resume_sections(text).get("experience", "").strip() and not parsed_headers:
        severity += 0.3
        reasons.append("Employment history lacks enough date structure to verify chronology.")

    return _clamp01(severity), reasons


def _unsupported_claims_signal(text: str, skill_names: Sequence[str]) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    severity = 0.0
    sections = split_resume_sections(text)
    experience_text = sections.get("experience", "")
    projects_text = sections.get("projects", "")
    evidence_text = f"{experience_text}\n{projects_text}".lower()
    claimed_advanced = [skill for skill in skill_names if skill.lower() in ADVANCED_SKILLS]
    unsupported = [skill for skill in claimed_advanced if skill.lower() not in evidence_text]

    if len(unsupported) >= 5:
        severity += 0.8
        reasons.append("Advanced skill claims are not well supported by project or experience details.")
    elif len(unsupported) >= 3:
        severity += 0.5
        reasons.append("Claimed technologies lack supporting evidence in work history.")

    if claimed_advanced and not projects_text.strip() and not experience_text.strip():
        severity += 0.35
        reasons.append("Resume lists advanced technologies without clear project or work evidence.")

    company_lines = _clean_lines(experience_text)
    vague_company_lines = [
        line for line in company_lines
        if any(term in line.lower() for term in GENERIC_COMPANY_TERMS)
        or ("company" in line.lower() and not re.search(r"(inc|llc|ltd|corp|technologies|systems|labs)", line.lower()))
    ]
    if len(vague_company_lines) >= 2:
        severity += 0.2
        reasons.append("Employment history uses vague company references that are hard to verify.")

    return _clamp01(severity), reasons


def _dedupe_reasons(reasons: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for reason in reasons:
        key = reason.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(reason.strip())
    return deduped


def _score_to_status(score: float) -> Tuple[str, str]:
    if score >= 65:
        return "High Risk", "Flag for Verification"
    if score >= 35:
        return "Medium Risk", "Review Carefully"
    return "Low Risk", "Proceed"


def detect_resume_fraud(
    resume_text: str,
    candidate_name: str = "",
    *,
    normalized_skills: Iterable[str] | None = None,
    jd_text: str | None = None,
) -> Dict[str, Any]:
    del candidate_name  # reserved for downstream logging/personalized reasons

    text = resume_text or ""
    combined_skills = _combine_resume_skills(text, normalized_skills)

    category_results = {
        "experience": _experience_inconsistency_signal(text),
        "skill_stacking": _skill_stacking_signal(combined_skills, jd_text),
        "buzzword": _buzzword_signal(text),
        "timeline": _timeline_anomaly_signal(text),
        "unsupported_claims": _unsupported_claims_signal(text, combined_skills),
    }

    total_score = 0.0
    reasons: List[str] = []
    for category, (severity, category_reasons) in category_results.items():
        total_score += _clamp01(severity) * WEIGHTS[category]
        reasons.extend(category_reasons)

    score = round(max(0.0, min(100.0, total_score)), 1)
    status, recommendation = _score_to_status(score)
    deduped_reasons = _dedupe_reasons(reasons)
    if not deduped_reasons:
        deduped_reasons = ["No strong fraud signals were detected from the visible resume text."]

    return {
        "fraudRiskScore": score,
        "fraudStatus": status,
        "fraudReasons": deduped_reasons[:6],
        "fraudRecommendation": recommendation,
    }


def analyze_resume_fraud(
    *,
    resume_text: str,
    normalized_skills: Iterable[str] | None = None,
    jd_text: str | None = None,
) -> Dict[str, Any]:
    return detect_resume_fraud(
        resume_text=resume_text,
        normalized_skills=normalized_skills,
        jd_text=jd_text,
    )
