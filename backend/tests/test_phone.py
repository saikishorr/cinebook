"""Phone helpers - no database needed."""
import pytest

from app.phone import mask_phone, normalize_phone, parse_number_list


@pytest.mark.parametrize("typed", ["9812345678", "09812345678", "919812345678", "+919812345678",
                                   "+91 98123-45678", "(+91) 98123 45678", "0091 9812345678"])
def test_indian_mobile_numbers_are_converted(typed):
    assert normalize_phone(typed) == "+919812345678"


def test_other_countries_in_international_form_are_kept():
    assert normalize_phone("+14155550123") == "+14155550123"


@pytest.mark.parametrize("typed", ["", None, "12345", "5812345678", "98123456789012345", "+0123456789", "abc"])
def test_invalid_numbers_are_refused(typed):
    with pytest.raises(ValueError):
        normalize_phone(typed)


def test_number_list_from_settings_ignores_bad_entries():
    assert parse_number_list("9812345678, junk , +919876543210,") == {"+919812345678", "+919876543210"}


def test_masking_shows_only_last_four_digits():
    assert mask_phone("+919812345678") == "+91 ******5678"
    assert mask_phone(None) is None
