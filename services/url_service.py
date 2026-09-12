"""Public URL checks for project links and credential pages. Never follows into private data."""
from urllib.parse import urlparse

import requests

import config
from services.cache_service import url_cache
from utils.text import ensure_scheme, is_valid_url

session = requests.Session()
session.headers.update({"User-Agent": "InternCandidateEvaluator/1.0 (+public-link-check)"})

KNOWN_CREDENTIAL_VERIFIERS = (
    "credly.com", "coursera.org", "aws.training", "learn.microsoft.com", "credentials.databricks.com",
    "certificates.cisco.com", "google.com/certificate", "cloud.google.com", "udemy.com/certificate",
    "edx.org/certificates", "verify.acloud.guru", "credential.net", "accredible.com", "youracclaim.com",
    "certiport.com", "pearsonvue.com", "linkedin.com/learning", "hackerrank.com/certificates",
    "kaggle.com/learn/certification", "nvidia.com", "snowflake.com", "oracle.com", "certificates.aws",
    "cloudskillsboost.google", "www.credly.com", "freecodecamp.org/certification",
)


def check_url(url: str, *, timeout: int | None = None) -> tuple[str, str, str]:
    """Return (status, detail, body_snippet). status ∈ accessible/inaccessible/broken/unknown."""
    if not url or not is_valid_url(url):
        return "unknown", "no valid URL", ""
    url = ensure_scheme(url)
    cached = url_cache.get(url)
    if cached is not None:
        return cached

    timeout = timeout or config.URL_TIMEOUT
    result: tuple[str, str, str]
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        code = resp.status_code
        body = ""
        try:
            content_type = resp.headers.get("Content-Type", "")
            if "text" in content_type or "json" in content_type or "html" in content_type:
                body = resp.raw.read(200_000, decode_content=True).decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            body = ""
        finally:
            resp.close()
        if 200 <= code < 300:
            result = ("accessible", f"HTTP {code}", body)
        elif code in (401, 403):
            result = ("inaccessible", f"HTTP {code} (access restricted)", "")
        elif code == 404 or code == 410:
            result = ("broken", f"HTTP {code}", "")
        elif code >= 500:
            result = ("inaccessible", f"HTTP {code} (server error)", "")
        else:
            result = ("unknown", f"HTTP {code}", body)
    except requests.exceptions.Timeout:
        result = ("inaccessible", "timed out", "")
    except requests.exceptions.SSLError:
        result = ("inaccessible", "SSL error", "")
    except requests.exceptions.ConnectionError:
        result = ("broken", "connection failed (DNS/refused)", "")
    except requests.exceptions.RequestException as exc:
        result = ("unknown", f"request error: {str(exc)[:60]}", "")

    url_cache.set(url, result)
    return result


def is_known_verifier(url: str) -> bool:
    host_and_path = (urlparse(ensure_scheme(url)).netloc + urlparse(ensure_scheme(url)).path).lower()
    return any(v in host_and_path for v in KNOWN_CREDENTIAL_VERIFIERS)


def verify_credential(url: str, *, cert_name: str, issuer: str, candidate_name: str) -> tuple[str, str]:
    """Neutral verification heuristic — never claims a credential is fake."""
    if not url or not is_valid_url(url):
        return "No Verification Information", "no credential URL provided"
    status, detail, body = check_url(url)
    if status != "accessible":
        return "Not Verifiable", f"credential page {status} ({detail})"
    text = body.lower()
    name_hit = bool(candidate_name) and candidate_name.lower().split()[0] in text
    cert_hit = any(word.lower() in text for word in cert_name.split() if len(word) > 3) if cert_name else False
    issuer_hit = bool(issuer) and issuer.lower() in text
    if is_known_verifier(url) and (name_hit or cert_hit):
        return "Verified", "credential page on a known verifier references the candidate/certification"
    if cert_hit or issuer_hit or name_hit:
        return "Evidence Found", "public page references the certification"
    return "Not Verifiable", "credential page reachable but could not be matched from public content"
