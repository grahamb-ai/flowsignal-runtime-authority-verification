from decimal import Decimal

import pytest

from app.engines.money import canonical_money, canonical_money_text


def test_exact_money_accepts_integer_and_decimal_text():
    assert canonical_money(750000) == Decimal("750000.00")
    assert canonical_money("750000.10") == Decimal("750000.10")
    assert canonical_money_text(750000) == "750000.00"


def test_binary_float_is_rejected_at_authority_boundary():
    with pytest.raises(TypeError):
        canonical_money(0.1)


def test_sub_minor_unit_precision_is_rejected():
    with pytest.raises(ValueError):
        canonical_money("1.001")


def test_non_finite_money_is_rejected():
    with pytest.raises(ValueError):
        canonical_money("NaN")
