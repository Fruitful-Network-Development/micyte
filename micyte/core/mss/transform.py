"""The engine's manipulation primitives: the three moves the operator named, as SET
operations over a document's rows, refused whole by the invariants when a result would
break one.

Contract: ``docs/contracts/datum_editing_atomicity.md`` (insert / delete / shift as one
sequence) and ``docs/contracts/mss_engine_invariants.md`` (what a result may not be).
Operator, 2026-09-16:

a. **re-denote** a datum to a different value group so an additional (reference,
   magnitude) pair can be present — :func:`redenote`;
b. **sibling detection by material binary difference**: a sequentially ordered run of
   datums on one layer + value group, each referencing the same parent datum, are
   siblings of one archetype, so a set is transformed AS A SET — note the document's
   digest, COPY the range, DELETE it, CREATE the transformed rows after the last row of
   the target family with addresses shifted — :func:`sibling_set` + :func:`transform_set`;
c. the parent-only archetype constraint lives in ``core/archetypes`` (``Run.parent``).

Every verb is pure over ``(address, raw)`` rows and returns a :class:`Transform`: the
rows after, the ``remap`` of every address that moved (referrers inside the document are
rewritten by it, and a caller with referrers OUTSIDE the document — a sources manifest,
a ``hy.`` magnet — applies the same map), and a content digest before and after. Nothing
here re-keys a document: the store's identity path does that when the rows are written,
which is the rule [[feedback_rekeying_is_free_rewriting_is_not]] names.

Two repairs ride the same machinery and are the audit's other half:
:func:`reindex_heads` (I6 — the head names its own address) and :func:`compact` (I8 —
a layer-4 family contiguous from 1), and :func:`readdress` is ``row_address.readdressed``
expressed as a move rather than a mapping.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .invariants import (
    ROW_LAYER,
    InvariantRefused,
    arity_convention_holds,
    arity_of,
    check_rows,
    head_of,
    is_refs_only,
)

Row = tuple[str, Any]


class TransformRefused(ValueError):
    """The request itself is wrong — an address the document lacks, an empty set — as
    distinct from :class:`InvariantRefused`, which says the RESULT would break a rule."""


@dataclass(frozen=True)
class Transform:
    rows: tuple[Row, ...]
    remap: dict[str, str]
    digest_before: str
    digest_after: str
    note: str

    @property
    def moved(self) -> int:
        return len(self.remap)


@dataclass(frozen=True)
class SiblingSet:
    """A contiguous run of rows in one family sharing one marker sequence and one parent."""

    family: tuple[int, int]
    addresses: tuple[str, ...]
    markers: tuple[str, ...]
    parent: str

    def __len__(self) -> int:
        return len(self.addresses)

    @property
    def first(self) -> str:
        return self.addresses[0]

    @property
    def last(self) -> str:
        return self.addresses[-1]


# --------------------------------------------------------------------------- #
# Row plumbing
# --------------------------------------------------------------------------- #
def _parse(address: str) -> tuple[int, int, int] | None:
    parts = str(address or "").split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def _key(address: str) -> tuple[int, ...]:
    parsed = _parse(address)
    return parsed if parsed is not None else (1 << 30, 0, 0)


def _rows(rows: Iterable[Any]) -> list[list[Any]]:
    """Mutable ``[address, raw]`` pairs from row objects, dicts or pairs — deep-copied,
    so a transform never edits what it was given."""
    out: list[list[Any]] = []
    for item in rows:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            address, raw = item
        elif isinstance(item, dict):
            address, raw = item.get("datum_address"), item.get("raw")
        else:
            address, raw = getattr(item, "datum_address", ""), getattr(item, "raw", None)
        out.append([str(address or ""), copy.deepcopy(raw)])
    return out


def digest(rows: Iterable[Any]) -> str:
    """A content digest of the rows — NOT the document's identity (that is the store's
    ``version_hash``); enough to say whether a transform changed anything."""
    listed = sorted(((a, r) for a, r in _rows(rows)), key=lambda p: _key(p[0]))
    payload = json.dumps(listed, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _markers_of(head: Sequence[Any]) -> tuple[str, ...]:
    """The marker cells of a head — positions 1, 3, 5, …: the row's material."""
    return tuple(str(head[i]) for i in range(1, len(head) - 1, 2))


