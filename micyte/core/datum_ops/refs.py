"""Sandbox-wide cross-document reference index (the L1 reference model).

The intra-document engine (``datum_semantics``) tracks only 3-segment datum-address
references *within* one document and skips ``rf.`` markers as value-typing. But a
sandbox's documents reference each other by **node-address value**: e.g. a
``product_profiles`` row stores a txa taxonomy node (``"4-9"``) as the magnitude of
an ``rf.3-1-1``-typed pair. When that txa node relocates, every such slot must be
rewritten — the cross-document integrity the engine cannot see.

This module builds that index over a :class:`Workbook`, convention-agnostically:

* A datum row head is ``[self_address] + pairs``, each pair ``(reference_slot,
  magnitude_slot)`` (the V0.4 positional ``2N+1`` model — not driven by any single
  reference convention).
* A **reference marker** is ``rf.<addr>`` / ``ref.<addr>`` (case-insensitive). When
  it types a pair, the magnitude slot may hold a **node-address reference** value.
* A **definition row** carries an id-pair ``(rf.<id>, node_addr)`` immediately
  describing a *titled* node (its second pair is a title blob): that row *defines*
  the node. Every other node-address magnitude slot is a **reference edge**.

Bare numeric magnitudes (gestation seconds), unit-abstraction markers (``2-1-1``),
and 512-bit ASCII title blobs are correctly excluded from edges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from micyte.core.structures.samras.structure import as_text

from . import field_registry as _fr
from . import node_addrs as na
from .ops import Workbook

_MARKER_RE = re.compile(r"^(rf|ref)\.[0-9]+(-[0-9]+)*$", re.IGNORECASE)
_MULTI_SEG_RE = re.compile(r"^[0-9]+(-[0-9]+)+$")

# Markers whose magnitude is a NODE-ID reference (vs a typed literal). In agro_erp
# the babelette design types rf.3-1-1 = txa_id and rf.3-1-5 = lcl_id as node ids,
# while rf.3-1-2 (title), rf.3-1-3 (HOPS coordinate), rf.3-1-4 (msn_id) carry
# literal values that merely *look* like multi-segment node addresses. mycelium_network
# types rf.3-1-13 = lcl_id (its rf.3-1-1/3-1-5 slots are coordinate/identification, so
# the agro markers cannot double there). Only node-id markers produce cross-document
# reference edges. Configurable per sandbox.
NODE_REF_MARKERS = frozenset({
    _fr.marker(_fr.FARM, "txa_id"),       # rf.3-1-1 — agro node id
    _fr.marker(_fr.FARM, "lcl_id"),       # rf.3-1-5 — agro lcl id
    _fr.marker(_fr.REGISTRAR, "lcl_id"),  # rf.3-1-13 — registrar (mycelium) lcl id
})


#: The logical FIELDS whose magnitude is a node-id reference. Namespaces disagree about
#: which ADDRESS carries each, which is the whole reason this is a field list and not an
#: address list.
_NODE_REF_FIELDS = ("txa_id", "lcl_id")


def node_ref_markers_for(namespace: str) -> frozenset[str]:
    """The node-reference markers OF ONE NAMESPACE, derived from the field registry.

    :data:`NODE_REF_MARKERS` is the UNION of three namespaces' answers, and using it
    everywhere is a real defect with a measured size. `rf.3-1-1` is ``txa_id`` in `farm`
    and `taxonomy` — but ``coordinate`` in `registrar` and `archetype`, and ``utc`` in
    `system`. MEASURED across the live store on 2026-09-01, the union made the reference
    check report **162,249 dangling references out of 163,643 edges — a 99.1% false
    positive rate**, 162,102 of them `rf.3-1-1` cells holding coordinates and timestamps
    that merely look like multi-segment addresses.

    That is not a reporting nuisance: reference existence is a HARD check, and
    `datum_workbook_apply._verify` turns `check_step`'s hard list into failures that REFUSE
    the write. Any workbook touching a registrar or agnet document was gated by a check
    that could not read its namespace.

    DERIVED, not tabulated. Asking the registry which address carries `txa_id` and `lcl_id`
    in this namespace means a namespace that renumbers a field cannot leave a stale copy
    here — the defect this function exists to end, one level up.
    """
    out: set[str] = set()
    for field_name in _NODE_REF_FIELDS:
        try:
            out.add(_fr.marker(namespace, field_name))
        except Exception:
            # A namespace that does not define the field has no marker for it, which is
            # an answer rather than an error: `registrar` has no `txa_id` at all.
            continue
    return frozenset(out)


def is_reference_marker(token: object) -> bool:
    """True for any ``rf.``/``ref.`` value-typing marker (used for pair structure)."""
    return bool(_MARKER_RE.fullmatch(as_text(token)))


def is_node_ref_marker(token: object, markers: frozenset[str] = NODE_REF_MARKERS) -> bool:
    """True for a marker whose magnitude is a node-id *reference* (not a literal)."""
    return as_text(token).lower() in markers


def is_node_addr_reference(token: object) -> bool:
    """True when ``token`` is a node-address *reference value*.

    Multi-segment positive tuples (``4-9``, ``1-3-2-5-1``) and small bare roots
    (``4``) qualify. The ``"0"`` no-reference sentinel, large bare magnitudes
    (gestation seconds), and binary title blobs are excluded.
    """
    text = as_text(token)
    if not text:
        return False
    if _MULTI_SEG_RE.fullmatch(text):
        return all(int(seg) >= 1 for seg in text.split("-"))
    if text.isdigit():
        return 1 <= int(text) <= 999
    return False


def is_title_blob(token: object) -> bool:
    """True for an encoded title magnitude (binary string, ≥8 bits)."""
    text = as_text(token)
    return len(text) >= 8 and set(text) <= {"0", "1"}


def _head(raw: Any) -> list[Any] | None:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return None


def _is_definition_head(head: list[Any]) -> bool:
    """True when the head's id-pair *defines* a titled node (vs only references)."""
    if len(head) < 3:
        return False
    if not is_node_ref_marker(head[1]) or not is_node_addr_reference(head[2]):
        return False
    if len(head) >= 5:
        return is_title_blob(head[4])  # second pair is a title → this row defines head[2]
    return True  # bare id pair [self, marker, node]


