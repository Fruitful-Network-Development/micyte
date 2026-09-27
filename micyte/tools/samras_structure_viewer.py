"""Unified SAMRAS structure viewer — one tool for every node-address SAMRAS structure.

An anchor carries several "structured magnitudes" that each denote a set of SAMRAS node
addresses and pair with a definition document giving every node an ASCII title —
``txa-SAMRAS``, ``msn-SAMRAS``, ``lcl-SAMRAS``, and whatever else a sandbox holds (the
registrar has a ``ruiqi-SAMRAS`` too). **Which row holds which is discovered, not fixed by
address:** a farm anchor keeps lcl at ``1-1-5`` while the registrar keeps it at ``1-1-6``
with ``HOPS-chornological`` sitting at ``1-1-5``. This single tool renders any one of them
— chosen via ``surface_query["samras_structure"]`` (an in-panel ``<select>`` on the client)
— through the shared, structure-agnostic :func:`build_magnitude_tree`. It replaces the
former per-structure ``txa_tree`` / ``lcl_structure`` tools; any future "nodes + ASCII
titles" SAMRAS structure appears automatically with no new code.

The HOPS magnitudes (``HOPS-spatial`` / ``HOPS-chronological``) are a different shape and
are excluded — only ``*-SAMRAS`` node trees are listed. A structure with no matching
definition document (e.g. ``msn`` today) renders structure-only (blank labels) — the
builder degrades gracefully.

The payload reports FOUR counts, not three: ``denoted`` (in the structure), ``defined`` (in
the structure and in the document), ``empty`` (in the structure, undefined) and
``undenoted`` (defined but absent from the structure — a stale magnitude). The last is the
one that can make a tree quietly smaller than its corpus.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    NODE_KIND_UNMARKED,
    cached_index,
    node_kind_index,
    view_token_index,
)
from micyte.core.datum_ops.node_addrs import parent_of, parse_node_addr
from micyte.core.datum_ops.refs import defined_node_addrs
from micyte.core.datum_ops.samras_deps import check_denotation
from micyte.core.datum_ops.samras_deps import (
    discover_samras_structures as core_discover_samras_structures,
)
from micyte.core.structures.samras.codec import decode_canonical_bitstream
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import find_anchor, find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.samras_structure.v1"


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
        "undenoted_count": 0,
        "undenoted_nodes": [],
        "nodes": [],
    }


def discover_samras_structures(anchor: Any) -> list[dict[str, str]]:
    """Every node-address SAMRAS structure the anchor denotes, in address order.

    A structure is an anchor row whose tail label ends in ``-SAMRAS`` and whose magnitude
    (``head[2]``) is a non-empty binary bitstream. ``name`` is the label minus the suffix
    (``txa`` / ``msn`` / ``lcl``). HOPS magnitudes (label ``HOPS-*``) are excluded because
    they do not end in ``-SAMRAS``. Cheap by design (no decode) — the chosen structure's
    bitstream is decoded once, later, in :func:`build_magnitude_tree`.

    The rule itself now lives in :mod:`micyte.core.datum_ops.samras_deps`, because the
    migration planner and the denotation checker need the same answer this tool needed —
    and the alternative was a hardcoded per-sandbox address map, which is precisely how the
    registrar's stale anchor went unnoticed. This keeps the dict shape its callers use.
    """
    return [{"name": ref.name, "magnitude_addr": ref.magnitude_addr}
            for ref in core_discover_samras_structures(anchor)]


def build_magnitude_tree(
    anchor: Any, magnitude_addr: str, defining_doc: Any
) -> dict[str, Any] | None:
    """Decode the anchor magnitude at ``magnitude_addr`` and overlay which of its
    denoted node addresses are DEFINED in ``defining_doc``.

    Returns ``{denoted, defined, undenoted, nodes}`` (sets + a flat cluster-dendrogram node
    list) or ``None`` when the magnitude row is missing/undecodable. Structure-agnostic — the
    same builder serves txa / msn / lcl (and any future ``*-SAMRAS`` node structure).
    ``defining_doc=None`` is valid: nodes render with blank labels (structure-only).

    ``undenoted`` is ``defined - denoted``: nodes the document defines that the magnitude
    does not carry. It is the missing half of a pair this builder already modelled from one
    side — a *denoted-but-undefined* node has always rendered as an ``empty`` placeholder,
    while a *defined-but-undenoted* one could not appear at all, because the node list is
    built by iterating ``denoted``. That asymmetry is why the registrar tree showed 53 of its
    lcl's 66 nodes with nothing anywhere saying so. Reported as ``{node, label}`` rather than
    bare addresses: an address alone cannot tell an operator what went missing.
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
    # What each node IS — a type (a definition other nodes hang off) or an instance (a
    # record). Read from the marker its address already rides; see `node_kind_index`. NOT
    # empty for txa, which carries every node on the type marker and so reads as types
    # throughout (correctly — a taxon is a definition, and it stays inert because txa has no
    # VIEW markers). Empty for msn. The samras renderer ignores this key either way.
    kinds = node_kind_index(defining_doc)

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
                # "type" | "instance" | "unmarked" — which VERB this node can offer an
                # editor. Deliberately not defaulted to "type": a node the corpus has not
                # classified is one a human still has to look at, not one to mint under.
                "node_kind": kinds.get(addr, NODE_KIND_UNMARKED),
            }
        )
    undenoted = [
        {"node": addr, "label": (labels.resolve(addr) if labels is not None else "") or ""}
        for addr in sorted(defined - denoted, key=parse_node_addr)
    ]
    return {"denoted": denoted, "defined": defined, "undenoted": undenoted, "nodes": nodes}


