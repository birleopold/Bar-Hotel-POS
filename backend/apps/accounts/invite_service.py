"""Shared user-invite creation (browser staff UI + API)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import UserInvite
from apps.tenants.models import Tenant


def create_user_invite(
    *,
    tenant: Tenant,
    email: str,
    role: str,
    expires_days: int,
    invited_by,
) -> tuple[UserInvite, str]:
    """
    Persist invite and return ``(invite, raw_token)``.
    ``raw_token`` is shown once to the operator; only its hash is stored.
    """
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    days = max(1, min(int(expires_days), 30))
    inv = UserInvite.objects.create(
        tenant=tenant,
        email=email.strip().lower(),
        role=role,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(days=days),
        invited_by=invited_by,
    )
    return inv, raw
