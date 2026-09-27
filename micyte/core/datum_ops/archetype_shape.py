"""The ARCHETYPE shape of a datum document — what KIND of thing it is, not which one.

A row's ``hyphae_hash`` is a *content identity*. It folds the document's anchor context and
the leaf magnitudes, so two documents of the same kind never share one: measured on the live
store, **101,485 distinct values over 105,811 rows**, and the highest recurrence of any single
value across documents is **5**. It cannot answer "what kind of document is this?" and was
never meant to — ``docs/wiki/60-canonical-datum-and-hyphae-flags.md`` binds *by content* on
purpose, so that a flag follows one datum wherever it is copied.

Archetype recognition needs the opposite fold: deliberately **lossy**, keeping only what two
documents of a kind have in common. This module is that fold.

    row shape  = (layer, run-collapsed tuple of LOGICAL field names)
    signature  = sha256 over the SET of row shapes the document contains

Four things are discarded, each for a stated reason:

* **Magnitudes.** They are the data. A contact record with a different name is the same kind
  of contact record.
* **Iteration, and the row's value group.** Both are positional — an insert or a move shifts
  every sibling (``preview_document_insert`` / ``preview_document_move``). A shape that moved
  when a row was inserted above it would not be a shape.
* **Run length.** Arity is not kind: a ring of 9 vertices and a ring of 29 are both polygons.
  Measured, folding the count in mints one archetype per polygon — **277 signatures across 510
  documents instead of 45**.
* **The anchor's physical numbering.** Markers resolve to logical fields through
  :mod:`.field_registry`, never read literally.

The last two rules do different jobs, and it is worth knowing which does what — measured one
at a time in ``evidence/archetype-viewscope/phase0/fold_variants.py``. **Run-collapsing** is
what makes the corpus tractable: 277 document signatures without it, 45 with. **The decoder
ring** changes nothing at document scope (45 either way, since a document has one namespace)
and everything at row scope: 565 polygon-ring rows carry ``rf.3-1-1`` in the registrar and
``rf.3-1-3`` in the farms, so a raw-marker fold splits them 556 + 9 and calls a county
boundary and a farm boundary different kinds of thing. Under the logical fold both are
``coordinate+`` — one archetype, which is the only reason ``geospatial_polygon`` can exist.
It also re-partitions rather than merely coarsening (83 row shapes against the raw fold's
84): rows sharing a marker but not a meaning — a registrar ``title`` and a farm
``coordinate``, both ``rf.3-1-3`` — correctly come apart.

A marker the namespace cannot name folds to ``<rf.3-1-N>`` rather than being dropped, so a gap
in the decoder ring is visible in the shape instead of silently merging two archetypes that
differ exactly where the registry stops knowing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from micyte.core.document_naming import parse_canonical_document_id

from . import field_registry as _fr

#: Fold policy version. A change to the rules above MUST bump this: signatures computed
#: under two policies are not comparable, and a stale archetype binding has to be
#: *detectably* stale rather than quietly wrong (``docs/wiki/60``, open question 3).
ARCHETYPE_SHAPE_POLICY = "mos.archetype_shape_v1"

#: The structural downward/definition edge. Namespace-independent — it is not a field
#: reference, so it is never resolved through the registry and never marked unresolved.
STRUCTURAL_MARKER = "~"

#: How a marker the namespace cannot name is spelled in a shape.
UNRESOLVED_FORMAT = "<{token}>"

#: Suffix marking a collapsed run of two or more identical consecutive fields.
RUN_SUFFIX = "+"

#: A marker-position slot holding something that is not a marker at all. The head does not
#: parse as ``[address, marker, magnitude, ...]`` from here on, so every slot after it is
#: read one position out. Measured live: 3 rows (``<a_farm>/farm_profile`` 7-4-1 / 7-5-1 /
#: 7-6-1, which carry a stray ``"1"`` after their ``lcl_id`` cell).
#:
#: These are marked rather than parsed around. ``refs._head_edges`` walks the same pairs and
#: simply skips a slot that is not a marker, which is right for *finding* edges and wrong
#: here: a shape is a claim about a whole row, and quietly re-reading a misaligned head
#: yields a confident description of a row nobody wrote. An archetype minted from one would
#: match nothing, or worse, match something else.
MISALIGNED_FIELD = "!misaligned"


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


@dataclass(frozen=True, order=True)
class RowShape:
    """One row's kind: its layer and the logical fields its head references, in order."""

    layer: str
    fields: tuple[str, ...]
    #: The backing radix of each field, parallel to ``fields`` — ``2-1-1`` for an ASCII
    #: babelette, ``2-0-5`` for an lcl address — read off the sandbox's anchor by
    #: ``viewscope_edit.backing_radices`` and supplied by the caller that has the anchor
    #: (2026-09-17, TASK-2026-09-16-002 P2c). Empty when nobody supplied it, which is
    #: every caller before this date, so an archetype that binds a field NAME reads the
    #: shape exactly as it did; only a run that binds a PARENT (``Run.parent``) looks here.
    #: Not part of ``__str__``: the radix is a fact about the anchor, not the row's kind.
    radices: tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"L{self.layer}:{','.join(self.fields)}"

    def radix_at(self, index: int) -> str:
        return self.radices[index] if index < len(self.radices) else ""


