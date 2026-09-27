"""The viewscope surface — one tool that renders any document its archetype describes.

This is deliberately the ONLY tool this program adds while removing 25. It is not a viewer
of a document kind; it is the seam through which every kind draws itself. Which primitive
draws which field lives in a ``viewscope_<archetype>`` datum document, so a new archetype
gets a rendered form with no Python and no JavaScript — the thing the 25 bespoke viewers
each had to be written for.

It declares no ``applies_to_archetype``, which makes it universal: a document with no
archetype is answered with the reason rather than an empty panel, because "this shape has
no archetype yet" is a fact worth reading and a blank pane is not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._viewscope import build_viewscope_payload

_SCHEMA = "mycite.v2.portal.workbench.tool.viewscope.v1"
_TENANT_DEFAULT = "fnd"


def _empty(reason: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "", "reason": reason}


class ViewscopeView:
    """Render the selected document through the viewscope its archetype declares."""

    tool_id = "viewscope"
    label = "Viewscope"
    summary = "Draw this document as the thing it is, not as a grid of rows."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = ""  # set per payload — the container IS the viewscope's declaration
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    tenant_id = _TENANT_DEFAULT
    # `viewscope_root` rides in the surface query so an address-space tree can be expanded
    # a level at a time. Browsing is a READ of a position, so it belongs in the query
    # string and reaches the same read-only endpoint the first render came from.
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
        if authority_db_file is None:
            return _empty("authority database not configured")
        target = _as_text(document_id)
        if not target:
            # Resolving "some document in this sandbox" would draw a document the operator
            # did not choose, which is exactly the empty-render bug `resolve_tool_document`
            # exists to prevent. A viewscope is ABOUT the selection.
            return _empty("select a document to draw it")
        payload = build_viewscope_payload(
            authority_db_file=Path(authority_db_file),
            tenant_id=self.tenant_id,
            document_id=target,
            space_root=_as_text((extra_query or {}).get("viewscope_root")),
        )
        payload.setdefault("sandbox_id", _as_text(sandbox_id) or payload.get("sandbox", ""))
        payload["selected_row_address"] = _as_text(datum_address)
        return payload


register(ViewscopeView())

__all__ = ["ViewscopeView"]
