"""Scoped management destinations and live exceptions; no financial posting here."""
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q, Count, Sum, Max
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent, ExceptionPolicy, ExceptionReview, SensitiveActionApproval
from apps.audit.services import exception_fingerprint, log_audit
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.lodging.models import Reservation, ReservationStatus
from apps.pos.models import Order, PosShift, PosShiftStatus, Refund
from ..middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .membership import LINE_ROLE_OUTLET_TYPES, staff_accessible_outlets
from .workspace import resolve_staff_outlet
from .modules import get_tenant_staff_modules
from .scoping import staff_nav_visibility_scoped
from .exception_sources import EXTRA_KINDS, extra_exception_rows

EXCEPTION_KINDS = ("cash_variance", "refund", "low_stock", "overdue_departure", *EXTRA_KINDS)

MANAGER_ROLES = {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER}


def management_scope(request):
    if request.tenant_membership.role not in MANAGER_ROLES:
        raise PermissionDenied("This workspace is available to managers only.")
    outlets = staff_accessible_outlets(request.tenant_membership)
    current = resolve_staff_outlet(request, outlets)
    selected = outlets if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL else ([current] if current else [])
    modules = get_tenant_staff_modules(request.tenant, outlet=current)
    return selected, modules, staff_nav_visibility_scoped(request.tenant_membership, modules=modules, tenant=request.tenant, outlet=current)


@dataclass
class ExceptionRow:
    kind: str
    entity_id: str
    fingerprint: str
    title: str
    detail: str
    url: str
    review: object = None
    history: tuple = ()
    scope_outlet_id: object = None
    scope_site_id: object = None


def _row(kind, obj, title, detail, url, version, *, outlet_id=None, site_id=None):
    fingerprint = exception_fingerprint(version)
    outlet_id = outlet_id or getattr(obj, "outlet_id", None)
    if not outlet_id and getattr(obj, "order_id", None):
        outlet_id = obj.order.outlet_id
    if not outlet_id and getattr(obj, "purchase_order_id", None):
        outlet_id = obj.purchase_order.outlet_id
    return ExceptionRow(kind, str(obj.pk), fingerprint, title, detail, url, scope_outlet_id=outlet_id, scope_site_id=site_id or getattr(obj, "site_id", None))


