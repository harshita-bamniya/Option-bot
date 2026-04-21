"""Black-Scholes pricing, Greeks, and IV inversion sanity checks."""
from __future__ import annotations

from app.options.black_scholes import bs_greeks, bs_price, implied_vol


def test_atm_call_price_is_positive() -> None:
    p = bs_price(S=100, K=100, T=30 / 365, r=0.07, sigma=0.20, option_type="C")
    assert 1.0 < p < 5.0


def test_call_put_parity() -> None:
    S, K, T, r, sigma = 100, 100, 30 / 365, 0.07, 0.20
    c = bs_price(S, K, T, r, sigma, "C")
    p = bs_price(S, K, T, r, sigma, "P")
    # C - P = S - K e^-rT
    import math
    assert abs((c - p) - (S - K * math.exp(-r * T))) < 1e-6


def test_greeks_in_expected_ranges() -> None:
    g = bs_greeks(S=100, K=100, T=30 / 365, r=0.07, sigma=0.20, option_type="C")
    assert 0.45 < g["delta"] < 0.65
    assert g["gamma"] > 0
    assert g["theta"] < 0
    assert g["vega"] > 0


def test_iv_inversion_recovers_input() -> None:
    sigma_in = 0.22
    p = bs_price(S=100, K=100, T=45 / 365, r=0.07, sigma=sigma_in, option_type="C")
    sigma_out = implied_vol(p, S=100, K=100, T=45 / 365, option_type="C")
    assert sigma_out is not None
    assert abs(sigma_out - sigma_in) < 1e-3
