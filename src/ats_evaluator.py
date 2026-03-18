import math
import re
from typing import Any, Dict, List, Set

from src.contact_info import extract_emails
from src.resume_sections import split_resume_sections
from src.skill_graph import analyze_skill_graph_match
from src.skills import extract_skills, split_jd_required_preferred


PAGE_EQUIVALENT_CHARS = 1800
EDUCATION_KEYWORDS = {
    "computer science",
    "artificial intelligence",
    "data science",
    "mathematics",
    "statistics",
    "information technology",
    "software engineering",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _normalise_text(text: str) -> str:
    return (text or "").replace("\x00", " ").strip()


def _score_text_extraction(text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    reasons: List[str] = []
    warnings: List[str] = []

    char_count = len(text)
    words = re.findall(r"\b[\w\+#./-]+\b", text)
    word_count = len(words)
    alpha_chars = sum(1 for char in text if char.isalpha())
    digit_chars = sum(1 for char in text if char.isdigit())
    printable_chars = sum(1 for char in text if not char.isspace())
    alpha_ratio = _safe_div(alpha_chars, printable_chars)
    digit_ratio = _safe_div(digit_chars, printable_chars)

    if char_count >= 1500:
        score = 1.0
    elif char_count >= 500:
        score = 0.55 + 0.45 * _safe_div(char_count - 500, 1000)
        warnings.append("Moderate text extraction quality.")
    else:
        score = 0.1 + 0.45 * _safe_div(char_count, 500)
        reasons.append("Very little readable text was extracted from the resume.")

    if word_count < 120:
        score *= 0.75
        reasons.append("Resume content is too short for reliable ATS parsing.")

    if alpha_ratio < 0.55:
        score *= 0.7
        reasons.append("Extracted content appears noisy or poorly readable.")

    if char_count < 250:
        score *= 0.45
        reasons.append("Resume may be scanned or image-based.")

    if digit_ratio > 0.35:
        score *= 0.85
        warnings.append("Resume text contains an unusually high amount of numeric noise.")

    metrics = {
        "charCount": char_count,
        "wordCount": word_count,
        "alphaRatio": round(alpha_ratio, 3),
        "digitRatio": round(digit_ratio, 3),
    }
    return _clamp(score), reasons, warnings, metrics

def _score_contact_presence(text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    emails = extract_emails(text)
    if emails:
        return 1.0, [], [], {
            "emails": emails,
            "hasEmail": True,
        }

    return 0.0, ["Resume does not include a detectable email address."], [
        "Add a direct email address in the resume header for ATS compatibility."
    ], {
        "emails": [],
        "hasEmail": False,
    }


def _score_sections(text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    sections = split_resume_sections(text)
    present = {
        name: bool((sections.get(name) or "").strip())
        for name in ("skills", "experience", "education", "projects")
    }

    score = 0.0
    reasons: List[str] = []
    warnings: List[str] = []

    required_sections = ("skills", "experience", "education")
    required_present = sum(1 for name in required_sections if present[name])
    score += 0.85 * _safe_div(required_present, len(required_sections))
    score += 0.15 if present["projects"] else 0.0

    for name in required_sections:
        if not present[name]:
            reasons.append(f"Missing a clear {name} section.")

    if not present["projects"]:
        warnings.append("No projects section detected.")

    metrics = {
        "presentSections": [name for name, is_present in present.items() if is_present],
        "missingSections": [name for name, is_present in present.items() if not is_present],
    }
    return _clamp(score), reasons, warnings, metrics


def _required_skills_for_ats(jd_text: str) -> Set[str]:
    required, preferred = split_jd_required_preferred(jd_text)
    if required:
        return required
    extracted, _ = extract_skills(jd_text)
    return extracted | preferred


def _parse_years_requirement(jd_text: str) -> tuple[int | None, int | None]:
    text = jd_text.lower()
    range_match = re.search(r"(\d+)\s*[-to]+\s*(\d+)\s*years", text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    plus_match = re.search(r"(\d+)\+?\s*years", text)
    if plus_match:
        years = int(plus_match.group(1))
        return years, None

    return None, None


def _extract_resume_years(resume_text: str) -> float | None:
    text = resume_text.lower()
    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+of\s+experience",
        r"experience\s+of\s+(\d+(?:\.\d+)?)\+?\s+years?",
        r"(\d+(?:\.\d+)?)\+?\s+years?\s+experience",
    ]
    values: List[float] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                values.append(float(match))
            except ValueError:
                continue
    return max(values) if values else None


def _parse_education_requirements(jd_text: str) -> Set[str]:
    text = jd_text.lower()
    found = {keyword for keyword in EDUCATION_KEYWORDS if keyword in text}
    if found:
        return found

    degree_block = ""
    match = re.search(r"education(.*?)(nice to have|preferred qualifications|$)", text, re.DOTALL)
    if match:
        degree_block = match.group(1)
    return {keyword for keyword in EDUCATION_KEYWORDS if keyword in degree_block}


def _extract_resume_education(resume_text: str) -> Set[str]:
    text = resume_text.lower()
    found = {keyword for keyword in EDUCATION_KEYWORDS if keyword in text}
    if "bachelor" in text or "b.tech" in text or "b.e" in text:
        found.add("bachelor")
    if "master" in text or "m.tech" in text or "m.s" in text or "mba" in text:
        found.add("master")
    return found


def _score_experience_alignment(resume_text: str, jd_text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    min_years, max_years = _parse_years_requirement(jd_text)
    resume_years = _extract_resume_years(resume_text)

    if min_years is None:
        return 0.75, [], [], {
            "requiredMinYears": None,
            "requiredMaxYears": None,
            "resumeYears": resume_years,
            "experienceMatch": None,
        }

    reasons: List[str] = []
    warnings: List[str] = []

    if resume_years is None:
        return 0.5, ["Resume does not clearly state years of experience required by the JD."], [], {
            "requiredMinYears": min_years,
            "requiredMaxYears": max_years,
            "resumeYears": None,
            "experienceMatch": False,
        }

    if resume_years < min_years:
        gap = round(min_years - resume_years, 1)
        return 0.35, [f"Resume appears below the JD experience requirement by about {gap} years."], [], {
            "requiredMinYears": min_years,
            "requiredMaxYears": max_years,
            "resumeYears": resume_years,
            "experienceMatch": False,
        }

    if max_years is not None and resume_years > max_years + 3:
        warnings.append("Resume may be over the target experience range for this role.")
        score = 0.78
    else:
        score = 1.0

    return score, reasons, warnings, {
        "requiredMinYears": min_years,
        "requiredMaxYears": max_years,
        "resumeYears": resume_years,
        "experienceMatch": True,
    }


def _score_education_alignment(resume_text: str, jd_text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    jd_education = _parse_education_requirements(jd_text)
    resume_education = _extract_resume_education(resume_text)

    if not jd_education:
        return 0.8, [], [], {
            "requiredEducation": [],
            "resumeEducation": sorted(resume_education),
            "educationMatch": None,
        }

    matched = sorted(jd_education & resume_education)
    score = _safe_div(len(matched), len(jd_education))
    if "bachelor" in resume_education or "master" in resume_education:
        score = max(score, 0.75)

    reasons: List[str] = []
    if score < 0.5:
        reasons.append("Resume does not clearly match the JD education background.")

    return max(0.35, score), reasons, [], {
        "requiredEducation": sorted(jd_education),
        "resumeEducation": sorted(resume_education),
        "educationMatch": bool(matched) or "bachelor" in resume_education or "master" in resume_education,
    }


def _score_keyword_match(resume_text: str, jd_text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    jd_required = _required_skills_for_ats(jd_text)
    jd_required_explicit, jd_preferred = split_jd_required_preferred(jd_text)
    resume_skills, _ = extract_skills(resume_text)
    matched_skills = sorted(resume_skills & jd_required)
    missing_skills = sorted(jd_required - resume_skills)
    literal_coverage = _safe_div(len(matched_skills), len(jd_required))

    graph_analysis = analyze_skill_graph_match(
        resume_text=resume_text,
        jd_text=jd_text,
        jd_required=jd_required_explicit or jd_required,
        jd_preferred=jd_preferred,
    )
    graph_coverage = _safe_div(
        len(graph_analysis.get("graphMatchedSkills", [])),
        len(graph_analysis.get("graphMatchedSkills", [])) + len(graph_analysis.get("graphMissingSkills", [])),
    )
    coverage = max(literal_coverage, graph_coverage)

    if not jd_required:
        return 0.65, [], ["JD does not expose clear required skills for ATS matching."], {
            "requiredSkills": [],
            "matchedSkills": [],
            "missingSkills": [],
            "skillCoverage": 0.0,
            "literalSkillCoverage": 0.0,
            "graphSkillCoverage": 0.0,
        }

    reasons: List[str] = []
    warnings: List[str] = []

    if coverage >= 0.7:
        score = 0.85 + 0.15 * _safe_div(coverage - 0.7, 0.3)
    elif coverage >= 0.4:
        score = 0.55 + 0.3 * _safe_div(coverage - 0.4, 0.3)
        warnings.append("Resume only partially covers the JD skill requirements.")
    else:
        score = 0.15 + 0.4 * _safe_div(coverage, 0.4)
        reasons.append("Weak keyword alignment with the required JD skills.")

    if len(matched_skills) == 0 and graph_coverage < 0.35:
        reasons.append("No clear overlap found between resume skills and JD requirements.")
    elif literal_coverage < 0.3 and graph_coverage >= 0.45:
        warnings.append("ATS accepted related skills through the skill graph because wording differs from the JD.")

    metrics = {
        "requiredSkills": sorted(jd_required),
        "matchedSkills": matched_skills,
        "missingSkills": missing_skills,
        "skillCoverage": round(coverage, 3),
        "literalSkillCoverage": round(literal_coverage, 3),
        "graphSkillCoverage": round(graph_coverage, 3),
    }
    return _clamp(score), reasons, warnings, metrics


def _score_structure(text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    special_chars = sum(1 for char in text if not char.isalnum() and not char.isspace())
    table_chars = sum(text.count(char) for char in ("|", "\t"))
    repeated_dots = len(re.findall(r"[._-]{4,}", text))
    section_headings = sum(
        1
        for line in lines
        if re.fullmatch(r"[A-Za-z &/]{3,40}", line) and len(line.split()) <= 5
    )
    special_ratio = _safe_div(special_chars, max(1, len(text)))
    table_ratio = _safe_div(table_chars, max(1, len(text)))

    score = 1.0
    reasons: List[str] = []
    warnings: List[str] = []

    if special_ratio > 0.12:
        score -= 0.25
        reasons.append("Resume contains too many special characters for reliable ATS parsing.")
    elif special_ratio > 0.08:
        score -= 0.12
        warnings.append("Resume formatting looks noisy.")

    if table_ratio > 0.015:
        score -= 0.28
        reasons.append("Resume appears to rely on tables or tabular formatting.")
    elif table_ratio > 0.005:
        score -= 0.12
        warnings.append("Resume may use table-heavy formatting.")

    if repeated_dots >= 8:
        score -= 0.15
        warnings.append("Resume uses repeated separator characters that ATS parsers often mishandle.")

    if section_headings < 2:
        score -= 0.25
        reasons.append("Resume lacks clear section headings.")

    avg_line_length = sum(len(line) for line in lines) / len(lines) if lines else 0.0
    if avg_line_length > 140:
        score -= 0.1
        warnings.append("Resume has very long lines, which can indicate layout extraction issues.")

    metrics = {
        "specialCharRatio": round(special_ratio, 3),
        "tableCharRatio": round(table_ratio, 3),
        "sectionHeadingCount": section_headings,
        "avgLineLength": round(avg_line_length, 1),
    }
    return _clamp(score), reasons, warnings, metrics


def _score_length(text: str) -> tuple[float, List[str], List[str], Dict[str, Any]]:
    page_equivalent = len(text) / PAGE_EQUIVALENT_CHARS if text else 0.0
    reasons: List[str] = []
    warnings: List[str] = []

    if page_equivalent < 1.0:
        score = 0.45 + 0.35 * page_equivalent
        reasons.append("Resume is shorter than a typical one-page equivalent.")
    elif page_equivalent <= 3.0:
        score = 1.0
    elif page_equivalent <= 5.0:
        score = 0.82 - 0.12 * _safe_div(page_equivalent - 3.0, 2.0)
        warnings.append("Resume is longer than typical ATS-friendly length.")
    else:
        score = max(0.35, 0.7 - 0.25 * math.log1p(page_equivalent - 5.0))
        reasons.append("Resume is significantly longer than the recommended ATS-friendly range.")

    metrics = {
        "pageEquivalent": round(page_equivalent, 2),
    }
    return _clamp(score), reasons, warnings, metrics


def _dedupe(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def evaluate_resume_ats(resume_text: str, jd_text: str) -> Dict[str, Any]:
    resume_text = _normalise_text(resume_text)
    jd_text = _normalise_text(jd_text)

    text_score, text_reasons, text_warnings, text_metrics = _score_text_extraction(resume_text)
    contact_score, contact_reasons, contact_warnings, contact_metrics = _score_contact_presence(resume_text)
    section_score, section_reasons, section_warnings, section_metrics = _score_sections(resume_text)
    keyword_score, keyword_reasons, keyword_warnings, keyword_metrics = _score_keyword_match(resume_text, jd_text)
    structure_score, structure_reasons, structure_warnings, structure_metrics = _score_structure(resume_text)
    length_score, length_reasons, length_warnings, length_metrics = _score_length(resume_text)
    experience_score, experience_reasons, experience_warnings, experience_metrics = _score_experience_alignment(resume_text, jd_text)
    education_score, education_reasons, education_warnings, education_metrics = _score_education_alignment(resume_text, jd_text)

    keyword_score = _clamp((keyword_score * 0.8) + (experience_score * 0.12) + (education_score * 0.08))

    weighted_score = (
        text_score * 0.25
        + section_score * 0.20
        + keyword_score * 0.30
        + structure_score * 0.15
        + length_score * 0.10
    ) * 100.0

    ats_score = round(max(0.0, min(100.0, weighted_score)), 1)

    if contact_score <= 0:
        ats_score = min(ats_score, 55.0)
        ats_status = "FAIL"
        ats_decision = "Reject"
    elif ats_score >= 78:
        ats_status = "PASS"
        ats_decision = "Screen"
    elif ats_score >= 58:
        ats_status = "REVIEW"
        ats_decision = "Review"
    else:
        ats_status = "FAIL"
        ats_decision = "Reject"

    reasons = _dedupe(
        text_reasons
        + contact_reasons
        + section_reasons
        + keyword_reasons
        + structure_reasons
        + length_reasons
        + experience_reasons
        + education_reasons
    )
    warnings = _dedupe(
        text_warnings
        + contact_warnings
        + section_warnings
        + keyword_warnings
        + structure_warnings
        + length_warnings
        + experience_warnings
        + education_warnings
    )

    if not reasons and ats_status == "PASS":
        reasons = ["Resume meets the baseline ATS validation checks."]

    return {
        "atsScore": ats_score,
        "atsStatus": ats_status,
        "atsReasons": reasons,
        "atsWarnings": warnings,
        "atsDecision": ats_decision,
        "atsBreakdown": {
            "textExtractionQuality": round(text_score * 100, 1),
            "sectionPresence": round(section_score * 100, 1),
            "keywordSkillMatch": round(keyword_score * 100, 1),
            "structureQuality": round(structure_score * 100, 1),
            "resumeLengthQuality": round(length_score * 100, 1),
        },
        "atsMetrics": {
            "textExtraction": text_metrics,
            "contact": contact_metrics,
            "sections": section_metrics,
            "keywordMatch": keyword_metrics,
            "structure": structure_metrics,
            "length": length_metrics,
            "experience": experience_metrics,
            "education": education_metrics,
        },
    }
