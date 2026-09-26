from __future__ import annotations

from decimal import Decimal, InvalidOperation


def canonical_money(value: Decimal | str | int) -> Decimal:
    """Return an exact two-decimal payment amount.

    Binary floating-point is deliberately rejected at the authority boundary.
    The reference payment fixture uses GBP-style minor-unit precision.
    """
    if isinstance(value, float):
        raise TypeError("binary floating-point is not permitted for authority-material money")

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc

    if not amount.is_finite():
        raise ValueError("monetary value must be finite")
    if amount.as_tuple().exponent < -2:
        raise ValueError("monetary value exceeds canonical minor-unit precision")

    return amount.quantize(Decimal("0.01"))


def canonical_money_text(value: Decimal | str | int) -> str:
    return format(canonical_money(value), ".2f")
