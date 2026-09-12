"""Read-only GitHub REST access (public data only), cached per batch."""
import re
from typing import Any

import requests

import config
from services.cache_service import github_cache

BASE_URL = "https://api.github.com"
session = requests.Session()


class GitHubError(Exception):
    pass


class GitHubNotFound(GitHubError):
    pass


class GitHubRateLimited(GitHubError):
    pass


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "InternCandidateEvaluator/1.0",
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def has_token() -> bool:
    return bool(config.GITHUB_TOKEN)


def _get(path: str, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    key = url + ("?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())) if params else "")
    cached = github_cache.get(key)
    if cached is not None:
        if isinstance(cached, Exception):
            raise cached
        return cached

    try:
        resp = session.get(url, headers=_headers(), params=params, timeout=config.GITHUB_TIMEOUT)
    except requests.exceptions.Timeout as exc:
        raise GitHubError("GitHub request timed out") from exc
    except requests.exceptions.RequestException as exc:
        raise GitHubError(f"GitHub request failed: {str(exc)[:80]}") from exc

    headers = {k.lower(): v for k, v in resp.headers.items()}
    if resp.status_code in (403, 429):
        remaining = headers.get("x-ratelimit-remaining")
        body = ""
        try:
            body = resp.text[:200].lower()
        except Exception:  # noqa: BLE001
            pass
        if remaining == "0" or "rate limit" in body or resp.status_code == 429:
            exc = GitHubRateLimited("GitHub API rate limit reached")
            github_cache.set(key, exc)
            raise exc
        exc = GitHubError(f"GitHub access forbidden (HTTP {resp.status_code})")
        github_cache.set(key, exc)
        raise exc
    if resp.status_code == 404:
        exc = GitHubNotFound(f"GitHub resource not found: {path}")
        github_cache.set(key, exc)
        raise exc
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub HTTP {resp.status_code} for {path}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise GitHubError("GitHub returned non-JSON response") from exc
    result = (data, headers)
    github_cache.set(key, result)
    return result


def get_user(username: str) -> dict:
    data, _ = _get(f"/users/{username}")
    return data


def get_repos(username: str, limit: int | None = None) -> list[dict]:
    limit = limit or config.GITHUB_MAX_REPOS
    data, _ = _get(f"/users/{username}/repos", {"per_page": min(limit, 100), "sort": "pushed", "type": "owner"})
    return data if isinstance(data, list) else []


def get_repo(owner: str, repo: str) -> dict:
    data, _ = _get(f"/repos/{owner}/{repo}")
    return data


def get_languages(owner: str, repo: str) -> dict[str, int]:
    data, _ = _get(f"/repos/{owner}/{repo}/languages")
    return data if isinstance(data, dict) else {}


def get_readme_size(owner: str, repo: str) -> int:
    try:
        data, _ = _get(f"/repos/{owner}/{repo}/readme")
    except GitHubNotFound:
        return 0
    return int(data.get("size", 0)) if isinstance(data, dict) else 0


def get_tree_paths(owner: str, repo: str, branch: str) -> tuple[list[str], bool]:
    """Return (paths, truncated) of the default branch tree."""
    try:
        data, _ = _get(f"/repos/{owner}/{repo}/git/trees/{branch}", {"recursive": "1"})
    except GitHubNotFound:
        return [], False
    if not isinstance(data, dict):
        return [], False
    paths = [t.get("path", "") for t in data.get("tree", []) if t.get("type") == "blob"]
    return paths, bool(data.get("truncated"))


_LAST_PAGE_RE = re.compile(r'[?&]page=(\d+)>; rel="last"')


def get_commits(owner: str, repo: str, sample: int = 30) -> tuple[int, list[dict]]:
    """Return (total_commit_count, recent_commits). Count is derived from the Link header."""
    try:
        data, headers = _get(f"/repos/{owner}/{repo}/commits", {"per_page": sample})
    except GitHubNotFound:
        return 0, []
    except GitHubError as exc:
        if "409" in str(exc):  # empty repository
            return 0, []
        raise
    recent = data if isinstance(data, list) else []
    link = headers.get("link", "")
    match = _LAST_PAGE_RE.search(link)
    if match:
        last_page = int(match.group(1))
        # last page has between 1 and `sample` commits; estimate conservatively
        total = (last_page - 1) * sample + max(1, len(recent) if last_page == 1 else sample // 2)
    else:
        total = len(recent)
    return total, recent
