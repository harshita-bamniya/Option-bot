"""Candlestick + chart pattern detection.

Candlestick: pandas-ta wraps TA-Lib's 60+ patterns when TA-Lib is installed;
we implement the most reliable few in pure pandas so the system works without
TA-Lib compiled natively (Windows-friendly).

Output: list of PatternHit → feeds the Pattern Score input of FCS (spec §8.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd


@dataclass
class PatternHit:
    name: str
    direction: int           # +1 bullish, -1 bearish
    confidence: str          # HIGH | MEDIUM | LOW
    bar_index: int           # relative offset (-1 = last bar)

    def score(self) -> float:
        mag = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}[self.confidence]
        return self.direction * mag


# --- single-bar patterns ---

def _body(o, c): return abs(c - o)
def _range(h, l): return h - l
def _upper_wick(o, h, c): return h - max(o, c)
def _lower_wick(o, l, c): return min(o, c) - l


def _doji(df: pd.DataFrame, i: int) -> PatternHit | None:
    o, h, l, c = df.iloc[i][["open","high","low","close"]]
    rng = _range(h, l)
    if rng == 0: return None
    if _body(o, c) / rng < 0.1:
        return PatternHit("Doji", direction=0, confidence="LOW", bar_index=i)
    return None


def _hammer(df: pd.DataFrame, i: int) -> PatternHit | None:
    o, h, l, c = df.iloc[i][["open","high","low","close"]]
    body = _body(o, c); rng = _range(h, l)
    if rng == 0: return None
    lower = _lower_wick(o, l, c); upper = _upper_wick(o, h, c)
    if body / rng < 0.35 and lower >= 2 * body and upper <= 0.3 * body:
        # Requires preceding downtrend
        if i >= 5 and df["close"].iloc[i-5:i].mean() > c:
            return PatternHit("Hammer", direction=1, confidence="HIGH", bar_index=i)
    return None


def _shooting_star(df: pd.DataFrame, i: int) -> PatternHit | None:
    o, h, l, c = df.iloc[i][["open","high","low","close"]]
    body = _body(o, c); rng = _range(h, l)
    if rng == 0: return None
    upper = _upper_wick(o, h, c); lower = _lower_wick(o, l, c)
    if body / rng < 0.35 and upper >= 2 * body and lower <= 0.3 * body:
        if i >= 5 and df["close"].iloc[i-5:i].mean() < c:
            return PatternHit("Shooting Star", direction=-1, confidence="HIGH", bar_index=i)
    return None


# --- two-bar patterns ---

def _bullish_engulfing(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 1: return None
    p_o, p_c = df["open"].iloc[i-1], df["close"].iloc[i-1]
    o, c = df["open"].iloc[i], df["close"].iloc[i]
    if p_c < p_o and c > o and o <= p_c and c >= p_o:
        return PatternHit("Bullish Engulfing", direction=1, confidence="HIGH", bar_index=i)
    return None


def _bearish_engulfing(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 1: return None
    p_o, p_c = df["open"].iloc[i-1], df["close"].iloc[i-1]
    o, c = df["open"].iloc[i], df["close"].iloc[i]
    if p_c > p_o and c < o and o >= p_c and c <= p_o:
        return PatternHit("Bearish Engulfing", direction=-1, confidence="HIGH", bar_index=i)
    return None


# --- three-bar patterns ---

def _morning_star(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 2: return None
    a, b, c = df.iloc[i-2], df.iloc[i-1], df.iloc[i]
    a_bear = a["close"] < a["open"] and (a["open"] - a["close"]) / max(a["high"] - a["low"], 1e-9) > 0.4
    b_small = _body(b["open"], b["close"]) / max(_range(b["high"], b["low"]), 1e-9) < 0.4
    c_bull = c["close"] > c["open"] and c["close"] > (a["open"] + a["close"]) / 2
    if a_bear and b_small and c_bull:
        return PatternHit("Morning Star", direction=1, confidence="HIGH", bar_index=i)
    return None


def _evening_star(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 2: return None
    a, b, c = df.iloc[i-2], df.iloc[i-1], df.iloc[i]
    a_bull = a["close"] > a["open"] and (a["close"] - a["open"]) / max(a["high"] - a["low"], 1e-9) > 0.4
    b_small = _body(b["open"], b["close"]) / max(_range(b["high"], b["low"]), 1e-9) < 0.4
    c_bear = c["close"] < c["open"] and c["close"] < (a["open"] + a["close"]) / 2
    if a_bull and b_small and c_bear:
        return PatternHit("Evening Star", direction=-1, confidence="HIGH", bar_index=i)
    return None


def _three_white_soldiers(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 2: return None
    bars = df.iloc[i-2:i+1]
    bullish = all(bars["close"] > bars["open"])
    higher = bars["close"].iloc[0] < bars["close"].iloc[1] < bars["close"].iloc[2]
    if bullish and higher:
        return PatternHit("Three White Soldiers", direction=1, confidence="MEDIUM", bar_index=i)
    return None


def _three_black_crows(df: pd.DataFrame, i: int) -> PatternHit | None:
    if i < 2: return None
    bars = df.iloc[i-2:i+1]
    bearish = all(bars["close"] < bars["open"])
    lower = bars["close"].iloc[0] > bars["close"].iloc[1] > bars["close"].iloc[2]
    if bearish and lower:
        return PatternHit("Three Black Crows", direction=-1, confidence="MEDIUM", bar_index=i)
    return None


# --- chart patterns (very lightweight heuristics) ---

def _double_bottom(df: pd.DataFrame) -> PatternHit | None:
    if len(df) < 30: return None
    lows = df["low"].iloc[-30:]
    idx_min1 = int(lows.iloc[:15].idxmin().to_datetime64().astype("int64")) if False else lows.iloc[:15].argmin()
    idx_min2 = 15 + lows.iloc[15:].argmin()
    if abs(lows.iloc[idx_min1] - lows.iloc[idx_min2]) / max(lows.iloc[idx_min1], 1e-9) < 0.01:
        if df["close"].iloc[-1] > lows.iloc[idx_min1:idx_min2].max():
            return PatternHit("Double Bottom", direction=1, confidence="MEDIUM", bar_index=len(df)-1)
    return None


def _double_top(df: pd.DataFrame) -> PatternHit | None:
    if len(df) < 30: return None
    highs = df["high"].iloc[-30:]
    idx_max1 = highs.iloc[:15].argmax()
    idx_max2 = 15 + highs.iloc[15:].argmax()
    if abs(highs.iloc[idx_max1] - highs.iloc[idx_max2]) / max(highs.iloc[idx_max1], 1e-9) < 0.01:
        if df["close"].iloc[-1] < highs.iloc[idx_max1:idx_max2].min():
            return PatternHit("Double Top", direction=-1, confidence="MEDIUM", bar_index=len(df)-1)
    return None


_SINGLE = [_doji, _hammer, _shooting_star]
_TWO    = [_bullish_engulfing, _bearish_engulfing]
_THREE  = [_morning_star, _evening_star, _three_white_soldiers, _three_black_crows]


def detect_patterns(df: pd.DataFrame, lookback: int = 5) -> List[PatternHit]:
    """Scan the last `lookback` bars for candlestick patterns + full df for chart patterns."""
    if df is None or len(df) < 5:
        return []

    hits: List[PatternHit] = []
    last = len(df) - 1
    for i in range(max(0, last - lookback + 1), last + 1):
        for fn in _SINGLE + _TWO + _THREE:
            try:
                h = fn(df, i)
            except Exception:
                h = None
            if h is not None:
                hits.append(h)

    for fn in (_double_bottom, _double_top):
        try:
            h = fn(df)
        except Exception:
            h = None
        if h is not None:
            hits.append(h)

    return hits


def pattern_score(hits: List[PatternHit]) -> tuple[float, str, str]:
    """Aggregate pattern hits into (score [-100..100], name, confidence_label).

    The most recent HIGH-confidence hit dominates; older/weak hits decay.
    """
    if not hits:
        return 0.0, "NONE", "LOW"
    # Prefer last-bar HIGH-confidence hit
    last_bar = max(h.bar_index for h in hits)
    primary = next((h for h in hits if h.bar_index == last_bar and h.confidence == "HIGH"), None)
    if primary is None:
        primary = max(hits, key=lambda h: (h.bar_index, {"HIGH":3,"MEDIUM":2,"LOW":1}[h.confidence]))
    return primary.score() * 100, primary.name, primary.confidence
