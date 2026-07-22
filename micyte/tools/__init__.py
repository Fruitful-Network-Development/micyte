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
    contacts_viewer,  # noqa: F401
    contracts_tool,  # noqa: F401
    farm_profile_viewer,  # noqa: F401  (consolidated: profile_card + geospatial_projection)
    geospatial_projection_viewer,  # noqa: F401  (field/plots map base)
    inventory_manager,  # noqa: F401  (writable supply-batch table)
    invoices_viewer,  # noqa: F401
    local_domain_viewer,  # noqa: F401  (lcl tree + expand-to-table instance containers)
    onboarding,  # noqa: F401  (base Onboarding -> FarmOnboardingTool)
    planting_calendar_viewer,  # noqa: F401  (plots x days contract swimlanes; PLAN Planting tab)
    planting_map_viewer,  # noqa: F401  (PLAN Planting map: occupancy + contract creation)
    plot_manager_viewer,  # noqa: F401  (geospatial + date + select + create-cluster)
    plot_overview_viewer,  # noqa: F401  (read-only defined fields/clusters/plots; PLAN Plot tab)
    plots_viewer,  # noqa: F401
    product_document_view,  # noqa: F401
    profile_card_viewer,  # noqa: F401  (base profile contract; farm_profile builds on it)
    record_studio,  # noqa: F401  (write/form base; ContractEditor)
    record_synopsis,  # noqa: F401  (derived-figure summaries; InventorySynopsis)
    registrar_portal_viewer,  # noqa: F401  (registrar entity-profile search/view/edit/create)
    samras_structure_viewer,  # noqa: F401  (unified txa/msn/lcl structure viewer)
    taxonomy_domain_viewer,  # noqa: F401  (txa taxonomy graph w/ produce icons; taxonomy sandbox)
)

# Intentionally NOT imported (so they do not self-register into the viz palette):
#   * workbench_ui_view — `workbench_ui` is the workbench SURFACE (registered as a
#     surface-routing entry in shell_registry), not a visualization tool; importing it
#     made it a fake "navigates_to_surface" tool on every doc. Surface nav is unaffected.
#   (The legacy cts_gis_map / cts_gis_district / cts_gis_admin fixed-artifact viewers,
#     their `_cts_gis_artifact` infra, and the cross_domain/cts_gis module were deleted
#     once the cts_gis sandbox data was migrated to mycelium_network — they gated on a
#     near-universal `sandbox_source` bucket with no honest per-doc eligibility and were
#     already unreachable from the palette/surface/registry.)
from ._contract import WorkbenchTool
from ._registry import TOOL_REGISTRY, all_tools, describe_for_palette, get, register

__all__ = [
    "WorkbenchTool",
    "TOOL_REGISTRY",
    "all_tools",
    "describe_for_palette",
    "get",
    "register",
]
