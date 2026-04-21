"""Position sizing (spec §8.4).

Equity/Futures: size = (Capital × Risk%) / StopLossDistance (points)
Options:        size = (Capital × Risk%) / PremiumRisk (Rs per unit)
"""
from __future__ import annotations

from typing import Tuple


def position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    lot_size: int = 1,
) -> Tuple[int, int, float]:
    """Return (units, lots, risk_rupees) for equity/futures."""
    risk_rupees = capital * (risk_pct / 100.0)
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return 0, 0, risk_rupees
    units = int(risk_rupees // sl_distance)
    lots = max(1, units // lot_size) if units >= lot_size else 0
    return units, lots, risk_rupees


def options_position_size(
    capital: float,
    risk_pct: float,
    entry_premium: float,
    sl_premium: float,
    lot_size: int,
) -> Tuple[int, int, float]:
    """For options we risk premium × quantity. Return (units, lots, risk_rupees)."""
    risk_rupees = capital * (risk_pct / 100.0)
    premium_risk = abs(entry_premium - sl_premium)
    if premium_risk <= 0:
        return 0, 0, risk_rupees
    units = int(risk_rupees // premium_risk)
    lots = max(0, units // lot_size)
    return units, lots, risk_rupees
