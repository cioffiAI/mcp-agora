import hashlib
import json

from agora.db.database import Database


def _cache_key(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class L2Cache:
    def __init__(self, db: Database, ttl_seconds: int = 86400):
        self._db = db
        self._ttl_seconds = ttl_seconds

    def get(self, tool: str, query: str, top_k: int, model: str, collection: str = "knowledge") -> dict | None:
        key = _cache_key(
            {
                "tool": tool,
                "collection": collection,
                "query": query,
                "top_k": top_k,
                "model": model,
            }
        )
        row = self._db.l2_get(key)
        if row is None:
            return None
        return json.loads(row["result_json"])

    def set(self, tool: str, query: str, top_k: int, model: str, value: dict, collection: str = "knowledge"):
        key = _cache_key(
            {
                "tool": tool,
                "collection": collection,
                "query": query,
                "top_k": top_k,
                "model": model,
            }
        )
        self._db.l2_set(key, result_json=json.dumps(value), ttl_seconds=self._ttl_seconds)

    def stats(self) -> dict:
        return self._db.l2_stats()

    def prune_expired(self):
        self._db.l2_prune_expired()

    def clear(self):
        self._db.l2_clear()
