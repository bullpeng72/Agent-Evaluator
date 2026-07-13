"""
agent_evaluator.serve.cache
===========================
H3: Dashboard API 응답 캐시 — 간단한 in-memory TTL LRU 캐시.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class ResponseCache:
    """TTL 기반 in-memory LRU 응답 캐시 (H3).

    대시보드의 무거운 집계 엔드포인트 응답을 캐싱해 성능을 개선한다.

    Args:
        maxsize: 최대 캐시 항목 수 (기본 128). 초과 시 가장 오래된 항목 제거.
        ttl: 항목 유효 시간(초, 기본 30).

    Example::
        cache = ResponseCache(maxsize=64, ttl=60)
        cache.set("stats", {"total": 100})
        val = cache.get("stats")  # {"total": 100}
    """

    def __init__(self, maxsize: int = 128, ttl: float = 30.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Any | None:
        """캐시에서 값을 읽는다. TTL 만료 시 None 반환."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, expiry = entry
        if time.time() > expiry:
            del self._cache[key]
            self._misses += 1
            return None
        # LRU: 최근 접근 항목을 뒤로 이동
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """캐시에 값을 저장한다."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.time() + self.ttl)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)  # 가장 오래된 항목 제거

    def invalidate(self, key: str) -> None:
        """특정 키를 캐시에서 제거한다."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """캐시 전체를 비운다."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, Any]:
        """캐시 통계를 반환한다."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "ttl": self.ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }


# 전역 캐시 인스턴스 (대시보드 서버 공유)
_GLOBAL_CACHE = ResponseCache(maxsize=128, ttl=30)
