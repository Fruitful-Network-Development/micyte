"""A document plus the pictures it names — what a receiver has to be handed.

TASK-2026-09-12-001 A4. Operator, 2026-09-12: *"a collection of plantar profile entries in
a datum doc can be full contained for use by a receiver"*.

A row names an artifact by its SLOT — a node on the tree, the same way a document is named
by its slot. That is an address in the writer's books, so a receiver holding only the
document holds a list of names it cannot follow. Containment is the closure: the document,
and every ``art.`` document its rows name, with the bytes in hand.

Pure, and asked in two halves so a caller can pay for only the half it needs:

* :func:`named_slots` answers "what would this cost me" without reading a single artifact —
  which is the question the publisher asks before deciding whether to embed or to publish
  the files beside the bin;
* :func:`contained` reads them, and reports what is MISSING rather than returning a bundle
  that is quietly short. A receiver handed an incomplete bundle finds out when it tries to
  draw a picture, which is the worst moment to find out.

The artifact slots are the TREE's, passed in: a cell holding ``1-1-4-1-27`` is a picture
only because that node is a child of the artifact branch, and the same digits under the
objects branch are a product. The reader that does not check would bundle a tomato.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .datum_resolve import as_text


@dataclass(frozen=True)
class ContainedBundle:
    """One document and the artifacts it names, with every absence stated."""

    document: object = None
    #: Every artifact slot the document's rows name, in first-mention order.
    slots: tuple[str, ...] = ()
    #: ``slot -> bytes``, for those the books hold.
    artifacts: dict[str, bytes] = field(default_factory=dict)
    #: Slots the document names and the books do not hold — the bundle is INCOMPLETE.
    missing: tuple[str, ...] = ()

    @property
    def whole(self) -> bool:
        """True when every slot named was carried. A receiver can draw everything."""
        return not self.missing

    @property
    def payload_bytes(self) -> int:
        return sum(len(blob) for blob in self.artifacts.values())

    def to_dict(self) -> dict[str, object]:
        return {"slots": list(self.slots), "carried": sorted(self.artifacts),
                "missing": list(self.missing), "whole": self.whole,
                "payload_bytes": self.payload_bytes}


def _cells(document: object) -> Iterable[str]:
    for row in getattr(document, "rows", ()) or ():
        raw = getattr(row, "raw", None)
        head = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else []
        for cell in head:
            yield as_text(cell)


def named_slots(document: object, *, artifacts: Iterable[str]) -> tuple[str, ...]:
    """Every artifact slot ``document``'s rows name, deduplicated, in first-mention order.

    Order is the document's own: a collection's first entry is its first picture, and a
    receiver writing the bundle out in this order writes it in the order the document
    reads. Deduplicated because two entries may honestly share one photograph, and
    carrying those bytes twice would make the bundle bigger than the books.
    """
    known = {as_text(slot) for slot in artifacts if as_text(slot)}
    seen: dict[str, None] = {}
    for cell in _cells(document):
        if cell in known:
            seen.setdefault(cell, None)
    return tuple(seen)


def contained(
    document: object, *, artifacts: Iterable[str],
    read: Callable[[str], bytes | None],
) -> ContainedBundle:
    """The document and the bytes of every artifact it names.

    ``read`` takes a slot and returns its bytes, or ``None`` when the books do not hold it.
    A slot that reads as ``None`` lands in ``missing`` — never dropped, and never faked with
    an empty blob, which would make an unreadable picture look like an empty one.
    """
    slots = named_slots(document, artifacts=artifacts)
    carried: dict[str, bytes] = {}
    missing: list[str] = []
    for slot in slots:
        blob = read(slot)
        if blob is None:
            missing.append(slot)
        else:
            carried[slot] = blob
    return ContainedBundle(document=document, slots=slots, artifacts=carried,
                           missing=tuple(missing))


__all__ = ["ContainedBundle", "contained", "named_slots"]
