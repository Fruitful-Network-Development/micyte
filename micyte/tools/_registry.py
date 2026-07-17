"""Workbench-tool registry (Plan v2).

Tools self-register by appending to ``TOOL_REGISTRY`` on import. The
workbench runtime imports this module and looks up tools by
``tool_id`` from ``surface_query.tool``.

The registry is intentionally a dict, not a class — tools are global
singletons keyed by ID. Use :func:`register` to add a tool; use
:func:`all_tools` for the menubar palette listing.
"""

from __future__ import annotations

from typing import Any

from ._contract import WorkbenchTool

# tool_id -> WorkbenchTool instance.
TOOL_REGISTRY: dict[str, WorkbenchTool] = {}


def register(tool: WorkbenchTool) -> WorkbenchTool:
    """Add a tool to the registry. Returns the tool for fluent use.

    Re-registering the same ``tool_id`` overwrites the previous entry —
    useful for tests but typically a tool module is imported once.
    """
    if not isinstance(tool, WorkbenchTool):
        raise TypeError(
            f"register() expected a WorkbenchTool, got {type(tool).__name__}"
        )
    TOOL_REGISTRY[tool.tool_id] = tool
    return tool


def get(tool_id: str) -> WorkbenchTool | None:
    """Look up a tool by id, or None when absent."""
    return TOOL_REGISTRY.get(tool_id)


def all_tools() -> list[WorkbenchTool]:
    """Return every registered tool, sorted by tool_id for stability."""
    return [TOOL_REGISTRY[k] for k in sorted(TOOL_REGISTRY)]


def describe_for_palette() -> list[dict[str, Any]]:
    """Render every registered tool as the palette's eligibility dict.

    The menubar palette uses this when the user hasn't selected a
    datum — show all tools, let the user pick one. When a datum *is*
    selected, the workbench runtime filters by applies_to_archetype /
    applies_to_source_kind.
    """
    return [
        {
            "tool_id": t.tool_id,
            "label": t.label,
            "summary": t.summary,
            "applies_to_archetype": list(t.applies_to_archetype),
            "applies_to_source_kind": list(t.applies_to_source_kind),
        }
        for t in all_tools()
    ]
