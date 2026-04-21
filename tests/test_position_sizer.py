"""Position sizing — spec §8.4."""
from __future__ import annotations

from app.risk.position_sizer import options_position_size, position_size


def test_basic_equity_sizing() -> None:
    units, lots, risk_rs = position_size(
        capital=500_000, risk_pct=1.0, entry_price=2000, stop_loss=1980, lot_size=1
    )
    # risk = 5000, sl_dist = 20 → 250 units
    assert units == 250
    assert risk_rs == 5000


def test_zero_sl_distance_safe() -> None:
    units, lots, risk_rs = position_size(500_000, 1.0, 2000, 2000, 1)
    assert units == 0
    assert lots == 0


def test_options_sizing_with_lots() -> None:
    units, lots, _ = options_position_size(
        capital=500_000, risk_pct=1.0, entry_premium=100, sl_premium=70, lot_size=25
    )
    # risk = 5000, premium_risk=30 → 166 units → 6 lots
    assert units == 166
    assert lots == 6
