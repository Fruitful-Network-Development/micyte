"""Node-address-level operations (mint / relocate / repoint / rename / drop) plus
the cross-sheet reference rewrite and SAMRAS-magnitude recompile.

These build on :mod:`node_addrs` (the variable-depth tree algebra), :mod:`refs`
(the sandbox reference index), and :mod:`samras_deps`. Unlike the row-level ops
(which reorder ``layer-vg-iteration`` row keys), these change the **node-address
values** stored as magnitudes — and therefore must cascade across every sheet
that references the moved node. Each op returns a :class:`WorkbookDelta` touching
*all* affected sheets, computed against the workbook it is given, so a sequence
composes correctly (the next op sees prior edits).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)
from micyte.core.datum_semantics import parse_datum_address

from . import labels, samras_deps
from . import node_addrs as na
from .ops import InsertRow, Workbook, WorkbookDelta
from .refs import _head, _is_definition_head, build_reference_index, defined_node_addrs


def _rewrite_row_node_values(row: AuthoritativeDatumDocumentRow, remap: dict[str, str]) -> AuthoritativeDatumDocumentRow:
    """Exact-match remap every head value token (index ≥ 1; self-address preserved)."""
    head = _head(row.raw)
    if head is None:
        return row
    changed = False
    new_head = [head[0]]
    for token in head[1:]:
        mapped = remap.get(token, token) if isinstance(token, str) else token
        if mapped != token:
            changed = True
        new_head.append(mapped)
    if not changed:
        return row
    return AuthoritativeDatumDocumentRow(datum_address=row.datum_address, raw=[new_head, *list(row.raw[1:])])


def _rewrite_sheet(doc: AuthoritativeDatumDocument, remap: dict[str, str], *, skip_row: str | None = None) -> AuthoritativeDatumDocument:
    # skip_row protects a folded node's own definition row from being rewritten onto its target.
    rows = tuple(
        r if r.datum_address == skip_row else _rewrite_row_node_values(r, remap)
        for r in doc.rows
    )
    if rows == doc.rows:
        return doc
    return replace(doc, rows=rows)


def _apply_remap_all_sheets(workbook: Workbook, remap: dict[str, str], *, skip: tuple[str, str] | None = None) -> dict[str, AuthoritativeDatumDocument]:
    """Apply a node-address remap to every sheet; return only the sheets that changed.

    ``skip`` is an optional ``(sheet, row)`` whose row is left untouched.
    """
    touched: dict[str, AuthoritativeDatumDocument] = {}
    for name in workbook.names():
        skip_row = skip[1] if (skip and skip[0] == name) else None
        updated = _rewrite_sheet(workbook.sheet(name), remap, skip_row=skip_row)
        if updated is not workbook.sheet(name):
            touched[name] = updated
    return touched


def _def_family_next_address(doc: AuthoritativeDatumDocument) -> str:
    """The next contiguous row address at the tail of the definition family."""
    families: dict[tuple[int, int], int] = {}
    for row in doc.rows:
        head = _head(row.raw)
        if head is not None and _is_definition_head(head):
            layer, vg, iteration = parse_datum_address(row.datum_address)
            families[(layer, vg)] = max(families.get((layer, vg), 0), iteration)
    if not families:
        raise ValueError("sheet has no definition family")
    if len(families) > 1:
        raise ValueError(f"sheet has multiple definition families: {sorted(families)}")
    (layer, vg), upper = next(iter(families.items()))
    return f"{layer}-{vg}-{upper + 1}"


def _drop_and_renumber(doc: AuthoritativeDatumDocument, drop_addrs: set[str]) -> AuthoritativeDatumDocument:
    """Remove ``drop_addrs`` rows and compact each affected family from its lower bound.

    Family lower bounds are preserved (only gaps left by drops are closed), and
    each kept row's self-address (head[0]) is updated to its new key.
    """
    drop_families = {parse_datum_address(a)[:2] for a in drop_addrs}
    survivors = [r for r in doc.rows if r.datum_address not in drop_addrs]
    # group survivors of affected families, renumber from each family's lower bound
    lowers: dict[tuple[int, int], int] = {}
    for r in doc.rows:
        fam = parse_datum_address(r.datum_address)[:2]
        it = parse_datum_address(r.datum_address)[2]
        lowers[fam] = min(lowers.get(fam, it), it)
    by_family: dict[tuple[int, int], list[AuthoritativeDatumDocumentRow]] = {}
    for r in survivors:
        by_family.setdefault(parse_datum_address(r.datum_address)[:2], []).append(r)
    new_rows: list[AuthoritativeDatumDocumentRow] = []
    for r in survivors:
        fam = parse_datum_address(r.datum_address)[:2]
        if fam not in drop_families:
            new_rows.append(r)
    for fam in drop_families:
        layer, vg = fam
        ordered = sorted(by_family.get(fam, []), key=lambda r: parse_datum_address(r.datum_address)[2])
        nxt = lowers[fam]
        for r in ordered:
            new_addr = f"{layer}-{vg}-{nxt}"
            nxt += 1
            head = _head(r.raw)
            if head is not None and head[0] == r.datum_address:
                new_raw = [[new_addr, *head[1:]], *list(r.raw[1:])]
                new_rows.append(AuthoritativeDatumDocumentRow(datum_address=new_addr, raw=new_raw))
            else:
                new_rows.append(AuthoritativeDatumDocumentRow(datum_address=new_addr, raw=r.raw))
    return replace(doc, rows=tuple(new_rows))


# --------------------------------------------------------------------------- #
# Node-address ops
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MintNode:
    """Append a new definition row that mints ``node_addr`` (a contiguous child)."""

    sheet: str
    node_addr: str
    title: str
    marker: str = labels.RF_NODE_ID
    title_marker: str = labels.RF_TITLE

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        node_set = defined_node_addrs(doc)
        if self.node_addr in node_set:
            raise ValueError(f"node already defined: {self.node_addr}")
        parent = na.parent_of(self.node_addr)
        if parent and parent not in node_set:
            raise ValueError(f"mint parent not present: {parent!r}")
        if self.node_addr != na.next_child(parent, node_set):
            raise ValueError(
                f"mint must be the next contiguous child of {parent!r}: "
                f"expected {na.next_child(parent, node_set)}, got {self.node_addr}"
            )
        label = labels.label_for_encoding(self.title)
        row_addr = _def_family_next_address(doc)
        raw = [[row_addr, self.marker, self.node_addr, self.title_marker, labels.encode_label_bits(label)], [self.title]]
        delta = InsertRow(self.sheet, row_addr, raw).apply(workbook)
        return WorkbookDelta(touched_sheets=delta.touched_sheets, address_map=delta.address_map)


@dataclass(frozen=True)
class RelocateNode:
    """Re-parent ``node_addr`` under ``new_parent`` (sibling-renumber + ref cascade)."""

    sheet: str
    node_addr: str
    new_parent: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        node_set = defined_node_addrs(doc)
        if self.node_addr not in node_set:
            raise ValueError(f"node not defined in {self.sheet}: {self.node_addr}")
        remap, _new_node = na.relocate_subtree_remap(self.node_addr, self.new_parent, node_set)
        touched = _apply_remap_all_sheets(workbook, remap)
        return WorkbookDelta(touched_sheets=touched, node_addr_remap=remap)


@dataclass(frozen=True)
class RepointNode:
    """Fold references to ``node_addr`` onto an existing ``target`` node.

    Rewrites every *reference* to ``node_addr`` across the sandbox to ``target``,
    leaving ``node_addr``'s own definition row intact (so a subsequent
    :class:`DropNode` can remove it). ``target`` must already be defined.
    """

    sheet: str
    node_addr: str
    target: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        index = build_reference_index(workbook)
        if self.target not in index.defined_nodes():
            raise ValueError(f"repoint target not defined: {self.target}")
        owner = index.defining_row(self.node_addr)
        skip = (owner.sheet, owner.row) if owner else None
        touched = _apply_remap_all_sheets(workbook, {self.node_addr: self.target}, skip=skip)
        return WorkbookDelta(touched_sheets=touched, node_addr_remap={self.node_addr: self.target})


@dataclass(frozen=True)
class RenameNode:
    """Rename a node's title (label tail + 512-bit title magnitude); address unchanged."""

    sheet: str
    node_addr: str
    new_title: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        index = build_reference_index(workbook)
        owner = index.defining_row(self.node_addr)
        if owner is None or owner.sheet != self.sheet:
            raise ValueError(f"node not defined in {self.sheet}: {self.node_addr}")
        doc = workbook.sheet(self.sheet)
        rows: list[AuthoritativeDatumDocumentRow] = []
        for row in doc.rows:
            if row.datum_address != owner.row:
                rows.append(row)
                continue
            head = _head(row.raw)
            label = labels.label_for_encoding(self.new_title)
            new_head = list(head)
            # title magnitude is the slot after the title marker (rf.3-1-2)
            for i in range(1, len(new_head) - 1):
                if str(new_head[i]) == labels.RF_TITLE:
                    new_head[i + 1] = labels.encode_label_bits(label)
            rows.append(AuthoritativeDatumDocumentRow(datum_address=row.datum_address, raw=[new_head, [self.new_title]]))
        return WorkbookDelta(touched_sheets={self.sheet: replace(doc, rows=tuple(rows))})


