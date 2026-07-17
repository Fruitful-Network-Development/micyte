"""Lightweight quantity parsing for agro_erp nominals ('25 lbs', '$95.00', '500 slips').

Nominals are stored as free ASCII (a number + a unit word). This parses them back to a
(value, unit) pair, converts mass units to grams, and recognizes count units (slips / roots /
counts) where the number IS already the unit count. Used by the inventory synopsis to derive
unit counts from purchased weight ÷ per-unit weight; replaces the bespoke ``_parse_weight``
numeric-prefix extractor (kept as a shim in contracts_tool).
"""

from __future__ import annotations

from micyte.core.structures.samras.structure import as_text

# mass unit → grams
_MASS_TO_G: dict[str, float] = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kgs": 1000.0,
    "oz": 28.349523125, "ounce": 28.349523125, "ounces": 28.349523125,
    "lb": 453.59237, "lbs": 453.59237, "pound": 453.59237, "pounds": 453.59237,
}
# units where the leading number is already a discrete count (no per-unit weight needed)
_COUNT_UNITS: frozenset[str] = frozenset({
    "slip", "slips", "root", "roots", "bulb", "bulbs", "count", "counts",
    "each", "unit", "units", "plant", "plants", "set", "sets",
})


def parse_quantity(text: object) -> tuple[float, str]:
    """('25 lbs') → (25.0, 'lbs'); ('$95.00') → (95.0, ''); ('') → (0.0, '').

    Leading currency symbols are ignored; the unit is the first trailing alpha token
    (lower-cased). Returns (0.0, '') when no number is present.
    """
    s = as_text(text).strip().lstrip("$").strip()
    num = ""
    i = 0
    for i, ch in enumerate(s):  # noqa: B007 - i used after loop
        if ch.isdigit() or ch in ".-":
            num += ch
        else:
            break
    else:
        i = len(s)
    unit = s[i:].strip().lower()
    # keep only the first alpha word of the unit (drop trailing notes)
    unit = unit.split()[0] if unit.split() else ""
    try:
        value = float(num) if num else 0.0
    except ValueError:
        value = 0.0
    return value, unit


def is_count_unit(unit: object) -> bool:
    return as_text(unit).strip().lower() in _COUNT_UNITS


def to_grams(value: float, unit: object) -> float | None:
    """Convert a mass quantity to grams, or ``None`` when the unit is not a known mass unit."""
    factor = _MASS_TO_G.get(as_text(unit).strip().lower())
    return value * factor if factor is not None else None


def derive_unit_count(quantity_text: object, unit_weight_text: object) -> int | None:
    """How many discrete units a purchased quantity represents.

    - count unit (slips/roots/…): the leading number IS the count.
    - mass unit (lbs/oz/g): grams(quantity) // grams(per-unit weight).
    Returns ``None`` when it can't be derived (unknown unit / missing-or-zero unit weight).
    """
    qty, unit = parse_quantity(quantity_text)
    if is_count_unit(unit):
        return int(qty)
    grams = to_grams(qty, unit)
    if grams is None:
        return None
    uw_val, uw_unit = parse_quantity(unit_weight_text)
    uw_g = to_grams(uw_val, uw_unit)
    if not uw_g:
        return None
    # Floor, but nudge by a tiny epsilon so an exact division that float represents as
    # X.9999999996 (e.g. 3.0 / 0.1) counts as X+1, not X (IEEE-754 floor-division gotcha).
    return int(grams / uw_g + 1e-9)
