"""Additional exception sources, with permission-safe descriptions and links."""
from datetime import timedelta
from django.db.models import Q, CharField, Value, Count
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

EXTRA_KINDS = ("discount", "line_discount", "void", "drawer_no_sale", "manual_price", "price_change", "stock_adjustment", "delivery_discrepancy", "efris_failure", "offline_conflict", "pin_failure")


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
        lines = OrderLine.objects.filter(
            order__tenant=request.tenant,
            order__outlet_id__in=ids,
        ).select_related("order", "voided_by")
        for obj in limited(lines.filter(updated_at__gte=cutoff, line_discount_amount__gt=policy.discount_threshold, is_voided=False).order_by("-updated_at"), "line_discount"):
            result.append(row("line_discount", obj, "Line discount", f"{obj.label} · {obj.line_discount_amount} {obj.order.currency}", reverse("staff-order-detail", kwargs={"order_id":obj.order_id}), (obj.line_discount_amount, obj.updated_at)))
        # Investigate repeated voids on the same sale without mistaking the
        # most recent 50 displayed records for a complete frequency count.
        # Limit the grouped query to orders actually shown to the manager.
        visible_voids = list(limited(
            lines.filter(is_voided=True, voided_at__gte=cutoff).order_by("-voided_at"),
            "void",
        ))
        repeated_voids = {}
        cashier_voids = {}
        if visible_voids:
            repeated_voids = dict(
                lines.filter(
                    is_voided=True, voided_at__gte=cutoff,
                    order_id__in={item.order_id for item in visible_voids},
                ).order_by().values("order_id").annotate(total=Count("pk"))
                .values_list("order_id", "total")
            )
            cashier_ids = {item.voided_by_id for item in visible_voids if item.voided_by_id}
            if cashier_ids:
                cashier_voids = dict(
                    lines.filter(
                        is_voided=True,
                        voided_at__gte=cutoff,
                        voided_by_id__in=cashier_ids,
                    ).order_by().values("voided_by_id").annotate(total=Count("pk"))
                    .values_list("voided_by_id", "total")
                )
        for obj in visible_voids:
            count = repeated_voids.get(obj.order_id, 0)
            cashier_count = cashier_voids.get(obj.voided_by_id, 0)
            cashier = (
                obj.voided_by.get_full_name() or obj.voided_by.email
                if obj.voided_by_id and obj.voided_by
                else "Unknown worker"
            )
            detail = (
                f"{obj.label} · {obj.void_reason or 'No reason recorded'}"
                f" · voided by {cashier}"
            )
            if count > 1:
                detail += f" · {count} voided lines on this sale"
            if cashier_count > 1:
                detail += f" · {cashier_count} voided lines by this worker in the review window"
            result.append(row(
                "void",
                obj,
                "Voided line",
                detail,
                reverse("staff-order-detail", kwargs={"order_id":obj.order_id}),
                (obj.voided_at, obj.void_reason, count, obj.voided_by_id, cashier_count),
            ))
        # A manual price marker is a review signal, not proof that a shelf
        # price was overridden. Historical menu prices are not reconstructed.
        manual_lines = lines.filter(
            pricing_source="manual",
            is_voided=False,
            line_discount_amount=0,
            created_at__gte=cutoff,
        ).order_by("-created_at")
        for obj in limited(manual_lines, "manual_price"):
            result.append(row(
                "manual_price", obj, "Manual price entry",
                f"{obj.label} · {obj.quantity} × {obj.unit_price} {obj.order.currency}"
                " · compare with the authorized selling price",
                reverse("staff-order-detail", kwargs={"order_id": obj.order_id}),
                (obj.unit_price, obj.quantity, obj.updated_at, obj.pricing_source),
            ))
        price_events_qs = AuditEvent.objects.filter(
            tenant=request.tenant,
            action__in=[
                "catalog.unit_price_changed",
                "catalog.outlet_price_override_changed",
            ],
            created_at__gte=cutoff,
        ).select_related("user").order_by("-created_at")
        price_events = list(limited(price_events_qs, "price_change"))
        scoped_price_events = []
        outlet_id_strings = {str(i) for i in ids}
        for obj in price_events:
            payload = obj.payload if isinstance(obj.payload, dict) else {}
            event_outlet = str(payload.get("outlet_id") or "")
            explicit = {str(value) for value in (payload.get("outlet_ids") or [])}
            applies_all = bool(payload.get("applies_to_all_outlets"))
            if applies_all or event_outlet in outlet_id_strings or bool(explicit & outlet_id_strings):
                scoped_price_events.append(obj)
        for obj in scoped_price_events:
            payload = obj.payload if isinstance(obj.payload, dict) else {}
            actor = (
                obj.user.get_full_name() or obj.user.email
                if obj.user_id and obj.user
                else "Former or system user"
            )
            scope_label = payload.get("outlet_name") or (
                "All sales areas" if payload.get("applies_to_all_outlets") else "Selected sales areas"
            )
            detail = (
                f"{payload.get('item_name') or 'Product'} · {scope_label}"
                f" · {payload.get('before', '?')} → {payload.get('after', '?')}"
                f" · changed by {actor}"
            )
            result.append(row(
                "price_change",
                obj,
                "Selling price changed",
                detail,
                source_url("price_change", obj),
                (
                    obj.pk,
                    obj.created_at,
                    obj.action,
                    payload.get("before"),
                    payload.get("after"),
                    obj.user_id,
                ),
                outlet_id=payload.get("outlet_id") or None,
            ))
        drawer_events = list(limited(
            AuditEvent.objects.filter(
                tenant=request.tenant,
                action="pos.drawer_no_sale_opened",
                created_at__gte=cutoff,
                payload__outlet_id__in=[str(i) for i in ids],
            ).select_related("user").order_by("-created_at"),
            "drawer_no_sale",
        ))
        drawer_user_counts = {}
        if drawer_events:
            user_ids = {event.user_id for event in drawer_events if event.user_id}
            if user_ids:
                drawer_user_counts = dict(
                    AuditEvent.objects.filter(
                        tenant=request.tenant,
                        action="pos.drawer_no_sale_opened",
                        created_at__gte=cutoff,
                        payload__outlet_id__in=[str(i) for i in ids],
                        user_id__in=user_ids,
                    ).order_by().values("user_id").annotate(total=Count("pk"))
                    .values_list("user_id", "total")
                )
        for obj in drawer_events:
            worker = (
                obj.user.get_full_name() or obj.user.email
                if obj.user_id and obj.user
                else "Unknown worker"
            )
            count = drawer_user_counts.get(obj.user_id, 0)
            detail = f"{obj.payload.get('reason') or 'No reason recorded'} · recorded by {worker}"
            if count > 1:
                detail += f" · {count} no-sale openings by this worker in the review window"
            result.append(row(
                "drawer_no_sale",
                obj,
                "No-sale drawer opening",
                detail,
                source_url("drawer_no_sale", obj),
                (obj.pk, obj.created_at, obj.user_id, count, obj.payload.get("reason")),
                outlet_id=obj.payload.get("outlet_id") or None,
            ))
        queue = OfflineQueuedOperation.objects.filter(tenant=request.tenant, outlet_id__in=ids).filter(Q(status="failed") | Q(status="pending", created_at__lt=timezone.now()-timedelta(hours=policy.offline_age_hours))).order_by("created_at")
        for obj in limited(queue, "offline_conflict"):
            result.append(row("offline_conflict", obj, "Offline operation needs attention", f"{obj.operation_type} · {obj.status} · queued {obj.created_at:%Y-%m-%d %H:%M}", source_url("offline_conflict",obj), (obj.status, obj.updated_at)))
    if "inventory" in modules and vis.inventory:
        movements = StockMovement.objects.filter(tenant=request.tenant, outlet_id__in=ids, menu_item__tenant=request.tenant, created_at__gte=cutoff, reason__in=[StockReason.ADJUST_IN, StockReason.ADJUST_OUT, StockReason.WASTE, StockReason.PHYSICAL_COUNT]).filter(Q(quantity_change__gt=policy.stock_adjustment_threshold) | Q(quantity_change__lt=-policy.stock_adjustment_threshold)).select_related("menu_item").order_by("-created_at")
        for obj in limited(movements,"stock_adjustment"):
            result.append(row("stock_adjustment",obj,"Stock adjustment",f"{obj.menu_item.name} · {obj.quantity_change:+} · {obj.get_reason_display()}",source_url("stock_adjustment",obj),(obj.quantity_change,obj.created_at)))
    if "purchasing" in modules and vis.purchasing:
        receipts = PurchaseReceipt.objects.filter(tenant=request.tenant, purchase_order__tenant=request.tenant, purchase_order__outlet_id__in=ids, created_at__gte=cutoff).exclude(discrepancy_note="").select_related("purchase_order").order_by("-created_at")
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
