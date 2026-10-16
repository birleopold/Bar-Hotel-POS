"""Opt-in scheduled owner reports, scoped by business and optionally property.

Delivery runs on an hourly beat but selects each tenant's local clock.
Existing staff summary calculations remain the sole source for CSV and PDF.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.staff.report_csv import format_sales_summary_csv_from_summary
from apps.staff.sales_summary import build_sales_summary
from apps.tenants.models import (
    Outlet, OwnerReportDelivery, OwnerReportDeliveryStatus,
    OwnerReportFrequency, OwnerReportSchedule, TenantSettings,
)


@contextmanager
def report_worker_tenant_scope(tenant_id):
    """Scope non-HTTP worker queries using PostgreSQL session GUC.

    Avoid keeping a DB transaction open while SMTP communicates externally.
    Always restore connection state before processing another business.
    """
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        previous = cursor.fetchone()[0]
        cursor.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            if previous:
                cursor.execute("SELECT set_config('app.tenant_id', %s, false)", [previous])
            else:
                cursor.execute("RESET app.tenant_id")


OWNER_ROLES = (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)
MAX_ATTEMPTS = 3
RETRY_GAP = timedelta(minutes=45)


def scheduled_period(schedule: OwnerReportSchedule, *, at: datetime):
    """Return fully closed report dates when this local schedule is due."""
    tz_name = ""
    if schedule.site_id:
        tz_name = (schedule.site.business_timezone or "").strip()
    if not tz_name:
        # Do not rely on a cached tenant.settings relation: report schedules
        # must respect the most recently saved owner timezone preference.
        current_settings = TenantSettings.objects.filter(
            tenant_id=schedule.tenant_id,
        ).only("default_timezone").first()
        tz_name = (
            (current_settings.default_timezone or "").strip()
            if current_settings is not None else "UTC"
        )
    try:
        zone = ZoneInfo(tz_name or "UTC")
    except ZoneInfoNotFoundError:
        # Bad timezone configuration fails closed; no unexpected delivery.
        return None
    local = at.astimezone(zone)
    if local.hour < schedule.local_send_hour:
        return None
    today = local.date()
    if schedule.frequency == OwnerReportFrequency.DAILY:
        return today - timedelta(days=1), today - timedelta(days=1)
    if schedule.frequency == OwnerReportFrequency.WEEKLY:
        if local.weekday() != schedule.send_weekday:
            return None
        return today - timedelta(days=7), today - timedelta(days=1)
    if schedule.frequency == OwnerReportFrequency.MONTHLY:
        if local.day != schedule.send_monthday:
            return None
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    return None


def eligible_recipients(schedule):
    """Only explicitly checked, currently active owner/admin accounts."""
    eligible = Membership.objects.filter(
        tenant=schedule.tenant, is_active=True,
        user__is_active=True, role__in=OWNER_ROLES,
        pk__in=schedule.recipients.values_list("pk", flat=True),
    ).select_related("user")
    return sorted({
        m.user.email.strip()
        for m in eligible
        if m.user.email and m.user.email.strip()
    })


def build_pdf_summary(*, schedule, period, summary):
    """Build a small readable report, with no customer personal information."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

    def pdf_text(value):
        raw = str(value).encode("latin-1", errors="replace").decode("latin-1")
        return escape(raw[:220])

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=40, bottomMargin=38)
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 13
    title_style = styles["Title"]
    title_style.alignment = TA_LEFT
    currency = getattr(schedule.tenant.settings, "default_currency", "UGX")
    scope = schedule.site.name if schedule.site_id else "All business sections"
    story = [
        Paragraph("Operations report", title_style),
        Spacer(1, 12),
        Paragraph(pdf_text(schedule.tenant.name), styles["Heading2"]),
        Paragraph("Scope: " + pdf_text(scope), styles["Normal"]),
        Paragraph("Period: " + pdf_text(period[0]) + " to " + pdf_text(period[1]), styles["Normal"]),
        Paragraph(
            "Operating dates for one property" if schedule.site_id
            else "UTC calendar dates across the business", styles["Normal"],
        ),
        Spacer(1, 18),
        Paragraph("Sales overview (" + pdf_text(currency) + ")", styles["Heading2"]),
    ]
    rows = [
        ["Metric", "Amount / count"],
        ["Payments", str(summary["payments_count"])],
        ["Gross sales", str(summary["gross_sales"])],
        ["Refunds", str(summary["refunds_total"])],
        ["Net sales", str(summary["net_sales"])],
    ]
    table = Table(rows, colWidths=[270, 190], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5EFF2")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D2D9E2")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([table, Spacer(1, 16), Paragraph("Top items", styles["Heading2"])])
    items = summary.get("top_items") or []
    if not items:
        story.append(Paragraph("No sales items recorded for this period.", styles["Normal"]))
    else:
        item_rows = [["Item", "Quantity", "Revenue"]]
        for item in items[:12]:
            item_rows.append([
                Paragraph(pdf_text(item.get("item_name", "Unknown")), styles["Normal"]),
                pdf_text(item.get("quantity_sold", "0")),
                pdf_text(item.get("revenue", "0")),
            ])
        items_table = Table(item_rows, colWidths=[245, 80, 135], repeatRows=1)
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5EFF2")),
            ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D2D9E2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(items_table)
    story.extend([
        Spacer(1, 18),
        Paragraph(
            "Generated from recorded POS transactions. Verify cash counts, "
            "provider settlements, tax and stock valuations separately.",
            styles["Normal"],
        ),
    ])
    doc.build(story)
    return buf.getvalue()


