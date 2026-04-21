"""MarketDataService — orchestrates tick stream → candles → DB + cache.

This is the single place the rest of the system should request OHLCV history
from. It prefers TrueData for live data, DB for historical backfill, and keeps
a warm window in Redis for sub-second access.
"""
from __future__ import annotations

import asyncio
from typing import List

import pandas as pd

from app.data.cache import cache, k_candle
from app.data.candles import CandleBuilder, TIMEFRAME_SECONDS
from app.data.truedata_client import TrueDataClient
from app.db.repositories import MarketDataRepo
from app.utils.logging import get_logger

log = get_logger(__name__)


class MarketDataService:

    def __init__(self, symbols: List[str]) -> None:
        self.symbols = symbols
        self._batch: list[dict] = []
        self._builder = CandleBuilder(
            timeframes=("1m", "5m", "15m", "1h", "1d"),
            flush_cb=self._on_candle_close,
        )
        self._client = TrueDataClient(symbols)
        self._flush_task: asyncio.Task | None = None

    # ---- history accessors (used by indicator engine / scoring) ----

    def recent_candles(self, instrument: str, timeframe: str, lookback: int = 500) -> pd.DataFrame:
        """Return the most recent N candles, indexed by ts."""
        df = MarketDataRepo.recent(instrument, timeframe, limit=lookback)
        return df

    # ---- live pipeline ----

    def _on_candle_close(self, row: dict) -> None:
        """Invoked by CandleBuilder when a candle rolls forward."""
        self._batch.append(row)
        # Warm Redis with latest candle
        cache.set_json(
            k_candle(row["instrument"], row["timeframe"]),
            {"ts": row["ts"].isoformat(), "o": row["open"], "h": row["high"],
             "l": row["low"], "c": row["close"], "v": row["volume"]},
            ttl_seconds=max(TIMEFRAME_SECONDS[row["timeframe"]] * 3, 120),
        )

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            if not self._batch:
                continue
            batch, self._batch = self._batch, []
            try:
                MarketDataRepo.insert_candles(batch)
                log.debug("candles_flushed", n=len(batch))
            except Exception:
                log.exception("candle_flush_db_failed", n=len(batch))
                # Put back for retry (bounded)
                if len(self._batch) < 5000:
                    self._batch[:0] = batch

    async def run(self) -> None:
        """Main loop — consumes TrueData ticks, builds candles, flushes to DB."""
        self._flush_task = asyncio.create_task(self._flush_loop())
        async for tick in self._client.stream_ticks():
            self._builder.on_tick(tick.instrument, tick.ts, tick.price, tick.volume)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        self._builder.flush_all()
        if self._batch:
            MarketDataRepo.insert_candles(self._batch)
            self._batch.clear()
        await self._client.close()
