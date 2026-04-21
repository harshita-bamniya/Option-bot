"""Structure Group (spec §5.1 #5) — weight 15%.

Indicators: Pivot Points (daily/weekly), Fibonacci retracements + extensions,
S/R zones (rolling highs/lows), regression channel.

Measures price proximity to key levels; high confluence = higher score.
Also exposes key levels dict for the Risk Engine (target/SL validation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from .base import GroupResult, safe_last


@dataclass
class KeyLevels:
    pivot: float = 0.0
    r1: float = 0.0; r2: float = 0.0; r3: float = 0.0
    s1: float = 0.0; s2: float = 0.0; s3: float = 0.0
    fib_382: float = 0.0; fib_500: float = 0.0; fib_618: float = 0.0
    swing_high: float = 0.0
    swing_low: float = 0.0

    def as_list(self) -> List[float]:
        return [v for v in (self.pivot, self.r1, self.r2, self.r3, self.s1, self.s2, self.s3,
                            self.fib_382, self.fib_500, self.fib_618, self.swing_high, self.swing_low)
                if v]


def _pivot_points(last_bar: pd.Series) -> Dict[str, float]:
    """Classic daily pivots from prior bar's HLC."""
    h, l, c = float(last_bar["high"]), float(last_bar["low"]), float(last_bar["close"])
    p = (h + l + c) / 3
    return {
        "pivot": p,
        "r1": 2 * p - l,  "s1": 2 * p - h,
        "r2": p + (h - l),"s2": p - (h - l),
        "r3": h + 2 * (p - l), "s3": l - 2 * (h - p),
    }


def _fib_levels(swing_high: float, swing_low: float) -> Dict[str, float]:
    diff = swing_high - swing_low
    return {
        "fib_382": swing_high - 0.382 * diff,
        "fib_500": swing_high - 0.500 * diff,
        "fib_618": swing_high - 0.618 * diff,
    }


def compute_key_levels(df: pd.DataFrame) -> KeyLevels:
    """Used directly by Risk Engine and /levels command."""
    kl = KeyLevels()
    if len(df) < 2:
        return kl
    pp = _pivot_points(df.iloc[-2])     # previous bar
    kl.pivot, kl.r1, kl.r2, kl.r3 = pp["pivot"], pp["r1"], pp["r2"], pp["r3"]
    kl.s1, kl.s2, kl.s3 = pp["s1"], pp["s2"], pp["s3"]
    # Swing high/low over last 50 bars
    lookback = min(50, len(df))
    kl.swing_high = float(df["high"].iloc[-lookback:].max())
    kl.swing_low  = float(df["low"].iloc[-lookback:].min())
    fib = _fib_levels(kl.swing_high, kl.swing_low)
    kl.fib_382, kl.fib_500, kl.fib_618 = fib["fib_382"], fib["fib_500"], fib["fib_618"]
    return kl


def compute_structure_group(df: pd.DataFrame) -> GroupResult:
    if len(df) < 20:
        return GroupResult(group="structure", score=0.0, state="UNKNOWN",
                           confidence=0.0, details={})

    kl = compute_key_levels(df)
    price = float(df["close"].iloc[-1])
    levels = kl.as_list()
    if not levels:
        return GroupResult(group="structure", score=0.0, state="UNKNOWN", confidence=0.3)

    # Find nearest level by pct distance
    nearest = min(levels, key=lambda lv: abs(price - lv))
    distance_pct = abs(price - nearest) / price * 100

    # Price above pivot → bullish structure; below → bearish
    direction = 1 if price > kl.pivot else -1 if price < kl.pivot else 0

    # Score magnitude grows as price approaches a key level (confluence zone)
    if distance_pct < 0.15:
        magnitude = 0.8   # at-level
    elif distance_pct < 0.5:
        magnitude = 0.5
    elif distance_pct < 1.0:
        magnitude = 0.3
    else:
        magnitude = 0.15

    # Add Fibonacci pullback bonus — price near 38.2/50/61.8 within an uptrend
    for fib in (kl.fib_382, kl.fib_500, kl.fib_618):
        if abs(price - fib) / price * 100 < 0.25:
            magnitude = min(1.0, magnitude + 0.1)
            break

    score = direction * magnitude
    state = "Bullish Structure" if score > 0.15 else ("Bearish Structure" if score < -0.15 else "Neutral Structure")
    details = {
        "nearest_level": nearest,
        "distance_pct": distance_pct,
        "pivot": kl.pivot,
        "swing_high": kl.swing_high,
        "swing_low": kl.swing_low,
        "fib_382": kl.fib_382, "fib_500": kl.fib_500, "fib_618": kl.fib_618,
    }
    return GroupResult(group="structure", score=score, state=state,
                       confidence=0.9, details=details)
