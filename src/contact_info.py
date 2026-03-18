import re
from typing import List, Set


EMAIL_REGEX = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.IGNORECASE)
MAILTO_REGEX = re.compile(r"mailto:\s*([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", re.IGNORECASE)
EMAIL_IN_URL_REGEX = re.compile(
    r"(?:email|contact|user|e-mail)=([a-z0-9._%+\-]+%40[a-z0-9.\-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
LOCAL_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+- ")
DOMAIN_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.- ")


def _compact_candidate(candidate: str) -> str:
    value = re.sub(r"\s+", "", candidate or "")
    value = value.strip(" <>[](){}.,;:'\"")
    return value


def _extract_fragmented_emails(source: str) -> List[str]:
    candidates: List[str] = []

    for idx, char in enumerate(source):
        if char != "@":
            continue

        left = idx - 1
        while left >= 0 and source[left] in LOCAL_ALLOWED:
            left -= 1
        right = idx + 1
        while right < len(source) and source[right] in DOMAIN_ALLOWED:
            right += 1

        local_raw = source[left + 1:idx]
        domain_raw = source[idx + 1:right]

        local_parts = [part for part in local_raw.split() if part]
        domain_parts = [part for part in domain_raw.split() if part]

        local_variants = []
        if local_parts:
            for take in range(1, min(4, len(local_parts)) + 1):
                local_variants.append("".join(local_parts[-take:]))
        else:
            local_variants.append(local_raw)

        domain_variants = []
        if domain_parts:
            for take in range(1, min(3, len(domain_parts)) + 1):
                domain_variants.append("".join(domain_parts[:take]))
        else:
            domain_variants.append(domain_raw)

        for local in local_variants:
            for domain in domain_variants:
                candidate = _compact_candidate(f"{local}@{domain}")
                if EMAIL_REGEX.fullmatch(candidate):
                    candidates.append(candidate)

    return candidates


def _email_rank(email: str) -> tuple[int, int, int, int]:
    local = email.split("@", 1)[0]
    has_dot = 1 if "." in local else 0
    starts_alpha = 1 if local[:1].isalpha() else 0
    leading_digits = len(local) - len(local.lstrip("0123456789"))
    return (
        starts_alpha,
        has_dot,
        -leading_digits,
        len(local),
    )


def extract_emails(text: str) -> List[str]:
    found: List[str] = []
    source = text or ""

    for match in EMAIL_REGEX.findall(source):
        found.append(match)

    for match in MAILTO_REGEX.findall(source):
        found.append(match)

    for match in EMAIL_IN_URL_REGEX.findall(source):
        decoded = match.replace("%40", "@").replace("%2B", "+")
        found.append(decoded)

    found.extend(_extract_fragmented_emails(source))

    normalized: List[str] = []
    seen: Set[str] = set()
    for email in found:
        clean = email.strip(" <>[](){}.,;:'\"").lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    normalized.sort(key=_email_rank, reverse=True)
    return normalized
