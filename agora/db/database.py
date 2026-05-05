import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT DEFAULT 'unknown',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    sessions_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS provenance (
    entry_id TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    source_session TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entry_id, source_agent, source_session)
);

CREATE TABLE IF NOT EXISTS l2_cache (
    cache_key TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    ttl_seconds INTEGER NOT NULL DEFAULT 86400,
    hit_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | None = None):
        self._path = Path(path or Path.home() / ".agora" / "agora.db").expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._connection()
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    # --- Agents ---

    def register_agent(self, agent: str, agent_type: str = "unknown") -> dict:
        conn = self._connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            row = conn.execute(
                "SELECT * FROM agents WHERE id = ?", (agent,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE agents SET last_seen = ?, sessions_count = sessions_count + 1 WHERE id = ?",
                    (now, agent),
                )
            else:
                conn.execute(
                    "INSERT INTO agents (id, name, agent_type, first_seen, last_seen, sessions_count) VALUES (?, ?, ?, ?, ?, 1)",
                    (agent, agent, agent_type, now, now),
                )
            conn.commit()
            return {"agent": agent, "new": row is None}
        finally:
            conn.close()

    def get_agent(self, agent: str) -> dict | None:
        conn = self._connection()
        try:
            row = conn.execute(
                "SELECT * FROM agents WHERE id = ?", (agent,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def list_agents(self) -> list[dict]:
        conn = self._connection()
        try:
            rows = conn.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_agents(self) -> int:
        conn = self._connection()
        try:
            return conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        finally:
            conn.close()

    def delete_agent(self, agent: str):
        conn = self._connection()
        try:
            conn.execute("DELETE FROM agents WHERE id = ?", (agent,))
            conn.commit()
        finally:
            conn.close()

    # --- Provenance ---

    def add_provenance(self, entry_id: str, source_agent: str, source_session: str, confidence: float = 0.5):
        conn = self._connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO provenance (entry_id, source_agent, source_session, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
                (entry_id, source_agent, source_session, confidence, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_provenance(self, entry_id: str) -> dict | None:
        conn = self._connection()
        try:
            row = conn.execute(
                "SELECT * FROM provenance WHERE entry_id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def list_provenance(self, agent: str | None = None) -> list[dict]:
        conn = self._connection()
        try:
            if agent:
                rows = conn.execute(
                    "SELECT * FROM provenance WHERE source_agent = ? ORDER BY created_at DESC", (agent,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM provenance ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_provenance(self, entry_ids: list[str]):
        conn = self._connection()
        try:
            placeholders = ",".join("?" for _ in entry_ids)
            conn.execute(f"DELETE FROM provenance WHERE entry_id IN ({placeholders})", entry_ids)
            conn.commit()
        finally:
            conn.close()

    def delete_provenance_by_agent(self, agent: str):
        conn = self._connection()
        try:
            conn.execute("DELETE FROM provenance WHERE source_agent = ?", (agent,))
            conn.commit()
        finally:
            conn.close()

    # --- L2 Cache ---

    def l2_get(self, cache_key: str) -> dict | None:
        conn = self._connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            row = conn.execute(
                "SELECT * FROM l2_cache WHERE cache_key = ? AND expires_at > ?",
                (cache_key, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE l2_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            conn.commit()
            return dict(row)
        finally:
            conn.close()

    def l2_set(self, cache_key: str, result_json: str, ttl_seconds: int = 86400):
        conn = self._connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            expires_at = datetime.fromtimestamp(
                time.time() + ttl_seconds, tz=timezone.utc
            ).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO l2_cache (cache_key, result_json, ttl_seconds, hit_count, created_at, expires_at) VALUES (?, ?, ?, 0, ?, ?)",
                (cache_key, result_json, ttl_seconds, now, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def l2_prune_expired(self) -> int:
        conn = self._connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute("DELETE FROM l2_cache WHERE expires_at <= ?", (now,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def l2_clear(self):
        conn = self._connection()
        try:
            conn.execute("DELETE FROM l2_cache")
            conn.commit()
        finally:
            conn.close()

    def l2_stats(self) -> dict:
        conn = self._connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM l2_cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM l2_cache WHERE expires_at <= ?",
                (datetime.now(timezone.utc).isoformat(),),
            ).fetchone()[0]
            total_hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM l2_cache").fetchone()[0]
            total_size = conn.execute("SELECT COALESCE(SUM(LENGTH(result_json)), 0) FROM l2_cache").fetchone()[0]
            return {
                "total_entries": total,
                "expired_entries": expired,
                "total_hits": total_hits,
                "total_size_bytes": total_size,
            }
        finally:
            conn.close()

    def db_size_bytes(self) -> int:
        try:
            return self._path.stat().st_size
        except OSError:
            return 0
