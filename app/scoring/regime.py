"""Market regime classifier (spec ENH-001).

Labels each session as TRENDING / RANGING / VOLATILE based on ADX + ATR%.
Different groups/weights perform better in different regimes — the Learning
Engine eventually adjusts per-regime weights.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

from app.config.constants import Regime


def detect_regime(df: pd.DataFrame) -> Regime:
    if df is None or len(df) < 30:
        return Regime.RANGING
    try:
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
        adx_val = float(adx_df["ADX_14"].iloc[-1])
    except Exception:
        adx_val = 15.0
    try:
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        atr_pct = float(atr.iloc[-1] / df["close"].iloc[-1] * 100)
    except Exception:
        atr_pct = 1.0

    if atr_pct > 2.5:
        return Regime.VOLATILE
    if adx_val >= 25:
        return Regime.TRENDING
    return Regime.RANGING