def exception_rows(request, *, source=None):
    outlets, modules, vis = management_scope(request)
    outlet_ids = [o.pk for o in outlets]
    policy = ExceptionPolicy.objects.filter(tenant=request.tenant).first() or ExceptionPolicy()
    cutoff = timezone.now() - timedelta(days=policy.lookback_days)
    rows = []
    # A source-specific lookup revalidates any current record, even outside the first page.
    def limited(qs, kind):
        if source:
            return qs.filter(pk=source[1]) if source[0] == kind else qs.none()
        return qs[:50]

    def actor_label(user, fallback="Operator not recorded"):
        if user is None:
            return fallback
        return user.get_full_name() or user.email
    if "pos" in modules and vis.orders:
        shifts = PosShift.objects.filter(tenant=request.tenant, outlet_id__in=outlet_ids, status=PosShiftStatus.CLOSED, closed_at__gte=cutoff, counted_cash__isnull=False).annotate(variance=F("counted_cash") - F("expected_cash")).filter(Q(variance__gt=policy.cash_variance_threshold) | Q(variance__lt=-policy.cash_variance_threshold)).select_related("outlet", "workstation", "closed_by").order_by("-closed_at")
        for shift in limited(shifts, "cash_variance"):
            rows.append(_row(
                "cash_variance",
                shift,
                "Cash variance",
                (
                    f"{shift.outlet.name} · "
                    f"{shift.workstation.name if shift.workstation else 'Section register'} · "
                    f"{shift.variance:+.2f} · closed by {actor_label(shift.closed_by)}"
                ),
                reverse("staff-management-shift", kwargs={"shift_id": shift.pk}),
                (shift.expected_cash, shift.counted_cash, shift.closed_at),
            ))
        refunds = Refund.objects.filter(tenant=request.tenant, order__tenant=request.tenant, order__outlet_id__in=outlet_ids, created_at__gte=cutoff, amount__gte=policy.refund_threshold).select_related("order", "order__outlet", "recorded_by").order_by("-created_at")
        visible_refunds = list(limited(refunds, "refund"))
        # Aggregate from all refunds for each visible sale, including refunds
        # below the single-refund threshold. Do not treat the 50-row display
        # limit as a count limit or combine different currencies.
        refund_history = {}
        if visible_refunds:
            refund_history = {
                record["order_id"]: record
                for record in Refund.objects.filter(
                    tenant=request.tenant, order__tenant=request.tenant,
                    order__outlet_id__in=outlet_ids, created_at__gte=cutoff,
                    order_id__in={refund.order_id for refund in visible_refunds},
                ).order_by().values("order_id").annotate(
                    count=Count("pk"), total=Sum("amount"),
                )
            }
        for refund in visible_refunds:
            history = refund_history.get(refund.order_id, {})
            count = history.get("count", 1)
            detail = (
                f"{refund.order.outlet.name} · {refund.amount:.2f} "
                f"{refund.order.currency} · {refund.reason or 'No reason recorded'}"
                f" · recorded by {actor_label(refund.recorded_by)}"
            )
            if count > 1:
                detail += (
                    f" · {count} refunds on this sale within review window "
                    f"(total {history['total']:.2f} {refund.order.currency})"
                )
            if not refund.restocked:
                detail += " · Inventory not restocked by this refund"
            rows.append(_row(
                "refund", refund, "Refund review", detail,
                reverse("staff-order-detail", kwargs={"order_id": refund.order_id}),
                (refund.amount, refund.created_at, count, history.get("total"), refund.restocked),
            ))
    if "inventory" in modules and vis.inventory:
        balances = StockBalance.objects.filter(tenant=request.tenant, outlet_id__in=outlet_ids, menu_item__tenant=request.tenant, menu_item__track_inventory=True, menu_item__reorder_level__isnull=False, quantity__lte=F("menu_item__reorder_level")).select_related("outlet", "menu_item").order_by("quantity", "pk")
        for balance in limited(balances, "low_stock"):
            rows.append(_row("low_stock", balance, "Low stock", f"{balance.outlet.name} · {balance.menu_item.name}: {balance.quantity} (reorder {balance.menu_item.reorder_level})", reverse("staff-inventory-balances") + "?low_stock=1", (balance.quantity, balance.menu_item.reorder_level, balance.updated_at)))
    if "lodging" in modules and vis.lodging:
        from .membership import sites_visible_for_membership
        from .workspace import resolve_staff_site
        site = resolve_staff_site(request, sites_visible_for_membership(request.tenant_membership))
        stays = Reservation.objects.filter(tenant=request.tenant, site=site, status=ReservationStatus.CHECKED_IN, check_out__lt=timezone.localdate()).order_by("check_out", "pk") if site else Reservation.objects.none()
        for stay in limited(stays, "overdue_departure"):
            rows.append(_row("overdue_departure", stay, "Overdue departure", f"{stay.guest_name} · due {stay.check_out}", reverse("staff-lodging-reservation-detail", kwargs={"reservation_id": stay.pk}), (stay.check_out, stay.updated_at)))
    rows.extend(extra_exception_rows(request, policy, outlets, modules, vis, source, _row))
    reviews = {(r.kind, r.entity_id, r.fingerprint): r for r in ExceptionReview.objects.filter(tenant=request.tenant, entity_id__in=[r.entity_id for r in rows]).select_related("reviewed_by")}
    history = AuditEvent.objects.filter(tenant=request.tenant, action="exception.reviewed", payload__source_id__in=[r.entity_id for r in rows]).select_related("user").order_by("-created_at")[:200]
    histories = {}
    for event in history:
        histories.setdefault((event.payload.get("kind"), event.payload.get("source_id")), []).append(event)
    for row in rows:
        row.review = reviews.get((row.kind, row.entity_id, row.fingerprint))
        row.history = tuple(histories.get((row.kind, row.entity_id), []))
    return rows, policy


def exception_assignees(request):
    from apps.accounts.models import User
    users = [m.user_id for m in management_team(request) if m.role in MANAGER_ROLES]
    return User.objects.filter(pk__in=users, is_active=True)


