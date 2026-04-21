"""IV Rank & IV Percentile (spec §6.2).

    iv_rank      = (IV_now - IV_min_1Y) / (IV_max_1Y - IV_min_1Y) × 100
    iv_percentile = count(days where IV < IV_now) / 252 × 100
"""
from __future__ import annotations

from typing import List

from app.db.repositories import IVHistoryRepo


def iv_rank(iv_now: float, history: List[float]) -> float:
    if not history or iv_now is None:
        return 50.0
    lo = min(history)
    hi = max(history)
    if hi - lo < 1e-9:
        return 50.0
    return max(0.0, min(100.0, (iv_now - lo) / (hi - lo) * 100))


def iv_percentile(iv_now: float, history: List[float]) -> float:
    if not history or iv_now is None:
        return 50.0
    below = sum(1 for x in history if x < iv_now)
    # Denominator is 252 per spec; if we have less history, use len.
    denom = max(252, len(history))
    return max(0.0, min(100.0, below / denom * 100))


def compute_iv_metrics(instrument: str, iv_now: float) -> dict:
    """Pulls 1Y IV history from DB and returns both metrics + a state label."""
    history = IVHistoryRepo.last_252(instrument)
    r = iv_rank(iv_now, history)
    p = iv_percentile(iv_now, history)
    state = ("CHEAP OPTIONS" if r < 30 else
             "FAIR VALUE" if r < 55 else
             "EXPENSIVE OPTIONS" if r < 75 else "EXTREME PREMIUM")
    return {"iv_rank": r, "iv_percentile": p, "iv_state": state,
            "history_days": len(history)}
