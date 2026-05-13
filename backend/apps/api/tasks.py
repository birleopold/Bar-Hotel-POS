"""Celery tasks for API-adjacent async work (email, future reports)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, send_mail

logger = logging.getLogger(__name__)


@shared_task
def daily_operations_digest() -> None:
    """
    Daily (UTC) snapshot for each active tenant: sales + cashbook CSVs.

    Uses the same aggregates as staff exports (``build_sales_summary`` / cashbook rows).
    Set ``DAILY_OPERATIONS_DIGEST_SEND=true`` to email workspace owners and tenant admins;
    otherwise the task only logs a one-line summary per tenant (safe default).
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts.models import Membership, MembershipRole
    from apps.staff.report_csv import (
        cashbook_entries_for_export,
        format_cashbook_csv,
        format_sales_summary_csv_from_summary,
    )
    from apps.staff.sales_summary import build_sales_summary
    from apps.tenants.models import SubscriptionStatus, Tenant, TenantSubscription

    send_email = bool(getattr(settings, "DAILY_OPERATIONS_DIGEST_SEND", False))
    digest_date = timezone.now().date() - timedelta(days=1)

    def tenants() -> list[Tenant]:
        out: list[Tenant] = []
        for tenant in Tenant.objects.filter(is_active=True).order_by("id").iterator():
            try:
                sub = tenant.subscription
            except TenantSubscription.DoesNotExist:
                out.append(tenant)
                continue
            if sub.status in {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}:
                continue
            out.append(tenant)
        return out

    def recipient_emails(tenant: Tenant) -> list[str]:
        roles = (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)
        emails: list[str] = []
        for m in Membership.objects.filter(
            tenant=tenant, is_active=True, role__in=roles
        ).select_related("user"):
            addr = (m.user.email or "").strip()
            if addr:
                emails.append(addr)
        return sorted(set(emails))

    for tenant in tenants():
        summary = build_sales_summary(tenant.id, digest_date, digest_date, outlet_id=None)
        sales_csv = format_sales_summary_csv_from_summary(summary)
        cash_qs = cashbook_entries_for_export(tenant.id, digest_date, digest_date)
        cash_count = cash_qs.count()
        cash_csv = format_cashbook_csv(cash_qs)

        logger.info(
            "daily_operations_digest tenant=%s date=%s net_sales=%s cashbook_lines=%s send=%s",
            tenant.slug,
            digest_date.isoformat(),
            summary["net_sales"],
            cash_count,
            send_email,
        )

        if not send_email:
            continue

        to = recipient_emails(tenant)
        if not to:
            logger.warning("daily_operations_digest skip email tenant=%s (no recipients)", tenant.slug)
            continue

        body = (
            f"Workspace: {tenant.name}\n"
            f"Digest date (UTC calendar day): {digest_date.isoformat()}\n"
            f"Net sales: {summary['net_sales']}\n"
            f"Cashbook lines in range: {cash_count}\n"
            "\n"
            "CSV attachments use the same layouts as staff exports "
            "(sales summary and cashbook entries).\n"
        )
        msg = EmailMessage(
            subject=f"[{tenant.name}] Daily operations — {digest_date.isoformat()}",
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to,
        )
        msg.attach(
            f"sales-summary-{digest_date.isoformat()}.csv",
            sales_csv.encode("utf-8"),
            "text/csv",
        )
        msg.attach(
            f"cashbook-{digest_date.isoformat()}.csv",
            cash_csv.encode("utf-8"),
            "text/csv",
        )
        msg.send(fail_silently=False)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_password_reset_email_task(self, *, user_email: str, uid_b64: str, token: str) -> None:
    """Send password reset email off-request when Celery broker is configured."""
    from apps.api.password_views import build_password_reset_email_body

    subject = getattr(settings, "PASSWORD_RESET_EMAIL_SUBJECT", "Password reset")
    body = build_password_reset_email_body(user_email=user_email, uid=uid_b64, token=token)
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
        )
    except OSError as exc:
        raise self.retry(exc=exc) from exc
