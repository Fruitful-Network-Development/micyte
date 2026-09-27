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

from micyte.core.instance_baseline import LOCAL_DOMAIN_NAMES
from micyte.core.instances import list_farm_instances
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import read_sandbox_catalog
from ._shared.utilities import as_text as _as_text
from ._viewscope import viewscope_pane
from .entity_profile_table import EntityProfileTable
from .farm_profile_viewer import FarmProfileViewer
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_profile
from .local_domain_viewer import build_record_view
from .network_map_viewer import NetworkMapViewer, build_network_map_base
from .object_profiles_view import build_object_rows
from .objects_viewer import ObjectsViewer, _load_object_profiles
from .planting_calendar_viewer import PlantingCalendarViewer
from .planting_map_viewer import PlantingMapViewer
from .plot_manager_viewer import PlotManagerViewer
from .plot_overview_viewer import PlotOverviewViewer
from .taxa_product_table import TaxaProductTable

_SCHEMA = "mycite.v2.portal.workbench.tool.agronomics.v1"
# The LCL id-space is the agronomics structure of interest; default the right pane to it.
_DEFAULT_STRUCTURE = "lcl"
# The txa taxonomy lives in its own dedicated sandbox (not agro_erp); the Taxonomy Domain
# tab reads it there. See scripts/bootstrap_taxonomy_anchor.py.
_TAXONOMY_SANDBOX = "taxonomy"


