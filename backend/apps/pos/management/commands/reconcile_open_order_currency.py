"""Re-label safe legacy OPEN POS baskets to the configured tenant currency.

Never converts amounts or touches payments, completed sales, or financial history.
Run without --apply to preview. --include-lines assumes existing line prices were
already entered in the intended currency (no exchange rate is applied).
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from apps.pos.models import Order, OrderLine, Payment, Refund
from apps.tenants.models import TenantSettings


class Command(BaseCommand):
    help = "Preview or repair currency labels on unpaid open baskets; never modify accounted sales."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes (default: preview)")
        parser.add_argument("--include-lines", action="store_true", help="Also relabel baskets containing items; amounts will not be converted")
        parser.add_argument("--tenant", help="Optional tenant slug; omitted means all tenants")
        parser.add_argument("--limit", type=int, default=0, help="Max number of orders to inspect (0 = all)")

    def handle(self, *args, **options):
        qs = Order.objects.select_related("tenant").order_by("created_at", "pk")
        if options["tenant"]:
            qs = qs.filter(tenant__slug=options["tenant"])
        if options["limit"] < 0:
            raise ValueError("--limit must be nonnegative")
        if options["limit"]:
            qs = qs[: options["limit"]]
        currencies = dict(TenantSettings.objects.values_list("tenant_id", "default_currency"))
        checked = eligible = changed = skipped_history = skipped_lines = 0
        for order in qs.iterator():
            configured = (currencies.get(order.tenant_id) or "").strip().upper()
            if not configured or order.currency == configured:
                continue
            checked += 1
            if order.status != "open" or order.is_paid or Payment.objects.filter(order_id=order.pk).exists() or Refund.objects.filter(order_id=order.pk).exists():
                skipped_history += 1
                continue
            has_lines = OrderLine.objects.filter(order_id=order.pk).exists()
            if has_lines and not options["include_lines"]:
                skipped_lines += 1
                continue
            eligible += 1
            self.stdout.write(f"{'APPLY' if options['apply'] else 'PREVIEW'} {order.tenant.slug} {order.pk}: {order.currency} -> {configured} (items={'yes' if has_lines else 'no'})")
            if options["apply"]:
                with transaction.atomic():
                    # Lock and recheck immediately before writing: no partial/paid histories.
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    if (locked.status != "open" or locked.is_paid
                        or Payment.objects.filter(order_id=locked.pk).exists()
                        or Refund.objects.filter(order_id=locked.pk).exists()
                        or (not options["include_lines"] and OrderLine.objects.filter(order_id=locked.pk).exists())):
                        skipped_history += 1
                        eligible -= 1
                        continue
                    Order.objects.filter(pk=locked.pk).update(currency=configured)
                    changed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Currency mismatches inspected={checked}, eligible={eligible}, changed={changed}, "
            f"protected financial history={skipped_history}, item baskets deferred={skipped_lines}. "
            f"{'Applied.' if options['apply'] else 'Preview only; use --apply to commit.'}"
        ))
