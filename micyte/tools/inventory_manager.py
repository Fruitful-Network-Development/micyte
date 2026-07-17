"""Inventory Management — a WRITABLE supply-batch table (the PLAN tab's inventory subpage).

Where InvoicesViewer READS the invoices doc, this is the editable version reached from the
Inventory Synopsis "edit" button or a Flora & Fauna product-card "add" button. It emits a
``container:"inventory_table"`` payload: the batch rows (newest receival first) each with a
per-row edit affordance, a create affordance (a new entry at the top of the table), and — when
``inventory_new``/``inventory_edit`` is set — an ``editing`` block that seeds the inline entry
(product pre-filled from the card add). Saving POSTs to /portal/api/v2/agro/save_invoice; the
sibling Inventory Synopsis then re-totals (it already aggregates per product).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    cached_index,
    decode_label,
    iter_marker_pairs,
)
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import document_sandbox, read_sandbox_catalog, resolve_tool_sandbox
from ._consumption import batch_consumption
from ._hops_dates import chrono_authority, hops_token_to_date
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

_SAVE_ROUTE = "/portal/api/v2/agro/save_invoice"


def _find_doc(docs: Any, sandbox: str, name: str) -> Any | None:
    """First doc in ``sandbox`` named ``name`` — tolerant of the legacy full-id canonical_name.

    A freshly-written doc carries the short canonical_name ("invoices"), but a doc from the
    pre-rename ``agro_erp`` sandbox still carries ``lv.<msn>.agro_erp.invoices``. ``find_named_document``
    only matches the short form, so it would read an EMPTY table until the first save normalizes the
    name; matching ``.endswith("." + name)`` too keeps the read and the write path in agreement.
    """
    for doc in docs:
        if sandbox and document_sandbox(doc) != sandbox:
            continue
        cn = _as_text(getattr(doc, "canonical_name", ""))
        if cn == name or cn.endswith("." + name):
            return doc
    return None


def _options_by_prefix(lcl_doc: Any, *prefixes: str) -> list[dict[str, str]]:
    """[{value: node, label: 'name (node)'}] for lcl definition nodes under any of ``prefixes``."""
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


class InventoryManagerTool:
    """The writable inventory (supply-batch) table for the PLAN tab."""

    tool_id = "inventory_manager"
    label = "Inventory Management"
    summary = "Supply batches you can create/edit — product, amount, cost, supplier, receival date."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = "mycite.v2.portal.workbench.tool.inventory_manager.v1"

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        eq = extra_query or {}
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id="fnd")
        if err:
            return {"schema": self.schema, "container": "inventory_table", "error": err, "rows": []}
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return {"schema": self.schema, "container": "inventory_table", "error": "no sandbox specified", "rows": []}
        inv = _find_doc(docs, sandbox, "invoices")
        lcl_doc = _find_doc(docs, sandbox, "lcl")
        lcl = cached_index(lcl_doc)

        # Lifecycle overlays (Phase B–D): batch consumption/remaining + shelf-life days,
        # and the calendar receival date decoded from the stored HOPS token.
        consumption = batch_consumption(docs, sandbox)
        authority = chrono_authority(_find_doc(docs, sandbox, "anchor"))
        today = date.today()

        rows: list[dict[str, Any]] = []
        for r in getattr(inv, "rows", ()) or ():
            if not _as_text(r.datum_address).startswith("4-7-"):
                continue
            buckets: dict[str, list[Any]] = {}
            for m, v in iter_marker_pairs(_row_head(r)):
                buckets.setdefault(_as_text(m).lower(), []).append(v)
            refs = buckets.get("rf.3-1-5", [])
            noms = buckets.get("rf.3-1-7", [])
            date_tok = _as_text((buckets.get("rf.3-1-6") or [""])[0])
            batch = _as_text(refs[0]) if refs else ""
            product = _as_text(refs[1]) if len(refs) > 1 else ""
            supplier = _as_text(refs[2]) if len(refs) > 2 else ""
            decoded = [decode_label(n) for n in noms]
            retired = any(t.strip().lower() == "retired" for t in decoded)

            meta = consumption.get(batch, {})
            received_date = hops_token_to_date(authority, date_tok)
            shelf_days = int(meta.get("shelf_days") or 0)
            days_until_bad = None
            if received_date is not None and shelf_days > 0:
                days_until_bad = (received_date + timedelta(days=shelf_days) - today).days
            remaining = meta.get("remaining_units")
            rows.append({
                "datum_address": _as_text(r.datum_address),
                "batch": lcl.resolve(batch) or batch, "batch_node": batch,
                "product": lcl.resolve(product) or product, "product_node": product,
                "received": received_date.isoformat() if received_date else date_tok,
                "received_token": date_tok,
                "amount": decoded[0] if decoded else "",
                "cost": decoded[1] if len(decoded) > 1 else "",
                "supplier": lcl.resolve(supplier) or supplier, "supplier_node": supplier,
                "retired": retired,
                "shelf_days": shelf_days,
                "days_until_bad": days_until_bad,
                "total_units": meta.get("total_units"),
                "consumed_units": meta.get("consumed_units"),
                # a retired batch closes its remaining to 0; the un-planted remainder is waste
                "remaining_units": 0 if retired else remaining,
                "waste_units": (remaining if retired else None),
                "basis": meta.get("basis"),
            })
        # newest first (append order tracks receival; 4-7-N ordinal is a stable proxy)
        rows.sort(key=lambda x: int(x["datum_address"].split("-")[-1]), reverse=True)

        product_options = _options_by_prefix(lcl_doc, "1-1-5-")
        supplier_options = _options_by_prefix(lcl_doc, "1-1-4-")

        editing = None
        edit_addr = _as_text(eq.get("inventory_edit"))
        new_seed = _as_text(eq.get("inventory_new"))
        if edit_addr:
            cur = next((x for x in rows if x["datum_address"] == edit_addr), None)
            if cur:
                editing = {"datum_address": edit_addr, "product_node": cur["product_node"],
                           "amount": cur["amount"], "cost": cur["cost"],
                           "supplier": cur["supplier"], "date": ""}
        elif new_seed:
            # A Flora & Fauna card passes the 1-1-5 product-leaf node; be forgiving and also
            # accept a product name, resolving either against THIS farm's product options (a
            # leaf from another farm's lcl won't match — the user then picks from the dropdown).
            resolved = ""
            if new_seed:
                if any(o["value"] == new_seed for o in product_options):
                    resolved = new_seed
                else:
                    low = new_seed.strip().lower()
                    for o in product_options:
                        if o["label"].rsplit(" (", 1)[0].strip().lower() == low:
                            resolved = o["value"]
                            break
            editing = {"datum_address": "", "product_node": resolved,
                       "amount": "", "cost": "", "supplier": "", "date": ""}

        return {
            "schema": self.schema, "container": "inventory_table", "sandbox_id": sandbox,
            "title": "Inventory Management",
            "columns": ["batch", "product", "amount", "cost", "supplier", "received"],
            "rows": rows, "row_count": len(rows),
            "save_route": _SAVE_ROUTE,
            "product_options": product_options, "supplier_options": supplier_options,
            "editing": editing,
            # Phase B–D: the renderer shows per-row days-until-bad + remaining/consumed, a retire
            # toggle, and a "plan" button that exits to the PLAN Cluster Editor (Plot Manager).
            "lifecycle": True,
            "empty_text": "No supply batches yet — use + Add entry.",
        }


register(InventoryManagerTool())
