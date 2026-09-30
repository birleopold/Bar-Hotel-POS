"""Browser selection and revocable approvals; neither grants worker permissions."""
from datetime import timedelta
import hashlib
import secrets
import uuid

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.pos.models import Workstation, WorkstationPairing
from apps.tenants.models import Outlet

COOKIE = "staff_workstation"
SALT = "staff.workstation.v1"
PAIR_COOKIE = "staff_workstation_pair"
PAIR_SALT = "staff.workstation.pair.v1"
MAX_AGE = 30 * 24 * 60 * 60


def _selection_id(request):
    try:
        return uuid.UUID(signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=MAX_AGE))
    except (signing.BadSignature, ValueError, TypeError, AttributeError):
        return None


def active_pairing(request, *, tenant_id):
    """Read only after tenant GUC attachment, including anonymous PIN unlock."""
    try:
        payload = signing.loads(request.COOKIES.get(PAIR_COOKIE, ""), salt=PAIR_SALT, max_age=MAX_AGE)
        pair_id = uuid.UUID(payload["id"])
        secret = payload["secret"]
        if not isinstance(secret, str):
            return None
    except (signing.BadSignature, KeyError, ValueError, TypeError, AttributeError):
        return None
    pairing = WorkstationPairing.objects.filter(
        pk=pair_id, tenant_id=tenant_id, workstation__tenant_id=tenant_id,
        workstation__is_active=True, revoked_at__isnull=True, expires_at__gt=timezone.now(),
    ).select_related("workstation").first()
    if pairing is None or not secrets.compare_digest(pairing.token_hash, hashlib.sha256(secret.encode()).hexdigest()):
        return None
    return pairing


def selected_workstation(request, *, outlets, strict=False):
    identifier = _selection_id(request)
    if identifier is None:
        return None
    station = Workstation.objects.filter(pk=identifier, tenant=request.tenant, is_active=True, outlet__in=outlets).select_related("outlet").first()
    if station is None:
        if strict:
            raise ValidationError({"workstation": "Your selected workstation is unavailable. Ask an administrator to check this device."})
        return None
    pairing = active_pairing(request, tenant_id=request.tenant.pk)
    if station.requires_pairing and (pairing is None or pairing.workstation_id != station.pk):
        if strict:
            raise ValidationError({"workstation": "This browser needs administrator approval before using the register."})
        return None
    now = timezone.now()
    changed = Workstation.objects.filter(pk=station.pk).filter(Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - timedelta(minutes=5))).update(last_seen_at=now)
    if changed:
        station.last_seen_at = now
    if pairing and pairing.workstation_id == station.pk:
        WorkstationPairing.objects.filter(pk=pairing.pk).filter(Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - timedelta(minutes=5))).update(last_seen_at=now)
    return station


def select_workstation(response, station):
    response.set_cookie(COOKIE, signing.dumps(str(station.pk), salt=SALT), max_age=MAX_AGE, httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Strict", path="/staff/")
    return response


def forget_workstation(response):
    for name in (COOKIE, PAIR_COOKIE):
        response.delete_cookie(name, path="/staff/", samesite="Strict")
    return response


@transaction.atomic
def approve_browser(*, station, user, label):
    Outlet.objects.select_for_update().get(pk=station.outlet_id, site__tenant_id=station.tenant_id)
    station = Workstation.objects.select_for_update().get(pk=station.pk, tenant_id=station.tenant_id)
    if not station.is_active:
        raise ValidationError({"workstation": "Enable this workstation before pairing a browser."})
    secret = secrets.token_urlsafe(32)
    pair = WorkstationPairing.objects.create(
        tenant_id=station.tenant_id, workstation=station, approved_by=user,
        label=label, token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(seconds=MAX_AGE),
    )
    log_audit(tenant_id=station.tenant_id, user_id=user.pk, action="workstation.browser_approved", entity_type="workstation_pairing", entity_id=str(pair.pk), payload={"workstation_id": str(station.pk), "label": label})
    return pair, secret


def set_pairing_cookie(response, pair, secret):
    response = select_workstation(response, pair.workstation)
    response.set_cookie(PAIR_COOKIE, signing.dumps({"id": str(pair.pk), "secret": secret}, salt=PAIR_SALT), max_age=MAX_AGE, httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Strict", path="/staff/")
    return response


@transaction.atomic
def revoke_pairing(*, pairing, user, reason):
    locked = WorkstationPairing.objects.select_for_update().get(pk=pairing.pk, tenant_id=pairing.tenant_id)
    if locked.revoked_at is not None:
        return locked
    locked.revoked_at = timezone.now()
    locked.revoked_by = user
    locked.revocation_reason = reason[:255]
    locked.save(update_fields=["revoked_at", "revoked_by", "revocation_reason", "updated_at"])
    log_audit(tenant_id=locked.tenant_id, user_id=user.pk, action="workstation.browser_revoked", entity_type="workstation_pairing", entity_id=str(locked.pk), payload={"workstation_id": str(locked.workstation_id), "reason": locked.revocation_reason})
    return locked


def settlement_workstation_id(request, *, outlet=None):
    from .services import staff_accessible_outlets
    outlets = staff_accessible_outlets(request.tenant_membership)
    selected = require_staff_register_selection(request, outlet=outlet) if outlet else selected_workstation(request, outlets=outlets, strict=True)
    return selected.pk if selected else None


def require_staff_register_selection(request, *, outlet):
    from .services import staff_accessible_outlets
    station = selected_workstation(request, outlets=staff_accessible_outlets(request.tenant_membership), strict=True)
    if station is not None and station.outlet_id != outlet.pk:
        raise ValidationError({"workstation": "Choose a workstation in this section."})
    if station is None and Workstation.objects.filter(tenant=request.tenant, outlet=outlet, is_active=True, requires_pairing=True).exists():
        raise ValidationError({"workstation": "Choose an approved workstation before using this section's register."})
    return station
