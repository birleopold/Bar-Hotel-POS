from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Max, Sum

from apps.catalog.models import MenuCategory
from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.finance.models import (
    AccountingExportBatch,
    AccountingMapping,
    AccountingMappingKind,
    FinancePostingLink,
    FinancePostingSource,
)
from apps.lodging.models import FolioLine, FolioPayment
from apps.pos.models import Order, OrderLine, Payment, Refund
from apps.purchasing.models import SupplierInvoice, SupplierPayment


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _category_identity(line: OrderLine) -> tuple[str, str]:
    if line.menu_item_id and getattr(line.menu_item, "category_id", None):
        return str(line.menu_item.category_id), (
            line.merchandise_category_snapshot
            or line.menu_item.category.name
            or "Uncategorized"
        )
    name = (line.merchandise_category_snapshot or "").strip() or "Uncategorized"
    return "", name


def _line_net_revenue(order: Order, line: OrderLine) -> Decimal:
    gross = _money(line.line_total)
    subtotal = _money(order.subtotal)
    discount = _money(order.discount_amount)
    if gross <= 0 or subtotal <= 0 or discount <= 0:
        return gross
    allocated = (discount * gross / subtotal).quantize(MONEY, rounding=ROUND_HALF_UP)
    return max(ZERO, gross - min(gross, allocated))


class MappingResolver:
    def __init__(self, *, tenant_id):
        self.rows = list(
            AccountingMapping.objects.filter(
                tenant_id=tenant_id,
                is_active=True,
            ).order_by("kind", "source_key")
        )
        self.by_key = {(row.kind, row.source_key): row for row in self.rows}

    def exact(self, kind, source_key=""):
        return self.by_key.get((kind, str(source_key or "")))

    def with_default(self, specific_kind, source_key, default_kind):
        return self.exact(specific_kind, source_key) or self.exact(default_kind, "")

    def snapshot(self):
        return {
            f"{row.kind}:{row.source_key}": {
                "kind": row.kind,
                "source_key": row.source_key,
                "source_label": row.source_label,
                "account_code": row.account_code,
                "account_name": row.account_name,
            }
            for row in self.rows
        }


def _line(*, account, debit=ZERO, credit=ZERO, memo="", dimensions=None, source_refs=None):
    return {
        "account_code": account.account_code,
        "account_name": account.account_name,
        "debit": str(_money(debit)),
        "credit": str(_money(credit)),
        "memo": memo,
        "dimensions": dimensions or {},
        "source_refs": source_refs or [],
    }


def _append_aggregate(
    bucket, *, account, debit=ZERO, credit=ZERO, memo, dimensions,
    source_ref=None, source_refs=None,
):
    key = (
        account.account_code,
        account.account_name,
        memo,
        json.dumps(dimensions, sort_keys=True),
    )
    row = bucket.setdefault(key, {
        "account": account,
        "debit": ZERO,
        "credit": ZERO,
        "memo": memo,
        "dimensions": dimensions,
        "source_refs": [],
    })
    row["debit"] += _money(debit)
    row["credit"] += _money(credit)
    refs = list(source_refs or [])
    if source_ref:
        refs.append(source_ref)
    for ref in refs:
        if ref and ref not in row["source_refs"]:
            row["source_refs"].append(ref)


