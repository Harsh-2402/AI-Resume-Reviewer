"""Fake HTTP session for GitHub / URL services."""
import json


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text="", raw_bytes=b""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text if text else (json.dumps(payload) if payload is not None else "")
        self.raw = _Raw(raw_bytes or self.text.encode())

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def close(self):
        pass


class _Raw:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, n=-1, decode_content=True):
        return self._data if n < 0 else self._data[:n]


class FakeSession:
    """Routes GET by URL substring; unknown URLs → 404. Records calls."""

    def __init__(self):
        self.routes: list[tuple[str, object]] = []
        self.calls: list[str] = []
        self.headers = {}

    def route(self, needle: str, response):
        self.routes.append((needle, response))

    def get(self, url, headers=None, params=None, timeout=None, allow_redirects=True, stream=False):
        full = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        self.calls.append(full)
        for needle, response in self.routes:
            if needle in full:
                if isinstance(response, Exception):
                    raise response
                return response() if callable(response) else response
        return FakeResponse(404, {"message": "Not Found"})


def repo(name, language="Python", pushed="2026-08-01T00:00:00Z", fork=False, description="", topics=None, stars=0):
    return {
        "name": name, "html_url": f"https://github.com/u/{name}", "language": language, "pushed_at": pushed,
        "created_at": "2025-01-01T00:00:00Z", "fork": fork, "description": description, "topics": topics or [],
        "stargazers_count": stars, "forks_count": 0, "default_branch": "main",
    }


def commits(n, meaningful=True):
    msg = "Implement retrieval pipeline with chunking and reranking" if meaningful else "update"
    return [{"commit": {"message": msg, "author": {"date": "2026-08-01T00:00:00Z"}}} for _ in range(n)]
