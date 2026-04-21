"""IST-aware clock + NSE market session helpers."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

import pytz

from app.config.constants import TRADING_SESSIONS

ist = pytz.timezone("Asia/Kolkata")

NSE_OPEN  = time(9, 15)
NSE_CLOSE = time(15, 30)


def now_ist() -> datetime:
    return datetime.now(tz=ist)


def is_market_open(dt: Optional[datetime] = None) -> bool:
    dt = dt or now_ist()
    if dt.weekday() >= 5:          # Sat/Sun
        return False
    t = dt.time()
    return NSE_OPEN <= t <= NSE_CLOSE


def current_session(dt: Optional[datetime] = None) -> str:
    dt = dt or now_ist()
    t = dt.time()
    for name, start, end in TRADING_SESSIONS:
        if start <= t < end:
            return name
    if t < NSE_OPEN:
        return "Pre-Market"
    return "Post-Close"


def next_weekday(dt: datetime, weekday: int) -> datetime:
    """weekday: Mon=0 … Sun=6"""
    days_ahead = (weekday - dt.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return dt + timedelta(days=days_ahead)


def days_to_weekly_expiry(dt: Optional[datetime] = None) -> int:
    """NSE index options expire Thursday (weekday=3)."""
    dt = dt or now_ist()
    if dt.weekday() == 3 and dt.time() < NSE_CLOSE:
        return 0
    return ((3 - dt.weekday()) % 7) or 7
