"""Local Domain — the SAMRAS lcl id-space, extended with expand-to-table nodes.

``local_domain`` is a standardized tool built ON TOP of the ``samras_structure`` viewer
(which stays exactly as-is). It renders the **lcl** node tree, but nodes carrying a
``rf.3-1-8`` VIEW marker (``contacts`` / ``product_type`` / and the ``records.*_instance``
containers for invoices, contracts, sales and the offering) render a diagonal "expand view"
button instead of the child-dropdown. Expanding one shifts the Agronomics FARM tab into a
full-width gallery/table of that node's child instances — keyed by their lcl-id — with a
back arrow.

The record table is **composition over the existing record viewers**: each VIEW token maps
(:data:`VIEW_DISPATCH`) to the viewer that already reads that datum doc and resolves its
lcl refs (products / invoices / contracts / contacts). :func:`build_record_view` calls that
viewer and normalizes its payload into one shared ``record_table`` whose leading column is
the lcl-id.

A token with no :data:`VIEW_DISPATCH` entry is **not** unknown: it falls through to
:func:`_declared_table`, which builds the same shape from whatever the sandbox's
``record_spec`` document declares. So a record type a tenant defines needs no entry here and
no rendering code — only the VIEW marker its container node already carries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    NODE_KIND_TYPE,
    Markers,
    decode_label,
    iter_marker_pairs,
)
from micyte.core.datum_ops.record_spec import SPEC_DOCUMENT, specs_for
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._shared.utilities import as_text as _as_text
from .product_document_view import ProductDocumentViewer
from .samras_structure_viewer import SamrasStructureViewer

_SCHEMA = "mycite.v2.portal.workbench.tool.local_domain.v1"
#: The SAMRAS structure this viewer renders (not a document name).
_LCL_STRUCTURE = "lcl"


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


def _record_table(viewer: Any, db: Path | None, sandbox: str, *,
                  title: str, noun: str) -> dict[str, Any]:
    """The lcl-id-led table for any :class:`RecordViewerBase` viewer.

    `RecordViewerBase` attaches the raw lcl node of the lead reference as ``r["lcl_id"]``;
    the leading column is that node ADDRESS (the datum denotation), with the resolved
    display columns after it. Written out per record type until there were three of them
    — every copy identical but for a title and a noun, which is the shape of a helper.
    """
    p = viewer.build_panel_payload(
        authority_db_file=db, sandbox_id=sandbox, document_id="", datum_address="",
    )
    if p.get("error"):
        return _table(title, ["lcl_id"], [], noun=noun)
    columns = p.get("columns", [])
    cols = ["lcl_id", *columns]
    rows = [{"lcl_id": _as_text(r.get("lcl_id")), **{c: r.get(c, "") for c in columns}}
            for r in p.get("rows", [])]
    return _table(title, cols, rows, noun=noun)


# VIEW token -> normalizer for the record types a BESPOKE viewer owns. A token with no entry
# here is not unknown — it falls through to `_declared_table`, which builds the same shape from
# whatever the sandbox's `record_spec` document declares.
VIEW_DISPATCH = {
    "product": _product_table,
    # `contacts` fell out of this table when `contacts_viewer` retired (Phase 3b,
    # 2026-08-15): the token now falls through to `_declared_table`, whose built-in
    # RECORD_SPEC floor reads the same 4-5-family rows — one reader instead of two.
    # `invoice` / `sale` / `offering` followed in the old-model pane cleanup, and
    # `contract` in the batch re-point (its ContractsTool spoke the pre-archetype 4-6
    # row; a planting is a ledger row now). NOTE the corrected census: live trees DO
    # declare VIEW tokens — a farm carries contract/invoice/product/contacts, decoded
    # from the bit-encoded VIEW cells (the earlier "zero tokens" census text-searched
    # what the store bit-encodes). Those nodes are exactly why `OWNED_ELSEWHERE` names
    # the modern owner: the editor shows the refusal, never a second dead table.
}


def _declared_table(db: Path | None, sandbox: str, token: str) -> dict[str, Any] | None:
    """The record table for a TENANT-DECLARED type, built from its spec.

    Without this a declared record type would be creatable and invisible: ``create_instance``
    would write its rows and nothing would ever show them. The columns are the declared field
    names in declaration order, led by the lcl id — the same shape every bespoke normalizer
    above produces, so the shared ``record_table`` renderer paints it with no new code.
    """
    from ._archetype import find_named_document, read_sandbox_catalog

    docs, err = read_sandbox_catalog(db, sandbox=sandbox)
    if err:
        return None
    spec_doc = find_named_document(docs, sandbox=sandbox, name=SPEC_DOCUMENT)
    spec = specs_for({SPEC_DOCUMENT: spec_doc}, sandbox_id=sandbox).get(token)
    if spec is None:
        return None

    document = find_named_document(docs, sandbox=sandbox, name=spec.document)
    columns = ["lcl_id", *[f.name for f in spec.fields]]
    rows: list[dict[str, Any]] = []
    for row in (getattr(document, "rows", ()) or ()) if document is not None else ():
        if not _as_text(getattr(row, "datum_address", "")).startswith(spec.row_family + "-"):
            continue
        head = getattr(row, "raw", None)
        head = head[0] if isinstance(head, list) and head and isinstance(head[0], list) else []
        node = ""
        values: list[str] = []
        for marker, magnitude in iter_marker_pairs(head):
            if marker == Markers.LCL_ID and not node:
                node = _as_text(magnitude)
            else:
                values.append(decode_label(magnitude))
        entry = {"lcl_id": node}
        for field, value in zip(spec.fields, [*values, *[""] * len(spec.fields)], strict=False):
            entry[field.name] = value
        rows.append(entry)
    return _table(token.replace("_", " ").title(), columns, rows, noun=token.replace("_", " "))


def build_record_view(token: str, *, authority_db_file: Path | None, sandbox_id: str) -> dict[str, Any] | None:
    """Normalized ``record_table`` for an expanded node's VIEW token, or ``None``."""
    if not _as_text(sandbox_id):
        return None
    fn = VIEW_DISPATCH.get(_as_text(token))
    if fn is None:
        return _declared_table(authority_db_file, _as_text(sandbox_id), _as_text(token))
    return fn(authority_db_file, sandbox_id)


