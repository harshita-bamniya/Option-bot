"""Shared pytest fixtures.

The test-suite is designed to run WITHOUT live DB / Redis / TrueData.
We monkey-patch the few repository methods that pure unit tests touch.
"""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "ERROR")
