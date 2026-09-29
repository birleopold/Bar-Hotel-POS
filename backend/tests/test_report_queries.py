"""Unit tests for report API query helpers."""

from datetime import date, datetime, time, timezone as dt_timezone
import uuid

import pytest
from rest_framework.response import Response
from apps.api.report_queries import parse_outlet_uuid_param, parse_report_dates_from_query


def test_parse_report_dates_success():
    rng = parse_report_dates_from_query("2026-01-01", "2026-01-02")
    assert not isinstance(rng, Response)
    assert rng.d0 == date(2026, 1, 1)
    assert rng.d1 == date(2026, 1, 2)
    assert rng.start == datetime.combine(date(2026, 1, 1), time.min).replace(tzinfo=dt_timezone.utc)
    assert rng.end.tzinfo == dt_timezone.utc


@pytest.mark.parametrize(
    ("a", "b", "expect_code"),
    [
        ("", "2026-01-02", "dates_required"),
        ("bad", "2026-01-02", "invalid_date"),
        ("2026-01-03", "2026-01-02", "invalid_range"),
    ],
)
def test_parse_report_dates_errors(a: str, b: str, expect_code: str):
    r = parse_report_dates_from_query(a, b)
    assert isinstance(r, Response)
    body = r.data
    assert body["error"]["code"] == expect_code


def test_parse_outlet_uuid():
    assert parse_outlet_uuid_param("") is None
    assert parse_outlet_uuid_param(None) is None
    val = parse_outlet_uuid_param("550e8400-e29b-41d4-a716-446655440000")
    assert isinstance(val, uuid.UUID)
    assert parse_outlet_uuid_param("not-a-uuid").status_code == 400