def _defining_document(docs: Any, *, sandbox: str, structure: str) -> Any:
    """The document whose rows NAME the nodes of ``structure``, or ``None``.

    A structure's name comes from the anchor row's label minus ``-SAMRAS`` — ``txa``,
    ``msn``, ``lcl`` — and for txa and msn that is also what the document is called. It is
    NOT for the local domain: the structure is still ``lcl`` and the document became
    ``lcl_domain`` on 2026-08-20.

    Found by SCREENSHOT, which is the only thing that could have found it: the tree drew
    every node, at the right address, with the right preview and the right slot stamp, and
    every single label read ``(undefined)``. Nothing raised, because a defining document is
    legitimately absent for a structure-only tree — the one case this lookup was written to
    tolerate is the case a rename turns it into.
    """
    from micyte.core.instance_baseline import LCL_DOCUMENT, LOCAL_DOMAIN_NAMES

    found = find_named_document(docs, sandbox=sandbox, name=structure)
    if found is not None:
        return found
    # The local domain's structure keeps the old spelling in the anchor's own row, and
    # re-labelling that row would be re-cutting the magnitude for a cosmetic reason.
    if structure in LOCAL_DOMAIN_NAMES or structure == LCL_DOCUMENT:
        for name in LOCAL_DOMAIN_NAMES:
            found = find_named_document(docs, sandbox=sandbox, name=name)
            if found is not None:
                return found
    return None


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
        # ONE sandbox when the request names it; the whole catalog only for the blank
        # request the resolver answers with the first farm by shape (2026-09-25).
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT, sandbox=_as_text(sandbox_id))
        if err:
            return _error(err)
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return _error("no sandbox specified")
        anchor = find_anchor(docs, sandbox=sandbox)
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
            defining = _defining_document(docs, sandbox=sandbox, structure=s["name"])
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
        # WHY the structure is short, when it is — asked of the same checker a gate would use,
        # so the tree and the check can never give an operator different answers. Only the
        # SELECTED structure's sheet is passed, so the others resolve as `unpaired` without
        # paying an encode; and this runs at all only when something is actually missing.
        gap_status, gap_reason = "", ""
        if built["undenoted"]:
            for finding in check_denotation(anchor, {selected: defining}, sandbox=sandbox):
                if finding.structure == selected:
                    gap_status, gap_reason = finding.status, finding.detail
                    break
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
            # The fourth number: definitions this structure does NOT carry, so the tree can
            # say "showing 53 of 66" instead of implying the corpus holds 53.
            "undenoted_count": len(built["undenoted"]),
            "undenoted_nodes": built["undenoted"],
            "undenoted_status": gap_status,
            "undenoted_reason": gap_reason,
            "nodes": built["nodes"],
        }


# Self-register on import.
register(SamrasStructureViewer())