def sandbox_of(document: Any) -> str:
    """The sandbox token a document belongs to, from its canonical id.

    The sandbox picks the namespace, so it is what the whole fold is relative to. A
    document whose id is not canonical has no sandbox to resolve against and yields ``""``
    — which :func:`row_shape` turns into an all-unresolved shape rather than a guess. A
    guessed namespace is the one failure this module cannot detect afterwards: every marker
    would resolve, to the wrong field.
    """
    for source in (getattr(document, "document_id", ""), document):
        token = _text(source)
        if not token:
            continue
        try:
            return _text(parse_canonical_document_id(token).sandbox)
        except Exception:
            continue
    return ""


def _row_head(raw: Any) -> list[Any]:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _classify(token: str) -> tuple[str, str]:
    """``(kind, payload)`` for a token sitting in a marker position.

    Three kinds are markers and one is not:

    * ``structural`` — ``~``, the downward/definition edge. Namespace-independent.
    * ``field`` — a **babelette** address (layer 3, group 1), the thing the decoder ring
      names. The ``rf.`` prefix is conventional, not load-bearing: ``fnd_ebi/registrar``
      writes 76 rows of bare ``3-1-2`` / ``3-1-5``, and ``rf.3-1-2`` and ``3-1-2`` mean the
      same field. Keying on the prefix would have split that sandbox off on spelling.
    * ``position`` — any other datum address (``6-0-1``, ``5-0-3``, ``2-1-10``). It
      references a POSITION, not a field, so the ring has nothing to look it up in. The
      iteration is dropped for the same reason the row's own is: it is positional.
    * ``misaligned`` — anything else. See :data:`MISALIGNED_FIELD`.
    """
    if token == STRUCTURAL_MARKER:
        return "structural", token
    lowered = token.lower()
    body = token.split(".", 1)[1] if lowered.startswith(("rf.", "ref.")) else token
    parts = body.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        if (parts[0], parts[1]) == ("3", "1"):
            return "field", body
        return "position", f"{parts[0]}-{parts[1]}"
    return "misaligned", token


#: Bounded memo for :func:`_field_name`. The fold asks the same few questions an enormous
#: number of times: indexing `registrar/address_nodes` calls it **188,920 times for 4
#: distinct answers**, since every one of 41,999 rows carries the same two markers. The
#: function is pure — :mod:`.field_registry`'s tables are module constants — so this is a
#: memo, not a cache with an invalidation story. Bounded for the reason every memo in this
#: program is bounded: an unbounded one cost +293 MiB per test on 2026-08-05. The whole
#: marker vocabulary across every namespace is a few hundred entries, so 4096 never evicts
#: in practice and still cannot grow without limit if a corpus arrives full of junk tokens.
_FIELD_NAME_MEMO_MAX = 4096


def _body(token: str) -> str:
    """A marker token without its conventional ``rf.`` / ``ref.`` prefix."""
    lowered = token.lower()
    return token.split(".", 1)[1] if lowered.startswith(("rf.", "ref.")) else token


@lru_cache(maxsize=_FIELD_NAME_MEMO_MAX)
def _field_name(token: str, *, sandbox: str) -> str:
    """The logical field a head marker names, or a visibly non-field token."""
    kind, payload = _classify(token)
    if kind == "structural":
        return STRUCTURAL_MARKER
    if kind == "misaligned":
        return MISALIGNED_FIELD
    if not sandbox:
        return UNRESOLVED_FORMAT.format(token=payload)
    if kind == "position":
        # A babelette's LAYER is its chain's DEPTH, and `_classify` above encodes the
        # corpus as it was: every chain three deep, so every field marker at ``3-1-N``.
        # The glyph anchor's grid point is `((((siu;512:);512:);1:);0)` — four deep — and
        # its babelette can only be at ``4-1-1``. Folded as a position it reads ``<4-1>``,
        # which merges "a point on the canvas" with "a reference to layer 4" and makes the
        # arc archetype unrecognisable.
        #
        # So a token the NAMESPACE DECLARES as a field is a field, wherever it sits. This
        # is additive by construction: it can only turn an unresolved ``<a-b>`` into a
        # name, never rename anything, and only GLYPH declares an address outside 3-1
        # (`test_only_the_glyph_namespace_declares_a_field_outside_3_1` holds the line).
        try:
            declared = _fr.field_at(sandbox, _body(token))
        except KeyError:
            declared = None
        return declared or UNRESOLVED_FORMAT.format(token=payload)
    try:
        name = _fr.field_at(sandbox, payload)
    except KeyError:  # no namespace for this sandbox — say so, never guess one
        name = None
    return name or UNRESOLVED_FORMAT.format(token=payload)


