"""Shared staff terminal credentials and scoped, short lived device marker."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership

from .middleware import STAFF_SESSION_OUTLET_ALL
from .services.membership import staff_outlet_allowed_for_membership

TERMINAL_COOKIE = "staff_terminal"
TERMINAL_SALT = "staff.terminal.v1"
TERMINAL_SECONDS = 12 * 60 * 60
PIN_IDLE_SECONDS = 2 * 60
PIN_FAILURE_LIMIT = 5
PIN_LOCK_MINUTES = 15


def terminal_scope(request, *, validate_pairing=True):
    try:
        payload = signing.loads(request.COOKIES.get(TERMINAL_COOKIE, ""), salt=TERMINAL_SALT, max_age=TERMINAL_SECONDS)
        tenant_id = uuid.UUID(payload["tenant"])
        outlet_id = payload.get("outlet", "")
        if validate_pairing:
            from apps.pos.models import Workstation
            from .workstations import active_pairing, _selection_id
            pairing_id = payload.get("pairing")
            if pairing_id:
                pair = active_pairing(request, tenant_id=tenant_id)
                if (pair is None or str(pair.pk) != pairing_id or _selection_id(request) != pair.workstation_id
                        or outlet_id != str(pair.workstation.outlet_id)):
                    return None
            else:
                required = Workstation.objects.filter(tenant_id=tenant_id, is_active=True, requires_pairing=True)
                selected_id = _selection_id(request)
                if selected_id:
                    required = required.filter(pk=selected_id)
                elif outlet_id and outlet_id != STAFF_SESSION_OUTLET_ALL:
                    required = required.filter(outlet_id=uuid.UUID(outlet_id))
                if required.exists():
                    return None
        return tenant_id, outlet_id
    except (signing.BadSignature, KeyError, ValueError, TypeError, AttributeError):
        return None


def mark_terminal(response, *, tenant_id, outlet_id="", request=None):
    payload = {"tenant": str(tenant_id), "outlet": str(outlet_id)}
    if request is not None:
        from .workstations import active_pairing, _selection_id
        pair = active_pairing(request, tenant_id=tenant_id)
        from .workstations import PAIR_COOKIE
        if PAIR_COOKIE in request.COOKIES and pair is None:
            payload["pairing"] = "unavailable"
        if pair is not None and _selection_id(request) == pair.workstation_id:
            payload["pairing"] = str(pair.pk)
            payload["outlet"] = str(pair.workstation.outlet_id)
    value = signing.dumps(payload, salt=TERMINAL_SALT)
    response.set_cookie(
        TERMINAL_COOKIE, value, max_age=TERMINAL_SECONDS, httponly=True,
        secure=settings.SESSION_COOKIE_SECURE, samesite="Strict", path="/staff/",
    )
    return response


def clear_terminal(response):
    response.delete_cookie(TERMINAL_COOKIE, path="/staff/", samesite="Strict")
    return response


def available_workers(tenant_id, outlet_id):
    members = Membership.objects.filter(
        tenant_id=tenant_id, is_active=True, user__is_active=True,
    ).exclude(staff_pin_hash="").select_related("user", "tenant")
    if outlet_id and outlet_id != STAFF_SESSION_OUTLET_ALL:
        try:
            outlet_uuid = uuid.UUID(outlet_id)
        except ValueError:
            return []
        members = [m for m in members if staff_outlet_allowed_for_membership(m, outlet_uuid)]
    return sorted(members, key=lambda m: m.user.email.lower())


def set_member_pin(membership, pin):
    membership.staff_pin_hash = make_password(pin + settings.SECRET_KEY)
    membership.staff_pin_failures = 0
    membership.staff_pin_locked_until = None
    membership.save(update_fields=["staff_pin_hash", "staff_pin_failures", "staff_pin_locked_until", "updated_at"])


@transaction.atomic
def verify_member_pin(*, member_id, tenant_id, outlet_id, pin):
    member = Membership.objects.select_for_update().select_related("user", "tenant").filter(
        id=member_id, tenant_id=tenant_id, is_active=True, user__is_active=True,
    ).exclude(staff_pin_hash="").first()
    if member is None:
        return None
    if outlet_id and outlet_id != STAFF_SESSION_OUTLET_ALL:
        try:
            outlet_uuid = uuid.UUID(outlet_id)
        except ValueError:
            return None
        if not staff_outlet_allowed_for_membership(member, outlet_uuid):
            return None
    now = timezone.now()
    if member.staff_pin_locked_until and member.staff_pin_locked_until > now:
        return None
    if check_password(pin + settings.SECRET_KEY, member.staff_pin_hash):
        member.staff_pin_failures = 0
        member.staff_pin_locked_until = None
        member.save(update_fields=["staff_pin_failures", "staff_pin_locked_until", "updated_at"])
        return member
    member.staff_pin_failures += 1
    failure_count = member.staff_pin_failures
    if member.staff_pin_failures >= PIN_FAILURE_LIMIT:
        member.staff_pin_locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
        member.staff_pin_failures = 0
    member.save(update_fields=["staff_pin_failures", "staff_pin_locked_until", "updated_at"])
    from apps.audit.services import log_audit
    log_audit(tenant_id=tenant_id, user_id=None, action="staff.pin_failed", entity_type="membership", entity_id=str(member.pk), payload={"outlet_id": str(outlet_id), "failure_count": failure_count, "locked": bool(member.staff_pin_locked_until)})
    return None
