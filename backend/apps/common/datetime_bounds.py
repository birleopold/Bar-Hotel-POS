"""Reusable timezone-aware bounds for report-style filters."""

from __future__ import annotations

from datetime import date, datetime, time, timezone as dt_timezone


def utc_day_range_inclusive(d0: date, d1: date) -> tuple[datetime, datetime]:
    """
    UTC [start, end] for ``DateTimeField`` filters when ``date_from`` / ``date_to`` mean UTC calendar days.

    Matches prior naive ``combine(min)`` / ``combine(max)`` semantics under ``TIME_ZONE=UTC`` + ``USE_TZ``,
    but passes aware datetimes so the ORM does not warn.
    """
    start = datetime.combine(d0, time.min, tzinfo=dt_timezone.utc)
    end = datetime.combine(d1, time.max, tzinfo=dt_timezone.utc)
    return start, end
