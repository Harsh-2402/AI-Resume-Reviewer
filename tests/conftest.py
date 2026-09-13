import io
import zipfile

import pytest

from services import cache_service, llm_service


class FakeLLM:
    """Routes generate_structured calls by schema; tests override per schema."""

    def __init__(self) -> None:
        self.responses: dict[type, object] = {}
        self.factories: dict[type, object] = {}
        self.fail_for: set[type] = set()
        self.calls: list[tuple[str, str]] = []

    def generate_structured(self, prompt, schema, **_kwargs):
        self.calls.append((schema.__name__, prompt))
        if schema in self.fail_for:
            raise llm_service.LLMError(f"simulated failure for {schema.__name__}")
        if schema in self.factories:
            return self.factories[schema](prompt)
        if schema in self.responses:
            return self.responses[schema].model_copy(deep=True)
        return schema()

    def count(self, schema) -> int:
        return sum(1 for name, _ in self.calls if name == schema.__name__)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_service, "generate_structured", fake.generate_structured)
    return fake


@pytest.fixture(autouse=True)
def _reset_caches():
    cache_service.reset_all()
    yield
    cache_service.reset_all()


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text: str) -> bytes:
    """Minimal single-page PDF whose text PyPDF2 can extract."""
    lines = text.split("\n")
    content = ("BT /F1 10 Tf 12 TL 36 780 Td " + " ".join(f"({_pdf_escape(l)}) Tj T*" for l in lines) + " ET")
    content_bytes = content.encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content_bytes) + content_bytes + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_docx(text: str) -> bytes:
    from docx import Document

    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


SAMPLE_RESUME = """Jane Doe
jane.doe@example.com | +1 555 222 3333 | github.com/janedoe | linkedin.com/in/janedoe
EDUCATION
B.S. Computer Science, State University, 2025, GPA 3.7/4.0
Coursework: Data Structures, Databases, Distributed Systems, Machine Learning
SKILLS
Python, FastAPI, PostgreSQL, Docker, React, AWS
PROJECTS
RAG Chatbot - retrieval pipeline with LangChain, Chroma, FastAPI; deployed on AWS. github.com/janedoe/rag-bot
Task Tracker - React + Node app with JWT auth. https://tasks.janedoe.dev
CERTIFICATIONS
AWS Certified Cloud Practitioner (2024) https://www.credly.com/badges/abc123
ACHIEVEMENTS
2nd place, University Hackathon 2024 (team of 3)
Dean's List 2023"""

SAMPLE_JD = """Software Engineering Intern - Backend
We are looking for a student intern to build backend services.
Required: Python, FastAPI or Flask, PostgreSQL, Docker, REST APIs, Git.
Preferred: AWS, Kubernetes, CI/CD, unit testing.
Education: pursuing a BS in Computer Science or related field."""


@pytest.fixture
def sample_resume_text():
    return SAMPLE_RESUME


@pytest.fixture
def sample_jd_text():
    return SAMPLE_JD


@pytest.fixture
def pdf_factory():
    return make_pdf


@pytest.fixture
def zip_factory():
    return make_zip
