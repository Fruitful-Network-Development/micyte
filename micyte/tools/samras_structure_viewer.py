"""Unified SAMRAS structure viewer — one tool for every node-address SAMRAS structure.

The agro_erp anchor carries several "structured magnitudes" that each denote a set of
SAMRAS node addresses and pair with a definition document giving every node an ASCII
title: ``txa-SAMRAS`` (anchor row ``1-1-1``), ``msn-SAMRAS`` (``1-1-4``), ``lcl-SAMRAS``
(``1-1-5``). This single tool DISCOVERS those structures from the anchor and renders any
one of them — chosen via ``surface_query["samras_structure"]`` (an in-panel ``<select>``
on the client) — through the shared, structure-agnostic :func:`build_magnitude_tree`. It
replaces the former per-structure ``txa_tree`` / ``lcl_structure`` tools; any future
"nodes + ASCII titles" SAMRAS structure appears automatically with no new code.

The HOPS magnitudes (``HOPS-spatial`` / ``HOPS-chronological``) are a different shape and
are excluded — only ``*-SAMRAS`` node trees are listed. A structure with no matching
definition document (e.g. ``msn`` today) renders structure-only (blank labels) — the
builder degrades gracefully.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import cached_index, view_token_index
from micyte.core.datum_ops.node_addrs import parent_of, parse_node_addr
from micyte.core.datum_ops.refs import defined_node_addrs
from micyte.core.structures.samras.codec import decode_canonical_bitstream
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.samras_structure.v1"
_SAMRAS_SUFFIX = "-SAMRAS"


def _error(
    message: str,
    *,
    structures: list[dict[str, Any]] | None = None,
    selected: str = "",
) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "error": message,
        "structure": selected,
        "magnitude": selected,
        "structures": structures or [],
        "has_titles": False,
        "denoted_count": 0,
        "defined_count": 0,
        "empty_count": 0,
        "nodes": [],
    }


def _addr_key(addr: str) -> tuple[int, ...]:
    """Sort key for a datum address like ``1-1-5`` (segment-wise, numeric)."""
    out: list[int] = []
    for seg in _as_text(addr).split("-"):
        try:
            out.append(int(seg))
        except ValueError:
            out.append(0)
    return tuple(out)


def discover_samras_structures(anchor: Any) -> list[dict[str, str]]:
    """Every node-address SAMRAS structure the anchor denotes, in address order.

    A structure is an anchor row whose tail label ends in ``-SAMRAS`` and whose magnitude
    (``head[2]``) is a non-empty binary bitstream. ``name`` is the label minus the suffix
    (``txa`` / ``msn`` / ``lcl``). HOPS magnitudes (label ``HOPS-*``) are excluded because
    they do not end in ``-SAMRAS``. Cheap by design (no decode) — the chosen structure's
    bitstream is decoded once, later, in :func:`build_magnitude_tree`.
    """
    out: list[dict[str, str]] = []
    for row in getattr(anchor, "rows", ()) or []:
        label = _row_tail_label(row)
        if not label.endswith(_SAMRAS_SUFFIX):
            continue
        head = _row_head(row)
        bitstream = _as_text(head[2]) if len(head) > 2 else ""
        if not bitstream or any(bit not in "01" for bit in bitstream):
            continue
        out.append(
            {
                "name": label[: -len(_SAMRAS_SUFFIX)],
                "magnitude_addr": _as_text(row.datum_address),
            }
        )
    out.sort(key=lambda s: _addr_key(s["magnitude_addr"]))
    return out


def build_magnitude_tree(
    anchor: Any, magnitude_addr: str, defining_doc: Any
) -> dict[str, Any] | None:
    """Decode the anchor magnitude at ``magnitude_addr`` and overlay which of its
    denoted node addresses are DEFINED in ``defining_doc``.

    Returns ``{denoted, defined, nodes}`` (sets + a flat cluster-dendrogram node list)
    or ``None`` when the magnitude row is missing/undecodable. Structure-agnostic — the
    same builder serves txa / msn / lcl (and any future ``*-SAMRAS`` node structure).
    ``defining_doc=None`` is valid: nodes render with blank labels (structure-only).
    """
    magnitude_row = next(
        (r for r in (getattr(anchor, "rows", ()) or []) if _as_text(r.datum_address) == magnitude_addr),
        None,
    )
    if magnitude_row is None:
        return None
    head = _row_head(magnitude_row)
    bitstream = _as_text(head[2]) if len(head) > 2 else ""
    if not bitstream:
        return None
    try:
        structure = decode_canonical_bitstream(bitstream)
    except Exception:
        return None

    denoted: set[str] = set(structure.addresses)
    defined: set[str] = defined_node_addrs(defining_doc) if defining_doc is not None else set()
    labels = cached_index(defining_doc) if defining_doc is not None else None
    # Per-node record-view tokens (rf.3-1-8 VIEW markers): which nodes are instance
    # containers the local_domain tool can expand into a record table. Empty for txa/msn
    # and for any structure with no VIEW markers — so the samras viewer is unaffected.
    views = view_token_index(defining_doc)

    # has_children in ONE O(N) parent-bucket pass (the old per-node direct_children scan
    # was O(N^2) — ~70s on the 4670-node lcl structure; this is ~0.06s).
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for node_addr in denoted:
        children_by_parent[parent_of(node_addr)].append(node_addr)

    # Flat node list in the cluster-dendrogram shape (clusterLayout consumes
    # full_slug / parent_slug / depth / has_children) + the resolved label and
    # defined-vs-empty status. Address-sorted so each parent's children land in
    # address order in the diagram. This is the SAME diagram the Resource type
    # browser uses (.v2-dendro / clusterLayout) — reused for the SAMRAS id-space.
    nodes: list[dict[str, Any]] = []
    for addr in sorted(denoted, key=parse_node_addr):
        parent = parent_of(addr)
        nodes.append(
            {
                "full_slug": addr,
                "parent_slug": parent if parent in denoted else "",
                "depth": len(parse_node_addr(addr)) - 1,
                "has_children": bool(children_by_parent.get(addr)),
                # Direct child count — the SAMRAS analog of the Resource browser's
                # per-type instance count; rendered as the node's pill badge. Reuses
                # the children_by_parent bucket built above (no extra pass).
                "count": len(children_by_parent.get(addr, ())),
                "label": (labels.resolve(addr) if labels is not None else "") or "",
                "status": "defined" if addr in defined else "empty",
                # Record-view token (e.g. "product"/"invoice") when this node is an
                # instance container; "" otherwise. The samras renderer ignores it; the
                # local_domain renderer turns it into an expand-to-table button.
                "record_view": views.get(addr, ""),
            }
        )
    return {"denoted": denoted, "defined": defined, "nodes": nodes}


class SamrasStructureViewer:
    """Render any anchor-denoted SAMRAS node structure (txa / msn / lcl), selectable."""

    tool_id = "samras_structure"
    label = "SAMRAS Structure"
    summary = (
        "Node-address structure tree (txa / msn / lcl) — defined nodes vs empty "
        "(denoted-but-undefined) placeholders. Switch structures in the panel."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    # Surfaces in the taxonomy context: the lcl/txa docs are recognized structurally as
    # `samras_taxonomy` (4-2-N titled-definition rows). The legacy archetype tokens stay
    # for back-compat with lcl's stamped metadata. The tool resolves anchor + each
    # structure's defining doc BY NAME, independent of the selected document.
    applies_to_archetype: tuple[str, ...] = (
        "samras_taxonomy",
        "agro_erp_taxonomy_row",
        "mycite.v2.datum.agro_erp.taxonomy_source.v1",
    )
    applies_to_source_kind: tuple[str, ...] = ()
    # Opt in to receiving the surface_query so the panel <select> can pick the structure.
    wants_surface_query = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _error(err)
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return _error("no sandbox specified")
        anchor = find_named_document(docs, sandbox=sandbox, name="anchor")
        if anchor is None:
            return _error("anchor document not found")

        structures = discover_samras_structures(anchor)
        if not structures:
            return _error("no SAMRAS structures denoted by the anchor")

        # Resolve each structure's defining doc BY NAME (collision-safe: txa & lcl both
        # match samras_taxonomy, so an archetype resolve would pick the wrong one).
        by_name: dict[str, tuple[str, Any]] = {}
        struct_meta: list[dict[str, Any]] = []
        for s in structures:
            defining = find_named_document(docs, sandbox=sandbox, name=s["name"])
            by_name[s["name"]] = (s["magnitude_addr"], defining)
            struct_meta.append({"name": s["name"], "has_titles": defining is not None})

        requested = _as_text((extra_query or {}).get("samras_structure"))
        selected = requested if requested in by_name else structures[0]["name"]
        magnitude_addr, defining = by_name[selected]

        built = build_magnitude_tree(anchor, magnitude_addr, defining)
        if built is None:
            return _error(
                f"{selected} magnitude ({magnitude_addr}) missing or undecodable",
                structures=struct_meta,
                selected=selected,
            )

        denoted, defined = built["denoted"], built["defined"]
        return {
            "schema": _SCHEMA,
            "sandbox_id": sandbox,
            "document_id": _as_text(getattr(defining, "document_id", "")),
            "selected_row_address": _as_text(datum_address),
            "structure": selected,
            # `magnitude` kept for the renderer header ("<name> structure · N denoted …").
            "magnitude": selected,
            "has_titles": defining is not None,
            "structures": struct_meta,
            "denoted_count": len(denoted),
            "defined_count": len(defined & denoted),
            "empty_count": len(denoted - defined),
            "nodes": built["nodes"],
        }


# Self-register on import.
register(SamrasStructureViewer())