def _head_edges(head: list[Any], markers: frozenset[str] = NODE_REF_MARKERS):
    """Every node-address reference in one row head, as ``(slot, marker, target)``.

    The pair-walk rule lives here once. A row head is ``[self_address] + pairs``, so
    the markers sit at odd indices and their magnitudes one slot on; a definition
    row's FIRST pair is its own id and is not an outbound edge.

    ``markers`` is THE NAMESPACE'S set — see :func:`node_ref_markers_for` for why the
    union is wrong and what it measured. It defaults to the union so a caller that has no
    namespace to offer behaves exactly as before rather than silently checking nothing.
    """
    definition = _is_definition_head(head)
    for i in range(1, len(head) - 1, 2):
        if definition and i == 1:
            continue  # the id-pair defines this row's node; not an outbound edge
        marker = as_text(head[i])
        value = as_text(head[i + 1])
        if is_node_ref_marker(marker, markers) and is_node_addr_reference(value):
            yield i + 1, marker, value


@dataclass(frozen=True)
class Edge:
    """A cross-reference: ``src_sheet``/``src_row`` head slot → ``target_node_addr``."""

    src_sheet: str
    src_row: str
    slot: int  # head index of the magnitude slot holding the reference value
    marker: str
    target_node_addr: str


@dataclass(frozen=True)
class DefinedNode:
    sheet: str
    row: str
    node_addr: str


@dataclass
class ReferenceIndex:
    edges: list[Edge] = field(default_factory=list)
    defined: dict[str, DefinedNode] = field(default_factory=dict)

    def references_to(self, node_addr: str) -> list[Edge]:
        """Edges pointing at ``node_addr`` or any of its descendants."""
        node = as_text(node_addr)
        return [e for e in self.edges if e.target_node_addr == node or na.is_descendant(e.target_node_addr, node)]

    def defining_row(self, node_addr: str) -> DefinedNode | None:
        return self.defined.get(as_text(node_addr))

    def is_referenced(self, node_addr: str) -> bool:
        """True when some row (other than the node's own definition) references it."""
        node = as_text(node_addr)
        owner = self.defined.get(node)
        for edge in self.references_to(node):
            if owner is not None and edge.src_sheet == owner.sheet and edge.src_row == owner.row:
                continue
            return True
        return False

    def defined_nodes(self) -> set[str]:
        return set(self.defined.keys())


def defined_node_addrs(doc: Any) -> set[str]:
    """The set of node addresses this document *defines* (titled id-pair rows)."""
    out: set[str] = set()
    for row in doc.rows:
        head = _head(row.raw)
        if head is not None and _is_definition_head(head):
            out.add(as_text(head[2]))
    return out


