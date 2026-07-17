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
    iter_marker_pairs,
)

from ._archetype import find_named_document
from ._contract import DatumDocTool
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

# column kinds
LCL = "lcl"        # lcl node ref → name via lcl NameIndex
TXA = "txa"        # txa node ref → name via txa NameIndex
NOMINAL = "nominal"  # 136-bit ASCII nominal (weight/cost/amount) → text
DATE = "date"      # HOPS-UTC token (raw passthrough)
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
        if kind == NOMINAL:
            return decode_label(value)
        return _as_text(value)

    # column kind → the head marker it consumes (lcl and event share the lcl-id marker).
    _KIND_MARKER = {LCL: Markers.LCL_ID, EVENT: Markers.LCL_ID, TXA: Markers.NODE_ID,
                    NOMINAL: Markers.NOMINAL, DATE: Markers.UTC}

    def project_rows(self, *, doc: Any, lcl: Any, txa: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in getattr(doc, "rows", ()) or ():
            if not _as_text(row.datum_address).startswith(self.row_prefix):
                continue
            # Bucket head pairs BY MARKER (order-independent): a reordered or missing middle
            # pair no longer shifts every following column the way a positional zip would.
            buckets: dict[str, list[Any]] = {}
            for marker, value in iter_marker_pairs(_row_head(row)):
                buckets.setdefault(_as_text(marker).lower(), []).append(value)
            cursor: dict[str, int] = {}
            rec: dict[str, Any] = {}
            lead_node = ""
            for col, kind in self.column_spec:
                mk = self._KIND_MARKER.get(kind, "")
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
        lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))
        txa = cached_index(find_named_document(docs, sandbox=sandbox, name="txa"))
        rows = self.project_rows(doc=doc, lcl=lcl, txa=txa)
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
