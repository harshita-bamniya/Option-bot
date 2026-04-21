"""Volume Group (spec §5.1 #4) — weight 20%.

Indicators: Volume, RVOL (20-day), OBV, A/D Line, CMF(20), MFI(14), VWAP,
VWAP Bands, Volume Oscillator.

Core rule: price move without volume is low-confidence. OBV divergence is an
early reversal warning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from .base import GroupResult, safe_last, vote


def compute_volume_group(df: pd.DataFrame) -> GroupResult:
    close = df["close"]
    high, low = df["high"], df["low"]
    volume = df.get("volume")
    if volume is None or volume.sum() == 0:
        return GroupResult(group="volume", score=0.0, state="UNKNOWN", confidence=0.2,
                           details={"reason": "no_volume"})

    details: dict = {}
    votes: list[int] = []

    # --- RVOL (current vs 20-day avg) ---
    try:
        vol_ma = volume.rolling(20).mean()
        rvol = float(volume.iloc[-1] / vol_ma.iloc[-1]) if vol_ma.iloc[-1] > 0 else 1.0
        details["rvol"] = rvol
        # Price direction
        candle_bull = close.iloc[-1] > close.iloc[-2]
        if rvol > 1.5:
            votes.append(1 if candle_bull else -1)
            votes.append(1 if candle_bull else -1)  # double-weight volume confirmation
        elif rvol < 0.7:
            # Low volume — reduce conviction (neutral vote)
            votes.append(0)
    except Exception:
        rvol = 1.0

    # --- OBV ---
    try:
        obv = ta.obv(close, volume)
        obv_slope = obv.diff(10).iloc[-1]
        details["obv_slope_10"] = float(obv_slope)
        votes.append(vote(obv_slope > 0, obv_slope < 0))
        # OBV divergence: price up, obv down (or vice-versa)
        price_delta = close.iloc[-1] - close.iloc[-10]
        obv_delta = obv.iloc[-1] - obv.iloc[-10]
        if price_delta > 0 and obv_delta < 0:
            votes.append(-1)
            details["obv_divergence"] = "bearish"
        elif price_delta < 0 and obv_delta > 0:
            votes.append(1)
            details["obv_divergence"] = "bullish"
    except Exception:
        pass

    # --- CMF(20) ---
    try:
        cmf = ta.cmf(high, low, close, volume, length=20)
        v = safe_last(cmf)
        details["cmf"] = v
        votes.append(vote(v > 0.05, v < -0.05))
    except Exception:
        pass

    # --- MFI(14) ---
    try:
        mfi = safe_last(ta.mfi(high, low, close, volume, length=14))
        details["mfi"] = mfi
        votes.append(vote(mfi > 60, mfi < 40))
    except Exception:
        pass

    # --- VWAP ---
    try:
        vwap = ta.vwap(high, low, close, volume)
        if vwap is not None:
            v = safe_last(vwap)
            details["vwap"] = v
            votes.append(vote(close.iloc[-1] > v, close.iloc[-1] < v))
    except Exception:
        pass

    # --- A/D line ---
    try:
        ad = ta.ad(high, low, close, volume)
        slope = ad.diff(5).iloc[-1]
        votes.append(vote(slope > 0, slope < 0))
    except Exception:
        pass

    if not votes:
        return GroupResult(group="volume", score=0.0, state="UNKNOWN", confidence=0.3, details=details)

    raw = sum(votes) / len(votes)
    state = "Bullish" if raw > 0.15 else ("Bearish" if raw < -0.15 else "Neutral")
    # Confidence anchored to rvol — big volume = high confidence
    confidence = min(1.0, 0.5 + min(rvol, 3.0) / 6.0)
    return GroupResult(group="volume", score=raw, state=state,
                       confidence=confidence, details=details)