@dataclass(frozen=True)
class DropNode:
    """Delete a node's definition row(s) (+ sibling renumber). Blocked if referenced."""

    sheet: str
    node_addr: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        index = build_reference_index(workbook)
        if index.is_referenced(self.node_addr):
            raise ValueError(f"cannot drop still-referenced node: {self.node_addr}")
        doc = workbook.sheet(self.sheet)
        node_set = defined_node_addrs(doc)
        if self.node_addr not in node_set:
            raise ValueError(f"node not defined in {self.sheet}: {self.node_addr}")
        sibling_remap, removed_subtree = na.remove_subtree_remap(self.node_addr, node_set)
        # rows that DEFINE a removed node (head[2] in removed_subtree) get dropped
        drop_rows: set[str] = set()
        for row in doc.rows:
            head = _head(row.raw)
            if head is not None and len(head) >= 3 and str(head[2]) in removed_subtree and _is_definition_head(head):
                drop_rows.add(row.datum_address)
        new_doc = _drop_and_renumber(doc, drop_rows)
        # apply the sibling node-address renumber across all sheets (post-drop workbook)
        post = workbook.with_sheet(self.sheet, new_doc)
        touched = _apply_remap_all_sheets(post, sibling_remap)
        touched.setdefault(self.sheet, post.sheet(self.sheet))
        return WorkbookDelta(touched_sheets=touched, node_addr_remap=sibling_remap)


