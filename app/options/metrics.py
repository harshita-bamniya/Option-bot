"""Options-chain derived metrics: PCR, Max Pain, Gamma Exposure, IV Skew,
OI Buildup (spec §6.4).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from app.data.options_chain import OptionsChain, OptionQuote


# --- PCR ---

def pcr(chain: OptionsChain) -> float:
    call_oi = sum(q.oi or 0 for q in chain.ce())
    put_oi  = sum(q.oi or 0 for q in chain.pe())
    if call_oi == 0:
        return 0.0
    return put_oi / call_oi


# --- Max Pain ---

def _intrinsic(option_type: str, strike: float, expiry_spot: float) -> float:
    if option_type == "CE":
        return max(0.0, expiry_spot - strike)
    return max(0.0, strike - expiry_spot)


def max_pain(chain: OptionsChain) -> float:
    """Strike where total OI-weighted intrinsic value paid to buyers is MINIMIZED
    (= option writers' pain is maximized). Standard interpretation.
    """
    strikes = sorted({q.strike for q in chain.quotes})
    if not strikes:
        return chain.spot
    min_pain_strike, min_pain = strikes[0], float("inf")
    for test_spot in strikes:
        total = 0.0
        for q in chain.quotes:
            if q.oi is None:
                continue
            total += _intrinsic(q.option_type, q.strike, test_spot) * q.oi
        if total < min_pain:
            min_pain = total
            min_pain_strike = test_spot
    return float(min_pain_strike)


# --- Gamma Exposure ---

def gamma_exposure(chain: OptionsChain, contract_multiplier: int = 100) -> Dict[float, float]:
    """Simple dealer-neutral GEX per strike = gamma × OI × multiplier × spot^2 × 0.01.
    Positive sum = pinning (price drawn toward strike).
    """
    out: Dict[float, float] = {}
    for q in chain.quotes:
        if q.gamma is None or q.oi is None:
            continue
        sign = 1 if q.option_type == "CE" else -1
        out[q.strike] = out.get(q.strike, 0.0) + sign * q.gamma * q.oi * contract_multiplier * chain.spot ** 2 * 0.01
    return out


# --- IV Skew ---

def iv_skew(chain: OptionsChain) -> float:
    """OTM put IV − OTM call IV, 1σ-ish offset from ATM.

    Positive = fear (puts paying up). Negative = call skew (greed / short squeeze).
    """
    atm = chain.atm_strike()
    if atm is None:
        return 0.0
    # Take the strike ~5% OTM on each side
    otm_put = min(chain.pe(), key=lambda q: abs(q.strike - atm * 0.95), default=None)
    otm_call = min(chain.ce(), key=lambda q: abs(q.strike - atm * 1.05), default=None)
    if not otm_put or not otm_call or otm_put.iv is None or otm_call.iv is None:
        return 0.0
    return float(otm_put.iv - otm_call.iv)


# --- OI Buildup classification ---

def oi_buildup(prev: OptionQuote, curr: OptionQuote) -> str:
    """Classify OI change + price change into the standard 4 regimes."""
    if curr.oi is None or prev.oi is None or curr.ltp is None or prev.ltp is None:
        return "UNKNOWN"
    d_oi = curr.oi - prev.oi
    d_price = curr.ltp - prev.ltp
    if d_oi > 0 and d_price > 0:
        return "LONG BUILDUP"
    if d_oi > 0 and d_price < 0:
        return "SHORT BUILDUP"
    if d_oi < 0 and d_price > 0:
        return "SHORT COVERING"
    if d_oi < 0 and d_price < 0:
        return "LONG UNWINDING"
    return "UNCHANGED"


# --- Max call/put wall (for Telegram heat-map alerts — spec ENH-002) ---

def walls(chain: OptionsChain, top_n: int = 3) -> dict:
    ce = sorted(chain.ce(), key=lambda q: q.oi or 0, reverse=True)[:top_n]
    pe = sorted(chain.pe(), key=lambda q: q.oi or 0, reverse=True)[:top_n]
    return {
        "call_walls": [(q.strike, q.oi or 0) for q in ce],
        "put_walls":  [(q.strike, q.oi or 0) for q in pe],
    }
