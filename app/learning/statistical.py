"""Phase 1 statistical learning engine — spec §9.

Computes per-group win-rates and adjusts FCS group weights with the
**safety gates** from §9.3:

    * No mid-session updates (only Sunday job)
    * Min 50 outcomes per group before its weight is allowed to move
    * Max 10% relative change per weekly run
    * 70/30 holdout validation; rollback if holdout win-rate drops > 5%
    * Gradual rollout — new weights stored as a versioned row, then activated
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import select

from app.config.constants import GROUP_WEIGHTS
from app.db.models import LearningWeights, TradeOutcome, TradeSignal
from app.db.repositories import WeightsRepo
from app.db.session import get_session
from app.utils.logging import get_logger

log = get_logger(__name__)


MIN_SAMPLES_PER_GROUP   = 50
MAX_RELATIVE_CHANGE     = 0.10        # 10%
HOLDOUT_FRACTION        = 0.30
ROLLBACK_DROP_PCT       = 5.0


# ---------------------------------------------------------------------------

def _load_closed_signals() -> List[Tuple[TradeSignal, TradeOutcome]]:
    with get_session() as s:
        q = (select(TradeSignal, TradeOutcome)
             .join(TradeOutcome, TradeOutcome.signal_id == TradeSignal.signal_id)
             .where(TradeOutcome.outcome_label.in_(["WIN", "LOSS"])))
        rows = list(s.execute(q).all())
        for sig, out in rows:
            s.expunge(sig); s.expunge(out)
        return rows


def compute_indicator_performance(rows) -> Dict[str, dict]:
    """Per-group win-rate and contribution stat."""
    out: Dict[str, dict] = {g: {"wins": 0, "losses": 0} for g in GROUP_WEIGHTS}
    for sig, oc in rows:
        wl = "wins" if oc.outcome_label == "WIN" else "losses"
        # We only have aggregated group scores per signal; use sign-alignment:
        for g, score_attr in [
            ("trend",      "trend_group_score"),
            ("momentum",   "momentum_group_score"),
            ("volume",     "volume_group_score"),
            ("structure",  "structure_group_score"),
        ]:
            val = getattr(sig, score_attr, None)
            if val is None:
                continue
            # group "agreed with the signal" when its sign matched direction
            agreed = (val > 0 and sig.direction == "BUY") or (val < 0 and sig.direction == "SELL")
            if agreed:
                out[g][wl] += 1
    for g, d in out.items():
        n = d["wins"] + d["losses"]
        d["n"] = n
        d["win_rate"] = (d["wins"] / n) if n else 0.0
    return out


# ---------------------------------------------------------------------------

def _propose_weights(perf: Dict[str, dict], current: Dict[str, float]) -> Dict[str, float]:
    """Bump groups with above-average win-rates, dampen poor ones — bounded."""
    avg_wr = sum(p["win_rate"] for p in perf.values()) / max(len(perf), 1)
    proposed: Dict[str, float] = {}
    for g, w in current.items():
        p = perf.get(g, {})
        if p.get("n", 0) < MIN_SAMPLES_PER_GROUP or avg_wr == 0:
            proposed[g] = w
            continue
        rel = (p["win_rate"] - avg_wr) / max(avg_wr, 0.01)
        rel = max(-MAX_RELATIVE_CHANGE, min(MAX_RELATIVE_CHANGE, rel))
        proposed[g] = w * (1 + rel)
    # Renormalize to sum 1.0
    s = sum(proposed.values()) or 1.0
    return {k: v / s for k, v in proposed.items()}


def _holdout_score(rows, weights: Dict[str, float]) -> float:
    """Re-score signals using new weights and compute hypothetical win-rate.

    A signal is counted as a 'predicted win' when the weighted group score
    sign matches the actual outcome's direction.
    """
    if not rows:
        return 0.0
    correct = 0
    for sig, oc in rows:
        proxy = (
            (sig.trend_group_score      or 0) * weights.get("trend", 0)
            + (sig.momentum_group_score or 0) * weights.get("momentum", 0)
            + (sig.volume_group_score   or 0) * weights.get("volume", 0)
            + (sig.structure_group_score or 0) * weights.get("structure", 0)
        )
        predicted = "BUY" if proxy > 0 else "SELL"
        if (predicted == sig.direction and oc.outcome_label == "WIN") \
           or (predicted != sig.direction and oc.outcome_label == "LOSS"):
            correct += 1
    return correct / len(rows) * 100.0


# ---------------------------------------------------------------------------

def run_weekly_update() -> dict:
    """Top-level entry point (called from scheduler.jobs)."""
    rows = _load_closed_signals()
    if len(rows) < 100:
        log.info("learning_skip_insufficient_data", n=len(rows))
        return {"status": "skipped", "reason": "insufficient_data", "n": len(rows)}

    cutoff = int(len(rows) * (1 - HOLDOUT_FRACTION))
    train, holdout = rows[:cutoff], rows[cutoff:]

    current = (WeightsRepo.active().weights if WeightsRepo.active() else GROUP_WEIGHTS).copy() \
        if WeightsRepo.active() else GROUP_WEIGHTS.copy()

    perf = compute_indicator_performance(train)
    proposed = _propose_weights(perf, current)

    cur_score = _holdout_score(holdout, current)
    new_score = _holdout_score(holdout, proposed)
    log.info("learning_holdout", current=cur_score, proposed=new_score)

    if new_score < cur_score - ROLLBACK_DROP_PCT:
        log.warning("learning_rollback", drop=cur_score - new_score)
        return {"status": "rolled_back", "current": cur_score, "proposed": new_score}

    # Persist new version
    with get_session() as s:
        last = s.execute(select(LearningWeights).order_by(LearningWeights.version_id.desc()).limit(1)).scalar_one_or_none()
        next_v = (last.version_id if last else 0) + 1
        row = LearningWeights(
            version_id=next_v,
            created_at=datetime.utcnow(),
            active=False,
            weights=proposed,
            performance={"holdout_current": cur_score, "holdout_proposed": new_score,
                         "perf": perf, "n_train": len(train), "n_holdout": len(holdout)},
        )
        s.add(row)
        s.flush()
        version_id = row.version_id
    WeightsRepo.activate(version_id)
    log.info("learning_activated", version=version_id, weights=proposed)
    return {"status": "activated", "version": version_id, "weights": proposed,
            "current": cur_score, "proposed": new_score}
