import re

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def chunk_lines(text: str, min_len: int = 25):
    # Split into bullet-ish lines first; fallback to sentences
    lines = []
    for raw in text.split("\n"):
        s = raw.strip(" •\t-")
        if len(s) >= min_len:
            lines.append(s)

    if not lines:
        parts = re.split(r"(?<=[.!?])\s+", text)
        lines = [p.strip() for p in parts if len(p.strip()) >= min_len]

    return lines[:200]