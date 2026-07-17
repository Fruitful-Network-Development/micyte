"""Agronomics — the portal's primary tool: FARM / PLAN / NETWORK tabs.

Renders a ``container:"tabbed"`` payload. The FARM tab is a COMPOSITE of two existing
single-purpose viewers laid out side by side; PLAN and NETWORK are blank scaffolds that
future agronomics sub-component tools slot into:

    ┌─ Agronomics ──[ FARM ][ PLAN ][ NETWORK ]──┐
    │  Farm Profile (map)   │  LCL ID Space (tree) │   ← FARM tab
    └────────────────────────────────────────────┘

Each pane is just another tool's panel_payload, carried under a generic ``container:
"composite"`` payload that the client's composite renderer lays out and delegates back to
each pane's own renderer; the tabs are a ``container:"tabbed"`` wrapper switched client-side
(no shell reload). This is the abstraction seam: a composite/tab is a declaration of panes,
so a section can be reworked (or new sub-tools assembled) without touching the sub-tools.
``farm_profile`` and ``samras_structure`` remain available standalone (still selectable in
the menubar search).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.instances import list_farm_instances
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import read_sandbox_catalog
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .agro_calendar_viewer import AgroCalendarViewer
from .contracts_tool import ContractsTool
from .entity_profile_table import EntityProfileTable
from .farm_profile_viewer import FarmProfileViewer
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_profile
from .inventory_manager import InventoryManagerTool
from .local_domain_viewer import LocalDomainViewer, build_record_view
from .network_map_viewer import NetworkMapViewer
from .object_profiles_view import build_object_rows
from .objects_viewer import ObjectsViewer, _load_object_profiles
from .planting_calendar_viewer import PlantingCalendarViewer
from .planting_map_viewer import PlantingMapViewer
from .plot_manager_viewer import PlotManagerViewer
from .plot_overview_viewer import PlotOverviewViewer
from .record_synopsis import InventorySynopsis
from .taxa_product_table import TaxaProductTable
from .taxonomy_domain_viewer import TaxonomyDomainViewer

_SCHEMA = "mycite.v2.portal.workbench.tool.agronomics.v1"
# The LCL id-space is the agronomics structure of interest; default the right pane to it.
_DEFAULT_STRUCTURE = "lcl"
# The txa taxonomy lives in its own dedicated sandbox (not agro_erp); the Taxonomy Domain
# tab reads it there. See scripts/bootstrap_taxonomy_anchor.py.
_TAXONOMY_SANDBOX = "taxonomy"


def _list_farms(authority_db_file: Path | None) -> list[str]:
    """Farm sandboxes, discovered by shape — see micyte.core.instances.

    Returns [] when the store is unreadable or holds no farm. It used to return
    ``["trapp_family_farm"]`` in both cases, which claimed a farm existed on the
    strength of a failed read and named one farm in code; the FARM selector now
    renders empty instead of pointing at a farm it never confirmed.
    """
    docs, err = read_sandbox_catalog(authority_db_file, tenant_id="fnd")
    if err:
        return []
    return [instance.sandbox for instance in list_farm_instances(docs)]


def _pretty_farm(sandbox: str) -> str:
    return sandbox.replace("_", " ").title()


class AgronomicsViewer:
    """Compose farm_profile + the LCL structure viewer into one two-pane section."""

    tool_id = "agronomics"
    label = "Agronomics"
    summary = "Farm profile map beside the LCL id-space tree — the two agronomics views together."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Surfaces wherever EITHER sub-tool would: the agro_erp sandbox has both the
    # hops_geospatial_filament (farm_profile) and samras_taxonomy (lcl) archetypes.
    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament", "samras_taxonomy")
    applies_to_source_kind: tuple[str, ...] = ()
    # Pass the surface_query through so the right pane's structure <select> works.
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
        eq = extra_query or {}
        # FARM selector: the tool operates on whichever farm sandbox is chosen (farm_sandbox
        # surface param), defaulting to the doc's sandbox. Validated against the discovered
        # farm list so a stale/invalid token falls back to the first discovered farm rather
        # than to a farm named in code. The resolved ``sandbox`` is threaded to every
        # farm-specific sub-tool below; "" when the store holds no farm at all.
        farms = _list_farms(authority_db_file)
        explicit = _as_text(eq.get("farm_sandbox"))
        requested = explicit or sandbox_id
        if requested in farms:
            sandbox = requested
        elif explicit:
            # An EXPLICITLY-selected farm that does not currently resolve (e.g. a
            # farm mid-rekey whose documents momentarily span two msns, so it is
            # filtered out of the discovered list) must NOT silently fall through
            # to another farm's data. Fail closed: "" renders "no farm" downstream
            # rather than one instance's data under another's selection.
            sandbox = ""
        else:
            # No explicit selection (fresh open / stale doc sandbox): default to
            # the first discovered farm, a rule not a name. "" when none exist.
            sandbox = farms[0] if farms else ""

        # Shared tabbed-hub builder — the single place that assembles a `container:"tabbed"`
        # payload and VALIDATES active_tab against the real tab ids (a stale/removed tab token
        # falls back to the default, then the first tab, instead of rendering blank). Every
        # nested hub (FARM / NETWORK / Flora & Fauna) and the outer Agronomics hub go through
        # it so the sub-tab structure is consistent. `force` wins over the query param (the
        # inventory takeover forces PLAN).
        def _hub(title: str, query_param: str, default: str, tabs: list[dict[str, Any]],
                 *, farm_selector: dict[str, Any] | None = None, force: str = "") -> dict[str, Any]:
            ids = [t["id"] for t in tabs]
            active = force if (force and force in ids) else (_as_text(eq.get(query_param)) or default)
            if active not in ids:
                active = default if default in ids else (ids[0] if ids else "")
            hub: dict[str, Any] = {
                "schema": _SCHEMA, "container": "tabbed", "title": title, "sandbox_id": sandbox,
                "active_tab": active, "tab_query_param": query_param, "tabs": tabs,
            }
            if farm_selector is not None:
                hub["farm_selector"] = farm_selector
            return hub

        # Full-tab takeover: an expand-view node (local_view = its record-view token) shifts
        # the FARM tab from the map+tree composite into a full-width record table of that
        # node's child instances, with a back affordance the renderer turns into a ← bar.
        local_view = _as_text(eq.get("local_view"))
        record_table = (
            build_record_view(local_view, authority_db_file=authority_db_file, sandbox_id=sandbox)
            if local_view else None
        )
        if record_table is not None:
            farm_panel = {
                **record_table,
                "back": {"label": "Back to farm view", "param": "local_view", "value": ""},
            }
        else:
            # Left pane: the farm-profile map (resolves its own doc by archetype).
            farm_payload = FarmProfileViewer().build_panel_payload(
                authority_db_file=authority_db_file,
                sandbox_id=sandbox,
                document_id=document_id,
                datum_address=datum_address,
            )
            # Right pane: the LOCAL DOMAIN viewer (the SAMRAS lcl tree extended with
            # expand-to-table instance containers), defaulted to the lcl id-space.
            structure = _as_text(eq.get("samras_structure")) or _DEFAULT_STRUCTURE
            lcl_payload = LocalDomainViewer().build_panel_payload(
                authority_db_file=authority_db_file,
                sandbox_id=sandbox,
                document_id=document_id,
                datum_address=datum_address,
                extra_query={"samras_structure": structure},
            )
            # FARM = a summary HUB (nested tabbed): Overview (stat tiles + identity + map) beside
            # typed sub-sections that reuse the existing tools. Selecting an object row opens its
            # profile page (TASK-006); an Inventory/Plots/Clusters tile jumps to the PLAN tab.
            sub_kw = {"authority_db_file": authority_db_file, "sandbox_id": sandbox,
                      "document_id": "", "datum_address": ""}
            # counts for the Overview
            geo = {}
            fp_doc, _fp_err = resolve_farm_profile(authority_db_file, sandbox, "", tool=FarmProfileViewer())
            if fp_doc is not None:
                gp = build_geospatial_payload(fp_doc)
                geo = {k: gp.get(k, 0) for k in ("field_count", "plot_count", "cluster_count", "structure_count")}
            op_doc = _load_object_profiles(authority_db_file, sandbox)
            obj_rows = build_object_rows(op_doc) if op_doc is not None else []
            n_live = sum(1 for o in obj_rows if o.get("kind") == "livestock")
            n_ppl = sum(1 for o in obj_rows if o.get("kind") == "employee")
            contracts_payload = ContractsTool().build_panel_payload(**sub_kw)
            inventory_payload = InventorySynopsis().build_panel_payload(**sub_kw)
            n_contracts = contracts_payload.get("row_count", len(contracts_payload.get("rows", [])))
            n_inv = len(inventory_payload.get("items", []))
            stat_payload = {
                "schema": _SCHEMA, "container": "stat_tiles", "sandbox_id": sandbox, "title": "Farm at a glance",
                "tiles": [
                    {"label": "Fields", "value": geo.get("field_count", 0)},  # shown on the Overview map
                    {"label": "Structures", "value": geo.get("structure_count", 0), "tab": "infrastructure"},
                    {"label": "Livestock", "value": n_live, "tab": "animals"},
                    {"label": "People", "value": n_ppl, "tab": "people"},
                    {"label": "Contracts", "value": n_contracts, "tab": "contracts"},
                    {"label": "Plots", "value": geo.get("plot_count", 0), "tab": "__plan"},
                    {"label": "Clusters", "value": geo.get("cluster_count", 0), "tab": "__plan"},
                    {"label": "Inventory", "value": n_inv, "tab": "__plan"},
                ],
            }
            overview = {
                "schema": _SCHEMA, "container": "composite", "direction": "column",
                "title": "Overview", "sandbox_id": sandbox,
                "panes": [
                    {"tool_id": "farm_stats", "label": "", "panel_payload": stat_payload},
                    {"tool_id": "farm_profile", "label": "Farm Profile", "panel_payload": farm_payload},
                ],
            }
            infra_payload = ObjectsViewer().build_panel_payload(
                **sub_kw, filter_kinds=["barn", "greenhouse", "tunnel", "custom_area", "tractor"])
            animals_payload = ObjectsViewer().build_panel_payload(**sub_kw, filter_kinds=["livestock"])
            people_payload = ObjectsViewer().build_panel_payload(**sub_kw, filter_kinds=["employee"])
            farm_panel = _hub("Farm", "farm_section", "overview", [
                {"id": "overview", "label": "Overview", "panel_payload": overview},
                {"id": "infrastructure", "label": "Infrastructure", "panel_payload": infra_payload},
                {"id": "animals", "label": "Animals", "panel_payload": animals_payload},
                {"id": "people", "label": "People", "panel_payload": people_payload},
                {"id": "contracts", "label": "Contracts", "panel_payload": contracts_payload},
                {"id": "local", "label": "Local Domain", "panel_payload": lcl_payload},
            ])
        # PLAN tab: a nested tabbed HUB (like FARM / NETWORK / Flora & Fauna), partitioned by what
        # the operator is doing rather than by tool (operator spec):
        #   Plot     — the farm's DEFINED fields/clusters/plots, read-only, zoomed to the field.
        #              No authoring, and no fabricated live_preview plots (plot_overview passes
        #              preview=False) — a viewing surface must not invent geometry.
        #   Planting — the default: the map + inventory rail (the plots x days calendar navigator
        #              and the contract-creation map popup land here in later phases).
        #   Delegate — ALL geometry authoring: draw fields / clusters, edit plots.
        # PLAN was the only top-level tab that never went through _hub; routing it through the same
        # helper is what "solidify the sub-tab structure" means here — active_tab is validated
        # against the real ids, so a stale plan_section token falls back instead of rendering blank.
        _kw = {"authority_db_file": authority_db_file, "sandbox_id": sandbox,
               "document_id": "", "datum_address": ""}
        # Inventory-management takeover: the Inventory Synopsis "edit" button, or a Flora & Fauna
        # product-card "add" button, sets inventory_manage / inventory_new / inventory_edit — which
        # replaces the PLAN view (the whole hub, not one sub-tab) with the writable Inventory
        # Management table (backable-out).
        _inv_takeover = bool(_as_text(eq.get("inventory_manage")) or _as_text(eq.get("inventory_new"))
                             or _as_text(eq.get("inventory_edit")))
        if _inv_takeover:
            plan_panel = InventoryManagerTool().build_panel_payload(**_kw, extra_query=eq)
            plan_panel["back"] = {"label": "Back to plan",
                                  "params": ["inventory_manage", "inventory_new", "inventory_edit"]}
        else:
            # plan_day is the PLAN tab's single viewing date, shared by every sub-tab: geometry is
            # effective-dated, so the maps render the epoch this day falls in.
            plot_overview_payload = PlotOverviewViewer().build_panel_payload(**_kw, extra_query=eq)
            inventory_payload = InventorySynopsis().build_panel_payload(**_kw)
            inventory_payload["edit_action"] = {"param": "inventory_manage", "value": "1"}
            # Planting = [map | inventory count rail] over the plots x days calendar navigator.
            # All three read the same plan_day, so the map's geometry, the inventory counts and the
            # calendar's window always describe the same moment.
            planting_top = {
                "schema": _SCHEMA, "container": "composite", "direction": "row",
                "sandbox_id": sandbox,
                "panes": [
                    # Planting's map is the Plot overview PLUS occupancy shading and the contract
                    # popup; Plot itself stays a pure viewing surface.
                    {"tool_id": "planting_map", "label": "Map",
                     "panel_payload": PlantingMapViewer().build_panel_payload(**_kw, extra_query=eq)},
                    {"tool_id": "inventory_synopsis", "label": "Inventory",
                     "panel_payload": inventory_payload},
                ],
            }
            planting_panel = {
                "schema": _SCHEMA, "container": "composite", "direction": "column",
                "title": "Planting", "sandbox_id": sandbox,
                "panes": [
                    {"tool_id": "planting_top", "label": "", "panel_payload": planting_top},
                    {"tool_id": "planting_calendar", "label": "Calendar",
                     "panel_payload": PlantingCalendarViewer().build_panel_payload(**_kw, extra_query=eq)},
                ],
            }
            delegate_payload = PlotManagerViewer().build_panel_payload(**_kw, extra_query=eq)
            plan_panel = _hub("Plan", "plan_section", "planting", [
                {"id": "plot", "label": "Plot", "panel_payload": plot_overview_payload},
                {"id": "planting", "label": "Planting", "panel_payload": planting_panel},
                {"id": "delegate", "label": "Delegate", "panel_payload": delegate_payload},
            ])
        # NETWORK tab: the resources mycelium_network publishes via its source-binary
        # manifest — the cross-sandbox seam (agro_erp loads mycelium_network's produced
        # binaries, "some, not all"): boundary polygons + fnd_ag_profiles points +
        # calendar (ic-hops cyclical) events. Rendered by the network_map tool renderer.
        #
        # NETWORK is a nested tabbed hub that partitions the network by role (operator spec):
        #   Operation (main) — public food-access points (CSAs / farmers markets / markets /
        #     farm stands): the MAP over the Agro Calendar (all events are public recurrences →
        #     they live here). No entity table — Operation is a map + calendar surface.
        #   Peer — other farms, co-ops, other legal/administrative/informal entities: map + table.
        #   Logistic — suppliers: map + table.
        # Each sub-tab filters the same one classification (network_map_viewer._section_for)
        # via the network_section param, so map + table + calendar always agree. The map
        # suppresses its own events aside (hide_events) — events belong to the Operation
        # calendar; Peer/Logistic's table owns the right pane.
        def _network_section_panel(section: str, *, with_calendar: bool) -> dict[str, Any]:
            sec_eq = {**eq, "network_section": section}
            section_map = {**NetworkMapViewer().build_panel_payload(**_kw, extra_query=sec_eq),
                           "hide_events": True}
            if with_calendar:
                # Operation = the map stacked over the Agro Calendar (no entity table).
                calendar = AgroCalendarViewer().build_panel_payload(**_kw, extra_query=eq)
                return {
                    "schema": _SCHEMA, "container": "composite", "direction": "column",
                    "title": section.title(), "sandbox_id": sandbox,
                    "panes": [
                        {"tool_id": "network_map", "label": "Map", "panel_payload": section_map},
                        {"tool_id": "agro_calendar", "label": "Calendar", "panel_payload": calendar},
                    ],
                }
            # Peer / Logistic = the map beside the entity-profile table.
            section_table = EntityProfileTable().build_panel_payload(**_kw, extra_query=sec_eq)
            return {
                "schema": _SCHEMA, "container": "composite", "direction": "row",
                "title": section.title(), "sandbox_id": sandbox,
                "panes": [
                    {"tool_id": "network_map", "label": "Map", "panel_payload": section_map},
                    {"tool_id": "entity_profile_table", "label": "Entity Profiles",
                     "panel_payload": section_table},
                ],
            }

        network_payload = _hub("Network", "network_view", "operation", [
            {"id": "operation", "label": "Operation",
             "panel_payload": _network_section_panel("operation", with_calendar=True)},
            {"id": "peer", "label": "Peer",
             "panel_payload": _network_section_panel("peer", with_calendar=False)},
            {"id": "logistic", "label": "Logistic",
             "panel_payload": _network_section_panel("logistic", with_calendar=False)},
        ])
        # TAXONOMY DOMAIN tab: a 2-pane composite — the vertical txa cluster tree (read
        # from the dedicated ``taxonomy`` sandbox, produce icons + closest-parent fallback,
        # opened down to the crop-profile taxa) beside a grouped/filterable product-profile
        # table (agro_erp product_profiles keyed by txa lineage).
        # The tree itself lives in the shared ``taxonomy`` sandbox, but its
        # crop-expansion reads product_profiles from the ACTIVE FARM — pass the
        # resolved farm so each instance opens the tree down to its own crops
        # (was hardcoded to one farm, so every instance opened trapp's).
        taxonomy_tree = TaxonomyDomainViewer().build_panel_payload(
            authority_db_file=authority_db_file, sandbox_id=_TAXONOMY_SANDBOX,
            document_id="", datum_address="", extra_query={**eq, "product_sandbox": sandbox},
        )
        taxa_table = TaxaProductTable().build_panel_payload(
            authority_db_file=authority_db_file, sandbox_id=sandbox,
            document_id="", datum_address="", extra_query=eq,
        )
        # Flora & Fauna: a nested tabbed hub whose subtabs toggle between the product-profile
        # cards and the taxonomy node cluster graph. Each page mainly displays info / sub-nodes;
        # its renderer also hosts an "add" affordance that jumps to the PLAN tab's inventory
        # management with a pre-queued entry (agronomics_tab=plan + inventory_new=<product node>).
        taxonomy_payload = _hub("Flora & Fauna", "flora_section", "products", [
            {"id": "products", "label": "Product Profiles", "panel_payload": taxa_table},
            {"id": "cluster", "label": "Cluster Graph", "panel_payload": taxonomy_tree},
        ])
        # FARM / PLAN / NETWORK / Flora & Fauna tabs. Tab switching is client-side in the
        # ``tabbed`` container renderer (no shell reload); ``active_tab`` lets an overlay/
        # surface_query param (agronomics_tab) re-open on a chosen tab. An inventory takeover
        # FORCES PLAN so the Flora & Fauna "add" jump (which only sets inventory_new) still
        # lands on the manager. The FARM selector rides in the tab strip; switching sets the
        # farm_sandbox surface param and refetches the whole tool on the chosen farm.
        return _hub(
            "Agronomics", "agronomics_tab", "farm",
            [
                {"id": "farm", "label": "FARM", "panel_payload": farm_panel},
                {"id": "plan", "label": "PLAN", "panel_payload": plan_panel},
                {"id": "network", "label": "NETWORK", "panel_payload": network_payload},
                {"id": "taxonomy", "label": "Flora & Fauna", "panel_payload": taxonomy_payload},
            ],
            farm_selector={
                "param": "farm_sandbox", "current": sandbox,
                "options": [{"value": f, "label": _pretty_farm(f)} for f in farms],
            },
            force=("plan" if _inv_takeover else ""),
        )


# Self-register on import.
register(AgronomicsViewer())