def visible_cases(request):
    outlets, modules, vis = management_scope(request)
    from .membership import sites_visible_for_membership
    from .workspace import resolve_staff_site
    site = resolve_staff_site(request, sites_visible_for_membership(request.tenant_membership))
    scope = Q(scope_outlet_id__in=[o.pk for o in outlets])
    if site:
        scope |= Q(scope_outlet__isnull=True, scope_site=site)
    if request.tenant_membership.role in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}:
        scope |= Q(scope_outlet__isnull=True, scope_site__isnull=True)
    kinds = ["pin_failure"]
    if "pos" in modules and vis.orders:
        kinds += ["cash_variance", "refund", "discount", "line_discount", "void", "drawer_no_sale", "manual_price", "price_change", "offline_conflict"]
    if "inventory" in modules and vis.inventory:
        kinds += ["low_stock", "stock_adjustment"]
    if "purchasing" in modules and vis.purchasing:
        kinds += ["delivery_discrepancy"]
    if "lodging" in modules and vis.lodging:
        kinds += ["overdue_departure"]
    if "finance" in modules and vis.finance:
        kinds += ["efris_failure"]
    return ExceptionReview.objects.filter(scope, tenant=request.tenant, kind__in=kinds).select_related("reviewed_by", "assigned_to").order_by("-reviewed_at")


def _save_assessment(request, review, *, status, note, assigned_to=None, due_date=None):
    if status not in {"open", "reviewed", "follow_up", "resolved"} or not note.strip() or len(note.strip()) > 1000:
        raise ValidationError("Choose a review status and explain your assessment.")
    if assigned_to is not None and not exception_assignees(request).filter(pk=assigned_to.pk).exists():
        raise ValidationError("Choose an authorized manager in your scope.")
    if status == "follow_up" and (assigned_to is None or due_date is None):
        raise ValidationError("Follow-up requires an assigned manager and due date.")
    assigned_id = assigned_to.pk if assigned_to else None
    if review.status == status and review.note == note.strip() and review.assigned_to_id == assigned_id and review.due_date == due_date:
        return review
    before = review.status
    review.status, review.note = status, note.strip()
    review.reviewed_by, review.assigned_to, review.due_date = request.user, assigned_to, due_date
    review.save()
    log_audit(tenant_id=request.tenant.pk, user_id=request.user.pk, action="exception.reviewed", entity_type="exception_review", entity_id=str(review.pk), payload={"kind": review.kind, "source_id": review.entity_id, "fingerprint": review.fingerprint, "before": before, "status": status, "note": review.note, "assigned_to": str(assigned_id) if assigned_id else None, "due_date": str(due_date) if due_date else None})
    return review


@transaction.atomic
def review_exception(request, *, kind, entity_id, fingerprint, status, note, assigned_to=None, due_date=None):
    management_scope(request)
    rows, _ = exception_rows(request, source=(kind, entity_id))
    if not rows or rows[0].fingerprint != fingerprint:
        raise ValidationError("This exception changed or is no longer in your scope. Refresh before reviewing it.")
    row = rows[0]
    review, _ = ExceptionReview.objects.get_or_create(tenant=request.tenant, kind=kind, entity_id=entity_id, fingerprint=fingerprint, defaults={"status": "open", "note": "", "scope_outlet_id": row.scope_outlet_id, "scope_site_id": row.scope_site_id, "source_url": row.url})
    review = ExceptionReview.objects.select_for_update().get(pk=review.pk)
    return _save_assessment(request, review, status=status, note=note, assigned_to=assigned_to, due_date=due_date)


@transaction.atomic
def update_exception_case(request, *, case_id, status, note, assigned_to=None, due_date=None):
    review = visible_cases(request).select_for_update(of=("self",)).filter(pk=case_id).first()
    if review is None:
        raise ValidationError("This review is not in your scope.")
    return _save_assessment(request, review, status=status, note=note, assigned_to=assigned_to, due_date=due_date)


