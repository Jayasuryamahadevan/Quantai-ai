"""Bounded single-process cache for per-run results.

Multi-worker deployments require a shared result store.
"""
from __future__ import annotations
import time
from collections import OrderedDict
from threading import RLock
from typing import Any, Callable


class RunResultCache:
    def __init__(self, max_runs: int = 32, ttl_seconds: float = 3600,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if max_runs < 1 or ttl_seconds <= 0:
            raise ValueError("Cache capacity and TTL must be positive")
        self.max_runs, self.ttl_seconds, self.clock = max_runs, ttl_seconds, clock
        self._runs: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = RLock()

    def _prune(self, now: float) -> None:
        for run_id, (created, _) in list(self._runs.items()):
            if now - created >= self.ttl_seconds:
                del self._runs[run_id]
        while len(self._runs) > self.max_runs:
            self._runs.popitem(last=False)

    def put(self, run_id: str, key: str, value: Any) -> None:
        with self._lock:
            now = self.clock()
            self._prune(now)
            created, items = self._runs.pop(run_id, (now, {}))
            items[key] = value
            self._runs[run_id] = (created, items)
            self._prune(now)

    def get(self, run_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            self._prune(self.clock())
            entry = self._runs.get(run_id)
            if entry is None:
                return default
            self._runs.move_to_end(run_id)
            return entry[1].get(key, default)

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)


_cache = RunResultCache()


def cache_put(run_id: str, key: str, value: Any) -> None:
    _cache.put(run_id, key, value)


def cache_get(run_id: str, key: str, default: Any = None) -> Any:
    return _cache.get(run_id, key, default)


def cache_clear(run_id: str) -> None:
    _cache.clear(run_id)
