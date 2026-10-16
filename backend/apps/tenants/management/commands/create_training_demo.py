"""Create an isolated, nonfinancial training business on a local development database.

Never use on a production database. It deliberately creates no users, payments,
orders, subscriptions, fiscal documents, integrations or customer personal data.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import MenuCategory, MenuItem
from apps.tenants.business_lines import BUSINESS_LINES
from apps.tenants.models import Outlet, Site, Tenant, TenantSettings


DEMO_CATALOG = {
    "bar": (("Soft drink", "3000"), ("Bottled water", "2000")),
    "restaurant": (("Lunch special", "15000"), ("Coffee", "5000")),
    "lodging": (),
    "supermarket": (("Rice 1 kg", "4500"), ("Cooking oil 1 L", "9000")),
}


class Command(BaseCommand):
    help = "Create an isolated sample tenant on local DEBUG database; never a live workspace."

    def add_arguments(self, parser):
        parser.add_argument("--type", choices=sorted(DEMO_CATALOG), required=True)
        parser.add_argument("--slug", required=True, help="Unique slug, must start with training-")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Training creation is disabled unless DEBUG=True.")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Use a disposable local SQLite database for training.")
        slug = options["slug"].strip().lower()
        if not slug.startswith("training-"):
            raise CommandError("Training workspace slugs must start with training-.")
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError("The slug already exists. Refusing to alter an existing business.")
        business_type = options["type"]
        profile = BUSINESS_LINES[business_type]
        tenant = Tenant.objects.create(slug=slug, name=f"TRAINING — {profile.label}")
        TenantSettings.objects.create(
            tenant=tenant, business_lines=[business_type],
            default_currency="UGX", default_timezone="Africa/Kampala",
            efris_enabled=False, loyalty_enabled=False,
        )
        site = Site.objects.create(tenant=tenant, name="Sample branch", country_code="UG")
        outlet = Outlet.objects.create(
            site=site, name=profile.default_outlet_name,
            outlet_type=profile.default_outlet_type,
        )
        products = DEMO_CATALOG[business_type]
        if products:
            category = MenuCategory.objects.create(tenant=tenant, name="Training products")
            for name, price in products:
                MenuItem.objects.create(
                    tenant=tenant, category=category, name=name,
                    unit_price=Decimal(price), track_inventory=False,
                )
        self.stdout.write(self.style.SUCCESS(
            f"Created training business {slug} ({business_type}); {len(products)} sample items. "
            "No employees, live transactions or providers were created."
        ))