def build_accounting_preview(
    *,
    tenant_id,
    date_from,
    date_to,
    allowed_outlet_ids,
    currency,
):
    """Build a balanced, provider-neutral operational journal preview.

    Sales are recognized once at final POS settlement. Refunds are recognized
    on their refund date. This function never posts to the cashbook/GL.
    """
    start, end = utc_day_range_inclusive(date_from, date_to)
    outlet_ids = list(allowed_outlet_ids)
    resolver = MappingResolver(tenant_id=tenant_id)
    missing = []
    warnings = []
    aggregate = {}

    completed = list(
        Order.objects.filter(
            tenant_id=tenant_id,
            outlet_id__in=outlet_ids,
            is_paid=True,
            currency=currency,
        )
        .annotate(final_payment_at=Max("payments__created_at"))
        .filter(final_payment_at__gte=start, final_payment_at__lte=end)
        .select_related("outlet", "outlet__site", "created_by")
        .order_by("final_payment_at", "pk")
    )

    sale_order_ids = [order.pk for order in completed]
    sale_lines = defaultdict(list)
    if sale_order_ids:
        for line in (
            OrderLine.objects.filter(
                order_id__in=sale_order_ids,
                is_voided=False,
            )
            .select_related("menu_item", "menu_item__category")
            .order_by("order_id", "sort_order", "created_at")
        ):
            sale_lines[line.order_id].append(line)

    validation_errors = []
    source_counts = {
        "completed_sales": len(completed),
        "refunds": 0,
        "folio_charges": 0,
        "folio_payments": 0,
        "supplier_invoices": 0,
        "supplier_payments": 0,
        "unmatched_supplier_invoices": 0,
        "trusted_cost_lines": 0,
        "unknown_cost_lines": 0,
    }

    def require(mapping, label):
        if mapping is None and label not in missing:
            missing.append(label)
        return mapping

    for order in completed:
        dimensions = {
            "site": order.outlet.site.name,
            "site_id": str(order.outlet.site_id),
            "outlet": order.outlet.name,
            "outlet_id": str(order.outlet_id),
            "register": "",
            "cashier": order.created_by.email if order.created_by_id else "",
        }
        order_ref = f"order:{order.pk}"

        # Revenue by sale-time category after proportional order discount.
        category_totals = defaultdict(Decimal)
        category_costs = defaultdict(Decimal)
        for line in sale_lines.get(order.pk, []):
            category_id, category_name = _category_identity(line)
            category_totals[(category_id, category_name)] += _line_net_revenue(order, line)
            inventory_tracked = (
                line.inventory_tracked_snapshot is True
                or (
                    line.inventory_tracked_snapshot is None
                    and line.menu_item_id
                    and line.menu_item.track_inventory
                )
            )
            if (
                inventory_tracked
                and line.cost_basis_complete_snapshot
                and line.cost_unit_snapshot is not None
            ):
                category_costs[(category_id, category_name)] += (
                    Decimal(str(line.cost_unit_snapshot))
                    * Decimal(str(line.quantity))
                )
                source_counts["trusted_cost_lines"] += 1
            elif inventory_tracked:
                source_counts["unknown_cost_lines"] += 1

        for (category_id, category_name), amount in category_totals.items():
            if amount <= 0:
                continue
            account = require(
                resolver.with_default(
                    AccountingMappingKind.REVENUE_CATEGORY,
                    category_id,
                    AccountingMappingKind.REVENUE_DEFAULT,
                ),
                f"Revenue mapping for {category_name}",
            )
            if account:
                _append_aggregate(
                    aggregate,
                    account=account,
                    credit=amount,
                    memo=f"Sales revenue · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=order_ref,
                )

        tax = _money(order.tax_total)
        if tax > 0:
            account = require(
                resolver.exact(AccountingMappingKind.TAX_LIABILITY, ""),
                "Tax / VAT liability mapping",
            )
            if account:
                _append_aggregate(
                    aggregate,
                    account=account,
                    credit=tax,
                    memo="Sales tax / VAT",
                    dimensions=dimensions,
                    source_ref=order_ref,
                )

        # Net retained tender by method at the final settlement timestamp.
        payments = list(
            Payment.objects.filter(order=order)
            .select_related("shift", "shift__workstation")
            .order_by("created_at", "pk")
        )
        retained_by_method = defaultdict(Decimal)
        retained_refs_by_method = defaultdict(list)
        for payment in payments:
            refunded_before_settlement = (
                Refund.objects.filter(
                    payment=payment,
                    created_at__lte=order.final_payment_at,
                ).aggregate(total=Sum("amount"))["total"]
                or ZERO
            )
            retained = _money(payment.amount - refunded_before_settlement)
            if retained > 0:
                retained_by_method[payment.method] += retained
                retained_refs_by_method[payment.method].append(f"payment:{payment.pk}")
                if payment.shift_id and payment.shift.workstation_id:
                    dimensions["register"] = payment.shift.workstation.code

        retained_total = _money(sum(retained_by_method.values(), ZERO))
        if retained_total != _money(order.total):
            warnings.append(
                f"{order.bill_reference}: retained tender {retained_total} does not equal order total {_money(order.total)}."
            )
        for method, amount in retained_by_method.items():
            account = require(
                resolver.exact(AccountingMappingKind.TENDER, method),
                f"Tender clearing mapping for {method}",
            )
            if account:
                _append_aggregate(
                    aggregate,
                    account=account,
                    debit=amount,
                    memo=f"Tender clearing · {method}",
                    dimensions={**dimensions, "tender": method},
                    source_refs=[order_ref, *retained_refs_by_method[method]],
                )

        # Trusted COGS/inventory only. Unknown cost never becomes zero-cost.
        for (category_id, category_name), raw_cost in category_costs.items():
            cost = _money(raw_cost)
            if cost <= 0:
                continue
            cogs = require(
                resolver.with_default(
                    AccountingMappingKind.COGS_CATEGORY,
                    category_id,
                    AccountingMappingKind.COGS_DEFAULT,
                ),
                f"COGS mapping for {category_name}",
            )
            inventory = require(
                resolver.with_default(
                    AccountingMappingKind.INVENTORY_CATEGORY,
                    category_id,
                    AccountingMappingKind.INVENTORY_DEFAULT,
                ),
                f"Inventory asset mapping for {category_name}",
            )
            if cogs and inventory:
                _append_aggregate(
                    aggregate,
                    account=cogs,
                    debit=cost,
                    memo=f"COGS · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=order_ref,
                )
                _append_aggregate(
                    aggregate,
                    account=inventory,
                    credit=cost,
                    memo=f"Inventory relieved · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=order_ref,
                )

    # Refunds in the selected period. Tax is reversed proportionally from the
    # immutable order-level tax/total because a general refund may not identify
    # one product line.
    refunds = list(
        Refund.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=outlet_ids,
            order__currency=currency,
            created_at__gte=start,
            created_at__lte=end,
        )
        .select_related(
            "order",
            "order__outlet",
            "order__outlet__site",
            "payment",
            "recorded_by",
            "shift",
            "shift__workstation",
        )
        .order_by("created_at", "pk")
    )
    source_counts["refunds"] = len(refunds)
    for refund in refunds:
        order = refund.order
        dimensions = {
            "site": order.outlet.site.name,
            "site_id": str(order.outlet.site_id),
            "outlet": order.outlet.name,
            "outlet_id": str(order.outlet_id),
            "register": (
                refund.shift.workstation.code
                if refund.shift_id and refund.shift.workstation_id else ""
            ),
            "cashier": refund.recorded_by.email if refund.recorded_by_id else "",
            "tender": refund.payment.method,
        }
        refund_ref = f"refund:{refund.pk}"
        amount = _money(refund.amount)
        order_total = _money(order.total)
        order_tax = _money(order.tax_total)
        tax_reversal = (
            (amount * order_tax / order_total).quantize(MONEY, rounding=ROUND_HALF_UP)
            if order_total > 0 and order_tax > 0 else ZERO
        )
        pre_tax = _money(amount - tax_reversal)

        returns_account = require(
            resolver.exact(AccountingMappingKind.RETURNS, ""),
            "Sales returns mapping",
        )
        tender_account = require(
            resolver.exact(AccountingMappingKind.TENDER, refund.payment.method),
            f"Tender clearing mapping for {refund.payment.method}",
        )
        if returns_account and pre_tax > 0:
            _append_aggregate(
                aggregate,
                account=returns_account,
                debit=pre_tax,
                memo="Sales returns / refunds",
                dimensions=dimensions,
                source_ref=refund_ref,
            )
        if tax_reversal > 0:
            tax_account = require(
                resolver.exact(AccountingMappingKind.TAX_LIABILITY, ""),
                "Tax / VAT liability mapping",
            )
            if tax_account:
                _append_aggregate(
                    aggregate,
                    account=tax_account,
                    debit=tax_reversal,
                    memo="Refund tax / VAT reversal",
                    dimensions=dimensions,
                    source_ref=refund_ref,
                )
        if tender_account:
            _append_aggregate(
                aggregate,
                account=tender_account,
                credit=amount,
                memo=f"Refund tender clearing · {refund.payment.method}",
                dimensions=dimensions,
                source_ref=refund_ref,
            )

    # POS orders charged to a guest folio: recognize the sale at the folio
    # charge event, debit any retained POS tender plus A/R for the unpaid balance.
    folio_charges = list(
        FolioLine.objects.filter(
            tenant_id=tenant_id,
            source_order__isnull=False,
            source_order__outlet_id__in=outlet_ids,
            source_order__currency=currency,
            amount__gt=0,
            created_at__gte=start,
            created_at__lte=end,
        )
        .select_related(
            "folio",
            "source_order",
            "source_order__outlet",
            "source_order__outlet__site",
            "source_order__created_by",
        )
        .order_by("created_at", "pk")
    )
    source_counts["folio_charges"] = len(folio_charges)
    folio_order_ids = [charge.source_order_id for charge in folio_charges]
    folio_lines = defaultdict(list)
    if folio_order_ids:
        for line in (
            OrderLine.objects.filter(
                order_id__in=folio_order_ids,
                is_voided=False,
            )
            .select_related("menu_item", "menu_item__category")
            .order_by("order_id", "sort_order", "created_at")
        ):
            folio_lines[line.order_id].append(line)

    for charge in folio_charges:
        order = charge.source_order
        dimensions = {
            "site": order.outlet.site.name,
            "site_id": str(order.outlet.site_id),
            "outlet": order.outlet.name,
            "outlet_id": str(order.outlet_id),
            "register": "",
            "cashier": order.created_by.email if order.created_by_id else "",
            "folio": str(charge.folio_id),
        }
        charge_ref = f"folio_charge:{charge.pk}"
        category_totals = defaultdict(Decimal)
        category_costs = defaultdict(Decimal)
        for line in folio_lines.get(order.pk, []):
            category_id, category_name = _category_identity(line)
            category_totals[(category_id, category_name)] += _line_net_revenue(order, line)
            inventory_tracked = (
                line.inventory_tracked_snapshot is True
                or (
                    line.inventory_tracked_snapshot is None
                    and line.menu_item_id
                    and line.menu_item.track_inventory
                )
            )
            if (
                inventory_tracked
                and line.cost_basis_complete_snapshot
                and line.cost_unit_snapshot is not None
            ):
                category_costs[(category_id, category_name)] += (
                    Decimal(str(line.cost_unit_snapshot))
                    * Decimal(str(line.quantity))
                )
                source_counts["trusted_cost_lines"] += 1
            elif inventory_tracked:
                source_counts["unknown_cost_lines"] += 1

        for (category_id, category_name), amount in category_totals.items():
            if amount <= 0:
                continue
            account = require(
                resolver.with_default(
                    AccountingMappingKind.REVENUE_CATEGORY,
                    category_id,
                    AccountingMappingKind.REVENUE_DEFAULT,
                ),
                f"Revenue mapping for {category_name}",
            )
            if account:
                _append_aggregate(
                    aggregate,
                    account=account,
                    credit=amount,
                    memo=f"Folio sale revenue · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=charge_ref,
                )

        tax = _money(order.tax_total)
        if tax > 0:
            tax_account = require(
                resolver.exact(AccountingMappingKind.TAX_LIABILITY, ""),
                "Tax / VAT liability mapping",
            )
            if tax_account:
                _append_aggregate(
                    aggregate,
                    account=tax_account,
                    credit=tax,
                    memo="Folio sale tax / VAT",
                    dimensions=dimensions,
                    source_ref=charge_ref,
                )

        retained_by_method = defaultdict(Decimal)
        retained_refs_by_method = defaultdict(list)
        retained_total = ZERO
        for payment in (
            Payment.objects.filter(order=order, created_at__lte=charge.created_at)
            .select_related("shift", "shift__workstation")
            .order_by("created_at", "pk")
        ):
            refunded = (
                Refund.objects.filter(
                    payment=payment,
                    created_at__lte=charge.created_at,
                ).aggregate(total=Sum("amount"))["total"]
                or ZERO
            )
            retained = _money(payment.amount - refunded)
            if retained > 0:
                retained_by_method[payment.method] += retained
                retained_refs_by_method[payment.method].append(f"payment:{payment.pk}")
                retained_total += retained
                if payment.shift_id and payment.shift.workstation_id:
                    dimensions["register"] = payment.shift.workstation.code
        retained_total = _money(retained_total)
        for method, amount in retained_by_method.items():
            tender = require(
                resolver.exact(AccountingMappingKind.TENDER, method),
                f"Tender clearing mapping for {method}",
            )
            if tender:
                _append_aggregate(
                    aggregate,
                    account=tender,
                    debit=amount,
                    memo=f"Folio sale POS tender · {method}",
                    dimensions={**dimensions, "tender": method},
                    source_refs=[charge_ref, *retained_refs_by_method[method]],
                )

        receivable = _money(order.total - retained_total)
        if receivable > 0:
            ar = require(
                resolver.exact(AccountingMappingKind.ACCOUNTS_RECEIVABLE, ""),
                "Accounts receivable mapping",
            )
            if ar:
                _append_aggregate(
                    aggregate,
                    account=ar,
                    debit=receivable,
                    memo="Guest folio receivable",
                    dimensions=dimensions,
                    source_ref=charge_ref,
                )

        expected_debit = _money(retained_total + receivable)
        if expected_debit != _money(order.total):
            validation_errors.append(
                f"{order.bill_reference}: folio sale settlement dimensions do not equal the order total."
            )

        for (category_id, category_name), raw_cost in category_costs.items():
            cost = _money(raw_cost)
            if cost <= 0:
                continue
            cogs = require(
                resolver.with_default(
                    AccountingMappingKind.COGS_CATEGORY,
                    category_id,
                    AccountingMappingKind.COGS_DEFAULT,
                ),
                f"COGS mapping for {category_name}",
            )
            inventory = require(
                resolver.with_default(
                    AccountingMappingKind.INVENTORY_CATEGORY,
                    category_id,
                    AccountingMappingKind.INVENTORY_DEFAULT,
                ),
                f"Inventory asset mapping for {category_name}",
            )
            if cogs and inventory:
                _append_aggregate(
                    aggregate,
                    account=cogs,
                    debit=cost,
                    memo=f"Folio sale COGS · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=charge_ref,
                )
                _append_aggregate(
                    aggregate,
                    account=inventory,
                    credit=cost,
                    memo=f"Folio inventory relieved · {category_name}",
                    dimensions={**dimensions, "category": category_name},
                    source_ref=charge_ref,
                )

    folio_payments = list(
        FolioPayment.objects.filter(
            tenant_id=tenant_id,
            folio__site__outlets__id__in=outlet_ids,
            folio__currency=currency,
            created_at__gte=start,
            created_at__lte=end,
        )
        .select_related("folio", "folio__site", "recorded_by")
        .distinct()
        .order_by("created_at", "pk")
    )
    source_counts["folio_payments"] = len(folio_payments)
    for payment in folio_payments:
        ar = require(
            resolver.exact(AccountingMappingKind.ACCOUNTS_RECEIVABLE, ""),
            "Accounts receivable mapping",
        )
        tender = require(
            resolver.exact(AccountingMappingKind.TENDER, payment.method),
            f"Tender clearing mapping for {payment.method}",
        )
        dims = {
            "site": payment.folio.site.name,
            "site_id": str(payment.folio.site_id),
            "outlet": "",
            "outlet_id": "",
            "register": "",
            "cashier": payment.recorded_by.email if payment.recorded_by_id else "",
            "folio": str(payment.folio_id),
            "tender": payment.method,
        }
        ref = f"folio_payment:{payment.pk}"
        if tender:
            _append_aggregate(
                aggregate,
                account=tender,
                debit=payment.amount,
                memo=f"Folio payment · {payment.method}",
                dimensions=dims,
                source_ref=ref,
            )
        if ar:
            _append_aggregate(
                aggregate,
                account=ar,
                credit=payment.amount,
                memo="Guest folio receivable settlement",
                dimensions=dims,
                source_ref=ref,
            )

    # Supplier invoices create A/P only when immutable matched invoice lines
    # fully explain the supplier invoice amount.
    supplier_invoices = list(
        SupplierInvoice.objects.filter(
            tenant_id=tenant_id,
            purchase_order__outlet_id__in=outlet_ids,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
        )
        .select_related(
            "purchase_order",
            "purchase_order__outlet",
            "purchase_order__outlet__site",
            "purchase_order__supplier",
        )
        .prefetch_related(
            "matched_lines__purchase_order_line__menu_item__category"
        )
        .order_by("invoice_date", "pk")
    )
    source_counts["supplier_invoices"] = len(supplier_invoices)
    for invoice in supplier_invoices:
        matched = list(invoice.matched_lines.all())
        matched_total = _money(sum((item.amount for item in matched), ZERO))
        if matched_total != _money(invoice.amount):
            source_counts["unmatched_supplier_invoices"] += 1
            validation_errors.append(
                f"Supplier invoice {invoice.reference}: matched lines {matched_total} do not equal invoice amount {_money(invoice.amount)}."
            )
            continue
        dims = {
            "site": invoice.purchase_order.outlet.site.name,
            "site_id": str(invoice.purchase_order.outlet.site_id),
            "outlet": invoice.purchase_order.outlet.name,
            "outlet_id": str(invoice.purchase_order.outlet_id),
            "register": "",
            "cashier": "",
            "supplier": invoice.purchase_order.supplier.name,
        }
        ref = f"supplier_invoice:{invoice.pk}"
        category_amounts = defaultdict(Decimal)
        for item in matched:
            menu_item = item.purchase_order_line.menu_item
            category_id = str(menu_item.category_id or "")
            category_name = (
                menu_item.category.name
                if menu_item.category_id else "Uncategorized"
            )
            category_amounts[(category_id, category_name)] += item.amount
        all_mapped = True
        mapped_rows = []
        for (category_id, category_name), amount in category_amounts.items():
            inventory = require(
                resolver.with_default(
                    AccountingMappingKind.INVENTORY_CATEGORY,
                    category_id,
                    AccountingMappingKind.INVENTORY_DEFAULT,
                ),
                f"Inventory asset mapping for {category_name}",
            )
            if inventory is None:
                all_mapped = False
            else:
                mapped_rows.append((inventory, category_name, _money(amount)))
        ap = require(
            resolver.exact(AccountingMappingKind.ACCOUNTS_PAYABLE, ""),
            "Accounts payable mapping",
        )
        if ap is None:
            all_mapped = False
        if all_mapped:
            for inventory, category_name, amount in mapped_rows:
                _append_aggregate(
                    aggregate,
                    account=inventory,
                    debit=amount,
                    memo=f"Supplier inventory invoice · {category_name}",
                    dimensions={**dims, "category": category_name},
                    source_ref=ref,
                )
            _append_aggregate(
                aggregate,
                account=ap,
                credit=invoice.amount,
                memo=f"Supplier payable · {invoice.reference}",
                dimensions=dims,
                source_ref=ref,
            )

    supplier_payments = list(
        SupplierPayment.objects.filter(
            tenant_id=tenant_id,
            purchase_order__outlet_id__in=outlet_ids,
            created_at__gte=start,
            created_at__lte=end,
        )
        .select_related(
            "purchase_order",
            "purchase_order__outlet",
            "purchase_order__outlet__site",
            "purchase_order__supplier",
            "recorded_by",
        )
        .order_by("created_at", "pk")
    )
    source_counts["supplier_payments"] = len(supplier_payments)
    for payment in supplier_payments:
        ap = require(
            resolver.exact(AccountingMappingKind.ACCOUNTS_PAYABLE, ""),
            "Accounts payable mapping",
        )
        tender = require(
            resolver.exact(AccountingMappingKind.TENDER, payment.method),
            f"Tender clearing mapping for {payment.method}",
        )
        dims = {
            "site": payment.purchase_order.outlet.site.name,
            "site_id": str(payment.purchase_order.outlet.site_id),
            "outlet": payment.purchase_order.outlet.name,
            "outlet_id": str(payment.purchase_order.outlet_id),
            "register": "",
            "cashier": payment.recorded_by.email if payment.recorded_by_id else "",
            "supplier": payment.purchase_order.supplier.name,
            "tender": payment.method,
        }
        ref = f"supplier_payment:{payment.pk}"
        if ap:
            _append_aggregate(
                aggregate,
                account=ap,
                debit=payment.amount,
                memo="Supplier payable settlement",
                dimensions=dims,
                source_ref=ref,
            )
        if tender:
            _append_aggregate(
                aggregate,
                account=tender,
                credit=payment.amount,
                memo=f"Supplier payment · {payment.method}",
                dimensions=dims,
                source_ref=ref,
            )

    if source_counts["unknown_cost_lines"]:
        warnings.append(
            f"{source_counts['unknown_cost_lines']} inventory-tracked sale line(s) have incomplete sale-time cost; no COGS/inventory journal was guessed for them."
        )

    posting_type_for_prefix = {
        "payment": FinancePostingSource.POS_PAYMENT,
        "refund": FinancePostingSource.POS_REFUND,
        "folio_payment": FinancePostingSource.FOLIO_PAYMENT,
        "supplier_payment": FinancePostingSource.SUPPLIER_PAYMENT,
    }
    posting_keys = []
    for row in aggregate.values():
        for ref in row["source_refs"]:
            if ":" not in ref:
                continue
            prefix, source_id = ref.split(":", 1)
            source_type = posting_type_for_prefix.get(prefix)
            if source_type:
                posting_keys.append((source_type, source_id))
    linked_cashbook = {}
    if posting_keys:
        source_types = {item[0] for item in posting_keys}
        source_ids = {item[1] for item in posting_keys}
        for link in FinancePostingLink.objects.filter(
            tenant_id=tenant_id,
            source_type__in=source_types,
            source_id__in=source_ids,
        ).only("source_type", "source_id", "cashbook_entry_id"):
            linked_cashbook[(link.source_type, link.source_id)] = str(
                link.cashbook_entry_id
            )
        for row in aggregate.values():
            additions = []
            for ref in row["source_refs"]:
                if ":" not in ref:
                    continue
                prefix, source_id = ref.split(":", 1)
                source_type = posting_type_for_prefix.get(prefix)
                cashbook_id = linked_cashbook.get((source_type, source_id))
                if cashbook_id:
                    additions.append(f"cashbook:{cashbook_id}")
            for ref in additions:
                if ref not in row["source_refs"]:
                    row["source_refs"].append(ref)

    source_counts["linked_cashbook_entries"] = len(set(linked_cashbook.values()))

    journal_lines = []
    for row in aggregate.values():
        journal_lines.append(
            _line(
                account=row["account"],
                debit=row["debit"],
                credit=row["credit"],
                memo=row["memo"],
                dimensions=row["dimensions"],
                source_refs=row["source_refs"][:200],
            )
        )
    journal_lines.sort(
        key=lambda row: (
            row["dimensions"].get("site", ""),
            row["dimensions"].get("outlet", ""),
            row["account_code"],
            row["memo"],
        )
    )
    total_debit = _money(sum((Decimal(row["debit"]) for row in journal_lines), ZERO))
    total_credit = _money(sum((Decimal(row["credit"]) for row in journal_lines), ZERO))
    balanced = total_debit == total_credit

    if not balanced and not missing:
        warnings.append(
            f"Journal is not balanced: debits {total_debit} vs credits {total_credit}."
        )

    if not journal_lines:
        warnings.append("No accounting journal activity exists in the selected period and scope.")

    return {
        "currency": currency,
        "date_from": date_from,
        "date_to": date_to,
        "journal_lines": journal_lines,
        "mapping_snapshot": resolver.snapshot(),
        "missing_mappings": missing,
        "validation_errors": validation_errors,
        "warnings": warnings,
        "source_summary": source_counts,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": balanced,
        "ready": balanced and not missing and not validation_errors and bool(journal_lines),
    }


