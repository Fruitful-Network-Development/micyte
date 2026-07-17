"""Invoice Viewer — agro_erp supply-invoice line items (record_table).

A thin :class:`RecordViewerBase` subclass: the base owns the catalog-read/resolve/envelope
preamble and the spec-driven projection; this supplies only the column spec. Reads the
``invoices`` doc (``4-7-N`` vg-7 rows since the event-type append), resolving the
invoice / product / supplier lcl refs and the event-type to names, decoding the nominal
weight/cost. The invoice name embeds its date, so the HOPS-UTC date stays a hidden column.
"""

from __future__ import annotations

from ._registry import register
from .record_viewer import DATE, EVENT, LCL, NOMINAL, RecordViewerBase


class InvoicesViewer(RecordViewerBase):
    tool_id = "invoices"
    label = "Invoice Viewer"
    summary = "Supply invoice line items — product, supplier, weight, cost and event-type."
    schema = "mycite.v2.portal.workbench.tool.invoices.v1"
    canonical_name = "invoices"
    applies_to_archetype: tuple[str, ...] = ("mycite.v2.datum.agro_erp.invoices.v1",)
    row_prefix = "4-7-"
    title = "Invoices"
    noun = "line item"
    # head order: invoice, date, product, weight, cost, supplier, event.
    column_spec = (
        ("invoice", LCL), ("date", DATE), ("product", LCL),
        ("weight", NOMINAL), ("cost", NOMINAL), ("supplier", LCL), ("event", EVENT),
    )
    display_columns = ("invoice", "product", "supplier", "weight", "cost", "event")


register(InvoicesViewer())
