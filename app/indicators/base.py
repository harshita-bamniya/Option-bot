"""Shared base types and utilities for the 6 indicator groups.

Spec §5.1: each group emits a score in [-1.0, +1.0]; the Scoring Engine combines
them into the IIS (spec §5.2). Raw indicator values never leave this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np
import pandas as pd


@dataclass
class GroupResult:
    """Output of a single indicator group."""
    group: str
    score: float                          # [-1.0, +1.0]
    state: str                            # group-specific label, e.g. 'Bullish', 'NORMAL'
    confidence: float = 1.0               # [0, 1] — reduces influence when uncertain
    details: Dict[str, Any] = field(default_factory=dict)

    def clamp(self) -> "GroupResult":
        self.score = float(np.clip(self.score, -1.0, 1.0))
        self.confidence = float(np.clip(self.confidence, 0.0, 1.0))
        return self


# ----------------- helpers -----------------

def vote(cond_bull: bool, cond_bear: bool) -> int:
    """+1 bullish, -1 bearish, 0 neutral. Mutually exclusive inputs."""
    if cond_bull and not cond_bear:
        return 1
    if cond_bear and not cond_bull:
        return -1
    return 0


def safe_last(series: pd.Series, default: float = float("nan")) -> float:
    if series is None or len(series) == 0:
        return default
    val = series.iloc[-1]
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def pct_rank(series: pd.Series, value: float) -> float:
    """Percentile rank of `value` within `series` (0-100)."""
    if series is None or len(series) == 0 or np.isnan(value):
        return 50.0
    s = series.dropna()
    if len(s) == 0:
        return 50.0
    return float((s < value).sum() / len(s) * 100)


# ----------------- aggregator -----------------

class IndicatorEngine:
    """Runs all 6 groups on a candle DataFrame and returns GroupResults.

    Input DataFrame MUST have columns: open, high, low, close, volume
    indexed by timestamp (ascending). Minimum 200 rows recommended for daily TF.
    """

    @staticmethod
    def run(df: pd.DataFrame) -> Dict[str, GroupResult]:
        # Lazy imports to avoid cycles
        from .trend import compute_trend_group
        from .momentum import compute_momentum_group
        from .volatility import compute_volatility_group
        from .volume import compute_volume_group
        from .structure import compute_structure_group
        from .hybrid import compute_hybrid_group

        if df is None or len(df) < 30:
            empty = GroupResult(group="insufficient_data", score=0.0, state="UNKNOWN", confidence=0.0)
            return {g: GroupResult(group=g, score=0.0, state="UNKNOWN", confidence=0.0)
                    for g in ("trend", "momentum", "volume", "volatility", "structure", "hybrid")}

        return {
            "trend":      compute_trend_group(df).clamp(),
            "momentum":   compute_momentum_group(df).clamp(),
            "volume":     compute_volume_group(df).clamp(),
            "volatility": compute_volatility_group(df).clamp(),
            "structure":  compute_structure_group(df).clamp(),
            "hybrid":     compute_hybrid_group(df).clamp(),
        }
