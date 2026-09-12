import re
from urllib.parse import urlparse

URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'()\[\]{}]+|"
    r"\b(?:github\.com|linkedin\.com|gitlab\.com|bitbucket\.org|"
    r"credly\.com|coursera\.org|udemy\.com|kaggle\.com|leetcode\.com|"
    r"hackerrank\.com|devpost\.com|vercel\.app|netlify\.app|herokuapp\.com|"
    r"streamlit\.app|huggingface\.co)/[^\s<>\"'()\[\]{}]+",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s().]{7,}\d)")

_GITHUB_RESERVED = {
    "features", "topics", "trending", "explore", "marketplace", "settings", "orgs",
    "organizations", "login", "join", "about", "pricing", "site", "sponsors",
    "collections", "events", "issues", "pulls", "notifications", "search", "apps",
}


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n[...truncated...]"


def _strip_url_punct(url: str) -> str:
    return url.rstrip(".,;:!?'\"")


def extract_urls(text: str) -> list[str]:
    seen: dict[str, str] = {}
    for match in URL_RE.finditer(text):
        url = _strip_url_punct(match.group(0))
        key = url.lower().rstrip("/")
        if key not in seen:
            seen[key] = url
    return list(seen.values())


def ensure_scheme(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return "https://" + url.lstrip("/")
    return url


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(ensure_scheme(url))
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and "." in parsed.netloc


def extract_email(text: str) -> str:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    for match in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 10 <= len(digits) <= 15:
            return match.group(0).strip()
    return ""


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _github_path_parts(url: str) -> list[str]:
    parsed = urlparse(ensure_scheme(url))
    host = parsed.netloc.lower()
    if host not in ("github.com", "www.github.com"):
        return []
    return [p for p in parsed.path.split("/") if p]


def github_username_from_url(url: str) -> str | None:
    if not url:
        return None
    parts = _github_path_parts(url)
    if not parts:
        return None
    user = parts[0].strip("@")
    if user.lower() in _GITHUB_RESERVED or not re.match(r"^[A-Za-z0-9-]{1,39}$", user):
        return None
    return user


def github_repo_from_url(url: str) -> tuple[str, str] | None:
    parts = _github_path_parts(url or "")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], re.sub(r"\.git$", "", parts[1])
    if owner.lower() in _GITHUB_RESERVED:
        return None
    return owner, repo


def find_github_urls(text: str) -> list[str]:
    return [u for u in extract_urls(text) if "github.com" in u.lower()]


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9+#.]+", (text or "").lower()) if t]


def dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = (item or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def safe_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def gpa_on_4_scale(gpa: str) -> float | None:
    """Best-effort normalization: '8.7/10' → 3.48, '3.6' → 3.6, '85%' → 3.4."""
    if not gpa:
        return None
    text = str(gpa).strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
    if m:
        num, denom = float(m.group(1)), float(m.group(2))
        return round(num / denom * 4, 2) if denom > 0 else None
    if "%" in text:
        val = safe_float(text)
        return round(val / 100 * 4, 2) if val is not None else None
    val = safe_float(text)
    if val is None:
        return None
    if val <= 4.0:
        return val
    if val <= 5.0:
        return round(val / 5 * 4, 2)
    if val <= 10.0:
        return round(val / 10 * 4, 2)
    if val <= 100.0:
        return round(val / 100 * 4, 2)
    return None
