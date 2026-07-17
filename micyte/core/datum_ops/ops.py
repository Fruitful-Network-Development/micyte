"""Rudimentary datum-document manipulation operations.

Each operation is a frozen dataclass with an ``apply(workbook) -> WorkbookDelta``
method. Operations are *pure*: they never touch a store; they transform an
in-memory :class:`Workbook` (a sandbox loaded as a set of named sheets) and
return the touched sheets plus any address remaps. A higher layer
(:mod:`migrate`) threads the deltas, re-mints canonical ids, and a single
store-bound executor (:mod:`adapters.sql.datum_workbook_apply`) persists them.

Row-level ops (``InsertRow``/``DeleteRow``/``MoveRow``/``ReorderRow``) are thin
wrappers over the trusted intra-document reorder engine in
:mod:`micyte.core.datum_semantics` — they inherit its
iteration-shift, intra-document reference remap, contiguity guard, and
delete-while-referenced block. Node-address ops (mint/relocate/repoint/…) and
the cross-sheet ops (RewriteRefs/RecompileMagnitude/RebuildCollection) live in
:mod:`node_ops` and build on this same delta protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from micyte.core.datum_documents import AuthoritativeDatumDocument
from micyte.core.datum_semantics import (
    parse_datum_address,
    preview_document_delete,
    preview_document_insert,
    preview_document_move,
)

# Canonical sandbox sheet order: anchor first (magnitudes), then taxonomy/
# classification, then referrers — used for both serialization and write order.
SHEET_ORDER = ["anchor", "txa", "lcl", "product_profiles"]


def order_sheets(names) -> list[str]:
    """Known sheets in SHEET_ORDER, then any others alphabetically."""
    names = set(names)
    return [n for n in SHEET_ORDER if n in names] + sorted(n for n in names if n not in SHEET_ORDER)


@dataclass(frozen=True)
class Workbook:
    """A sandbox loaded as a set of named sheets (one datum document each).

    ``external_nodes`` are node addresses defined OUTSIDE this sandbox that its
    rows are permitted to reference — the reference-existence rule treats them as
    defined. Empty means "this sandbox must be self-contained".

    It exists because cross-sandbox references are designed, not accidental: the
    heirloom ingest keys trapp's ``product_profiles`` rows to taxon nodes it looks
    up in the ``taxonomy`` sandbox ("Only trapp_family_farm docs are written;
    taxonomy is Phase I"), and ``deployed/tff/build.json`` names ``txa`` as a
    cross-portal reference. Without this the rule check sees only the one sandbox
    it loaded, reports every such reference as dangling, and blocks every
    workbook apply on trapp.

    The set is supplied by whoever loads the workbook, so the policy for "which
    documents may I reference" stays at the composition root (see
    ``load_workbook``) rather than in the engine. Phase 3 replaces that caller's
    hardcoded list with the declared ``references[]`` contract; nothing here
    changes when it does.
    """

    sandbox: str
    sheets: dict[str, AuthoritativeDatumDocument]
    external_nodes: frozenset[str] = frozenset()

    def sheet(self, name: str) -> AuthoritativeDatumDocument:
        if name not in self.sheets:
            raise KeyError(f"sheet not in workbook: {name!r}")
        return self.sheets[name]

    def names(self) -> tuple[str, ...]:
        return tuple(self.sheets.keys())

    def with_sheet(self, name: str, document: AuthoritativeDatumDocument) -> Workbook:
        merged = dict(self.sheets)
        merged[name] = document
        return replace(self, sheets=merged)

    def with_sheets(self, updates: dict[str, AuthoritativeDatumDocument]) -> Workbook:
        merged = dict(self.sheets)
        merged.update(updates)
        return replace(self, sheets=merged)


@dataclass(frozen=True)
class WorkbookDelta:
    """The effect of one op: touched sheets + any address remaps + issues.

    ``address_map`` is the intra-document datum-address (row) remap produced by
    the reorder engine. ``node_addr_remap`` is the cross-document node-address
    (value) remap produced by relocate/repoint — what :class:`RewriteRefs`
    applies to dependent slots in other sheets.
    """

    touched_sheets: dict[str, AuthoritativeDatumDocument]
    address_map: dict[str, str] = field(default_factory=dict)
    node_addr_remap: dict[str, str] = field(default_factory=dict)
    issues: tuple[str, ...] = ()


def apply_sequence(workbook: Workbook, ops: list[Any]) -> tuple[Workbook, list[WorkbookDelta]]:
    """Apply ``ops`` in order, threading each delta's touched sheets forward.

    The next op always sees prior edits (mirrors how the ingest script threads
    the rebuilt txa doc into the product-row loop). Returns the final workbook
    and the per-op delta list.
    """
    deltas: list[WorkbookDelta] = []
    current = workbook
    for op in ops:
        delta = op.apply(current)
        if delta.touched_sheets:
            current = current.with_sheets(delta.touched_sheets)
        deltas.append(delta)
    return current, deltas


# --------------------------------------------------------------------------- #
# Row-level ops (delegate to datum_semantics; intra-sheet)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InsertRow:
    sheet: str
    target_address: str
    raw: Any

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        res = preview_document_insert(doc, target_address=self.target_address, raw=self.raw)
        return WorkbookDelta(
            touched_sheets={self.sheet: res["updated_document"]},
            address_map=dict(res["address_map"]),
        )


@dataclass(frozen=True)
class DeleteRow:
    sheet: str
    target_address: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        res = preview_document_delete(doc, target_address=self.target_address)
        return WorkbookDelta(
            touched_sheets={self.sheet: res["updated_document"]},
            address_map=dict(res["address_map"]),
        )


@dataclass(frozen=True)
class MoveRow:
    sheet: str
    source_address: str
    destination_address: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        res = preview_document_move(
            doc,
            source_address=self.source_address,
            destination_address=self.destination_address,
        )
        return WorkbookDelta(
            touched_sheets={self.sheet: res["updated_document"]},
            address_map=dict(res["address_map"]),
        )


@dataclass(frozen=True)
class ReorderRow:
    """A within-family MoveRow (reorder a row's positional iteration value).

    Asserts source and destination share a ``(layer, value_group)`` family — a
    reorder, not a re-home into another family. (The cross-document reference
    guard precheck is layered on in :mod:`node_ops` once the sandbox reference
    index is available.)
    """

    sheet: str
    source_address: str
    destination_address: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        src_family = parse_datum_address(self.source_address)[:2]
        dst_family = parse_datum_address(self.destination_address)[:2]
        if src_family != dst_family:
            raise ValueError("reorder_must_stay_within_family")
        return MoveRow(self.sheet, self.source_address, self.destination_address).apply(workbook)
