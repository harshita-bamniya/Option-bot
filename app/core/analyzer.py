"""Analyzer — the end-to-end pipeline for a single instrument analysis.

Flow:
    candles_by_tf (+ options chain, news, VIX)
        → indicator groups per TF → IIS per TF → MTFS
        → pattern detection (15m + daily)
        → options score (IV rank + chain metrics)
        → news sentiment aggregation
        → FCS = weighted sum
        → Risk Engine
        → Position sizer
        → persisted signal row + JSON payload for explainer / Telegram

Runs synchronously for speed (<5s target — spec §12.3).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from app.config.constants import Direction, TradeType
from app.data.options_chain import OptionsChain
from app.db.repositories import SignalRepo
from app.indicators import IndicatorEngine, compute_iis
from app.indicators.structure import compute_key_levels
from app.options.iv_rank import compute_iv_metrics
from app.options.options_score import options_score
from app.options.strategy import select_strategy
from app.patterns.detector import detect_patterns, pattern_score
from app.risk.position_sizer import position_size, options_position_size
from app.risk.risk_engine import RiskContext, RiskDecision, RiskEngine
from app.scoring.fcs import FCSInputs, compute_fcs, position_scale
from app.scoring.mtfs import compute_mtfs
from app.scoring.regime import detect_regime
from app.utils.clock import current_session, days_to_weekly_expiry, now_ist
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class AnalysisResult:
    signal_id: str
    ts: datetime
    instrument: str
    spot_price: float
    direction: str
    trade_type: str
    fcs: float
    confidence_pct: float
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    position: dict
    groups: dict           # per-TF group scores
    mtfs: float
    iis_primary_tf: float
    pattern: dict
    options: dict
    news_sentiment: float
    regime: str
    session: str
    iv_rank: Optional[float]
    iv_percentile: Optional[float]
    vix: Optional[float]
    risk: dict
    warnings: List[str] = field(default_factory=list)
    rejected_reasons: List[str] = field(default_factory=list)
    key_levels: dict = field(default_factory=dict)


class Analyzer:

    def __init__(self) -> None:
        pass

    def analyze(
        self,
        *,
        instrument: str,
        candles_by_tf: Dict[str, pd.DataFrame],
        options_chain: Optional[OptionsChain],
        news_sentiment: float,
        vix_level: Optional[float] = None,
        iv_now: Optional[float] = None,
        user_capital: float,
        user_risk_pct: float,
        chat_id: Optional[int] = None,
        lot_size: int = 1,
    ) -> AnalysisResult:

        ts = now_ist()
        # --- MTFS ---
        mtfs_out = compute_mtfs(candles_by_tf)
        mtfs_raw = mtfs_out["mtfs"]

        # Primary TF for indicator details & pattern detection
        primary_tf = "15m" if "15m" in candles_by_tf else "1h"
        _pf = candles_by_tf.get(primary_tf)
        primary_df = _pf if (_pf is not None and not _pf.empty) else candles_by_tf.get("1d")
        if primary_df is None or primary_df.empty:
            raise ValueError(f"No candles available for {instrument}")

        groups = IndicatorEngine.run(primary_df)
        iis_primary = compute_iis(groups)

        # --- Pattern Detection ---
        hits_15m = detect_patterns(primary_df, lookback=5)
        hits_1d = detect_patterns(candles_by_tf.get("1d", primary_df), lookback=2)
        ps, pname, pconf = pattern_score(hits_15m + hits_1d)

        # --- Options Score ---
        dte = days_to_weekly_expiry(ts)
        iv_metrics: Dict = {}
        iv_rank_val: Optional[float] = None
        iv_pct_val: Optional[float] = None
        if iv_now is not None:
            iv_metrics = compute_iv_metrics(instrument, iv_now)
            iv_rank_val = iv_metrics.get("iv_rank")
            iv_pct_val = iv_metrics.get("iv_percentile")
        direction_hint = 1 if mtfs_raw > 0 else -1 if mtfs_raw < 0 else 0
        opt_score, opt_details = options_score(
            options_chain, iv_rank_val or 50.0, direction_hint, dte
        )

        # --- FCS ---
        fcs_res = compute_fcs(FCSInputs(
            iis=iis_primary,
            mtfs=mtfs_raw,
            options_score=opt_score,
            pattern_score=ps,
            news_sentiment=news_sentiment,
        ))

        # --- Levels + SL/TP heuristics ---
        spot = float(primary_df["close"].iloc[-1])
        klev = compute_key_levels(primary_df)
        atr = groups["volatility"].details.get("atr") or (spot * 0.005)
        atr_pct = groups["volatility"].details.get("atr_percentile")

        direction = fcs_res.direction
        entry = spot
        if direction == Direction.BUY:
            sl = max(klev.fib_382, spot - 1.5 * atr)
            t1 = spot + 2.0 * atr
            t2 = spot + 3.5 * atr
        elif direction == Direction.SELL:
            sl = min(klev.fib_618, spot + 1.5 * atr) if klev.fib_618 else (spot + 1.5 * atr)
            t1 = spot - 2.0 * atr
            t2 = spot - 3.5 * atr
        else:
            sl = spot; t1 = spot; t2 = spot

        rr = (abs(t1 - entry) / abs(entry - sl)) if abs(entry - sl) > 0 else 0

        # --- Risk Engine ---
        ctx = RiskContext(
            instrument=instrument,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            target_1=t1,
            target_2=t2,
            atr=atr,
            atr_percentile=atr_pct,
            iv_rank=iv_rank_val,
            vix=vix_level,
            chat_id=chat_id,
            capital=user_capital,
            daily_tf_bias=mtfs_out["biases"].get("1d", 0),
            hourly_tf_bias=mtfs_out["biases"].get("1h", 0),
            is_options=True,
            is_naked_buy=(direction == Direction.BUY and iv_rank_val is not None and iv_rank_val > 55),
        )
        decision: RiskDecision = RiskEngine.evaluate(ctx)

        # --- Position sizing ---
        scale = position_scale(fcs_res.fcs) * decision.size_scale
        if direction == Direction.NO_TRADE or not decision.allow:
            units, lots, risk_rs = 0, 0, user_capital * user_risk_pct / 100
        else:
            units, lots, risk_rs = position_size(
                capital=user_capital * scale,
                risk_pct=user_risk_pct,
                entry_price=entry,
                stop_loss=sl,
                lot_size=lot_size,
            )

        # --- Trade type classification ---
        trade_type = _classify_trade_type(
            dte=dte, iv_rank=iv_rank_val, mtfs=mtfs_raw, is_options=True
        ) if direction != Direction.NO_TRADE else TradeType.NO_TRADE

        # --- Strategy recommendation ---
        strategy = select_strategy(
            direction=direction.value,
            iv_rank=iv_rank_val or 50.0,
            days_to_expiry=dte,
            vix=vix_level,
            pcr=opt_details.get("pcr"),
        )

        regime = detect_regime(candles_by_tf.get("1d", primary_df))

        result = AnalysisResult(
            signal_id=f"SIG-{ts.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
            ts=ts,
            instrument=instrument,
            spot_price=spot,
            direction=direction.value,
            trade_type=trade_type.value,
            fcs=fcs_res.fcs,
            confidence_pct=fcs_res.confidence_pct,
            entry_price=entry,
            stop_loss=sl,
            target_1=t1,
            target_2=t2,
            risk_reward=rr,
            position={"units": units, "lots": lots, "risk_rs": risk_rs, "scale": scale},
            groups={g: {"score": r.score, "state": r.state, "confidence": r.confidence,
                        "details": r.details} for g, r in groups.items()},
            mtfs=mtfs_raw,
            iis_primary_tf=iis_primary,
            pattern={"name": pname, "confidence": pconf, "score": ps,
                     "hits": [h.__dict__ for h in hits_15m + hits_1d]},
            options={"score": opt_score, "details": opt_details,
                     "strategy": strategy, "dte": dte,
                     "iv_metrics": iv_metrics},
            news_sentiment=news_sentiment,
            regime=regime.value,
            session=current_session(ts),
            iv_rank=iv_rank_val,
            iv_percentile=iv_pct_val,
            vix=vix_level,
            risk={"allow": decision.allow, "size_scale": decision.size_scale,
                  "reasons_block": decision.reasons_block, "warnings": decision.warnings},
            warnings=decision.warnings,
            rejected_reasons=decision.reasons_block,
            key_levels=asdict(klev),
        )

        # --- Persist signal row (Parts A + B) ---
        self._persist(result, chat_id)
        return result

    # ------------------------------------------------------------------

    def _persist(self, r: AnalysisResult, chat_id: Optional[int]) -> None:
        try:
            SignalRepo.insert({
                "signal_id":      r.signal_id,
                "ts":             r.ts,
                "telegram_chat_id": chat_id,
                "instrument":     r.instrument,
                "spot_price":     r.spot_price,
                "trade_type":     r.trade_type,
                "direction":      r.direction,
                "fcs_score":      r.fcs,
                "confidence_pct": r.confidence_pct,
                "entry_price":    r.entry_price,
                "stop_loss":      r.stop_loss,
                "target_1":       r.target_1,
                "target_2":       r.target_2,
                "risk_reward":    r.risk_reward,
                "session":        r.session,
                "market_regime":  r.regime,
                "trend_group_score":    r.groups["trend"]["score"],
                "momentum_group_score": r.groups["momentum"]["score"],
                "volume_group_score":   r.groups["volume"]["score"],
                "volatility_state":     r.groups["volatility"]["state"],
                "structure_group_score": r.groups["structure"]["score"],
                "mtfs_score":     r.mtfs,
                "pattern_detected": r.pattern["name"],
                "pattern_confidence": r.pattern["confidence"],
                "iv_rank":        r.iv_rank,
                "iv_percentile":  r.iv_percentile,
                "pcr":            r.options["details"].get("pcr"),
                "news_sentiment_score": r.news_sentiment,
                "macro_event_flag": False,
                "vix_level":      r.vix,
                "raw_context":    {"options": r.options, "pattern": r.pattern,
                                   "key_levels": r.key_levels, "risk": r.risk},
            })
        except Exception:
            log.exception("persist_signal_failed", signal_id=r.signal_id)


def _classify_trade_type(*, dte: int, iv_rank: Optional[float], mtfs: float, is_options: bool) -> TradeType:
    """Spec §4.2 trade type rules."""
    if not is_options:
        return TradeType.POSITIONAL_EQUITY
    if dte <= 2:
        return TradeType.INTRADAY_OPTIONS
    if dte <= 7:
        return TradeType.SWING_OPTIONS
    if iv_rank is not None and iv_rank < 40 and abs(mtfs) > 0.5:
        return TradeType.POSITIONAL_OPTIONS
    if iv_rank is not None and iv_rank > 65:
        return TradeType.HEDGED
    return TradeType.SWING_OPTIONS
