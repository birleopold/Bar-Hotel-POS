from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from apps.accounts.models import Membership, UserInvite
from apps.catalog.models import MenuCategory, MenuItem, ServiceOffering
from apps.inventory.models import StockMovement, StockReason
from apps.lodging.models import Room, RoomType
from apps.pos.models import Order, Payment
from apps.purchasing.models import PurchaseOrder, PurchaseOrderStatus
from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Outlet, Site, TenantSettings, TenantSetupProgress


@dataclass(frozen=True)
class SetupStep:
    key: str
    name: str
    description: str
    done: bool
    cta_label: str
    cta_url: str
    required: bool = True
    secondary_cta_label: str | None = None
    secondary_cta_url: str | None = None
    manual_state: str = ""

    def as_dict(self) -> dict:
        status = "done"
        if not self.done:
            if self.manual_state == "skipped":
                status = "skipped"
            elif self.manual_state == "blocked":
                status = "blocked"
            else:
                status = "pending"
        effective_done = self.done or self.manual_state == "skipped"
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "done": self.done,
            "effective_done": effective_done,
            "status": status,
            "cta_label": self.cta_label,
            "cta_url": self.cta_url,
            "required": self.required,
            "secondary_cta_label": self.secondary_cta_label,
            "secondary_cta_url": self.secondary_cta_url,
            "manual_state": self.manual_state,
        }


def build_tenant_setup_state(tenant, progress: TenantSetupProgress | None = None) -> dict:
    try:
        settings_obj = tenant.settings
    except TenantSettings.DoesNotExist:
        business_lines: list[str] = []
    else:
        business_lines = normalize_business_lines(getattr(settings_obj, "business_lines", None))
    bl = set(business_lines)
    # If business lines are not configured yet, default to showing core inventory/POS setup
    # steps so first-run flows guide the workspace correctly.
    lines_configured = bool(bl)
    has_fnb = bool(bl & {"bar", "lounge", "restaurant", "cafeteria", "kitchen"})
    has_retail = bool(bl & {"retail", "supermarket"})
    has_inventory_work = (has_fnb or has_retail) or not lines_configured
    has_lodging_line = "lodging" in bl
    has_events_line = "events" in bl
    has_services_line = "services" in bl

    sites = Site.objects.filter(tenant=tenant, is_active=True).order_by("name")
    first_site = sites.first()
    has_sites = sites.exists()
    has_outlets = Outlet.objects.filter(site__tenant=tenant, site__is_active=True, is_active=True).exists()
    has_menu_categories = MenuCategory.objects.filter(tenant=tenant, is_active=True).exists()
    has_menu_items = MenuItem.objects.filter(tenant=tenant, is_active=True).exists()
    has_services = ServiceOffering.objects.filter(tenant=tenant, is_active=True).exists()
    has_stock_receive = StockMovement.objects.filter(tenant=tenant, reason=StockReason.RECEIVE).exists()
    has_team_invite_or_member = (
        Membership.objects.filter(tenant=tenant, is_active=True).count() > 1
        or UserInvite.objects.filter(tenant=tenant, accepted_at__isnull=False).exists()
    )
    has_po_receive = PurchaseOrder.objects.filter(
        tenant=tenant,
        status__in=[PurchaseOrderStatus.PARTIALLY_RECEIVED, PurchaseOrderStatus.RECEIVED],
    ).exists()
    has_paid_order = (
        Payment.objects.filter(tenant=tenant).exists()
        and Order.objects.filter(tenant=tenant, is_paid=True).exists()
    )
    has_lodging_basics = (
        RoomType.objects.filter(tenant=tenant).exists()
        and Room.objects.filter(room_type__tenant=tenant).exists()
    )
    has_tables = has_outlets and tenant.sites.filter(outlets__tables__is_active=True).exists()

    outlet_cta_url = (
        reverse("console-org-outlet-create", kwargs={"site_id": first_site.id})
        if first_site
        else reverse("console-org-sites")
    )
    outlet_cta_label = "Create first section" if first_site else "Create a branch first"

    required_steps = [
        SetupStep(
            key="first_property",
            name="Create your first branch",
            description="Add at least one physical location for this workspace.",
            done=has_sites,
            cta_label="Create branch",
            cta_url=reverse("console-org-site-create"),
        ),
        SetupStep(
            key="first_outlet",
            name="Add a section under that branch",
            description="Define the locations and work areas your team operates.",
            done=has_outlets,
            cta_label=outlet_cta_label,
            cta_url=outlet_cta_url,
        ),
        SetupStep(
            key="first_menu_category",
            name="Seed items and services",
            description="Create your first item category or add your first service.",
            done=has_menu_categories or has_services,
            cta_label="Create service" if has_services_line and not (has_fnb or has_retail) else "Create item category",
            cta_url=(
                reverse("console-org-service-offering-create")
                if has_services_line and not (has_fnb or has_retail)
                else reverse("console-org-menu-category-create")
            ),
            secondary_cta_label="Create service" if has_services_line and (has_fnb or has_retail) else None,
            secondary_cta_url=(
                reverse("console-org-service-offering-create")
                if has_services_line and (has_fnb or has_retail)
                else None
            ),
        ),
    ]
    if has_inventory_work:
        required_steps.append(
            SetupStep(
                key="first_stock_receive",
                name="Record first stock receive",
                description=(
                    "Use purchasing receipts or a direct stock movement so opening inventory is "
                    "in place for operations."
                ),
                done=has_stock_receive,
                cta_label="Create purchase order",
                cta_url=reverse("staff-purchasing-order-create"),
                secondary_cta_label="Record stock",
                secondary_cta_url=reverse("staff-inventory-movement-create"),
            )
        )
    optional_steps = [
        SetupStep(
            key="first_team_invite",
            name="Invite your first teammate",
            description="Send an invite so day-to-day operations are not tied to one owner account.",
            done=has_team_invite_or_member,
            cta_label="Invite teammate",
            cta_url=reverse("staff-workspace-invite-create"),
            required=False,
        ),
        *(
            [
                SetupStep(
                    key="first_po_received",
                    name="Complete a purchasing receive cycle",
                    description="Mark at least one purchase order as partially or fully received.",
                    done=has_po_receive,
                    cta_label="Open purchase orders",
                    cta_url=reverse("staff-purchasing-orders"),
                    required=False,
                )
            ]
            if has_inventory_work
            else []
        ),
        SetupStep(
            key="first_paid_order",
            name="Close your first paid order",
            description="Complete one real or demo sale so settlement/audit flows are proven.",
            done=has_paid_order,
            cta_label="Open orders",
            cta_url=reverse("staff-orders"),
            required=False,
        ),
        *(
            [
                SetupStep(
                    key="lodging_basics",
                    name="Configure lodging basics",
                    description="Create room types and rooms for front-desk operations.",
                    done=has_lodging_basics,
                    cta_label="Create room type",
                    cta_url=reverse("console-org-room-type-create"),
                    secondary_cta_label="View rooms",
                    secondary_cta_url=reverse("console-org-rooms"),
                    required=False,
                )
            ]
            if has_lodging_line
            else []
        ),
    ]

    overrides = (progress.step_state_overrides if progress is not None else {}) or {}

    def _apply_override(step: SetupStep) -> SetupStep:
        st = str(overrides.get(step.key, "")).strip().lower()
        if st not in {"skipped", "blocked"}:
            st = ""
        return SetupStep(
            key=step.key,
            name=step.name,
            description=step.description,
            done=step.done,
            cta_label=step.cta_label,
            cta_url=step.cta_url,
            required=step.required,
            secondary_cta_label=step.secondary_cta_label,
            secondary_cta_url=step.secondary_cta_url,
            manual_state=st,
        )

    required_steps = [_apply_override(s) for s in required_steps]
    optional_steps = [_apply_override(s) for s in optional_steps]

    required_done = sum(1 for s in required_steps if s.done or s.manual_state == "skipped")
    required_total = len(required_steps) or 1
    required_completion_percent = int((required_done * 100) / required_total)
    setup_complete = all(s.done or s.manual_state == "skipped" for s in required_steps)
    all_steps = required_steps + optional_steps
    next_step = next(
        (s for s in required_steps if not (s.done or s.manual_state == "skipped")),
        None,
    ) or next(
        (s for s in optional_steps if not (s.done or s.manual_state == "skipped")),
        None,
    )

    go_live_checks = [
        {"label": "Active section exists", "done": has_outlets, "fix_url": reverse("console-org-sites")},
        {
            "label": "At least one active sellable (item or service)",
            "done": has_menu_items or has_services,
            "fix_url": reverse(
                "console-org-service-offering-create"
                if has_services_line and not (has_fnb or has_retail)
                else "console-org-menu-categories"
            ),
        },
        *(
            [
                {
                    "label": "At least one service table",
                    "done": has_tables,
                    "fix_url": reverse("staff-table-create"),
                }
            ]
            if has_fnb
            else []
        ),
        {
            "label": "At least one paid order completed",
            "done": has_paid_order,
            "fix_url": reverse("staff-orders"),
        },
    ]

    return {
        "required_steps": [s.as_dict() for s in required_steps],
        "optional_steps": [s.as_dict() for s in optional_steps],
        "all_steps": [s.as_dict() for s in all_steps],
        "setup_complete": setup_complete,
        "required_completion_percent": required_completion_percent,
        "next_step": next_step.as_dict() if next_step else None,
        "go_live_checks": go_live_checks,
        "go_live_ready": all(c["done"] for c in go_live_checks),
    }


