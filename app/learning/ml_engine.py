"""Phase 2 ML engine — XGBoost on engineered features (spec §9.2).

Trained only after we have ≥500 closed outcomes. Outputs a calibrated
probability that is *blended* with the rule-based FCS rather than replacing it.

This module is intentionally a thin scaffold — full feature engineering and
training is deferred until the dataset is mature, but the interface is fixed
so the rest of the system (FCS, Risk Engine) can call into it safely.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.utils.logging import get_logger

log = get_logger(__name__)

MODEL_PATH = os.environ.get("ML_MODEL_PATH", "models/fcs_xgb.pkl")
MIN_OUTCOMES_FOR_TRAINING = 500
BLEND_WEIGHT = 0.30                 # ML contribution = 30%, rules = 70%


@dataclass
class MLPrediction:
    probability: float              # 0..1, BUY-up
    blended_fcs: float              # combined with rule-based fcs
    used_model: bool


class MLEngine:

    def __init__(self) -> None:
        self.model = None
        self._load()

    def _load(self) -> None:
        if not os.path.exists(MODEL_PATH):
            return
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            log.info("ml_model_loaded", path=MODEL_PATH)
        except Exception:
            log.exception("ml_model_load_failed")

    def predict(self, features: dict, rule_fcs: float) -> MLPrediction:
        if self.model is None:
            return MLPrediction(probability=0.5, blended_fcs=rule_fcs, used_model=False)
        try:
            x = np.array([[features.get(k, 0.0) for k in sorted(features)]])
            p = float(self.model.predict_proba(x)[0, 1])
            ml_fcs = (p - 0.5) * 200          # → roughly [-100, +100]
            blended = (1 - BLEND_WEIGHT) * rule_fcs + BLEND_WEIGHT * ml_fcs
            return MLPrediction(probability=p, blended_fcs=blended, used_model=True)
        except Exception:
            log.exception("ml_predict_failed")
            return MLPrediction(probability=0.5, blended_fcs=rule_fcs, used_model=False)


def can_train(n_outcomes: int) -> bool:
    return n_outcomes >= MIN_OUTCOMES_FOR_TRAINING
