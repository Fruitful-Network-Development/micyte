"""Record Studio — a base WRITE tool: a form that creates or edits record datum rows.

Where Record Viewer/Synopsis READ record docs, Record Studio emits a ``record_form`` payload
(field spec + a submit action) the client posts to a domain write route. :class:`ContractEditor`
develops it into the agronomics contract create/edit form (date / invoice / referent (a cluster
OR a plot) / amount / cost); empty to create, pre-filled (``?edit=<datum_address>``) to edit. It
posts to ``/portal/api/v2/agro/save_contract`` which HOPS-encodes the date, builds the row via
``contracts_tool.build_contract_row`` (event = investment), and inserts/updates it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    cached_index,
    decode_label,
    iter_marker_pairs,
)
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._agro_events import EVENT_INVESTMENT  # noqa: F401  (the event the save route stamps)
from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head


def _options_by_prefix(lcl_doc: Any, *prefixes: str) -> list[dict[str, str]]:
    """[{value: node, label: name}] for lcl definition nodes under any of ``prefixes``."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in getattr(lcl_doc, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith("4-2-"):
            continue
        head = _row_head(row)
        if len(head) < 3:
            continue
        node = _as_text(head[2])
        if node in seen or not any(node.startswith(p) and node != p for p in prefixes):
            continue
        seen.add(node)
        label = _as_text(row.raw[1][0]) if len(row.raw) > 1 and row.raw[1] else node
        out.append({"value": node, "label": f"{label} ({node})"})
    out.sort(key=lambda o: o["value"])
    return out


class RecordStudioBase:
    """Emit a ``record_form`` (fields + submit_action) for create/edit of a record doc."""

    tool_id = ""
    label = ""
    summary = ""
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = ""
    title = "Record"
    submit_route = ""
    submit_label = "Save"

    def fields(self, *, docs: list[Any], sandbox: str, edit: dict[str, Any] | None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _load_edit(self, *, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any] | None:
        return None

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id="fnd")
        if err:
            return {"schema": self.schema, "error": err, "container": "record_form", "fields": []}
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return {"schema": self.schema, "error": "no sandbox specified", "container": "record_form", "fields": []}
        edit_addr = _as_text((extra_query or {}).get(f"{self.tool_id}_edit"))
        edit = self._load_edit(docs=docs, sandbox=sandbox, datum_address=edit_addr) if edit_addr else None
        return {
            "schema": self.schema,
            "container": "record_form",
            "sandbox_id": sandbox,
            "title": self.title + (" — edit" if edit else " — create"),
            "fields": self.fields(docs=docs, sandbox=sandbox, edit=edit),
            "submit_label": self.submit_label,
            "submit_action": {"route": self.submit_route, "sandbox_id": sandbox,
                              "datum_address": edit_addr},
        }


class ContractEditor(RecordStudioBase):
    tool_id = "contract_editor"
    label = "Contract Editor"
    summary = "Create or edit a contract (date / invoice / cluster-or-plot referent / amount / cost)."
    applies_to_archetype = ("mycite.v2.datum.agro_erp.contracts.v1",)
    schema = "mycite.v2.portal.workbench.tool.contract_editor.v1"
    title = "Contract"
    submit_route = "/portal/api/v2/agro/save_contract"
    submit_label = "Save contract"

    def fields(self, *, docs: list[Any], sandbox: str, edit: dict[str, Any] | None) -> list[dict[str, Any]]:
        lcl = find_named_document(docs, sandbox=sandbox, name="lcl")
        invoices = _options_by_prefix(lcl, "1-1-6-1-")          # invoice_instance nodes
        referents = _options_by_prefix(lcl, "1-2-5-", "1-2-4-")  # clusters + plots
        e = edit or {}
        return [
            {"key": "date", "label": "Date (MM-DD-YYYY)", "type": "text", "value": e.get("date", "")},
            {"key": "invoice_node", "label": "Invoice", "type": "select", "options": invoices,
             "value": e.get("invoice_node", "")},
            {"key": "referent_node", "label": "Cluster or plot", "type": "select", "options": referents,
             "value": e.get("referent_node", "")},
            {"key": "amount", "label": "Amount (e.g. 10 lbs)", "type": "text", "value": e.get("amount", "")},
            {"key": "cost", "label": "Cost (e.g. $40.00)", "type": "text", "value": e.get("cost", "")},
        ]

    def _load_edit(self, *, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any] | None:
        doc = find_named_document(docs, sandbox=sandbox, name="contracts")
        if doc is None:
            return None
        row = next((r for r in getattr(doc, "rows", ()) or () if _as_text(r.datum_address) == datum_address), None)
        if row is None:
            return None
        lcl_refs: list[str] = []
        nominals: list[str] = []
        date = ""
        for marker, value in iter_marker_pairs(_row_head(row)):
            m = _as_text(marker).lower()
            if m == "rf.3-1-6":
                date = _as_text(value)
            elif m == "rf.3-1-5":
                lcl_refs.append(_as_text(value))
            elif m == "rf.3-1-7":
                nominals.append(decode_label(value))
        # head order: date, invoice, referent(plot/cluster), amount, cost, event.
        return {
            "date": date, "invoice_node": lcl_refs[0] if lcl_refs else "",
            "referent_node": lcl_refs[1] if len(lcl_refs) > 1 else "",
            "amount": nominals[0] if nominals else "", "cost": nominals[1] if len(nominals) > 1 else "",
        }


register(ContractEditor())
# cached_index import kept available for future field resolution.
_ = cached_index
