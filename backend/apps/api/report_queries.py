"""Shared query parsing for tenant sales/report API views."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from django.utils.dateparse import parse_date
from rest_framework.response import Response

from apps.common.datetime_bounds import utc_day_range_inclusive


@dataclass(frozen=True, slots=True)
class ParsedReportRange:
    """Validated calendar range and timezone-aware UTC ``created_at`` bounds."""

    d0: date
    d1: date
    start: datetime
    end: datetime


def parse_report_dates_from_query(raw_from: str | None, raw_to: str | None) -> Response | ParsedReportRange:
    if not raw_from or not raw_to:
        return Response(
            {
                "error": {
                    "code": "dates_required",
                    "message": "Query parameters date_from and date_to are required (YYYY-MM-DD).",
                }
            },
            status=400,
        )
    d0 = parse_date(str(raw_from))
    d1 = parse_date(str(raw_to))
    if d0 is None or d1 is None:
        return Response(
            {
                "error": {
                    "code": "invalid_date",
                    "message": "date_from and date_to must be valid dates.",
                }
            },
            status=400,
        )
    if d0 > d1:
        return Response(
            {
                "error": {
                    "code": "invalid_range",
                    "message": "date_from must be on or before date_to.",
                }
            },
            status=400,
        )
    start, end = utc_day_range_inclusive(d0, d1)
    return ParsedReportRange(d0=d0, d1=d1, start=start, end=end)


def parse_outlet_uuid_param(outlet_raw: str | None) -> Response | uuid.UUID | None:
    """Validated outlet UUID, ``None`` if absent, or 400 ``Response`` on malformed input."""
    if not outlet_raw or not str(outlet_raw).strip():
        return None
    try:
        return uuid.UUID(str(outlet_raw))
    except ValueError:
        return Response(
            {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
            status=400,
        )
