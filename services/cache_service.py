import threading
from typing import Any, Callable

_MISSING = object()


class MemoryCache:
    """Thread-safe in-memory cache scoped to one batch run."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return default

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        value = self.get(key, _MISSING)
        if value is not _MISSING:
            return value
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


llm_cache = MemoryCache()
github_cache = MemoryCache()
url_cache = MemoryCache()


def reset_all() -> None:
    for cache in (llm_cache, github_cache, url_cache):
        cache.clear()