def sync_tenant_setup_progress(tenant, state: dict) -> TenantSetupProgress:
    defaults = {
        "last_completion_percent": int(state.get("required_completion_percent") or 0),
        "last_next_step_key": ((state.get("next_step") or {}).get("key") or ""),
        "completed_at": None,
    }
    if state.get("setup_complete"):
        from django.utils import timezone

        defaults["completed_at"] = timezone.now()

    progress, _ = TenantSetupProgress.objects.get_or_create(tenant=tenant)
    progress.last_completion_percent = defaults["last_completion_percent"]
    progress.last_next_step_key = defaults["last_next_step_key"]
    if defaults["completed_at"] and progress.completed_at is None:
        progress.completed_at = defaults["completed_at"]
    if not defaults["completed_at"]:
        progress.completed_at = None
    progress.save(update_fields=["last_completion_percent", "last_next_step_key", "completed_at", "updated_at"])
    return progress


def set_tenant_setup_step_state(tenant, *, step_key: str, state: str) -> TenantSetupProgress:
    progress, _ = TenantSetupProgress.objects.get_or_create(tenant=tenant)
    overrides = dict(progress.step_state_overrides or {})
    current_state = build_tenant_setup_state(tenant, progress=progress)
    valid_keys = {s["key"] for s in current_state.get("all_steps", [])}
    if step_key not in valid_keys:
        raise ValueError("Unknown setup step key.")
    normalized = str(state or "").strip().lower()
    if normalized in {"", "reset", "pending", "done"}:
        overrides.pop(step_key, None)
    elif normalized in {"skipped", "blocked"}:
        overrides[step_key] = normalized
    else:
        raise ValueError("Unsupported setup step state.")
    progress.step_state_overrides = overrides
    progress.save(update_fields=["step_state_overrides", "updated_at"])
    return progress
