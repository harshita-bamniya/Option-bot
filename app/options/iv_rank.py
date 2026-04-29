"""IV Rank & IV Percentile (spec §6.2).

    iv_rank      = (IV_now - IV_min_1Y) / (IV_max_1Y - IV_min_1Y) × 100
    iv_percentile = count(days where IV < IV_now) / 252 × 100

When live options chain is unavailable (trial account / NSE block),
realized_vol_rank() estimates IV rank from daily OHLCV candles using
Yang-Zhang historical volatility — a well-known proxy in quant finance.
"""
from __future__ import annotations

import math
from typing import List, Optional

import pandas as pd

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


def realized_vol_from_candles(df: pd.DataFrame, window: int = 20) -> Optional[float]:
    """Estimate annualized volatility from daily OHLCV candles (close-to-close).

    Returns annualized vol as a decimal (e.g. 0.18 = 18%).
    Used as IV proxy when live options chain is unavailable.
    """
    if df is None or len(df) < window + 1:
        return None
    try:
        closes = df["close"].astype(float).dropna()
        log_returns = closes.pct_change().dropna()
        if len(log_returns) < window:
            return None
        vol_daily = log_returns.rolling(window).std().iloc[-1]
        return float(vol_daily * math.sqrt(252))   # annualize
    except Exception:
        return None


def realized_vol_rank(df: pd.DataFrame) -> Optional[float]:
    """Compute IV rank proxy from realized vol history in candle data.

    Uses rolling 20-day vol as 'IV now' and the 1-year range of rolling
    vol as the historical range — mirrors the IV rank formula exactly.
    Returns 0-100 rank, or None if insufficient data.
    """
    if df is None or len(df) < 60:
        return None
    try:
        closes = df["close"].astype(float).dropna()
        log_ret = closes.pct_change().dropna()
        rolling_vol = log_ret.rolling(20).std() * math.sqrt(252)
        rolling_vol = rolling_vol.dropna()
        if len(rolling_vol) < 30:
            return None
        vol_now = float(rolling_vol.iloc[-1])
        vol_history = rolling_vol.iloc[-252:].tolist()
        return iv_rank(vol_now, vol_history)
    except Exception:
        return None


def compute_iv_metrics(instrument: str, iv_now: float,
                       rv_rank_override: Optional[float] = None) -> dict:
    """Pulls 1Y IV history from DB and returns both metrics + a state label.

    When DB history is empty (e.g. first run / trial account), falls back to
    rv_rank_override if provided (computed from realized vol in candle data).
    """
    history = IVHistoryRepo.last_252(instrument)
    if len(history) >= 30:        # need enough history to form a meaningful range
        r = iv_rank(iv_now, history)
        p = iv_percentile(iv_now, history)
    elif rv_rank_override is not None:
        # Use realized vol rank as proxy — computed from daily candles
        r = rv_rank_override
        p = rv_rank_override      # approximate
    else:
        r, p = 50.0, 50.0        # neutral default
    state = ("CHEAP OPTIONS" if r < 30 else
             "FAIR VALUE" if r < 55 else
             "EXPENSIVE OPTIONS" if r < 75 else "EXTREME PREMIUM")
    return {"iv_rank": r, "iv_percentile": p, "iv_state": state,
            "history_days": len(history)}