def _set_head_address(raw: Any, address: str) -> None:
    head = head_of(raw)
    if head is not None:
        raw[0][0] = address


def _apply_remap(rows: list[list[Any]], remap: dict[str, str]) -> None:
    """Rewrite every head cell (after the address) naming a moved row. One pass with the
    whole map, so a chain (``4-2-5 -> 4-2-4`` while ``4-2-4 -> 4-4-1``) cannot compound."""
    if not remap:
        return
    for _address, raw in rows:
        head = head_of(raw)
        if head is None:
            continue
        for i in range(1, len(head)):
            cell = head[i]
            if isinstance(cell, str) and cell in remap:
                raw[0][i] = remap[cell]


def _families(rows: list[list[Any]], *, layer: int) -> dict[tuple[int, int], list[list[Any]]]:
    out: dict[tuple[int, int], list[list[Any]]] = {}
    for row in rows:
        parsed = _parse(row[0])
        if parsed is not None and parsed[0] == layer:
            out.setdefault(parsed[:2], []).append(row)
    for members in out.values():
        members.sort(key=lambda r: _key(r[0]))
    return out


def _highest(rows: list[list[Any]], family: tuple[int, int]) -> int:
    top = 0
    for row in rows:
        parsed = _parse(row[0])
        if parsed is not None and parsed[:2] == family:
            top = max(top, parsed[2])
    return top


def _renumber(rows: list[list[Any]], family: tuple[int, int], remap: dict[str, str]) -> None:
    """Close the gaps in ``family``: its rows take 1..K in their current order."""
    members = _families(rows, layer=family[0]).get(family, [])
    for n, row in enumerate(members, start=1):
        new = f"{family[0]}-{family[1]}-{n}"
        if row[0] != new:
            remap[row[0]] = new
            row[0] = new
            _set_head_address(row[1], new)


def _finish(before: list[list[Any]], after: list[list[Any]], remap: dict[str, str], *,
            note: str, layer: int, arity: bool | None = None) -> Transform:
    _apply_remap(after, remap)
    after.sort(key=lambda r: _key(r[0]))
    holds = arity_convention_holds(before, layer=layer) is True if arity is None else arity
    # A transform may not make the document WORSE: a violation it introduces is refused
    # whole. A violation the document already carried is not — the repairs compose one
    # verb at a time (heads, then gaps, then families), and a verb that refused the
    # document for the defect the NEXT verb repairs would block every repair.
    # Compared by COUNT per invariant, not by identity: a repair renumbers rows, so a
    # finding the document already carried (a long title at 4-1-92) comes back at a new
    # address and would read as introduced under equality. More findings of a kind than
    # before is what "worse" means.
    from collections import Counter

    before_counts = Counter(r.invariant for r in check_rows(before, layer=layer, arity=holds))
    after_findings = check_rows(after, layer=layer, arity=holds)
    after_counts = Counter(r.invariant for r in after_findings)
    grew = {inv for inv, n in after_counts.items() if n > before_counts.get(inv, 0)}
    if grew:
        raise InvariantRefused(tuple(r for r in after_findings if r.invariant in grew))
    return Transform(
        rows=tuple((a, r) for a, r in after), remap=dict(remap),
        digest_before=digest(before), digest_after=digest(after), note=note)


