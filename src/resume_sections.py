import re
from functools import lru_cache
from typing import Dict


SECTION_PATTERNS = {
    "skills": (
        r"skills",
        r"technical skills",
        r"technical skills and tools",
        r"skills and tools",
        r"tools and technologies",
        r"core competencies",
        r"tech stack",
        r"competencies",
        r"technologies",
    ),
    "experience": (
        r"experience",
        r"work experience",
        r"work history",
        r"employment",
        r"employment history",
        r"professional experience",
        r"career history",
    ),
    "projects": (
        r"projects",
        r"project experience",
        r"selected projects",
        r"personal projects",
        r"academic projects",
    ),
    "education": (
        r"education",
        r"academic background",
        r"academic qualifications",
    ),
}


def _normalize_heading(line: str) -> str:
    lowered = line.strip().lower()
    lowered = lowered.strip("-•*|:> ")
    lowered = lowered.replace("&", " and ")
    lowered = lowered.replace("/", " ")
    lowered = re.sub(r"[^a-z0-9 +#.-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip(" :-")


def _is_heading(line: str, pattern: str) -> bool:
    normalized = _normalize_heading(line)
    if not normalized:
        return False
    if re.fullmatch(pattern, normalized):
        return True
    return normalized.startswith(pattern + " ") and len(normalized.split()) <= 6


@lru_cache(maxsize=256)
def _split_resume_sections_cached(text: str) -> tuple[tuple[str, str], ...]:
    sections = {
        "skills": "",
        "experience": "",
        "projects": "",
        "education": "",
        "other": "",
    }

    current = "other"
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        next_section = None
        for name, patterns in SECTION_PATTERNS.items():
            if any(_is_heading(line, pattern) for pattern in patterns):
                next_section = name
                break

        if next_section is not None:
            current = next_section
            continue

        sections[current] += line + "\n"

    return tuple((name, value.strip()) for name, value in sections.items())


def split_resume_sections(text: str) -> Dict[str, str]:
    return dict(_split_resume_sections_cached(text or ""))
