"""Read-only, role and location-scoped audit timeline with PII redaction."""
import json
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import MembershipRole
from apps.audit.models import AuditEvent
from .membership import sites_visible_for_membership, staff_accessible_outlets

OWNER_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN})
READER_ROLES = OWNER_ROLES | frozenset({
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})
REDACT_KEY = re.compile(
    r"(password|secret|credential|token|cookie|authorization|pin|cvv|pan|"
    r"account_number|access_key|private_key|card_number|"
    r"email|phone|contact|address|guest_name|full_name|date_of_birth|dob)",
    re.IGNORECASE,
)
MAX_DEPTH = 5


def safe_audit_payload(value, depth=0):
    """Retain review evidence while omitting personal and secret values."""
    if depth >= MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key)[:80]: ("[redacted]" if REDACT_KEY.search(str(key))
                            else safe_audit_payload(item, depth + 1))
            for key, item in list(value.items())[:60]
        }
    if isinstance(value, (list, tuple)):
        return [safe_audit_payload(item, depth + 1) for item in value[:60]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Never disclose long blobs (embedded documents, JWTs etc.).
    return str(value)[:240]


def safe_csv_value(value):
    item = str(value)
    return "'" + item if item.lstrip().startswith(("=", "+", "-", "@")) else item


def visible_audit_events(*, tenant, membership, params):
    if not membership or not membership.is_active or membership.tenant_id != tenant.pk:
        return AuditEvent.objects.none(), {}
    if membership.role not in READER_ROLES:
        return AuditEvent.objects.none(), {}
    qs = AuditEvent.objects.filter(tenant=tenant).select_related("user")
    if membership.role not in OWNER_ROLES:
        outlet_ids = [str(o.pk) for o in staff_accessible_outlets(membership)]
        site_ids = [str(s.pk) for s in sites_visible_for_membership(membership)]
        if not outlet_ids and not site_ids:
            return AuditEvent.objects.none(), {}
        # Audit events do not yet store normalized branch/outlet FKs. Fail
        # closed on events without an explicit scope instead of leaking them.
        qs = qs.filter(
            Q(payload__outlet_id__in=outlet_ids)
            | Q(payload__site_id__in=site_ids)
        )
    action = str(params.get("action") or "").strip()[:64]
    if action:
        qs = qs.filter(action__icontains=action)
    entity = str(params.get("entity") or "").strip()[:64]
    if entity:
        qs = qs.filter(entity_type__icontains=entity)
    date_from = parse_date(str(params.get("from") or "")) if params.get("from") else None
    date_to = parse_date(str(params.get("to") or "")) if params.get("to") else None
    today = timezone.localdate()
    if date_from is None:
        date_from = today - timedelta(days=30)
    if date_to is None:
        date_to = today
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 366:
        date_from = date_to - timedelta(days=366)
    qs = qs.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
    return qs.order_by("-created_at", "-pk"), {
        "action": action, "entity": entity,
        "from": date_from.isoformat(), "to": date_to.isoformat(),
    }


def audit_view_row(event):
    evidence = safe_audit_payload(event.payload or {})
    return {
        "time": event.created_at,
        "actor": (event.user.email if event.user_id and event.user else "System"),
        "action": event.action.replace(".", " ").replace("_", " "),
        "action_code": event.action,
        "entity": event.entity_type.replace("_", " "),
        "entity_id": event.entity_id,
        "details": json.dumps(evidence, ensure_ascii=False, default=str),
    }