# --------------------------------------------------------------------------- #
# The primitives
# --------------------------------------------------------------------------- #
def sibling_set(rows: Iterable[Any], *, layer: int, value_group: int, parent: str,
                start: str = "") -> SiblingSet:
    """The maximal contiguous run of rows in family ``(layer, value_group)`` that share
    one marker sequence containing ``parent`` — siblings by material binary difference:
    the same references, different magnitudes.

    ``start`` names the row the run must contain when a family holds several runs;
    otherwise the first run wins. Refuses a family or parent the document lacks.
    """
    listed = _rows(rows)
    members = _families(listed, layer=layer).get((layer, value_group), [])
    if not members:
        raise TransformRefused(f"the document holds no rows in family {layer}-{value_group}")
    runs: list[list[list[Any]]] = []
    for row in members:
        head = head_of(row[1])
        if head is None or is_refs_only(head):
            runs.append([])
            continue
        markers = _markers_of(head)
        if parent not in markers:
            runs.append([])
            continue
        if runs and runs[-1] and _markers_of(head_of(runs[-1][-1][1]) or []) == markers \
                and _parse(runs[-1][-1][0])[2] + 1 == _parse(row[0])[2]:
            runs[-1].append(row)
        else:
            runs.append([row])
    runs = [run for run in runs if run]
    if not runs:
        raise TransformRefused(
            f"no row in family {layer}-{value_group} references {parent!r}")
    chosen = runs[0]
    if start:
        chosen = next((run for run in runs if any(r[0] == start for r in run)), None)
        if chosen is None:
            raise TransformRefused(f"{start} is not in a run that references {parent!r}")
    return SiblingSet(
        family=(layer, value_group), addresses=tuple(r[0] for r in chosen),
        markers=_markers_of(head_of(chosen[0][1]) or []), parent=parent)


def transform_set(rows: Iterable[Any], siblings: SiblingSet, *,
                  add: Sequence[tuple[str, Any]] = (),
                  transform: Callable[[list[Any]], list[Any]] | None = None,
                  value_group: int | None = None, layer: int = ROW_LAYER) -> Transform:
    """Transform a sibling set AS A SET: copy the range, delete it (its family closes
    the gap), create the transformed rows after the last row of the target family with
    their addresses shifted, and rewrite every referrer.

    ``add`` appends ``(marker, magnitude)`` pairs to every head; ``transform`` rewrites a
    head outright (given a copy, returns the new head; the address cell is overwritten
    after). The target family is ``value_group`` when given, else the family the
    transformed head's ARITY names — which is what makes "add a fiat value to all 60"
    land the 60 in ``4-4`` when they were ``4-3``. Refused whole when the result would
    break an invariant.
    """
    before = _rows(rows)
    after = _rows(rows)
    wanted = set(siblings.addresses)
    if not wanted:
        raise TransformRefused("an empty set transforms nothing")
    present = {row[0] for row in after}
    missing = sorted(wanted - present, key=_key)
    if missing:
        raise TransformRefused(f"the document no longer holds {missing[:3]}")
    remap: dict[str, str] = {}
    copied = [row for row in after if row[0] in wanted]
    after = [row for row in after if row[0] not in wanted]
    _renumber(after, siblings.family, remap)
    created: list[list[Any]] = []
    for old_address, raw in copied:
        head = list(head_of(raw) or [old_address])
        head = list(transform(list(head))) if transform is not None else head
        for marker, magnitude in add:
            head += [str(marker), magnitude]
        family = (layer, value_group if value_group is not None else max(1, arity_of(head)))
        new_address = f"{family[0]}-{family[1]}-{_highest(after, family) + _highest(created, family) + 1}"
        head[0] = new_address
        new_raw = [head, *list(raw[1:])] if isinstance(raw, list) else [head]
        created.append([new_address, new_raw])
        remap[old_address] = new_address
    after.extend(created)
    return _finish(before, after, remap, layer=layer,
                   note=f"{len(copied)} rows of {siblings.family[0]}-{siblings.family[1]} "
                        f"transformed and re-created after the last row of their new family")


def redenote(rows: Iterable[Any], address: str, *, value_group: int,
             add: Sequence[tuple[str, Any]] = (), layer: int = ROW_LAYER) -> Transform:
    """Move ONE row to family ``<layer>-<value_group>``, adding ``add`` pairs on the way
    so the row's arity names the family it lands in (I7). The family it leaves closes
    the gap; every referrer follows."""
    listed = _rows(rows)
    row = next((r for r in listed if r[0] == address), None)
    if row is None:
        raise TransformRefused(f"the document holds no row at {address}")
    parsed = _parse(address)
    if parsed is None or parsed[0] != layer:
        raise TransformRefused(f"{address} is not a layer-{layer} row")
    head = head_of(row[1]) or [address]
    siblings = SiblingSet(family=parsed[:2], addresses=(address,), markers=_markers_of(head),
                          parent=str(head[1]) if len(head) > 1 else "")
    out = transform_set(listed, siblings, add=add, value_group=value_group, layer=layer)
    return Transform(rows=out.rows, remap=out.remap, digest_before=out.digest_before,
                     digest_after=out.digest_after,
                     note=f"{address} re-denoted to {out.remap.get(address, address)}")


