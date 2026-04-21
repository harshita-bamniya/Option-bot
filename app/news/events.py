"""Macro event calendar (spec §11.2).

High-impact events that trigger risk adjustments and/or hard blocks.
Real deployments should sync this from an authoritative source daily.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from app.utils.clock import now_ist


@dataclass(frozen=True)
class MacroEvent:
    name: str
    ts: datetime           # IST-aware
    impact: str            # HIGH | MEDIUM | LOW


# In production this is populated from a calendar feed (RBI, NSE, FOMC, BLS)
# and refreshed daily. Here we expose a mutable registry the scheduler updates.
MACRO_EVENTS: List[MacroEvent] = []


def has_high_impact_event_within(minutes: int) -> tuple[bool, MacroEvent | None]:
    """Return (True, event) if a HIGH-impact event occurs within `minutes` from now."""
    now = now_ist()
    horizon = now + timedelta(minutes=minutes)
    for e in MACRO_EVENTS:
        if e.impact == "HIGH" and now <= e.ts <= horizon:
            return True, e
    return False, None


def register_event(name: str, ts: datetime, impact: str = "HIGH") -> None:
    MACRO_EVENTS.append(MacroEvent(name=name, ts=ts, impact=impact))
