"""Housekeeping workflow for staff phones, tablets and manager workspaces."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.audit.services import log_audit

from .models import (
    MaintenanceStatus, Room, RoomHousekeepingEvent, RoomMaintenanceRequest,
    RoomStatus,
)


MANAGER_ROLES = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
}
ROOM_EDIT_ROLES = MANAGER_ROLES | {MembershipRole.CLEANER, MembershipRole.FRONT_DESK}


def cleaners_for_site(*, tenant, site):
    if site.tenant_id != tenant.pk:
        raise ValueError("Property is outside this business")
    return Membership.objects.filter(
        tenant=tenant, is_active=True, role=MembershipRole.CLEANER,
    ).filter(Q(sites=site) | Q(outlets__site=site)).distinct().select_related("user").order_by("user__email")


@transaction.atomic
def change_housekeeping_room(*, tenant, site, room_id, membership, action, user,
                             assigned_user_id=None):
    """Atomic assignment, cleaning, inspection and out-of-service updates.

    A cleaner can claim an unassigned room; only its assigned cleaner may
    then start/finish it. Managers can assign and inspect. A room with open
    maintenance cannot be marked ready by an inspection.
    """
    if site.tenant_id != tenant.pk or membership.tenant_id != tenant.pk:
        raise ValidationError({"site": "Property is outside your workspace."})
    if membership.role not in ROOM_EDIT_ROLES or not membership.is_active:
        raise ValidationError({"detail": "Your role cannot update housekeeping."})
    if membership.user_id != user.pk:
        raise ValidationError({"detail": "Staff identity must match the active session."})
    if membership.role not in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}:
        can_access = (membership.sites.filter(pk=site.pk).exists()
                      or membership.outlets.filter(site=site).exists())
        if not can_access:
            raise ValidationError({"site": "This property is not assigned to your role."})
    room = Room.objects.select_for_update().select_related("room_type").filter(
        pk=room_id, room_type__site=site, room_type__tenant=tenant,
        is_active=True,
    ).first()
    if room is None:
        raise ValidationError({"room": "Select a room in your current property."})

    old_status, old_assignee = room.status, room.assigned_housekeeper_id
    manager = membership.role in MANAGER_ROLES
    action = (action or "").strip()
    update_fields = ["updated_at"]
    now = timezone.now()

    if action == "assign":
        if not manager:
            raise ValidationError({"action": "A manager must assign rooms."})
        if room.status not in (RoomStatus.DIRTY, RoomStatus.CLEANING):
            raise ValidationError({"room": "Only rooms awaiting cleaning can be assigned."})
        if assigned_user_id:
            worker = cleaners_for_site(tenant=tenant, site=site).filter(
                user_id=assigned_user_id,
            ).first()
            if worker is None:
                raise ValidationError({"assigned_to": "Choose a housekeeper assigned to this property."})
            room.assigned_housekeeper_id = worker.user_id
        else:
            room.assigned_housekeeper_id = None
        update_fields.append("assigned_housekeeper")
    elif action == "claim":
        if membership.role != MembershipRole.CLEANER:
            raise ValidationError({"action": "Only housekeepers can claim rooms."})
        if room.status != RoomStatus.DIRTY or room.assigned_housekeeper_id is not None:
            raise ValidationError({"room": "This room is not available to claim."})
        room.assigned_housekeeper_id = user.pk
        update_fields.append("assigned_housekeeper")
    elif action in {"start", "finish"}:
        if not manager:
            if room.assigned_housekeeper_id not in (None, user.pk):
                raise ValidationError({"room": "This room is assigned to another worker."})
            if room.assigned_housekeeper_id is None:
                room.assigned_housekeeper_id = user.pk
                update_fields.append("assigned_housekeeper")
        if action == "start":
            if room.status != RoomStatus.DIRTY:
                raise ValidationError({"room": "Start cleaning only when the room is dirty."})
            room.status = RoomStatus.CLEANING
            room.housekeeping_started_at = now
            update_fields.extend(["status", "housekeeping_started_at"])
        else:
            if room.status not in (RoomStatus.DIRTY, RoomStatus.CLEANING):
                raise ValidationError({"room": "Finish cleaning only when the room needs cleaning."})
            if RoomMaintenanceRequest.objects.filter(
                tenant=tenant, room=room,
            ).exclude(status=MaintenanceStatus.RESOLVED).exists():
                raise ValidationError({"room": "Resolve open maintenance before marking the room clean."})
            room.status = RoomStatus.CLEAN
            room.housekeeping_finished_at = now
            update_fields.extend(["status", "housekeeping_finished_at"])
    elif action == "inspect":
        if not manager:
            raise ValidationError({"action": "A supervisor must inspect rooms."})
        if room.status != RoomStatus.CLEAN:
            raise ValidationError({"room": "Room must be cleaned before inspection."})
        if RoomMaintenanceRequest.objects.filter(
            tenant=tenant, room=room,
        ).exclude(status=MaintenanceStatus.RESOLVED).exists():
            raise ValidationError({"room": "Resolve open maintenance before inspection."})
        room.status = RoomStatus.INSPECTED
        room.housekeeping_inspected_at = now
        update_fields.extend(["status", "housekeeping_inspected_at"])
    elif action in {"reopen", "unavailable"}:
        if not manager and membership.role != MembershipRole.FRONT_DESK:
            raise ValidationError({"action": "A manager or reception must change room availability."})
        new_status = RoomStatus.DIRTY if action == "reopen" else RoomStatus.OUT_OF_ORDER
        if room.status == new_status:
            return room, False
        room.status = new_status
        if action == "reopen":
            room.assigned_housekeeper = None
            room.housekeeping_started_at = None
            room.housekeeping_finished_at = None
            room.housekeeping_inspected_at = None
            update_fields.extend([
                "assigned_housekeeper", "housekeeping_started_at",
                "housekeeping_finished_at", "housekeeping_inspected_at",
            ])
        update_fields.append("status")
    else:
        raise ValidationError({"action": "Choose a housekeeping action."})

    if room.status == old_status and room.assigned_housekeeper_id == old_assignee:
        return room, False
    room.save(update_fields=update_fields)
    event = RoomHousekeepingEvent.objects.create(
        tenant=tenant, room=room, actor=user, action=action,
        previous_status=old_status, new_status=room.status,
        previous_assignee_id=old_assignee,
        new_assignee_id=room.assigned_housekeeper_id,
    )
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk,
        action="lodging.housekeeping_action",
        entity_type="room_housekeeping_event", entity_id=str(event.pk),
        payload={
            "room_id": str(room.pk), "site_id": str(site.pk),
            "action": action, "before": old_status, "after": room.status,
            "previous_assignee_id": str(old_assignee) if old_assignee else None,
            "assignee_id": str(room.assigned_housekeeper_id) if room.assigned_housekeeper_id else None,
        },
    )
    return room, True
