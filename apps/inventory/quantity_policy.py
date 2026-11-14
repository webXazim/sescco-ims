"""Single source of truth for whole-number Inventory units.

Legacy installations may have decimal-enabled 'piece' units due to imported
fractional balances. Do not let that persisted flag authorize new fractions.
"""
from decimal import Decimal, InvalidOperation

COUNTABLE_UNIT_ALIASES = frozenset({
    "pc", "pcs", "pce", "piece", "pieces", "no", "nos", "nr", "number", "numbers",
    "each", "ea", "unit", "units", "set", "sets", "box", "boxes", "carton", "cartons",
    "bag", "bags", "pair", "pairs", "roll", "rolls", "pack", "packs", "packet", "packets",
    "kit", "kits", "laptop", "laptops", "bottle", "bottles", "can", "cans",
    "drum", "drums", "pallet", "pallets", "bundle", "bundles", "sheet", "sheets",
    "panel", "panels", "device", "devices", "machine", "machines", "item", "items",
})


def is_named_countable(name, symbol):
    def key(value):
        return str(value or "").strip().casefold().rstrip(".")
    return key(name) in COUNTABLE_UNIT_ALIASES or key(symbol) in COUNTABLE_UNIT_ALIASES


def allows_fractional(unit):
    """Countable symbols/names take precedence over an old database setting."""
    return bool(unit and unit.allows_fractional_quantities and
                not is_named_countable(unit.name, unit.symbol))


def is_whole(value):
    try:
        value = Decimal(value)
        return value.is_finite() and value == value.to_integral_value()
    except (ValueError, TypeError, InvalidOperation):
        return False
