"""Timezone-aware operating day for POS, hotel and property reporting.

Uses the actual local instant for DST changes; never assumes a fixed UTC
offset. No shift closing or financial postings happen merely by reading the
business date.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.utils import timezone

from .models import TenantSettings


def effective_business_clock(*, tenant, site=None):
    if site is not None and site.tenant_id != tenant.pk:
        raise ValueError("Property does not belong to the business")
    settings = TenantSettings.objects.filter(tenant=tenant).first()
    name = (site.business_timezone if site and site.business_timezone else
            (settings.default_timezone if settings else "UTC"))
    hour = (site.business_day_cutover_hour if site and
            site.business_day_cutover_hour is not None else
            (settings.business_day_cutover_hour if settings else 4))
    if not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError("Business day boundary must be between 0 and 23")
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Invalid configured time zone") from exc
    return zone, hour, name


def business_date_for(*, tenant, site=None, at=None):
    """Compute the operating date from a timezone-aware timestamp."""
    zone, cutover_hour, _name = effective_business_clock(tenant=tenant, site=site)
    when = at if at is not None else timezone.now()
    if timezone.is_naive(when):
        raise ValueError("A timezone-aware timestamp is required")
    local_time = timezone.localtime(when, timezone=zone)
    return (local_time.date() - timedelta(days=1)
            if local_time.hour < cutover_hour else local_time.date())
