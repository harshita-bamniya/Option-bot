"""Options strategy selector (spec §6.3).

Given (direction, iv_rank, days-to-expiry, vix_band), return a dict describing
the preferred strategy + rationale + what to avoid.
"""
from __future__ import annotations

from typing import Dict

from app.config.constants import IV_STRATEGY_BANDS


def iv_band(iv_rank: float) -> tuple[str, list[str], list[str]]:
    for lo, hi, state, prefer, avoid in IV_STRATEGY_BANDS:
        if lo <= iv_rank < hi:
            return state, prefer, avoid
    return IV_STRATEGY_BANDS[-1][2], IV_STRATEGY_BANDS[-1][3], IV_STRATEGY_BANDS[-1][4]


def select_strategy(
    *,
    direction: str,                 # 'BUY' | 'SELL' | 'NO TRADE'
    iv_rank: float,
    days_to_expiry: int,
    vix: float | None = None,
    pcr: float | None = None,
) -> Dict:
    state, prefer, avoid = iv_band(iv_rank)

    strategy: str
    rationale: list[str] = [f"IV Rank {iv_rank:.0f} → {state}."]

    if direction == "NO TRADE":
        strategy = "STAND ASIDE"
        rationale.append("Signal conviction below threshold.")
    elif state == "CHEAP OPTIONS":
        strategy = "Long Call" if direction == "BUY" else "Long Put"
        rationale.append("Premium cheap — favor long options.")
    elif state == "FAIR VALUE":
        if days_to_expiry <= 3 and direction == "BUY":
            strategy = "Debit Call Spread"   # theta cushion
            rationale.append("Short DTE + BUY → spread beats naked long to offset theta.")
        else:
            strategy = "Long Call" if direction == "BUY" else "Long Put"
            rationale.append("Fair-value IV — directional trade valid.")
    elif state == "EXPENSIVE OPTIONS":
        strategy = "Bull Put Spread" if direction == "BUY" else "Bear Call Spread"
        rationale.append("IV rich — sell premium via defined-risk credit spread.")
    else:  # EXTREME PREMIUM
        strategy = "Iron Condor" if direction == "NO TRADE" else (
            "Bull Put Spread (wide)" if direction == "BUY" else "Bear Call Spread (wide)")
        rationale.append("Extreme IV — IV crush risk high; stay hedged.")

    if vix is not None and vix > 20 and state in ("CHEAP OPTIONS", "FAIR VALUE"):
        rationale.append(f"VIX {vix:.1f} elevated → consider reducing size 10–25%.")

    if pcr is not None:
        if pcr > 1.3:
            rationale.append(f"PCR {pcr:.2f} — excess bearish positioning (contrarian bullish tilt).")
        elif pcr < 0.7:
            rationale.append(f"PCR {pcr:.2f} — euphoria; be cautious of fading.")

    return {
        "strategy": strategy,
        "iv_state": state,
        "preferred": prefer,
        "avoid": avoid,
        "rationale": rationale,
    }
