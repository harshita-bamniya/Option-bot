"""Production entrypoint — wires the data pipeline, Telegram bot, and scheduler.

Run with:    python -m app.main

All long-running coroutines are supervised by a single asyncio event loop.
A graceful shutdown handler closes the bot, scheduler, market-data pipeline,
and HTTP clients in reverse order of startup.
"""
from __future__ import annotations

import asyncio
import signal
from typing import List

from app.config.constants import INSTRUMENT_UNIVERSE
from app.config.settings import settings
from app.data.market_data_service import MarketDataService
from app.scheduler.jobs import job_warmup
from app.scheduler.scheduler import build_scheduler
from app.telegram_bot.bot import build_application
from app.utils.logging import get_logger

log = get_logger(__name__)


async def _warmup_bg() -> None:
    try:
        await job_warmup()
    except Exception:
        log.exception("startup_warmup_failed")


def _live_symbols() -> List[str]:
    return [s for s in INSTRUMENT_UNIVERSE.keys() if s != "INDIAVIX"] + ["INDIAVIX"]


async def _run() -> None:
    log.info("startup", env=settings.app_env)

    tg_app = build_application()
    svc = tg_app.bot_data["service"]

    md = MarketDataService(symbols=_live_symbols())

    sched = build_scheduler(tg_app.bot, svc)

    stop_event = asyncio.Event()

    def _signal(*_):
        log.info("shutdown_signal_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal)
        except NotImplementedError:
            pass        # Windows fallback: rely on KeyboardInterrupt

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling()
    sched.start()
    md_task = asyncio.create_task(md.run(), name="market_data")

    # Warmup historical data on every startup (safe — upserts on conflict)
    log.info("warmup_starting")
    asyncio.create_task(_warmup_bg(), name="warmup")

    log.info("startup_complete")
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("shutdown_begin")
        sched.shutdown(wait=False)
        md_task.cancel()
        try:
            await md.stop()
        except Exception:
            log.exception("market_data_stop_failed")
        try:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        except Exception:
            log.exception("telegram_shutdown_failed")
        try:
            await svc.close()
        except Exception:
            log.exception("service_close_failed")
        log.info("shutdown_complete")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
