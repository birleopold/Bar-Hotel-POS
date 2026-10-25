"""Read-only purchasing exposure by PO; no currency guesses or posting.

Ordered value is only estimated where every line has an explicit unit cost.
Payments are actual supplier settlements, not a reduction of ordered quantity.
"""
from decimal import Decimal
from .models import PurchaseOrder, PurchaseOrderStatus


def purchase_order_exposure(*, tenant, outlet=None, outlet_ids=None, today=None):
    """PO-level payable exposure with truthful invoice aging.

    Total invoice liability can be exact even when historical payments are not
    assigned to a document. Invoice due dates/overdue amounts are only exposed
    when every supplier payment on the PO has a verified invoice allocation.
    """
    from django.utils import timezone

    current = today or timezone.localdate()
    qs = (
        PurchaseOrder.objects.filter(tenant=tenant)
        .select_related("supplier", "outlet")
        .prefetch_related(
            "lines",
            "payments",
            "invoices__credits",
            "invoices__allocated_payments",
            "credits",
        )
    )
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
        payments = list(order.payments.all())
        paid = sum((payment.amount for payment in payments), Decimal("0"))
        unallocated = sum(
            (payment.amount for payment in payments if payment.invoice_id is None),
            Decimal("0"),
        )
        invoices = list(order.invoices.all())
        invoiced = sum((inv.amount for inv in invoices), Decimal("0"))
        credited = sum((credit.amount for credit in order.credits.all()), Decimal("0"))
        net_invoiced = invoiced - credited

        invoice_balances = []
        for invoice in invoices:
            invoice_credited = sum(
                (credit.amount for credit in invoice.credits.all()),
                Decimal("0"),
            )
            invoice_paid = sum(
                (payment.amount for payment in invoice.allocated_payments.all()),
                Decimal("0"),
            )
            invoice_balances.append((
                invoice,
                max(Decimal("0"), invoice.amount - invoice_credited - invoice_paid),
            ))

        # Never assign a legacy PO-level payment to an invoice by assumption.
        # Exact due-date aging resumes once those payments are explicitly linked.
        invoice_aging_exact = unallocated == 0
        if invoice_aging_exact:
            unpaid_invoice_rows = [
                (invoice, unpaid)
                for invoice, unpaid in invoice_balances
                if unpaid > 0
            ]
            earliest_unpaid_due = min(
                (invoice.due_date for invoice, _ in unpaid_invoice_rows),
                default=None,
            )
            overdue_rows = [
                (invoice, unpaid)
                for invoice, unpaid in unpaid_invoice_rows
                if invoice.due_date < current
            ]
            overdue_invoiced = sum(
                (unpaid for _, unpaid in overdue_rows),
                Decimal("0"),
            )
            max_overdue_days = max(
                ((current - invoice.due_date).days for invoice, _ in overdue_rows),
                default=0,
            )
        else:
            earliest_unpaid_due = None
            overdue_invoiced = None
            max_overdue_days = None

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
            # Compatibility key now means the next verified unpaid due date.
            "earliest_invoice_due_date": earliest_unpaid_due,
            "earliest_unpaid_invoice_due_date": earliest_unpaid_due,
            "invoice_aging_exact": invoice_aging_exact,
            "unallocated_payment_amount": unallocated,
            "overdue_invoiced_value": overdue_invoiced,
            "max_overdue_days": max_overdue_days,
            "unbilled_received_value": max(Decimal("0"), received - net_invoiced) if received is not None else None,
            # This PO-level balance remains exact even with unallocated payments.
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
