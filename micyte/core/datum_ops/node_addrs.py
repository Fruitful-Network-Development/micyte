"""Variable-depth SAMRAS node-address algebra.

A *node address* (``4``, ``4-9``, ``1-3-2-5-1``) is a position in a SAMRAS tree
stored as a magnitude *value* inside a datum row's head — distinct from a *datum
address* (``4-2-17``), the 3-segment ``layer-value_group-iteration`` key of a row.
``packages/core/datum_semantics`` reorders datum addresses; this module
provides the parallel algebra for node addresses (parent/child, contiguous child
allocation, and the re-parent remap that rides descendants along).

Segment rules mirror :mod:`micyte.core.structures.samras.structure`:
every segment is a positive integer (no ordinal-0), so the SAMRAS codec's
contiguity/root constraints are preserved by construction.
"""

from __future__ import annotations

from micyte.core.structures.samras.structure import (
    as_text,
    format_address,
    parent_address,
    parse_address_segments,
)


def is_node_addr(token: object) -> bool:
    """True when ``token`` is a well-formed node address (positive hyphen tuple)."""
    text = as_text(token)
    if not text:
        return False
    try:
        parse_address_segments(text)
    except ValueError:
        return False
    return True


def parse_node_addr(addr: str) -> tuple[int, ...]:
    """Parse a node address into its positive-integer segments (raises on invalid)."""
    return parse_address_segments(addr)


def format_node_addr(segments: tuple[int, ...] | list[int]) -> str:
    return format_address(segments)


def parent_of(addr: str) -> str:
    """Return the parent node address, or ``""`` for a root."""
    return parent_address(addr)


def depth(addr: str) -> int:
    return len(parse_address_segments(addr))


def is_descendant(addr: str, ancestor: str) -> bool:
    """True when ``addr`` is strictly below ``ancestor`` in the tree."""
    a = as_text(addr)
    anc = as_text(ancestor)
    return bool(anc) and a != anc and a.startswith(anc + "-")


def direct_children(parent: str, nodes: set[str]) -> list[str]:
    """Direct children of ``parent`` present in ``nodes`` (``parent=""`` → roots)."""
    return sorted(
        (n for n in nodes if parent_of(n) == as_text(parent)),
        key=parse_address_segments,
    )


def child_ordinals(parent: str, nodes: set[str]) -> list[int]:
    """Trailing ordinals of ``parent``'s direct children, sorted ascending."""
    return sorted(parse_address_segments(child)[-1] for child in direct_children(parent, nodes))


def child_ordinals_contiguous(parent: str, nodes: set[str]) -> bool:
    """True when ``parent``'s direct child ordinals are ``1..N`` with no gaps."""
    ordinals = child_ordinals(parent, nodes)
    return ordinals == list(range(1, len(ordinals) + 1))


def next_child_ordinal(parent: str, nodes: set[str]) -> int:
    """Next contiguous child ordinal under ``parent`` (``max(children)+1``, else 1)."""
    ordinals = child_ordinals(parent, nodes)
    return (ordinals[-1] + 1) if ordinals else 1


def next_child(parent: str, nodes: set[str]) -> str:
    """The next contiguous child node address under ``parent``."""
    ordinal = next_child_ordinal(parent, nodes)
    parent_text = as_text(parent)
    return f"{parent_text}-{ordinal}" if parent_text else str(ordinal)


def remove_subtree_remap(node: str, nodes: set[str]) -> tuple[dict[str, str], set[str]]:
    """Compute the sibling-renumber remap for *removing* ``node`` (and its subtree).

    Mirrors the row-level iteration decrement in
    :func:`datum_semantics.preview_document_delete` but on tree node addresses:
    every later sibling of ``node`` under the same parent (and its descendants)
    shifts its ordinal down by one so the parent's children stay contiguous from 1
    — exactly the SAMRAS contiguity rule. Returns ``(remap, removed_subtree)``
    where ``remap`` maps surviving shifted nodes old → new and ``removed_subtree``
    is the set of addresses to delete.
    """
    node = as_text(node)
    if node not in nodes:
        raise ValueError(f"node not present: {node!r}")
    segs = parse_node_addr(node)
    parent_segs = segs[:-1]
    node_ord = segs[-1]
    depth_idx = len(parent_segs)  # position of the child-ordinal segment
    removed = {n for n in nodes if n == node or is_descendant(n, node)}
    remap: dict[str, str] = {}
    for n in nodes:
        if n in removed:
            continue
        nsegs = parse_node_addr(n)
        if len(nsegs) > depth_idx and tuple(nsegs[:depth_idx]) == parent_segs and nsegs[depth_idx] > node_ord:
            shifted = list(nsegs)
            shifted[depth_idx] = nsegs[depth_idx] - 1
            remap[n] = format_node_addr(shifted)
    return remap, removed


def relocate_subtree_remap(node: str, new_parent: str, nodes: set[str]) -> tuple[dict[str, str], str]:
    """Compute the full remap for *relocating* ``node`` to be a child of ``new_parent``.

    Two phases mirroring :func:`datum_semantics.preview_document_move`: first the
    old parent's later siblings shift down (removal), then ``node`` (with its
    descendants) is appended as the next contiguous child of ``new_parent``
    (computed against the post-removal node set). Returns ``(remap, new_node)``
    covering both the shifted survivors and the moved subtree.
    """
    node = as_text(node)
    new_parent = as_text(new_parent)
    removal_remap, removed = remove_subtree_remap(node, nodes)
    survivors: set[str] = set()
    for n in nodes:
        if n in removed:
            continue
        survivors.add(removal_remap.get(n, n))
    eff_new_parent = removal_remap.get(new_parent, new_parent)
    if eff_new_parent and eff_new_parent not in survivors:
        raise ValueError(f"new parent not present: {new_parent!r}")
    new_node = next_child(eff_new_parent, survivors)
    remap = dict(removal_remap)
    for n in removed:
        remap[n] = new_node + n[len(node):]
    return remap, new_node
