import re
from typing import Any, Dict, Iterable, List, Set


ROLE_FAMILIES: Dict[str, Dict[str, Any]] = {
    "software_engineering": {
        "label": "Software Engineering",
        "title": r"\b(software|backend|frontend|full\s*stack|web|mobile|devops|qa|test)\s+(engineer|developer|tester|architect|lead|intern)\b|\bdeveloper\b",
        "evidence": r"\b(python|java|javascript|typescript|react|node|api|database|git|docker|kubernetes|testing|software|frontend|backend|full\s*stack)\b",
    },
    "data_ai": {
        "label": "Data/AI",
        "title": r"\b(data|machine\s+learning|ai|ml|analytics?|bi)\s+(scientist|engineer|analyst|developer|intern)\b",
        "evidence": r"\b(machine\s+learning|deep\s+learning|nlp|computer\s+vision|data\s+science|statistics|python|sql|power\s*bi|tableau|dashboard|model|analytics?)\b",
    },
    "business_analysis": {
        "label": "Business Analysis",
        "title": r"\bbusiness\s+analyst\b|\bba\s+(role|position|intern)\b",
        "evidence": r"\b(requirements?\s+(gathering|elicitation|analysis|documentation|management)|business\s+analysis|brd|frd|srs|stakeholders?|user\s+stor(?:y|ies)|acceptance\s+criteria|process\s+(mapping|modelling|modeling)|uat|jira|confluence)\b",
    },
    "product_project": {
        "label": "Product/Project Management",
        "title": r"\b(product|project|program|delivery)\s+(manager|management|coordinator|lead|owner|intern)\b",
        "evidence": r"\b(roadmap|backlog|sprint|scrum|agile|stakeholder|delivery|milestone|budget|risk|planning|coordination|project\s+management|product\s+management)\b",
    },
    "sales": {
        "label": "Sales/Business Development",
        "title": r"\b(sales|business\s+development|account)\s+(executive|manager|representative|associate|intern|lead)\b",
        "evidence": r"\b(sales|lead\s+generation|prospecting|cold\s+calling|pipeline|quota|revenue|negotiation|crm|salesforce|hubspot|account\s+management|client\s+relationship)\b",
    },
    "marketing_content": {
        "label": "Marketing/Content",
        "title": r"\b(marketing|digital\s+marketing|content|seo|social\s+media|brand)\s+(executive|manager|specialist|writer|associate|intern)\b",
        "evidence": r"\b(marketing|seo|sem|campaign|content|copywriting|social\s+media|brand|email\s+marketing|market\s+research|google\s+analytics)\b",
    },
    "hr_recruiting": {
        "label": "HR/Recruiting",
        "title": r"\b(hr|human\s+resources|recruit(?:er|ment)|talent\s+acquisition)\s+(executive|manager|specialist|associate|intern)?\b",
        "evidence": r"\b(recruitment|talent\s+acquisition|sourcing|screening|interview\s+scheduling|onboarding|payroll|employee\s+engagement|hr\s+operations|human\s+resources)\b",
    },
    "finance_accounting": {
        "label": "Finance/Accounting",
        "title": r"\b(accountant|finance|financial)\s+(executive|analyst|manager|associate|intern)?\b|\baccounts\s+(executive|manager|associate|intern)\b",
        "evidence": r"\b(accounting|bookkeeping|financial\s+analysis|financial\s+reporting|accounts\s+payable|accounts\s+receivable|taxation|gst|tally|quickbooks|audit|reconciliation)\b",
    },
    "operations_supply_chain": {
        "label": "Operations/Supply Chain",
        "title": r"\b(operations?|supply\s+chain|procurement|logistics|inventory)\s+(executive|manager|analyst|coordinator|associate|intern)?\b",
        "evidence": r"\b(operations|supply\s+chain|procurement|purchase|vendor|inventory|logistics|warehouse|process\s+improvement|mis\s+reporting|quality\s+control)\b",
    },
    "education_training": {
        "label": "Education/Training",
        "title": r"\b(teacher|trainer|faculty|instructor|educator|training\s+manager)\b",
        "evidence": r"\b(teaching|curriculum|lesson\s+planning|classroom|training|instructional\s+design|coaching|learning\s+outcomes)\b",
    },
    "healthcare": {
        "label": "Healthcare",
        "title": r"\b(nurse|doctor|physician|clinical|healthcare|medical)\s*(assistant|executive|officer|specialist|intern)?\b",
        "evidence": r"\b(patient\s+care|clinical|medical|healthcare|nursing|diagnosis|treatment|hospital|clinic|clinical\s+documentation)\b",
    },
    "legal_compliance": {
        "label": "Legal/Compliance",
        "title": r"\b(legal|law|compliance|contract)\s+(executive|associate|analyst|manager|specialist|intern)?\b",
        "evidence": r"\b(legal\s+research|contract|compliance|case\s+management|litigation|regulatory|policy|legal\s+drafting)\b",
    },
}


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text or "", flags=re.IGNORECASE))


