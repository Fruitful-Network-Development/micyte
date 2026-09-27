"""Brevat — the generalized ERP hub: the stock, the books, and what is for sale.

    ┌─ Brevat ─[ OVERVIEW ][ PRODUCTS ][ SUPPLY ][ SALES ][ OFFERING ]─┐
    │   see where it stands · what it makes · what it bought ·         │
    │                what it sold · what it offers                     │
    └──────────────────────────────────────────────────────────────────┘

A composite, not a new renderer — the seam ``agronomics_viewer`` established and ``quiar``
carries: each tab is another tool's ``panel_payload`` under ``container:"tabbed"``, so the
ERP can be rearranged, or a vertical assembled from the same parts, without touching the
tools themselves.

The generalized lineage is Brevat; the package offered to farm instances will be
**Brevat – Farmers** (the specialized lineage that adds geometry, planting, consumption
and the Flora & Fauna taxonomy, and retires ``agronomics`` only at live parity —
TASK-2026-08-14-002 AC-4). Generic Brevat deliberately holds NO farm geometry: a
``farm_profile`` stays what makes a sandbox a farm, and the operator's rule keeps
profile-like documents in the ``system`` sandbox.

## The Farmers specialization is discovered by SHAPE, not declared by a second hub

A sandbox holding a ``farm_profile`` IS a farm — the house rule for instance kind — so
this hub appends the farm tabs (built by the ``agronomics_viewer`` LIBRARY: Farm, Plan,
Network, Flora & Fauna) exactly there, and titles itself **Brevat – Farmers**. One hub,
no second rail icon, and ``agronomics`` retired to the library that builds those tabs
once parity across both farms was verified (AC-4).

The ledger tabs are the Farmers-phase REBUILD (`ledger_books`): append-path tables whose
rows are the minted archetypes — `invoice` for supply and sales (the document carries
the direction), `offer` for the standing offers — provisioned by the Brevat package.
The Overview derives from the same row builders the tables use, so a figure here and
the table it summarizes cannot disagree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .ledger_books import OfferLedger, ProductCatalog, SalesLedger, SupplyLedger
from .stock_ledger import StockLedger

TOOL_ID = "brevat"
_SCHEMA = "mycite.v2.portal.workbench.tool.brevat.v1"
_TENANT_DEFAULT = "fnd"

#: The query parameter the client switches on — its own, so the three hubs cannot read
#: each other's active tab out of one URL (`agronomics_tab`, `erp_tab`, this).
TAB_QUERY = "brevat_tab"
DEFAULT_TAB = "overview"


def _overview(*, authority_db_file: Path | None, sandbox: str) -> dict[str, Any]:
    """The books at a glance, from the SAME row builders the three tables use."""
    from micyte.core import archetypes as arc

    from . import _node_names as nn
    from ._viewscope import read_document
    from .job_manager import _document_named
    from .ledger_books import (
        ENTRY_ARCHETYPE,
        OFFER_ARCHETYPE,
        OFFER_DOC,
        SALES_DOC,
        SUPPLY_DOC,
        entry_rows,
        ledger_totals,
        offer_rows,
    )

    if authority_db_file is None or not sandbox:
        return {"schema": _SCHEMA, "container": "synopsis", "title": "Overview",
                "items": [], "count_label": "no sandbox selected"}

    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    library = store.read_documents_by_sandbox(
        tenant_id=_TENANT_DEFAULT, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    names = nn.name_index_for(
        store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox, registry=registry)
    anchor_id = _document_named(
        store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox, name="anchor")
    authority = None
    if anchor_id:
        from ._hops_dates import chrono_authority

        authority = chrono_authority(
            read_document(store, tenant_id=_TENANT_DEFAULT, document_id=anchor_id))

    def _doc(name: str):
        doc_id = _document_named(
            store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox, name=name)
        return (read_document(store, tenant_id=_TENANT_DEFAULT, document_id=doc_id)
                if doc_id else None)

    # `items: [{label, figure}]` — the shape `renderSynopsis` READS. The first cut said
    # `figures: [{label, value, detail}]` and rendered "Nothing to summarize" over three
    # real answers: correct by its own lights, unreadable by the client, caught only by
    # the screenshot — the recurring lesson every hub in this file's lineage carries.
    # And the FIGURE is short by design (the oveure lesson, same screenshot family): it
    # is the no-shrink column, so a sentence there crushes the label to nothing.
    items = []
    for label, name, kind in (("Supply", SUPPLY_DOC, "entry"),
                              ("Sales", SALES_DOC, "entry"),
                              ("Offers", OFFER_DOC, "offer")):
        document = _doc(name)
        if document is None:
            items.append({"label": f"{label} — no {name} document yet; install Brevat",
                          "figure": "none"})
            continue
        if kind == "entry":
            totals = ledger_totals(entry_rows(
                document, sandbox=sandbox, archetype=registry.get(ENTRY_ARCHETYPE),
                names=names, authority=authority))
            items.append({"label": label,
                          # No `$` of its own: `money` renders one now, and this line used to
                          # supply the symbol that function was missing.
                          "figure": f"{totals['total']} · {totals['entries']} entries"})
        else:
            rows = offer_rows(
                document, sandbox=sandbox, archetype=registry.get(OFFER_ARCHETYPE),
                names=names)
            items.append({"label": label, "figure": f"{len(rows)} standing offers"})
    return {
        "schema": _SCHEMA, "container": "synopsis", "sandbox_id": sandbox,
        "title": "The books", "items": items,
    }


#: ``(tab id, label, a FACTORY or None)`` — ``None`` marks the composite the hub builds
#: itself. Order is the order of the work: see where it stands, what it makes, what it
#: bought, what it sold, what it offers.
TABS: tuple[tuple[str, str, Any], ...] = (
    ("overview", "Overview", None),
    # `ProductCatalog`, not `ProductDocumentViewer`: the viewer is READ-ONLY (no
    # `writes`) over the twelve-pair agro_erp shape, which no instance in the live
    # store holds — measured 2026-09-02, zero `product_profiles` documents outside
    # FND's `agnet`. So the tab could not fill and nothing could ever fill it. The
    # catalog reads the `offering_record` rows the class library already calls a
    # `product_profile` and declares the write that appends one. The viewer stays the
    # LIBRARY it was retired into — `build_product_rows` still feeds `_consumption`
    # and the Flora & Fauna table, untouched.
    ("products", "Products", ProductCatalog),
    # WHAT IS ON HAND (TASK-2026-09-12-001). Beside Supply and Sales rather than inside
    # either: a delivery and a sale are both movements and the balance is their sum, so a
    # log that lived under one of them would answer half the question. The measure a count
    # is relative to is the PRODUCT's, which is why this tab sits after Products.
    ("stock", "Stock", StockLedger),
    ("supply", "Supply", SupplyLedger),
    ("sales", "Sales", SalesLedger),
    ("offering", "Offering", OfferLedger),
)


class Brevat:
    """The surfaces an instance that sells goods needs, in one place."""

    tool_id = TOOL_ID
    label = "Brevat"
    # UI copy: the rail hover. One sentence from the user's side — the each-tab-is-
    # the-standalone-tool rule lives in the class docstring, not in a tooltip.
    summary = "Track products, supply, sales and your standing offer."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: follows the instance switcher.
    icon = "brevat"
    #: ANY-OF: a farm (the specialization lights by shape), or an instance already
    #: holding one of the modern ledger documents. An instance with neither has nothing
    #: this hub can show — installing the Brevat app provisions the ledgers and the gate
    #: opens with them.
    requires = ToolRequirement(documents_any=(
        DocumentRequirement(
            name="farm_profile", archetype="farm_profile_identity",
            why="a farm — the Farmers tabs light where this document is"),
        DocumentRequirement(
            name="invoices", archetype="invoice",
            why="the supply book"),
        DocumentRequirement(
            name="sales", archetype="invoice",
            why="the sales book — invoice-shaped rows; the document is the direction"),
        DocumentRequirement(
            name="offering", archetype="offer",
            why="the standing offers"),
    ))
    # No `writes`: each pane owns its own, and `_write_owners` refuses a second
    # declaration of an action — the composite rule all three hubs share.

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = dict(extra_query or {})
        sandbox = as_text(sandbox_id)
        panes: list[dict[str, Any]] = []
        for tab_id, label, tool in TABS:
            try:
                if tool is None:
                    payload = _overview(
                        authority_db_file=authority_db_file, sandbox=sandbox)
                    pane_tool_id = "brevat_overview"
                else:
                    instance = tool()
                    pane_tool_id = instance.tool_id
                    kwargs: dict[str, Any] = {
                        "authority_db_file": authority_db_file,
                        "sandbox_id": sandbox,
                        "document_id": (
                            document_id if query.get(TAB_QUERY) == tab_id else ""),
                        "datum_address": (
                            datum_address if query.get(TAB_QUERY) == tab_id else ""),
                    }
                    # Only for tools that DECLARE they read it: `ProductDocumentViewer`
                    # (a library since Phase 1) predates `wants_surface_query` and its
                    # signature refuses the kwarg — found on the deployed build, where
                    # the Products tab rendered its own failure envelope.
                    if getattr(instance, "wants_surface_query", False):
                        kwargs["extra_query"] = query
                    payload = instance.build_panel_payload(**kwargs)
            except Exception as exc:  # pragma: no cover — defensive
                payload = {"schema": _SCHEMA, "error": f"{tab_id} pane failed: {exc}"}
                pane_tool_id = tab_id
            panes.append({
                "id": tab_id,
                "label": label,
                "tool_id": pane_tool_id,
                "panel_payload": payload,
            })

        # The Farmers specialization, by SHAPE: a sandbox holding `farm_profile` is a
        # farm, so the farm tabs are LIFTED from the agronomics builder — its whole
        # tabbed payload built once by the same code that served it as a standalone hub,
        # its tabs appended here. Their ids (farm/plan/network/taxonomy) do not collide
        # with this hub's; their sub-tab params ride `extra_query` untouched.
        farmers = False
        if authority_db_file is not None and sandbox and self._is_farm(
            authority_db_file, sandbox
        ):
            try:
                from .agronomics_viewer import AgronomicsViewer

                lifted = AgronomicsViewer().build_panel_payload(
                    authority_db_file=authority_db_file, sandbox_id=sandbox,
                    document_id=document_id, datum_address=datum_address,
                    extra_query=query,
                )
                panes.extend(lifted.get("tabs") or ())
                farmers = True
            except Exception as exc:  # pragma: no cover — defensive
                panes.append({
                    "id": "farm", "label": "Farm", "tool_id": "agronomics",
                    "panel_payload": {
                        "schema": _SCHEMA, "error": f"farm tabs failed: {exc}"},
                })
                farmers = True

        ids = [pane["id"] for pane in panes]
        active = as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in ids:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Brevat – Farmers" if farmers else "Brevat",
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
        }

    def _is_farm(self, authority_db_file: Path | str, sandbox: str) -> bool:
        """Shape, not a list: the sandbox is a farm iff it holds a `farm_profile`."""
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        from .job_manager import _document_named

        return bool(_document_named(
            store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox, name="farm_profile"))


register(Brevat())

__all__ = ["DEFAULT_TAB", "TABS", "TAB_QUERY", "Brevat"]
