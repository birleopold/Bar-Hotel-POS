"""CSV serialization for staff reports (shared by HTTP exports and scheduled digests)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import date
from io import StringIO
from uuid import UUID

from django.db.models import QuerySet

from apps.finance.models import CashbookEntry

from .sales_summary import build_sales_summary


def write_sales_summary_csv(writer: csv.writer, summary: dict) -> None:
    writer.writerow(["metric", "value"])
    writer.writerow(["payments_count", summary["payments_count"]])
    writer.writerow(["gross_sales", summary["gross_sales"]])
    writer.writerow(["refunds_total", summary["refunds_total"]])
    writer.writerow(["net_sales", summary["net_sales"]])
    writer.writerow([])
    writer.writerow(["section", "gross_sales", "refunds_total", "net_sales"])
    for row in summary["by_section"]:
        writer.writerow([row["section_label"], row["gross_sales"], row["refunds_total"], row["net_sales"]])
    writer.writerow([])
    writer.writerow(["payment_method", "count", "amount"])
    for row in summary["by_payment_method"]:
        writer.writerow([row["method"], row["count"], row["amount"]])
    writer.writerow([])
    writer.writerow(["outlet_name", "payment_count", "amount"])
    for row in summary["by_outlet"]:
        writer.writerow([row["outlet_name"], row["count"], row["amount"]])
    writer.writerow([])
    writer.writerow(["item", "quantity_sold", "revenue"])
    for it in summary["top_items"]:
        writer.writerow([it["item_name"], it["quantity_sold"], it["revenue"]])


def format_sales_summary_csv(
    tenant_id: UUID,
    d0: date,
    d1: date,
    outlet_id: UUID | None = None,
    *,
    allowed_outlet_ids: list[UUID] | None = None,
    outlet_ids: list[UUID] | None = None,
) -> str:
    summary = build_sales_summary(
        tenant_id,
        d0,
        d1,
        outlet_id,
        allowed_outlet_ids=allowed_outlet_ids,
        outlet_ids=outlet_ids,
    )
    return format_sales_summary_csv_from_summary(summary)


def format_sales_summary_csv_from_summary(summary: dict) -> str:
    buf = StringIO()
    w = csv.writer(buf)
    write_sales_summary_csv(w, summary)
    return buf.getvalue()


def write_cashbook_entry_rows(writer: csv.writer, entries: Iterable[CashbookEntry]) -> None:
    writer.writerow(
        [
            "transaction_date",
            "category_kind",
            "category",
            "branch",
            "amount",
            "reference",
            "note",
        ]
    )
    for e in entries:
        writer.writerow(
            [
                e.transaction_date.isoformat(),
                e.category.get_kind_display(),
                e.category.name,
                e.site.name if e.site else "",
                str(e.amount),
                e.reference or "",
                (e.note or "").replace("\n", " ").replace("\r", " "),
            ]
        )


def format_cashbook_csv(entries: Iterable[CashbookEntry]) -> str:
    buf = StringIO()
    w = csv.writer(buf)
    write_cashbook_entry_rows(w, entries)
    return buf.getvalue()


def cashbook_entries_for_export(tenant_id: UUID, d0: date, d1: date) -> QuerySet[CashbookEntry]:
    return (
        CashbookEntry.objects.filter(
            tenant_id=tenant_id,
            transaction_date__gte=d0,
            transaction_date__lte=d1,
        )
        .select_related("category", "site")
        .order_by("-transaction_date", "-created_at")
    )


def format_cashbook_csv_for_tenant_range(tenant_id: UUID, d0: date, d1: date) -> str:
    return format_cashbook_csv(cashbook_entries_for_export(tenant_id, d0, d1))
