"""Project Manager — the standing things an instance's jobs are done against.

An `editable_table` over the sandbox's `projects` document. A `job_event` is an entry in a
log; a **project** is a subject with a profile — whose it is, where, what kind, what it is
called, and optionally when it was opened — which is why the operator's tree puts them on
opposite sides of the object/list split, and why `project_profile` was minted as its own
archetype (2026-08-08) and sat unread until this tool (TASK-2026-08-14-002 Phase 3).

Nothing here is trade-specific: the kind is an `lcl_id` the instance mints for itself with
`lcl_editor`, and the customer and site pickers are bounded by the address space exactly as
`job_manager`'s are — the two tables deliberately share those helpers rather than growing a
second copy of the picker rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._editable_table import editable_table, editable_table_error, field
from ._record_view import facet, narrow
from ._registry import register
from ._viewscope import _row_values
from .job_manager import _document_named, _lcl_options, _options, _readable

#: The document a sandbox keeps its projects in, and the archetype every row must be.
#: Declared HERE, in micyte, and imported by the fnd write runtime — never the other way
#: round; the same boundary `job_manager` states for `JOB_LOG`.
PROJECTS = "projects"
PROJECT_ARCHETYPE = "project_profile"

_SCHEMA = "mycite.v2.portal.workbench.tool.project_manager.v1"
_SAVE_ROUTE = "/portal/api/v2/projects/save_project"
_TENANT_DEFAULT = "fnd"


def _project_rows(document: Any, *, sandbox: str, names: Any, archetype: Any,
                  authority: Any = None, people: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        node = next((v for v in values.get("msn_id", ()) if v), "")
        who = (people or {}).get(node) or names.label(node, key_field="msn_id")
        where = names.label(
            next((v for v in values.get("site_msn", ()) if v), ""), key_field="msn_id")
        kind = names.label(
            next((v for v in values.get("lcl_id", ()) if v), ""), key_field="lcl_id")
        stamps = [v for v in values.get("utc", ()) if v]
        # TWO key sets, the `job_manager` rule: the renderer reads `r[<column>]` for display
        # and `r[<field.name>]` for the edit row, and the three whose names differ would
        # otherwise render blank — `test_every_editable_table_column_resolves` covers it.
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            "row": row.datum_address,
            "project": decode_label(next((v for v in values.get("title", ()) if v), "")),
            "title": decode_label(next((v for v in values.get("title", ()) if v), "")),
            "person": who,
            "site": where,
            "customer": who,
            "address": where,
            "kind": kind,
            "opened": _readable(authority, stamps[0]) if stamps else "",
        })
    return rows


class ProjectManager:
    """Open, edit and review projects against the sandbox's own projects document."""

    tool_id = "project_manager"
    label = "Projects"
    summary = "The standing things jobs are done against: whose, where, what kind."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    #: Its OWN document, beyond the CRM floor — which is what lets the install ledger
    #: provision `projects` when the Quiar package lands on an instance that predates it.
    requires = ToolRequirement(
        documents=(
            DocumentRequirement(
                name=PROJECTS, archetype=PROJECT_ARCHETYPE,
                why="the standing things this instance's jobs are done against"),
        ),
    )

    applies_to_archetype: tuple[str, ...] = (PROJECT_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    filter_prefix = "projects"
    #: `row` is the identity column (contacts' shape): the renderer draws the row's
    #: server-assigned address there and `(new)` on the edit row. Without it the
    #: column count was one short of the field count, so `editable_table` REFUSED
    #: the payload — for the tool's whole life, because the only sweep that builds
    #: every table swallowed the refusal and no instance held a `projects` document
    #: until the client instance's install provisioned one and the tab rendered the error.
    table_columns: tuple[str, ...] = ("row", "project", "customer", "address", "kind", "opened")
    search_columns: tuple[str, ...] = ("project", "customer", "address", "kind")
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="project", action="save_project"),
    )

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id
        if authority_db_file is None:
            return editable_table_error(self.schema, "authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            return editable_table_error(self.schema, "no sandbox selected")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from ._viewscope import read_document
        from .job_manager import _people

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        projects_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=PROJECTS)
        if not projects_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {PROJECTS} document yet — installing the Quiar app "
                "provisions one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")

        document = read_document(store, tenant_id=self.tenant_id, document_id=projects_id)
        anchor_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name="anchor")
        authority = None
        if anchor_id:
            from ._hops_dates import chrono_authority

            authority = chrono_authority(
                read_document(store, tenant_id=self.tenant_id, document_id=anchor_id))
        rows = _project_rows(
            document, sandbox=sandbox, names=names,
            archetype=registry.get(PROJECT_ARCHETYPE), authority=authority,
            people=_people(store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry))

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.filter_prefix,
            search_columns=self.search_columns,
            facets=(facet("kind", label="kind", all_label="All kinds"),),
            search_placeholder="Search projects",
        )

        root = as_text((extra_query or {}).get("service_area"))
        options = _options(space, names, root)
        kinds = _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)

        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title="Projects",
            columns=list(self.table_columns),
            fields=[
                field("title", label="project", placeholder="back garden rework",
                      required_text="A project needs a name."),
                field("person", kind="select", label="customer", options_key="site_options",
                      required_text="Pick the customer's node."),
                field("site", kind="select", label="address", options_key="site_options",
                      required_text="Pick the address the project is at."),
                field("kind", kind="select", label="kind", options_key="trade_options",
                      required_text="Pick a kind — add one in the LCL Editor."),
                field("opened", kind="date", label="opened",
                      edit_hint="optional — when the project was opened"),
            ],
            rows=rows, save_route=_SAVE_ROUTE,
            empty_text="No projects yet — use + Open a project.",
            add_label="Open a project",
            filters=controls,
            site_options=options, trade_options=kinds,
            service_area=root,
            options_truncated=max(0, len(space.children.get(root, ())) - len(options)),
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


register(ProjectManager())

__all__ = ["PROJECTS", "PROJECT_ARCHETYPE", "ProjectManager"]
