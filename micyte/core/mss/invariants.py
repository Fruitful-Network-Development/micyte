"""The invariants the MSS engine holds a document to, and the one checker that refuses.

Contract: ``docs/contracts/mss_engine_invariants.md`` — read it for what each rule means and
where it is enforced. This module is the code half: every rule is a named
:class:`Invariant`, every violation is a :class:`Refusal` carrying the rule, the address and a
sentence an operator can act on, and a check returns EVERY refusal rather than the first — a
writer that is told one thing, fixes it, and is then told the next is a writer being taught
the rules one refusal at a time.

Two levels, two checkers:

* :func:`check_datums` — the WIRE level, over codec datums (anything with ``address``,
  ``layer``, ``refs``, ``tuples`` and ``dependency_addresses()``). These are the five
  refusals ``document_codec._validate_canonical`` has always made; it now calls this.
* :func:`check_rows` / :func:`check_new_rows` — the DOCUMENT level, over stored rows
  ``(datum_address, raw)``. The wire is deliberately lossless about these (it carries a
  row's arity explicitly, so it can encode a row whose address lies about it), which is
  why the ENGINE refuses them at the store's write door instead. Operator decision D1,
  2026-09-17: a value group on an instance row IS its arity.

Pure. No store, no registry, no import of the codec (the codec imports this). The one
rule that needs the outside world — I9, archetype coverage — is a callback the door
supplies, because the archetype library is a fact about a sandbox and this module has no
business reading one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

#: The layer an instance row lives at (``row_address.ROW_LAYER`` says the same thing).
ROW_LAYER = 4

#: The family the structural blank ``[["4-1-1"]]`` keeps: a head with NO pairs.
BLANK_FAMILY = (ROW_LAYER, 1)

#: ``labels.TITLE_BITS`` / 8 — the title babelette is 64 eight-bit ASCII characters.
TITLE_CHARS = 64

#: The marker that opens a refs-only head.
STRUCTURAL_MARKER = "~"

WIRE = "wire"
DOCUMENT = "document"


@dataclass(frozen=True)
class Invariant:
    id: str
    level: str
    rule: str


I1 = Invariant("I1", WIRE, "every datum address is unique")
I2 = Invariant("I2", WIRE, "layers are contiguous from 0 (reindex first)")
I3 = Invariant("I3", WIRE, "a datum is refs-only or tuple-bearing, never both")
I4 = Invariant("I4", WIRE, "every reference names a datum in the set")
I5 = Invariant("I5", WIRE, "references point downward, to a strictly lower layer")
I6 = Invariant("I6", DOCUMENT, "a row's head names its own address")
I7 = Invariant("I7", DOCUMENT,
               "an instance row carrying n pairs lives in family 4-n; a head with no pairs "
               "is the structural blank and lives in 4-1")
I8 = Invariant("I8", DOCUMENT,
               "iterations are contiguous from 1 within a family; an appended row lands one "
               "past the family's highest")
I9 = Invariant("I9", DOCUMENT, "a row filed under an archetype is covered by that archetype")
I10 = Invariant("I10", DOCUMENT, "a title is at most 64 ASCII characters")

INVARIANTS: tuple[Invariant, ...] = (I1, I2, I3, I4, I5, I6, I7, I8, I9, I10)
WIRE_INVARIANTS = tuple(i for i in INVARIANTS if i.level == WIRE)
DOCUMENT_INVARIANTS = tuple(i for i in INVARIANTS if i.level == DOCUMENT)


@dataclass(frozen=True)
class Refusal:
    invariant: str
    address: str
    sentence: str

    def __str__(self) -> str:
        return f"{self.invariant} at {self.address}: {self.sentence}"


def sentence(refusals: Iterable[Refusal]) -> str:
    """One line carrying every refusal, in the order they were found."""
    return "; ".join(str(r) for r in refusals)


class InvariantRefused(ValueError):
    """Raised by a write door: the rows would violate the engine's invariants.

    Carries the refusals themselves so a surface can draw them one per line instead of
    parsing the sentence back apart.
    """

    def __init__(self, refusals: Iterable[Refusal]) -> None:
        self.refusals = tuple(refusals)
        super().__init__(sentence(self.refusals))


# --------------------------------------------------------------------------- #
# Wire level
# --------------------------------------------------------------------------- #
def check_datums(datums: Sequence[Any]) -> tuple[Refusal, ...]:
    """I1–I5 over a datum set the codec is about to encode. Every refusal, not the first."""
    out: list[Refusal] = []
    addresses = [d.address for d in datums]
    if len(set(addresses)) != len(addresses):
        seen: set[str] = set()
        for a in addresses:
            if a in seen:
                out.append(Refusal(I1.id, a, "duplicate datum address"))
            seen.add(a)
    by_addr = {d.address: d for d in datums}
    layers = sorted({d.layer for d in datums})
    if layers and layers != list(range(len(layers))):
        out.append(Refusal(I2.id, "-", "layers must be contiguous from 0 (reindex first)"))
    for d in datums:
        if d.refs and d.tuples:
            out.append(Refusal(
                I3.id, d.address, f"datum {d.address} cannot be both refs-only and tuple-bearing"))
        for ref in d.dependency_addresses():
            if ref not in by_addr:
                out.append(Refusal(I4.id, d.address, f"datum {d.address} references missing {ref}"))
            elif by_addr[ref].layer >= d.layer:
                out.append(Refusal(
                    I5.id, d.address,
                    f"datum {d.address} references {ref} which is not in a lower layer "
                    "(refs must point downward)"))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Document level
# --------------------------------------------------------------------------- #
def _parse(address: object) -> tuple[int, int, int] | None:
    parts = str(address or "").split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def _row(item: Any) -> tuple[str, Any]:
    """``(datum_address, raw)`` from a row object, a dict, a pair — or a bare raw row.

    A raw row ``[[address, marker, magnitude, …], [title]]`` is ALSO a two-element list,
    and until 2026-09-29 it was read as an ``(address, raw)`` pair: the head became the
    "address", the title list the "raw", and every such row was silently skipped as
    unparseable. ``arity_convention_holds`` then answered ``None`` ("has not said") for a
    document that plainly kept the convention. A pair's first element is a string; a raw
    row's is the head list — that is the whole distinction.
    """
    if isinstance(item, (tuple, list)) and len(item) == 2:
        if isinstance(item[0], list):
            head = item[0]
            return (str(head[0]) if head else ""), item
        return str(item[0] or ""), item[1]
    if isinstance(item, dict):
        return str(item.get("datum_address") or ""), item.get("raw")
    return str(getattr(item, "datum_address", "") or ""), getattr(item, "raw", None)


def head_of(raw: Any) -> list[Any] | None:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return None


def title_of(raw: Any) -> str | None:
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        first = raw[1][0]
        return first if isinstance(first, str) else None
    return None


def arity_of(head: Sequence[Any]) -> int:
    """The (marker, magnitude) pairs after the address — ``row_address.value_group_of``."""
    return max(0, len(head) - 1) // 2


def is_refs_only(head: Sequence[Any]) -> bool:
    return len(head) > 1 and head[1] == STRUCTURAL_MARKER


def arity_convention_holds(rows: Iterable[Any], *, layer: int = ROW_LAYER) -> bool | None:
    """Does this document keep I7 — is every pair-bearing row at ``layer`` in family
    ``<layer>-<arity>``? ``None`` when the document holds no such row yet, so the caller
    can tell "keeps it" from "has not said".

    Measured 2026-09-17: 10,517 of the live store's layer-4 rows use the value group
    POSITIONALLY (a channel profile's one-pair rows at ``4-2``, ``msn_registry`` at
    ``4-9``, txa's four-pair rows at ``4-2``, analytics' five-pair rows at ``4-1``, every
    archetype's own blank instance at ``4-1-1``). Those documents are not wrong by their
    own lights; they predate the rule. So the door holds a document to I7 when the
    document itself keeps it, and the audit maps the rest for `transform.py` to convert
    one document at a time, as an operator's decision each.
    """
    seen = False
    for address, raw in (_row(r) for r in rows):
        head = head_of(raw)
        parsed = _parse(address)
        if head is None or parsed is None or parsed[0] != layer or is_refs_only(head):
            continue
        n = arity_of(head)
        if n == 0:
            continue
        seen = True
        if parsed[1] != n:
            return False
    return True if seen else None


def _check_one(address: str, raw: Any, *, layer: int, covers: Callable[[Any], bool] | None,
               archetype: str, title_chars: int, artifact: bool, arity: bool) -> list[Refusal]:
    out: list[Refusal] = []
    head = head_of(raw)
    parsed = _parse(address)
    # I6 is a rule of the DATUM row grammar ``[[address, marker, magnitude, …], [title]]``.
    # An artifact's rows (``art.`` documents) are bytes: ``[[chain, kind, magnitude,
    # width], []]``, the chain reference first — ``datum_ops/artifact.py`` is their codec
    # and ``test_artifact_codec`` their round trip.
    if not artifact and head is not None and head and str(head[0]) != address:
        out.append(Refusal(I6.id, address, f"row {address} has a head that names {head[0]}"))
    if arity and head is not None and parsed is not None and parsed[0] == layer and not is_refs_only(head):
        n = arity_of(head)
        family = max(1, n)
        if parsed[1] != family:
            what = f"carries {n} pairs" if n else "is a blank (no pairs)"
            out.append(Refusal(
                I7.id, address,
                f"row {address} {what}, so its family is {layer}-{family}, not {layer}-{parsed[1]}"))
    # I9 asks what KIND a row is, and a structural row — the blank, a `~` collection —
    # is scaffolding every document carries; it can never say what kind one is
    # (`ArchetypeRegistry.primary_archetype_of` skips them for the same reason).
    structural = head is None or arity_of(head) == 0 or is_refs_only(head)
    if covers is not None and not structural and not covers(raw):
        out.append(Refusal(
            I9.id, address,
            f"row {address} folds to a shape {archetype or 'the archetype'} does not cover"))
    title = title_of(raw)
    if title is not None and len(title) > title_chars:
        out.append(Refusal(
            I10.id, address,
            f"row {address} has a title of {len(title)} characters; the title babelette "
            f"holds {title_chars}"))
    return out


def check_rows(rows: Iterable[Any], *, layer: int = ROW_LAYER,
               covers: Callable[[Any], bool] | None = None, archetype: str = "",
               title_chars: int = TITLE_CHARS, artifact: bool = False,
               arity: bool = True) -> tuple[Refusal, ...]:
    """I6–I10 over a WHOLE document's rows — the audit's checker.

    ``covers`` is the I9 callback (``raw -> bool``); ``None`` skips I9, for a document
    nobody filed under an archetype. ``artifact`` names an ``art.`` document (no I6).
    ``arity=False`` skips I7 — the audit passes True and counts; a door passes what
    :func:`arity_convention_holds` said about the document.

    I8 is judged at ``layer`` only: below it an address is a NAME (a babelette at
    ``3-1-21`` is the price field wherever the anchor put it), and a gap there is the
    field registry's business, not a hole in a log.
    """
    listed = [_row(r) for r in rows]
    out: list[Refusal] = []
    families: dict[tuple[int, int], list[int]] = {}
    for address, raw in listed:
        out.extend(_check_one(address, raw, layer=layer, covers=covers, archetype=archetype,
                              title_chars=title_chars, artifact=artifact, arity=arity))
        parsed = _parse(address)
        if parsed is not None and parsed[0] == layer:
            families.setdefault(parsed[:2], []).append(parsed[2])
    for (lay, vg), iterations in sorted(families.items()):
        ordered = sorted(iterations)
        if ordered != list(range(1, len(ordered) + 1)):
            expected = next((k for k, it in enumerate(ordered, start=1) if it != k), len(ordered) + 1)
            out.append(Refusal(
                I8.id, f"{lay}-{vg}-{expected}",
                f"family {lay}-{vg} is not contiguous from 1: it holds {ordered[:6]}"
                f"{'…' if len(ordered) > 6 else ''}"))
    return tuple(out)


def check_new_rows(existing: Iterable[Any], new: Iterable[Any], *, layer: int = ROW_LAYER,
                   covers: Callable[[Any], bool] | None = None, archetype: str = "",
                   title_chars: int = TITLE_CHARS, artifact: bool = False) -> tuple[Refusal, ...]:
    """I6, I9, I10 over the rows being APPENDED; I7 when the document keeps the arity
    convention (:func:`arity_convention_holds`); I8 as "lands one past the highest".

    The rows already in the document are not judged: a gap or a lying head an earlier writer
    left is the audit's finding and the transform's repair, not a reason to refuse the next
    honest append. A door that judged the whole document would block the repair.
    """
    existing_rows = [_row(r) for r in existing]
    arity = arity_convention_holds(existing_rows, layer=layer) is True
    highest: dict[tuple[int, int], int] = {}
    for address, _raw in existing_rows:
        parsed = _parse(address)
        if parsed is not None and parsed[0] == layer:
            highest[parsed[:2]] = max(highest.get(parsed[:2], 0), parsed[2])
    out: list[Refusal] = []
    incoming: dict[tuple[int, int], list[int]] = {}
    for address, raw in (_row(r) for r in new):
        out.extend(_check_one(address, raw, layer=layer, covers=covers, archetype=archetype,
                              title_chars=title_chars, artifact=artifact, arity=arity))
        parsed = _parse(address)
        if parsed is not None and parsed[0] == layer:
            incoming.setdefault(parsed[:2], []).append(parsed[2])
    for (lay, vg), iterations in sorted(incoming.items()):
        top = highest.get((lay, vg), 0)
        ordered = sorted(iterations)
        if ordered != list(range(top + 1, top + 1 + len(ordered))):
            out.append(Refusal(
                I8.id, f"{lay}-{vg}-{ordered[0]}",
                f"row {lay}-{vg}-{ordered[0]} would leave a gap: family {lay}-{vg} reaches "
                f"{top}, so the next row is {lay}-{vg}-{top + 1}"))
    return tuple(out)


#: A sentinel for "no prior row at this address" — ``None`` is a possible raw value.
_MISSING = object()


def _canon(raw: Any) -> Any:
    """A row's value, shape-normalised: the prior comes back from the store as JSON lists,
    the replacement may carry the writer's tuples. Same cells, one comparison."""
    if isinstance(raw, (list, tuple)):
        return [_canon(item) for item in raw]
    return raw


def _gaps(iterations: Iterable[int]) -> frozenset[int]:
    """The holes in a family: every iteration below its highest that nothing holds."""
    held = set(iterations)
    if not held:
        return frozenset()
    return frozenset(set(range(1, max(held) + 1)) - held)


def check_replaced_rows(existing: Iterable[Any], replacement: Iterable[Any], *,
                        layer: int = ROW_LAYER,
                        covers: Callable[[Any], bool] | None = None, archetype: str = "",
                        title_chars: int = TITLE_CHARS, artifact: bool = False) -> tuple[Refusal, ...]:
    """The REPLACE door's judgment: a document handed back whole, against the one it replaces.

    Every writer that edits a document in place — the ag-profile, sources, notes and
    object-profile runtimes, the repair scripts — replaces the whole document, and until
    2026-09-29 that door judged nothing: a writer could place a four-pair row at ``4-1-1``
    in a document that keeps its rows at ``4-4`` and be told nothing (the rehearsal that
    found it is in `evidence/isolated-development-readiness-2026-09-27`). So the door
    judges what CHANGED, by the same rules the append door holds new rows to:

    * I6, I9, I10 on every row that is new or whose bytes changed;
    * I7 on those rows when the document being replaced keeps the arity convention
      (:func:`arity_convention_holds` on ``existing``) — a positional document is left to
      its own, as the append door leaves it;
    * I8 per family the replacement touched: the family may not GAIN a hole. A compaction
      closes holes and a readdress fills a family from 1 — both pass; a writer that skips
      an iteration opens one — refused, naming the first new hole. A hole an earlier writer
      left is the audit's finding, not this writer's fault, so it is not judged here.

    Rows the replacement drops are not judged: a delete cannot violate a row rule, and
    the hole it may leave is the one case the I8 rule above deliberately admits, because
    the alternative is a door that refuses every delete but the last row's.
    """
    before = {address: _canon(raw) for address, raw in (_row(r) for r in existing)}
    after = [(address, raw) for address, raw in (_row(r) for r in replacement)]
    arity = arity_convention_holds(before.items(), layer=layer) is True
    out: list[Refusal] = []
    touched: set[tuple[int, int]] = set()
    for address, raw in after:
        parsed = _parse(address)
        prior = before.get(address, _MISSING)
        if prior is _MISSING or prior != _canon(raw):
            out.extend(_check_one(address, raw, layer=layer, covers=covers, archetype=archetype,
                                  title_chars=title_chars, artifact=artifact, arity=arity))
            if prior is _MISSING and parsed is not None and parsed[0] == layer:
                touched.add(parsed[:2])
    kept = {address for address, _raw in after}
    for address in before:
        parsed = _parse(address)
        if address not in kept and parsed is not None and parsed[0] == layer:
            touched.add(parsed[:2])
    for family in sorted(touched):
        held_before = {p[2] for p in (_parse(a) for a in before) if p is not None and p[:2] == family}
        was = _gaps(held_before)
        now = _gaps(p[2] for p in (_parse(a) for a, _r in after) if p is not None and p[:2] == family)
        # A hole where a row USED to be is a delete's hole, admitted; a hole where nothing
        # ever was is a writer skipping ahead, refused.
        opened = sorted((now - was) - held_before)
        if opened:
            lay, vg = family
            out.append(Refusal(
                I8.id, f"{lay}-{vg}-{opened[0]}",
                f"the replacement leaves family {lay}-{vg} with a new gap at {lay}-{vg}-{opened[0]}"
                f"{' (and ' + str(len(opened) - 1) + ' more)' if len(opened) > 1 else ''}: "
                f"a row lands one past the family's highest, and a compaction closes holes "
                f"rather than opening them"))
    return tuple(out)


__all__ = [
    "BLANK_FAMILY",
    "DOCUMENT",
    "DOCUMENT_INVARIANTS",
    "I1",
    "I2",
    "I3",
    "I4",
    "I5",
    "I6",
    "I7",
    "I8",
    "I9",
    "I10",
    "INVARIANTS",
    "ROW_LAYER",
    "TITLE_CHARS",
    "WIRE",
    "WIRE_INVARIANTS",
    "Invariant",
    "InvariantRefused",
    "Refusal",
    "arity_of",
    "check_datums",
    "check_new_rows",
    "check_replaced_rows",
    "check_rows",
    "head_of",
    "is_refs_only",
    "sentence",
    "title_of",
]
