import re
from typing import Any, Dict, List, Sequence

from src.resume_sections import split_resume_sections


WEAK_BULLET_PREFIXES = (
    "worked on",
    "responsible for",
    "helped with",
    "involved in",
    "participated in",
    "handled",
    "did",
    "supported",
    "assisted with",
)
STRONG_ACTION_VERBS = (
    "built",
    "developed",
    "designed",
    "improved",
    "optimized",
    "implemented",
    "led",
    "launched",
    "created",
    "architected",
    "automated",
    "delivered",
    "reduced",
    "increased",
)
FILLER_PHRASES = (
    "team player",
    "hardworking",
    "detail oriented",
    "good communication",
    "quick learner",
    "self motivated",
    "go getter",
)
MEASUREMENT_HINTS = (
    "%",
    "percent",
    "x",
    "ms",
    "seconds",
    "minutes",
    "hours",
    "days",
    "users",
    "customers",
    "requests",
    "latency",
    "throughput",
    "revenue",
    "cost",
    "accuracy",
    "growth",
    "uptime",
    "mrr",
)

WEIGHTS = {
    "sections": 20.0,
    "bullet_quality": 20.0,
    "quantified_achievements": 20.0,
    "readability": 15.0,
    "ats_presentation": 10.0,
    "description_strength": 15.0,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clean_lines(text: str) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _bullet_candidates(text: str) -> List[str]:
    bullets: List[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip(" \t\r\n-â€¢")
        if len(stripped) < 12:
            continue
        if line.strip().startswith(("-", "â€¢")):
            bullets.append(stripped)
            continue
        if re.match(r"^[A-Za-z].{20,}$", stripped):
            bullets.append(stripped)
    return bullets


def _is_weak_bullet(bullet: str) -> bool:
    lowered = bullet.lower().strip()
    return lowered.startswith(WEAK_BULLET_PREFIXES) and not re.search(r"\d", lowered)


def _is_strong_bullet(bullet: str) -> bool:
    lowered = bullet.lower().strip()
    return lowered.startswith(STRONG_ACTION_VERBS)


def _is_measurable_bullet(bullet: str) -> bool:
    lowered = bullet.lower()
    return bool(re.search(r"\d", lowered) and any(hint in lowered for hint in MEASUREMENT_HINTS))


def _section_presence_signal(sections: Dict[str, str]) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    expected = ("skills", "experience", "education", "projects")
    missing = [name for name in expected if not (sections.get(name) or "").strip()]
    present_count = len(expected) - len(missing)
    severity = 1.0 if present_count == 4 else 0.75 if present_count == 3 else 0.45 if present_count == 2 else 0.2

    if present_count >= 3:
        reasons.append("Resume contains clear standard sections.")
    if "skills" in missing:
        reasons.append("Resume is missing a dedicated Skills section.")
        suggestions.append("Add a clear Skills section.")
    if "experience" in missing:
        reasons.append("Resume is missing a clear Experience section.")
        suggestions.append("Add a dedicated Experience or Work Experience section.")
    if "education" in missing:
        reasons.append("Resume is missing a clear Education section.")
        suggestions.append("Add a dedicated Education section.")
    if "projects" in missing:
        reasons.append("Resume is missing a dedicated Projects section.")
        suggestions.append("Include a dedicated Projects section if applicable.")

    return severity, reasons, suggestions


def _bullet_quality_signal(bullets: Sequence[str]) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    if not bullets:
        return 0.4, ["Resume has limited bullet-style detail in experience or project descriptions."], [
            "Break experience and project details into concise action-oriented bullet points."
        ]

    weak = [bullet for bullet in bullets if _is_weak_bullet(bullet)]
    strong = [bullet for bullet in bullets if _is_strong_bullet(bullet)]
    strong_ratio = len(strong) / max(1, len(bullets))
    weak_ratio = len(weak) / max(1, len(bullets))
    severity = 0.55 + (strong_ratio * 0.4) - (weak_ratio * 0.35)
    severity = _clamp01(severity)

    if weak_ratio >= 0.3:
        reasons.append("Several experience bullets are vague and generic.")
        suggestions.append("Replace vague phrases like 'worked on' with clear action verbs.")
        suggestions.append("Rewrite responsibilities as concrete achievements.")
    if strong_ratio >= 0.35:
        reasons.append("Resume includes concrete action-oriented bullet points.")

    return severity, reasons, suggestions


def _quantified_achievement_signal(bullets: Sequence[str]) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    measurable = [bullet for bullet in bullets if _is_measurable_bullet(bullet)]

    if len(measurable) >= 3:
        severity = 1.0
        reasons.append("Resume includes measurable impact in work or project descriptions.")
    elif len(measurable) >= 1:
        severity = 0.7
        reasons.append("Resume includes some quantified achievements.")
    else:
        severity = 0.25
        reasons.append("Resume lacks quantified achievements.")
        suggestions.append("Add metrics such as percentages, user counts, or performance improvements.")
        suggestions.append("Quantify project outcomes where possible.")

    return severity, reasons, suggestions


def _readability_signal(resume_text: str) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    lowered = resume_text.lower()
    sentence_candidates = [item.strip() for item in re.split(r"[.\n]+", resume_text) if item.strip()]
    avg_sentence_words = (
        sum(len(item.split()) for item in sentence_candidates) / len(sentence_candidates)
        if sentence_candidates
        else 0.0
    )
    long_lines = [line for line in _clean_lines(resume_text) if len(line.split()) >= 30]
    filler_hits = [phrase for phrase in FILLER_PHRASES if phrase in lowered]
    symbol_density = len(re.findall(r"[^\w\s.,()/%+-]", resume_text)) / max(1, len(resume_text))

    severity = 0.9
    if avg_sentence_words > 28:
        severity -= 0.2
    if len(long_lines) >= 3:
        severity -= 0.2
    if filler_hits:
        severity -= min(0.15, len(filler_hits) * 0.04)
    if symbol_density > 0.06:
        severity -= 0.1
    severity = max(0.2, severity)

    if severity >= 0.75:
        reasons.append("Resume is generally readable and well-organized.")
    if avg_sentence_words > 28 or len(long_lines) >= 3:
        reasons.append("Some sections are dense and hard to scan quickly.")
        suggestions.append("Break long paragraphs into bullet points.")
    if filler_hits or symbol_density > 0.06:
        reasons.append("Formatting or filler wording reduces clarity in places.")
        suggestions.append("Use consistent formatting and spacing.")

    return severity, reasons, suggestions


def _ats_presentation_signal(
    sections: Dict[str, str],
    resume_text: str,
    ats_score: float,
    ats_status: str | None,
) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    section_labels_present = sum(1 for key in ("skills", "experience", "education", "projects") if (sections.get(key) or "").strip())
    extracted_len = len((resume_text or "").strip())
    suspicious_symbols = len(re.findall(r"[|]{2,}|[_]{3,}|[~]{2,}", resume_text))

    severity = 0.55 + min(0.3, max(0.0, ats_score / 100.0) * 0.3)
    if section_labels_present >= 3:
        severity += 0.15
        reasons.append("Resume uses ATS-friendly section headings.")
    if extracted_len < 350:
        severity -= 0.2
        reasons.append("Low extracted text volume may reduce readability and parsing.")
        suggestions.append("Use a cleaner text-based resume file with readable section headings.")
    if suspicious_symbols:
        severity -= 0.15
        reasons.append("Formatting may reduce readability and parsing.")
        suggestions.append("Remove heavy decorative symbols and simplify layout.")
    if ats_status == "FAIL":
        severity -= 0.2
    severity = _clamp01(severity)

    return severity, reasons, suggestions


def _description_strength_signal(sections: Dict[str, str]) -> tuple[float, List[str], List[str]]:
    reasons: List[str] = []
    suggestions: List[str] = []
    experience_lines = _clean_lines(sections.get("experience", ""))
    project_lines = _clean_lines(sections.get("projects", ""))
    bullets = _bullet_candidates("\n".join(experience_lines + project_lines))
    detailed_lines = [
        bullet for bullet in bullets
        if len(bullet.split()) >= 8 and re.search(r"\b(using|with|built|developed|designed|implemented|improved)\b", bullet.lower())
    ]
    impact_lines = [
        bullet for bullet in bullets
        if re.search(r"\b(reduced|increased|improved|optimized|delivered|launched|automated)\b", bullet.lower())
    ]

    if len(detailed_lines) >= 3 and impact_lines:
        severity = 0.95
        reasons.append("Project and experience descriptions are specific and informative.")
    elif len(detailed_lines) >= 1:
        severity = 0.65
        reasons.append("Some experience descriptions are reasonably specific.")
    else:
        severity = 0.3
        reasons.append("Project descriptions are too short or generic.")
        suggestions.append("Describe what the project does, what tools were used, and what outcome was achieved.")

    return severity, reasons, suggestions


def _dedupe(values: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value.strip())
    return output


def evaluate_resume_quality(
    resume_text: str,
    candidate_name: str = "",
    *,
    ats_score: float = 0.0,
    ats_status: str | None = None,
) -> Dict[str, Any]:
    del candidate_name  # reserved for personalized suggestions if needed later

    sections = split_resume_sections(resume_text)
    bullet_pool = _bullet_candidates(f"{sections.get('experience', '')}\n{sections.get('projects', '')}")

    section_signal = _section_presence_signal(sections)
    bullet_signal = _bullet_quality_signal(bullet_pool)
    quantified_signal = _quantified_achievement_signal(bullet_pool)
    readability_signal = _readability_signal(resume_text)
    ats_signal = _ats_presentation_signal(sections, resume_text, ats_score, ats_status)
    description_signal = _description_strength_signal(sections)

    weighted_score = (
        section_signal[0] * WEIGHTS["sections"]
        + bullet_signal[0] * WEIGHTS["bullet_quality"]
        + quantified_signal[0] * WEIGHTS["quantified_achievements"]
        + readability_signal[0] * WEIGHTS["readability"]
        + ats_signal[0] * WEIGHTS["ats_presentation"]
        + description_signal[0] * WEIGHTS["description_strength"]
    )
    score = round(max(0.0, min(100.0, weighted_score)), 1)

    reasons = _dedupe(
        [
            *section_signal[1],
            *bullet_signal[1],
            *quantified_signal[1],
            *readability_signal[1],
            *ats_signal[1],
            *description_signal[1],
        ]
    )
    suggestions = _dedupe(
        [
            *section_signal[2],
            *bullet_signal[2],
            *quantified_signal[2],
            *readability_signal[2],
            *ats_signal[2],
            *description_signal[2],
        ]
    )

    if not reasons:
        reasons = ["Resume structure looks balanced and recruiter-friendly."]
    if not suggestions:
        suggestions = ["Maintain concise, impact-driven bullets and clear section structure."]

    if score >= 80:
        status = "Strong"
    elif score >= 55:
        status = "Moderate"
    else:
        status = "Weak"

    return {
        "resumeQualityScore": score,
        "resumeQualityStatus": status,
        "resumeQualityReasons": reasons[:5],
        "improvementSuggestions": suggestions[:5],
    }
