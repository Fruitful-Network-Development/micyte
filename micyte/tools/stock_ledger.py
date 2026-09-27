"""Brevat's STOCK tab — what came in, what went out, and what is on hand.

TASK-2026-09-12-001 B3. Operator, 2026-09-12: *"a singular log datum doc would contain
event entries of supply or output and denote a lcl_id to which it refers ... and the
entries would include a msn_id for who the supplier was or who the buyer was"*.

An `editable_table` over the sandbox's one ``stock_log`` document, beside the Products
table that says what each node IS. The two are joined by the product node and by nothing
else: this tab holds movements and no measure, because the measure is the product
profile's ``nominal`` and a count restated with its unit here would be a second denotation
of one fact — the rule `SubscriptionBook` states about state and quantity.

The KIND is chosen from the instance's own ``stock_events`` vocabulary, which the
convention seeds and the Domain editor shows, so an instance that mints a kind of its own
sees it in this form the moment it exists. A kind whose direction
:data:`micyte.core.datum_ops.stock_log.DIRECTIONS` does not declare is refused by the
writer rather than accepted and left out of the total.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.stock_log import (
    DIRECTIONS,
    ENTRY_ARCHETYPE,
    STOCK_DOCUMENT,
    read_log,
)
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._editable_table import editable_table, editable_table_error, field
from ._record_view import facet, narrow
from ._registry import register
from ._shared.utilities import as_text
from .job_manager import _lcl_options

_SCHEMA = "mycite.v2.portal.workbench.tool.stock_log.v1"
_SAVE_ROUTE = "/portal/api/v2/ledger"
_TENANT_DEFAULT = "fnd"


class StockLedger:
    """The instance's stock movements, appendable."""

    tool_id = "stock_log"
    label = "Stock"
    summary = "What came in and what went out, one row per event — and what is on hand."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    applies_to_archetype: tuple[str, ...] = (ENTRY_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=STOCK_DOCUMENT, archetype=ENTRY_ARCHETYPE,
            why="what came in and what went out — the log the on-hand figure is summed from"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="stock_log", action="record_stock"),
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
        from micyte.core import archetypes as arc
        from micyte.core.datum_ops import field_registry as _fr
        from micyte.core.datum_ops import local_domain as _ld
        from micyte.core.instance_scope import resolve_msn

        from . import _node_names as nn
        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        msn = resolve_msn()
        doc_id = store.document_id_for(
            tenant_id=self.tenant_id, msn_id=msn, sandbox=sandbox, name=STOCK_DOCUMENT)
        if not doc_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {STOCK_DOCUMENT} document yet — installing the Brevat "
                "app provisions one, and this table appends to it rather than creating it")
        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        tree_id = store.document_id_for(
            tenant_id=self.tenant_id, msn_id=msn, sandbox=sandbox, name="lcl_domain")
        labels: dict[str, str] = {}
        kinds: dict[str, str] = {}
        if tree_id:
            log = _ld.read_log(read_document(store, tenant_id=self.tenant_id, document_id=tree_id))
            labels = {n: as_text(e.label) for n, e in log.entries.items()}
            if log.class_root:
                kind_node = next((n for n, e in log.children_of(log.class_root).items()
                                  if as_text(e.label) == "stock_events"), "")
                if kind_node:
                    kinds = {as_text(e.label): n
                             for n, e in log.children_of(kind_node).items()}
        try:
            namespace = _fr.namespace_for_sandbox(sandbox, msn_id=msn)
        except KeyError as exc:
            return editable_table_error(self.schema, f"this sandbox cannot spell a movement ({exc})")
        movements = read_log(
            read_document(store, tenant_id=self.tenant_id, document_id=doc_id),
            registry=registry, namespace=namespace, labels=labels)
        balances = movements.balances()

        rows: list[dict[str, Any]] = []
        # Newest first: a log IS an event series, so the last thing that happened is the
        # thing an operator opening the tab is looking for — the reversal the sale table
        # takes and the offering table deliberately does not.
        for event in reversed(movements.events):
            on_hand = balances.get(event.product)
            rows.append({
                "datum_address": event.address,
                "product": names.label(event.product, key_field="lcl_id") or event.product,
                "product_node": event.product,
                "kind": event.kind_name or event.kind,
                "count": str(event.count),
                "way": "in" if (event.signed or 0) > 0 else ("out" if event.signed else "?"),
                "party": names.label(event.party, key_field="msn_id") or event.party,
                "day": event.day,
                "note": event.note,
                "on_hand": "unknown" if on_hand is None else str(on_hand),
            })
        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.tool_id,
            search_columns=("product", "kind", "party", "note"),
            facets=(facet("kind", label="Event"), facet("way", label="Direction")),
            search_placeholder="Search movements",
        )
        known = [k for k in kinds if k in DIRECTIONS]
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title="Stock",
            columns=["day", "product", "kind", "count", "party", "on_hand", "note"],
            fields=[
                field("product", kind="select", label="product", options_key="trade_options",
                      required_text="Pick a product — the Products tab says what each node is."),
                field("kind", kind="select", options_key="kind_options",
                      required_text="Say what happened: a delivery, a sale, a loss."),
                field("count", placeholder="12",
                      required_text="How many, in the product's own measure.",
                      edit_hint="a whole number; which way it moves is the event, not a sign"),
                field("day", placeholder="2026-09-12",
                      required_text="A movement happened on a day."),
                # SAID, not picked. `job_manager`'s own lesson: a bounded picker called
                # with no root offers hemispheres, and the counterparty of a movement is
                # somebody the operator already knows the address of.
                field("party", placeholder="3-2-3-17-77-…",
                      edit_hint="optional — the supplier or the buyer, as an msn address"),
                field("note", placeholder="optional"),
            ],
            rows=rows, save_route=f"{_SAVE_ROUTE}/record_stock",
            empty_text=("Nothing recorded yet — use + Record a movement. What is on hand is "
                        "summed from these rows, so the first one is where the figure starts."),
            add_label="Record a movement",
            filters=controls,
            trade_options=_lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox),
            kind_options=[{"value": k, "label": k.replace("_", " ")} for k in sorted(known)],
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


register(StockLedger())

__all__ = ["StockLedger"]
