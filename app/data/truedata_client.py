"""TrueData WebSocket client — real-time tick feed for NSE instruments.

Protocol (from TrueData Integration Guide):
  1. Connect to wss://push.truedata.in:<port>?user=X&password=Y
  2. On login-success JSON  → send addsymbol request
  3. On touchline/symbols-added → build symbolID→name map
  4. On each 'trade' message   → yield Tick
  5. Heartbeat every 5-6s     → detect drops, auto-reconnect

Trade array indices (TrueData spec §4.5):
  [0]=SymbolID  [1]=Timestamp  [2]=LTP  [3]=LTQ  [4]=ATP  [5]=TTQ
  [6]=Open  [7]=High  [8]=Low  [9]=PrevClose  [10]=OI  [11]=PrevOI
  [12]=Turnover  [13]=OHL_Tag  [14]=TickSeq  [15]=Bid  [16]=BidQty
  [17]=Ask  [18]=AskQty

Sandbox  → port 8086  (trial credentials supplied in .env)
Production → port 8084
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

import websocket  # websocket-client

from app.config.settings import settings
from app.utils.clock import ist
from app.utils.logging import get_logger

log = get_logger(__name__)

# ── Trade-array field positions ──────────────────────────────────────────────
_IDX_SYM_ID    = 0
_IDX_TS        = 1
_IDX_LTP       = 2
_IDX_LTQ       = 3
_IDX_ATP       = 4
_IDX_VOLUME    = 5
_IDX_OPEN      = 6
_IDX_HIGH      = 7
_IDX_LOW       = 8
_IDX_PREV_CLS  = 9
_IDX_OI        = 10
_IDX_BID       = 15
_IDX_ASK       = 17


@dataclass
class Tick:
    ts: datetime
    instrument: str
    price: float
    volume: int = 0
    bid: Optional[float] = None
    ask: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    oi: Optional[int] = None


class TrueDataClient:
    """Async tick generator backed by TrueData raw WebSocket.

    Usage::
        client = TrueDataClient(["NIFTY-I", "BANKNIFTY-I"])
        async for tick in client.stream_ticks():
            ...
    """

    HEARTBEAT_TIMEOUT = 15          # seconds without heartbeat → reconnect
    RECONNECT_DELAY   = 5           # seconds between reconnect attempts
    MAX_QUEUE_SIZE    = 10_000

    def __init__(self, symbols: List[str]) -> None:
        self.symbols   = symbols
        self._user     = settings.truedata_user
        self._password = settings.truedata_password
        self._host     = settings.truedata_ws_url
        self._port     = settings.truedata_ws_port   # 8086=sandbox, 8084=prod
        self._ws_url   = (
            f"wss://{self._host}:{self._port}"
            f"?user={self._user}&password={self._password}"
        )
        self._queue: asyncio.Queue[Optional[Tick]] = asyncio.Queue(
            maxsize=self.MAX_QUEUE_SIZE
        )
        self._symbol_map: Dict[str, str] = {}       # symbolID → symbol name
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread]   = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_heartbeat = time.monotonic()
        self._running = False

    # ── public interface ─────────────────────────────────────────────────────

    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Async generator yielding live ticks. Reconnects automatically."""
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._start_ws_thread()
        try:
            while self._running:
                try:
                    tick = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                    if tick is None:            # sentinel: reconnect in progress
                        continue
                    yield tick
                except asyncio.TimeoutError:
                    # Check heartbeat watchdog
                    if time.monotonic() - self._last_heartbeat > self.HEARTBEAT_TIMEOUT:
                        log.warning("truedata_heartbeat_timeout_reconnecting")
                        self._restart()
        except asyncio.CancelledError:
            self._running = False
            raise

    async def close(self) -> None:
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    # ── websocket thread ─────────────────────────────────────────────────────

    def _start_ws_thread(self) -> None:
        self._ws = websocket.WebSocketApp(
            self._ws_url,
            on_message=self._on_message,
            on_open=self._on_open,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 20, "ping_timeout": 10},
            daemon=True,
            name="truedata-ws",
        )
        self._thread.start()
        log.info("truedata_ws_thread_started", url=self._ws_url)

    def _restart(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        time.sleep(self.RECONNECT_DELAY)
        self._symbol_map.clear()
        self._start_ws_thread()

    # ── WS callbacks (run in the WS thread) ──────────────────────────────────

    def _on_open(self, ws) -> None:
        log.info("truedata_ws_connected")
        self._last_heartbeat = time.monotonic()

    def _on_error(self, ws, error) -> None:
        log.error("truedata_ws_error", error=str(error))

    def _on_close(self, ws, code, msg) -> None:
        log.warning("truedata_ws_closed", code=code, msg=msg)
        if self._running:
            time.sleep(self.RECONNECT_DELAY)
            self._symbol_map.clear()
            self._start_ws_thread()

    def _on_message(self, ws, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            return

        # ── 1. Heartbeat ────────────────────────────────────────────────────
        if data.get("message") == "HeartBeat":
            self._last_heartbeat = time.monotonic()
            return

        # ── 2. Login success → subscribe symbols ───────────────────────────
        if data.get("success") and data.get("message") == "TrueData Real Time Data Service":
            log.info("truedata_login_success",
                     segments=data.get("segments"),
                     validity=data.get("validity"))
            ws.send(json.dumps({
                "method":  "addsymbol",
                "symbols": self.symbols,
            }))
            return

        # ── 3. Login failure ────────────────────────────────────────────────
        if data.get("success") is False:
            log.error("truedata_login_failed", msg=data.get("message"))
            return

        # ── 4. Touchline / symbols added → build symbol map ─────────────────
        if data.get("message") in ("symbols added", "touchline"):
            for row in data.get("symbollist", []):
                # row: [Symbol, SymbolID, Timestamp, LTP, ...]
                if len(row) >= 2:
                    sym_id   = str(row[1])
                    sym_name = str(row[0])
                    self._symbol_map[sym_id] = sym_name
                    log.debug("truedata_symbol_mapped", sym=sym_name, id=sym_id,
                              ltp=row[3] if len(row) > 3 else None)
            return

        # ── 5. Real-time tick ────────────────────────────────────────────────
        if "trade" in data:
            tick = self._parse_tick(data["trade"])
            if tick and self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._queue.put(tick), self._loop
                    )
                except Exception:
                    pass  # queue full — drop tick

    def _parse_tick(self, t: list) -> Optional[Tick]:
        try:
            sym_id   = str(t[_IDX_SYM_ID])
            sym_name = self._symbol_map.get(sym_id, sym_id)
            ts_raw   = t[_IDX_TS]
            ts = (datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str)
                  else datetime.fromtimestamp(float(ts_raw), tz=ist))
            if ts.tzinfo is None:
                ts = ist.localize(ts)
            return Tick(
                ts         = ts,
                instrument = sym_name,
                price      = _f(t[_IDX_LTP])  or 0.0,
                volume     = int(_f(t[_IDX_LTQ])  or 0),
                bid        = _f(t[_IDX_BID])  if len(t) > _IDX_BID  else None,
                ask        = _f(t[_IDX_ASK])  if len(t) > _IDX_ASK  else None,
                open       = _f(t[_IDX_OPEN]) if len(t) > _IDX_OPEN else None,
                high       = _f(t[_IDX_HIGH]) if len(t) > _IDX_HIGH else None,
                low        = _f(t[_IDX_LOW])  if len(t) > _IDX_LOW  else None,
                oi         = int(_f(t[_IDX_OI]) or 0) if len(t) > _IDX_OI else None,
            )
        except Exception:
            log.exception("truedata_tick_parse_failed", tick=t)
            return None


def _f(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None
