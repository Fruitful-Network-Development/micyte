"""Taxonomy Domain — the txa biological-taxonomy id-space with produce icons.

A development of the ``samras_structure`` viewer (like ``local_domain``), specialized to
the **txa** SAMRAS structure held in the dedicated ``taxonomy`` sandbox. It reuses the
shared discovery + :func:`build_magnitude_tree` machinery, then overlays two things the
plain SAMRAS browse view does not carry:

* **common name** (``rf.3-1-9``) — a human-facing label shown beside the scientific title;
* **icon_ref** (``rf.3-1-10``) — a produce/crop-family icon leaflet, resolved with a
  *closest-ancestor* fallback: a node with no icon of its own inherits the nearest ancestor
  that has one (so every "russet potato" cultivar shows the potato icon, and any brassica
  without a species icon shows the ``brassicas`` family icon).

The scientific (Latin) name is the node's ``rf.3-1-2`` title — already present on every txa
node — so "scientific names alongside the txa_id" needs no new field there. The two extra
babelette pairs ride on the same ``4-2-N`` definition rows (safe: the taxonomy/lcl row shape
is not validated for pair-count — cf. the lcl ``rf.3-1-8`` VIEW precedent).

If the ``taxonomy`` sandbox is not yet provisioned the tool renders a friendly notice rather
than erroring, so the tab is safe to ship ahead of the MOS bootstrap.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label, iter_marker_pairs
from micyte.core.datum_ops.node_addrs import parent_of
from micyte.core.instances import default_farm_sandbox
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import find_named_document, read_sandbox_catalog
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from .samras_structure_viewer import build_magnitude_tree, discover_samras_structures

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.taxonomy_domain.v1"
_SANDBOX = "taxonomy"
_STRUCTURE = "txa"
_PRODUCT_DOC = "product_profiles"

# New taxonomy-sandbox babelettes (extend the agro_erp txa vocab).
_MARK_COMMON = "rf.3-1-9"    # common_name (ASCII label)
_MARK_ICON = "rf.3-1-10"     # icon_ref (bare icon-leaflet stem)
_MARK_TAXON = "rf.3-1-1"     # product_profiles: taxonomy_id (a txa node address)

_ICON_PREFIX = "/assets/icons/"
# On-disk store of the mycite-txa CLADE icons (filename encodes the txa node
# address), scanned read-only to layer clade icons under the per-node rf.3-1-10
# bindings as an ancestor source. The location is deployment-specific, so it is
# read from MICYTE_ICON_DIR; unset means "no clade-icon overlay" (the per-node
# bindings still render), which is the standalone default.
_ICON_DISK_DIR = Path(os.environ.get("MICYTE_ICON_DIR", ""))


def _clade_icon_index() -> dict[str, str]:
    """txa node address -> mycite-txa icon asset stem, parsed from filenames like
    ``0000-00-00.artifact-icon.mycite-txa.1-1-3-5-6-monocots.svg`` (address = the
    leading numeric segments; the trailing word(s) are the label)."""
    out: dict[str, str] = {}
    if not os.environ.get("MICYTE_ICON_DIR"):
        return out  # no clade-icon dir configured (Path("") would glob the CWD)
    try:
        paths = _ICON_DISK_DIR.glob("*.artifact-icon.mycite-txa.*.svg")
    except OSError:
        return out
    for p in paths:
        stem = p.name[:-4]
        tail = stem.split(".mycite-txa.", 1)[-1]
        segs = tail.split("-")
        addr = []
        for s in segs:
            if s.isdigit():
                addr.append(s)
            else:
                break
        if addr:
            out["-".join(addr)] = stem
    return out


def _crop_profile_expand_to(docs: Any, product_sandbox: str) -> list[str]:
    """The txa nodes to keep expanded on open: every proper ancestor on a path down to
    a taxon that carries a product profile (product_profiles.taxonomy_id).

    ``product_sandbox`` is the instance being viewed. This used to read one farm
    named in code regardless of it, so every instance opened the tree down to that
    farm's crops."""
    if not product_sandbox:
        return []
    product = find_named_document(docs, sandbox=product_sandbox, name=_PRODUCT_DOC)
    if product is None:
        return []
    bearing: set[str] = set()
    for row in getattr(product, "rows", ()) or ():
        for _m, addr in iter_marker_pairs(_row_head(row)):
            if _m == _MARK_TAXON:
                a = _as_text(addr).strip()
                if a:
                    bearing.add(a)
                break
    keep: set[str] = set()
    for node in bearing:
        cur = parent_of(node)
        while cur:
            keep.add(cur)
            nxt = parent_of(cur)
            if nxt == cur:
                break
            cur = nxt
    return sorted(keep)


def _product_sandbox(docs: Any, extra_query: dict[str, Any] | None) -> str:
    """The FARM whose product_profiles gate the tree's crop-expansion.

    Agronomics passes the active farm as ``product_sandbox`` (already resolved and
    validated — possibly "" when it failed closed). Invoked standalone (no such
    key), default to the first discovered farm. Never the ``taxonomy`` sandbox
    itself, which holds the tree but carries no product_profiles."""
    eq = extra_query or {}
    if "product_sandbox" in eq:
        return _as_text(eq.get("product_sandbox"))
    return default_farm_sandbox(docs) or ""


