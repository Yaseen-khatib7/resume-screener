from pathlib import Path
import io
import re
import zipfile
import fitz  # PyMuPDF
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT


CHAR_REPLACEMENTS = {
    "\u00a0": " ",
    "\u200b": "",
    "\ufeff": "",
    "â€¢": "•",
    "â€“": "-",
    "â€”": "-",
    "â€": "\"",
    "’": "'",
    "“": "\"",
    "”": "\"",
}


def _normalize_extracted_text(text: str) -> str:
    normalized = text or ""
    for source, target in CHAR_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _format_links(links: list[str]) -> str:
    cleaned = []
    seen = set()
    for link in links:
        value = (link or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    if not cleaned:
        return ""
    return "\n".join(f"HYPERLINK: {link}" for link in cleaned)


def _dedupe_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen = set()
    for line in lines:
        value = re.sub(r"\s+", " ", (line or "").strip())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned


def _read_docx_xml_text(data: bytes) -> tuple[list[str], list[str]]:
    text_parts: list[str] = []
    links: list[str] = []

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()

        xml_targets = [
            name
            for name in names
            if name.startswith("word/")
            and name.endswith(".xml")
            and not name.endswith(".rels")
        ]
        rel_targets = [name for name in names if name.startswith("word/") and name.endswith(".rels")]

        for name in xml_targets:
            try:
                xml_text = archive.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue

            xml_text = re.sub(r"</w:p>|</w:tr>|</w:tc>|</w:tbl>|</w:txbxContent>|</v:textbox>", "\n", xml_text)
            xml_text = re.sub(r"<[^>]+>", " ", xml_text)
            xml_text = re.sub(r"[ \t\r\f\v]+", " ", xml_text)
            xml_text = re.sub(r"\n+", "\n", xml_text)
            text_parts.extend(part.strip() for part in xml_text.split("\n") if part.strip())

        for name in rel_targets:
            try:
                rel_text = archive.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for match in re.findall(r'Target="([^"]+)"', rel_text):
                if match.strip():
                    links.append(match.strip())

    return _dedupe_lines(text_parts), _dedupe_lines(links)


def read_pdf_bytes(data: bytes) -> str:
    doc = fitz.open(stream=data, filetype="pdf")
    text = []
    links: list[str] = []
    for page in doc:
        text.append(page.get_text("text"))
        for link in page.get_links():
            uri = str(link.get("uri") or "").strip()
            if uri:
                links.append(uri)

    link_block = _format_links(links)
    combined = "\n".join(part for part in ["\n".join(text), link_block] if part).strip()
    return _normalize_extracted_text(combined)


def read_docx_bytes(data: bytes) -> str:
    bio = io.BytesIO(data)
    doc = Document(bio)
    parts = []
    links: list[str] = []
    for p in doc.paragraphs:
        parts.append(p.text)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_text = " ".join(paragraph.text for paragraph in cell.paragraphs if paragraph.text.strip())
                if cell_text.strip():
                    parts.append(cell_text)

    for section in doc.sections:
        for paragraph in section.header.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)
        for paragraph in section.footer.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)

    for rel in doc.part.rels.values():
        if rel.reltype == RT.HYPERLINK:
            target = str(rel.target_ref or "").strip()
            if target:
                links.append(target)

    xml_parts, xml_links = _read_docx_xml_text(data)
    parts.extend(xml_parts)
    links.extend(xml_links)

    parts = _dedupe_lines(parts)
    link_block = _format_links(links)
    combined = "\n".join(part for part in ["\n".join(parts), link_block] if part).strip()
    return _normalize_extracted_text(combined)


def read_txt_bytes(data: bytes) -> str:
    return _normalize_extracted_text(data.decode("utf-8", errors="ignore"))


def load_uploaded_file(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return read_pdf_bytes(data)
    elif suffix == ".docx":
        return read_docx_bytes(data)
    elif suffix in [".txt", ".md"]:
        return read_txt_bytes(data)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
