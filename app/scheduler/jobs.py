"""Scheduled job implementations — kept here so scheduler.py is just wiring.

Schedule (spec §13, IST):
    08:30  warmup   — refresh historical/EOD pulls into DB if missing
    09:00  pre-market brief to every user (alerts_on=True)
    09:30  expiry-day reminder (Thursdays only)
    every 5m during market hours    — news poll + sentiment refresh
    every 30m during market hours   — options chain snapshot + IV log
    15:30  EOD IV close persisted into iv_history
    Sun 02:00  weekly learning run (Phase 1 statistical)
"""
from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select

from app.alerts.alert_engine import AlertEngine
from app.config.constants import INSTRUMENT_UNIVERSE
from app.db.models import User
from app.db.repositories import IVHistoryRepo
from app.db.session import get_session
from app.news.marketaux import MarketauxClient
from app.telegram_bot.service import TelegramService
from app.utils.clock import is_market_open, now_ist
from app.utils.logging import get_logger

log = get_logger(__name__)


# ----------------- 09:00 — pre-market brief -----------------

async def job_premarket_brief(bot, engine: AlertEngine) -> None:
    with get_session() as s:
        users = list(s.execute(select(User).where(User.alerts_on.is_(True))).scalars().all())
    log.info("premarket_brief_run", users=len(users))
    alerts = [engine.pre_market_brief(u) for u in users]
    await engine.dispatch(alerts, bot.send_message)


# ----------------- 09:30 — expiry-day reminder ----------------

async def job_expiry_reminder(bot, engine: AlertEngine) -> None:
    template = engine.detect_expiry_day()
    if not template:
        return
    alerts = engine.expand_for_users(template)
    await engine.dispatch(alerts, bot.send_message)


# ----------------- every 5m — news poll ----------------------

async def job_news_poll(svc: TelegramService) -> None:
    if not is_market_open():
        return
    try:
        await svc.news.all_news(symbols=list(INSTRUMENT_UNIVERSE.keys())[:5], limit=20)
    except Exception:
        log.exception("news_poll_failed")


# ----------------- every 30m — options chain snapshot --------

async def job_chain_snapshot(svc: TelegramService, bot, engine: AlertEngine) -> None:
    if not is_market_open():
        return
    for sym, meta in INSTRUMENT_UNIVERSE.items():
        if not meta.get("options"):
            continue
        try:
            expiry = svc._nearest_expiry()
            chain = await svc.chain_svc.fetch(sym, expiry)
            if not chain:
                continue
            atm = chain.atm_strike()
            if not atm:
                continue
            atm_q = next((q for q in chain.quotes if q.strike == atm and q.option_type == "CE"), None)
            if not atm_q or not atm_q.iv:
                continue
            iv = float(atm_q.iv) / 100.0 if atm_q.iv > 5 else float(atm_q.iv)
            # IV spike/crush detection
            tmpl = engine.detect_iv_event(sym, iv)
            if tmpl:
                await engine.dispatch(engine.expand_for_users(tmpl), bot.send_message)
        except Exception:
            log.exception("chain_snapshot_failed", sym=sym)


# ----------------- every 5m — breakout scanner ---------------

async def job_breakout_scan(bot, engine: AlertEngine) -> None:
    if not is_market_open():
        return
    for sym in INSTRUMENT_UNIVERSE.keys():
        try:
            tmpl = engine.detect_breakout(sym)
            if tmpl:
                await engine.dispatch(engine.expand_for_users(tmpl), bot.send_message)
        except Exception:
            log.exception("breakout_scan_failed", sym=sym)


# ----------------- 15:30 — EOD IV store ----------------------

async def job_eod_iv(svc: TelegramService) -> None:
    today = now_ist().date()
    for sym, meta in INSTRUMENT_UNIVERSE.items():
        if not meta.get("options"):
            continue
        try:
            expiry = svc._nearest_expiry()
            chain = await svc.chain_svc.fetch(sym, expiry)
            if not chain:
                continue
            atm = chain.atm_strike()
            atm_q = next((q for q in chain.quotes if q.strike == atm and q.option_type == "CE"), None)
            if not atm_q or not atm_q.iv:
                continue
            iv = float(atm_q.iv) / 100.0 if atm_q.iv > 5 else float(atm_q.iv)
            IVHistoryRepo.upsert({
                "instrument": sym,
                "date": today,
                "iv_close": iv,
            })
        except Exception:
            log.exception("eod_iv_failed", sym=sym)


# ----------------- Sunday — learning run ---------------------

async def job_weekly_learning() -> None:
    from app.learning.statistical import run_weekly_update
    try:
        await asyncio.get_event_loop().run_in_executor(None, run_weekly_update)
    except Exception:
        log.exception("weekly_learning_failed")
