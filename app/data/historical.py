"""TrueData REST Historical Data client (spec §5 of TrueData Integration Guide).

Endpoints:
    Auth   → POST https://auth.truedata.in/token  (bearer, TTL 3600s)
    Bars   → GET  https://history.truedata.in/getbars
    LastN  → GET  https://history.truedata.in/getlastnbars
    Ticks  → GET  https://history.truedata.in/getticks

Trial limits: 15 days bar history, 2 days tick history, 5 req/s, 300 req/min.
Bar format param: from/to as "YYMMDDTHH:MM:SS" e.g. "250421T09:15:00"
"""
from __future__ import annotations

import io
import time
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd

from app.config.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

_AUTH_URL    = "https://auth.truedata.in/token"
_BARS_URL    = "https://history.truedata.in/getbars"
_LASTN_URL   = "https://history.truedata.in/getlastnbars"
_TICKS_URL   = "https://history.truedata.in/getticks"

# Interval map: our internal TF names → TrueData interval strings
TF_TO_TD: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "1h":  "60min",
    "1d":  "eod",
}


class TrueDataHistorical:
    """Token-cached REST client for TrueData historical endpoints."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expiry: float  = 0.0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ── auth ─────────────────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        r = await self._client.post(
            _AUTH_URL,
            data={
                "username":   settings.truedata_user,
                "password":   settings.truedata_password,
                "grant_type": "password",
            },
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        self._token_expiry = time.time() + 3600
        log.info("truedata_auth_token_refreshed")
        return self._token

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ── bar history ──────────────────────────────────────────────────────────

    async def get_bars(
        self,
        symbol: str,
        from_dt: datetime,
        to_dt: datetime,
        timeframe: str = "5m",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars; returns DataFrame indexed by timestamp."""
        interval = TF_TO_TD.get(timeframe, "5min")
        fmt = "%y%m%dT%H:%M:%S"
        token = await self._get_token()
        r = await self._client.get(
            _BARS_URL,
            params={
                "symbol":   symbol,
                "from":     from_dt.strftime(fmt),
                "to":       to_dt.strftime(fmt),
                "interval": interval,
                "response": "csv",
            },
            headers=self._headers(token),
        )
        r.raise_for_status()
        return _parse_bar_csv(r.text)

    async def get_last_n_bars(
        self,
        symbol: str,
        n: int = 200,
        timeframe: str = "5m",
    ) -> pd.DataFrame:
        """Convenience: last N bars (max 200 per request per TrueData limits)."""
        interval = TF_TO_TD.get(timeframe, "5min")
        token = await self._get_token()
        r = await self._client.get(
            _LASTN_URL,
            params={
                "symbol":   symbol,
                "nbars":    min(n, 200),
                "interval": interval,
                "bidask":   0,
                "response": "csv",
            },
            headers=self._headers(token),
        )
        r.raise_for_status()
        return _parse_bar_csv(r.text)

    async def get_ticks(
        self,
        symbol: str,
        from_dt: datetime,
        to_dt: datetime,
        bidask: bool = False,
    ) -> pd.DataFrame:
        fmt = "%y%m%dT%H:%M:%S"
        token = await self._get_token()
        r = await self._client.get(
            _TICKS_URL,
            params={
                "symbol":   symbol,
                "from":     from_dt.strftime(fmt),
                "to":       to_dt.strftime(fmt),
                "bidask":   1 if bidask else 0,
                "response": "csv",
            },
            headers=self._headers(token),
        )
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        if not df.empty and "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_bar_csv(text: str) -> pd.DataFrame:
    """Parse TrueData bar CSV → clean DataFrame with standard column names."""
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    # Normalise column names — TrueData uses different cases
    df.columns = [c.lower().strip() for c in df.columns]
    col_map = {}
    for c in df.columns:
        if "time" in c or c == "date":
            col_map[c] = "ts"
        elif c in ("o", "open"):
            col_map[c] = "open"
        elif c in ("h", "high"):
            col_map[c] = "high"
        elif c in ("l", "low"):
            col_map[c] = "low"
        elif c in ("c", "close"):
            col_map[c] = "close"
        elif c in ("v", "vol", "volume"):
            col_map[c] = "volume"
    df = df.rename(columns=col_map)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
