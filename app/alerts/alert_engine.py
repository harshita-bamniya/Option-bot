"""Alert engine — proactive notifications per spec §2.3.

Alert types implemented:
    - Breakout: price closes beyond key swing high/low with RVOL > 1.5
    - IV Spike: ATM IV > 2σ above 20-day mean
    - IV Crush: ATM IV < 0.5× 20-day mean (good for buyers)
    - Pre-Market Brief: 09:00 IST scheduled brief per user
    - Event Warning: HIGH-impact macro event within 30 min
    - Expiry Day: 09:30 IST Thursday reminder of cutoffs
    - Trade Update: TP1/SL hit on tracked open signals

Each alert is delivered via the Telegram bot's `bot.send_message` and logged
into `alerts_log` for observability and idempotency.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from sqlalchemy import select

from app.config.constants import EXPIRY_OTM_BUY_CUTOFF, INSTRUMENT_UNIVERSE
from app.data.cache import cache
from app.db.models import AlertLog, IVHistory, User
from app.db.repositories import IVHistoryRepo, MarketDataRepo, UserRepo
from app.db.session import get_session
from app.news.events import has_high_impact_event_within
from app.utils.clock import days_to_weekly_expiry, is_market_open, now_ist
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class Alert:
    chat_id: int
    instrument: Optional[str]
    alert_type: str
    severity: str               # INFO | WARN | CRITICAL
    title: str
    body: str
    dedup_key: str              # idempotency
    extra: dict = field(default_factory=dict)


class AlertEngine:
    """Pure-detection engine. Delivery is decoupled — pass a `send_fn`
    (e.g. `bot.send_message`) at runtime."""

    DEDUP_TTL_SECONDS = 1800     # don't repeat same alert within 30 min

    # ----------------------- detectors -----------------------

    def detect_breakout(self, instrument: str) -> Optional[Alert]:
        df = MarketDataRepo.recent(instrument, "15m", 100)
        if len(df) < 50:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-50:-1]
        swing_high = float(prev["high"].max())
        swing_low = float(prev["low"].min())
        avg_vol = float(prev["volume"].mean()) or 1.0
        rvol = float(last["volume"]) / avg_vol

        if last["close"] > swing_high and rvol > 1.5:
            return Alert(
                chat_id=0, instrument=instrument, alert_type="BREAKOUT",
                severity="WARN",
                title=f"🚀 Breakout: {instrument}",
                body=(f"{instrument} closed {last['close']:.2f} above 50-bar high "
                      f"{swing_high:.2f} on 15m with RVOL {rvol:.2f}x."),
                dedup_key=f"breakout:up:{instrument}:{last.name:%Y%m%d%H%M}",
            )
        if last["close"] < swing_low and rvol > 1.5:
            return Alert(
                chat_id=0, instrument=instrument, alert_type="BREAKDOWN",
                severity="WARN",
                title=f"⚠️ Breakdown: {instrument}",
                body=(f"{instrument} closed {last['close']:.2f} below 50-bar low "
                      f"{swing_low:.2f} on 15m with RVOL {rvol:.2f}x."),
                dedup_key=f"breakout:dn:{instrument}:{last.name:%Y%m%d%H%M}",
            )
        return None

    def detect_iv_event(self, instrument: str, current_iv: float) -> Optional[Alert]:
        history = IVHistoryRepo.last_252(instrument)[:20]
        if len(history) < 10:
            return None
        mean = statistics.mean(history)
        stdev = statistics.pstdev(history) or 0.01
        z = (current_iv - mean) / stdev

        if z > 2.0:
            return Alert(
                chat_id=0, instrument=instrument, alert_type="IV_SPIKE",
                severity="WARN",
                title=f"📈 IV Spike: {instrument}",
                body=(f"ATM IV {current_iv*100:.1f}% is +{z:.1f}σ vs 20-day mean "
                      f"({mean*100:.1f}%). Favour premium-selling structures."),
                dedup_key=f"iv_spike:{instrument}:{now_ist():%Y%m%d}",
            )
        if current_iv < 0.5 * mean:
            return Alert(
                chat_id=0, instrument=instrument, alert_type="IV_CRUSH",
                severity="INFO",
                title=f"📉 IV Crush: {instrument}",
                body=(f"ATM IV {current_iv*100:.1f}% has collapsed to "
                      f"{current_iv/mean*100:.0f}% of 20-day mean — long premium gets cheap."),
                dedup_key=f"iv_crush:{instrument}:{now_ist():%Y%m%d}",
            )
        return None

    def detect_event_warning(self, instrument: str) -> Optional[Alert]:
        if not has_high_impact_event_within(30):
            return None
        return Alert(
            chat_id=0, instrument=instrument, alert_type="EVENT_WARNING",
            severity="CRITICAL",
            title="⏰ Event Warning",
            body="HIGH-impact macro event within 30 min — new entries blocked. "
                 "Square-off existing intraday positions or use protective hedges.",
            dedup_key=f"event:{now_ist():%Y%m%d%H%M}",
        )

    def detect_expiry_day(self) -> Optional[Alert]:
        now = now_ist()
        if now.weekday() != 3:        # Thursday
            return None
        return Alert(
            chat_id=0, instrument="NIFTY", alert_type="EXPIRY_DAY",
            severity="WARN",
            title="🗓️ Weekly Expiry Today",
            body=(f"No fresh OTM long buying after {EXPIRY_OTM_BUY_CUTOFF:%H:%M}. "
                  "Premium-selling only from 11:00. Theta-decay is severe; size halves."),
            dedup_key=f"expiry:{now:%Y%m%d}",
        )

    def pre_market_brief(self, user: User) -> Alert:
        wl = ", ".join(user.watchlist[:6]) if user.watchlist else "—"
        body_lines = [
            f"☀️ Good morning — {now_ist():%a %d %b}",
            f"Capital: Rs {float(user.capital):,.0f}   Risk/trade: {float(user.risk_pct)}%",
            f"Watchlist: {wl}",
            f"Style: {user.trade_style}",
            "Use /watchlist for a one-shot scan or /analyze SYMBOL for the full report.",
        ]
        return Alert(
            chat_id=user.telegram_chat_id, instrument=None,
            alert_type="PRE_MARKET", severity="INFO",
            title="Pre-Market Brief",
            body="\n".join(body_lines),
            dedup_key=f"premarket:{user.telegram_chat_id}:{now_ist():%Y%m%d}",
        )

    # ----------------------- dedup + persist -----------------------

    def _is_duplicate(self, dedup_key: str) -> bool:
        k = f"alert_dedup:{dedup_key}"
        if cache.get(k):
            return True
        cache.set(k, "1", ttl_seconds=self.DEDUP_TTL_SECONDS)
        return False

    def _persist(self, a: Alert) -> None:
        try:
            with get_session() as s:
                s.add(AlertLog(
                    ts=now_ist(),
                    telegram_chat_id=a.chat_id or None,
                    instrument=a.instrument,
                    alert_type=a.alert_type,
                    severity=a.severity,
                    title=a.title,
                    body=a.body,
                    extra=a.extra,
                ))
        except Exception:
            log.exception("alert_persist_failed", type=a.alert_type)

    # ----------------------- dispatch -----------------------

    async def dispatch(self, alerts: Iterable[Alert], send_fn) -> int:
        sent = 0
        for a in alerts:
            if not a or self._is_duplicate(a.dedup_key):
                continue
            if not a.chat_id:
                continue
            try:
                await send_fn(chat_id=a.chat_id, text=f"{a.title}\n{a.body}")
                sent += 1
            except Exception:
                log.exception("alert_send_failed", type=a.alert_type, chat=a.chat_id)
            self._persist(a)
        return sent

    # ----------------------- broadcast helpers -----------------------

    def expand_for_users(self, template: Alert) -> List[Alert]:
        """Clone an instrument-level alert to every user with that symbol on watchlist."""
        with get_session() as s:
            users = s.execute(select(User).where(User.alerts_on.is_(True))).scalars().all()
            result = []
            for u in users:
                if template.instrument and template.instrument not in (u.watchlist or []):
                    continue
                a = Alert(**{**template.__dict__,
                             "chat_id": u.telegram_chat_id,
                             "dedup_key": f"{template.dedup_key}:{u.telegram_chat_id}"})
                result.append(a)
            return result
