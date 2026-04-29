"""Helpers for exchange expiry-date selection."""
from __future__ import annotations

from datetime import date, timedelta

from app.config.constants import INSTRUMENT_UNIVERSE


def weekly_expiry_candidates(start: date, count: int = 4, weekday: int = 3) -> list[date]:
    expiries: list[date] = []
    current = start
    while len(expiries) < count:
        days_ahead = (weekday - current.weekday()) % 7
        expiry = current + timedelta(days=days_ahead)
        expiries.append(expiry)
        current = expiry + timedelta(days=1)
    return expiries


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def monthly_expiry_candidates(start: date, count: int = 4, weekday: int = 3) -> list[date]:
    expiries: list[date] = []
    year, month = start.year, start.month
    while len(expiries) < count:
        expiry = _last_weekday_of_month(year, month, weekday)
        if expiry >= start:
            expiries.append(expiry)
        month += 1
        if month == 13:
            year += 1
            month = 1
    return expiries


def expiry_candidates(instrument: str, start: date, count: int = 4) -> list[date]:
    meta = INSTRUMENT_UNIVERSE.get(instrument, {})
    if meta.get("weekly", False):
        return weekly_expiry_candidates(start, count=count)
    return monthly_expiry_candidates(start, count=count)
