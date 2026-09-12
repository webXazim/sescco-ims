from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ONES = (
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
    "Eighteen", "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
_SCALES = ((1_000_000_000_000, "Trillion"), (1_000_000_000, "Billion"), (1_000_000, "Million"), (1_000, "Thousand"))
_CURRENCY_NAMES = {
    "SAR": ("Saudi Riyal", "Saudi Riyals", "Halala", "Halalas"),
    "AED": ("UAE Dirham", "UAE Dirhams", "Fils", "Fils"),
    "USD": ("US Dollar", "US Dollars", "Cent", "Cents"),
}


def _under_thousand(value: int) -> str:
    parts: list[str] = []
    if value >= 100:
        parts.extend((_ONES[value // 100], "Hundred"))
        value %= 100
    if value >= 20:
        parts.append(_TENS[value // 10])
        if value % 10:
            parts.append(_ONES[value % 10])
    elif value:
        parts.append(_ONES[value])
    return " ".join(parts)


def integer_to_words(value: int) -> str:
    if value < 0:
        return f"Minus {integer_to_words(-value)}"
    if value == 0:
        return _ONES[0]
    if value >= 1_000_000_000_000_000:
        raise ValueError("Amount is too large to convert to words.")
    parts: list[str] = []
    remaining = value
    for divisor, label in _SCALES:
        count, remaining = divmod(remaining, divisor)
        if count:
            parts.extend((integer_to_words(count), label))
    if remaining:
        parts.append(_under_thousand(remaining))
    return " ".join(parts)


def money_to_words(value, currency_code: str = "SAR") -> str:
    """Return a deterministic English amount-in-words string for immutable documents."""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid monetary amount.") from exc
    if not amount.is_finite():
        raise ValueError("Invalid monetary amount.")

    sign = "Minus " if amount < 0 else ""
    amount = abs(amount)
    major = int(amount)
    minor = int((amount - Decimal(major)) * 100)
    code = (currency_code or "SAR").strip().upper()
    singular_major, plural_major, singular_minor, plural_minor = _CURRENCY_NAMES.get(
        code, (code, code, "Minor Unit", "Minor Units")
    )
    major_label = singular_major if major == 1 else plural_major
    result = f"{sign}{integer_to_words(major)} {major_label}"
    if minor:
        minor_label = singular_minor if minor == 1 else plural_minor
        result += f" and {integer_to_words(minor)} {minor_label}"
    return f"{result} Only"
