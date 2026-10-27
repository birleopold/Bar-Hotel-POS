from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod

from apps.finance.models import AccountingExportBatch


def spreadsheet_safe(value) -> str:
    token = str(value or "")
    return "'" + token if token.startswith(("=", "+", "-", "@", "\t", "\r")) else token


class AccountingExportAdapter(ABC):
    """Provider boundary for immutable AccountingExportBatch snapshots."""

    key: str
    label: str
    content_type: str
    file_extension: str

    @abstractmethod
    def render(self, batch: AccountingExportBatch) -> str:
        raise NotImplementedError


class JournalCsvAdapter(AccountingExportAdapter):
    key = "journal_csv"
    label = "Journal-ready CSV"
    content_type = "text/csv; charset=utf-8"
    file_extension = "csv"

    def render(self, batch: AccountingExportBatch) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([
            "date_from",
            "date_to",
            "currency",
            "account_code",
            "account_name",
            "debit",
            "credit",
            "memo",
            "site",
            "site_id",
            "outlet",
            "outlet_id",
            "register",
            "cashier",
            "tender",
            "category",
            "folio",
            "supplier",
            "source_references",
        ])
        for line in batch.journal_lines:
            dims = line.get("dimensions") or {}
            writer.writerow([
                batch.date_from,
                batch.date_to,
                spreadsheet_safe(batch.currency),
                spreadsheet_safe(line.get("account_code")),
                spreadsheet_safe(line.get("account_name")),
                line.get("debit", "0.00"),
                line.get("credit", "0.00"),
                spreadsheet_safe(line.get("memo")),
                spreadsheet_safe(dims.get("site")),
                spreadsheet_safe(dims.get("site_id")),
                spreadsheet_safe(dims.get("outlet")),
                spreadsheet_safe(dims.get("outlet_id")),
                spreadsheet_safe(dims.get("register")),
                spreadsheet_safe(dims.get("cashier")),
                spreadsheet_safe(dims.get("tender")),
                spreadsheet_safe(dims.get("category")),
                spreadsheet_safe(dims.get("folio")),
                spreadsheet_safe(dims.get("supplier")),
                spreadsheet_safe(";".join(line.get("source_refs") or [])),
            ])
        return out.getvalue()


ADAPTERS = {
    JournalCsvAdapter.key: JournalCsvAdapter(),
}


def accounting_export_adapter(key: str = JournalCsvAdapter.key) -> AccountingExportAdapter:
    try:
        return ADAPTERS[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported accounting export adapter: {key}") from exc
