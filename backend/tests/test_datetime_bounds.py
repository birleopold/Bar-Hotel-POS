from datetime import date, datetime, time, timezone as dt_timezone

from apps.common.datetime_bounds import utc_day_range_inclusive


def test_utc_day_range_inclusive_is_aware_and_spanning():
    d0 = date(2026, 5, 1)
    d1 = date(2026, 5, 2)
    start, end = utc_day_range_inclusive(d0, d1)
    assert start.tzinfo == dt_timezone.utc
    assert end.tzinfo == dt_timezone.utc
    assert start == datetime(2026, 5, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
    assert end.time() == time.max
    assert start <= end
