"""Shared timing rules for dashboard-only action and event tests."""

from __future__ import annotations

import math


MAX_TEST_DELAY_SECONDS = 10.0


def normalize_test_delay(value) -> float:
    """Return a safe dashboard test delay between zero and ten seconds."""

    try:
        delay = float(value or 0)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(delay):
        return 0.0

    return min(
        MAX_TEST_DELAY_SECONDS,
        max(0.0, delay),
    )
