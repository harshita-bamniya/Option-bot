"""APScheduler wiring — converts the job definitions into cron triggers."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.alerts.alert_engine import AlertEngine
from app.config.settings import settings
from app.scheduler import jobs
from app.telegram_bot.service import TelegramService
from app.utils.logging import get_logger

log = get_logger(__name__)


def build_scheduler(bot, svc: TelegramService) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=settings.tz)
    engine = AlertEngine()

    # 08:30 IST — historical warmup (backfill missing bars)
    sched.add_job(
        jobs.job_warmup, CronTrigger(hour=8, minute=30, day_of_week="mon-fri"),
        id="warmup", replace_existing=True,
    )

    # 09:00 IST — pre-market brief, weekdays
    sched.add_job(
        jobs.job_premarket_brief, CronTrigger(hour=9, minute=0, day_of_week="mon-fri"),
        args=[bot, engine], id="premarket_brief", replace_existing=True,
    )

    # 09:30 IST — expiry-day reminder (Thursdays)
    sched.add_job(
        jobs.job_expiry_reminder, CronTrigger(hour=9, minute=30, day_of_week="thu"),
        args=[bot, engine], id="expiry_reminder", replace_existing=True,
    )

    # Every 5 min during market hours — news poll + breakout scan
    sched.add_job(
        jobs.job_news_poll, CronTrigger(minute="*/5", hour="9-15", day_of_week="mon-fri"),
        args=[svc], id="news_poll", replace_existing=True,
    )
    sched.add_job(
        jobs.job_breakout_scan, CronTrigger(minute="*/5", hour="9-15", day_of_week="mon-fri"),
        args=[bot, engine], id="breakout_scan", replace_existing=True,
    )

    # Every 30 min — options chain snapshot
    sched.add_job(
        jobs.job_chain_snapshot, CronTrigger(minute="0,30", hour="9-15", day_of_week="mon-fri"),
        args=[svc, bot, engine], id="chain_snapshot", replace_existing=True,
    )

    # 15:30 IST — EOD IV store
    sched.add_job(
        jobs.job_eod_iv, CronTrigger(hour=15, minute=30, day_of_week="mon-fri"),
        args=[svc], id="eod_iv", replace_existing=True,
    )

    # Sunday 02:00 IST — weekly learning
    sched.add_job(
        jobs.job_weekly_learning, CronTrigger(hour=2, minute=0, day_of_week="sun"),
        id="weekly_learning", replace_existing=True,
    )

    log.info("scheduler_built", jobs=[j.id for j in sched.get_jobs()])
    return sched