def _collapse(names: list[str], radices: list[str] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fold consecutive equal names into one ``name+`` run; a run's radix is its first's."""
    out: list[list[Any]] = []
    for index, name in enumerate(names):
        radix = radices[index] if radices is not None and index < len(radices) else ""
        if out and out[-1][0] == name:
            out[-1][1] += 1
        else:
            out.append([name, 1, radix])
    fields = tuple(f"{name}{RUN_SUFFIX}" if count > 1 else name for name, count, _r in out)
    return fields, (tuple(radix for _n, _c, radix in out) if radices is not None else ())


def row_shape(raw: Any, *, sandbox: str, radices: Mapping[str, str] | None = None) -> RowShape:
    """The kind of one row, from its ``raw`` payload.

    A head is ``[self_address, marker, magnitude, marker, magnitude, ...]``. The trailing
    tail (``[["4-5-1", ...], ["parcel_1"]]``) is the row's LABEL and is content, so it is
    not part of the shape.
    """
    head = _row_head(raw)
    if not head:
        return RowShape(layer="?", fields=())
    address = _text(head[0])
    layer = address.split("-", 1)[0] if "-" in address else "?"
    markers = [_text(head[i]) for i in range(1, len(head) - 1, 2)]
    names = [_field_name(token, sandbox=sandbox) for token in markers]
    # ``radices`` — ``field address -> backing radix`` from the anchor — makes the shape
    # carry each field's parent too (see :class:`RowShape`).
    parents = ([_text(radices.get(_body(token), "")) for token in markers]
               if radices is not None else None)
    fields, rads = _collapse(names, parents)
    return RowShape(layer=layer, fields=fields, radices=rads)


def document_row_shapes(document: Any, *, sandbox: str = "") -> Counter[RowShape]:
    """Every row shape in a document, with how many rows carry it."""
    resolved = _text(sandbox) or sandbox_of(document)
    shapes: Counter[RowShape] = Counter()
    for row in getattr(document, "rows", ()) or ():
        raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
        shapes[row_shape(raw, sandbox=resolved)] += 1
    return shapes


def document_shape_signature(document: Any, *, sandbox: str = "") -> str:
    """The document's archetype signature: a ``sha256:`` token over its SET of row shapes.

    The **set**, not the multiset: how many rows of a kind a document holds is its size, not
    its kind. Two county boundaries with different vertex counts, and a contact list of 3
    against one of 300, are each one archetype.
    """
    shapes = document_row_shapes(document, sandbox=sandbox)
    payload = json.dumps(
        {"policy": ARCHETYPE_SHAPE_POLICY, "shapes": sorted(str(shape) for shape in shapes)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def unresolved_markers(document: Any, *, sandbox: str = "") -> Counter[str]:
    """Every ``<…>`` token in a document's shapes, with its row count.

    A non-empty result is a gap in :mod:`.field_registry` for that namespace, and it is
    reported rather than tolerated: two archetypes that differ only inside an unresolved
    marker are indistinguishable to this fold.
    """
    out: Counter[str] = Counter()
    for shape, count in document_row_shapes(document, sandbox=sandbox).items():
        for name in shape.fields:
            base = name[: -len(RUN_SUFFIX)] if name.endswith(RUN_SUFFIX) else name
            if base.startswith("<") and base.endswith(">"):
                out[base] += count
    return out


def is_misaligned(shape: RowShape) -> bool:
    """True when the row this shape describes stopped parsing as marker/magnitude pairs.

    Checks the base name, because consecutive bad slots collapse into a run like any other
    repeat — the live 7-4-1 row folds to ``('lcl_id', '!misaligned+')``.
    """
    return any(
        (field[: -len(RUN_SUFFIX)] if field.endswith(RUN_SUFFIX) else field) == MISALIGNED_FIELD
        for field in shape.fields
    )


def misaligned_rows(document: Any, *, sandbox: str = "") -> int:
    """How many rows in the document have a head that stops parsing as marker/magnitude pairs.

    Non-zero means an archetype minted from this document would describe rows nobody wrote.
    Phase 0 reports it; Phase 1 refuses to mint from it.
    """
    return sum(
        count
        for shape, count in document_row_shapes(document, sandbox=sandbox).items()
        if is_misaligned(shape)
    )


__all__ = [
    "ARCHETYPE_SHAPE_POLICY",
    "MISALIGNED_FIELD",
    "RUN_SUFFIX",
    "STRUCTURAL_MARKER",
    "UNRESOLVED_FORMAT",
    "RowShape",
    "document_row_shapes",
    "document_shape_signature",
    "is_misaligned",
    "misaligned_rows",
    "row_shape",
    "sandbox_of",
    "unresolved_markers",
]
