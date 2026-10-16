"""One permission-aware lookup service for global search and command palette.

All returned links point to existing staff views. Never query data outside the
active tenant, assigned properties or permitted outlets. No search terms are
written to logs or stored, because they may contain guest identifiers.
"""
import uuid
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import MenuItem
from apps.customers.models import Customer
from apps.events.models import EventBooking
from apps.lodging.models import Folio, Reservation, Room
from apps.pos.models import Order
from apps.purchasing.models import PurchaseOrder, Supplier
from .customers import can_manage_customers, visible_customers
from .membership import sites_visible_for_membership, staff_accessible_outlets
from .modules import get_tenant_staff_modules
from .scoping import staff_nav_visibility_scoped

CATEGORIES = (
    "Orders", "Reservations", "Rooms", "Customers", "Items",
    "Suppliers", "Purchase orders", "Events", "Guest folios", "Team",
)
MANAGEMENT_ROLES = frozenset({
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})


def staff_global_search(*, tenant, membership, user, query, per_group=5, page=1):
    if not membership or not membership.is_active or membership.tenant_id != tenant.pk:
        return []
    query = (query or "").strip()[:80]
    if len(query) < 2:
        return []
    per_group = max(1, min(int(per_group), 8))
    page = max(1, min(int(page), 100))
    offset = (page - 1) * per_group
    current_outlets = staff_accessible_outlets(membership)
    outlet_ids = [outlet.pk for outlet in current_outlets]
    sites = sites_visible_for_membership(membership)
    site_ids = [site.pk for site in sites]
    modules = get_tenant_staff_modules(tenant)
    nav = staff_nav_visibility_scoped(membership, modules=modules, tenant=tenant)
    groups = []
    try:
        record_id = uuid.UUID(query)
    except (ValueError, AttributeError):
        record_id = None

    def add_group(name, entries):
        if entries:
            groups.append({
                "name": name, "items": entries[:per_group],
                "has_more": len(entries) > per_group,
            })

    def exact_pk():
        return Q(pk=record_id) if record_id else Q(pk__isnull=True)

    if nav.orders and outlet_ids:
        qs = Order.objects.filter(tenant=tenant, outlet_id__in=outlet_ids).filter(
            Q(bill_reference__icontains=query)
            | Q(table_label__icontains=query) | exact_pk()
        ).select_related("outlet").order_by("-created_at")[offset:offset+per_group+1]
        add_group("Orders", [{
            "title": order.bill_reference or ("Order " + str(order.pk)[:8]),
            "subtitle": f"{order.outlet.name} · {order.get_status_display()}",
            "url": reverse("staff-order-detail", kwargs={"order_id": order.pk}),
        } for order in qs])

    if nav.lodging and site_ids:
        qs = Reservation.objects.filter(tenant=tenant, site_id__in=site_ids).filter(
            Q(guest_name__icontains=query) | exact_pk()
        ).select_related("site").order_by("-created_at")[offset:offset+per_group+1]
        add_group("Reservations", [{
            "title": res.guest_name, "subtitle": f"{res.site.name} · {res.get_status_display()}",
            "url": reverse("staff-lodging-reservation-detail", kwargs={"reservation_id": res.pk}),
        } for res in qs])

        rooms = Room.objects.filter(
            room_type__tenant=tenant, room_type__site_id__in=site_ids,
        ).filter(Q(name__icontains=query) | exact_pk()).select_related(
            "room_type", "room_type__site"
        ).order_by("name")[offset:offset+per_group+1]
        add_group("Rooms", [{
            "title": "Room " + room.name,
            "subtitle": f"{room.room_type.site.name} · {room.get_status_display()}",
            "url": reverse("staff-lodging-rooms"),
        } for room in rooms])

        folios = Folio.objects.filter(
            tenant=tenant, site_id__in=site_ids
        ).filter(Q(guest_name__icontains=query) | exact_pk()).select_related(
            "site"
        ).order_by("-created_at")[offset:offset+per_group+1]
        add_group("Guest folios", [{
            "title": folio.guest_name,
            "subtitle": f"{folio.site.name} · Guest folio",
            "url": reverse("staff-lodging-folio-detail", kwargs={"folio_id": folio.pk}),
        } for folio in folios])

    if can_manage_customers(membership) and (nav.orders or nav.lodging or nav.events):
        customers = visible_customers(membership, user).filter(
            Q(name__icontains=query) | Q(email__icontains=query)
            | Q(phone__icontains=query) | exact_pk()
        ).order_by("name")[offset:offset+per_group+1]
        add_group("Customers", [{
            "title": cust.name, "subtitle": "Customer account",
            "url": reverse("staff-customer-detail", kwargs={"customer_id": cust.pk}),
        } for cust in customers])

    if (nav.menu or nav.inventory) and outlet_ids:
        # A product is accessible when offered in a permitted outlet, or when
        # no outlet restrictions were configured for that product.
        from django.db.models import Exists, OuterRef
        from apps.catalog.models import MenuItemOutlet
        links = MenuItemOutlet.objects.filter(menu_item_id=OuterRef("pk"))
        allowed_links = links.filter(outlet_id__in=outlet_ids)
        items = MenuItem.objects.filter(tenant=tenant).alias(
            any_link=Exists(links), permitted_link=Exists(allowed_links),
        ).filter(Q(any_link=False) | Q(permitted_link=True)).filter(
            Q(name__icontains=query) | Q(sku__icontains=query)
            | Q(barcode__icontains=query) | exact_pk()
        ).order_by("name")[offset:offset+per_group+1]
        destination = reverse("staff-menu" if nav.menu else "staff-inventory-balances")
        add_group("Items", [{
            "title": item.name, "subtitle": ("SKU " + item.sku) if item.sku else "Catalog item",
            "url": destination,
        } for item in items])

    if nav.purchasing and outlet_ids:
        # Suppliers are tenant-level (not section restricted) in existing UI;
        # POs must always be limited to accessible receiving outlets.
        suppliers = Supplier.objects.filter(tenant=tenant).filter(
            Q(name__icontains=query) | exact_pk()
        ).order_by("name")[offset:offset+per_group+1]
        add_group("Suppliers", [{
            "title": supplier.name, "subtitle": "Supplier",
            "url": reverse("staff-purchasing-suppliers"),
        } for supplier in suppliers])
        pos = PurchaseOrder.objects.filter(
            tenant=tenant, outlet_id__in=outlet_ids,
        ).filter(Q(reference__icontains=query) | Q(supplier__name__icontains=query)
                 | exact_pk()).select_related("supplier", "outlet").order_by(
            "-created_at"
        )[offset:offset+per_group+1]
        add_group("Purchase orders", [{
            "title": po.reference or ("PO " + str(po.pk)[:8]),
            "subtitle": f"{po.supplier.name} · {po.outlet.name}",
            "url": reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk}),
        } for po in pos])

    if nav.events and site_ids:
        bookings = EventBooking.objects.filter(
            tenant=tenant, space__site_id__in=site_ids,
        ).filter(Q(title__icontains=query) | Q(customer_name__icontains=query)
                 | exact_pk()).select_related("space").order_by("-created_at")[offset:offset+per_group+1]
        add_group("Events", [{
            "title": booking.title,
            "subtitle": f"{booking.space.name} · {booking.get_status_display()}",
            "url": reverse("staff-events-booking-detail", kwargs={"booking_id": booking.pk}),
        } for booking in bookings])

    if nav.workspace and membership.role in MANAGEMENT_ROLES and site_ids:
        worker_qs = Membership.objects.filter(
            tenant=tenant, is_active=True,
        ).filter(
            Q(sites__id__in=site_ids) | Q(outlets__site_id__in=site_ids)
            | Q(role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN])
        ).filter(
            Q(user__email__icontains=query) | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        ).select_related("user").distinct().order_by("user__email")[offset:offset+per_group+1]
        add_group("Team", [{
            "title": member.user.get_full_name() or member.user.email,
            "subtitle": member.get_role_display(),
            "url": reverse("staff-management"),
        } for member in worker_qs])

    return groups[:10]