def management_shrink_watch(request, *, policy, limit=10):
    """Repeated negative inventory adjustments in the manager's current scope.

    Quantities are never added across different products/UoMs. This is an
    operational review aid over the existing stock ledger, not a valuation.
    """
    outlets, modules, vis = management_scope(request)
    if "inventory" not in modules or not vis.inventory or not outlets:
        return []
    cutoff = timezone.now() - timedelta(days=policy.lookback_days)
    rows = list(
        StockMovement.objects.filter(
            tenant=request.tenant,
            outlet__in=outlets,
            menu_item__tenant=request.tenant,
            created_at__gte=cutoff,
            quantity_change__lt=0,
            reason__in=[
                StockReason.WASTE,
                StockReason.ADJUST_OUT,
                StockReason.PHYSICAL_COUNT,
            ],
        )
        .values(
            "outlet_id",
            "outlet__name",
            "menu_item_id",
            "menu_item__name",
            "menu_item__unit_of_measure",
        )
        .annotate(
            event_count=Count("pk"),
            total_change=Sum("quantity_change"),
            last_seen=Max("created_at"),
        )
        .order_by("-event_count", "total_change", "-last_seen")[:limit]
    )
    for item in rows:
        item["quantity_removed"] = -item["total_change"]
    return rows


def management_orders(request):
    outlets, modules, vis = management_scope(request)
    if "pos" not in modules or not vis.orders:
        return Order.objects.none()
    return Order.objects.filter(tenant=request.tenant, outlet__in=outlets, status__in=["open", "closed"]).select_related("outlet").order_by("-created_at")[:50]


def management_approval_evidence(request):
    """Recent consumed sensitive approvals within the manager's current scope."""
    outlets, modules, vis = management_scope(request)
    if "pos" not in modules or not vis.orders or not outlets:
        return []
    approvals = list(
        SensitiveActionApproval.objects.filter(
            tenant=request.tenant,
            scope_outlet__in=outlets,
            used_at__isnull=False,
        )
        .select_related(
            "requester__user",
            "approver__user",
            "scope_outlet",
        )
        .order_by("-used_at", "-created_at")[:50]
    )
    order_ids = []
    for item in approvals:
        if item.entity_type != "order":
            continue
        try:
            order_ids.append(uuid.UUID(str(item.entity_id)))
        except (ValueError, TypeError, AttributeError):
            continue
    order_map = {
        str(order.pk): order
        for order in Order.objects.filter(
            tenant=request.tenant,
            outlet__in=outlets,
            pk__in=order_ids,
        ).only("id", "bill_reference", "outlet_id")
    }
    for item in approvals:
        order = order_map.get(item.entity_id)
        item.receipt_label = (
            order.bill_reference or str(order.pk)
            if order is not None
            else item.entity_id
        )
        item.source_url = (
            reverse("staff-order-detail", kwargs={"order_id": order.pk})
            if order is not None
            else ""
        )
        intent = item.intent_payload if isinstance(item.intent_payload, dict) else {}
        parts = []
        if intent.get("amount"):
            parts.append(f"amount {intent['amount']}")
        if intent.get("quantity"):
            parts.append(f"qty {intent['quantity']}")
        if intent.get("reason"):
            parts.append(f"reason: {intent['reason']}")
        item.intent_summary = " · ".join(parts) or "Exact transaction intent recorded"
    return approvals


def management_team(request):
    outlets, _, _ = management_scope(request)
    allowed = Q(pk__in=[])
    for outlet in outlets:
        roles = [role for role, _ in MembershipRole.choices if role not in LINE_ROLE_OUTLET_TYPES or outlet.outlet_type in LINE_ROLE_OUTLET_TYPES[role]]
        allowed |= Q(role__in=roles) & (Q(outlets=outlet) | Q(outlets__isnull=True)) & (Q(sites=outlet.site_id) | Q(sites__isnull=True))
    if not outlets:
        from .membership import sites_visible_for_membership
        from .workspace import resolve_staff_site
        site = resolve_staff_site(request, sites_visible_for_membership(request.tenant_membership))
        if site:
            allowed = Q(outlets__isnull=True) & (Q(sites=site) | Q(sites__isnull=True))
    return Membership.objects.filter(allowed, tenant=request.tenant, is_active=True, user__is_active=True).select_related("user").distinct().order_by("user__email")[:100]
