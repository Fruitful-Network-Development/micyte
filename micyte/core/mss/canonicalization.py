"""Canonicalization helpers for datum-row sequences.

These pure-stdlib functions enforce the MOS row-ordering invariants that
must hold before a document can be MSS-hashed and written to the
``documents`` table:

* iteration values within a ``(layer, value_group)`` family are
  contiguous (``1, 2, 3, ...``); skips are repaired by shifting later
  iterations down.
* same-family rows are sorted by SAMRAS magnitude (when supplied),
  with ``layer/value_group/iteration`` as the deterministic tiebreaker.

The functions operate on a list of ``Mapping[str, Any]`` rows (each with
at least ``datum_address``); ``raw`` and any other content is preserved.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

_DATUM_ADDRESS_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")


def _parse_address(text: str) -> tuple[int, int, int]:
    if not _DATUM_ADDRESS_RE.fullmatch(text or ""):
        raise ValueError(f"invalid datum address: {text!r}")
    layer, value_group, iteration = (text or "").split("-")
    return int(layer), int(value_group), int(iteration)


def _format_address(layer: int, value_group: int, iteration: int) -> str:
    return f"{layer}-{value_group}-{iteration}"


def _row_address(row: Mapping[str, Any]) -> str:
    addr = row.get("datum_address")
    if not isinstance(addr, str):
        raise ValueError("row missing 'datum_address'")
    return addr


def _rewrite_address(row: Mapping[str, Any], new_address: str) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)
    out["datum_address"] = new_address
    return out


def canonicalize_iteration_addresses(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Repair iteration-skip violations within each ``(layer, value_group)``.

    Within each family, iteration values are renumbered to be contiguous
    starting from 1, preserving the *relative* ordering by current
    iteration. Returns ``(canonicalized_rows, address_remap)`` where
    ``address_remap`` maps old → new for every changed address.

    ``rows`` is left unchanged; the canonical list is returned in the
    canonical sort order ``(layer, value_group, new_iteration)``.
    """

    parsed: list[tuple[int, int, int, dict[str, Any]]] = []
    for row in rows:
        layer, value_group, iteration = _parse_address(_row_address(row))
        parsed.append((layer, value_group, iteration, dict(row)))

    parsed.sort(key=lambda item: (item[0], item[1], item[2]))

    remap: dict[str, str] = {}
    repaired: list[dict[str, Any]] = []
    last_family: tuple[int, int] | None = None
    next_iteration = 0
    for layer, value_group, iteration, row in parsed:
        family = (layer, value_group)
        if family != last_family:
            last_family = family
            next_iteration = 1
        old_addr = _format_address(layer, value_group, iteration)
        new_addr = _format_address(layer, value_group, next_iteration)
        if old_addr != new_addr:
            remap[old_addr] = new_addr
        repaired.append(_rewrite_address(row, new_addr))
        next_iteration += 1

    return repaired, remap


def canonicalize_value_group_ordering(
    rows: Iterable[Mapping[str, Any]],
    *,
    magnitude_of: Callable[[Mapping[str, Any]], int | None] | None = None,
) -> list[dict[str, Any]]:
    """Order rows within each ``(layer, value_group)`` by SAMRAS magnitude.

    ``magnitude_of`` is invoked per row and may return ``None`` for rows
    without an explicit magnitude; those rows fall back to their current
    iteration value. The function returns rows in the canonical sort
    order ``(layer, value_group, magnitude_or_iteration, original_index)``.

    This does **not** re-number iteration; iterations are left as-is so a
    caller can subsequently invoke ``canonicalize_iteration_addresses`` if
    they want a contiguous sequence after reordering.
    """

    rows_list = list(rows)
    decorated: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for index, row in enumerate(rows_list):
        layer, value_group, iteration = _parse_address(_row_address(row))
        magnitude = magnitude_of(row) if magnitude_of is not None else None
        sort_key = magnitude if isinstance(magnitude, int) else iteration
        decorated.append((layer, value_group, sort_key, index, dict(row)))

    decorated.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [item[4] for item in decorated]


__all__ = [
    "canonicalize_iteration_addresses",
    "canonicalize_value_group_ordering",
]
