"""The archetype registry — what KIND a document is, read out of the archetype sandbox.

``docs/wiki/60-canonical-datum-and-hyphae-flags.md`` leaves open question 4 as: *"Where is
the registry sourced? In-code constant, a MOS datum document, or per-tenant config? A
datum-document-backed registry would be self-hosting (the registry is itself canonical
data) but introduces a bootstrap dependency."* This module takes the self-hosting option.

The bootstrap dependency is real and bounded: :func:`build_registry` reads only documents
whose metadata says ``role == "archetype"``, folds them with the same
:mod:`~micyte.core.datum_ops.archetype_shape` fold it will later apply to the corpus, and
never consults the registry it is building.

## An archetype is a blank instance, not a description of one

The document IS the denotation. A ``geospatial_polygon`` archetype is a row with two
coordinate cells; a ``record`` is a row with an msn_id cell and a title cell. So the shape
an archetype claims cannot drift from the shape it has, and nothing about matching lives in
a side-channel that could disagree with the data.

Optionality rides in the MAGNITUDE, which the shape fold discards and this reader keeps:

===================  ==========================================================
``"0"``              the cell is required
``""``               the cell is optional
===================  ==========================================================

Consecutive cells naming the same field form a **run**, and the run's rule falls straight
out of its cells:

===================================  ====================================================
2 required coordinate cells          matches ``coordinate+`` only — a lone coordinate is a
                                     ``geospatial_point``, and the two must not collapse
1 required + 1 optional msn_id cell  matches ``msn_id`` or ``msn_id+`` — the corpus carries
                                     boundary nodes both ways (428 single, 39 doubled)
1 required cell                      matches ``msn_id`` only
all cells optional                   the run may be absent entirely
===================================  ====================================================

That last table is the whole matching rule, and every input to it is a magnitude in a live
document.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from micyte.core.datum_ops.archetype_shape import (
    RUN_SUFFIX,
    STRUCTURAL_MARKER,
    RowShape,
    document_row_shapes,
    is_misaligned,
    row_shape,
    sandbox_of,
)

#: The sandbox the library lives in, and the metadata key that marks a member of it.
ARCHETYPE_SANDBOX = "archetype"
ROLE_KEY = "role"
ROLE_VALUE = "archetype"

REQUIRED_FILLER = "0"
OPTIONAL_FILLER = ""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


@dataclass(frozen=True)
class Run:
    """One field's consecutive cells in an archetype's row."""

    field: str
    #: How many of the cells are required. Zero means the whole run may be absent.
    minimum: int
    #: How many cells the archetype declares. Two or more means the field may repeat.
    declared: int
    #: A radix address (``2-1-1``) instead of a field name: the run is satisfied by ANY
    #: field the sandbox's anchor backs with that radix — a 256-16 name and a 256-64 title
    #: both satisfy "a common ascii-256 parent" (operator, 2026-09-16, primitive c; D3).
    #: Declared in the archetype's row by putting the radix address in the marker cell.
    parent: str = ""

    def matches(self, token: str, *, radix: str = "") -> bool:
        observed_run = token.endswith(RUN_SUFFIX)
        base = token[: -len(RUN_SUFFIX)] if observed_run else token
        if self.parent:
            if radix != self.parent:
                return False
        elif base != self.field:
            return False
        if observed_run:
            return self.declared >= 2
        return self.minimum <= 1

    @property
    def optional(self) -> bool:
        return self.minimum == 0

    @property
    def token(self) -> str:
        return self.field + RUN_SUFFIX if self.declared >= 2 else self.field


@dataclass(frozen=True)
class Archetype:
    """One named row shape, read back out of its blank instance."""

    name: str
    document_id: str
    layer: str
    runs: tuple[Run, ...]
    note: str = ""

    @property
    def has_parent_runs(self) -> bool:
        """Does any run bind a parent radix? Then ``covers`` needs a shape with radices,
        and the caller must read the anchor (``viewscope_edit.backing_radices``)."""
        return any(run.parent for run in self.runs)

    @property
    def maximal_shape(self) -> RowShape:
        """Every run present. Usually NOT itself an observed shape — see :meth:`covers`."""
        return RowShape(layer=self.layer, fields=tuple(run.token for run in self.runs))

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(run.field for run in self.runs if not run.optional)

    @property
    def declared_fields(self) -> tuple[str, ...]:
        """Every field this archetype declares, required or optional, in row order.

        The vocabulary a CLASS slot is filtered against: a class describes what its members
        have in common, so a slot naming a field this archetype does not carry is dropped
        rather than drawn as an empty pair. Distinct from :attr:`required_fields`, which
        answers a different question — what a row must carry to match at all.
        """
        return tuple(run.field for run in self.runs)

    def covers(self, shape: RowShape) -> bool:
        """Is ``shape`` an instance of this archetype?

        The observed tokens must be a SUBSEQUENCE of the runs — order preserved, optional
        runs skippable — and no required run may be skipped. A maximal row carrying every
        optional field at once is what the archetype document holds; what the corpus holds
        is the variants, and one declaration has to recognise all of them or the five
        spellings of a contact card become five archetypes.
        """
        if shape.layer != self.layer or is_misaligned(shape):
            return False
        index = 0
        for position, token in enumerate(shape.fields):
            radix = shape.radix_at(position)
            while index < len(self.runs) and not self.runs[index].matches(token, radix=radix):
                if not self.runs[index].optional:
                    return False
                index += 1
            if index >= len(self.runs):
                return False
            index += 1
        return all(run.optional for run in self.runs[index:])


_RADIX_ADDRESS = re.compile(r"^2-[0-9]+-[0-9]+$")


def _parent_radix(cell: Any) -> str:
    """The radix address a marker cell names, or ``""`` for a field marker. A radix lives
    at layer 2 (``2-1-1`` ASCII, ``2-0-5`` lcl); a field babelette at layer 3."""
    token = _text(cell)
    body = token.split(".", 1)[1] if token.lower().startswith(("rf.", "ref.")) else token
    return body if _RADIX_ADDRESS.fullmatch(body) else ""


def _is_archetype_document(document: Any) -> bool:
    metadata = getattr(document, "document_metadata", None)
    if not isinstance(metadata, dict):
        return False
    return _text(metadata.get(ROLE_KEY)) == ROLE_VALUE


def _archetype_name(document: Any) -> str:
    """The archetype's name: its canonical name, else the id's name segment."""
    name = _text(getattr(document, "canonical_name", ""))
    if name:
        return name
    parts = _text(getattr(document, "document_id", "")).split(".")
    return parts[3] if len(parts) > 4 else ""


def parse_archetype(document: Any, *, sandbox: str = ARCHETYPE_SANDBOX) -> Archetype | None:
    """Read one archetype document back into an :class:`Archetype`, or ``None``.

    ``None`` for the sandbox anchor (it declares the vocabulary rather than an archetype),
    for a document with no rows, and for one whose row does not parse — an archetype minted
    from a misaligned head would describe rows nobody wrote.

    The runs are derived from the ROW, never from ``document_metadata``. The metadata
    carries a ``shape`` string for a human reading the document, and a reader that trusted
    it would be trusting a copy of the thing it is looking at.
    """
    rows = tuple(getattr(document, "rows", ()) or ())
    if not rows or not _is_archetype_document(document):
        return None
    name = _archetype_name(document)
    if not name or getattr(document, "is_anchor", False) or name == "anchor":
        return None

    row = rows[0]
    raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
    shape = row_shape(raw, sandbox=sandbox)
    if not shape.fields or is_misaligned(shape):
        return None
    head = raw[0]

    runs: list[Run] = []
    for index in range(1, len(head) - 1, 2):
        required = _text(head[index + 1]) == REQUIRED_FILLER
        parent = _parent_radix(head[index])
        if parent:
            # A radix address in the marker cell binds the PARENT, not a field.
            token = f"any:{parent}"
            if runs and runs[-1].field == token:
                previous = runs.pop()
                runs.append(Run(field=token, minimum=previous.minimum + (1 if required else 0),
                                declared=previous.declared + 1, parent=parent))
            else:
                runs.append(Run(field=token, minimum=1 if required else 0, declared=1, parent=parent))
            continue
        field = row_shape([[head[0], head[index], head[index + 1]]], sandbox=sandbox).fields
        if not field:
            return None
        token = field[0]
        if runs and runs[-1].field == token:
            previous = runs.pop()
            runs.append(
                Run(
                    field=token,
                    minimum=previous.minimum + (1 if required else 0),
                    declared=previous.declared + 1,
                )
            )
        else:
            runs.append(Run(field=token, minimum=1 if required else 0, declared=1))

    metadata = document.document_metadata
    return Archetype(
        name=name,
        document_id=_text(getattr(document, "document_id", "")),
        layer=shape.layer,
        runs=tuple(runs),
        note=_text(metadata.get("note")),
    )


class ArchetypeRegistry:
    """``RowShape -> archetype name``, built from the archetype sandbox's own documents."""

    def __init__(self, archetypes: tuple[Archetype, ...]) -> None:
        self._archetypes = archetypes
        self._by_name = {a.name: a for a in archetypes}
        self._cache: dict[RowShape, tuple[str, ...]] = {}

    def __len__(self) -> int:
        return len(self._archetypes)

    @property
    def archetypes(self) -> tuple[Archetype, ...]:
        return self._archetypes

    def get(self, name: str) -> Archetype | None:
        return self._by_name.get(_text(name))

    def ambiguities(self) -> dict[str, tuple[str, ...]]:
        """Any maximal shape more than one archetype covers.

        A row matching two archetypes has no archetype: the binding would resolve by
        iteration order, which is not a denotation. Non-empty is a defect in the LIBRARY,
        so it is reported rather than raised — the caller decides whether to refuse.
        """
        out: dict[str, tuple[str, ...]] = {}
        for archetype in self._archetypes:
            owners = tuple(
                other.name for other in self._archetypes if other.covers(archetype.maximal_shape)
            )
            if len(owners) > 1:
                out[str(archetype.maximal_shape)] = owners
        return out

    def match_row(self, shape: RowShape) -> tuple[str, ...]:
        """Every archetype covering this row shape. Empty when none does."""
        hit = self._cache.get(shape)
        if hit is None:
            hit = tuple(a.name for a in self._archetypes if a.covers(shape))
            self._cache[shape] = hit
        return hit

    def archetypes_for(self, document: Any, *, sandbox: str = "") -> tuple[str, ...]:
        """Every archetype any of the document's rows matches, most rows first."""
        counts: Counter = Counter()
        for shape, rows in document_row_shapes(document, sandbox=sandbox).items():
            for name in self.match_row(shape):
                counts[name] += rows
        return tuple(name for name, _ in counts.most_common())

    def primary_archetype(self, document: Any, *, sandbox: str = "") -> str:
        """The archetype of the document's most numerous SUBSTANTIVE row, or ``""``."""
        return self.primary_archetype_of(document_row_shapes(document, sandbox=sandbox))

    def primary_archetype_of(self, shapes: Counter) -> str:
        """:meth:`primary_archetype`, from a shape census a caller already holds.

        A caller that streams a document row by row has counted the shapes on the way
        past and must not be made to assemble the document again to ask what it is — that
        assembly is the whole cost ``iter_document_rows_by_sandbox`` exists to avoid.

        Structural rows — a head of nothing but ``~`` — are scaffolding every document
        carries, so they can never say what kind one is.
        """
        counts: Counter = Counter()
        for shape, rows in shapes.items():
            if not shape.fields or set(shape.fields) <= {STRUCTURAL_MARKER}:
                continue
            for name in self.match_row(shape):
                counts[name] += rows
        return counts.most_common(1)[0][0] if counts else ""


