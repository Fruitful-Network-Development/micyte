"""Taxa Product Table — the Taxonomy Domain tab's right pane.

A grouped, collapsible, filterable table of ``agro_erp`` **product profiles**, grouped
and ordered by their ``taxonomy_id`` lineage in the ``taxonomy`` txa tree. The group
tree spans family → genus → species → cultivar-group, with the product profiles hanging
as leaves under their own taxon — so a whole species (``Capsicum annuum``) collapses at
once, while a cultivar-group node (``cabbage`` under ``Brassica oleracea``) collapses only
its own products. Common names lead (scientific as fallback); the produce icon is the
taxon's own or nearest-ancestor icon (same closest-parent rule as the tree). The renderer
adds per-facet filters (rotation group, propagule, genesis, ownership, raunkiaerality)
and a free-text search.

Pure payload builder (``container:"taxa_product_table"``); read-only across the agro_erp
(products + lcl) and taxonomy (txa) sandboxes — no MOS writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import cached_index
from micyte.core.datum_ops.node_addrs import parent_of
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .product_document_view import _find_named, build_product_rows
from .taxonomy_domain_viewer import (
    _MARK_COMMON,
    _MARK_ICON,
    _clade_icon_index,
    _marker_index,
    _pretty,
    _resolve_icon,
)

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.taxa_product_table.v1"
_TAXONOMY_SANDBOX = "taxonomy"
_ICON_PREFIX = "/assets/icons/"
# Root the visible group tree just below the universal life/domain roots (depth-2), so
# every product clusters under its full biological lineage (kingdom → … → species →
# cultivar-group). The rank ladder is uneven across branches (fungi products attach much
# shallower than plant cultivars), so a fixed family depth would leave many taxa ungrouped.
_ROOT_DEPTH = 2
# Facet fields the table filters on (resolved lcl labels).
_FACETS = ("rotation_group", "propagule", "genesis", "ownership", "raunkiaerality")


def _depth(addr: str) -> int:
    return len(addr.split("-")) if addr else 0


def _ancestors_from(addr: str, floor_depth: int) -> list[str]:
    """addr's ancestors-or-self with depth >= floor_depth, shallowest first."""
    chain: list[str] = []
    cur = addr
    while cur and _depth(cur) >= floor_depth:
        chain.append(cur)
        nxt = parent_of(cur)
        if nxt == cur:
            break
        cur = nxt
    chain.reverse()
    return chain


def _notice(msg: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "taxa_product_table", "notice": msg,
            "groups": [], "products": [], "facets": {}, "icon_url_prefix": _ICON_PREFIX}


