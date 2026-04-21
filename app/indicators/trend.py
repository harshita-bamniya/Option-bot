"""Trend Group (spec §5.1 #1) — weight 25%.

Indicators: EMA 8/21/50/200, SMA 20/50/200, HMA, VWMA, Supertrend (10,3),
ADX(14), Aroon(25), Parabolic SAR, DMI, KAMA, TEMA.

Logic: each votes +1/-1/0; weighted avg → score in [-1,1]. ADX>25 boosts confidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from .base import GroupResult, safe_last, vote


def compute_trend_group(df: pd.DataFrame) -> GroupResult:
    close = df["close"]
    high, low = df["high"], df["low"]
    volume = df["volume"] if "volume" in df.columns else pd.Series(1, index=df.index)

    votes: list[int] = []
    details: dict = {}

    # --- EMAs (multi-timeframe proxies on same series) ---
    for span in (8, 21, 50, 200):
        if len(close) < span:
            continue
        ema = ta.ema(close, length=span)
        v = vote(close.iloc[-1] > ema.iloc[-1], close.iloc[-1] < ema.iloc[-1])
        votes.append(v)
        details[f"ema_{span}"] = safe_last(ema)

    # EMA stacking — bullish if 8>21>50>200
    try:
        e8, e21, e50, e200 = [safe_last(ta.ema(close, length=n)) for n in (8, 21, 50, 200)]
        if e8 > e21 > e50 > e200:
            votes.append(1); votes.append(1)       # double count — strong alignment
        elif e8 < e21 < e50 < e200:
            votes.append(-1); votes.append(-1)
    except Exception:
        pass

    # --- SMAs ---
    for span in (20, 50, 200):
        if len(close) < span:
            continue
        sma = ta.sma(close, length=span)
        votes.append(vote(close.iloc[-1] > sma.iloc[-1], close.iloc[-1] < sma.iloc[-1]))

    # --- Supertrend(10,3) ---
    try:
        st = ta.supertrend(high, low, close, length=10, multiplier=3.0)
        if st is not None and not st.empty:
            direction_col = [c for c in st.columns if c.startswith("SUPERTd_")][0]
            dir_val = int(st[direction_col].iloc[-1])
            votes.append(1 if dir_val == 1 else -1 if dir_val == -1 else 0)
            details["supertrend_dir"] = dir_val
    except Exception:
        pass

    # --- ADX / DMI ---
    adx_val = np.nan
    try:
        adx_df = ta.adx(high, low, close, length=14)
        if adx_df is not None and not adx_df.empty:
            adx_val = safe_last(adx_df["ADX_14"])
            plus_di = safe_last(adx_df["DMP_14"])
            minus_di = safe_last(adx_df["DMN_14"])
            votes.append(vote(plus_di > minus_di, minus_di > plus_di))
            details["adx"] = adx_val
    except Exception:
        pass

    # --- Aroon(25) ---
    try:
        aroon = ta.aroon(high, low, length=25)
        if aroon is not None and not aroon.empty:
            up_col = [c for c in aroon.columns if c.startswith("AROONU_")][0]
            dn_col = [c for c in aroon.columns if c.startswith("AROOND_")][0]
            au, ad = safe_last(aroon[up_col]), safe_last(aroon[dn_col])
            votes.append(vote(au > 70 and ad < 30, ad > 70 and au < 30))
    except Exception:
        pass

    # --- Parabolic SAR ---
    try:
        psar = ta.psar(high, low, close)
        if psar is not None and not psar.empty:
            long_col = next((c for c in psar.columns if c.startswith("PSARl_")), None)
            short_col = next((c for c in psar.columns if c.startswith("PSARs_")), None)
            votes.append(vote(long_col and not np.isnan(psar[long_col].iloc[-1]),
                              short_col and not np.isnan(psar[short_col].iloc[-1])))
    except Exception:
        pass

    # --- HMA(21), VWMA(20), KAMA(10), TEMA(21) ---
    for fn, args in (("hma", {"length": 21}),
                     ("kama", {"length": 10}),
                     ("tema", {"length": 21})):
        try:
            v = getattr(ta, fn)(close, **args)
            if v is not None:
                votes.append(vote(close.iloc[-1] > v.iloc[-1], close.iloc[-1] < v.iloc[-1]))
        except Exception:
            pass
    try:
        vwma = ta.vwma(close, volume, length=20)
        if vwma is not None:
            votes.append(vote(close.iloc[-1] > vwma.iloc[-1], close.iloc[-1] < vwma.iloc[-1]))
    except Exception:
        pass

    if not votes:
        return GroupResult(group="trend", score=0.0, state="UNKNOWN", confidence=0.0, details=details)

    raw = sum(votes) / len(votes)
    confidence = 1.0
    # ADX > 25 boosts confidence; ADX < 15 reduces
    if not np.isnan(adx_val):
        if adx_val >= 25:
            confidence = 1.0
            raw *= 1.05   # light boost — re-clipped in GroupResult.clamp
        elif adx_val < 15:
            confidence = 0.6

    state = "Bullish" if raw > 0.15 else ("Bearish" if raw < -0.15 else "Neutral")
    return GroupResult(group="trend", score=raw, state=state,
                       confidence=confidence, details=details)