def workbook_msn(workbook: Workbook) -> str:
    """The instance a workbook's sheets belong to, read off a document id.

    A sandbox is addressed by (msn_id, sandbox) — eight instances hold one called `pim`
    and four hold `system` — so the sandbox NAME alone cannot resolve a namespace. The
    documents say whose they are (``lv.<msn>.<sandbox>.<name>.<hash>``), which is the
    honest source: the workbook is told nothing it does not already carry.
    """
    for sheet_name in workbook.names():
        parts = as_text(getattr(workbook.sheet(sheet_name), "document_id", "")).split(".")
        if len(parts) > 2 and parts[0] in ("lv", "st", "stl"):
            return parts[1]
    return ""


def markers_for_workbook(workbook: Workbook) -> tuple[frozenset[str], str]:
    """``(markers, why_not)`` — the node-ref markers this workbook's namespace defines.

    ``why_not`` is empty when the namespace resolved. When it did NOT, the markers fall
    back to the union and the reason is returned rather than swallowed, because the two
    outcomes are not the same check: a namespace-resolved run measures references, and a
    fallback run measures references PLUS every coordinate and timestamp that looks like
    one. `check_step` reports that as an advisory so a reader can tell which they got.
    """
    sandbox = as_text(getattr(workbook, "sandbox", ""))
    if not sandbox:
        return NODE_REF_MARKERS, "the workbook names no sandbox"
    try:
        namespace = _fr.namespace_for_sandbox(sandbox, msn_id=workbook_msn(workbook))
    except Exception as exc:
        return NODE_REF_MARKERS, f"no namespace for sandbox {sandbox!r}: {exc}"
    return node_ref_markers_for(namespace), ""


def build_reference_index(workbook: Workbook,
                          markers: frozenset[str] | None = None) -> ReferenceIndex:
    """Walk every sheet/row, recording defined nodes and cross-reference edges.

    ``markers`` is the namespace's node-ref set; ``None`` resolves it from the workbook.
    See :func:`node_ref_markers_for` for what the union costs — 99.1% false positives
    across the live store, on a check that REFUSES writes.
    """
    if markers is None:
        markers, _why = markers_for_workbook(workbook)
    index = ReferenceIndex()
    for sheet_name in workbook.names():
        doc = workbook.sheet(sheet_name)
        for row in doc.rows:
            head = _head(row.raw)
            if head is None:
                continue
            if _is_definition_head(head):
                node = as_text(head[2])
                # First definition wins (mirrors title_to_node.setdefault in the ingest resolver).
                index.defined.setdefault(node, DefinedNode(sheet=sheet_name, row=row.datum_address, node_addr=node))
            for slot, marker, value in _head_edges(head, markers):
                index.edges.append(
                    Edge(src_sheet=sheet_name, src_row=row.datum_address, slot=slot, marker=marker, target_node_addr=value)
                )
    return index


@dataclass(frozen=True)
class InboundReference:
    """One row, in some other document, that references a node address."""

    document_id: str
    document_name: str
    datum_address: str
    marker: str
    target_node_addr: str


def inbound_references(
    documents: Any,
    *,
    defined: set[str],
    exclude_document_id: str = "",
    limit: int = 0,
) -> tuple[int, list[InboundReference]]:
    """Rows that reference any address in ``defined``, excluding one document's own.

    The question a *deletion* has to answer and a rename does not. Renaming a document
    moves neither its node addresses nor its hash, so nothing that references it
    notices; deleting it removes the definitions outright, and
    :func:`~micyte.core.datum_ops.rules_loop.check_step` then reports every such row as
    a dangling ref and HARD-fails any workbook apply on that sandbox.

    Matching is exact, not by descent: ``defined`` is what this document itself
    defines, and a child address is somebody else's node.

    Returns ``(total, sample)`` — the count is complete even when ``limit`` truncates
    the sample, because "12 rows in 3 documents" is the number the operator decides on.
    """
    if not defined:
        return 0, []
    skip = as_text(exclude_document_id)
    total = 0
    sample: list[InboundReference] = []
    for document in documents:
        if as_text(getattr(document, "document_id", "")) == skip:
            continue
        for row in getattr(document, "rows", ()):
            head = _head(row.raw)
            if head is None:
                continue
            for _slot, marker, value in _head_edges(head):
                if value not in defined:
                    continue
                total += 1
                if limit and len(sample) >= limit:
                    continue
                sample.append(
                    InboundReference(
                        document_id=as_text(document.document_id),
                        document_name=as_text(getattr(document, "canonical_name", ""))
                        or as_text(getattr(document, "document_name", "")),
                        datum_address=as_text(row.datum_address),
                        marker=marker,
                        target_node_addr=value,
                    )
                )
    return total, sample
