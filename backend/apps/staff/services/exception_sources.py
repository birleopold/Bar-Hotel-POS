"""Additional exception sources, with permission-safe descriptions and links."""
from datetime import timedelta
from django.db.models import Q, CharField, Value
from django.db.models.functions import Cast, Replace
from django.utils import timezone
from django.urls import reverse
from apps.accounts.models import MembershipRole
from apps.audit.models import AuditEvent
from apps.finance.models import FinancePostingLink
from apps.inventory.models import StockMovement, StockReason
from apps.integrations.models import EfrisSubmission
from apps.pos.models import Order, OrderLine, OfflineQueuedOperation, Payment, Refund
from apps.purchasing.models import PurchaseReceipt

EXTRA_KINDS = ("discount", "line_discount", "void", "stock_adjustment", "delivery_discrepancy", "efris_failure", "offline_conflict", "pin_failure")


def extra_exception_rows(request, policy, outlets, modules, vis, source, row):
    ids = [o.pk for o in outlets]
    cutoff = timezone.now() - timedelta(days=policy.lookback_days)
    result = []
    def limited(qs, kind):
        if source:
            return qs.filter(pk=source[1]) if source[0] == kind else qs.none()
        return qs[:50]
    def source_url(kind, obj):
        return reverse("staff-management-source", kwargs={"kind": kind, "entity_id": obj.pk})
    if "pos" in modules and vis.orders:
        orders = Order.objects.filter(tenant=request.tenant, outlet_id__in=ids, updated_at__gte=cutoff, discount_amount__gt=policy.discount_threshold).order_by("-updated_at")
        for obj in limited(orders, "discount"):
            result.append(row("discount", obj, "Order discount", f"{obj.discount_amount} {obj.currency}", reverse("staff-order-detail", kwargs={"order_id":obj.pk}), (obj.discount_amount, obj.updated_at)))
        lines = OrderLine.objects.filter(order__tenant=request.tenant, order__outlet_id__in=ids).select_related("order")
        for obj in limited(lines.filter(updated_at__gte=cutoff, line_discount_amount__gt=policy.discount_threshold, is_voided=False).order_by("-updated_at"), "line_discount"):
            result.append(row("line_discount", obj, "Line discount", f"{obj.label} · {obj.line_discount_amount} {obj.order.currency}", reverse("staff-order-detail", kwargs={"order_id":obj.order_id}), (obj.line_discount_amount, obj.updated_at)))
        for obj in limited(lines.filter(is_voided=True, voided_at__gte=cutoff).order_by("-voided_at"), "void"):
            result.append(row("void", obj, "Voided line", f"{obj.label} · {obj.void_reason}", reverse("staff-order-detail", kwargs={"order_id":obj.order_id}), (obj.voided_at, obj.void_reason)))
        queue = OfflineQueuedOperation.objects.filter(tenant=request.tenant, outlet_id__in=ids).filter(Q(status="failed") | Q(status="pending", created_at__lt=timezone.now()-timedelta(hours=policy.offline_age_hours))).order_by("created_at")
        for obj in limited(queue, "offline_conflict"):
            result.append(row("offline_conflict", obj, "Offline operation needs attention", f"{obj.operation_type} · {obj.status} · queued {obj.created_at:%Y-%m-%d %H:%M}", source_url("offline_conflict",obj), (obj.status, obj.updated_at)))
    if "inventory" in modules and vis.inventory:
        movements = StockMovement.objects.filter(tenant=request.tenant, outlet_id__in=ids, menu_item__tenant=request.tenant, created_at__gte=cutoff, reason__in=[StockReason.ADJUST_IN, StockReason.ADJUST_OUT, StockReason.WASTE, StockReason.PHYSICAL_COUNT]).filter(Q(quantity_change__gt=policy.stock_adjustment_threshold) | Q(quantity_change__lt=-policy.stock_adjustment_threshold)).select_related("menu_item").order_by("-created_at")
        for obj in limited(movements,"stock_adjustment"):
            result.append(row("stock_adjustment",obj,"Stock adjustment",f"{obj.menu_item.name} · {obj.quantity_change:+} · {obj.get_reason_display()}",source_url("stock_adjustment",obj),(obj.quantity_change,obj.created_at)))
    if "purchasing" in modules and vis.purchasing:
        receipts = PurchaseReceipt.objects.filter(tenant=request.tenant, purchase_order__tenant=request.tenant, purchase_order__outlet_id__in=ids).exclude(discrepancy_note="").select_related("purchase_order").order_by("-created_at")
        for obj in limited(receipts,"delivery_discrepancy"):
            result.append(row("delivery_discrepancy",obj,"Delivery discrepancy",obj.discrepancy_note,reverse("staff-purchasing-order-detail",kwargs={"po_id":obj.purchase_order_id}),(obj.discrepancy_note,obj.updated_at)))
    if "finance" in modules and vis.finance:
        site_ids = {o.site_id for o in outlets}
        if not site_ids:
            from .membership import sites_visible_for_membership
            from .workspace import resolve_staff_site
            site = resolve_staff_site(request,sites_visible_for_membership(request.tenant_membership))
            site_ids = {site.pk} if site else set()
        # Posting links use string IDs; normalize UUID text consistently on SQLite/PostgreSQL.
        def norm(field): return Replace(Cast(field,CharField()),Value("-"),Value(""))
        allowed_payments = Payment.objects.filter(tenant=request.tenant,order__outlet_id__in=ids).annotate(key=norm("pk")).values("key")
        allowed_refunds = Refund.objects.filter(tenant=request.tenant,order__outlet_id__in=ids).annotate(key=norm("pk")).values("key")
        links = FinancePostingLink.objects.filter(tenant=request.tenant).annotate(key=norm("source_id")).filter(Q(source_type="pos_payment",key__in=allowed_payments) | Q(source_type="pos_refund",key__in=allowed_refunds)).values("cashbook_entry_id")
        fiscal = EfrisSubmission.objects.filter(tenant=request.tenant,cashbook_entry__tenant=request.tenant,cashbook_entry__site_id__in=site_ids,status="failed").filter(Q(cashbook_entry__posting_link__isnull=True) | ~Q(cashbook_entry__posting_link__source_type__in=["pos_payment","pos_refund"]) | Q(cashbook_entry_id__in=links)).select_related("cashbook_entry", "cashbook_entry__posting_link").order_by("created_at")
        fiscal_rows = list(limited(fiscal,"efris_failure"))
        payment_ids, refund_ids = [], []
        for obj in fiscal_rows:
            link = getattr(obj.cashbook_entry, "posting_link", None)
            if link and link.source_type == "pos_payment": payment_ids.append(link.source_id)
            if link and link.source_type == "pos_refund": refund_ids.append(link.source_id)
        source_outlets = {str(o.pk): o.order.outlet_id for o in Payment.objects.filter(pk__in=payment_ids).select_related("order")}
        source_outlets.update({str(o.pk): o.order.outlet_id for o in Refund.objects.filter(pk__in=refund_ids).select_related("order")})
        for obj in fiscal_rows:
            link = getattr(obj.cashbook_entry, "posting_link", None)
            outlet_id = source_outlets.get(link.source_id) if link else None
            result.append(row("efris_failure",obj,"Fiscal submission failed",f"Attempts: {obj.attempts} · source {obj.cashbook_entry_id}",source_url("efris_failure",obj),(obj.status,obj.updated_at),site_id=obj.cashbook_entry.site_id,outlet_id=outlet_id))
    events = AuditEvent.objects.filter(tenant=request.tenant,action="staff.pin_failed",created_at__gte=cutoff,payload__failure_count__gte=policy.pin_failure_threshold)
    scoped = Q(payload__outlet_id__in=[str(i) for i in ids])
    if request.tenant_membership.role in {MembershipRole.OWNER,MembershipRole.TENANT_ADMIN}:
        scoped |= Q(payload__outlet_id__in=["", "__all__"])
    for obj in limited(events.filter(scoped).order_by("-created_at"),"pin_failure"):
        outlet_id = obj.payload.get("outlet_id")
        result.append(row("pin_failure",obj,"Failed PIN attempt",f"Failure count: {obj.payload.get('failure_count')} · terminal locked: {bool(obj.payload.get('locked'))}",source_url("pin_failure",obj),(obj.pk,obj.created_at),outlet_id=outlet_id if outlet_id not in {"","__all__"} else None))
    return result