def _notice(message: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "container": "taxonomy_dendro",
        "notice": message,
        "denoted_count": 0,
        "defined_count": 0,
        "nodes": [],
        "icon_url_prefix": _ICON_PREFIX,
    }


def _marker_index(document: Any, marker: str) -> dict[str, str]:
    """node_address -> decoded ASCII value for ``marker`` across a doc's definition rows.

    Mirrors :func:`datum_resolve.view_token_index` but for an arbitrary ``rf.3-1-N``
    marker (here common_name / icon_ref), robust to extra head pairs and prefix family.
    """
    out: dict[str, str] = {}
    if document is None:
        return out
    for row in getattr(document, "rows", ()) or ():
        head = _row_head(row)
        if len(head) < 3:
            continue
        node = _as_text(head[2])
        if not node:
            continue
        for m, magnitude in iter_marker_pairs(head):
            if m == marker:
                val = decode_label(magnitude).strip()
                if val:
                    out[node] = val
                break
    return out


def _resolve_icon(addr: str, own: dict[str, str]) -> tuple[str, bool]:
    """(icon_ref, inherited) — the node's own icon, else the nearest ancestor's."""
    if addr in own:
        return own[addr], False
    cur = parent_of(addr)
    while cur:
        if cur in own:
            return own[cur], True
        nxt = parent_of(cur)
        if nxt == cur:
            break
        cur = nxt
    return "", False


def _pretty(title: str) -> str:
    """Fallback display name from a scientific slug (``lens_esculenta`` -> ``Lens esculenta``)."""
    t = _as_text(title).replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else ""


class TaxonomyDomainViewer:
    """The txa taxonomy cluster graph with produce icons + common names (taxonomy sandbox)."""

    tool_id = "taxonomy_domain"
    label = "Taxonomy Domain"
    summary = (
        "The txa biological-taxonomy id-space (taxonomy sandbox) as a cluster graph — "
        "scientific + common names with produce icons and closest-parent icon fallback."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = (
        "samras_taxonomy",
        "agro_erp_taxonomy_row",
        "mycite.v2.datum.agro_erp.taxonomy_source.v1",
    )
    applies_to_source_kind: tuple[str, ...] = ()
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
            return _notice(err)
        anchor = find_named_document(docs, sandbox=_SANDBOX, name="anchor")
        if anchor is None:
            return _notice(
                "The taxonomy sandbox is not provisioned yet. Run "
                "scripts/bootstrap_taxonomy_anchor.py to create it."
            )
        txa = find_named_document(docs, sandbox=_SANDBOX, name=_STRUCTURE)
        structures = discover_samras_structures(anchor)
        match = next((s for s in structures if s["name"] == _STRUCTURE), None)
        if match is None:
            return _notice("No txa structure denoted by the taxonomy anchor.")

        built = build_magnitude_tree(anchor, match["magnitude_addr"], txa)
        if built is None:
            return _notice("The txa magnitude is missing or undecodable.")

        common = _marker_index(txa, _MARK_COMMON)
        own_icon = _marker_index(txa, _MARK_ICON)
        # Layer the mycite-txa CLADE icons UNDER the per-node bindings (own wins), so
        # kingdom/phylum/clade nodes gain an icon and descendants inherit it via the
        # closest-parent fallback.
        icons = {**_clade_icon_index(), **own_icon}

        nodes: list[dict[str, Any]] = []
        iconed = 0
        for n in built["nodes"]:
            addr = _as_text(n.get("full_slug"))
            sci = _as_text(n.get("label"))
            icon_ref, inherited = _resolve_icon(addr, icons)
            if icon_ref:
                iconed += 1
            display = common.get(addr) or _pretty(sci) or addr
            nodes.append({
                **n,
                "label": display,             # common name leads the node
                "scientific_name": sci,       # Latin binomial subtitle
                "common_name": common.get(addr, ""),
                "icon_ref": icon_ref,         # own or inherited (closest-parent fallback)
                "icon_inherited": inherited,
            })

        denoted, defined = built["denoted"], built["defined"]
        return {
            "schema": _SCHEMA,
            "container": "taxonomy_dendro",
            "sandbox_id": _SANDBOX,
            "document_id": _as_text(getattr(txa, "document_id", "")),
            "structure": _STRUCTURE,
            "orientation": "vertical",             # root-on-top SAMRAS view
            "expand_to": _crop_profile_expand_to(docs, _product_sandbox(docs, extra_query)),
            "has_titles": txa is not None,
            "denoted_count": len(denoted),
            "defined_count": len(defined & denoted),
            "empty_count": len(denoted - defined),
            "iconed_count": iconed,
            "icon_url_prefix": _ICON_PREFIX,
            "nodes": nodes,
        }


# Self-register on import.
register(TaxonomyDomainViewer())
