"""Daily loss limit tracker — spec §8.3 rule #7.

Per-user: daily_pnl ≤ -3% of capital → trading suspended for the day.
State stored in Redis with TTL aligned to IST midnight.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from app.data.cache import cache
from app.utils.clock import ist, now_ist


class DailyLimitTracker:

    @staticmethod
    def _key(chat_id: int, day: str) -> str:
        return f"daily_pnl:{chat_id}:{day}"

    @staticmethod
    def _ttl_to_midnight() -> int:
        now = now_ist()
        midnight = ist.localize(datetime.combine(now.date() + timedelta(days=1), time(0, 5)))
        return max(60, int((midnight - now).total_seconds()))

    @classmethod
    def record_pnl(cls, chat_id: int, pnl_rs: float) -> float:
        day = now_ist().strftime("%Y-%m-%d")
        k = cls._key(chat_id, day)
        current = float(cache.get(k) or 0.0)
        new = current + pnl_rs
        cache.set(k, str(new), ttl_seconds=cls._ttl_to_midnight())
        return new

    @classmethod
    def current(cls, chat_id: int) -> float:
        day = now_ist().strftime("%Y-%m-%d")
        return float(cache.get(cls._key(chat_id, day)) or 0.0)

    @classmethod
    def is_suspended(cls, chat_id: int, capital: float, limit_pct: float = 3.0) -> bool:
        loss = -cls.current(chat_id)           # positive when in loss
        return loss >= capital * (limit_pct / 100.0)
