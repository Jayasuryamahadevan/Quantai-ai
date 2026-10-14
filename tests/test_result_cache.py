from app.core.result_cache import RunResultCache


def test_cache_reuses_values_within_same_run():
    now = [0.0]
    cache = RunResultCache(max_runs=2, ttl_seconds=10, clock=lambda: now[0])
    cache.put("a", "frame", [1, 2])
    cache.put("a", "schema", ["x"])
    assert cache.get("a", "frame") == [1, 2]
    assert cache.get("a", "schema") == ["x"]


def test_lru_eviction():
    cache = RunResultCache(max_runs=2)
    cache.put("a", "x", 1)
    cache.put("b", "x", 2)
    assert cache.get("a", "x") == 1
    cache.put("c", "x", 3)
    assert cache.get("b", "x") is None
    assert cache.get("a", "x") == 1


def test_ttl_and_clear():
    now = [1.0]
    cache = RunResultCache(ttl_seconds=10, clock=lambda: now[0])
    cache.put("a", "x", 99)
    now[0] = 11.0
    assert cache.get("a", "x") is None
    cache.put("b", "x", 3)
    cache.clear("b")
    assert cache.get("b", "x") is None
