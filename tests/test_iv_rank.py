"""IV Rank / Percentile — spec §6.2."""
from __future__ import annotations

from app.options.iv_rank import iv_percentile, iv_rank


def test_iv_rank_at_extremes() -> None:
    history = [0.10 + i * 0.001 for i in range(252)]   # 0.10..0.351
    assert iv_rank(min(history), history) == 0.0
    assert iv_rank(max(history), history) == 100.0


def test_iv_rank_midpoint() -> None:
    history = [0.10, 0.20, 0.30]
    assert 49 < iv_rank(0.20, history) < 51


def test_iv_percentile_uses_252_floor() -> None:
    # If history < 252 days, denominator should be 252, not len()
    history = [0.10] * 100
    assert iv_percentile(0.20, history) == 100 / 252 * 100


def test_iv_handles_empty_history() -> None:
    assert iv_rank(0.20, []) == 50.0
    assert iv_percentile(0.20, []) == 50.0