def archetype_documents(documents: Any) -> tuple[Any, ...]:
    """The members of the archetype library, by their declared role.

    By ``document_metadata.role``, not by sandbox name: a library copied into another
    tenant is still the library, and a document that lands in the sandbox without the role
    is not one.
    """
    return tuple(d for d in documents if _is_archetype_document(d))


def build_registry(documents: Any) -> ArchetypeRegistry:
    """Fold the archetype library into a registry.

    Reads only ``role == "archetype"`` documents and never consults the registry it is
    building — the bootstrap dependency the wiki flags, kept to one direction.
    """
    parsed = []
    for document in archetype_documents(documents):
        sandbox = sandbox_of(document) or ARCHETYPE_SANDBOX
        archetype = parse_archetype(document, sandbox=sandbox)
        if archetype is not None:
            parsed.append(archetype)
    parsed.sort(key=lambda a: a.name)
    return ArchetypeRegistry(tuple(parsed))


#: Bounded memo so a per-request read does not re-fold the library. Keyed on the archetype
#: documents' ids, which carry their content hash — so any edit to any archetype is a new
#: key, and a stale registry is not reachable. Two entries, for the same reason the catalog
#: cache is bounded to two: an unbounded one cost +293 MiB per test on 2026-08-05.
_REGISTRY_CACHE: dict[tuple[str, ...], ArchetypeRegistry] = {}
_REGISTRY_CACHE_MAX = 2


def registry_for(documents: Any) -> ArchetypeRegistry:
    """:func:`build_registry`, memoized on the library's content-addressed ids."""
    key = tuple(sorted(_text(getattr(d, "document_id", "")) for d in archetype_documents(documents)))
    hit = _REGISTRY_CACHE.get(key)
    if hit is not None:
        return hit
    registry = build_registry(documents)
    if len(_REGISTRY_CACHE) >= _REGISTRY_CACHE_MAX:
        _REGISTRY_CACHE.pop(next(iter(_REGISTRY_CACHE)))
    _REGISTRY_CACHE[key] = registry
    return registry


__all__ = [
    "ARCHETYPE_SANDBOX",
    "Archetype",
    "ArchetypeRegistry",
    "OPTIONAL_FILLER",
    "REQUIRED_FILLER",
    "ROLE_KEY",
    "ROLE_VALUE",
    "Run",
    "archetype_documents",
    "build_registry",
    "parse_archetype",
    "registry_for",
]
