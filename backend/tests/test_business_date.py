"""Phase 10 timezone-aware operating dates, including daylight-saving changes."""
from datetime import datetime, date, timezone as datetime_timezone

from django.test import TestCase

from apps.tenants.business_date import business_date_for, effective_business_clock
from apps.tenants.models import Site, Tenant, TenantSettings


class BusinessDateTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Business Date Test", slug="business-date-test")
        self.site = Site.objects.create(tenant=self.tenant, name="Main Property")
        self.settings, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        self.settings.default_timezone = "Africa/Kampala"
        self.settings.business_day_cutover_hour = 4
        self.settings.save()

    def test_early_morning_belongs_to_previous_operating_date(self):
        at = datetime(2026, 10, 15, 0, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(
            business_date_for(tenant=self.tenant, site=self.site, at=at),
            date(2026, 10, 14),
        )
        after = datetime(2026, 10, 15, 1, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(
            business_date_for(tenant=self.tenant, site=self.site, at=after),
            date(2026, 10, 15),
        )

    def test_site_can_override_timezone_and_boundary(self):
        self.site.business_timezone = "UTC"
        self.site.business_day_cutover_hour = 1
        self.site.save()
        at = datetime(2026, 10, 15, 1, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(business_date_for(tenant=self.tenant, site=self.site, at=at), date(2026, 10, 15))
        zone, cutover, name = effective_business_clock(tenant=self.tenant, site=self.site)
        self.assertEqual((cutover, name), (1, "UTC"))

    def test_site_must_belong_to_business(self):
        other = Tenant.objects.create(name="Other Business Date", slug="business-date-other")
        with self.assertRaises(ValueError):
            business_date_for(
                tenant=other, site=self.site,
                at=datetime(2026, 10, 15, 0, 0, tzinfo=datetime_timezone.utc),
            )

    def test_dst_fall_back_is_handled_as_two_instants(self):
        self.settings.default_timezone = "America/New_York"
        self.settings.save(update_fields=["default_timezone"])
        early = datetime(2026, 11, 1, 5, 30, tzinfo=datetime_timezone.utc)
        late = datetime(2026, 11, 1, 6, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(business_date_for(tenant=self.tenant, at=early), date(2026, 10, 31))
        self.assertEqual(business_date_for(tenant=self.tenant, at=late), date(2026, 10, 31))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            business_date_for(tenant=self.tenant, at=datetime(2026, 10, 15, 0, 30))
