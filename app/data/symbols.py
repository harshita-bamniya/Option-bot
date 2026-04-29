"""Canonical instrument and TrueData symbol mappings."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TrueDataSymbolSpec:
    internal: str
    websocket: str
    historical: str
    options_chain: str | None = None
    aliases: tuple[str, ...] = ()


_SPECS: dict[str, TrueDataSymbolSpec] = {
    "NIFTY": TrueDataSymbolSpec(
        internal="NIFTY",
        websocket="NIFTY-I",
        historical="NIFTY-I",
        options_chain="NIFTY",
    ),
    "BANKNIFTY": TrueDataSymbolSpec(
        internal="BANKNIFTY",
        websocket="BANKNIFTY-I",
        historical="BANKNIFTY-I",
        options_chain="BANKNIFTY",
    ),
    "FINNIFTY": TrueDataSymbolSpec(
        internal="FINNIFTY",
        websocket="FINNIFTY-I",
        historical="FINNIFTY-I",
        options_chain="FINNIFTY",
    ),
    "MIDCPNIFTY": TrueDataSymbolSpec(
        internal="MIDCPNIFTY",
        websocket="MIDCPNIFTY-I",
        historical="MIDCPNIFTY-I",
        options_chain="MIDCPNIFTY",
    ),
    "NIFTYIT": TrueDataSymbolSpec(
        internal="NIFTYIT",
        websocket="NIFTYIT-I",
        historical="NIFTYIT-I",
        options_chain="NIFTYIT",
        aliases=("NIFTY IT",),
    ),
    "INDIAVIX": TrueDataSymbolSpec(
        internal="INDIAVIX",
        websocket="INDIA VIX",
        historical="INDIA VIX",
        options_chain=None,
        aliases=("INDIA VIX",),
    ),
}


def _normalize_symbol(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value or "").upper()


_ALIASES: dict[str, str] = {}
for spec in _SPECS.values():
    candidates = {
        spec.internal,
        spec.websocket,
        spec.historical,
        *(spec.aliases or ()),
    }
    if spec.options_chain:
        candidates.add(spec.options_chain)
    for candidate in candidates:
        _ALIASES[_normalize_symbol(candidate)] = spec.internal


def canonicalize_instrument(symbol: str) -> str:
    """Return the internal canonical symbol used by the application."""
    normalized = _normalize_symbol(symbol)
    return _ALIASES.get(normalized, (symbol or "").strip().upper())


def truedata_ws_symbol(symbol: str) -> str:
    canonical = canonicalize_instrument(symbol)
    return _SPECS.get(canonical, TrueDataSymbolSpec(canonical, canonical, canonical, canonical)).websocket


def truedata_historical_symbol(symbol: str) -> str:
    canonical = canonicalize_instrument(symbol)
    return _SPECS.get(canonical, TrueDataSymbolSpec(canonical, canonical, canonical, canonical)).historical


def truedata_options_chain_symbol(symbol: str) -> str:
    canonical = canonicalize_instrument(symbol)
    spec = _SPECS.get(canonical)
    if spec and spec.options_chain:
        return spec.options_chain
    return canonical


def truedata_to_internal_symbol(symbol: str) -> str:
    """Map a symbol seen on TrueData back to our internal canonical name."""
    return canonicalize_instrument(symbol)
