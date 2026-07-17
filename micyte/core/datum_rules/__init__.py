"""MOS datum shape/arity rules (pure core authority)."""

from .rules import (
    SHAPE_PAIRS,
    SHAPE_RECORD,
    SHAPE_RUDI,
    SHAPE_SCALAR,
    SHAPE_UNKNOWN,
    Column,
    DatumShape,
    classify_row,
    family_column_template,
    validate_row,
)

__all__ = [
    "SHAPE_PAIRS",
    "SHAPE_RECORD",
    "SHAPE_RUDI",
    "SHAPE_SCALAR",
    "SHAPE_UNKNOWN",
    "Column",
    "DatumShape",
    "classify_row",
    "family_column_template",
    "validate_row",
]