def reindex_heads(rows: Iterable[Any], *, artifact: bool = False) -> Transform:
    """I6 repair: every head names its own address. The KEY is the truth — it is what
    the store indexes and what referrers use; a head that disagrees was left behind by
    a re-address that moved the key alone. No referrer changes."""
    if artifact:
        raise TransformRefused("an artifact's rows keep the chain reference first; there is no head to reindex")
    before = _rows(rows)
    after = _rows(rows)
    fixed = 0
    for address, raw in after:
        head = head_of(raw)
        if head is not None and head and str(head[0]) != address:
            raw[0][0] = address
            fixed += 1
    return _finish(before, after, {}, layer=ROW_LAYER, arity=False,
                   note=f"{fixed} heads re-pointed at their own address")


def compact(rows: Iterable[Any], *, layer: int = ROW_LAYER,
            families: Iterable[tuple[int, int]] | None = None) -> Transform:
    """I8 repair: each layer-``layer`` family (or the ``families`` named) contiguous
    from 1, rows keeping their order; referrers follow the renumbering."""
    before = _rows(rows)
    after = _rows(rows)
    remap: dict[str, str] = {}
    targets = list(families) if families is not None else sorted(_families(after, layer=layer))
    for family in targets:
        _renumber(after, family, remap)
    return _finish(before, after, remap, layer=layer, arity=False,
                   note=f"{len(remap)} rows renumbered across {len(targets)} families")


def readdress(rows: Iterable[Any], *, layer: int = ROW_LAYER) -> Transform:
    """I7 repair, as a move: every pair-bearing layer-``layer`` row whose family is not
    its arity goes to the family its arity names, after that family's highest; the
    families it left close their gaps; referrers follow. ``row_address.readdressed``
    computes the same mapping; this performs it."""
    before = _rows(rows)
    after = _rows(rows)
    remap: dict[str, str] = {}
    movers: list[list[Any]] = []
    for row in list(after):
        parsed = _parse(row[0])
        head = head_of(row[1])
        if parsed is None or parsed[0] != layer or head is None or is_refs_only(head):
            continue
        family = (layer, max(1, arity_of(head)))
        if parsed[:2] != family:
            movers.append(row)
    if not movers:
        return _finish(before, after, remap, layer=layer, arity=False, note="every row is in its family")
    left = {tuple(_parse(r[0])[:2]) for r in movers}
    after = [row for row in after if row not in movers]
    for family in sorted(left):
        _renumber(after, family, remap)
    placed: list[list[Any]] = []
    for row in movers:
        head = head_of(row[1])
        family = (layer, max(1, arity_of(head)))
        # One past the family's highest — whether that highest is a row that was already
        # there or one placed a moment ago. Adding the two gave a second mover into a
        # non-empty family the address TWO past the first (2, 4, 6, 8), a gap the
        # transform then refused as its own I8; four live documents were refused so.
        new_address = f"{family[0]}-{family[1]}-{max(_highest(after, family), _highest(placed, family)) + 1}"
        remap[row[0]] = new_address
        row[0] = new_address
        _set_head_address(row[1], new_address)
        placed.append(row)
    after.extend(placed)
    return _finish(before, after, remap, layer=layer, arity=True,
                   note=f"{len(movers)} rows moved to the family their arity names")


__all__ = [
    "Row",
    "SiblingSet",
    "Transform",
    "TransformRefused",
    "compact",
    "digest",
    "readdress",
    "redenote",
    "reindex_heads",
    "sibling_set",
    "transform_set",
]
