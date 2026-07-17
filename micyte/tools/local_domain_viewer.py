"""Local Domain — the SAMRAS lcl id-space, extended with expand-to-table nodes.

``local_domain`` is a standardized tool built ON TOP of the ``samras_structure`` viewer
(which stays exactly as-is). It renders the **lcl** node tree, but nodes carrying a
``rf.3-1-8`` VIEW marker (``contacts`` / ``product_type`` / ``records.invoice_instance`` /
``records.contract_instance``) render a diagonal "expand view" button instead of the
child-dropdown. Expanding one shifts the Agronomics FARM tab into a full-width gallery/table
of that node's child instances — keyed by their lcl-id — with a back arrow.

The record table is **composition over the existing record viewers**: each VIEW token maps
(:data:`VIEW_DISPATCH`) to the viewer that already reads that datum doc and resolves its
lcl refs (products / invoices / contracts / contacts). :func:`build_record_view` calls that
viewer and normalizes its payload into one shared ``record_table`` whose leading column is
the lcl-id. Adding a new expandable record type later = one VIEW marker (in the lcl datum
doc) + one :data:`VIEW_DISPATCH` entry — no new rendering code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._registry import register
from ._shared.utilities import as_text as _as_text
from .contacts_viewer import ContactsViewer
from .invoices_viewer import InvoicesViewer
from .product_document_view import ProductDocumentViewer
from .samras_structure_viewer import SamrasStructureViewer

_SCHEMA = "mycite.v2.portal.workbench.tool.local_domain.v1"
_LCL = "lcl"


# --------------------------------------------------------------------------- #
# Record-view normalizers: each returns a shared record_table (lcl-id lead column).
# --------------------------------------------------------------------------- #
def _table(title: str, columns: list[str], rows: list[dict[str, Any]], *, noun: str) -> dict[str, Any]:
    n = len(rows)
    return {
        "schema": _SCHEMA,
        "container": "record_table",
        "title": title,
        "count_label": f"{n} {noun}{'' if n == 1 else 's'}",
        "columns": columns,
        "rows": rows,
        "row_count": n,
        "empty_text": f"No {noun}s.",
    }


def _product_table(db: Path | None, sandbox: str) -> dict[str, Any]:
    p = ProductDocumentViewer().build_panel_payload(
        authority_db_file=db, sandbox_id=sandbox, document_id="", datum_address="",
    )
    if p.get("error"):
        return _table("Product Type", ["lcl_id"], [], noun="product")
    cols = ["lcl_id", "product", "taxonomy", "rotation_group", "propagule",
            "genesis", "ownership", "raunkiaerality", "gestation", "spacing"]
    rows: list[dict[str, Any]] = []
    for prod in p.get("products", []):
        by_field = {f.get("field"): f for f in prod.get("fields", [])}
        pid = by_field.get("product_id", {})
        row = {"lcl_id": _as_text(pid.get("magnitude")), "product": prod.get("product_name") or _as_text(pid.get("resolved"))}
        for f in ("taxonomy_id", "rotation_group", "propagule", "genesis", "ownership", "raunkiaerality", "gestation", "spacing"):
            col = "taxonomy" if f == "taxonomy_id" else f
            fld = by_field.get(f, {})
            row[col] = _as_text(fld.get("resolved")) or _as_text(fld.get("magnitude"))
        rows.append(row)
    return _table("Product Type", cols, rows, noun="product")


def _invoice_table(db: Path | None, sandbox: str) -> dict[str, Any]:
    p = InvoicesViewer().build_panel_payload(
        authority_db_file=db, sandbox_id=sandbox, document_id="", datum_address="",
    )
    if p.get("error"):
        return _table("Invoices", ["lcl_id"], [], noun="invoice")
    # RecordViewerBase attaches the raw lcl node of the lead reference as r["lcl_id"]; the
    # leading column is that node ADDRESS (the datum denotation), with the resolved display
    # columns after it.
    cols = ["lcl_id", *p.get("columns", [])]
    rows = [{"lcl_id": _as_text(r.get("lcl_id")), **{c: r.get(c, "") for c in p.get("columns", [])}}
            for r in p.get("rows", [])]
    return _table("Invoices", cols, rows, noun="invoice line")


def _contract_table(db: Path | None, sandbox: str) -> dict[str, Any]:
    from .contracts_tool import ContractsTool  # lazy: avoids any import-order surprises
    p = ContractsTool().build_panel_payload(
        authority_db_file=db, sandbox_id=sandbox, document_id="", datum_address="",
    )
    if p.get("error"):
        return _table("Contracts", ["lcl_id"], [], noun="contract")
    cols = ["lcl_id", *p.get("columns", [])]
    rows = [{"lcl_id": _as_text(r.get("lcl_id")), **{c: r.get(c, "") for c in p.get("columns", [])}}
            for r in p.get("rows", [])]
    return _table("Contracts", cols, rows, noun="contract")


def _contacts_table(db: Path | None, sandbox: str) -> dict[str, Any]:
    p = ContactsViewer().build_panel_payload(
        authority_db_file=db, sandbox_id=sandbox, document_id="", datum_address="",
    )
    if p.get("error"):
        return _table("Contacts", ["lcl_id"], [], noun="contact")
    rows: list[dict[str, Any]] = []
    for it in p.get("items", []):
        flds = {f.get("label"): f.get("value") for f in it.get("fields", [])}
        # contacts is a record_list; the supplier lcl node is the item subtitle, the name the title.
        rows.append({
            "lcl_id": _as_text(it.get("subtitle")), "name": _as_text(it.get("title")),
            "email": _as_text(flds.get("email")), "phone": _as_text(flds.get("phone")),
            "website": _as_text(flds.get("website")),
        })
    return _table("Contacts", ["lcl_id", "name", "email", "phone", "website"], rows, noun="contact")


# VIEW token -> normalizer. Adding a record type = one entry here + one lcl VIEW marker.
VIEW_DISPATCH = {
    "product": _product_table,
    "invoice": _invoice_table,
    "contract": _contract_table,
    "contacts": _contacts_table,
}


def build_record_view(token: str, *, authority_db_file: Path | None, sandbox_id: str) -> dict[str, Any] | None:
    """Normalized ``record_table`` for an expanded node's VIEW token, or ``None``."""
    fn = VIEW_DISPATCH.get(_as_text(token))
    if fn is None:
        return None
    if not _as_text(sandbox_id):
        return None
    return fn(authority_db_file, sandbox_id)


class LocalDomainViewer:
    """The lcl id-space tree with expand-to-table instance-container nodes."""

    tool_id = "local_domain"
    label = "Local Domain"
    summary = (
        "The local (lcl) id-space — entity / land / classification — with instance-container "
        "nodes (products, invoices, contracts, contacts) expandable into record tables."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    # Same surfacing as the samras viewer it extends.
    applies_to_archetype: tuple[str, ...] = SamrasStructureViewer.applies_to_archetype
    applies_to_source_kind: tuple[str, ...] = ()
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
        # Reuse the SAMRAS viewer wholesale for discovery + tree build (nodes already carry
        # the record_view token via build_magnitude_tree). Default to the lcl structure.
        base = SamrasStructureViewer().build_panel_payload(
            authority_db_file=authority_db_file,
            sandbox_id=sandbox_id,
            document_id=document_id,
            datum_address=datum_address,
            extra_query={"samras_structure": _as_text((extra_query or {}).get("samras_structure")) or _LCL},
        )
        if base.get("error"):
            return {**base, "schema": _SCHEMA, "container": "local_tree"}
        return {**base, "schema": _SCHEMA, "container": "local_tree"}


# Self-register on import.
register(LocalDomainViewer())
