"""Smoke test the indicator engine end-to-end on synthetic data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators import IndicatorEngine, compute_iis


def _synthetic_uptrend(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(100, 130, n) + rng.normal(0, 0.4, n)
    high = base + rng.uniform(0.3, 1.0, n)
    low = base - rng.uniform(0.3, 1.0, n)
    open_ = base + rng.normal(0, 0.2, n)
    close = base + rng.normal(0, 0.2, n)
    volume = rng.integers(100_000, 500_000, n)
    idx = pd.date_range("2025-01-01", periods=n, freq="15min")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


def test_engine_returns_all_six_groups() -> None:
    df = _synthetic_uptrend()
    out = IndicatorEngine.run(df)
    for g in ("trend", "momentum", "volume", "volatility", "structure", "hybrid"):
        assert g in out
        assert -1.0 <= out[g].score <= 1.0


def test_uptrend_yields_positive_iis() -> None:
    df = _synthetic_uptrend()
    out = IndicatorEngine.run(df)
    iis = compute_iis(out)
    assert iis > 0          # synthetic up-drift → bullish IIS
    assert -100.0 <= iis <= 100.0