class TaxaProductTable:
    """Grouped product-profile table keyed by txa lineage (Taxonomy Domain right pane)."""

    tool_id = "taxa_product_table"
    label = "Product Profiles"
    summary = "agro_erp product profiles grouped by taxonomy, with facet filters and search."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Embedded-only pane (composed into the Taxonomy Domain tab) — like network_map,
    # it is never independently eligible, so it stays out of the menubar palette.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _notice(err)
        # Honor the selected farm (agronomics FARM selector); a farm without a product_profiles
        # doc (e.g. a newly-onboarded farm) shows an empty notice rather than trapp's products.
        product_sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        product_doc = _find_named(docs, product_sandbox, "product_profiles")
        if product_doc is None:
            return _notice(f"No product profiles for {product_sandbox.replace('_', ' ').title()} yet.")
        lcl_index = cached_index(_find_named(docs, product_sandbox, "lcl"))
        agro_txa = cached_index(_find_named(docs, product_sandbox, "txa"))
        rows = build_product_rows(product_doc, lcl_index=lcl_index, txa_index=agro_txa)

        # taxonomy-sandbox txa: common names, produce icons (+ clade fallback), titles.
        txa_tax = find_named_document(docs, sandbox=_TAXONOMY_SANDBOX, name="txa")
        common = _marker_index(txa_tax, _MARK_COMMON)
        icons = {**_clade_icon_index(), **_marker_index(txa_tax, _MARK_ICON)}
        title_index = cached_index(txa_tax)

        def taxon_common(addr: str) -> str:
            return common.get(addr) or _pretty(title_index.resolve(addr)) or addr

        products: list[dict[str, Any]] = []
        group_addrs: set[str] = set()
        for r in rows:
            by_field = {f["field"]: f for f in r.get("fields", [])}
            taxon = _as_text((by_field.get("taxonomy_id") or {}).get("magnitude"))
            if not taxon:
                continue
            icon_ref, _inh = _resolve_icon(taxon, icons)
            facet_vals = {k: _as_text((by_field.get(k) or {}).get("resolved")) for k in _FACETS}
            name = _as_text(r.get("product_name")) or _as_text(r.get("datum_address"))
            search = " ".join([name, taxon_common(taxon), _as_text(title_index.resolve(taxon)),
                               *facet_vals.values()]).lower()
            gestation = _as_text((by_field.get("gestation") or {}).get("resolved"))
            products.append({
                "taxon": taxon,
                "name": name,
                # The lcl product-leaf node (1-1-5-*) — the join to inventory/contracts. The
                # Flora & Fauna "add" affordance passes this as inventory_new so the PLAN-tab
                # inventory manager opens with this product pre-queued.
                "product_node": _as_text((by_field.get("product_id") or {}).get("magnitude")),
                "subtitle": taxon_common(taxon),
                "common": taxon_common(taxon),
                "scientific": _as_text(title_index.resolve(taxon)),
                "icon_ref": icon_ref,
                "gestation": gestation,
                "spacing": _as_text((by_field.get("spacing") or {}).get("resolved")),
                "unit_weight": _as_text((by_field.get("singular_unit_weight") or {}).get("resolved")),
                "meta": [{"label": "rot", "value": facet_vals["rotation_group"]},
                         {"label": "prop", "value": facet_vals["propagule"]},
                         {"label": "gen", "value": facet_vals["genesis"]},
                         {"label": "own", "value": facet_vals["ownership"]},
                         {"label": "gest", "value": gestation}],
                "search": search,
                **facet_vals,
            })
            floor = min(_ROOT_DEPTH, _depth(taxon))
            group_addrs.update(_ancestors_from(taxon, floor))

        # group tree: displayed parent = nearest kept ancestor.
        parent_of_group: dict[str, str] = {}
        for addr in group_addrs:
            cur, parent = parent_of(addr), ""
            while cur:
                if cur in group_addrs:
                    parent = cur
                    break
                nxt = parent_of(cur)
                if nxt == cur:
                    break
                cur = nxt
            parent_of_group[addr] = parent
        direct = {a: 0 for a in group_addrs}
        subtree: dict[str, int] = {}     # products at this taxon or any descendant
        for p in products:
            if p["taxon"] in direct:
                direct[p["taxon"]] += 1
            cur = p["taxon"]
            while cur:
                subtree[cur] = subtree.get(cur, 0) + 1
                nxt = parent_of(cur)
                if nxt == cur:
                    break
                cur = nxt
        # Trim pass-through clade nodes (0 direct products, exactly 1 child group) so the
        # visible tree starts at real branch points (families/genera) not the long
        # kingdom→…→angiosperm single-child chain. Iterate until stable.
        kept = set(group_addrs)
        changed = True
        while changed:
            changed = False
            children: dict[str, list[str]] = {}
            for a in kept:
                children.setdefault(parent_of_group[a], []).append(a)
            for a in list(kept):
                if direct.get(a, 0) == 0 and len(children.get(a, [])) == 1:
                    child = children[a][0]
                    parent_of_group[child] = parent_of_group[a]  # splice out
                    kept.discard(a)
                    changed = True
                    break
        groups = []
        for addr in sorted(kept, key=lambda a: [int(s) if s.isdigit() else s for s in a.split("-")]):
            g_icon, _gi = _resolve_icon(addr, icons)
            pcount = subtree.get(addr, 0)
            groups.append({
                "addr": addr,
                "parent": parent_of_group[addr],
                "depth": _depth(addr),
                "label": taxon_common(addr),
                "scientific": _as_text(title_index.resolve(addr)),
                "icon_ref": g_icon,
                "product_count": pcount,
            })

        products.sort(key=lambda p: ([int(s) if s.isdigit() else s for s in p["taxon"].split("-")], p["name"]))
        facets = {k: sorted({p[k] for p in products if p[k]}) for k in _FACETS}
        return {
            "schema": _SCHEMA,
            "container": "taxa_product_table",
            "sandbox_id": product_sandbox,
            "title": "Product profiles",
            "count_label": f"{len(products)} products · {len(groups)} taxa",
            "icon_url_prefix": _ICON_PREFIX,
            "groups": groups,
            "products": products,
            "facets": facets,
            "facet_fields": list(_FACETS),
        }


# Self-register on import.
register(TaxaProductTable())
