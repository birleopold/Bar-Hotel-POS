from django.db.models import Q

from apps.accounts.models import MembershipRole
from apps.customers.models import Customer

from .membership import sites_visible_for_membership, staff_accessible_outlets

CUSTOMER_ROLES = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER,
    MembershipRole.OUTLET_MANAGER, MembershipRole.FRONT_DESK,
}


def can_manage_customers(membership):
    return membership.is_active and membership.role in CUSTOMER_ROLES


def visible_customers(membership, user):
    qs = Customer.objects.filter(tenant_id=membership.tenant_id, merged_into__isnull=True)
    if membership.role in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}:
        return qs
    site_ids = [site.pk for site in sites_visible_for_membership(membership)]
    outlet_ids = [outlet.pk for outlet in staff_accessible_outlets(membership)]
    return qs.filter(
        Q(created_by=user) | Q(reservations__site_id__in=site_ids)
        | Q(folios__site_id__in=site_ids) | Q(event_bookings__space__site_id__in=site_ids)
        | Q(orders__outlet_id__in=outlet_ids)
    ).distinct()
