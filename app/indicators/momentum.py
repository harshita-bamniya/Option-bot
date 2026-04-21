"""Momentum Group (spec §5.1 #2) — weight 20%.

Indicators: RSI(14), MACD(12,26,9), Stochastic, StochRSI, CCI(20), ROC,
Williams %R, TRIX, TSI, CMO, DPO, Momentum Oscillator.

Special logic: divergence detection (RSI/price), extreme-reading penalty.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from .base import GroupResult, safe_last, vote


def _detect_divergence(price: pd.Series, osc: pd.Series, lookback: int = 20) -> int:
    """Return +1 bullish div, -1 bearish div, 0 none. Simple pivot-based check."""
    if len(price) < lookback + 2 or len(osc) < lookback + 2:
        return 0
    p = price.iloc[-lookback:].values
    o = osc.iloc[-lookback:].values
    # Higher high in price, lower high in osc → bearish
    p_max_idx = int(np.argmax(p))
    if p_max_idx > 2 and p[-1] > p[p_max_idx] * 0.98:
        # Compare osc at last peak vs prior peak
        if o[-1] < o[p_max_idx]:
            return -1
    # Lower low in price, higher low in osc → bullish
    p_min_idx = int(np.argmin(p))
    if p_min_idx > 2 and p[-1] < p[p_min_idx] * 1.02:
        if o[-1] > o[p_min_idx]:
            return 1
    return 0


def compute_momentum_group(df: pd.DataFrame) -> GroupResult:
    close = df["close"]
    high, low = df["high"], df["low"]
    votes: list[int] = []
    details: dict = {}
    penalty = 0.0

    # --- RSI(14) ---
    try:
        rsi = ta.rsi(close, length=14)
        r = safe_last(rsi)
        details["rsi_14"] = r
        # Bullish bias above 50, bearish below 50
        votes.append(vote(r > 55, r < 45))
        if r >= 75 or r <= 25:
            penalty += 0.15  # extreme reading — reduces conviction
        # Divergence
        div = _detect_divergence(close, rsi)
        if div != 0:
            votes.append(div)
            details["rsi_divergence"] = div
    except Exception:
        pass

    # --- MACD ---
    try:
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            m_col = [c for c in macd.columns if c.startswith("MACD_")][0]
            s_col = [c for c in macd.columns if c.startswith("MACDs_")][0]
            h_col = [c for c in macd.columns if c.startswith("MACDh_")][0]
            votes.append(vote(macd[m_col].iloc[-1] > macd[s_col].iloc[-1],
                              macd[m_col].iloc[-1] < macd[s_col].iloc[-1]))
            # Histogram direction
            h_now, h_prev = macd[h_col].iloc[-1], macd[h_col].iloc[-2]
            votes.append(vote(h_now > 0 and h_now > h_prev,
                              h_now < 0 and h_now < h_prev))
            details["macd_hist"] = float(h_now)
    except Exception:
        pass

    # --- Stochastic ---
    try:
        stoch = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            k_col = [c for c in stoch.columns if c.startswith("STOCHk_")][0]
            d_col = [c for c in stoch.columns if c.startswith("STOCHd_")][0]
            k, d = safe_last(stoch[k_col]), safe_last(stoch[d_col])
            votes.append(vote(k > d and k < 80, k < d and k > 20))
            if k > 85 or k < 15:
                penalty += 0.10
    except Exception:
        pass

    # --- Stochastic RSI ---
    try:
        srsi = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
        if srsi is not None and not srsi.empty:
            k_col = [c for c in srsi.columns if "k" in c.lower()][0]
            v = safe_last(srsi[k_col])
            votes.append(vote(v > 50, v < 50))
    except Exception:
        pass

    # --- CCI(20) ---
    try:
        cci = ta.cci(high, low, close, length=20)
        v = safe_last(cci)
        votes.append(vote(v > 100, v < -100))
    except Exception:
        pass

    # --- ROC, Williams %R, TRIX, TSI, CMO, DPO, MOM ---
    try:
        votes.append(vote(safe_last(ta.roc(close, length=10)) > 0,
                          safe_last(ta.roc(close, length=10)) < 0))
    except Exception: pass
    try:
        willr = safe_last(ta.willr(high, low, close, length=14))
        votes.append(vote(willr > -20, willr < -80))
    except Exception: pass
    try:
        trix = ta.trix(close, length=18)
        if trix is not None and not trix.empty:
            col = trix.columns[0]
            votes.append(vote(safe_last(trix[col]) > 0, safe_last(trix[col]) < 0))
    except Exception: pass
    try:
        tsi = ta.tsi(close)
        if tsi is not None and not tsi.empty:
            votes.append(vote(safe_last(tsi.iloc[:, 0]) > 0, safe_last(tsi.iloc[:, 0]) < 0))
    except Exception: pass
    try:
        cmo = safe_last(ta.cmo(close, length=14))
        votes.append(vote(cmo > 25, cmo < -25))
    except Exception: pass
    try:
        dpo = safe_last(ta.dpo(close, length=20))
        votes.append(vote(dpo > 0, dpo < 0))
    except Exception: pass
    try:
        mom = safe_last(ta.mom(close, length=10))
        votes.append(vote(mom > 0, mom < 0))
    except Exception: pass

    if not votes:
        return GroupResult(group="momentum", score=0.0, state="UNKNOWN", confidence=0.0, details=details)

    raw = sum(votes) / len(votes)
    raw -= np.sign(raw) * penalty    # extreme readings reduce magnitude
    state = "Bullish" if raw > 0.15 else ("Bearish" if raw < -0.15 else "Neutral")
    confidence = max(0.2, 1.0 - penalty)
    return GroupResult(group="momentum", score=raw, state=state,
                       confidence=confidence, details=details)
