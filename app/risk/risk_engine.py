"""Hard-rule Risk Engine (spec §8.3).

Every signal passes through here BEFORE the user sees it. If any rule fires
the signal is rejected regardless of FCS. Also decides position scaling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.config.constants import HARD_RISK_RULES, VIX_BANDS, Direction, EXPIRY_OTM_BUY_CUTOFF, EXPIRY_SELL_ONLY_FROM
from app.news.events import has_high_impact_event_within
from app.risk.daily_limits import DailyLimitTracker
from app.utils.clock import now_ist, days_to_weekly_expiry


@dataclass
class RiskContext:
    instrument: str
    direction: Direction
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: Optional[float]
    atr: Optional[float] = None
    atr_percentile: Optional[float] = None
    iv_rank: Optional[float] = None
    vix: Optional[float] = None
    chat_id: Optional[int] = None
    capital: Optional[float] = None
    daily_tf_bias: int = 0         # +1/-1/0
    hourly_tf_bias: int = 0
    circuit_breaker_active: bool = False
    is_options: bool = False
    is_naked_buy: bool = False


@dataclass
class RiskDecision:
    allow: bool
    reasons_block: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    size_scale: float = 1.0          # 0.0 = no trade, 0.5 = half, etc.
    adjusted_sl: Optional[float] = None
    adjusted_target: Optional[float] = None


class RiskEngine:

    @staticmethod
    def evaluate(ctx: RiskContext) -> RiskDecision:
        d = RiskDecision(allow=True)

        # --- Rule 0: circuit breaker halts all trading ---
        if ctx.circuit_breaker_active:
            return RiskDecision(allow=False, reasons_block=["Market circuit breaker active"], size_scale=0.0)

        direction_sign = 1 if ctx.direction == Direction.BUY else -1 if ctx.direction == Direction.SELL else 0
        if direction_sign == 0:
            return RiskDecision(allow=False, reasons_block=["Direction = NO TRADE"], size_scale=0.0)

        # --- Rule 1: SL distance > 2% of price ---
        sl_distance_pct = abs(ctx.entry_price - ctx.stop_loss) / ctx.entry_price * 100 if ctx.entry_price else 100
        if sl_distance_pct > HARD_RISK_RULES["max_sl_distance_pct"]:
            d.reasons_block.append(
                f"SL distance {sl_distance_pct:.2f}% exceeds max {HARD_RISK_RULES['max_sl_distance_pct']}%"
            )

        # --- Rule 2: RR < 2:1 ---
        reward = abs(ctx.target_1 - ctx.entry_price)
        risk = abs(ctx.entry_price - ctx.stop_loss)
        rr = reward / risk if risk > 0 else 0
        if rr < HARD_RISK_RULES["min_rr_ratio"]:
            d.reasons_block.append(f"RR {rr:.2f}:1 < min {HARD_RISK_RULES['min_rr_ratio']}:1")

        # --- Rule 3: HIGH-impact event within blackout window ---
        has_event, evt = has_high_impact_event_within(HARD_RISK_RULES["event_blackout_minutes"])
        if has_event:
            d.reasons_block.append(
                f"HIGH-impact event within {HARD_RISK_RULES['event_blackout_minutes']}min: {evt.name if evt else ''}"
            )

        # --- Rule 4: ATR in top 5% of 1-year range ---
        if ctx.atr_percentile is not None and ctx.atr_percentile >= HARD_RISK_RULES["atr_extreme_percentile"]:
            d.reasons_block.append(
                f"ATR percentile {ctx.atr_percentile:.0f} ≥ {HARD_RISK_RULES['atr_extreme_percentile']} (EXTREME volatility)"
            )

        # --- Rule 5: IV Rank > 85 on BUY ---
        if ctx.direction == Direction.BUY and ctx.iv_rank is not None \
                and ctx.iv_rank > HARD_RISK_RULES["iv_rank_buy_block"]:
            d.reasons_block.append(
                f"IV Rank {ctx.iv_rank:.0f} > {HARD_RISK_RULES['iv_rank_buy_block']} on BUY — options dangerously overpriced"
            )

        # --- Rule 6: daily loss limit ---
        if ctx.chat_id and ctx.capital:
            if DailyLimitTracker.is_suspended(ctx.chat_id, ctx.capital,
                                              limit_pct=HARD_RISK_RULES["daily_loss_limit_pct"]):
                d.reasons_block.append(
                    f"Daily loss limit ({HARD_RISK_RULES['daily_loss_limit_pct']}% of capital) hit — suspended"
                )

        # --- Rule 7: Daily+Hourly both contradict direction ---
        if ctx.daily_tf_bias * direction_sign < 0 and ctx.hourly_tf_bias * direction_sign < 0:
            d.reasons_block.append("Both Daily and 1H timeframes contradict signal direction")

        # --- VIX bands (spec §11.3) — warnings + sizing ---
        if ctx.vix is not None:
            for lo, hi, interp, sl_mult, size_mult, block_naked in VIX_BANDS:
                if lo <= ctx.vix < hi:
                    if block_naked and ctx.is_naked_buy:
                        d.reasons_block.append(f"VIX {ctx.vix:.1f} — naked buy blocked ({interp})")
                    d.size_scale *= size_mult
                    if sl_mult != 1.0:
                        d.adjusted_sl = ctx.entry_price - direction_sign * abs(ctx.entry_price - ctx.stop_loss) * sl_mult
                        d.warnings.append(f"VIX {ctx.vix:.1f}: widening SL ×{sl_mult}, reducing size ×{size_mult}")
                    break

        # --- Expiry-day cutoffs (spec §10.4) ---
        if ctx.is_options:
            now = now_ist()
            dte = days_to_weekly_expiry(now)
            if dte == 0:
                t = now.time()
                if t >= EXPIRY_OTM_BUY_CUTOFF and ctx.is_naked_buy:
                    d.reasons_block.append("Expiry day after 10:00 — no OTM naked buying (theta decay)")
                elif t >= EXPIRY_SELL_ONLY_FROM and ctx.direction == Direction.BUY and ctx.is_naked_buy:
                    d.reasons_block.append("Expiry day after 11:00 — only premium selling permitted")

        if d.reasons_block:
            d.allow = False
            d.size_scale = 0.0
        return d
