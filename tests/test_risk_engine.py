"""RiskEngine hard rules — spec §8.3."""
from __future__ import annotations

from app.config.constants import Direction
from app.risk.risk_engine import RiskContext, RiskEngine


def _ctx(**over) -> RiskContext:
    base = dict(
        instrument="NIFTY", direction=Direction.BUY,
        entry_price=24500.0, stop_loss=24400.0, target_1=24700.0, target_2=24900.0,
        atr=80.0, atr_percentile=50, iv_rank=40, vix=14,
        chat_id=None, capital=500_000,
        daily_tf_bias=1, hourly_tf_bias=1,
        is_options=True, is_naked_buy=False,
    )
    base.update(over)
    return RiskContext(**base)


def test_clean_setup_passes() -> None:
    d = RiskEngine.evaluate(_ctx())
    assert d.allow
    assert d.size_scale > 0


def test_sl_too_wide_blocks() -> None:
    d = RiskEngine.evaluate(_ctx(stop_loss=23900.0))      # ~2.4%
    assert not d.allow
    assert any("SL distance" in r for r in d.reasons_block)


def test_low_rr_blocks() -> None:
    d = RiskEngine.evaluate(_ctx(target_1=24550.0))       # RR ~ 0.5
    assert not d.allow
    assert any("RR" in r for r in d.reasons_block)


def test_iv_rank_above_85_blocks_buy() -> None:
    d = RiskEngine.evaluate(_ctx(iv_rank=90))
    assert not d.allow
    assert any("IV Rank" in r for r in d.reasons_block)


def test_atr_extreme_blocks() -> None:
    d = RiskEngine.evaluate(_ctx(atr_percentile=98))
    assert not d.allow


def test_both_higher_tfs_contradict_blocks() -> None:
    d = RiskEngine.evaluate(_ctx(daily_tf_bias=-1, hourly_tf_bias=-1))
    assert not d.allow


def test_no_trade_direction_blocks() -> None:
    d = RiskEngine.evaluate(_ctx(direction=Direction.NO_TRADE))
    assert not d.allow
