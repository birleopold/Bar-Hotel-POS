"""Read-only purchasing exposure by PO; no currency guesses or posting.

Ordered value is only estimated where every line has an explicit unit cost.
Payments are actual supplier settlements, not a reduction of ordered quantity.
"""
from decimal import Decimal
from django.db.models import Sum
from .models import PurchaseOrder, PurchaseOrderStatus


def purchase_order_exposure(*, tenant, outlet=None, outlet_ids=None):
    qs = PurchaseOrder.objects.filter(tenant=tenant).select_related("supplier", "outlet").prefetch_related("lines")
    if outlet is not None:
        if outlet.site.tenant_id != tenant.pk:
            raise ValueError("outlet must belong to tenant")
        qs = qs.filter(outlet=outlet)
    if outlet_ids is not None:
        qs = qs.filter(outlet_id__in=outlet_ids)
    result = []
    for order in qs.exclude(status=PurchaseOrderStatus.CANCELLED):
        lines = list(order.lines.all())
        complete_costs = bool(lines) and all(line.unit_cost is not None for line in lines)
        ordered = sum((line.quantity_ordered * line.unit_cost for line in lines), Decimal("0")) if complete_costs else None
        received = sum((line.quantity_received * line.unit_cost for line in lines), Decimal("0")) if complete_costs else None
        paid = sum((p.amount for p in order.payments.all()), Decimal("0"))
        result.append({
            "order_id": order.pk,
            "outlet": order.outlet.name,
            "supplier": order.supplier.name,
            "status": order.status,
            "ordered_value": ordered,
            "received_value": received,
            "paid_amount": paid,
            "unpaid_received_value": max(Decimal("0"), received - paid) if received is not None else None,
            "missing_cost_data": not complete_costs,
        })
    return result
