"""Workbench-tool package.

Plan v2: tools are simple visualization renderers invoked from the
menubar palette. The contract is in :mod:`_contract`; the registry in
:mod:`_registry`. Each tool module self-registers on import.

To add a new tool: create ``fnd_app/packages/tools/<tool_id>.py``
implementing :class:`_contract.WorkbenchTool`, call
``_registry.register(MyTool())`` at module scope, then import the
module from this package's ``__init__`` so the registry is populated
when consumers import :mod:`micyte.tools`.
"""

from __future__ import annotations

# Self-registering tool modules (import for side effect). Order is irrelevant
# — ``_registry.all_tools()`` sorts by ``tool_id`` on read.
from . import (
    agronomics_viewer,  # noqa: F401  (composite: farm_profile + lcl structure)
    artifacts_viewer,  # noqa: F401  (INSTRUMENT: the instance's files, listed from the index)
    brevat,  # noqa: F401  (CORE composite ERP: overview + products + supply + sales + offering)
    calendar_viewer,  # noqa: F401  (CORE: this sandbox's own schedule, read by CLASS)
    contacts_manager,  # noqa: F401  (writable contact list)
    convention,  # noqa: F401  (CORE: the local domain convention — the library's tree, and every tree's standing)
    enchir,  # noqa: F401  (the datum-doc manager: documents by archetype, drawn by viewscope)
    export_manager,  # noqa: F401  (preview-then-take CSV; the one surface data leaves by)
    farm_profile_viewer,  # noqa: F401  (consolidated: profile_card + geospatial_projection)
    geospatial_projection_viewer,  # noqa: F401  (LIBRARY since Phase 1: geometry base, no longer a tool)
    grantor_overview,  # noqa: F401  (the grantor app's home: prices against measured overhead)
    grantor_permissions,  # noqa: F401  (declared/bound/granted per operation, and the two verbs)
    grantor_tolling,  # noqa: F401  (R8: the AWS cost record, residue first)
    job_manager,  # noqa: F401  (writable job log; appends, never rewrites the catalog)
    job_synopsis,  # noqa: F401  (derivation: what the work adds up to)
    lcl_editor,  # noqa: F401  (lcl node graph as the editing surface)
    local_domain_viewer,  # noqa: F401  (lcl tree + expand-to-table instance containers)
    mailbox_admin,  # noqa: F401  (OPERATOR: the addresses an instance holds, and the five acts on them)
    onboarding,  # noqa: F401  (base Onboarding -> FarmOnboardingTool)
    oveure,  # noqa: F401  (CORE composite shelf: overview + notes + domain + config; pulls note_books)
    pim_design,  # noqa: F401  (PIM's Design tab: the client's site, through the site_hosting port)
    pim_overview,  # noqa: F401  (PIM's home: what the sandbox keeps + the FND seam's state)
    planting_calendar_viewer,  # noqa: F401  (plots x days contract swimlanes; PLAN Planting tab)
    planting_map_viewer,  # noqa: F401  (PLAN Planting map: occupancy + contract creation)
    plot_manager_viewer,  # noqa: F401  (geospatial + date + select + create-cluster)
    plot_overview_viewer,  # noqa: F401  (read-only defined fields/clusters/plots; PLAN Plot tab)
    product_document_view,  # noqa: F401  (LIBRARY since Phase 1: build_product_rows, no longer a tool)
    profile_admin_edit_viewer,  # noqa: F401  (registry browse + entry/event curation)
    project_manager,  # noqa: F401  (writable projects table; the standing things jobs are done against)
    quiar,  # noqa: F401  (CORE composite CRM: overview + jobs + projects + clients + calendar; was handyman_erp)
    quiar_overview,  # noqa: F401  (the CRM's home: figures + upcoming + the booking form)
    registrar_portal_viewer,  # noqa: F401  (registrar entity-profile search/view/edit/create)
    resource_manifests,  # noqa: F401  (the shared leaflet library, its users, and the two deletes)
    rolodex,  # noqa: F401  (INSTRUMENT: every sandbox's contacts, read across the instance)
    samras_structure_viewer,  # noqa: F401  (unified txa/msn/lcl structure viewer)
    signin_manager,  # noqa: F401  (OPERATOR: client sign-ins + the acts on them, via the host)
    sources_manager,  # noqa: F401  (CORE: what this sandbox declares it reads from others)
    stock_ledger,  # noqa: F401  (brevat's Stock tab: what came in, what went out)
    taxonomy_domain_viewer,  # noqa: F401  (txa taxonomy graph w/ produce icons; taxonomy sandbox)
    viewscope_view,  # noqa: F401  (the archetype-driven renderer; replaces per-kind viewers)
)

# Intentionally NOT imported (so they do not self-register into the viz palette):
#   * home_config / agro_calendar_viewer — DELETED (Compendium redesign,
#     TASK-2026-08-16-001; the calendar-only rail). Their visualizing capacity moved
#     into the document layer: the instance card (home) renders when the msn_profile
#     document is OPENED (document_view_runtime → profile_admin_edit's renderer); the
#     network's cadence calendar was retired completely by the operator — nothing draws
#     it, and calendar_viewer's cadence-vs-moment doctrine now marks a boundary with
#     nothing on the far side.
#     `rolodex` went with them and CAME BACK on 2026-08-20 as an INSTRUMENT: the
#     primitive it read (`_sandboxes`) outlived it and named it as a caller, which is
#     what made the category visible. A contacts DOCUMENT still opens as the editable
#     contact table (contacts_manager); the instrument is the cross-sandbox question.
#   * note_manager — DELETED 2026-08-20 with the name convention: it listed documents by
#     a `note_` prefix that no document on the corpus carries any more. Its two surviving
#     actions moved to `lcl_editor`, which owns the surface a writing is now shown on.
#   * inventory_manager / sales_manager / offering_manager / record_synopsis /
#     invoices_viewer / sales_viewer / offering_viewer — DELETED (old-model pane
#     cleanup, TASK-2026-08-14-002): they spoke the pre-archetype record model into
#     documents no live sandbox holds, and the modern ledger (`ledger_books`) is the
#     one ledger the hub carries. Their write actions (save_invoice / save_sale /
#     save_offering) retired with them — removed, not re-owned.
#   * workbench_ui_view — DELETED (TASK-2026-08-14-002 Phase 1). `workbench_ui` is the
#     workbench SURFACE (registered as a surface-routing entry in shell_registry), not a
#     visualization tool; the module existed "so the palette could see it" while being
#     deliberately unimported, which meant it did nothing at all.
#   (The legacy cts_gis_map / cts_gis_district / cts_gis_admin fixed-artifact viewers,
#     their `_cts_gis_artifact` infra, and the cross_domain/cts_gis module were deleted
#     once the cts_gis sandbox data was migrated to mycelium_network — they gated on a
#     near-universal `sandbox_source` bucket with no honest per-doc eligibility and were
#     already unreachable from the palette/surface/registry.)
from ._contract import WorkbenchTool
from ._registry import (
    TOOL_REGISTRY,
    all_tools,
    declared_writes,
    declaring_tool,
    describe_for_palette,
    get,
    instance_can_use,
    register,
    requirements_for,
    tools_requiring,
    write_capable_tools,
)

__all__ = [
    "WorkbenchTool",
    "TOOL_REGISTRY",
    "all_tools",
    "declared_writes",
    "declaring_tool",
    "describe_for_palette",
    "get",
    "instance_can_use",
    "requirements_for",
    "tools_requiring",
    "register",
    "write_capable_tools",
]
