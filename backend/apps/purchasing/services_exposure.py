"""Read-only purchasing exposure by PO; no currency guesses or posting.

Ordered value is only estimated where every line has an explicit unit cost.
Payments are actual supplier settlements, not a reduction of ordered quantity.
"""
from decimal import Decimal
from .models import PurchaseOrder, PurchaseOrderStatus


def purchase_order_exposure(*, tenant, outlet=None, outlet_ids=None):
    qs = PurchaseOrder.objects.filter(tenant=tenant).select_related("supplier", "outlet").prefetch_related("lines", "payments", "invoices", "credits")
    if outlet is not None:
        if outlet.site.tenant_id != tenant.pk:
            raise ValueError("outlet must belong to tenant")
        qs = qs.filter(outlet=outlet)
    if outlet_ids is not None:
        qs = qs.filter(outlet_id__in=outlet_ids)
    result = []
    for order in qs.exclude(status=PurchaseOrderStatus.CANCELLED):
        lines = list(order.lines.all())
        received_lines = [line for line in lines if line.quantity_received > 0]
        full_order_costs = bool(lines) and all(line.unit_cost is not None for line in lines)
        complete_received_costs = all(line.unit_cost is not None for line in received_lines)
        ordered = (
            sum((line.quantity_ordered * line.unit_cost).quantize(Decimal("0.01"))
                for line in lines)
            if full_order_costs else None
        )
        received = (
            sum(((line.quantity_received * line.unit_cost).quantize(Decimal("0.01"))
                for line in received_lines), Decimal("0"))
            if complete_received_costs else None
        )
        paid = sum((payment.amount for payment in order.payments.all()), Decimal("0"))
        invoices = list(order.invoices.all())
        invoiced = sum((inv.amount for inv in invoices), Decimal("0"))
        credited = sum((credit.amount for credit in order.credits.all()), Decimal("0"))
        net_invoiced = invoiced - credited
        next_due = min((inv.due_date for inv in invoices), default=None)
        result.append({
            "order_id": order.pk,
            "outlet": order.outlet.name,
            "supplier": order.supplier.name,
            "status": order.status,
            "ordered_value": ordered,
            "received_value": received,
            "paid_amount": paid,
            "invoiced_value": invoiced,
            "credited_value": credited,
            "net_invoiced_value": net_invoiced,
            "earliest_invoice_due_date": next_due,
            "unbilled_received_value": max(Decimal("0"), received - net_invoiced) if received is not None else None,
            # A PO-level balance only: payments are not linked to individual invoice lines.
            "unpaid_invoiced_value": max(Decimal("0"), net_invoiced - paid),
            "unpaid_received_value": max(Decimal("0"), received - paid - credited) if received is not None else None,
            "missing_cost_data": not complete_received_costs,
            "missing_order_cost_data": not full_order_costs,
        })
    return result



def supplier_invoice_settlement_rows(*, po, today=None):
    """Read-only invoice balances: never guess which invoice old payments settled."""
    from datetime import date
    from django.db.models import Sum
    current = today or date.today()
    unallocated = po.payments.filter(invoice__isnull=True).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0")
    rows = []
    for invoice in po.invoices.prefetch_related("credits", "allocated_payments").order_by("due_date", "reference"):
        credited = sum((credit.amount for credit in invoice.credits.all()), Decimal("0"))
        allocated = sum((payment.amount for payment in invoice.allocated_payments.all()), Decimal("0"))
        unpaid = max(Decimal("0"), invoice.amount - credited - allocated)
        rows.append({
            "invoice": invoice, "credited": credited, "paid": allocated,
            "unpaid": unpaid, "overdue_days": max(0, (current - invoice.due_date).days) if unpaid else 0,
            "is_exact": unallocated == 0,
        })
    return rows, unallocated
