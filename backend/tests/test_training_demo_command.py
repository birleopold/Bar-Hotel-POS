"""Training seed must never mutate real businesses or reach live providers."""
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.catalog.models import MenuItem
from apps.integrations.models import EfrisSubmission, IntegrationLink
from apps.pos.models import Order, Payment
from apps.tenants.models import Tenant


@pytest.mark.django_db
@pytest.mark.parametrize("business_type", ["bar", "restaurant", "lodging", "supermarket"])
@override_settings(DEBUG=True)
def test_training_demo_is_isolated_and_has_no_financial_side_effects(business_type):
    slug = f"training-{business_type}-seed"
    call_command("create_training_demo", type=business_type, slug=slug)
    tenant = Tenant.objects.get(slug=slug)
    assert tenant.name.startswith("TRAINING")
    assert tenant.settings.business_lines == [business_type]
    assert tenant.settings.efris_enabled is False
    assert tenant.sites.count() == 1
    assert MenuItem.objects.filter(tenant=tenant).count() == (0 if business_type == "lodging" else 2)
    assert not Order.objects.filter(tenant=tenant).exists()
    assert not Payment.objects.filter(tenant=tenant).exists()
    assert not IntegrationLink.objects.filter(tenant=tenant).exists()
    assert not EfrisSubmission.objects.filter(tenant=tenant).exists()
    with pytest.raises(CommandError):
        call_command("create_training_demo", type=business_type, slug=slug)
    assert Tenant.objects.filter(slug=slug).count() == 1


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_training_demo_disabled_in_production():
    with pytest.raises(CommandError):
        call_command("create_training_demo", type="bar", slug="training-not-live")
    assert not Tenant.objects.filter(slug="training-not-live").exists()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_training_demo_requires_training_slug():
    with pytest.raises(CommandError):
        call_command("create_training_demo", type="bar", slug="customer-business")
    assert not Tenant.objects.filter(slug="customer-business").exists()
