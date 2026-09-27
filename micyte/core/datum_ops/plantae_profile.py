"""A plantae collection, read — entries carrying a taxon, a name and a photograph.

TASK-2026-09-12-001 A3. Operator, 2026-09-12:

> each entry of a planate profile can have an image, taken from the images previously held
> and attached by the micyte website. This way a collection of plantar profile entries in a
> datum doc can be full contained for use by a receiver.

One document is one collection. Each row is a :data:`ENTRY_ARCHETYPE`::

    plantae_entry  =  txa_id , title , lcl_id
                      ^which taxon
                               ^what it is called in this collection
                                        ^the artifact slot holding the photograph

**The photograph is a slot, not a path.** The slot names a node under the holding
sandbox's ``artifacts > image`` branch, whose ``art.`` document IS the bytes
(:mod:`micyte.core.datum_ops.artifact`). So a receiver handed the collection and the
artifacts it names can draw every picture with no site reachable — which is what "fully
contained" asks for, and what a URL could never give.

**Not `icon_ref`.** A taxon's ``icon_ref`` is an SVG leaflet stem standing for a clade,
inherited by descendants that have none. A photograph is of one plant and is not
inherited. The two are different facts and stay in different cells.

Pure: the caller passes the document, the registry it already holds, and optionally the
tree's labels; nothing here reads a store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import archetype_shape as ash
from .datum_resolve import as_text, decode_label, iter_marker_pairs

#: The archetype every row of a collection is, and the document that holds one.
ENTRY_ARCHETYPE = "plantae_entry"
COLLECTION_DOCUMENT = "plantae_profiles"


@dataclass(frozen=True)
class PlantaeEntry:
    """One entry: the taxon, the name it carries here, and its photograph's slot."""

    address: str
    taxon: str
    name: str
    slot: str = ""
    #: The slot's own label off the tree, when the caller supplied labels.
    photograph: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"address": self.address, "taxon": self.taxon, "name": self.name,
                "slot": self.slot, "photograph": self.photograph}


@dataclass(frozen=True)
class PlantaeCollection:
    """What one collection document says.

    ``extras`` carries rows of any OTHER archetype the registry covers and ``unmatched``
    the addresses of rows nothing covers — the same two channels a project document
    answers with, so a collection a receiver does not fully understand still arrives
    whole rather than silently trimmed.
    """

    name: str = ""
    entries: tuple[PlantaeEntry, ...] = ()
    extras: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)

    @property
    def slots(self) -> tuple[str, ...]:
        """Every artifact slot the collection names, in entry order, once each — what a
        containment bundle has to carry beside the document."""
        seen: list[str] = []
        for entry in self.entries:
            if entry.slot and entry.slot not in seen:
                seen.append(entry.slot)
        return tuple(seen)

    def by_taxon(self) -> dict[str, PlantaeEntry]:
        """``{taxon: entry}``. A taxon entered twice keeps the FIRST, and
        :meth:`duplicates` says so — a collection is not a map until somebody checks."""
        out: dict[str, PlantaeEntry] = {}
        for entry in self.entries:
            out.setdefault(entry.taxon, entry)
        return out

    def duplicates(self) -> dict[str, tuple[str, ...]]:
        """``{taxon: the addresses that entered it}`` where more than one did."""
        seen: dict[str, list[str]] = {}
        for entry in self.entries:
            seen.setdefault(entry.taxon, []).append(entry.address)
        return {taxon: tuple(rows) for taxon, rows in seen.items() if len(rows) > 1}

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "entries": [e.to_dict() for e in self.entries],
                "slots": list(self.slots), "extras": self.extras,
                "unmatched": list(self.unmatched),
                "duplicates": {k: list(v) for k, v in self.duplicates().items()}}


def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _cells(head: list[Any], *, namespace: str) -> list[tuple[str, str]]:
    return [(ash._field_name(as_text(marker), sandbox=namespace), as_text(magnitude))
            for marker, magnitude in iter_marker_pairs(head)]


def _first(cells: list[tuple[str, str]], name: str) -> str:
    return next((value for field_name, value in cells if field_name == name), "")


def read_collection(document: Any, *, registry: Any, namespace: str,
                    labels: dict[str, str] | None = None) -> PlantaeCollection:
    """Fold every row of ``document`` and answer the collection.

    ``labels`` is ``{node: label}`` off the holding tree, so an entry can report its
    photograph by the slot's own title where the caller has the tree, and by the slot's
    address where it does not — never as a guess.
    """
    entries: list[PlantaeEntry] = []
    extras: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[str] = []
    for row in getattr(document, "rows", ()) or ():
        address = as_text(getattr(row, "datum_address", ""))
        head = _head(row)
        if len(head) < 3:
            continue                                   # the structural blank
        matches = tuple(registry.match_row(ash.row_shape(row.raw, sandbox=namespace))) \
            if registry is not None else ()
        cells = _cells(head, namespace=namespace)
        if ENTRY_ARCHETYPE in matches:
            slot = _first(cells, "lcl_id")
            entries.append(PlantaeEntry(
                address=address, taxon=_first(cells, "txa_id"),
                name=decode_label(_first(cells, "title")), slot=slot,
                photograph=(labels or {}).get(slot, "")))
            continue
        if matches:
            folded: dict[str, list[str]] = {}
            for field_name, value in cells:
                folded.setdefault(field_name, []).append(value)
            extras.setdefault(matches[0], []).append({"address": address, "fields": folded})
        else:
            unmatched.append(address)
    return PlantaeCollection(
        name=as_text(getattr(document, "canonical_name", "")), entries=tuple(entries),
        extras=extras, unmatched=unmatched)


__all__ = [
    "COLLECTION_DOCUMENT",
    "ENTRY_ARCHETYPE",
    "PlantaeCollection",
    "PlantaeEntry",
    "read_collection",
]
