from io import BytesIO
from pathlib import Path

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

import config
from utils.text import clean_text


class DocumentExtractionError(Exception):
    pass


def extract_pdf_text(source: str | bytes) -> tuple[str, list[str]]:
    """Return (text, warnings). Raises DocumentExtractionError for unreadable files."""
    warnings: list[str] = []
    try:
        reader = PdfReader(BytesIO(source) if isinstance(source, bytes) else source, strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise DocumentExtractionError("PDF is password protected") from exc
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                warnings.append("A page could not be extracted")
    except DocumentExtractionError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError, KeyError, IndexError, AssertionError) as exc:
        raise DocumentExtractionError(f"Invalid or corrupted PDF: {str(exc)[:120]}") from exc

    text = clean_text("\n".join(pages))
    if len(text) < config.MIN_RESUME_CHARS:
        warnings.append(
            "Little or no extractable text — the PDF may be scanned or image-based; analysis will be limited"
        )
    return text, warnings


def extract_docx_text(source: str | bytes) -> str:
    from docx import Document

    try:
        doc = Document(BytesIO(source) if isinstance(source, bytes) else source)
    except Exception as exc:  # noqa: BLE001
        raise DocumentExtractionError(f"Invalid DOCX: {str(exc)[:120]}") from exc
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return clean_text("\n".join(parts))


def extract_document_text(data: bytes, filename: str) -> str:
    """JD/document text from PDF, DOCX or TXT bytes."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text, _ = extract_pdf_text(data)
        return text
    if suffix == ".docx":
        return extract_docx_text(data)
    if suffix in (".txt", ".md", ""):
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return clean_text(data.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise DocumentExtractionError("Could not decode text file")
    raise DocumentExtractionError(f"Unsupported file type: {suffix}")
