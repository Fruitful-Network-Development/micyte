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
NODE_REF_MARKERS = frozenset({"rf.3-1-1", "rf.3-1-5", "rf.3-1-13"})


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


def build_reference_index(workbook: Workbook) -> ReferenceIndex:
    """Walk every sheet/row, recording defined nodes and cross-reference edges."""
    index = ReferenceIndex()
    for sheet_name in workbook.names():
        doc = workbook.sheet(sheet_name)
        for row in doc.rows:
            head = _head(row.raw)
            if head is None:
                continue
            definition = _is_definition_head(head)
            if definition:
                node = as_text(head[2])
                # First definition wins (mirrors title_to_node.setdefault in the ingest resolver).
                index.defined.setdefault(node, DefinedNode(sheet=sheet_name, row=row.datum_address, node_addr=node))
            # Walk pairs: (marker @ i, magnitude @ i+1) for odd i.
            for i in range(1, len(head) - 1, 2):
                if definition and i == 1:
                    continue  # the id-pair defines this row's node; not an outbound edge
                marker = as_text(head[i])
                value = as_text(head[i + 1])
                if is_node_ref_marker(marker) and is_node_addr_reference(value):
                    index.edges.append(
                        Edge(src_sheet=sheet_name, src_row=row.datum_address, slot=i + 1, marker=marker, target_node_addr=value)
                    )
    return index
