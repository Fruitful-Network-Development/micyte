"""Profile-card viewer — the BASE datum-visualizer.

Loads a single value-group-0 "collecting" datum and renders it as a profile card from three
references: a SAMRAS id, a title, and an optional visual (see ``profile_projection``). It is the
hardened base contract that ``farm_profile`` builds on — farm_profile composes the same
``build_profile_projection`` for its identity header, then extends it with the filament's
fields/plots. Kept deliberately minimal so future datum-doc tools (ecologicals, operators, …)
are a composition of this base rather than a re-implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import read_sandbox_catalog, resolve_tool_document, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .profile_projection import PROFILE_ARCHETYPE, build_profile_projection

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.profile_card.v1"


def _error(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "profile_card", "error": message, "profile": {}}


class ProfileCardViewer:
    """Render a document's value-group-0 profile (SAMRAS id + title + visual) as a card."""

    tool_id = "profile_card"
    label = "Profile Card"
    summary = "Base profile: a SAMRAS id + title + visual from a value-group-0 collecting datum."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Eligible for the deliberately-authored profile archetype and the HOPS filament (whose
    # identity farm_profile projects). farm_profile composes the projection directly, so
    # profile_card need not be palette-exposed to deliver the base contract.
    applies_to_archetype: tuple[str, ...] = (PROFILE_ARCHETYPE, "hops_geospatial_filament")
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _error(err)
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return _error("no sandbox specified")
        doc = resolve_tool_document(
            docs,
            tool=self,
            sandbox=sandbox,
            document_id=document_id,
            canonical_name=None,
        )
        if doc is None:
            return _error("profile document not found")
        return {
            "schema": _SCHEMA,
            "container": "profile_card",
            "sandbox_id": sandbox,
            "document_id": _as_text(doc.document_id),
            "selected_row_address": _as_text(datum_address),
            "profile": build_profile_projection(doc),
        }


# Self-register on import.
register(ProfileCardViewer())