def _detect_families(text: str) -> Dict[str, Dict[str, Any]]:
    detected: Dict[str, Dict[str, Any]] = {}
    for key, config in ROLE_FAMILIES.items():
        title_hits = _count_matches(text, str(config["title"]))
        evidence_hits = _count_matches(text, str(config["evidence"]))
        if title_hits or evidence_hits >= 2:
            detected[key] = {
                "label": config["label"],
                "titleHits": title_hits,
                "evidenceHits": evidence_hits,
                "strength": min(1.0, (title_hits * 0.55) + min(evidence_hits, 6) * 0.12),
            }
    return detected


def _display(families: Iterable[str]) -> List[str]:
    labels = []
    for family in sorted(families):
        config = ROLE_FAMILIES.get(family)
        labels.append(str(config["label"]) if config else family)
    return labels


def assess_role_alignment(jd_text: str, resume_text: str) -> Dict[str, Any]:
    jd_families = _detect_families(jd_text)
    resume_families = _detect_families(resume_text)

    if not jd_families:
        return {
            "roleAlignmentScore": 1.0,
            "roleMismatch": False,
            "roleWarnings": [],
            "roleReasons": [],
            "roleMetrics": {
                "detectedRole": None,
                "jdRoleFamilies": [],
                "resumeRoleFamilies": _display(resume_families),
            },
        }

    jd_keys = set(jd_families)
    resume_keys = set(resume_families)
    overlap = jd_keys & resume_keys

    if overlap:
        strongest_overlap = max(float(resume_families[key]["strength"]) for key in overlap)
        score = max(0.62, min(1.0, 0.55 + strongest_overlap * 0.45))
    elif not resume_keys:
        score = 0.68
    else:
        strongest_jd = max(float(item["strength"]) for item in jd_families.values())
        strongest_resume = max(float(item["strength"]) for item in resume_families.values())
        score = 0.42 if strongest_jd >= 0.55 and strongest_resume >= 0.55 else 0.56

    role_mismatch = bool(
        resume_keys
        and not overlap
        and max(float(item["strength"]) for item in jd_families.values()) >= 0.65
        and max(float(item["strength"]) for item in resume_families.values()) >= 0.70
    )

    reasons: List[str] = []
    warnings: List[str] = []
    if role_mismatch:
        reasons.append(
            "Role mismatch: JD focus is "
            + ", ".join(_display(jd_keys)[:3])
            + " but the resume mainly signals "
            + ", ".join(_display(resume_keys)[:3])
            + "."
        )
    elif not overlap and resume_keys:
        warnings.append(
            "Resume role signals do not strongly overlap with the JD focus: "
            + ", ".join(_display(jd_keys)[:3])
            + "."
        )
    elif not resume_keys:
        warnings.append("Resume does not clearly state a role focus, so role alignment depends mostly on semantic matching.")

    return {
        "roleAlignmentScore": max(0.0, min(1.0, score)),
        "roleMismatch": role_mismatch,
        "roleWarnings": warnings,
        "roleReasons": reasons,
        "roleMetrics": {
            "detectedRole": ",".join(sorted(overlap or jd_keys)),
            "jdRoleFamilies": _display(jd_keys),
            "resumeRoleFamilies": _display(resume_keys),
            "matchedRoleFamilies": _display(overlap),
        },
    }
