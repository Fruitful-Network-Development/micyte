"""Polygon / multi-polygon row-group assembly for HOPS-typed datum families.

The CTS-GIS spatial chain assembles geographic features from a row tree
following the family layering ``4 → 5 → 6 → 7``:

* family ``4`` rows are individual coordinate rings (terminal nodes)
* family ``5`` rows aggregate a list of family-4 rings into one polygon
* family ``6`` rows aggregate family-4 rings or family-5 polygons into a
  multi-polygon
* family ``7`` rows aggregate everything below into a feature collection

This helper is **generic**: it operates on a flat dict of ``row_address ->
row_record`` where each row exposes (a) its address (in the dict key) and
(b) a list of *linked* row addresses provided by the caller. No
``DatumRecognitionRow`` or other framework dependency.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping

_DATUM_ADDRESS_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")


def _row_family(address: str) -> str:
    return (address or "").split("-", 1)[0]


def _is_address(token: str) -> bool:
    return bool(_DATUM_ADDRESS_RE.fullmatch(token or ""))


def assemble_polygon_groups(
    row_address: str,
    *,
    rows: Mapping[str, object],
    linked_addresses_of: Callable[[str], Iterable[str]],
) -> list[list[str]]:
    """Resolve the polygon row-groups rooted at ``row_address``.

    Returns a list of polygons, each a list of family-``4`` row addresses
    (the rings of that polygon, in declared order).

    * a family-``4`` root yields a single one-ring polygon
    * a family-``5`` root yields one polygon whose rings are the family-4
      addresses listed in ``linked_addresses_of(row_address)``
    * a family-``6`` root recurses through its linked family-5 entries
      (delegating polygon assembly to the recursive call) and includes
      direct family-4 children as singleton polygons
    * a family-``7`` root recurses through any family-4/5/6 link
    * any other family yields an empty result.
    """

    if row_address not in rows:
        return []

    family = _row_family(row_address)
    linked: list[str] = [
        addr
        for addr in linked_addresses_of(row_address)
        if isinstance(addr, str) and _is_address(addr) and addr in rows
    ]

    if family == "4":
        return [[row_address]]

    if family == "5":
        rings = [addr for addr in linked if _row_family(addr) == "4"]
        return [rings] if rings else []

    if family == "6":
        polygons: list[list[str]] = []
        for addr in linked:
            child_family = _row_family(addr)
            if child_family == "5":
                polygons.extend(
                    assemble_polygon_groups(
                        addr,
                        rows=rows,
                        linked_addresses_of=linked_addresses_of,
                    )
                )
            elif child_family == "4":
                polygons.append([addr])
        return polygons

    if family == "7":
        polygons = []
        for addr in linked:
            if _row_family(addr) not in {"4", "5", "6"}:
                continue
            polygons.extend(
                assemble_polygon_groups(
                    addr,
                    rows=rows,
                    linked_addresses_of=linked_addresses_of,
                )
            )
        return polygons

    return []


__all__ = ["assemble_polygon_groups"]
