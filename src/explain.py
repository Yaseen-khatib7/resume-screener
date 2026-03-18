import re
from typing import List, Tuple, Dict, Any, Set

# NOTE: this module provides two things:
# 1) top_evidence_pairs(...)  -> already used (semantic evidence)
# 2) build_hr_explanation(...) -> NEW (good match / bad match narrative)


def _sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    # Split on sentence endings and newlines
    parts = re.split(r"(?<=[\.\!\?])\s+|\n+", text)
    out = []
    for p in parts:
        p = p.strip()
        if len(p) >= 25:  # ignore very tiny fragments
            out.append(p)
    return out


def top_evidence_pairs(embedder, jd_text: str, resume_text: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
    """
    Returns top_k (jd_sentence, resume_sentence, similarity) pairs using embedding similarity.
    This is your existing 'evidence' feature.
    """
    jd_sents = _sentences(jd_text)
    rs_sents = _sentences(resume_text)

    if not jd_sents or not rs_sents:
        return []

    # Embed
    jd_vecs = embedder.embed(jd_sents)
    rs_vecs = embedder.embed(rs_sents)

    # Cosine similarity (manual to avoid dependency mismatch)
    def _norm(v):
        s = 0.0
        for x in v:
            s += float(x) * float(x)
        return (s ** 0.5) + 1e-9

    jd_norms = [_norm(v) for v in jd_vecs]
    rs_norms = [_norm(v) for v in rs_vecs]

    best = []
    for i, jv in enumerate(jd_vecs):
        # find best resume sentence for this jd sentence
        bi = -1
        bs = -1.0
        for k, rv in enumerate(rs_vecs):
            dot = 0.0
            for a, b in zip(jv, rv):
                dot += float(a) * float(b)
            sim = dot / (jd_norms[i] * rs_norms[k])
            if sim > bs:
                bs = sim
                bi = k
        if bi >= 0:
            best.append((jd_sents[i], rs_sents[bi], float(bs)))

    best.sort(key=lambda x: x[2], reverse=True)
    return best[:top_k]


def build_hr_explanation(
    *,
    candidate_name: str,
    score: float,
    match_style_label: str,
    jd_required: Set[str],
    jd_preferred: Set[str],
    matched_skills: List[str],
    missing_required: List[str],
    missing_preferred: List[str],
    evidence_pairs: List[Dict[str, Any]],
    max_points: int = 5
) -> Dict[str, Any]:
    """
    Produces human-friendly explanation like Streamlit version:
    - why_good: bullet points
    - why_bad: bullet points (gaps / risks)
    - summary: 2-3 lines for HR

    This explanation is deterministic and based on:
    - skills matched/missing
    - evidence sentence pairs (JD <-> Resume)
    - score thresholds
    """
    matched = matched_skills or []
    miss_req = missing_required or []
    miss_pref = missing_preferred or []

    # Basic score interpretation
    if score >= 80:
        fit_label = "Strong match"
    elif score >= 60:
        fit_label = "Good match"
    elif score >= 40:
        fit_label = "Moderate match"
    else:
        fit_label = "Weak match"

    # Evidence highlights
    evidence = evidence_pairs or []
    strong_evidence = [e for e in evidence if float(e.get("sim", 0.0)) >= 0.55]
    weak_evidence = [e for e in evidence if float(e.get("sim", 0.0)) < 0.55]

    # WHY GOOD bullets
    why_good: List[str] = []

    if matched:
        top_matched = matched[: min(len(matched), max_points)]
        why_good.append(f"Matches key skills from the JD: {', '.join(top_matched)}.")

    if strong_evidence:
        e = strong_evidence[0]
        why_good.append(
            "Resume aligns with the JD requirement: "
            f"“{e.get('jd', '')[:120]}…” ↔ “{e.get('resume', '')[:120]}…”"
        )

    if match_style_label:
        if match_style_label.lower() == "strict" and len(miss_req) == 0:
            why_good.append("Meets all required skills in the JD (strict screening passed).")
        elif match_style_label.lower() in ("balanced", "flexible"):
            why_good.append(f"Overall profile aligns well in {match_style_label.lower()} matching mode.")

    # WHY BAD bullets
    why_bad: List[str] = []

    if miss_req:
        top_missing_req = miss_req[: min(len(miss_req), max_points)]
        why_bad.append(f"Missing required skills: {', '.join(top_missing_req)}.")

    if miss_pref:
        top_missing_pref = miss_pref[: min(len(miss_pref), max_points)]
        why_bad.append(f"Missing preferred skills: {', '.join(top_missing_pref)}.")

    if not strong_evidence and evidence:
        e = evidence[0]
        why_bad.append(
            "Limited strong evidence of direct JD alignment in the resume text (semantic match looks weak)."
        )

    # If almost no matched skills detected
    if len(matched) == 0 and (len(jd_required) + len(jd_preferred)) > 0:
        why_bad.append("Few JD skills were detected in the resume (may be formatting/scanned PDF or true mismatch).")

    # Summary paragraph (HR friendly)
    summary_lines = []
    summary_lines.append(f"{fit_label} ({score}/100).")
    if miss_req:
        summary_lines.append("Key blockers are missing required skills.")
    else:
        summary_lines.append("No major required-skill blockers detected.")
    if matched:
        summary_lines.append(f"Top strengths: {', '.join(matched[:3])}.")
    summary = " ".join(summary_lines)

    # Ensure we always return at least one bullet each (for UI consistency)
    if not why_good:
        why_good = ["No strong positive signals could be extracted from this resume for the given JD."]
    if not why_bad:
        why_bad = ["No major gaps detected against the JD."]

    required_total = len(jd_required)
    matched_required = required_total - len(miss_req)

    if required_total > 0:
        required_coverage = matched_required / required_total
    else:
        required_coverage = 0.0

    preferred_total = len(jd_preferred)
    matched_preferred = preferred_total - len(miss_pref)
    preferred_coverage = (matched_preferred / preferred_total) if preferred_total > 0 else 0.0

    strong_profile = (
        score >= 72
        and (required_coverage >= 0.55 or preferred_coverage >= 0.5)
        and len(miss_req) <= 2
    )
    promising_profile = (
        score >= 58
        and (required_coverage >= 0.35 or preferred_coverage >= 0.35 or len(matched) >= 2)
        and len(miss_req) <= 3
    )
    high_scope_profile = (
        score >= 57
        and len(matched) >= 6
    )

    if strong_profile or high_scope_profile:
        recommendation = "Hire"
        if strong_profile and len(miss_req) == 0:
            recommendation_reason = "Strong overall alignment with the JD and no major required-skill blockers."
        else:
            recommendation_reason = "Strong overall fit with enough relevant skills and scope to justify moving forward."
    elif promising_profile or (score >= 50 and len(matched) >= 4):
        recommendation = "Hold"
        recommendation_reason = "Promising profile with enough relevant overlap to consider for interview validation."
    else:
        recommendation = "Do Not Hire"
        if miss_req and required_coverage < 0.35 and score < 58:
            recommendation_reason = "Too many important JD requirements are currently missing for this role."
        else:
            recommendation_reason = "Overall alignment with the JD is still too weak to recommend moving forward."

    return {
        "fitLabel": fit_label,
        "summary": summary,
        "whyGood": why_good[: max_points],
        "whyBad": why_bad[: max_points],
        "recommendation": recommendation,
        "recommendationReason": recommendation_reason,
    }
