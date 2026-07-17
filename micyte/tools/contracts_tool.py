"""Contract Viewer + create-builder for agro_erp.

A :class:`RecordViewerBase` subclass over the ``contracts`` doc (``4-6-N`` vg-6 since the
event-type append: ``date, invoice_id, plot_id, amount, cost, event``). The base renders the
record_table (refs → names, nominals decoded, event-type surfaced); this subclass adds an
**invoice weight draw-down** as an ``extra_tables`` entry (purchased weight minus committed
contract amounts). ``build_contract_row`` is the pure unit a create-form / ingest mints.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import NameIndex, cached_index, decode_label

from ._agro_events import EVENT_INVESTMENT
from ._archetype import find_named_document
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .record_viewer import DATE, EVENT, LCL, NOMINAL, RecordViewerBase

_SCHEMA = "mycite.v2.portal.workbench.tool.contracts.v1"
_RF_UTC = "rf.3-1-6"
_RF_LCL_ID = "rf.3-1-5"
_RF_NOMINAL = "rf.3-1-7"
_NOMINAL_BITS = 136
_INVOICES_PREFIX = "4-7-"  # post event-type append


def _encode_bits(label: str, *, bits: int) -> str:
    raw = "".join(format(b, "08b") for b in label.encode("ascii"))
    if len(raw) > bits:
        raise ValueError(f"value {label!r} exceeds {bits} bits")
    return raw.ljust(bits, "0")


def build_contract_row(
    addr: str,
    *,
    hops_date: str,
    invoice_node: str,
    plot_node: str,
    amount: str,
    cost: str,
    label: str,
    event_node: str = EVENT_INVESTMENT,
):
    """Pure builder for a contract datum (vg=6: date, invoice, plot, amount, cost, event).

    The trailing ``(rf.3-1-5, event_node)`` pair classifies the record's event-type
    (default investment ``1-3-2-3``). The unit a create-form mints.
    """
    from micyte.ports.datum_store import AuthoritativeDatumDocumentRow
    head = [
        addr,
        _RF_UTC, hops_date,
        _RF_LCL_ID, invoice_node,
        _RF_LCL_ID, plot_node,
        _RF_NOMINAL, _encode_bits(amount, bits=_NOMINAL_BITS),
        _RF_NOMINAL, _encode_bits(cost, bits=_NOMINAL_BITS),
        _RF_LCL_ID, event_node,
    ]
    return AuthoritativeDatumDocumentRow(datum_address=addr, raw=[head, [label]])


def _parse_weight(text: str) -> float:
    """Best-effort numeric prefix of a weight/amount string ('25 lbs' -> 25.0)."""
    num = ""
    for ch in _as_text(text).strip():
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    try:
        return float(num) if num else 0.0
    except ValueError:
        return 0.0


def _invoice_weights(invoices: Any, lcl: NameIndex) -> dict[str, dict[str, Any]]:
    """invoice lcl-node -> {label, weight} from the invoices ``4-7-*`` rows (marker-driven)."""
    out: dict[str, dict[str, Any]] = {}
    if invoices is None:
        return out
    for row in getattr(invoices, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith(_INVOICES_PREFIX):
            continue
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
        markers = [(_as_text(head[i]), head[i + 1]) for i in range(1, len(head) - 1, 2)]
        invoice_node = next((_as_text(v) for m, v in markers if m == _RF_LCL_ID), "")
        nominals = [v for m, v in markers if m == _RF_NOMINAL]
        weight = decode_label(nominals[0]) if nominals else ""
        if invoice_node:
            out[invoice_node] = {
                "label": lcl.resolve(invoice_node) or invoice_node,
                "weight": _parse_weight(weight),
                "weight_text": weight,  # raw "25 lbs" — the unit-aware draw-down guard reads this
            }
    return out


def _draw_down(inv_weights: dict[str, dict[str, Any]], committed: dict[str, float]) -> list[dict[str, Any]]:
    """Per-invoice purchased weight minus committed contract amounts."""
    rows: list[dict[str, Any]] = []
    for node in sorted(set(inv_weights) | set(committed)):
        info = inv_weights.get(node, {"label": node, "weight": 0.0})
        used = committed.get(node, 0.0)
        weight = info.get("weight", 0.0)
        rows.append({
            "invoice": info["label"],
            "purchased_weight": weight,
            "committed": used,
            "remaining": round(weight - used, 6),
            "over_committed": used > weight,
        })
    return rows


class ContractsTool(RecordViewerBase):
    """View contracts binding farm plots to invoices, with an invoice weight draw-down."""

    tool_id = "contracts"
    label = "Contract Viewer"
    summary = "Contracts binding farm plots to invoices, with weight draw-down."
    schema = _SCHEMA
    canonical_name = "contracts"
    applies_to_archetype: tuple[str, ...] = ("mycite.v2.datum.agro_erp.contracts.v1",)
    row_prefix = "4-6-"
    title = "Contracts"
    noun = "contract"
    # head order: date, invoice, plot, amount, cost, event.
    column_spec = (
        ("date", DATE), ("invoice", LCL), ("plot", LCL),
        ("amount", NOMINAL), ("cost", NOMINAL), ("event", EVENT),
    )
    display_columns = ("date", "invoice", "plot", "amount", "cost", "event")

    def empty_body(self) -> dict[str, Any]:
        return {"container": self.container, "columns": [], "rows": [], "row_count": 0, "extra_tables": []}

    def shape_payload(self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any]:
        base = super().shape_payload(doc=doc, docs=docs, sandbox=sandbox, datum_address=datum_address)
        lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))
        invoices = find_named_document(docs, sandbox=sandbox, name="invoices")
        inv_weights = _invoice_weights(invoices, lcl)
        committed: dict[str, float] = {}
        for row in getattr(doc, "rows", ()) or ():
            if not _as_text(row.datum_address).startswith(self.row_prefix):
                continue
            head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
            invoice_node = ""
            amount = ""
            for i in range(1, len(head) - 1, 2):
                m, v = _as_text(head[i]), head[i + 1]
                if m == _RF_LCL_ID and not invoice_node:
                    invoice_node = _as_text(v)  # first lcl ref = invoice
                elif m == _RF_NOMINAL and not amount:
                    amount = decode_label(v)     # first nominal = amount
            committed[invoice_node] = committed.get(invoice_node, 0.0) + _parse_weight(amount)
        base["extra_tables"] = [{
            "title": "Invoice draw-down",
            "columns": ["invoice", "purchased_weight", "committed", "remaining"],
            "rows": _draw_down(inv_weights, committed),
        }]
        return base


# Self-register on import.
register(ContractsTool())
