"""Redis cache wrapper with JSON ser/de and TTL helpers.

Used for: live indicator values, current session state, options chain snapshots,
analysis result deduplication (spec §12.3 — 100+ concurrent users).
"""
from __future__ import annotations

import json
from typing import Any, Optional

import redis

from app.config.settings import settings


class RedisCache:

    def __init__(self, url: Optional[str] = None) -> None:
        self._r = redis.Redis.from_url(url or settings.redis_url, decode_responses=True)

    # --- JSON ---

    def set_json(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        self._r.set(key, json.dumps(value, default=str), ex=ttl_seconds)

    def get_json(self, key: str) -> Any:
        raw = self._r.get(key)
        return json.loads(raw) if raw else None

    # --- raw ---

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        self._r.set(key, value, ex=ttl_seconds)

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def delete(self, *keys: str) -> None:
        if keys:
            self._r.delete(*keys)

    def incr(self, key: str, by: int = 1) -> int:
        return int(self._r.incrby(key, by))

    def exists(self, key: str) -> bool:
        return bool(self._r.exists(key))

    @property
    def raw(self) -> redis.Redis:
        return self._r


cache = RedisCache()


# --- Key helpers ---

def k_tick(instrument: str) -> str:
    return f"tick:{instrument}"


def k_candle(instrument: str, timeframe: str) -> str:
    return f"candle:{instrument}:{timeframe}"


def k_analysis(instrument: str) -> str:
    return f"analysis:{instrument}"


def k_options_chain(instrument: str, expiry: str) -> str:
    return f"chain:{instrument}:{expiry}"
