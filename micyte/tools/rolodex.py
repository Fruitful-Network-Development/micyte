"""``rolodex`` — every person this INSTANCE deals with, across all of its sandboxes.

An INSTRUMENT, not a tool of a sandbox (:mod:`micyte.tools._instruments`). A sandbox's
``contacts`` document is edited where it lives — ``contacts_manager``, reached by opening
that document — and this answers the question no single sandbox can: *who does this
instance know*.

It existed before, as a rail tool, and was deleted on 2026-08-16 when the Compendium
redesign moved every per-document capability into the document layer. The deletion note
recorded that its reading primitive stayed: ``micyte.tools._sandboxes`` exists, in its own
words, because "the rolodex reads every sandbox's contacts, the unpinned calendar reads
every sandbox's logs". The operator named the category on 2026-08-20 — "artifacts that
allow an instance to interface with specific TYPES of datum information from different
sandboxes" — which is what this always was.

READ ONLY, deliberately. A save here would need to know which sandbox's document a row
belongs to and would be a second writer of a document ``contacts_manager`` already owns;
the row names its sandbox and opening that sandbox's contacts is one click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.instance_scope import use_instance
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._record_view import facet, narrow
from ._registry import register
from ._sandboxes import instance_msn_and_sandboxes
from ._viewscope import read_document
from .contacts_manager import CONTACT_ARCHETYPE, CONTACTS, contact_rows
from .local_domain_viewer import _table

TOOL_ID = "rolodex"
_SCHEMA = "mycite.v2.portal.workbench.tool.rolodex.v1"
_TENANT = "fnd"

#: What the instrument DRAWS. `sandbox` leads because it is the column a per-sandbox table
#: cannot have, and it is the only reason to be looking here rather than at one.
COLUMNS: tuple[str, ...] = ("sandbox", "name", "email", "phone", "city", "county")


def _notice(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "notice": message,
            "columns": [], "rows": [], "row_count": 0}


def _rows_across(store: Any, *, msn: str, sandboxes: tuple[str, ...]) -> list[dict[str, Any]]:
    """Every sandbox's contacts, each row carrying which sandbox it came from.

    The whole read is inside ``use_instance``: the names being iterated include ``system``,
    which four instances hold, and a read outside the scope raises AmbiguousSandboxError
    exactly as it should.
    """
    rows: list[dict[str, Any]] = []
    library = store.read_documents_by_sandbox(tenant_id=_TENANT, sandbox=arc.ARCHETYPE_SANDBOX)
    archetype = arc.registry_for(library).get(CONTACT_ARCHETYPE)
    for sandbox in sandboxes:
        document_id = store.document_id_for(
            tenant_id=_TENANT, sandbox=sandbox, name=CONTACTS, msn_id=msn)
        if not document_id:
            continue
        document = read_document(store, tenant_id=_TENANT, document_id=document_id)
        for row in contact_rows(document, sandbox=sandbox, archetype=archetype):
            rows.append({**row, "sandbox": sandbox})
    return rows


class Rolodex:
    """Every contact this instance holds, wherever it keeps them."""

    tool_id = TOOL_ID
    schema = _SCHEMA
    container = "record_table"
    label = "Rolodex"
    route = WORKBENCH_UI_TOOL_ROUTE
    summary = "Everyone this instance deals with, across every sandbox it keeps."
    tenant_id = _TENANT
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    writes: tuple = ()
    #: Meaningful wherever there is a contacts document to read. `documents_any` rather
    #: than `documents`, because an instrument spans sandboxes: requiring ALL of them to
    #: hold one would hide it on every instance that keeps its people in one place.
    requires = ToolRequirement(
        documents_any=(
            DocumentRequirement(
                name=CONTACTS, archetype=CONTACT_ARCHETYPE,
                why="the people this instance deals with; the rolodex reads every "
                    "sandbox's copy and says which is whose",
            ),
        )
    )

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id, datum_address
        if authority_db_file is None:
            return _notice("authority database not configured")
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        msn, sandboxes = instance_msn_and_sandboxes(
            store, tenant_id=self.tenant_id, active_sandbox=as_text(sandbox_id))
        with use_instance(msn) if msn else _no_scope():
            rows = _rows_across(store, msn=msn, sandboxes=sandboxes)

        titles: dict[str, str] = {}
        for row in rows:
            for key, title in (("city_msn", "city"), ("county_msn", "county")):
                if row.get(key):
                    titles[as_text(row[key])] = as_text(row[title]) or as_text(row[key])
        rows, controls = narrow(
            rows, query=extra_query, param_prefix="rolodex",
            search_columns=("name", "email", "phone", "city", "sandbox"),
            facets=(facet("sandbox", label="sandbox", all_label="Every sandbox"),
                    facet("county_msn", label="county", all_label="All counties",
                          titles=titles)),
            search_placeholder="Search contacts",
        )
        table = _table("Rolodex", list(COLUMNS), rows, noun="contact")
        table["schema"] = self.schema
        table["filters"] = controls
        # WHERE each row is kept, as a link. An instrument spans sandboxes, so "which
        # sandbox is this person in" is the one question it must answer with an address
        # rather than a word -- editing happens there, not here.
        table["sandbox_route"] = WORKBENCH_UI_TOOL_ROUTE
        return table


class _no_scope:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: Any) -> bool:
        return False


register(Rolodex())

__all__ = ["COLUMNS", "TOOL_ID", "Rolodex"]
