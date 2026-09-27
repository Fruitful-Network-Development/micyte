"""Objects panel — list + manage typed farm objects (Infrastructure & People).

Reads the agro_erp ``object_profiles`` doc (barns / greenhouses / tunnels / custom areas /
livestock / employees / tractors / custom objects) and renders a compact list with a
"+ New" control; each row opens the editable object **profile page** (open → edit →
save / back-out-without-saving), which POSTs to the ``create_object`` / ``save_object`` /
``delete_object`` agro write actions (TASK-005). Lives on the FARM tab; the fuller summary
hub (TASK-007) will build on this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
from micyte.core.document_naming import document_in_sandbox
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import scoped_to_instance
from ._registry import register
from ._requirements import FARM
from .object_profiles_view import build_object_rows

_SCHEMA = "mycite.v2.portal.workbench.tool.object_manager.v1"
_TENANT = "fnd"

# The typed-object catalog the "+ New" picker offers (grouped for the future hub).
KINDS = [
    {"value": "barn", "label": "Barn", "group": "infrastructure", "geo": True},
    {"value": "greenhouse", "label": "Greenhouse", "group": "infrastructure", "geo": True},
    {"value": "tunnel", "label": "Tunnel", "group": "infrastructure", "geo": True},
    {"value": "custom_area", "label": "Custom area", "group": "infrastructure", "geo": True},
    {"value": "tractor", "label": "Tractor / equipment", "group": "infrastructure", "geo": False},
    {"value": "livestock", "label": "Livestock", "group": "livestock", "geo": False},
    {"value": "employee", "label": "Employee", "group": "people", "geo": False},
    {"value": "custom_object", "label": "Custom object", "group": "other", "geo": False},
]


def _load_object_profiles(authority_db_file: Path | None, sandbox: str):
    if not authority_db_file or not sandbox:
        return None
    store = SqliteSystemDatumStoreAdapter(authority_db_file, allow_legacy_writes=False)
    # ONE sandbox (2026-09-25), scoped to the instance before the name filter: `system`
    # names four instances' core sandbox, so the sandbox filter alone matched every farm's
    # `object_profiles` and returned whichever came first.
    documents = store.read_documents_by_sandbox(tenant_id=_TENANT, sandbox=sandbox)
    return next(
        (d for d in scoped_to_instance(documents)
         if document_in_sandbox(d.document_id, sandbox)
         and d.document_id.split(".")[3] == "object_profiles"),
        None,
    )


class ObjectsViewer:
    """The typed-object list + profile-page launcher (Infrastructure & People)."""

    tool_id = "object_manager"
    writes = (
        DeclaredWrite(document_kind="object", action="create_object"),
        DeclaredWrite(document_kind="object", action="save_object"),
        DeclaredWrite(document_kind="object", action="delete_object"),
    )
    label = "Infrastructure & People"
    summary = "Typed farm objects (barns, greenhouses, tractors, livestock, employees) — list, add, edit, remove."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = FARM

    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament", "samras_taxonomy")
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str, datum_address: str,
        filter_kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        doc = _load_object_profiles(authority_db_file, sandbox_id)
        objects = build_object_rows(doc) if doc is not None else []
        kinds = KINDS
        if filter_kinds:
            allow = set(filter_kinds)
            objects = [o for o in objects if o.get("kind") in allow]
            kinds = [k for k in KINDS if k["value"] in allow]
        return {
            "schema": _SCHEMA,
            "container": "objects_panel",
            "sandbox_id": sandbox_id,
            "objects": objects,
            "kinds": kinds,
            "filter_kinds": list(filter_kinds or []),
            "create_route": "/portal/api/v2/agro/create_object",
            "save_route": "/portal/api/v2/agro/save_object",
            "delete_route": "/portal/api/v2/agro/delete_object",
        }


register(ObjectsViewer())
