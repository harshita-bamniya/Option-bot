from __future__ import annotations

from datetime import date

import pytest

from app.data.options_chain import OptionsChainService


@pytest.mark.asyncio
async def test_fetch_falls_forward_to_next_valid_expiry(monkeypatch) -> None:
    calls: list[date] = []

    async def fake_request(instrument: str, expiry: date) -> dict:
        calls.append(expiry)
        if expiry == date(2026, 4, 24):
            return {"Records": [], "spot": 24350}
        if expiry == date(2026, 4, 28):
            return {
                "spot": 24380,
                "Records": [
                    {
                        "strikePrice": 24400,
                        "CE": {"lastPrice": 120, "impliedVolatility": 14.5, "openInterest": 1000},
                        "PE": {"lastPrice": 110, "impliedVolatility": 15.1, "openInterest": 900},
                    }
                ],
            }
        return {"Records": []}

    monkeypatch.setattr("app.data.options_chain.expiry_candidates", lambda instrument, start, count=4: [date(2026, 4, 28)])
    monkeypatch.setattr("app.data.options_chain.cache.get_json", lambda key: None)
    monkeypatch.setattr("app.data.options_chain.cache.set_json", lambda key, value, ttl_seconds=None: None)

    svc = OptionsChainService(base_url="https://example.test")
    monkeypatch.setattr(svc, "_request_chain_data", fake_request)

    chain = await svc.fetch("NIFTY", expiry=date(2026, 4, 24))
    await svc.close()

    assert chain is not None
    assert chain.expiry == date(2026, 4, 28)
    assert chain.instrument == "NIFTY"
    assert len(chain.quotes) == 2
    assert calls == [date(2026, 4, 24), date(2026, 4, 28)]
