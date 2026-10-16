"""Read-only inventory of historical postings that require human reconciliation."""

import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.finance.models import FinanceCategoryKind, FinancePostingLink, FinancePostingSource
from apps.lodging.models import FolioLine
from apps.pos.models import Order
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "List legacy POS folio charges and purchase receipt expenses for one tenant (no changes)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", required=True, help="Tenant UUID to audit")

    def handle(self, *args, **options):
        try:
            tenant_id = uuid.UUID(options["tenant_id"])
        except (ValueError, TypeError) as exc:
            raise CommandError("--tenant-id must be a UUID") from exc
        if not Tenant.objects.filter(pk=tenant_id).exists():
            raise CommandError("Tenant not found")
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL app.tenant_id = %s", [str(tenant_id)])
            legacy_folio_orders = []
            paid_orders = Order.objects.filter(tenant_id=tenant_id, is_paid=True, folio__isnull=False).values_list("id", flat=True)
            for order_id in paid_orders.iterator():
                lines = list(FolioLine.objects.filter(tenant_id=tenant_id, source_order_id=order_id))
                if any(line.amount > 0 for line in lines) and not any(line.amount < 0 for line in lines):
                    legacy_folio_orders.append(str(order_id))
            legacy_receipt_postings = list(
                FinancePostingLink.objects.filter(
                    tenant_id=tenant_id, source_type=FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT,
                ).order_by("source_id").values_list("source_id", flat=True)
            )
            # Investigate cross-tenant references and inverted posting categories.
            # Do not auto-fix financial history: the source transactions and
            # accounting correction policy must be verified by an operator.
            expected_kind = {
                FinancePostingSource.POS_PAYMENT: FinanceCategoryKind.INCOME,
                FinancePostingSource.FOLIO_PAYMENT: FinanceCategoryKind.INCOME,
                FinancePostingSource.EVENT_PAYMENT: FinanceCategoryKind.INCOME,
                FinancePostingSource.POS_REFUND: FinanceCategoryKind.EXPENSE,
                FinancePostingSource.SUPPLIER_PAYMENT: FinanceCategoryKind.EXPENSE,
                FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT: FinanceCategoryKind.EXPENSE,
            }
            suspect_links = []
            links = FinancePostingLink.objects.filter(tenant_id=tenant_id).select_related(
                "cashbook_entry", "cashbook_entry__category"
            ).order_by("source_type", "source_id")
            for link in links.iterator():
                entry = link.cashbook_entry
                issues = []
                if entry.tenant_id != tenant_id:
                    issues.append("cashbook_tenant_mismatch")
                if entry.category.tenant_id != tenant_id:
                    issues.append("category_tenant_mismatch")
                kind = expected_kind.get(link.source_type)
                if kind and entry.category.kind != kind:
                    issues.append("unexpected_category_kind")
                if issues:
                    suspect_links.append({
                        "source_type": link.source_type,
                        "source_id": link.source_id,
                        "cashbook_entry_id": str(entry.pk),
                        "issues": issues,
                    })
        self.stdout.write(json.dumps({
            "tenant_id": str(tenant_id),
            "paid_pos_orders_with_uncredited_folio_lines": sorted(legacy_folio_orders),
            "legacy_purchase_receipt_movement_ids": legacy_receipt_postings,
            "suspect_posting_links": suspect_links,
            "note": "Review against actual guest and supplier payments before correcting historical books.",
        }, indent=2))