def _summary_for_schedule(schedule, period):
    from apps.tenants.models import Outlet
    allowed_ids = list(Outlet.objects.filter(
        site__tenant=schedule.tenant, is_active=True,
        site__is_active=True,
        **({"site": schedule.site} if schedule.site_id else {}),
    ).values_list("pk", flat=True))
    return build_sales_summary(
        schedule.tenant_id, period[0], period[1],
        allowed_outlet_ids=allowed_ids,
        business_date_site=schedule.site if schedule.site_id else None,
    )


@transaction.atomic
def claim_report_delivery(*, schedule, period, now):
    """One durable sending claim per schedule/period; never queue twice."""
    schedule = OwnerReportSchedule.objects.select_for_update().get(
        pk=schedule.pk, is_enabled=True,
    )
    recipients = eligible_recipients(schedule)
    if not recipients:
        return None
    delivery, _ = OwnerReportDelivery.objects.select_for_update().get_or_create(
        schedule=schedule, tenant=schedule.tenant,
        period_start=period[0], period_end=period[1],
        defaults={"recipient_snapshot": recipients},
    )
    if delivery.status in (
        OwnerReportDeliveryStatus.SENT,
        OwnerReportDeliveryStatus.SENDING,
    ) and delivery.attempts > 0:
        return None
    if delivery.attempts >= MAX_ATTEMPTS:
        return None
    if (delivery.last_attempt_at and now - delivery.last_attempt_at < RETRY_GAP):
        return None
    delivery.status = OwnerReportDeliveryStatus.SENDING
    delivery.recipient_snapshot = recipients
    delivery.attempts += 1
    delivery.last_attempt_at = now
    delivery.error_message = ""
    delivery.save(update_fields=[
        "status", "recipient_snapshot", "attempts",
        "last_attempt_at", "error_message", "updated_at",
    ])
    return delivery.pk


def deliver_owner_report(*, schedule, at=None):
    now = at or timezone.now()
    if not schedule.is_enabled or not schedule.tenant.is_active:
        return None
    period = scheduled_period(schedule, at=now)
    if period is None:
        return None
    delivery_id = claim_report_delivery(
        schedule=schedule, period=period, now=now,
    )
    if delivery_id is None:
        return None
    delivery = OwnerReportDelivery.objects.get(pk=delivery_id)
    try:
        backend = str(getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"))
        if backend in {
            "django.core.mail.backends.console.EmailBackend",
            "django.core.mail.backends.locmem.EmailBackend",
            "django.core.mail.backends.dummy.EmailBackend",
            "django.core.mail.backends.filebased.EmailBackend",
        }:
            raise RuntimeError("SMTP email backend is not configured for real delivery.")
        # A worker could be queued when an owner loses access. Recheck
        # each address immediately before sending confidential totals.
        still_allowed = set(eligible_recipients(schedule))
        delivery.recipients_to_send = [
            address for address in delivery.recipient_snapshot
            if address in still_allowed
        ]
        if not schedule.is_enabled or not delivery.recipients_to_send:
            raise RuntimeError("Report disabled or no active authorized recipients remain.")
        summary = _summary_for_schedule(schedule, period)
        csv_body = format_sales_summary_csv_from_summary(summary)
        pdf_body = build_pdf_summary(schedule=schedule, period=period, summary=summary)
        report_label = period[0].isoformat() + "_" + period[1].isoformat()
        scope = schedule.site.name if schedule.site_id else schedule.tenant.name
        email = EmailMessage(
            subject=f"{schedule.tenant.name} — {schedule.get_frequency_display()} operations report",
            body=(
                f"Business: {schedule.tenant.name}\n"
                f"Scope: {scope}\n"
                f"Dates: {period[0]} to {period[1]}\n"
                f"Net sales: {summary['net_sales']}\n\n"
                "Attached: a compact PDF overview and detailed sales CSV.\n"
                "A property report uses its configured operating-date boundary. "
                "A business-wide report uses UTC calendar dates.\n"
                "This message does not confirm bank reconciliation or tax filing."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_FROM_EMAIL],
            bcc=delivery.recipients_to_send,
        )
        email.attach(f"operations-{report_label}.csv", csv_body, "text/csv")
        email.attach(f"operations-{report_label}.pdf", pdf_body, "application/pdf")
        delivered = email.send(fail_silently=False)
        if delivered != 1:
            raise RuntimeError("Email transport did not confirm acceptance.")
    except Exception as exc:
        # Keep delivery pending in an explicit failed state; hourly worker will
        # retry after 45 min, max 3 times. Unknown SMTP acceptance can still
        # cause duplicate email and must be surfaced to owners.
        OwnerReportDelivery.objects.filter(pk=delivery_id).update(
            status=OwnerReportDeliveryStatus.FAILED,
            error_message=f"{type(exc).__name__}: {str(exc)}"[:300],
        )
        raise
    else:
        OwnerReportDelivery.objects.filter(pk=delivery_id).update(
            status=OwnerReportDeliveryStatus.SENT,
            sent_at=timezone.now(), error_message="",
        )
    return delivery_id
