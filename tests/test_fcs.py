"""FCS scoring + thresholds — spec §8.1."""
from __future__ import annotations

from app.config.constants import Direction
from app.scoring.fcs import FCSInputs, compute_fcs, fcs_to_direction, position_scale


def test_strong_bullish_inputs_yield_high_buy() -> None:
    res = compute_fcs(FCSInputs(
        iis=80, mtfs=0.9, options_score=70, pattern_score=60, news_sentiment=0.6,
    ))
    assert res.direction == Direction.BUY
    assert res.fcs >= 60
    assert res.confidence_pct >= 70


def test_neutral_inputs_yield_no_trade() -> None:
    res = compute_fcs(FCSInputs(
        iis=10, mtfs=0.05, options_score=5, pattern_score=0, news_sentiment=0.0,
    ))
    assert res.direction == Direction.NO_TRADE


def test_strong_bearish_inputs_yield_sell() -> None:
    res = compute_fcs(FCSInputs(
        iis=-75, mtfs=-0.8, options_score=-60, pattern_score=-50, news_sentiment=-0.5,
    ))
    assert res.direction == Direction.SELL
    assert res.fcs <= -60


def test_threshold_boundaries() -> None:
    assert fcs_to_direction(60.0) == Direction.BUY
    assert fcs_to_direction(35.1) == Direction.BUY
    assert fcs_to_direction(34.9) == Direction.NO_TRADE
    assert fcs_to_direction(-60.0) == Direction.SELL


def test_position_scale_tiers() -> None:
    assert position_scale(70) == 1.0
    assert position_scale(40) == 0.5
    assert position_scale(20) == 0.0
