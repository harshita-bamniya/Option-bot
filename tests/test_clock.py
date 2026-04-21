"""Clock helpers — IST market session/expiry."""
from __future__ import annotations

from datetime import datetime

import pytz

from app.utils.clock import current_session, days_to_weekly_expiry, ist


def _ist(y, m, d, hh, mm) -> datetime:
    return ist.localize(datetime(y, m, d, hh, mm))


def test_session_classification_at_open() -> None:
    assert current_session(_ist(2025, 1, 6, 9, 30)) in ("Opening", "Morning Trend")


def test_days_to_weekly_expiry_is_zero_on_thursday() -> None:
    # 2026-04-16 is a Thursday
    assert days_to_weekly_expiry(_ist(2026, 4, 16, 10, 0)) == 0


def test_days_to_weekly_expiry_counts_forward() -> None:
    # 2026-04-13 (Mon) → Thursday is 3 days away
    assert days_to_weekly_expiry(_ist(2026, 4, 13, 10, 0)) == 3
