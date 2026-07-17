"""Workbench-UI palette entry — the universal datum grid as a palette tool.

Workbench-UI is the universal SQL-backed datum grid that hosts the default
``/portal/system/tools/workbench-ui`` surface. Registering it here gives the
menubar palette an explicit "switch to the workbench grid" option whenever a
datum context selects a sandbox-source or system-anthology document — the
sibling of every dedicated viz tool (cts_gis, agro_erp, …).

The actual document_table / datum_grid / overlay rendering lives in
``MyCiteV2/instances/_shared/runtime/portal_workbench_ui_runtime.py`` and is
reached by navigating to ``WORKBENCH_UI_TOOL_ROUTE`` (carried on the palette
entry's ``route`` field by the shell, not by the build-payload contract).
This module exists solely so the viz registry — the one
``portal_palette_runtime.build_eligible_tools_response`` consults — can see
workbench_ui alongside cts_gis. See ``portal_tool_surface_contract.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)


class WorkbenchUiTool:
    """Universal datum-grid palette entry.

    ``applies_to_source_kind`` mirrors
    ``shell_registry.build_portal_tool_registry_entries`` so the palette
    surfaces workbench_ui for both sandbox-source documents (alongside
    cts_gis / agro_erp) and system-anthology documents (where the
    workbench is the only applicable tool).
    """

    tool_id = "workbench_ui"
    label = "Workbench UI"
    summary = "Read-only SQL datum grid with additive directive-overlay inspection."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ("sandbox_source", "system_anthology")

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        # The workbench-UI tool does not render into the visualization panel;
        # selecting it from the palette navigates to its dedicated surface
        # (WORKBENCH_UI_TOOL_ROUTE), where portal_workbench_ui_runtime renders
        # the full document_table + datum_grid + overlay shape. The payload
        # below is just the schema marker so any consumer that introspects
        # panel_payload knows which tool produced it.
        return {
            "schema": "mycite.v2.portal.workbench.tool.workbench_ui.v1",
            "sandbox_id": sandbox_id,
            "document_id": document_id,
            "selected_row_address": datum_address,
            "navigates_to_surface": True,
        }


# NOT self-registered: `workbench_ui` is the workbench SURFACE (routed via shell_registry),
# not a visualization tool. It must never appear in the viz palette. The class stays for
# the surface-routing payload shape. See packages/tools/__init__.py.
