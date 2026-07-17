"""Onboarding — a base WRITE tool that COLLECTS fields and scaffolds a new sandbox.

``OnboardingTool`` is the rudimentary base (the abstraction seam the operator wants):
it owns the ``record_form`` envelope + a submit action to a create/onboard route, and a
subclass supplies only the field spec + the route. :class:`FarmOnboardingTool` specialises
it into farm onboarding — it collects a farm's name, sandbox token, registrar msn node and
(optional) parcels, and posts to ``/portal/api/v2/agro/create_farm``, which clones the
standardized ``trapp_family_farm`` template into a new blank farm-profile sandbox
(``scripts/bootstrap_farm_sandbox``). Same base can later specialise into other onboarding
flows (grantee, entity) without new client code — it reuses the shared ``record_form`` renderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._registry import register


class OnboardingTool:
    """Base: a ``record_form`` that collects fields and POSTs to a create/onboard route."""

    tool_id = ""
    label = ""
    summary = ""
    route = WORKBENCH_UI_TOOL_ROUTE
    # Universal: reachable from any sandbox (incl. an empty one) via the direct ?tool= path.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = ""
    title = "Onboard"
    intro = ""
    submit_route = ""
    submit_label = "Create"

    def onboarding_fields(self, *, extra_query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "container": "record_form",
            "sandbox_id": sandbox_id or "",
            "title": self.title,
            "intro": self.intro,
            "fields": self.onboarding_fields(extra_query=extra_query),
            "submit_label": self.submit_label,
            "submit_action": {"route": self.submit_route, "sandbox_id": sandbox_id or ""},
        }


class FarmOnboardingTool(OnboardingTool):
    """Onboard a new farm: clone the standardized template into a blank farm-profile sandbox."""

    tool_id = "farm_onboarding"
    label = "Farm Onboarding"
    summary = "Onboard a new farm — a blank farm-profile sandbox cloned from the standardized template."
    schema = "mycite.v2.portal.workbench.tool.farm_onboarding.v1"
    title = "Farm Onboarding"
    intro = (
        "Create a new farm as its own sandbox, cloned from the standardized "
        "trapp_family_farm template and keyed by the farm's registrar msn node. "
        "Optionally seed its property boundary from parcels."
    )
    submit_route = "/portal/api/v2/agro/create_farm"
    submit_label = "Create farm"

    def onboarding_fields(self, *, extra_query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [
            {"key": "title", "label": "Farm name (e.g. wolf_family_sustainable_farm_llc)",
             "type": "text", "value": ""},
            {"key": "sandbox", "label": "Sandbox token (e.g. wolf_family_sustainable_farm)",
             "type": "text", "value": ""},
            {"key": "msn_id", "label": "Registrar msn node (e.g. 1-2-3-4-5-6-7-8-9-0)",
             "type": "text", "value": ""},
            {"key": "parcels", "label": "Parcels JSON — [{name, ring:[[lat,lon],…]}] (optional)",
             "type": "text", "value": ""},
        ]


register(FarmOnboardingTool())
