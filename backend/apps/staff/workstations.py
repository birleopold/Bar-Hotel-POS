"""A signed browser preference; all authority comes from current membership."""
from datetime import timedelta
import uuid

from django.conf import settings
from django.core import signing
from django.db.models import Q
from django.utils import timezone

from apps.pos.models import Workstation

COOKIE = "staff_workstation"
SALT = "staff.workstation.v1"
MAX_AGE = 30 * 24 * 60 * 60


def selected_workstation(request, *, outlets):
    try:
        identifier = uuid.UUID(signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=MAX_AGE))
        station = Workstation.objects.filter(
            pk=identifier, tenant=request.tenant, is_active=True, outlet__in=outlets,
        ).select_related("outlet").first()
    except (signing.BadSignature, ValueError, TypeError):
        return None
    if station:
        now = timezone.now()
        # Throttle writes; last contact is not an assertion of device health.
        changed = Workstation.objects.filter(pk=station.pk).filter(
            Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - timedelta(minutes=5)),
        ).update(last_seen_at=now)
        if changed:
            station.last_seen_at = now
    return station


def select_workstation(response, station):
    response.set_cookie(
        COOKIE, signing.dumps(str(station.pk), salt=SALT), max_age=MAX_AGE,
        httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Strict", path="/staff/",
    )
    return response


def forget_workstation(response):
    response.delete_cookie(COOKIE, path="/staff/", samesite="Strict")
    return response


def settlement_workstation_id(request):
    from .services import staff_accessible_outlets
    selected = selected_workstation(request, outlets=staff_accessible_outlets(request.tenant_membership))
    return selected.pk if selected else None
