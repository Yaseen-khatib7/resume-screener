import re
from typing import List, Set


EMAIL_REGEX = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.IGNORECASE)
MAILTO_REGEX = re.compile(r"mailto:\s*([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", re.IGNORECASE)
EMAIL_IN_URL_REGEX = re.compile(
    r"(?:email|contact|user|e-mail)=([a-z0-9._%+\-]+%40[a-z0-9.\-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
MISSING_AT_EMAIL_REGEX = re.compile(
    r"\b([a-z0-9][a-z0-9._%+\-]{2,40})(gmail|outlook|hotmail|yahoo|icloud|protonmail|live|edu)\.(com|in|org|net)\b",
    re.IGNORECASE,
)
LOCAL_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+- ")
DOMAIN_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.- ")
SUSPICIOUS_LOCAL_PARTS = (
    "maharashtra",
    "india",
    "pune",
    "mumbai",
    "delhi",
    "bangalore",
    "bengaluru",
    "address",
    "location",
)
COMMON_EMAIL_PROVIDERS = (
    "gmail",
    "outlook",
    "hotmail",
    "yahoo",
    "icloud",
    "protonmail",
    "live",
)


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


def _extract_missing_at_emails(source: str) -> List[str]:
    candidates: List[str] = []
    for raw_line in (source or "").splitlines():
        line = raw_line.strip().lower()
        if not line:
            continue

        for token in re.findall(r"[a-z0-9._%+\-]+(?:gmail|outlook|hotmail|yahoo|icloud|protonmail|live|edu)\.(?:com|in|org|net)", line):
            match = MISSING_AT_EMAIL_REGEX.fullmatch(token)
            if not match:
                continue

            local, domain_name, tld = match.groups()

            # Avoid gluing location text or other nearby words into the local-part.
            for prefix in ("maharashtra", "india", "pune", "mumbai", "delhi", "bangalore", "bengaluru"):
                if local.startswith(prefix) and len(local) > len(prefix) + 3:
                    local = local[len(prefix):]
                    break

            candidate = _compact_candidate(f"{local}@{domain_name}.{tld}")
            if EMAIL_REGEX.fullmatch(candidate):
                candidates.append(candidate)
    return candidates


def _is_valid_local_part(local: str) -> bool:
    if not local:
        return False
    if local.startswith(".") or local.endswith("."):
        return False
    if ".." in local:
        return False
    if local.endswith(tuple(COMMON_EMAIL_PROVIDERS)):
        return False
    return True


def _repair_embedded_provider_email(email: str) -> List[str]:
    clean = email.strip(" <>[](){}.,;:'\"").lower()
    if "@" not in clean:
        return []

    local, domain = clean.split("@", 1)
    repaired: List[str] = []
    for provider in COMMON_EMAIL_PROVIDERS:
        if not local.endswith(provider):
            continue
        prefix = local[: -len(provider)].rstrip("._-")
        if len(prefix) < 3 or not _is_valid_local_part(prefix):
            continue
        if ".edu." in f".{domain}." or domain.endswith(".edu") or ".ac." in f".{domain}.":
            candidate = f"{prefix}@{domain}"
            if EMAIL_REGEX.fullmatch(candidate):
                repaired.append(candidate)
            continue
        candidate = f"{prefix}@{provider}.com"
        if EMAIL_REGEX.fullmatch(candidate):
            repaired.append(candidate)
    return repaired


def _email_rank(email: str) -> tuple[int, int, int, int]:
    local = email.split("@", 1)[0]
    domain = email.split("@", 1)[1] if "@" in email else ""
    has_dot = 1 if "." in local else 0
    starts_alpha = 1 if local[:1].isalpha() else 0
    leading_digits = len(local) - len(local.lstrip("0123456789"))
    suspicious = 1 if any(part in local for part in SUSPICIOUS_LOCAL_PARTS) else 0
    common_provider = 1 if any(domain == f"{provider}.com" for provider in COMMON_EMAIL_PROVIDERS) else 0
    return (
        common_provider,
        -suspicious,
        starts_alpha,
        has_dot,
        -leading_digits,
        len(local),
    )


def _normalize_email_candidate(email: str) -> str:
    clean = email.strip(" <>[](){}.,;:'\"").lower()
    if "@" not in clean:
        return clean

    local, domain = clean.split("@", 1)
    local = re.sub(r"^\d{1,6}(?=[a-z])", "", local)
    for prefix in SUSPICIOUS_LOCAL_PARTS:
        if local.startswith(prefix) and len(local) > len(prefix) + 3:
            local = local[len(prefix):]
            break
    return f"{local}@{domain}"


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
    found.extend(_extract_missing_at_emails(source))
    repaired: List[str] = []
    for email in list(found):
        repaired.extend(_repair_embedded_provider_email(email))
    found.extend(repaired)

    normalized: List[str] = []
    seen: Set[str] = set()
    for email in found:
        clean = _normalize_email_candidate(email)
        if "@" in clean:
            local = clean.split("@", 1)[0]
            if not _is_valid_local_part(local):
                continue
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)

    # If we have a more complete local-part on the same domain, drop strict suffix variants
    # like `khtb01@gmail.com` when `yaseen.khtb01@gmail.com` is also present.
    filtered: List[str] = []
    for email in normalized:
        local, domain = email.split("@", 1)
        shadowed = False
        for other in normalized:
            if other == email:
                continue
            other_local, other_domain = other.split("@", 1)
            if domain != other_domain:
                continue
            if other_local.endswith(local) and len(other_local) >= len(local) + 2:
                shadowed = True
                break
        if not shadowed:
            filtered.append(email)
    filtered.sort(key=_email_rank, reverse=True)
    return filtered
