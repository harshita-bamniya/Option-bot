"""Final Conviction Score — spec §8.1.

FCS = (IIS × 0.35) + (MTFS×100 × 0.25) + (Options × 0.20) + (Pattern × 0.10) + (News×100 × 0.10)

All inputs are normalized to [-100, +100] before weighting.
"""
from __future__ import annotations

from typing import NamedTuple

from app.config.constants import (
    FCS_WEIGHTS, FCS_HIGH_BUY, FCS_MOD_BUY, FCS_MOD_SELL, FCS_HIGH_SELL,
    Direction,
)


class FCSInputs(NamedTuple):
    iis: float                # -100..+100
    mtfs: float               # -1..+1   (raw MTFS)
    options_score: float      # -100..+100
    pattern_score: float      # -100..+100
    news_sentiment: float     # -1..+1


class FCSResult(NamedTuple):
    fcs: float
    direction: Direction
    confidence_pct: float
    breakdown: dict


def compute_fcs(inp: FCSInputs) -> FCSResult:
    mtfs_scaled = max(-100.0, min(100.0, inp.mtfs * 100))
    news_scaled = max(-100.0, min(100.0, inp.news_sentiment * 100))

    contributions = {
        "iis":     inp.iis * FCS_WEIGHTS["iis"],
        "mtfs":    mtfs_scaled * FCS_WEIGHTS["mtfs"],
        "options": inp.options_score * FCS_WEIGHTS["options"],
        "pattern": inp.pattern_score * FCS_WEIGHTS["pattern"],
        "news":    news_scaled * FCS_WEIGHTS["news"],
    }
    fcs = sum(contributions.values())
    fcs = max(-100.0, min(100.0, fcs))
    direction = fcs_to_direction(fcs)

    # Confidence maps |FCS| → 0-100% non-linearly (saturates past 60)
    conf = min(100.0, abs(fcs) * 1.5 if abs(fcs) < 60 else 70 + (abs(fcs) - 60) * 0.75)

    return FCSResult(
        fcs=fcs,
        direction=direction,
        confidence_pct=conf,
        breakdown={
            "contributions": contributions,
            "inputs": inp._asdict(),
        },
    )


def fcs_to_direction(fcs: float) -> Direction:
    if fcs >= FCS_HIGH_BUY:  return Direction.BUY      # HIGH conviction
    if fcs >= FCS_MOD_BUY:   return Direction.BUY      # MODERATE
    if fcs <= FCS_HIGH_SELL: return Direction.SELL
    if fcs <= FCS_MOD_SELL:  return Direction.SELL
    return Direction.NO_TRADE


def position_scale(fcs: float) -> float:
    """Returns 1.0 for full size, 0.5 for half, 0.0 for no-trade (spec §8.1)."""
    if abs(fcs) >= FCS_HIGH_BUY:
        return 1.0
    if abs(fcs) >= FCS_MOD_BUY:
        return 0.5
    return 0.0
