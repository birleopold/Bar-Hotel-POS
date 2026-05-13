"""Staff read models, nav, permission checks, and workspace resolution."""

from .dashboard_actions import StaffDashboardAction, staff_dashboard_actions
from .membership import (
    LINE_ROLE_OUTLET_TYPES,
    accessible_outlets_flat,
    membership_queryset_for,
    outlets_visible_for_site,
    sites_visible_for_membership,
    staff_accessible_outlets,
    staff_outlet_allowed_for_membership,
)
from .modules import (
    DEFAULT_STAFF_MODULES,
    STAFF_MODULE_CHOICES,
    STAFF_MODULE_KEYS,
    StaffNavVisibility,
    get_tenant_staff_modules,
    initial_staff_modules_for_form,
    resolve_effective_staff_modules,
    staff_nav_capability_allowed,
    staff_nav_visibility,
    tenant_stored_module_list_raw,
)
from .orders_display import (
    attach_order_payment_display,
    order_payment_totals,
    order_refundable_remaining,
    promotions_selectable_for_order,
)
from .permissions import (
    membership_can_acknowledge_ready_handoff,
    membership_can_approve_refunds,
    membership_can_manage_kitchen,
    membership_can_manage_workspace_settings,
    membership_can_modify_lodging,
)
from .workspace import resolve_staff_outlet, resolve_staff_site
from .workspace_setup import tenant_org_setup_incomplete
from .terminology import staff_action_overrides_for_tenant
from .scoping import staff_nav_visibility_scoped

__all__ = [
    "StaffDashboardAction",
    "DEFAULT_STAFF_MODULES",
    "LINE_ROLE_OUTLET_TYPES",
    "STAFF_MODULE_CHOICES",
    "STAFF_MODULE_KEYS",
    "StaffNavVisibility",
    "accessible_outlets_flat",
    "attach_order_payment_display",
    "get_tenant_staff_modules",
    "initial_staff_modules_for_form",
    "membership_can_approve_refunds",
    "membership_can_acknowledge_ready_handoff",
    "membership_can_manage_kitchen",
    "membership_can_manage_workspace_settings",
    "membership_can_modify_lodging",
    "membership_queryset_for",
    "order_payment_totals",
    "order_refundable_remaining",
    "outlets_visible_for_site",
    "promotions_selectable_for_order",
    "resolve_staff_outlet",
    "resolve_staff_site",
    "resolve_effective_staff_modules",
    "sites_visible_for_membership",
    "staff_dashboard_actions",
    "staff_accessible_outlets",
    "staff_nav_capability_allowed",
    "staff_nav_visibility",
    "staff_nav_visibility_scoped",
    "staff_outlet_allowed_for_membership",
    "staff_action_overrides_for_tenant",
    "tenant_org_setup_incomplete",
    "tenant_stored_module_list_raw",
]
