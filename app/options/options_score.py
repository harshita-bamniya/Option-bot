"""Options Score (feeds FCS with 20% weight — spec §8.1).

Blends: PCR (contrarian), IV Rank alignment, Max-Pain gravity, GEX regime,
IV skew (fear gauge). Output scale: [-100, +100].
"""
from __future__ import annotations

from typing import Optional

from app.data.options_chain import OptionsChain
from app.options.metrics import pcr as compute_pcr, max_pain, iv_skew, gamma_exposure


def options_score(
    chain: Optional[OptionsChain],
    iv_rank: float,
    direction_hint: int,         # +1 bullish bias so far, -1 bearish, 0 neutral
    dte: int,
) -> tuple[float, dict]:
    """Return (score [-100,+100], details)."""
    if chain is None:
        return 0.0, {"reason": "no_chain"}

    details: dict = {}
    score = 0.0
    weight_total = 0.0

    # --- PCR (contrarian) ---
    pr = compute_pcr(chain)
    details["pcr"] = pr
    if pr > 0:
        # PCR 1.0 = neutral; >1.2 = bearish positioning = contrarian bullish
        pcr_bias = 0.0
        if pr >= 1.3:
            pcr_bias = +0.5
        elif pr >= 1.1:
            pcr_bias = +0.2
        elif pr <= 0.7:
            pcr_bias = -0.5
        elif pr <= 0.9:
            pcr_bias = -0.2
        score += pcr_bias * 30  # scaled contribution
        weight_total += 30

    # --- IV Rank alignment (low IV favours BUY, high IV favours SELL) ---
    if direction_hint != 0:
        if direction_hint > 0 and iv_rank < 40:
            score += 15
        elif direction_hint > 0 and iv_rank > 75:
            score -= 15      # buying extremely expensive premium is a red flag
        elif direction_hint < 0 and iv_rank > 65:
            score += 10      # selling overpriced premium on bearish bias is favorable
        weight_total += 15

    # --- Max-Pain gravity near expiry ---
    try:
        mp = max_pain(chain)
        details["max_pain"] = mp
        spot = chain.spot
        dist_pct = (mp - spot) / spot * 100 if spot else 0
        details["max_pain_dist_pct"] = dist_pct
        if dte <= 3 and abs(dist_pct) > 0.4:
            # Price gravitates toward max pain near expiry
            pull = 1 if mp > spot else -1
            score += pull * 15 * (1 - dte / 3)
        weight_total += 15
    except Exception:
        pass

    # --- IV Skew (fear gauge) ---
    try:
        skew = iv_skew(chain)
        details["iv_skew"] = skew
        if skew > 0.03:
            # Strong put skew = fear — mildly bearish short-term, bullish contrarian
            score -= 5
        elif skew < -0.03:
            score += 5
        weight_total += 10
    except Exception:
        pass

    # --- GEX (pin / release) ---
    try:
        gex_map = gamma_exposure(chain)
        net_gex = sum(gex_map.values())
        details["net_gex"] = net_gex
        # High positive net GEX = pinning → reduces conviction magnitude
        # High negative net GEX = explosive moves likely → boost conviction
        if abs(net_gex) > 0:
            # Sign convention above: +ve net_gex here means dealers long gamma → stable
            if net_gex > 0:
                score *= 0.9
            else:
                score *= 1.1
    except Exception:
        pass

    # Clamp to [-100, 100]
    score = max(-100.0, min(100.0, score))
    details["score"] = score
    return score, details
