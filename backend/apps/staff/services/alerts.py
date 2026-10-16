"""Deduplicated staff alerts from current stock, repairs and goods receipts.

Only the inbox refresh action materializes alerts. Automatic refresh is not
claimed until a scheduled producer is deployed. State is scoped to membership.
"""
from urllib.parse import urlencode

from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MembershipRole
from apps.audit.models import StaffNotification
from apps.inventory.models import StockBalance
from apps.lodging.models import MaintenanceStatus, RoomMaintenanceRequest
from apps.purchasing.models import PurchaseReceipt

from .membership import staff_accessible_outlets, sites_visible_for_membership
from .modules import get_tenant_staff_modules
from .scoping import staff_nav_visibility_scoped


MANAGER_ROLES = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
}


def refresh_staff_alerts(*, tenant, membership):
    """Idempotently refresh only the current staff member's authorized alerts."""
    if not membership.is_active or membership.tenant_id != tenant.pk:
        return 0
    outlets = staff_accessible_outlets(membership)
    outlet_ids = [outlet.pk for outlet in outlets]
    sites = sites_visible_for_membership(membership)
    site_ids = [site.pk for site in sites]
    modules = get_tenant_staff_modules(tenant)
    vis = staff_nav_visibility_scoped(membership, modules=modules, tenant=tenant)
    allowed_stock = [
        o.pk for o in outlets if "inventory" in get_tenant_staff_modules(tenant, outlet=o)
    ]
    allowed_buying = [
        o.pk for o in outlets if "purchasing" in get_tenant_staff_modules(tenant, outlet=o)
    ]
    active_by_type = {}
    created_count = 0

    def emit(source_type, source_id, title, body, url, priority="normal"):
        nonlocal created_count
        if not url.startswith("/staff/") or url.startswith("//"):
            return
        if len(title) > 160 or len(body) > 400:
            raise ValueError("Notification text is too long")
        key = str(source_id)
        if not key or len(key) > 128:
            return
        active_by_type.setdefault(source_type, set()).add(key)
        alert, created = StaffNotification.objects.update_or_create(
            tenant=tenant, recipient=membership, source_type=source_type,
            source_id=key,
            defaults={
                "title": title, "body": body, "url": url,
                "priority": priority, "active": True,
            },
        )
        if created:
            created_count += 1

    if vis.inventory and allowed_stock:
        active_by_type["low_stock"] = set()
        qs = StockBalance.objects.filter(
            tenant=tenant, outlet_id__in=allowed_stock,
            menu_item__track_inventory=True,
            menu_item__reorder_level__isnull=False,
            quantity__lte=F("menu_item__reorder_level"),
        ).select_related("menu_item", "outlet").order_by("outlet_id", "menu_item_id")
        for balance in qs.iterator(chunk_size=100):
            url = reverse("staff-inventory-balances") + "?" + urlencode({
                "low_stock": "1", "q": balance.menu_item.name[:80],
            })
            emit(
                "low_stock", balance.pk,
                f"Low stock: {balance.menu_item.name}"[:160],
                f"{balance.outlet.name}: {balance.quantity} available, reorder level {balance.menu_item.reorder_level}"[:400],
                url,
                "high" if balance.quantity <= 0 else "normal",
            )

    if vis.lodging and site_ids and membership.role in MANAGER_ROLES:
        active_by_type["repair"] = set()
        repairs = RoomMaintenanceRequest.objects.filter(
            tenant=tenant, room__room_type__site_id__in=site_ids,
        ).exclude(status=MaintenanceStatus.RESOLVED).select_related(
            "room", "room__room_type__site",
        )
        for repair in repairs.iterator(chunk_size=100):
            emit(
                "repair", repair.pk,
                f"Room {repair.room.name}: open repair"[:160],
                f"{repair.room.room_type.site.name}: {repair.title}"[:400],
                reverse("staff-lodging-maintenance"),
                "urgent" if repair.priority == "urgent" else "high",
            )

    if vis.purchasing and allowed_buying:
        active_by_type["delivery_issue"] = set()
        deliveries = PurchaseReceipt.objects.filter(
            tenant=tenant, purchase_order__outlet_id__in=allowed_buying,
        ).exclude(discrepancy_note="").select_related(
            "purchase_order", "purchase_order__supplier",
        )
        for receipt in deliveries.iterator(chunk_size=100):
            po = receipt.purchase_order
            emit(
                "delivery_issue", receipt.pk,
                "Goods delivery needs review",
                f"Supplier {po.supplier.name}: delivery {receipt.delivery_reference or str(receipt.pk)[:8]} requires a discrepancy review"[:400],
                reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk}),
                "high",
            )

    # Only change current categories the worker is eligible to refresh. A
    # disappearing record is archived from the inbox, not deleted.
    for source_type, keys in active_by_type.items():
        stale = StaffNotification.objects.filter(
            tenant=tenant, recipient=membership,
            source_type=source_type, active=True,
        )
        if keys:
            stale = stale.exclude(source_id__in=keys)
        stale.update(active=False)
    return created_count


def mark_alerts_read(*, tenant, membership, ids=None, all_visible=False):
    qs = StaffNotification.objects.filter(
        tenant=tenant, recipient=membership, active=True,
        read_at__isnull=True,
    )
    if not all_visible:
        qs = qs.filter(pk__in=list(ids or []))
    return qs.update(read_at=timezone.now())
