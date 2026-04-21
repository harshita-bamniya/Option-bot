"""Volatility Group (spec §5.1 #3) — weight 15%.

Indicators: Bollinger(20,2), ATR(14), Keltner, Donchian, StdDev, Chaikin Vol.
Output state: LOW / NORMAL / HIGH / EXTREME. BB Squeeze flags imminent breakout.
ATR also used directly by Risk layer for SL sizing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from .base import GroupResult, safe_last, pct_rank


def compute_volatility_group(df: pd.DataFrame) -> GroupResult:
    close = df["close"]
    high, low = df["high"], df["low"]
    details: dict = {}

    atr = ta.atr(high, low, close, length=14)
    atr_now = safe_last(atr)
    atr_pct = pct_rank(atr, atr_now) if atr is not None else 50.0
    details["atr"] = atr_now
    details["atr_percentile"] = atr_pct

    # Classify state
    if atr_pct >= 95:
        state = "EXTREME"
    elif atr_pct >= 75:
        state = "HIGH"
    elif atr_pct <= 20:
        state = "LOW"
    else:
        state = "NORMAL"
    details["state"] = state

    # --- Bollinger Bands (20,2) ---
    bb_score = 0.0
    try:
        bb = ta.bbands(close, length=20, std=2.0)
        if bb is not None and not bb.empty:
            upper = next(c for c in bb.columns if c.startswith("BBU_"))
            lower = next(c for c in bb.columns if c.startswith("BBL_"))
            mid   = next(c for c in bb.columns if c.startswith("BBM_"))
            u, l, m = safe_last(bb[upper]), safe_last(bb[lower]), safe_last(bb[mid])
            c = close.iloc[-1]
            bw = (u - l) / m if m else 0
            details["bb_width"] = bw
            # Position within bands
            if u != l:
                pct_b = (c - l) / (u - l)
                details["percent_b"] = pct_b
                # Near upper band in uptrend is bullish momentum; near lower is bearish
                if pct_b > 0.8: bb_score += 0.3
                elif pct_b < 0.2: bb_score -= 0.3
    except Exception:
        pass

    # --- Keltner Channels for BB Squeeze detection ---
    squeeze = False
    try:
        kc = ta.kc(high, low, close, length=20, scalar=1.5)
        bb = ta.bbands(close, length=20, std=2.0)
        if bb is not None and kc is not None:
            bbu = safe_last(bb[next(c for c in bb.columns if c.startswith("BBU_"))])
            bbl = safe_last(bb[next(c for c in bb.columns if c.startswith("BBL_"))])
            kcu = safe_last(kc[next(c for c in kc.columns if c.startswith("KCU"))])
            kcl = safe_last(kc[next(c for c in kc.columns if c.startswith("KCL"))])
            squeeze = (bbu < kcu) and (bbl > kcl)
            details["squeeze"] = squeeze
    except Exception:
        pass

    # --- Donchian(20) ---
    try:
        don = ta.donchian(high, low, lower_length=20, upper_length=20)
        if don is not None and not don.empty:
            up_col = next(c for c in don.columns if c.startswith("DCU_"))
            dn_col = next(c for c in don.columns if c.startswith("DCL_"))
            details["donchian_high"] = safe_last(don[up_col])
            details["donchian_low"]  = safe_last(don[dn_col])
    except Exception:
        pass

    # Volatility group score is small-magnitude — it modulates, not directs.
    # Direction pull comes from BB %b; squeeze reduces confidence slightly.
    score = np.clip(bb_score, -0.5, 0.5)
    confidence = 0.9 if not squeeze else 0.7
    return GroupResult(group="volatility", score=float(score), state=state,
                       confidence=confidence, details=details)
