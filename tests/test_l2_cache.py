import tempfile

from agora.cache.l2_cache import L2Cache
from agora.db.database import Database


def _fresh_db():
    tmp = tempfile.mkdtemp()
    return Database(path=tmp + "/agora.db")


def test_l2_set_and_get():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=3600)
    cache.set("agora.query", "test query", 5, "test-model", {"result": "data"})
    result = cache.get("agora.query", "test query", 5, "test-model")
    assert result == {"result": "data"}


def test_l2_miss_returns_none():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=3600)
    result = cache.get("agora.query", "nonexistent", 5, "test-model")
    assert result is None


def test_l2_expiry():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=1)
    cache.set("agora.query", "test", 5, "test-model", {"result": "data"})
    import time

    time.sleep(1.5)
    result = cache.get("agora.query", "test", 5, "test-model")
    assert result is None


def test_l2_hit_count():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=3600)
    cache.set("agora.query", "test", 5, "test-model", {"result": "hit"})
    cache.get("agora.query", "test", 5, "test-model")
    cache.get("agora.query", "test", 5, "test-model")
    stats = cache.stats()
    assert stats["total_hits"] >= 2


def test_l2_stats():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=3600)
    stats = cache.stats()
    assert "total_entries" in stats
    assert "total_hits" in stats
    assert "total_size_bytes" in stats
    assert stats["total_entries"] == 0

    cache.set("agora.query", "a", 5, "test-model", {"result": "a"})
    stats = cache.stats()
    assert stats["total_entries"] == 1


def test_l2_clear():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=3600)
    cache.set("agora.query", "a", 5, "test-model", {"result": "a"})
    cache.clear()
    result = cache.get("agora.query", "a", 5, "test-model")
    assert result is None
    assert cache.stats()["total_entries"] == 0


def test_l2_prune_expired():
    db = _fresh_db()
    cache = L2Cache(db, ttl_seconds=0)
    cache.set("agora.query", "a", 5, "test-model", {"result": "a"})
    import time

    time.sleep(0.1)
    cache.prune_expired()
    stats = cache.stats()
    assert stats["total_entries"] == 0
