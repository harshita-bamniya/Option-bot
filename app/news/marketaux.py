"""Marketaux REST client — financial news + sentiment every 5 min (spec §13)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import httpx

from app.config.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


class MarketauxClient:

    def __init__(self) -> None:
        self._base = settings.marketaux_url.rstrip("/")
        self._key  = settings.marketaux_key
        self._client = httpx.AsyncClient(timeout=10.0)

    async def all_news(
        self,
        symbols: Optional[List[str]] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
        countries: str = "in",
    ) -> List[dict]:
        """Fetch news articles. Returns raw Marketaux article dicts."""
        if not self._key:
            log.warning("marketaux_key_missing — returning []")
            return []
        params = {
            "api_token": self._key,
            "countries": countries,
            "language": "en",
            "limit": min(limit, 100),
        }
        if symbols:
            # Marketaux uses exchange:ticker format (e.g. NSE:RELIANCE).
            # Index names (NIFTY, BANKNIFTY etc.) are not valid symbols —
            # drop them and rely on country+language filter for Indian news.
            _INDEX_NAMES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
                            "NIFTYIT", "INDIAVIX"}
            valid_syms = [s for s in symbols if s.upper() not in _INDEX_NAMES]
            if valid_syms:
                params["symbols"] = ",".join(valid_syms)
        if since:
            params["published_after"] = since.astimezone().isoformat(timespec="seconds")
        try:
            r = await self._client.get(f"{self._base}/news/all", params=params)
            r.raise_for_status()
            payload = r.json()
            return payload.get("data", [])
        except Exception as e:
            log.warning("marketaux_fetch_failed", error=str(e)[:120])
            return []

    async def close(self) -> None:
        await self._client.aclose()
