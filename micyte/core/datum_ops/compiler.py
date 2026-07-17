"""Compile an edited WORKBOOK into an ordered, rule-checked op sequence.

Diffs an edited :class:`Workbook` against its baseline and infers the rudimentary
ops that transform one into the other, so the UI can hand back edited YAML without
knowing the op grammar. Node-definition identity is tracked by **title** (a moved
node keeps its title; its address changes), which lets relocate/mint/drop/rename be
distinguished. When a sheet's node set changes, the housekeeping ops
(:class:`RecompileMagnitude` + :class:`RebuildCollection`) are appended so the
SAMRAS magnitude and the id-collection stay consistent — exactly the order
:func:`migrate.plan_migration` expects.

Scope: definition-structure edits (relocate / mint / drop / rename) and the
housekeeping cascade. Pure reference re-points without a node move are expressed by
the explicit :class:`RewriteRefs` / :class:`RepointNode` primitives, not inferred.
"""

from __future__ import annotations

from typing import Any

from . import node_addrs as na
from .node_ops import (
    DropNode,
    MintNode,
    RebuildCollection,
    RecompileMagnitude,
    RelocateNode,
    RenameNode,
)
from .ops import Workbook
from .refs import _head, _is_definition_head
from .samras_deps import ANCHOR_SAMRAS_SOURCE, TXA_ID_COLLECTION

# sheet → (anchor magnitude address, collection address) housekeeping mapping,
# derived from the single anchor→sheet source map (no independent restatement).
_HOUSEKEEPING = {sheet: (anchor_addr, TXA_ID_COLLECTION) for anchor_addr, sheet in ANCHOR_SAMRAS_SOURCE.items()}


def _def_title_map(doc: Any) -> dict[str, str]:
    """node_addr → title for every definition row in a sheet."""
    out: dict[str, str] = {}
    for row in doc.rows:
        head = _head(row.raw)
        if head is not None and _is_definition_head(head):
            title = str(row.raw[1][0]) if len(row.raw) > 1 and row.raw[1] else ""
            out[str(head[2])] = title
    return out


def compile_workbook(baseline: Workbook, edited: Workbook) -> list[Any]:
    """Infer the op sequence that turns ``baseline`` into ``edited``."""
    ops: list[Any] = []
    housekeeping: list[tuple[str, str, str]] = []  # (sheet, anchor_addr, collection_addr)

    for name in edited.names():
        if name not in baseline.sheets:
            continue
        before = _def_title_map(baseline.sheet(name))
        after = _def_title_map(edited.sheet(name))
        after_by_title = {t: n for n, t in after.items()}

        removed = {n: t for n, t in before.items() if n not in after}
        added = {n: t for n, t in after.items() if n not in before}
        node_set_changed = False

        # relocate: same title, address changed (matched between removed & added)
        relocated_added: set[str] = set()
        for b_node, title in sorted(removed.items(), key=lambda kv: na.parse_node_addr(kv[0]), reverse=True):
            e_node = after_by_title.get(title)
            if e_node is not None and e_node in added:
                ops.append(RelocateNode(name, b_node, na.parent_of(e_node)))
                relocated_added.add(e_node)
                node_set_changed = True

        # rename: same address, title changed
        for node in sorted(set(before) & set(after), key=na.parse_node_addr):
            if before[node] != after[node]:
                ops.append(RenameNode(name, node, after[node]))

        # mint: new title not explained by a relocate (parents first)
        for e_node, title in sorted(added.items(), key=lambda kv: na.depth(kv[0])):
            if e_node in relocated_added:
                continue
            ops.append(MintNode(name, e_node, title))
            node_set_changed = True

        # drop: removed title with no relocate match (descending ordinal → trailing-child)
        for b_node, title in sorted(removed.items(), key=lambda kv: na.parse_node_addr(kv[0]), reverse=True):
            if after_by_title.get(title) in added:
                continue
            ops.append(DropNode(name, b_node))
            node_set_changed = True

        if node_set_changed and name in _HOUSEKEEPING:
            anchor_addr, collection_addr = _HOUSEKEEPING[name]
            housekeeping.append((name, anchor_addr, collection_addr))

    for name, anchor_addr, collection_addr in housekeeping:
        if "anchor" in edited.names():
            ops.append(RecompileMagnitude("anchor", anchor_addr, name))
        label = _collection_label(edited.sheet(name), collection_addr)
        if label is not None:
            ops.append(RebuildCollection(name, collection_addr, label))

    return ops


def _collection_label(doc: Any, collection_address: str) -> str | None:
    for row in doc.rows:
        if row.datum_address == collection_address and len(row.raw) > 1 and row.raw[1]:
            return str(row.raw[1][0])
    return None
