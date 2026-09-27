"""Record Viewer — shared base for agro_erp record tables (invoices, contracts).

A *record* doc holds same-shaped entries: an ordered list of ``(marker, magnitude)`` head
pairs. This base projects them into a declarative ``record_table`` from one positional
``column_spec`` — each ``(col, kind)`` maps the head pair at that position, resolving lcl/txa
node refs to names, decoding nominals, and surfacing the event-type. :class:`InvoiceViewer`
and :class:`ContractViewer` are thin subclasses (spec + row-prefix + labels); the contract
viewer adds an invoice weight draw-down as an extra table.

Built on :class:`DatumDocTool` (canonical-name doc resolution + standard envelope); the only
subclass surface is the declarative spec, so a new record type is a few lines, no new walk.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    Markers,
    cached_index,
    decode_label,
    marker_buckets,
)
from micyte.core.datum_ops.fiat_datum import FiatChainError, find_fiat_chain, format_cents

from ._archetype import find_anchor, find_local_domain, find_named_document
from ._contract import DatumDocTool
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

# column kinds
LCL = "lcl"        # lcl node ref → name via lcl NameIndex
TXA = "txa"        # txa node ref → name via txa NameIndex
NOMINAL = "nominal"  # 136-bit ASCII nominal (weight/amount/unit) → text. NOT money: a
                     # cost or a price is a FIAT magnitude, below.
TEXT = "text"      # 512-bit ASCII title babelette (free text that is not a value) → text
DATE = "date"      # HOPS-UTC token (raw passthrough)
FIAT = "fiat"      # a price magnitude in cents against the sandbox's fiat datum → "$4.50"
EVENT = "event"    # lcl event_classification ref → name via lcl NameIndex


class RecordViewerBase(DatumDocTool):
    """Project a record doc's same-shaped entries into a ``record_table``."""

    container = "record_table"
    row_prefix: str = ""
    # Ordered spec, one entry per head pair: (column_name, kind).
    column_spec: tuple[tuple[str, str], ...] = ()
    # Columns to show, in order (default: every spec column).
    display_columns: tuple[str, ...] = ()
    title: str = "Records"
    noun: str = "record"

    def empty_body(self) -> dict[str, Any]:
        return {"container": self.container, "columns": [], "rows": [], "row_count": 0}

    @staticmethod
    def _resolve(kind: str, value: Any, lcl: Any, txa: Any) -> str:
        if kind in (LCL, EVENT):
            v = _as_text(value)
            return lcl.resolve(v) or v
        if kind == TXA:
            v = _as_text(value)
            return txa.resolve(v) or v
        if kind in (NOMINAL, TEXT):
            return decode_label(value)
        if kind == FIAT:
            try:
                return format_cents(value)
            except FiatChainError:
                # A magnitude that is not whole cents is shown as it is stored. The cell
                # states the row's problem instead of inventing a price for it.
                return _as_text(value)
        return _as_text(value)

    # column kind → the head marker it consumes (lcl and event share the lcl-id marker).
    #
    # FIAT is deliberately absent: a price marker is not network-wide, it is whichever
    # address THIS sandbox's anchor happened to allocate the fiat babelette at. It is
    # discovered per document set in `shape_payload` and passed in.
    _KIND_MARKER = {LCL: Markers.LCL_ID, EVENT: Markers.LCL_ID, TXA: Markers.NODE_ID,
                    NOMINAL: Markers.NOMINAL, TEXT: Markers.TITLE, DATE: Markers.UTC}

    def project_rows(self, *, doc: Any, lcl: Any, txa: Any,
                     kind_markers: dict[str, str] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in getattr(doc, "rows", ()) or ():
            if not _as_text(row.datum_address).startswith(self.row_prefix):
                continue
            # Bucket head pairs BY MARKER (order-independent): a reordered or missing middle
            # pair no longer shifts every following column the way a positional zip would.
            buckets = marker_buckets(_row_head(row))
            cursor: dict[str, int] = {}
            rec: dict[str, Any] = {}
            lead_node = ""
            markers = {**self._KIND_MARKER, **(kind_markers or {})}
            for col, kind in self.column_spec:
                mk = markers.get(kind, "")
                bucket = buckets.get(mk, [])
                i = cursor.get(mk, 0)
                value = bucket[i] if i < len(bucket) else ""
                cursor[mk] = i + 1
                rec[col] = self._resolve(kind, value, lcl, txa)
                if kind in (LCL, EVENT) and not lead_node:
                    lead_node = _as_text(value)
            # raw lcl node of the lead reference (the record's denotation) — the lcl-id local_domain
            # surfaces as the leading column, distinct from the resolved display name.
            rec["lcl_id"] = lead_node
            rows.append(rec)
        return rows

    def shape_payload(self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any]:
        lcl = cached_index(find_local_domain(docs, sandbox=sandbox))
        txa = cached_index(find_named_document(docs, sandbox=sandbox, name="txa"))
        chain = find_fiat_chain(find_anchor(docs, sandbox=sandbox))
        rows = self.project_rows(
            doc=doc, lcl=lcl, txa=txa,
            kind_markers={FIAT: chain.marker} if chain is not None else {})
        cols = list(self.display_columns) or [c for c, _ in self.column_spec]
        return {
            "container": self.container,
            "title": self.title,
            "count_label": f"{len(rows)} {self.noun}{'' if len(rows) == 1 else 's'}",
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "empty_text": f"No {self.noun}s.",
        }
