"""CSV serialization for staff reports (shared by HTTP exports and scheduled digests)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import date
from io import StringIO
from uuid import UUID

from django.db.models import QuerySet

from apps.finance.models import CashbookEntry
from apps.tenants.models import TenantSettings

from .profitability import build_merchandise_profitability
from .sales_summary import build_sales_summary


def _spreadsheet_text(value) -> str:
    """Prevent untrusted item/location names from becoming spreadsheet formulas."""
    cell = str(value or "")
    return "'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell


def write_sales_summary_csv(writer: csv.writer, summary: dict) -> None:
    writer.writerow(["metric", "value"])
    writer.writerow(["payments_count", summary["payments_count"]])
    writer.writerow(["gross_sales", summary["gross_sales"]])
    writer.writerow(["refunds_total", summary["refunds_total"]])
    writer.writerow(["net_sales", summary["net_sales"]])
    writer.writerow([])
    writer.writerow(["section", "gross_sales", "refunds_total", "net_sales"])
    for row in summary["by_section"]:
        writer.writerow([_spreadsheet_text(row["section_label"]), row["gross_sales"], row["refunds_total"], row["net_sales"]])
    writer.writerow([])
    writer.writerow(["payment_method", "count", "amount"])
    for row in summary["by_payment_method"]:
        writer.writerow([_spreadsheet_text(row["method"]), row["count"], row["amount"]])
    writer.writerow([])
    writer.writerow(["outlet_name", "payment_count", "amount"])
    for row in summary["by_outlet"]:
        writer.writerow([_spreadsheet_text(row["outlet_name"]), row["count"], row["amount"]])
    writer.writerow([])
    writer.writerow(["item", "quantity_sold", "revenue"])
    for it in summary["top_items"]:
        writer.writerow([_spreadsheet_text(it["item_name"]), it["quantity_sold"], it["revenue"]])

    profitability = summary.get("merchandise_profitability")
    if profitability:
        writer.writerow([])
        writer.writerow(["merchandise_profitability_metric", "value", "currency_or_unit"])
        writer.writerow(["net_merchandise_revenue", profitability["net_merchandise_revenue"], profitability["currency"]])
        writer.writerow(["covered_net_revenue", profitability["covered_net_revenue"], profitability["currency"]])
        writer.writerow(["uncovered_net_revenue", profitability["uncovered_net_revenue"], profitability["currency"]])
        writer.writerow(["covered_return_revenue", profitability["covered_return_revenue"], profitability["currency"]])
        writer.writerow(["known_net_cogs", profitability["known_net_cogs"], profitability["currency"]])
        writer.writerow(["known_gross_profit", profitability["known_gross_profit"], profitability["currency"]])
        writer.writerow(["known_margin_percent", profitability["known_margin_percent"] if profitability["known_margin_percent"] is not None else "", "%"])
        writer.writerow(["cost_coverage_percent", profitability["cost_coverage_percent"], "%"])
        writer.writerow(["incomplete_sale_lines", profitability["incomplete_sale_lines"], "count"])
        writer.writerow(["unmapped_refund_amount", profitability["unmapped_refund_amount"], profitability["currency"]])
        writer.writerow(["profitability_complete", "yes" if profitability["profitability_complete"] else "no", ""])
        writer.writerow(["margin_breach_sale_count", profitability.get("margin_breach_sale_count", 0), "count"])
        writer.writerow(["margin_breach_revenue", profitability.get("margin_breach_revenue", "0.00"), profitability["currency"]])
        writer.writerow(["margin_breach_gross_profit", profitability.get("margin_breach_gross_profit", "0.00"), profitability["currency"]])
        writer.writerow(["margin_breach_shortfall", profitability.get("margin_breach_shortfall", "0.00"), profitability["currency"]])
        writer.writerow([])
        writer.writerow([
            "merchandise_product", "sku", "net_revenue", "covered_net_revenue",
            "uncovered_net_revenue", "known_net_cogs", "known_gross_profit",
            "known_margin_percent", "incomplete_cost_lines",
        ])
        for row in profitability["products"]:
            writer.writerow([
                _spreadsheet_text(row["item_name"]), _spreadsheet_text(row["sku"]),
                row["net_revenue"], row["covered_net_revenue"],
                row["uncovered_net_revenue"], row["known_net_cogs"],
                row["known_gross_profit"],
                row["known_margin_percent"] if row["known_margin_percent"] is not None else "",
                row["incomplete_lines"] + row["incomplete_return_lines"],
            ])

        if profitability.get("categories"):
            writer.writerow([])
            writer.writerow([
                "merchandise_category", "net_revenue", "covered_net_revenue",
                "uncovered_net_revenue", "known_net_cogs", "known_gross_profit",
                "known_margin_percent", "incomplete_cost_lines",
            ])
            for row in profitability["categories"]:
                writer.writerow([
                    _spreadsheet_text(row["category_name"]),
                    row["net_revenue"], row["covered_net_revenue"],
                    row["uncovered_net_revenue"], row["known_net_cogs"],
                    row["known_gross_profit"],
                    row["known_margin_percent"] if row["known_margin_percent"] is not None else "",
                    row["incomplete_lines"] + row["incomplete_return_lines"],
                ])

        if profitability.get("outlets"):
            writer.writerow([])
            writer.writerow([
                "merchandise_outlet", "net_revenue", "covered_net_revenue",
                "uncovered_net_revenue", "known_net_cogs", "known_gross_profit",
                "known_margin_percent", "cost_coverage_percent",
                "incomplete_cost_lines",
            ])
            for row in profitability["outlets"]:
                writer.writerow([
                    _spreadsheet_text(row["outlet_name"]),
                    row["net_revenue"], row["covered_net_revenue"],
                    row["uncovered_net_revenue"], row["known_net_cogs"],
                    row["known_gross_profit"],
                    row["known_margin_percent"] if row["known_margin_percent"] is not None else "",
                    row["cost_coverage_percent"],
                    row["incomplete_lines"] + row["incomplete_return_lines"],
                ])

        if profitability.get("unknown_cost_exposure"):
            writer.writerow([])
            writer.writerow([
                "unknown_cost_product", "sku",
                "uncovered_net_revenue", "incomplete_cost_lines",
            ])
            for row in profitability["unknown_cost_exposure"]:
                writer.writerow([
                    _spreadsheet_text(row["item_name"]),
                    _spreadsheet_text(row["sku"]),
                    row["uncovered_net_revenue"],
                    row["incomplete_lines"],
                ])

        if profitability.get("margin_exceptions"):
            writer.writerow([])
            writer.writerow([
                "margin_exception_outlet", "product", "sku",
                "covered_net_revenue", "known_net_cogs",
                "known_gross_profit", "known_margin_percent",
                "configured_margin_floor_percent",
            ])
            for row in profitability["margin_exceptions"]:
                writer.writerow([
                    _spreadsheet_text(row["outlet_name"]),
                    _spreadsheet_text(row["item_name"]),
                    _spreadsheet_text(row["sku"]),
                    row["covered_net_revenue"],
                    row["known_net_cogs"],
                    row["known_gross_profit"],
                    row["known_margin_percent"],
                    row["margin_floor_percent"],
                ])

        if profitability.get("margin_breach_sales"):
            writer.writerow([])
            writer.writerow([
                "below_floor_sale", "outlet", "product", "sku",
                "quantity", "net_revenue", "known_cogs",
                "known_gross_profit", "known_margin_percent",
                "configured_margin_floor_percent", "target_gross_profit",
                "margin_shortfall", "cashier", "margin_override_linked",
                "override_requester", "override_approver", "override_reason",
                "override_approved_at",
            ])
            for row in profitability["margin_breach_sales"]:
                writer.writerow([
                    _spreadsheet_text(row["bill_reference"]),
                    _spreadsheet_text(row["outlet_name"]),
                    _spreadsheet_text(row["item_name"]),
                    _spreadsheet_text(row["sku"]),
                    row["quantity"], row["net_revenue"], row["known_cogs"],
                    row["known_gross_profit"],
                    row["known_margin_percent"] if row["known_margin_percent"] is not None else "",
                    row["margin_floor_percent"], row["target_gross_profit"],
                    row["margin_shortfall"],
                    _spreadsheet_text(row.get("cashier_email", "")),
                    "yes" if row.get("has_linked_margin_override") else "no",
                    _spreadsheet_text(row.get("override_requester_email", "")),
                    _spreadsheet_text(row.get("override_approver_email", "")),
                    _spreadsheet_text(row.get("override_reason", "")),
                    (
                        row["override_approved_at"].isoformat()
                        if row.get("override_approved_at") else ""
                    ),
                ])


def format_sales_summary_csv(
    tenant_id: UUID,
    d0: date,
    d1: date,
    outlet_id: UUID | None = None,
    *,
    allowed_outlet_ids: list[UUID] | None = None,
    outlet_ids: list[UUID] | None = None,
    business_date_site=None,
) -> str:
    summary = build_sales_summary(
        tenant_id,
        d0,
        d1,
        outlet_id,
        allowed_outlet_ids=allowed_outlet_ids,
        outlet_ids=outlet_ids,
        business_date_site=business_date_site,
    )
    if outlet_id is not None:
        effective_outlet_ids = [outlet_id]
    elif outlet_ids is not None:
        effective_outlet_ids = outlet_ids
    else:
        effective_outlet_ids = allowed_outlet_ids
    if effective_outlet_ids is not None:
        currency = (
            TenantSettings.objects.filter(tenant_id=tenant_id)
            .values_list("default_currency", flat=True)
            .first()
            or "UGX"
        )
        summary["merchandise_profitability"] = build_merchandise_profitability(
            tenant_id=tenant_id,
            date_from=d0,
            date_to=d1,
            allowed_outlet_ids=effective_outlet_ids,
            currency=currency,
            business_date_site=business_date_site,
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
                _spreadsheet_text(e.category.name),
                _spreadsheet_text(e.site.name) if e.site else "",
                str(e.amount),
                _spreadsheet_text(e.reference),
                _spreadsheet_text((e.note or "").replace("\n", " ").replace("\r", " ")),
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
