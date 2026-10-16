"""Customer entry uses conservative phone normalization and validation."""
import pytest
from apps.staff.forms.customers import StaffCustomerForm


@pytest.mark.parametrize("raw,normalized", [
    ("+256 700-123-456", "+256700123456"),
    ("0700 123 456", "0700123456"),
    (" (020) 123.4567 ", "0201234567"),
])
def test_customer_form_normalizes_phone_separators(raw, normalized):
    form = StaffCustomerForm(data={"name": "Test guest", "phone": raw})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["phone"] == normalized


@pytest.mark.parametrize("raw", ["abcdefghi", "+12", "1234567890123456", "0700 ext 123"])
def test_customer_form_rejects_invalid_phone(raw):
    form = StaffCustomerForm(data={"name": "Test guest", "phone": raw})
    assert not form.is_valid()
    assert "phone" in form.errors


def test_customer_form_leaves_blank_phone_optional():
    form = StaffCustomerForm(data={"name": "Guest without phone", "phone": ""})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["phone"] == ""
