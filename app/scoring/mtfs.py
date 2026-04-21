"""Multi-Timeframe Score (spec §8.2).

MTFS = Daily×0.30 + 1H×0.30 + 15m×0.25 + 5m×0.15
Each timeframe bias: Bullish=+1, Neutral=0, Bearish=-1.

CRITICAL RULE (spec): higher timeframes override lower. If Daily AND 1H
both contradict the trade direction, the signal is rejected by the Risk layer.
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from app.config.constants import MTFS_WEIGHTS
from app.indicators import IndicatorEngine, compute_iis


def tf_bias_from_iis(iis: float) -> int:
    if iis > 15: return 1
    if iis < -15: return -1
    return 0


def compute_mtfs(candles_by_tf: Dict[str, pd.DataFrame]) -> dict:
    """candles_by_tf maps '5m'/'15m'/'1h'/'1d' → OHLCV DataFrame."""
    biases: Dict[str, int] = {}
    details: Dict[str, dict] = {}

    for tf in MTFS_WEIGHTS:
        df = candles_by_tf.get(tf)
        if df is None or len(df) < 30:
            biases[tf] = 0
            details[tf] = {"reason": "insufficient_data"}
            continue
        results = IndicatorEngine.run(df)
        iis = compute_iis(results)
        bias = tf_bias_from_iis(iis)
        biases[tf] = bias
        details[tf] = {"iis": iis, "bias": bias,
                       "groups": {g: {"score": r.score, "state": r.state,
                                      "confidence": r.confidence}
                                  for g, r in results.items()}}

    mtfs = sum(biases[tf] * MTFS_WEIGHTS[tf] for tf in MTFS_WEIGHTS)
    # Alignment check
    higher_agree = (biases.get("1d", 0) != 0 and biases.get("1d", 0) == biases.get("1h", 0))
    higher_contradict = biases.get("1d", 0) * biases.get("1h", 0) < 0

    return {
        "mtfs": mtfs,
        "biases": biases,
        "per_tf": details,
        "higher_tf_aligned": higher_agree,
        "higher_tf_contradict": higher_contradict,
    }
