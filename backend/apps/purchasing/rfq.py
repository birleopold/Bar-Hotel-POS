"""Simple competitive sourcing workflow that terminates in the normal PO ledger."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.audit.services import log_audit

from .models import (
    PurchaseApprovalStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseRfq,
    PurchaseRfqLine,
    PurchaseRfqStatus,
    Supplier,
    SupplierQuote,
    SupplierQuoteLine,
    SupplierQuoteStatus,
)


def _decimal(value, *, field, positive=False, allow_zero=True):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid number."}) from exc
    if not amount.is_finite():
        raise ValidationError({field: "Enter a valid number."})
    if positive and (amount < 0 if allow_zero else amount <= 0):
        raise ValidationError({field: "Enter a non-negative number." if allow_zero else "Enter a number greater than zero."})
    return amount


@transaction.atomic
def create_rfq(
    *,
    tenant,
    outlet,
    membership,
    user,
    reference: str = "",
    needed_by=None,
    notes: str = "",
    lines: list[dict],
) -> PurchaseRfq:
    if not outlet_belongs_to_membership(membership, outlet.pk):
        raise ValidationError({"outlet": "You cannot create an RFQ for this outlet."})
    if outlet.site.tenant_id != tenant.pk:
        raise ValidationError({"outlet": "Choose an outlet from this business."})
    normalized = []
    seen = set()
    for row in lines:
        item = row.get("menu_item")
        if item is None or item.tenant_id != tenant.pk or not item.track_inventory:
            raise ValidationError({"lines": "Choose active inventory products from this business."})
        if item.pk in seen:
            raise ValidationError({"lines": f"{item.name} appears more than once."})
        seen.add(item.pk)
        qty = _decimal(
            row.get("quantity"), field="quantity",
            positive=True, allow_zero=False,
        )
        if qty != qty.quantize(Decimal("0.001")):
            raise ValidationError({"quantity": "Use at most three decimal places."})
        normalized.append((item, qty, (row.get("note") or "").strip()[:255]))
    if not normalized:
        raise ValidationError({"lines": "Add at least one product to request quotations for."})

    ref = (reference or "").strip()[:128]
    if not ref:
        ref = f"RFQ-{uuid.uuid4().hex[:8].upper()}"
    if PurchaseRfq.objects.filter(tenant=tenant, reference__iexact=ref).exists():
        raise ValidationError({"reference": "This RFQ reference is already in use."})

    rfq = PurchaseRfq.objects.create(
        tenant=tenant,
        outlet=outlet,
        reference=ref,
        needed_by=needed_by,
        notes=(notes or "").strip(),
        created_by=user,
        status=PurchaseRfqStatus.DRAFT,
    )
    PurchaseRfqLine.objects.bulk_create([
        PurchaseRfqLine(
            tenant=tenant, rfq=rfq, menu_item=item,
            quantity_requested=qty, note=note,
        )
        for item, qty, note in normalized
    ])
    log_audit(
        tenant_id=tenant.pk,
        user_id=user.pk if user else None,
        action="purchasing.rfq_created",
        entity_type="purchase_rfq",
        entity_id=str(rfq.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "reference": rfq.reference,
            "lines": [
                {"menu_item_id": str(item.pk), "quantity": str(qty)}
                for item, qty, _note in normalized
            ],
        },
    )
    return rfq


@transaction.atomic
def invite_supplier_to_rfq(*, rfq, supplier, user) -> SupplierQuote:
    locked = PurchaseRfq.objects.select_for_update().get(pk=rfq.pk)
    if locked.status in (PurchaseRfqStatus.AWARDED, PurchaseRfqStatus.CANCELLED):
        raise ValidationError({"rfq": "This RFQ is closed."})
    if supplier.tenant_id != locked.tenant_id or not supplier.is_active:
        raise ValidationError({"supplier": "Choose an active supplier from this business."})
    quote, created = SupplierQuote.objects.get_or_create(
        tenant_id=locked.tenant_id,
        rfq=locked,
        supplier=supplier,
        defaults={"created_by": user, "status": SupplierQuoteStatus.INVITED},
    )
    if locked.status == PurchaseRfqStatus.DRAFT:
        locked.status = PurchaseRfqStatus.OPEN
        locked.save(update_fields=["status", "updated_at"])
    if created:
        log_audit(
            tenant_id=locked.tenant_id,
            user_id=user.pk if user else None,
            action="purchasing.rfq_supplier_invited",
            entity_type="supplier_quote",
            entity_id=str(quote.pk),
            payload={"rfq_id": str(locked.pk), "supplier_id": str(supplier.pk)},
        )
    return quote


@transaction.atomic
def record_supplier_quote(
    *,
    quote,
    user,
    reference="",
    shipping_cost=Decimal("0"),
    other_cost=Decimal("0"),
    lead_time_days=None,
    availability_note="",
    payment_terms="",
    valid_until=None,
    lines: list[dict],
) -> SupplierQuote:
    locked = (
        SupplierQuote.objects.select_for_update()
        .select_related("rfq", "supplier")
        .get(pk=quote.pk)
    )
    if locked.rfq.status not in (PurchaseRfqStatus.DRAFT, PurchaseRfqStatus.OPEN):
        raise ValidationError({"quote": "This RFQ is no longer accepting quotations."})
    if locked.status == SupplierQuoteStatus.ACCEPTED:
        raise ValidationError({"quote": "The accepted quotation is locked."})

    requested = {
        line.pk: line
        for line in locked.rfq.lines.select_related("menu_item").all()
    }
    normalized = {}
    for row in lines:
        rfq_line = row.get("rfq_line")
        if rfq_line is None or rfq_line.pk not in requested:
            raise ValidationError({"lines": "Quoted product does not belong to this RFQ."})
        if rfq_line.pk in normalized:
            raise ValidationError({"lines": f"{rfq_line.menu_item.name} appears more than once."})
        unit_cost = _decimal(
            row.get("unit_cost"), field="unit_cost",
            positive=True, allow_zero=True,
        ).quantize(Decimal("0.01"))
        raw_available = row.get("quantity_available")
        available = None
        if raw_available not in (None, ""):
            available = _decimal(
                raw_available, field="quantity_available",
                positive=True, allow_zero=True,
            )
            if available != available.quantize(Decimal("0.001")):
                raise ValidationError({"quantity_available": "Use at most three decimal places."})
        normalized[rfq_line.pk] = (
            rfq_line, unit_cost, available,
            row.get("promised_date"), (row.get("note") or "").strip()[:255],
        )
    if set(normalized) != set(requested):
        missing = [
            requested[line_id].menu_item.name
            for line_id in requested if line_id not in normalized
        ]
        raise ValidationError({
            "lines": "Record a quoted price for every requested product: " + ", ".join(missing)
        })

    shipping = _decimal(
        shipping_cost, field="shipping_cost", positive=True, allow_zero=True,
    ).quantize(Decimal("0.01"))
    other = _decimal(
        other_cost, field="other_cost", positive=True, allow_zero=True,
    ).quantize(Decimal("0.01"))
    if lead_time_days not in (None, ""):
        try:
            lead_time_days = int(lead_time_days)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"lead_time_days": "Enter a whole number of days."}) from exc
        if lead_time_days < 0 or lead_time_days > 3650:
            raise ValidationError({"lead_time_days": "Use a lead time between 0 and 3650 days."})
    else:
        lead_time_days = None

    locked.reference = (reference or "").strip()[:128]
    locked.shipping_cost = shipping
    locked.other_cost = other
    locked.lead_time_days = lead_time_days
    locked.availability_note = (availability_note or "").strip()[:255]
    locked.payment_terms = (payment_terms or "").strip()[:255]
    locked.valid_until = valid_until
    locked.status = SupplierQuoteStatus.SUBMITTED
    locked.save(update_fields=[
        "reference", "shipping_cost", "other_cost", "lead_time_days",
        "availability_note", "payment_terms", "valid_until", "status", "updated_at",
    ])

    locked.lines.all().delete()
    SupplierQuoteLine.objects.bulk_create([
        SupplierQuoteLine(
            tenant_id=locked.tenant_id,
            quote=locked,
            rfq_line=rfq_line,
            unit_cost=unit_cost,
            quantity_available=available,
            promised_date=promised_date,
            note=note,
        )
        for rfq_line, unit_cost, available, promised_date, note
        in normalized.values()
    ])
    if locked.rfq.status == PurchaseRfqStatus.DRAFT:
        locked.rfq.status = PurchaseRfqStatus.OPEN
        locked.rfq.save(update_fields=["status", "updated_at"])

    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="purchasing.supplier_quote_recorded",
        entity_type="supplier_quote",
        entity_id=str(locked.pk),
        payload={
            "rfq_id": str(locked.rfq_id),
            "supplier_id": str(locked.supplier_id),
            "shipping_cost": str(shipping),
            "other_cost": str(other),
            "lead_time_days": lead_time_days,
        },
    )
    return locked


def quote_comparison_rows(rfq: PurchaseRfq) -> list[dict]:
    rows = []
    # Detail views prefetch both relations; using the relation caches keeps the
    # comparison cost constant instead of querying requested lines per supplier.
    requested_lines = list(rfq.lines.all())
    quotes = list(rfq.quotes.all())
    quotes.sort(key=lambda quote: quote.supplier.name.lower())
    for quote in quotes:
        line_map = {line.rfq_line_id: line for line in quote.lines.all()}
        subtotal = Decimal("0.00")
        fully_quoted = quote.status in (
            SupplierQuoteStatus.SUBMITTED,
            SupplierQuoteStatus.ACCEPTED,
        )
        fully_available = fully_quoted
        quoted_lines = []
        for requested in requested_lines:
            response = line_map.get(requested.pk)
            if response is None:
                fully_quoted = False
                fully_available = False
                quoted_lines.append({
                    "rfq_line_id": requested.pk,
                    "item": requested.menu_item,
                    "quantity_requested": requested.quantity_requested,
                    "unit_cost": None,
                    "quantity_available": None,
                    "line_total": None,
                    "available": False,
                })
                continue
            line_total = (
                requested.quantity_requested * response.unit_cost
            ).quantize(Decimal("0.01"))
            subtotal += line_total
            available = (
                response.quantity_available is None
                or response.quantity_available >= requested.quantity_requested
            )
            fully_available = fully_available and available
            quoted_lines.append({
                "rfq_line_id": requested.pk,
                "item": requested.menu_item,
                "quantity_requested": requested.quantity_requested,
                "unit_cost": response.unit_cost,
                "quantity_available": response.quantity_available,
                "line_total": line_total,
                "available": available,
                "promised_date": response.promised_date,
                "note": response.note,
            })
        total = (subtotal + quote.shipping_cost + quote.other_cost).quantize(
            Decimal("0.01")
        )
        rows.append({
            "quote": quote,
            "supplier": quote.supplier,
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "shipping_cost": quote.shipping_cost,
            "other_cost": quote.other_cost,
            "total": total,
            "fully_quoted": fully_quoted,
            "fully_available": fully_available,
            "lines": quoted_lines,
        })
    eligible_totals = [
        row["total"] for row in rows
        if row["fully_quoted"] and row["fully_available"]
        and row["quote"].status in (
            SupplierQuoteStatus.SUBMITTED, SupplierQuoteStatus.ACCEPTED,
        )
    ]
    best = min(eligible_totals) if eligible_totals else None
    for row in rows:
        row["best_price"] = best is not None and row["total"] == best
    return rows


@transaction.atomic
def award_supplier_quote(*, quote, membership, user) -> PurchaseOrder:
    locked = (
        SupplierQuote.objects.select_for_update()
        .select_related("rfq", "rfq__outlet", "supplier", "converted_purchase_order")
        .get(pk=quote.pk)
    )
    rfq = PurchaseRfq.objects.select_for_update().get(pk=locked.rfq_id)
    if not outlet_belongs_to_membership(membership, rfq.outlet_id):
        raise ValidationError({"outlet": "You cannot award purchasing for this outlet."})
    if locked.converted_purchase_order_id:
        return locked.converted_purchase_order
    if rfq.status == PurchaseRfqStatus.AWARDED:
        raise ValidationError({"rfq": "This RFQ has already been awarded."})
    if rfq.status == PurchaseRfqStatus.CANCELLED:
        raise ValidationError({"rfq": "This RFQ is cancelled."})
    if locked.status != SupplierQuoteStatus.SUBMITTED:
        raise ValidationError({"quote": "Only a received quotation can be awarded."})
    if locked.valid_until and locked.valid_until < timezone.localdate():
        raise ValidationError({"quote": "This supplier quotation has expired."})

    requested = list(rfq.lines.select_related("menu_item").order_by("menu_item_id"))
    line_map = {
        line.rfq_line_id: line
        for line in locked.lines.select_related("rfq_line").all()
    }
    if any(line.pk not in line_map for line in requested):
        raise ValidationError({"quote": "Record a price for every RFQ product before award."})
    for line in requested:
        response = line_map[line.pk]
        if (
            response.quantity_available is not None
            and response.quantity_available < line.quantity_requested
        ):
            raise ValidationError({
                "quote": (
                    f"{line.menu_item.name} has only {response.quantity_available} "
                    f"available against {line.quantity_requested} requested."
                )
            })

    promised = [
        line_map[line.pk].promised_date
        for line in requested if line_map[line.pk].promised_date
    ]
    expected_date = max(promised) if promised else None
    if expected_date is None and locked.lead_time_days is not None:
        expected_date = timezone.localdate() + timedelta(days=locked.lead_time_days)
    if expected_date is None:
        expected_date = rfq.needed_by

    po = PurchaseOrder.objects.create(
        tenant_id=rfq.tenant_id,
        supplier=locked.supplier,
        outlet=rfq.outlet,
        status=PurchaseOrderStatus.DRAFT,
        reference=locked.reference or f"{rfq.reference} / {locked.supplier.name}",
        expected_date=expected_date,
        notes=(
            f"Awarded from {rfq.reference}. "
            f"Quoted freight {locked.shipping_cost}; other charges {locked.other_cost}. "
            f"{locked.payment_terms}"
        )[:1000],
        created_by=user,
        approval_status=PurchaseApprovalStatus.APPROVED,
        reviewed_by=user,
        reviewed_at=timezone.now(),
        review_note=f"Awarded supplier quotation for {rfq.reference}"[:512],
    )
    PurchaseOrderLine.objects.bulk_create([
        PurchaseOrderLine(
            purchase_order=po,
            menu_item=line.menu_item,
            quantity_ordered=line.quantity_requested,
            unit_cost=line_map[line.pk].unit_cost,
        )
        for line in requested
    ])

    locked.status = SupplierQuoteStatus.ACCEPTED
    locked.converted_purchase_order = po
    locked.save(update_fields=[
        "status", "converted_purchase_order", "updated_at",
    ])
    SupplierQuote.objects.filter(rfq=rfq).exclude(pk=locked.pk).update(
        status=SupplierQuoteStatus.REJECTED,
    )
    rfq.status = PurchaseRfqStatus.AWARDED
    rfq.save(update_fields=["status", "updated_at"])

    log_audit(
        tenant_id=rfq.tenant_id,
        user_id=user.pk if user else None,
        action="purchasing.rfq_awarded",
        entity_type="purchase_rfq",
        entity_id=str(rfq.pk),
        payload={
            "quote_id": str(locked.pk),
            "supplier_id": str(locked.supplier_id),
            "purchase_order_id": str(po.pk),
            "quoted_shipping_cost": str(locked.shipping_cost),
            "quoted_other_cost": str(locked.other_cost),
        },
    )
    return po
