"""Centralized configuration. Every value can be overridden via environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ─── Gemini ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_MAX_CONCURRENT_REQUESTS = _env_int("GEMINI_MAX_CONCURRENT_REQUESTS", 4)
GEMINI_TIMEOUT_SECONDS = _env_int("GEMINI_TIMEOUT_SECONDS", 120)
GEMINI_MAX_RETRIES = _env_int("GEMINI_MAX_RETRIES", 4)
GEMINI_RETRY_BASE_DELAY = _env_float("GEMINI_RETRY_BASE_DELAY", 2.0)
GEMINI_TEMPERATURE = _env_float("GEMINI_TEMPERATURE", 0.1)

# ─── Batch processing ────────────────────────────────────────────────────────
MAX_CONCURRENT_CANDIDATES = _env_int("MAX_CONCURRENT_CANDIDATES", 10)
MAX_RESUME_CHARS = _env_int("MAX_RESUME_CHARS", 12000)
MIN_RESUME_CHARS = _env_int("MIN_RESUME_CHARS", 50)

# ─── GitHub ──────────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_TIMEOUT = _env_int("GITHUB_TIMEOUT", 15)
GITHUB_MAX_REPOS = _env_int("GITHUB_MAX_REPOS", 30)
GITHUB_MAX_DEEP_REPOS = _env_int("GITHUB_MAX_DEEP_REPOS", 6)

# ─── External URLs (project links, credential pages) ─────────────────────────
URL_TIMEOUT = _env_int("URL_TIMEOUT", 10)
MAX_PROJECT_LINK_CHECKS = _env_int("MAX_PROJECT_LINK_CHECKS", 6)
MAX_CREDENTIAL_CHECKS = _env_int("MAX_CREDENTIAL_CHECKS", 6)

# ─── Internship scoring ──────────────────────────────────────────────────────
INTERNSHIP_WEIGHTS: dict[str, float] = {
    "education": 0.15,
    "coursework": 0.10,
    "technical_skills": 0.15,
    "projects": 0.25,
    "github": 0.10,
    "certifications": 0.05,
    "achievements": 0.05,
    "jd_alignment": 0.10,
    "learning_potential": 0.05,
}

COMPONENT_LABELS: dict[str, str] = {
    "education": "Education",
    "coursework": "Coursework",
    "technical_skills": "Technical Skills",
    "projects": "Projects",
    "github": "GitHub",
    "certifications": "Certifications",
    "achievements": "Achievements",
    "jd_alignment": "JD Alignment",
    "learning_potential": "Learning Potential",
}

# (minimum score, classification) — evaluated top-down
CLASSIFICATION_THRESHOLDS: list[tuple[float, str]] = [
    (90, "Exceptional Internship Candidate"),
    (80, "Strong Internship Candidate"),
    (70, "Good Internship Candidate"),
    (60, "Potential / Review"),
    (50, "Weak Match"),
    (0, "Low Match"),
]

RECOMMENDATION_BY_CLASSIFICATION: dict[str, str] = {
    "Exceptional Internship Candidate": "Strongly Recommend",
    "Strong Internship Candidate": "Recommend",
    "Good Internship Candidate": "Consider",
    "Potential / Review": "Needs Review",
    "Weak Match": "Do Not Prioritize",
    "Low Match": "Do Not Prioritize",
}

# ─── Reporting ───────────────────────────────────────────────────────────────
REPORT_FILENAME_PREFIX = "intern_candidate_evaluation"
