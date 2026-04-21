"""Black–Scholes pricing, Greeks, and implied volatility via Brent's method.

Used to:
- Verify Greeks from broker feed (reject outliers)
- Compute IV for a quoted premium when broker does not provide IV
- Stress-test positions (e.g. theta cost at T-1 day)
"""
from __future__ import annotations

from math import exp, log, sqrt
from typing import Literal

from scipy.optimize import brentq
from scipy.stats import norm

OptionType = Literal["C", "P"]

# Risk-free rate proxy — India 10Y G-Sec yield. Override via settings for production.
DEFAULT_R = 0.07


def _d1(S, K, T, r, sigma, q=0.0):
    return (log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt(T))


def _d2(d1, sigma, T):
    return d1 - sigma * sqrt(T)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: OptionType = "C", q: float = 0.0) -> float:
    """Black-Scholes price (continuous dividend yield q)."""
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if option_type == "C" else (K - S))
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(d1, sigma, T)
    if option_type == "C":
        return S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
    else:
        return K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float,
              option_type: OptionType = "C", q: float = 0.0) -> dict:
    """Return dict with delta, gamma, theta (per day), vega (per 1% IV), rho."""
    if T <= 0 or sigma <= 0:
        return dict(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)
    d1 = _d1(S, K, T, r, sigma, q)
    d2 = _d2(d1, sigma, T)
    pdf_d1 = norm.pdf(d1)

    if option_type == "C":
        delta = exp(-q * T) * norm.cdf(d1)
        theta_yr = (-S * pdf_d1 * sigma * exp(-q * T) / (2 * sqrt(T))
                    - r * K * exp(-r * T) * norm.cdf(d2)
                    + q * S * exp(-q * T) * norm.cdf(d1))
        rho = K * T * exp(-r * T) * norm.cdf(d2) / 100
    else:
        delta = -exp(-q * T) * norm.cdf(-d1)
        theta_yr = (-S * pdf_d1 * sigma * exp(-q * T) / (2 * sqrt(T))
                    + r * K * exp(-r * T) * norm.cdf(-d2)
                    - q * S * exp(-q * T) * norm.cdf(-d1))
        rho = -K * T * exp(-r * T) * norm.cdf(-d2) / 100

    gamma = exp(-q * T) * pdf_d1 / (S * sigma * sqrt(T))
    vega  = S * exp(-q * T) * pdf_d1 * sqrt(T) / 100   # per 1% IV change
    theta = theta_yr / 365.0

    return dict(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def implied_vol(price: float, S: float, K: float, T: float, r: float = DEFAULT_R,
                option_type: OptionType = "C", q: float = 0.0,
                lo: float = 1e-4, hi: float = 5.0) -> float | None:
    """Solve BS equation for sigma given the observed option price. Returns IV or None."""
    if price <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (S - K) if option_type == "C" else (K - S))
    if price < intrinsic - 1e-6:
        return None

    def objective(sigma: float) -> float:
        return bs_price(S, K, T, r, sigma, option_type, q) - price

    try:
        return float(brentq(objective, lo, hi, maxiter=100, xtol=1e-6))
    except ValueError:
        return None
