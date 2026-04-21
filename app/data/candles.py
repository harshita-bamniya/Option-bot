"""OHLCV candle builder — aggregates 1-min ticks/bars into higher timeframes.

Tick input: {ts, instrument, price, volume}
Output: candles per timeframe flushed to MarketDataRepo + Redis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from app.utils.clock import ist
from app.utils.logging import get_logger

log = get_logger(__name__)


TIMEFRAME_SECONDS: Dict[str, int] = {
    "1m":  60,
    "5m":  5 * 60,
    "15m": 15 * 60,
    "1h":  60 * 60,
    "1d":  24 * 60 * 60,
}


@dataclass
class Candle:
    ts: datetime      # candle open time (IST, aware)
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    def update(self, price: float, vol: int = 0) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += vol

    def as_dict(self, instrument: str, timeframe: str) -> dict:
        return {
            "ts": self.ts, "instrument": instrument, "timeframe": timeframe,
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
        }


def _floor_to_tf(dt: datetime, tf_seconds: int) -> datetime:
    """Floor dt to the start of its timeframe bucket (IST-aware)."""
    if dt.tzinfo is None:
        dt = ist.localize(dt)
    else:
        dt = dt.astimezone(ist)
    if tf_seconds >= 86400:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    epoch = int(dt.timestamp())
    bucket = epoch - (epoch % tf_seconds)
    return datetime.fromtimestamp(bucket, tz=ist)


@dataclass
class CandleBuilder:
    """Builds multi-timeframe candles from tick stream.

    flush_cb(candle_dict) is invoked whenever a candle rolls to the next bucket.
    """
    timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h", "1d")
    flush_cb: Optional[Callable[[dict], None]] = None
    _live: Dict[tuple[str, str], Candle] = field(default_factory=dict)

    def on_tick(self, instrument: str, ts: datetime, price: float, volume: int = 0) -> None:
        for tf in self.timeframes:
            tf_sec = TIMEFRAME_SECONDS[tf]
            bucket_start = _floor_to_tf(ts, tf_sec)
            key = (instrument, tf)
            live = self._live.get(key)
            if live is None or live.ts != bucket_start:
                # Flush previous
                if live is not None and self.flush_cb:
                    try:
                        self.flush_cb(live.as_dict(instrument, tf))
                    except Exception:  # pragma: no cover — defensive
                        log.exception("candle_flush_failed", instrument=instrument, tf=tf)
                self._live[key] = Candle(ts=bucket_start, open=price, high=price,
                                         low=price, close=price, volume=volume)
            else:
                live.update(price, volume)

    def flush_all(self) -> None:
        """Flush every live candle — call on shutdown/EOD."""
        if not self.flush_cb:
            return
        for (instrument, tf), c in list(self._live.items()):
            try:
                self.flush_cb(c.as_dict(instrument, tf))
            except Exception:
                log.exception("flush_all_failed", instrument=instrument, tf=tf)
        self._live.clear()