# --------------------------------------------------------------------------- #
# Cross-sheet primitives
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RewriteRefs:
    """Apply a node-address remap to every reference slot across all sheets."""

    remap: dict[str, str]

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        touched = _apply_remap_all_sheets(workbook, dict(self.remap))
        return WorkbookDelta(touched_sheets=touched, node_addr_remap=dict(self.remap))


@dataclass(frozen=True)
class RecompileMagnitude:
    """Recompute a SAMRAS magnitude row over a source sheet's current node set."""

    sheet: str
    anchor_address: str
    node_source_sheet: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        node_set = defined_node_addrs(workbook.sheet(self.node_source_sheet))
        rows: list[AuthoritativeDatumDocumentRow] = []
        found = False
        for row in doc.rows:
            if row.datum_address == self.anchor_address:
                found = True
                rows.append(AuthoritativeDatumDocumentRow(
                    datum_address=row.datum_address,
                    raw=samras_deps.recompiled_magnitude_raw(row, node_set),
                ))
            else:
                rows.append(row)
        if not found:
            raise ValueError(f"magnitude row not found: {self.anchor_address}")
        return WorkbookDelta(touched_sheets={self.sheet: replace(doc, rows=tuple(rows))})


@dataclass(frozen=True)
class RebuildCollection:
    """Rebuild a RUDI collection row (e.g. txa 5-0-1) over the current def-family rows."""

    sheet: str
    collection_address: str
    label: str

    def apply(self, workbook: Workbook) -> WorkbookDelta:
        doc = workbook.sheet(self.sheet)
        refs = [
            r.datum_address
            for r in sorted(doc.rows, key=lambda x: parse_datum_address(x.datum_address))
            if (h := _head(r.raw)) is not None and _is_definition_head(h)
        ]
        rows: list[AuthoritativeDatumDocumentRow] = []
        found = False
        for row in doc.rows:
            if row.datum_address == self.collection_address:
                found = True
                rows.append(AuthoritativeDatumDocumentRow(
                    datum_address=row.datum_address,
                    raw=[[self.collection_address, "~", *refs], [self.label]],
                ))
            else:
                rows.append(row)
        if not found:
            rows.append(AuthoritativeDatumDocumentRow(
                datum_address=self.collection_address,
                raw=[[self.collection_address, "~", *refs], [self.label]],
            ))
        return WorkbookDelta(touched_sheets={self.sheet: replace(doc, rows=tuple(rows))})
