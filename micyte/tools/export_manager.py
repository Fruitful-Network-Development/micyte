"""Export — narrow a document down, SEE what would leave, then take it.

Works on any document whose rows an archetype covers, because that is what makes the
columns nameable: the archetype's logical fields are the column list, and a filter is an
equality on one of them. Your `friend` flag is a cell like any other and nothing here
knows what it means.

**The preview is the product.** A CSV is copied to a spreadsheet, mailed, uploaded — it is
the one surface where data leaves, and the operator has to see the exact rows before they
do. The download route is given the same spec and produces the same rows, so approving the
preview approves what leaves.

An `msn_id` column can EXPAND to a mailing address: `AddressSpace.path` already returns
every present ancestor, so "shows as mailing address" is a join that exists rather than one
this tool invents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops.datum_resolve import as_text
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._export import ADDRESS_FIELDS, MAX_EXPORT_ROWS, ExportSpec, header, rows_for
from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.export.v1"
_DOWNLOAD_ROUTE = "/portal/api/v2/export/csv"
_TENANT_DEFAULT = "fnd"

#: Rows shown in the PREVIEW. Small on purpose: this is the "is this the right set?"
#: question, not the data. The matched count is always exact, so a preview of 50 out of
#: 3,000 says so rather than looking like the whole answer.
PREVIEW_ROWS = 50


def _documents(store: Any, *, tenant_id: str, sandbox: str) -> list[str]:
    with store._connect() as connection:
        return [
            row["name"] for row in connection.execute(
                "SELECT name FROM documents WHERE tenant_id=? AND sandbox=? ORDER BY name",
                (tenant_id, sandbox),
            )
        ]


def _parse_filters(raw: str) -> dict[str, str]:
    """``field=value,field=value`` -> a dict. Empty on anything it cannot parse.

    Refuses rather than guesses: a filter that silently dropped a malformed clause would
    export MORE than the operator asked for, which is the wrong direction to fail in for
    a surface whose output leaves the building.
    """
    out: dict[str, str] = {}
    for clause in as_text(raw).split(","):
        if not clause.strip():
            continue
        field_name, sep, value = clause.partition("=")
        if not sep or not field_name.strip():
            return {}
        out[field_name.strip()] = value.strip()
    return out


class ExportManager:
    """Preview and take a CSV of any archetype-shaped document."""

    tool_id = "export"
    label = "Export"
    summary = "Narrow a document down, see the exact rows, then take a CSV."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "export_preview"
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def empty(reason: str, **extra: Any) -> dict[str, Any]:
            return {"schema": self.schema, "container": self.container,
                    "reason": reason, "rows": [], "columns": [], **extra}

        if authority_db_file is None:
            return empty("authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            return empty("no sandbox selected; an export is scoped to one sandbox")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from ._viewscope import read_document

        query = extra_query or {}
        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        available = _documents(store, tenant_id=self.tenant_id, sandbox=sandbox)
        wanted = as_text(query.get("export_document"))
        if not wanted:
            return empty("pick a document to export", documents=available, sandbox=sandbox)
        if wanted not in available:
            # By NAME, and refused when absent. Falling through to "the first document in
            # the sandbox" is how `planting_map` came to render an anchor in four of seven.
            return empty(f"{sandbox} has no document named {wanted!r}",
                         documents=available, sandbox=sandbox)

        document_id = store.document_id_for(
            tenant_id=self.tenant_id, sandbox=sandbox, name=wanted)
        if not document_id:
            return empty(f"{sandbox} has no document named {wanted!r}",
                         documents=available, sandbox=sandbox)
        document = read_document(store, tenant_id=self.tenant_id, document_id=document_id)
        if document is None:
            return empty(f"{wanted} is in the index but has no payload",
                         documents=available, sandbox=sandbox)

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")

        archetype_name = as_text(query.get("export_archetype")) or registry.primary_archetype(
            document, sandbox=sandbox)
        archetype = registry.get(archetype_name)
        if archetype is None:
            return empty(f"no archetype describes {wanted}'s rows, so its columns have no names",
                         documents=available, sandbox=sandbox)

        columns = tuple(
            c for c in as_text(query.get("export_columns")).split(",") if c.strip()
        ) or tuple(f.removesuffix("+") for f in archetype.maximal_shape.fields)
        expand = tuple(c for c in columns if c in ADDRESS_FIELDS and c != "lcl_id")
        spec = ExportSpec(
            archetype=archetype_name, columns=columns,
            filters=_parse_filters(query.get("export_filter", "")),
            expand=expand, limit=MAX_EXPORT_ROWS,
        )
        rows, matched = rows_for(
            document, spec, sandbox=sandbox, registry=registry, names=names, space=space)

        return {
            "schema": self.schema,
            "container": self.container,
            "sandbox": sandbox,
            "documents": available,
            "document": wanted,
            "archetype": archetype_name,
            "archetypes_available": list(registry.archetypes_for(document, sandbox=sandbox)),
            "columns": header(spec),
            "filters": spec.filters,
            "filter_text": as_text(query.get("export_filter", "")),
            # The preview is a sample; the COUNT is the answer. A cut-off list and a small
            # result set look identical otherwise, and only one means "this is all of them".
            "rows": rows[:PREVIEW_ROWS],
            "preview_rows": min(len(rows), PREVIEW_ROWS),
            "matched": matched,
            "truncated": max(0, matched - len(rows)),
            "download_route": _DOWNLOAD_ROUTE,
            "download_params": {
                "sandbox_id": sandbox, "document": wanted, "archetype": archetype_name,
                "columns": ",".join(columns), "filter": as_text(query.get("export_filter", "")),
            },
        }


register(ExportManager())

__all__ = ["PREVIEW_ROWS", "ExportManager"]
