"""Convert cartons into base inventory units, never a second stock ledger."""
from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError

MAX_UNITS = Decimal("99999999999.999")


def to_stock_units(*, units=0, cartons=0, units_per_carton=1, allow_zero=False):
    try:
        loose = Decimal(str(0 if units is None else units))
        cases = Decimal(str(0 if cartons is None else cartons))
        factor = int(units_per_carton)
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"quantity": "Enter a valid quantity and whole cartons."}) from exc
    if not (1 <= factor <= 10000):
        raise ValidationError({"cartons": "Invalid product carton size."})
    if (not loose.is_finite() or loose < 0 or loose > MAX_UNITS
            or loose != loose.quantize(Decimal("0.001"))):
        raise ValidationError({"quantity": "Loose units must be non-negative with up to three decimals."})
    if not cases.is_finite() or cases < 0 or cases != cases.to_integral_value():
        raise ValidationError({"cartons": "Cartons must be a non-negative whole number."})
    if cases and factor == 1:
        raise ValidationError({"cartons": "Configure pieces per carton on the product before using cartons."})
    total = loose + cases * factor
    if total > MAX_UNITS or (total <= 0 and not (allow_zero and total == 0)):
        raise ValidationError({"quantity": "Enter a valid positive quantity within stock limits."})
    return total
