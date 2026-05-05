import hashlib
import json
import threading
from collections.abc import Callable

from cachetools import TTLCache


def _cache_key(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


_MISS_SENTINEL = object()


class L1Cache:
    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0

    def get(self, tool: str, query: str, top_k: int, model: str, collection: str = "knowledge") -> dict | None:
        key = _cache_key({
            "tool": tool,
            "collection": collection,
            "query": query,
            "top_k": top_k,
            "model": model,
        })
        with self._lock:
            result = self._cache.get(key, _MISS_SENTINEL)
            if result is not _MISS_SENTINEL:
                self._hit_count += 1
                return result
            self._miss_count += 1
            return None

    def set(self, tool: str, query: str, top_k: int, model: str, value: dict, collection: str = "knowledge"):
        key = _cache_key({
            "tool": tool,
            "collection": collection,
            "query": query,
            "top_k": top_k,
            "model": model,
        })
        with self._lock:
            self._cache[key] = value

    def clear(self):
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self._cache.maxsize,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "ttl_seconds": self._cache.ttl,
            }
