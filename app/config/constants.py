"""Fixed domain constants per blueprint (spec.md).

Any weight change MUST go through the learning engine safety gates (spec §9.3),
never by editing this file in production. These are the bootstrap/default values.
"""
from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Dict, List, Tuple


# --- Indicator Group Weights (spec §5.2) — sum to 1.0 ---
GROUP_WEIGHTS: Dict[str, float] = {
    "trend":      0.25,
    "momentum":   0.20,
    "volume":     0.20,
    "volatility": 0.15,
    "structure":  0.15,
    "hybrid":     0.05,
}

# --- MTFS Weights (spec §8.2) — sum to 1.0 ---
MTFS_WEIGHTS: Dict[str, float] = {
    "1d":  0.30,
    "1h":  0.30,
    "15m": 0.25,
    "5m":  0.15,
}

# --- FCS Weights (spec §8.1) — sum to 1.0 ---
FCS_WEIGHTS: Dict[str, float] = {
    "iis":     0.35,
    "mtfs":    0.25,
    "options": 0.20,
    "pattern": 0.10,
    "news":    0.10,
}

# --- FCS decision thresholds (spec §8.1) ---
FCS_HIGH_BUY       = 60
FCS_MOD_BUY        = 35
FCS_MOD_SELL       = -35
FCS_HIGH_SELL      = -60

# --- MTFS thresholds (spec §8.2) ---
MTFS_BULL_THRESHOLD =  0.5
MTFS_BEAR_THRESHOLD = -0.5


class TradeType(str, Enum):
    INTRADAY_OPTIONS   = "Intraday Options"
    SWING_OPTIONS      = "Swing Options"
    POSITIONAL_OPTIONS = "Positional Options"
    POSITIONAL_EQUITY  = "Positional Equity"
    POSITIONAL_FUTURES = "Positional Futures"
    HEDGED             = "Hedged Position"
    NO_TRADE           = "No Trade"


class Direction(str, Enum):
    BUY      = "BUY"
    SELL     = "SELL"
    NO_TRADE = "NO TRADE"


class Regime(str, Enum):
    TRENDING = "TRENDING"
    RANGING  = "RANGING"
    VOLATILE = "VOLATILE"


# --- IV → strategy selector (spec §6.3) ---
# (iv_rank_low, iv_rank_high, state, preferred, avoid)
IV_STRATEGY_BANDS: List[Tuple[float, float, str, List[str], List[str]]] = [
    (0,  30,  "CHEAP OPTIONS",     ["Long Call", "Long Put", "Debit Spreads", "LEAPS"],
                                    ["Selling naked options"]),
    (30, 55,  "FAIR VALUE",        ["Directional trades", "Long options with confirmed setup"],
                                    ["Complex spreads (commission drag)"]),
    (55, 75,  "EXPENSIVE OPTIONS", ["Credit Spreads", "Iron Condor", "Covered Calls", "Short Straddle (if neutral)"],
                                    ["Naked long options"]),
    (75, 101, "EXTREME PREMIUM",   ["Iron Condor", "Wide Iron Fly", "Fully hedged positions"],
                                    ["Any naked directional trade"]),
]


# --- India VIX bands (spec §11.3) ---
# (vix_low, vix_high, interpretation, sl_multiplier, size_multiplier, block_naked_buy)
VIX_BANDS: List[Tuple[float, float, str, float, float, bool]] = [
    (0,   12,   "Extreme complacency — tail risk elevated",      1.00, 1.00, False),
    (12,  16,   "Normal calm — options fairly priced",           1.00, 1.00, False),
    (16,  20,   "Elevated uncertainty",                          1.20, 0.90, False),
    (20,  25,   "HIGH fear — premium very expensive",            1.30, 0.75, True),
    (25,  999,  "PANIC/CRISIS — no intraday options",            1.50, 0.50, True),
]


# --- Hard Risk Rules (spec §8.3) — each key is programmatically enforced ---
HARD_RISK_RULES = {
    "max_sl_distance_pct":          2.0,   # SL distance > 2% of instrument price → block
    "min_rr_ratio":                 2.0,   # RR < 2:1 → block
    "event_blackout_minutes":       30,    # HIGH-impact event within N min → block
    "atr_extreme_percentile":       95,    # ATR in top 5% of 1Y → block
    "iv_rank_buy_block":            85,    # IV Rank > 85 on BUY → block
    "daily_loss_limit_pct":         3.0,   # Daily loss ≥ 3% of capital → suspend
    # Rules enforced elsewhere:
    #  - Circuit breaker on Nifty → halt all
    #  - Both Daily+1H contradict signal → block
}


# --- Indian Trading Sessions (spec §10.3) — IST times ---
TRADING_SESSIONS = [
    ("Opening",         time(9, 15),  time(9, 45)),
    ("Morning Trend",   time(9, 45),  time(11, 30)),
    ("Midday Chop",     time(11, 30), time(13, 30)),
    ("Afternoon Setup", time(13, 30), time(14, 30)),
    ("Power Hour",      time(14, 30), time(15, 30)),
]


# --- Instrument Universe (spec §11.1) ---
INSTRUMENT_UNIVERSE: Dict[str, Dict] = {
    "NIFTY":          {"type": "index",        "exchange": "NSE", "options": True,  "lot_size": 25,  "weekly": True},
    "BANKNIFTY":      {"type": "index",        "exchange": "NSE", "options": True,  "lot_size": 15,  "weekly": True},
    "FINNIFTY":       {"type": "index",        "exchange": "NSE", "options": True,  "lot_size": 25,  "weekly": False},
    "MIDCPNIFTY":     {"type": "index",        "exchange": "NSE", "options": True,  "lot_size": 50,  "weekly": True},
    "NIFTYIT":        {"type": "sector_index", "exchange": "NSE", "options": True,  "lot_size": 75,  "weekly": False},
    "INDIAVIX":       {"type": "index",        "exchange": "NSE", "options": False, "lot_size": None, "weekly": False},
}


# --- Timeframe definitions (spec §8.2) ---
TIMEFRAMES = ("5m", "15m", "1h", "1d")


# --- Expiry-day cutoffs (spec §10.4) ---
EXPIRY_OTM_BUY_CUTOFF = time(10, 0)   # No OTM buying after 10:00 on expiry Thursday
EXPIRY_SELL_ONLY_FROM = time(11, 0)   # Only premium selling from 11:00
