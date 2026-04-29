"""Options chain service — fetch + snapshot OI, premium, IV, Greeks per strike.

TrueData historical+analytics API exposes options chain endpoints. We normalize
into rows for the `options_chain` hypertable and Redis cache.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

import httpx

from app.config.settings import settings
from app.data.cache import cache, k_options_chain
from app.data.symbols import canonicalize_instrument, truedata_options_chain_symbol
from app.utils.clock import now_ist
from app.utils.expiry import expiry_candidates
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class OptionQuote:
    strike: float
    option_type: str          # 'CE' | 'PE'
    ltp: Optional[float]
    iv: Optional[float]
    oi: Optional[int]
    oi_change: Optional[int]
    volume: Optional[int]
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega:  Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class OptionsChain:
    instrument: str
    expiry: date
    spot: float
    ts: datetime
    quotes: List[OptionQuote]

    def ce(self) -> List[OptionQuote]:
        return [q for q in self.quotes if q.option_type == "CE"]

    def pe(self) -> List[OptionQuote]:
        return [q for q in self.quotes if q.option_type == "PE"]

    def atm_strike(self) -> Optional[float]:
        if not self.quotes:
            return None
        strikes = sorted({q.strike for q in self.quotes})
        return min(strikes, key=lambda s: abs(s - self.spot))


class OptionsChainService:
    """Fetches options chain snapshots.

    Primary source: TrueData (requires auth). Falls back to any compatible REST
    endpoint the deployment provides. The implementation is intentionally
    pluggable so the same service can wrap NSE public feeds for testing.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        # TrueData option chain is on api.truedata.in (not history.)
        self._base = base_url or settings.truedata_api_url
        self._client = httpx.AsyncClient(timeout=10.0)

    async def fetch(self, instrument: str, expiry: Optional[date] = None) -> Optional[OptionsChain]:
        instrument = canonicalize_instrument(instrument)
        requested_expiry = expiry
        candidate_expiries = _dedupe_expiries(
            [requested_expiry] if requested_expiry else []
            + expiry_candidates(instrument, start=now_ist().date(), count=4)
        )

        for candidate in candidate_expiries:
            cache_key = k_options_chain(instrument, candidate.isoformat())
            cached = cache.get_json(cache_key)
            if cached:
                return _deserialize(cached)

            try:
                data = await self._request_chain_data(instrument, candidate)
            except Exception:
                log.exception("options_chain_fetch_failed", instrument=instrument, expiry=str(candidate))
                continue

            chain = _parse_truedata(instrument, candidate, data)
            if chain is None:
                log.warning(
                    "options_chain_empty_for_expiry",
                    instrument=instrument,
                    expiry=str(candidate),
                    requested_expiry=str(requested_expiry) if requested_expiry else None,
                )
                continue

            if requested_expiry and candidate != requested_expiry:
                log.warning(
                    "options_chain_expiry_corrected",
                    instrument=instrument,
                    requested_expiry=str(requested_expiry),
                    resolved_expiry=str(candidate),
                )
            cache.set_json(cache_key, _serialize(chain), ttl_seconds=120)
            return chain
        return None

    async def _request_chain_data(self, instrument: str, expiry: date) -> dict:
        # TrueData option chain endpoint — expiry as YYYYMMDD (e.g. 20250424)
        url = f"{self._base}/getOptionChain"
        params = {
            "user": settings.truedata_user,
            "password": settings.truedata_password,
            "symbol": truedata_options_chain_symbol(instrument),
            "expiry": expiry.strftime("%Y%m%d"),
        }
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._client.aclose()


# ---------- serialization helpers ----------

def _serialize(chain: OptionsChain) -> dict:
    return {
        "instrument": chain.instrument,
        "expiry": chain.expiry.isoformat(),
        "spot": chain.spot,
        "ts": chain.ts.isoformat(),
        "quotes": [q.__dict__ for q in chain.quotes],
    }


def _deserialize(d: dict) -> OptionsChain:
    return OptionsChain(
        instrument=d["instrument"],
        expiry=date.fromisoformat(d["expiry"]),
        spot=float(d["spot"]),
        ts=datetime.fromisoformat(d["ts"]),
        quotes=[OptionQuote(**q) for q in d["quotes"]],
    )


def _parse_truedata(instrument: str, expiry: date, data: dict) -> Optional[OptionsChain]:
    """Parse TrueData's option-chain JSON into an OptionsChain."""
    records = data.get("Records") or data.get("records") or []
    if not records:
        return None
    spot = float(data.get("spot") or data.get("underlyingValue") or 0.0)
    quotes: List[OptionQuote] = []
    for r in records:
        strike = float(r.get("strikePrice") or r.get("strike") or 0.0)
        for side_key, side in (("CE", "CE"), ("PE", "PE")):
            leg = r.get(side_key) or {}
            if not leg:
                continue
            quotes.append(OptionQuote(
                strike=strike,
                option_type=side,
                ltp=_f(leg.get("lastPrice") or leg.get("ltp")),
                iv=_f(leg.get("impliedVolatility") or leg.get("iv")),
                oi=_i(leg.get("openInterest") or leg.get("oi")),
                oi_change=_i(leg.get("changeinOpenInterest") or leg.get("oi_change")),
                volume=_i(leg.get("totalTradedVolume") or leg.get("volume")),
                delta=_f(leg.get("delta")),
                gamma=_f(leg.get("gamma")),
                theta=_f(leg.get("theta")),
                vega=_f(leg.get("vega")),
                bid=_f(leg.get("bidPrice") or leg.get("bid")),
                ask=_f(leg.get("askPrice") or leg.get("ask")),
            ))
    return OptionsChain(instrument=instrument, expiry=expiry, spot=spot,
                        ts=now_ist(), quotes=quotes)


def _dedupe_expiries(expiries: List[Optional[date]]) -> List[date]:
    seen: set[date] = set()
    ordered: List[date] = []
    for expiry in expiries:
        if expiry is None or expiry in seen:
            continue
        seen.add(expiry)
        ordered.append(expiry)
    return ordered


def _f(v):
    try: return float(v) if v not in (None, "", "-") else None
    except (TypeError, ValueError): return None


def _i(v):
    try: return int(v) if v not in (None, "", "-") else None
    except (TypeError, ValueError): return None
