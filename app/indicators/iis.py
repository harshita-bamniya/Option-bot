"""Indicator Intelligence Score (IIS) — spec §5.2.

IIS = Σ (group_score × group_weight × group_confidence) × 100 → [-100, +100]
"""
from __future__ import annotations

from typing import Dict

from app.config.constants import GROUP_WEIGHTS

from .base import GroupResult


def compute_iis(results: Dict[str, GroupResult]) -> float:
    """Combine group results into the IIS (scaled to -100..+100)."""
    total = 0.0
    weight_sum = 0.0
    for group, weight in GROUP_WEIGHTS.items():
        r = results.get(group)
        if r is None:
            continue
        effective = weight * r.confidence
        total += r.score * effective
        weight_sum += effective
    if weight_sum == 0:
        return 0.0
    # Normalize by effective weight and scale to ±100
    return (total / weight_sum) * 100