def preview_fingerprint(*, tenant_id, preview, allowed_outlet_ids):
    payload = {
        "tenant_id": str(tenant_id),
        "date_from": str(preview["date_from"]),
        "date_to": str(preview["date_to"]),
        "currency": preview["currency"],
        "scope_outlet_ids": sorted(str(pk) for pk in allowed_outlet_ids),
        "mapping_snapshot": preview["mapping_snapshot"],
        "journal_lines": preview["journal_lines"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@transaction.atomic
def create_accounting_export(
    *,
    tenant_id,
    preview,
    allowed_outlet_ids,
    user,
):
    if not preview["ready"]:
        raise ValueError("Accounting preview must be fully mapped and balanced before export.")
    fingerprint = preview_fingerprint(
        tenant_id=tenant_id,
        preview=preview,
        allowed_outlet_ids=allowed_outlet_ids,
    )
    existing = AccountingExportBatch.objects.filter(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
    ).first()
    if existing:
        return existing, True
    batch = AccountingExportBatch.objects.create(
        tenant_id=tenant_id,
        date_from=preview["date_from"],
        date_to=preview["date_to"],
        currency=preview["currency"],
        scope_outlet_ids=[str(pk) for pk in allowed_outlet_ids],
        mapping_snapshot=preview["mapping_snapshot"],
        journal_lines=preview["journal_lines"],
        source_summary=preview["source_summary"],
        fingerprint=fingerprint,
        line_count=len(preview["journal_lines"]),
        total_debit=preview["total_debit"],
        total_credit=preview["total_credit"],
        generated_by=user,
    )
    return batch, False
