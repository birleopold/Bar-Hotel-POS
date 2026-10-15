"""Deterministic FEFO allocation planning.

This module does not mutate stock: callers must separately lock and persist
batch records in a transaction. An unknown expiry is allocated last, and
expired batches are excluded by default.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


class InsufficientBatchStock(ValueError):
    pass


def plan_fefo_allocation(batches, quantity, *, as_of=None, allow_expired=False):
    """Return [(batch identifier, quantity)] in FEFO order.

    Each input is a mapping with id, quantity and expiry_date (date or None).
    Rejects duplicate identifiers and negative quantities. A planner result
    is never itself evidence that stock was consumed.
    """
    today = as_of or date.today()
    try:
        needed = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid requested quantity") from exc
    if not needed.is_finite() or needed <= 0:
        raise ValueError("Requested quantity must be positive and finite")
    eligible = []
    identifiers = set()
    for entry in batches:
        identifier = entry["id"]
        if identifier in identifiers:
            raise ValueError("Duplicate batch identifier")
        identifiers.add(identifier)
        try:
            available = Decimal(str(entry["quantity"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid batch quantity") from exc
        if not available.is_finite() or available < 0:
            raise ValueError("Batch quantity must be nonnegative and finite")
        expiry = entry.get("expiry_date")
        if expiry is not None and not isinstance(expiry, date):
            raise ValueError("expiry_date must be a date or None")
        if available and (allow_expired or expiry is None or expiry >= today):
            eligible.append((expiry or date.max, str(identifier), identifier, available))
    eligible.sort(key=lambda row: (row[0], row[1]))
    allocation = []
    for _, _, identifier, available in eligible:
        take = min(needed, available)
        if take:
            allocation.append((identifier, take))
            needed -= take
        if needed == 0:
            return allocation
    raise InsufficientBatchStock("Insufficient eligible batch stock")
