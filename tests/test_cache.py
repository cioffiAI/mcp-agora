from agora.cache.l1_memory import L1Cache


def test_set_and_get():
    cache = L1Cache(maxsize=100, ttl=60)
    cache.set("agora.query", "test query", 5, "test-model", {"result": "data"})
    result = cache.get("agora.query", "test query", 5, "test-model")
    assert result == {"result": "data"}


def test_miss_returns_none():
    cache = L1Cache(maxsize=100, ttl=60)
    result = cache.get("agora.query", "nonexistent", 5, "test-model")
    assert result is None


def test_expiry():
    cache = L1Cache(maxsize=100, ttl=1)
    cache.set("agora.query", "test", 5, "test-model", {"result": "data"})
    import time

    time.sleep(1.5)
    result = cache.get("agora.query", "test", 5, "test-model")
    assert result is None


def test_hit_count():
    cache = L1Cache(maxsize=100, ttl=60)
    cache.set("agora.query", "a", 5, "test-model", {"result": "a"})
    cache.get("agora.query", "a", 5, "test-model")
    cache.get("agora.query", "b", 5, "test-model")
    stats = cache.stats()
    assert stats["hit_count"] == 1
    assert stats["miss_count"] == 1


def test_clear():
    cache = L1Cache(maxsize=100, ttl=60)
    cache.set("agora.query", "a", 5, "test-model", {"result": "a"})
    cache.clear()
    result = cache.get("agora.query", "a", 5, "test-model")
    assert result is None