def _affordances(node: dict[str, Any]) -> dict[str, Any]:
    """Which editing verbs a tree node can offer, derived from what the node IS.

    The tree is the navigation AND the selection for editing, so each node has to say what
    can be done at it rather than leaving the client to infer it from the label:

    * ``can_define_type`` — a TYPE node may take a child type. This is how a vocabulary
      grows (a new structure subtype, a new classification value).
    * ``can_create_instance`` — a TYPE node that also carries a VIEW marker may take a
      RECORD. The VIEW marker is the existing, data-carried declaration that a node is an
      instance container and names which record table it opens, so it is exactly the right
      gate: a type with no view has nowhere to put a record and no way to show it.

    An INSTANCE offers neither — a record is not a container. An UNMARKED node offers
    neither either, deliberately: the corpus has not said what it is (`parcel_1..3` are
    marked as types while the identically-shaped `field_1` is marked an instance), and
    offering "create a record here" on a guess is how records land under a node that turns
    out not to be a type at all.
    """
    is_type = node.get("node_kind") == NODE_KIND_TYPE
    return {
        "can_define_type": is_type,
        "can_create_instance": bool(is_type and _as_text(node.get("record_view"))),
    }


class LocalDomainViewer:
    """The lcl id-space tree with expand-to-table instance-container nodes."""

    tool_id = "local_domain"
    label = "Local Domain"
    summary = (
        "The local (lcl) id-space — entity / land / classification — with instance-container "
        "nodes (products, invoices, sales, contracts, contacts) expandable into record tables."
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
            extra_query={"samras_structure": _as_text((extra_query or {}).get("samras_structure")) or _LCL_STRUCTURE},
        )
        if base.get("error"):
            return {**base, "schema": _SCHEMA, "container": "local_tree"}
        return {**base, "schema": _SCHEMA, "container": "local_tree",
                "nodes": [{**node, **_affordances(node)} for node in base.get("nodes", ())]}


# Self-register on import.
# NOT REGISTERED. A tool that merely renders a document's own values has no reason
# to be a tool. Its pane is a viewscope tree of the sandbox's own lcl now. The MODULE stays: `build_record_view` still serves agronomics' local_view takeover, and `lcl_editor` (a writer) composes the viewer directly.
# register(LocalDomainViewer())  # retired TASK-2026-08-06-004 Phase 9
