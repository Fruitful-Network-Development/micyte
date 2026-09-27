"""Convention — the local domain's base structure as a document the operator edits, and
every tree's standing against it.

Operator, 2026-09-11: *"edit the local domain archetype document from the FND instance in
the archetype sandbox via the view scope … mostly organization of defaults and icon
selection so that I can update the convention from there."*

Two panes, one composite. The first is the archetype library's own `lcl_domain` opened
in the Domain surface — the SAME editor every tree uses (`lcl_editor`'s verbs, posted
with the library's sandbox), so a glyph chosen here is `set_node_icon` and a branch moved
is `move_node`, gated the way they are everywhere. The second is the trees that pin the
convention, each with its verdict (`convention_runtime.convention_status`) and the one
verb that brings a stale tree up to it. The viewscope is not a second editor: it is what
draws the library's tree as the tree it is, and the editor is what changes it — "sturdy
but relative": bound by the document's archetype, never by a tool id.

Universal (no `applies_to_archetype`) and launched against the instance, because its
subject is one document every instance cites. Read-only itself; `apply_convention` is
declared here so the register knows who owns the write, and the agro route dispatches it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from ._shared.utilities import as_text

_SCHEMA = "mycyte.v2.portal.workbench.tool.convention.v1".replace("mycyte", "mycite")
_AGRO_ROUTE = "/portal/api/v2/agro"
ROUTES = {"apply_convention": f"{_AGRO_ROUTE}/apply_convention"}
_VERDICT_WORDS = {
    "fresh": "current", "stale": "behind the convention", "unpinned": "not pinned yet",
    "library": "the convention itself", "unreadable": "could not be read",
    "unverifiable": "pinned without a hash (its namespace cannot carry one)",
}


class ConventionSurface:
    """The library's tree in the editor, and every tree's standing against it."""

    tool_id = "convention"
    label = "Convention"
    summary = ("The base structure every local domain is made of — edit it here, see which "
               "trees are behind it, and bring them up.")
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "composite"
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    writes = (
        # A tree write on the TARGET sandbox (the one being brought up), declared here so
        # `_write_owners` names this surface and the route gates by the sandbox posted.
        DeclaredWrite(document_kind="lcl_type", action="apply_convention"),
    )

    def build_panel_payload(
        self, *, authority_db_file: Path | None = None, sandbox_id: str = "",
        document_id: str = "", datum_address: str = "",
        extra_query: dict[str, Any] | None = None, **_ignored: Any,
    ) -> dict[str, Any]:
        from micyte.core import archetypes as arc

        if authority_db_file is None:
            return {"schema": _SCHEMA, "container": "record_table", "title": "Convention",
                    "columns": ["tree"], "rows": [], "row_count": 0,
                    "empty_text": "authority database not configured"}
        # A composite's panes carry their payloads under `panel_payload` — the shape
        # `renderComposite` draws and every other composite (contacts, canvass) posts.
        panes = [
            {"label": "", "panel_payload": self._editor(
                authority_db_file, document_id=document_id, datum_address=datum_address,
                query=dict(extra_query or {}))},
            {"label": "", "panel_payload": self._standing(authority_db_file)},
        ]
        return {"schema": _SCHEMA, "container": "composite", "direction": "column",
                "title": "Convention", "sandbox_id": arc.ARCHETYPE_SANDBOX, "panes": panes}

    @staticmethod
    def _editor(db: Path, *, document_id: str, datum_address: str,
                query: dict[str, Any]) -> dict[str, Any]:
        from micyte.core import archetypes as arc
        from micyte.tools.lcl_editor import LclEditorViewer

        try:
            payload = LclEditorViewer().build_panel_payload(
                authority_db_file=db, sandbox_id=arc.ARCHETYPE_SANDBOX,
                document_id=document_id, datum_address=datum_address, extra_query=query)
        except Exception as exc:
            return {"schema": _SCHEMA, "container": "record_table", "title": "The convention",
                    "columns": ["node"], "rows": [], "row_count": 0,
                    "empty_text": f"the library's tree could not be read ({exc})"}
        payload["title"] = "The convention — the archetype library's own tree"
        payload["hint"] = ("What every local domain is made of. A glyph chosen here, a branch "
                           "renamed or moved, a vocabulary added under classes, becomes the "
                           "convention; the trees below say whether they have taken it.")
        return payload

    @staticmethod
    def _standing(db: Path) -> dict[str, Any]:
        from micyte.core.datum_ops.convention_standing import convention_status

        status = convention_status(db)
        if not status.get("ok"):
            return {"schema": _SCHEMA, "container": "record_table", "title": "Trees",
                    "columns": ["tree"], "rows": [], "row_count": 0,
                    "empty_text": as_text(status.get("error"))}
        rows = []
        for tree in status.get("trees", []):
            verdict = as_text(tree.get("verdict"))
            rows.append({
                "instance": as_text(tree.get("msn")), "sandbox": as_text(tree.get("sandbox")),
                "standing": _VERDICT_WORDS.get(verdict, verdict),
                "pinned": as_text(tree.get("pinned"))[:12],
                "wants": "; ".join(tree.get("wants") or []),
                "datum_address": f"{tree.get('sandbox')}@{tree.get('msn')}",
                "actions": ([] if verdict in ("fresh", "library", "unreadable", "unverifiable") else [{
                    "label": "Bring up to the convention", "route": ROUTES["apply_convention"],
                    "body": {"sandbox_id": as_text(tree.get("sandbox")),
                             "msn_id": as_text(tree.get("msn")), "apply": True}}]),
            })
        agrees = status.get("agrees_with_constants") or []
        counts = status.get("counts") or {}
        return {
            "schema": _SCHEMA, "container": "record_table",
            "title": "Trees that pin the convention",
            "count_label": ", ".join(f"{n} {_VERDICT_WORDS.get(v, v)}" for v, n in sorted(counts.items())),
            "columns": ["instance", "sandbox", "standing", "pinned", "wants"],
            "rows": rows, "row_count": len(rows),
            "notice": ("" if not agrees else
                       "the library's tree and the code's bootstrap disagree: " + "; ".join(agrees)),
            "empty_text": "no local domain pins the convention yet",
            "current": as_text(status.get("current"))[:12],
        }


register(ConventionSurface())

__all__ = ["ROUTES", "ConventionSurface"]
