"""MOS datum shape/arity authority (pure, stdlib-only).

Classifies a datum row into one of the structural shapes that occur in the
canonical catalog, and derives the positional column template for a
``(layer, value_group)`` family. This is the single place the workbench grid
asks "what cells does this row/family have?" so the Datum IDE never re-derives
shape logic ad hoc.

Shapes (census over the live FND catalog, 47,234 rows):

* ``PAIRS``  — ``raw = [[address, ref1, mag1, ref2, mag2, ...], tail]`` with a
  list tail and ``value_group >= 1``. The dominant family (~96% of rows). The
  pair count is ``(len(head) - 1) // 2`` taken from the ROW, not from
  ``value_group`` — the two usually match (``head_len == 2*value_group + 1``)
  but diverge in real data (e.g. a ``value_group=1`` contact row with 4 pairs),
  so ``value_group`` is treated as advisory, never as the source of truth.
* ``RECORD`` — list ``raw`` whose tail (``raw[1]``) is a ``dict`` of named
  magnitudes (archetype records: contact logs, product/taxonomy rows).
* ``RUDI``   — ``value_group == 0`` with a list tail; the head is
  ``[address, '~', ref, ref, ...]`` carrying a *variable* number of
  instantaneous references to lower-abstraction datums.
* ``SCALAR`` — ``raw`` is a bare scalar (``str``/``int``/...), not a
  ``[head, ...]`` structure (identity/metadata datums).
* ``UNKNOWN``— the datum address does not parse; classification is still total.

Every function is TOTAL: it never raises on malformed input, mirroring the
recognition layer's tolerance, because the catalog is not shape-validated on
write.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

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

SHAPE_PAIRS = "pairs"
SHAPE_RECORD = "record"
SHAPE_RUDI = "rudi"
SHAPE_SCALAR = "scalar"
SHAPE_UNKNOWN = "unknown"

RUDI_RELATION = "~"

_ADDRESS_RE = re.compile(r"^([0-9]+)-([0-9]+)-([0-9]+)$")


def _parse_address(datum_address: object) -> tuple[int, int, int] | None:
    match = _ADDRESS_RE.fullmatch(str(datum_address if datum_address is not None else "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _head_of(raw: Any) -> list[Any] | None:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return None


@dataclass(frozen=True)
class DatumShape:
    """The classified structure of a single datum row."""

    datum_address: str
    layer: int
    value_group: int
    iteration: int
    shape: str
    pair_count: int
    head_len: int
    tail_kind: str
    well_formed: bool
    issues: tuple[str, ...] = ()


def classify_row(datum_address: object, raw: Any) -> DatumShape:
    """Classify one datum row. Never raises."""

    parsed = _parse_address(datum_address)
    if parsed is None:
        return DatumShape(
            datum_address=str(datum_address if datum_address is not None else ""),
            layer=-1,
            value_group=-1,
            iteration=-1,
            shape=SHAPE_UNKNOWN,
            pair_count=0,
            head_len=0,
            tail_kind="none",
            well_formed=False,
            issues=("address_unparsable",),
        )

    layer, value_group, iteration = parsed
    address = f"{layer}-{value_group}-{iteration}"

    head = _head_of(raw)
    if head is None:
        # Bare scalar payload (str/int/...): a valid identity/metadata datum.
        return DatumShape(
            datum_address=address,
            layer=layer,
            value_group=value_group,
            iteration=iteration,
            shape=SHAPE_SCALAR,
            pair_count=0,
            head_len=0,
            tail_kind=type(raw).__name__ if raw is not None else "none",
            well_formed=True,
        )

    head_len = len(head)
    tail = raw[1] if isinstance(raw, list) and len(raw) >= 2 else None
    if isinstance(tail, dict):
        tail_kind = "dict"
    elif isinstance(tail, list):
        tail_kind = "list"
    elif tail is None:
        tail_kind = "none"
    else:
        tail_kind = type(tail).__name__

    issues: list[str] = []
    if isinstance(tail, dict):
        shape = SHAPE_RECORD
        pair_count = 0
        well_formed = head_len >= 1
        if not well_formed:
            issues.append("record_head_empty")
    elif value_group == 0:
        shape = SHAPE_RUDI
        pair_count = 0
        well_formed = head_len >= 1
        if not well_formed:
            issues.append("rudi_head_empty")
    else:
        shape = SHAPE_PAIRS
        pair_count = max((head_len - 1) // 2, 0)
        well_formed = head_len >= 3 and head_len % 2 == 1
        if not well_formed:
            issues.append("pairs_arity_malformed")
        elif pair_count != value_group:
            # Advisory only: the address's value_group is the conventional pair
            # count but real rows diverge; the row's own width is authoritative.
            issues.append("value_group_pair_mismatch")

    return DatumShape(
        datum_address=address,
        layer=layer,
        value_group=value_group,
        iteration=iteration,
        shape=shape,
        pair_count=pair_count,
        head_len=head_len,
        tail_kind=tail_kind,
        well_formed=well_formed,
        issues=tuple(issues),
    )


def validate_row(datum_address: object, raw: Any) -> list[str]:
    """Return shape issues for a row (empty list == clean). Never raises."""

    return list(classify_row(datum_address, raw).issues)


@dataclass(frozen=True)
class Column:
    """One column in a family's grid template."""

    role: str  # address | relation | reference | magnitude | value | record_key | references
    index: int = 0  # 1-based pair index for reference/magnitude
    key: str = ""  # dict key for record_key columns
    variadic: bool = False  # the column spans a variable number of cells


def family_column_template(rows: Iterable[tuple[object, Any]]) -> list[Column]:
    """Derive the positional column template for one ``(layer, value_group)`` family.

    ``rows`` is an iterable of ``(datum_address, raw)`` pairs already bucketed
    into a single family. Column WIDTH is taken from the family's actual rows
    (so a row whose pair count exceeds its ``value_group`` still gets cells),
    not from address arithmetic.
    """

    materialized = list(rows)
    shapes = [classify_row(addr, raw) for addr, raw in materialized]
    typed = [shape for shape in shapes if shape.shape != SHAPE_UNKNOWN]
    if not typed:
        return [Column("address")]

    dominant = Counter(shape.shape for shape in typed).most_common(1)[0][0]

    if dominant == SHAPE_PAIRS:
        max_pairs = max((shape.pair_count for shape in typed if shape.shape == SHAPE_PAIRS), default=0)
        columns = [Column("address")]
        for index in range(1, max_pairs + 1):
            columns.append(Column("reference", index=index))
            columns.append(Column("magnitude", index=index))
        return columns

    if dominant == SHAPE_RUDI:
        return [Column("address"), Column("relation"), Column("references", variadic=True)]

    if dominant == SHAPE_RECORD:
        keys: list[str] = []
        seen: set[str] = set()
        for _, raw in materialized:
            tail = raw[1] if isinstance(raw, list) and len(raw) >= 2 else None
            if isinstance(tail, dict):
                for key in tail.keys():
                    text = str(key)
                    if text not in seen:
                        seen.add(text)
                        keys.append(text)
        columns = [Column("address"), Column("relation"), Column("reference", index=1)]
        columns.extend(Column("record_key", key=key) for key in keys)
        return columns

    if dominant == SHAPE_SCALAR:
        return [Column("address"), Column("value")]

    return [Column("address")]