def _list_farms(authority_db_file: Path | None) -> list[str]:
    """Farm sandboxes, discovered by shape — see micyte.core.instances.

    Returns [] when the store is unreadable or holds no farm. It used to return
    a single hard-coded farm name in both cases, which claimed a farm existed on the
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
    #: A FARM's surface. `applies_to_archetype` already scopes it when a document is in
    #: focus; this scopes it when nothing is — the menubar palette with no selection used to
    #: offer every tool everywhere, so a handyman searching their own instance found the
    #: agronomics hub and opened somebody's farm.
    requires = ToolRequirement(
        documents=(
            DocumentRequirement(
                name="farm_profile", archetype="farm_profile_identity",
                why="the farm this hub is a view of"),
        ),
    )
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
        # it so the sub-tab structure is consistent. `force` wins over the query param
        # (unused since the inventory takeover left with the old-model panes; kept as the
        # seam a future takeover would use).
        def _hub(title: str, query_param: str, default: str, tabs: list[dict[str, Any]],
                 *, farm_selector: dict[str, Any] | None = None, force: str = "",
                 shared: dict[str, Any] | None = None) -> dict[str, Any]:
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
            # A hub's tabs are switched CLIENT-SIDE, so every tab's payload ships on the first
            # response whether or not it is ever opened. `shared` is the escape hatch for a
            # field that is IDENTICAL in several of them: it is serialized once here, and each
            # tab that wants it says so with `shared_fields` and is re-joined to it on paint.
            # Sharing a Python object between tabs does nothing on its own — JSON has no
            # aliasing, so an object referenced three times is written out three times.
            if shared:
                hub["shared_payload"] = shared
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
            # LOCAL DOMAIN — the sandbox's OWN lcl, drawn by its archetype. Per sandbox is
            # the point: a datum document is offered as a source file other sandboxes
            # import, and an import APPENDS to the importing sandbox's local domain. So this
            # resolves `lcl` in whichever farm is selected and never a shared one, and the
            # name index resolves local-first for the same reason — `1-1-1` is a different
            # node in every lcl there is.
            lcl_payload = viewscope_pane(
                # BOTH spellings, canonical first. The document was renamed on 2026-08-20
                # and this pane resolves it by name; asking for one literal would have
                # drawn "nothing here" over every farm's own classification.
                authority_db_file, sandbox=sandbox, names=LOCAL_DOMAIN_NAMES,
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
            # The SALES / OFFERING / INVENTORY panes and their tiles are GONE (old-model
            # pane cleanup, TASK-2026-08-14-002): they spoke the pre-archetype record
            # model into documents NO live sandbox holds — measured before removal, every
            # one rendered its empty state on every farm — while the hub these tabs are
            # LIFTED into (brevat) carries the modern Supply / Sales / Offering ledgers
            # beside them. Two ledgers on one hub, one of them dead; the dead one left.
            stat_payload = {
                "schema": _SCHEMA, "container": "stat_tiles", "sandbox_id": sandbox, "title": "Farm at a glance",
                "tiles": [
                    {"label": "Fields", "value": geo.get("field_count", 0)},  # shown on the Overview map
                    {"label": "Structures", "value": geo.get("structure_count", 0), "tab": "infrastructure"},
                    {"label": "Livestock", "value": n_live, "tab": "animals"},
                    {"label": "People", "value": n_ppl, "tab": "people"},
                    {"label": "Plots", "value": geo.get("plot_count", 0), "tab": "__plan"},
                    {"label": "Clusters", "value": geo.get("cluster_count", 0), "tab": "__plan"},
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
                # The Contracts tab is GONE (Phase 1: the `contracts` document does not
                # exist live), and the Sales / Offering sub-tabs followed it in the
                # old-model pane cleanup — see the note above the stat tiles.
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
        # The Inventory-management TAKEOVER and the Planting inventory rail are GONE with
        # the old-model panes (see the FARM note): both were the pre-archetype supply
        # table, and every live render was its empty state. The planting map's own batch
        # rail (`_consumption.available_batches`) is untouched — it reads documents, not
        # the retired panes — and re-points to the modern ledger when farm supply lands
        # there (a recorded gate, not this cleanup's).
        #
        # plan_day is the PLAN tab's single viewing date, shared by every sub-tab: geometry is
        # effective-dated, so the maps render the epoch this day falls in.
        plot_overview_payload = PlotOverviewViewer().build_panel_payload(**_kw, extra_query=eq)
        # Planting = the map over the plots x days calendar navigator. Both read the same
        # plan_day, so the map's geometry and the calendar's window always describe the
        # same moment.
        planting_panel = {
            "schema": _SCHEMA, "container": "composite", "direction": "column",
            "title": "Planting", "sandbox_id": sandbox,
            "panes": [
                # Planting's map is the Plot overview PLUS occupancy shading and the contract
                # popup; Plot itself stays a pure viewing surface.
                {"tool_id": "planting_map", "label": "Map",
                 "panel_payload": PlantingMapViewer().build_panel_payload(**_kw, extra_query=eq)},
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
        # The map base, built ONCE for the whole NETWORK tab. Its three sub-tabs previously
        # rebuilt it six times over — three maps, two entity tables and the calendar — for a
        # payload that differs only in which section its profiles and events are filtered to.
        # Everything costly in it (the manifest walk, the boundary geometry, the features) is
        # section-independent, so the other five builds bought nothing.
        #
        # Lazy: a request that opens on FARM or PLAN never pays for it. Defensive: if the base
        # cannot be built the sub-tools fall back to their own path and report the error
        # themselves, rather than the tab going blank on a shared failure.
        _net_base: list[dict[str, Any] | None] = []

        def _network_base() -> dict[str, Any] | None:
            if not _net_base:
                docs, err = read_sandbox_catalog(authority_db_file, tenant_id="fnd", sandbox="registrar")
                _net_base.append(
                    None if err else build_network_map_base(docs, sandbox_id=sandbox))
            return _net_base[0]

        # The geometry every NETWORK sub-tab draws, hoisted out of the three map payloads and
        # carried once on the hub. `feature_collection` is ~500 boundary polygons and by far the
        # largest thing in the payload; `region_layers` is its layer control. Neither depends on
        # the section — `section_view` copies both straight through — so a self-contained payload
        # per sub-tab serialized the same megabyte three times, on a response that is already
        # the slowest in the panel. The sub-tab names what it wants in `shared_fields` and the
        # renderer re-joins it before painting, so nothing downstream sees a partial payload.
        _network_shared: dict[str, Any] = {}
        _NETWORK_SHARED_FIELDS = ("feature_collection", "region_layers")

        def _network_section_panel(section: str, *, with_calendar: bool) -> dict[str, Any]:
            sec_eq = {**eq, "network_section": section}
            base = _network_base()
            section_map = {**NetworkMapViewer().build_panel_payload(
                **_kw, extra_query=sec_eq, network_base=base), "hide_events": True}
            if not section_map.get("error"):
                # An errored map keeps its own (empty) collection: the three sub-tabs can fail
                # for different reasons, and a shared field would hide that.
                hoisted = [f for f in _NETWORK_SHARED_FIELDS if f in section_map]
                for field in hoisted:
                    _network_shared.setdefault(field, section_map.pop(field))
                if hoisted:
                    # Only ever names fields the hub really carries — a marker for something
                    # absent would have the renderer looking for a re-join that never comes.
                    section_map["shared_fields"] = hoisted
            if with_calendar:
                # Operation = the map alone. It was the map stacked over the Agro
                # Calendar until the operator retired that tool completely
                # (2026-08-16); the network's cadences are no longer drawn anywhere.
                return {
                    "schema": _SCHEMA, "container": "composite", "direction": "column",
                    "title": section.title(), "sandbox_id": sandbox,
                    "panes": [
                        {"tool_id": "network_map", "label": "Map", "panel_payload": section_map},
                    ],
                }
            # Peer / Logistic = the map beside the entity-profile table.
            section_table = EntityProfileTable().build_panel_payload(
                **_kw, extra_query=sec_eq, network_base=base)
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
        ], shared=_network_shared)
        # TAXONOMY DOMAIN tab: a 2-pane composite — the vertical txa cluster tree (read
        # from the dedicated ``taxonomy`` sandbox, produce icons + closest-parent fallback,
        # opened down to the crop-profile taxa) beside a grouped/filterable product-profile
        # table (agro_erp product_profiles keyed by txa lineage).
        # The tree itself lives in the shared ``taxonomy`` sandbox, but its
        # crop-expansion reads product_profiles from the ACTIVE FARM — pass the
        # resolved farm so each instance opens the tree down to its own crops
        # (was hardcoded to one farm, so every instance opened the same one's).
        # The taxonomy is the one local domain that is NOT per sandbox: `txa` is the shared
        # space every sandbox cites, which is why this names _TAXONOMY_SANDBOX rather than
        # the selected farm. Same container, different scope.
        taxonomy_tree = viewscope_pane(
            authority_db_file, sandbox=_TAXONOMY_SANDBOX, names=("txa",),
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
        )


# Self-register on import.
# register(AgronomicsViewer())  # retired TASK-2026-08-14-002 Farmers phase: the
# standalone hub's tabs are LIFTED into `brevat` when a sandbox holds farm_profile
# (Brevat – Farmers). The module survives as the farm-tab library the lift builds.
