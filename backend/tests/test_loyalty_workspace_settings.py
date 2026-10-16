"""Workspace reward rule defaults, validation and UI visibility contract."""
from decimal import Decimal
from django.test import TestCase

from apps.staff.forms.workspace_forms import StaffTenantBrandingForm
from apps.tenants.models import Tenant, TenantSettings


class LoyaltyWorkspaceConfigurationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Reward Configuration", slug="reward-config")
        self.policy, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)

    def test_rewards_are_opt_in(self):
        self.assertFalse(self.policy.loyalty_enabled)
        self.assertEqual(self.policy.loyalty_spend_per_point, Decimal("10000.00"))

    def test_owner_branding_form_exposes_safe_reward_configuration(self):
        form = StaffTenantBrandingForm(instance=self.policy)
        self.assertIn("loyalty_enabled", form.fields)
        self.assertIn("loyalty_spend_per_point", form.fields)

    def test_spend_threshold_must_be_positive(self):
        data = {
            "default_currency": "UGX",
            "default_timezone": "Africa/Kampala",
            "loyalty_enabled": "on",
            "loyalty_spend_per_point": "-1.00",
            "theme_primary": self.policy.theme_primary,
            "theme_secondary": self.policy.theme_secondary,
            "theme_accent": self.policy.theme_accent,
        }
        form = StaffTenantBrandingForm(data, instance=self.policy)
        self.assertFalse(form.is_valid())
        self.assertIn("loyalty_spend_per_point", form.errors)
