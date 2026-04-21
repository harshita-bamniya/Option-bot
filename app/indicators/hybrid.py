"""Hybrid Group (spec §5.1 #6) — weight 5%.

Supporting confluence layer: Ichimoku, Supertrend, Vortex, Coppock, Fisher.
Used as a tiebreaker when the core groups are split.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from .base import GroupResult, safe_last, vote


def compute_hybrid_group(df: pd.DataFrame) -> GroupResult:
    close = df["close"]
    high, low = df["high"], df["low"]
    votes: list[int] = []
    details: dict = {}

    # --- Ichimoku (9/26/52) ---
    try:
        ichi, span = ta.ichimoku(high, low, close, tenkan=9, kijun=26, senkou=52)
        # ichi has columns: ISA_9, ISB_26, ITS_9, IKS_26, ICS_26
        if ichi is not None and not ichi.empty:
            # Price vs cloud (ISA / ISB)
            isa = safe_last(ichi["ISA_9"])
            isb = safe_last(ichi["ISB_26"])
            above = close.iloc[-1] > max(isa, isb) if not (np.isnan(isa) or np.isnan(isb)) else False
            below = close.iloc[-1] < min(isa, isb) if not (np.isnan(isa) or np.isnan(isb)) else False
            votes.append(vote(above, below))
            # Tenkan vs Kijun
            t = safe_last(ichi["ITS_9"]); k = safe_last(ichi["IKS_26"])
            votes.append(vote(t > k, t < k))
            details["ichimoku_cloud_above"] = above
    except Exception:
        pass

    # --- Supertrend (already used in trend group — small double-count as confluence) ---
    try:
        st = ta.supertrend(high, low, close, length=7, multiplier=3.0)
        if st is not None and not st.empty:
            dir_col = [c for c in st.columns if c.startswith("SUPERTd_")][0]
            d = int(st[dir_col].iloc[-1])
            votes.append(1 if d == 1 else -1 if d == -1 else 0)
    except Exception:
        pass

    # --- Vortex Indicator ---
    try:
        vortex = ta.vortex(high, low, close, length=14)
        if vortex is not None and not vortex.empty:
            vip = next(c for c in vortex.columns if c.startswith("VTXP_"))
            vim = next(c for c in vortex.columns if c.startswith("VTXM_"))
            votes.append(vote(safe_last(vortex[vip]) > safe_last(vortex[vim]),
                              safe_last(vortex[vip]) < safe_last(vortex[vim])))
    except Exception:
        pass

    # --- Coppock Curve (monthly indicator; still directionally useful on daily) ---
    try:
        copp = ta.coppock(close)
        if copp is not None:
            v = safe_last(copp)
            votes.append(vote(v > 0, v < 0))
    except Exception:
        pass

    # --- Fisher Transform ---
    try:
        fisher = ta.fisher(high, low, length=9)
        if fisher is not None and not fisher.empty:
            col = fisher.columns[0]
            s = safe_last(fisher[col])
            votes.append(vote(s > 0, s < 0))
    except Exception:
        pass

    if not votes:
        return GroupResult(group="hybrid", score=0.0, state="UNKNOWN", confidence=0.0, details=details)

    raw = sum(votes) / len(votes)
    state = "Bullish" if raw > 0.2 else ("Bearish" if raw < -0.2 else "Neutral")
    # High agreement boosts confidence (per spec)
    agree_ratio = abs(raw)
    confidence = 0.5 + 0.5 * agree_ratio
    return GroupResult(group="hybrid", score=raw, state=state,
                       confidence=confidence, details=details)
