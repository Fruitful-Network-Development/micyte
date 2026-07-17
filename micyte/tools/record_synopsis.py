"""Record Synopsis — a small DERIVED-FIGURE summary of a record doc (not a full table).

Where a Record Viewer lists every row, a Record Synopsis distils record entries into a short
set of ``{label, figure}`` figures. :class:`InventorySynopsis` derives, per purchased product,
how many discrete units the procurement invoices represent — count-unit purchases (slips/roots)
are direct; mass purchases are ``grams(weight) // grams(per-unit weight)`` using the product's
``singular_unit_weight`` estimate (units.py). Rendered as the far-right widget on the PLAN tab.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    Markers,
    cached_index,
    decode_label,
    iter_marker_pairs,
)
from micyte.core.datum_ops.units import derive_unit_count

from ._agro_events import EVENT_PROCUREMENT
from ._archetype import find_named_document
from ._contract import DatumDocTool
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from .product_document_view import build_product_rows

_INVOICES_PREFIX = "4-7-"


class RecordSynopsisBase(DatumDocTool):
    """Project a record doc into a compact list of derived figures (container ``synopsis``)."""

    container = "synopsis"
    title: str = "Synopsis"
    value_label: str = "value"
    empty_text: str = "Nothing to summarize."

    def empty_body(self) -> dict[str, Any]:
        return {"container": self.container, "items": [], "item_count": 0}

    def synthesize(self, *, doc: Any, docs: list[Any], sandbox: str) -> list[dict[str, Any]]:
        """Return ``[{label, figure}, …]`` derived from the record doc. Subclass implements."""
        raise NotImplementedError

    def shape_payload(self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any]:
        items = self.synthesize(doc=doc, docs=docs, sandbox=sandbox)
        return {
            "container": self.container,
            "title": self.title,
            "value_label": self.value_label,
            "count_label": f"{len(items)} product{'' if len(items) == 1 else 's'}",
            "items": items,
            "item_count": len(items),
            "empty_text": self.empty_text,
        }


class InventorySynopsis(RecordSynopsisBase):
    tool_id = "inventory_synopsis"
    label = "Inventory Synopsis"
    summary = "Per-product unit counts derived from procurement invoices (weight ÷ unit weight)."
    schema = "mycite.v2.portal.workbench.tool.inventory_synopsis.v1"
    canonical_name = "invoices"  # primary record doc = the procurement invoices
    applies_to_archetype: tuple[str, ...] = ("mycite.v2.datum.agro_erp.invoices.v1",)
    title = "Inventory"
    value_label = "units"
    empty_text = "No procurement to summarize."

    def synthesize(self, *, doc: Any, docs: list[Any], sandbox: str) -> list[dict[str, Any]]:
        lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))
        txa = cached_index(find_named_document(docs, sandbox=sandbox, name="txa"))
        products = build_product_rows(
            find_named_document(docs, sandbox=sandbox, name="product_profiles"),
            lcl_index=lcl, txa_index=txa,
        )
        # product lcl node -> {name, unit_weight text}
        by_node: dict[str, dict[str, str]] = {}
        for p in products:
            fields = {f.get("field"): f for f in p.get("fields", [])}
            node = _as_text(fields.get("product_id", {}).get("magnitude"))
            if node:
                # Show the product PROFILE's common name (its taxonomy/cultivar, resolved from the
                # product's txa node), NOT the generic "product_N" lcl SAMRAS node label.
                common = (_as_text(fields.get("taxonomy_id", {}).get("resolved"))
                          or _as_text(p.get("product_name")) or node)
                by_node[node] = {
                    "name": common,
                    "uw": _as_text(fields.get("singular_unit_weight", {}).get("resolved")),
                }
        tally: dict[str, int] = {}
        for row in getattr(doc, "rows", ()) or ():
            if not _as_text(row.datum_address).startswith(_INVOICES_PREFIX):
                continue
            lcl_refs: list[str] = []
            nominals: list[str] = []
            for marker, value in iter_marker_pairs(_row_head(row)):
                if marker == Markers.LCL_ID:
                    lcl_refs.append(_as_text(value))
                elif marker == Markers.NOMINAL:
                    nominals.append(decode_label(value))
            # head order: invoice, product, supplier, event (lcl refs in this order).
            product_node = lcl_refs[1] if len(lcl_refs) > 1 else ""
            event = lcl_refs[3] if len(lcl_refs) > 3 else ""
            if event != EVENT_PROCUREMENT:
                continue
            weight = nominals[0] if nominals else ""
            cnt = derive_unit_count(weight, by_node.get(product_node, {}).get("uw", ""))
            if cnt is None:
                continue
            tally[product_node] = tally.get(product_node, 0) + cnt
        items = [
            {"label": by_node.get(n, {}).get("name", n) or n, "figure": tally[n]}
            for n in tally
        ]
        items.sort(key=lambda x: -x["figure"])
        return items


register(InventorySynopsis())
