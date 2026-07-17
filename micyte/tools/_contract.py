"""Workbench-tool contract (Plan v2).

A workbench tool is a simple module that takes a (sandbox, document,
datum) context and produces a panel payload the JS renderer paints
into the workbench's visualization panel. Tools no longer own surfaces,
routes, or activity-bar slots — they are discovered via the menubar
search and invoked via ``surface_query.tool``.

The contract is intentionally minimal: a few identifying attributes and
one method. Tools self-register in :mod:`_registry` on import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class WorkbenchTool(Protocol):
    """Protocol every workbench visualization tool implements.

    Attributes are read by the menubar palette for eligibility
    filtering. ``build_panel_payload`` is invoked by the workbench
    runtime when the user selects this tool; its return value is
    embedded in ``regions.visualization_panel.panel_payload`` for the
    JS renderer.
    """

    tool_id: str
    label: str
    summary: str
    # Route the menubar palette stamps onto each item's data-route attribute;
    # ``v2_portal_tool_palette.js`` renderList reads it and dispatches it on
    # click. Should be the tool's canonical surface route (the shell
    # ``portal_system_tool`` dispatcher 302-redirects deep-link tool URLs
    # into the unified ``/portal/system?tool=<id>`` workbench).
    route: str
    applies_to_archetype: tuple[str, ...]
    applies_to_source_kind: tuple[str, ...]

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        """Return the panel_payload dict the JS renderer will consume."""
        ...


class DatumDocTool:
    """Template-method base for sandbox datum-document viewers (consolidation spine).

    Owns the ``build_panel_payload`` preamble that was copy-pasted across every agro_erp
    tool — db guard → store → read catalog → resolve the target doc by archetype/name →
    standard error/success envelope. A subclass supplies ONLY the projection
    (:meth:`shape_payload`) and its empty/error keys (:meth:`empty_body`).

    Keeps every :class:`WorkbenchTool` Protocol member (``route`` / ``summary`` /
    ``applies_to_*``) because :func:`_registry.register` ``isinstance``-checks the
    runtime-checkable Protocol and the palette reads those via ``getattr``.
    """

    # --- identity (subclass overrides) ---
    tool_id: str = ""
    label: str = ""
    summary: str = ""
    schema: str = ""
    # The canonical doc name the tool renders (resolved by name, then archetype).
    canonical_name: str | None = None
    # The JS container kind the renderer switches on (declarative dispatch).
    container: str = ""
    # --- Protocol members with spine defaults ---
    tenant_id: str = "fnd"
    # No sandbox is named here. When a caller does not specify one, the sandbox is
    # discovered from the store (first farm by shape) — a farm onboarded tomorrow
    # is eligible with no code change, and a store with no farms yields nothing
    # rather than a name that may not exist.
    default_sandbox: str | None = None
    applies_to_archetype: tuple[str, ...] = ()
    # Intentionally EMPTY: eligibility is by ARCHETYPE token only. Each live agro_erp doc
    # carries its mycite.v2.datum.agro_erp.<x>.v1 (or hops_geospatial_filament) archetype,
    # which scopes a viewer to the one sandbox holding its doc. Claiming a broad source_kind
    # (e.g. "sandbox_source") would surface the viewer in EVERY sandbox (cts_gis/grantee_legacy/…).
    applies_to_source_kind: tuple[str, ...] = ()

    @property
    def route(self) -> str:  # Protocol member; the unified workbench route.
        from micyte.state_machine.portal_shell.shell_schemas import (
            WORKBENCH_UI_TOOL_ROUTE,
        )

        return WORKBENCH_UI_TOOL_ROUTE

    # --- subclass hooks ---
    def empty_body(self) -> dict[str, Any]:
        """The tool-specific keys an error/empty payload must still carry."""
        return {}

    def shape_payload(
        self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str
    ) -> dict[str, Any]:
        """Project the resolved ``doc`` (+ sibling ``docs``) into the panel body."""
        raise NotImplementedError

    # --- template method ---
    def _error(self, message: str) -> dict[str, Any]:
        return {"schema": self.schema, "error": message, **self.empty_body()}

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        from ._archetype import read_sandbox_catalog, resolve_tool_document
        from ._shared.utilities import as_text

        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=self.tenant_id)
        if err:
            return self._error(err)
        # Resolve against the ACTIVE sandbox. A viewer is only addable where its datum docs
        # exist (archetype-scoped search), so this receives the right sandbox; invoked under
        # any other sandbox it resolves to nothing ("not found"), which is correct.
        # Do NOT fall back to "the first farm in the store": with canonical_name resolution
        # that renders a same-named document from an ARBITRARY farm instance on a no-sandbox
        # call — a cross-instance leak. No sandbox -> fail closed.
        sandbox = sandbox_id or self.default_sandbox
        if not sandbox:
            return self._error("no sandbox specified")
        doc = resolve_tool_document(
            docs, tool=self, sandbox=sandbox, document_id=document_id, canonical_name=self.canonical_name
        )
        if doc is None:
            return self._error(f"{self.canonical_name or 'target'} document not found")
        try:
            body = self.shape_payload(doc=doc, docs=docs, sandbox=sandbox, datum_address=datum_address)
        except Exception as exc:  # pragma: no cover — defensive
            return self._error(f"render failed: {exc}")
        if "error" in body:
            return {"schema": self.schema, **body}
        return {
            "schema": self.schema,
            "sandbox_id": sandbox,
            "document_id": as_text(getattr(doc, "document_id", "")),
            "selected_row_address": as_text(datum_address),
            **body,
        }
