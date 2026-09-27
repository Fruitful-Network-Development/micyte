"""The modern ledger — supply, sales and the standing offer, as ARCHETYPE rows.

TASK-2026-08-14-002, Farmers phase. Phase 4 found that the old ledger machinery
(`save_invoice` / `save_sale` / `save_offering`) wrote the pre-archetype lcl-container
record model into documents no live sandbox holds — those writers, their panes and
their synopses were DELETED in the old-model pane cleanup, so these three managers are
the ledger now, not the newer of two. The pattern the jobs and projects tables proved
twice: an `editable_table` over an append-path document whose rows ARE the minted
archetype —

* ``invoices`` — `invoice` rows: who it is from, when, how much, a note;
* ``sales``   — `invoice` rows too, DELIBERATELY: a sale row is invoice-shaped
  (msn_id, utc, price, title?), the mint's no-two-archetypes-per-shape check refuses a
  twin, and the DOCUMENT carries the direction;
* ``credits`` — `invoice` rows as well, for the same reason and a third direction: an
  amount credited TO a party rather than charged to them. Added 2026-08-24 for the
  grantor's free trials, where the operator's rule is "no negative datum values" — so a
  trial is a POSITIVE row in a credit-direction document, never a negative price. What a
  party owes is ``sales`` minus ``credits``, computed at read time; nothing stored is ever
  below zero;
* ``offering`` — `offer` rows (minted this phase): which product, at how many cents,
  per what unit.

Because `invoice` classes under `log` and declares `utc`, supply and sale entries land
on the general calendar with no code — the class layer doing exactly what it is for.

One read model (:func:`entry_rows` / :func:`offer_rows` / :func:`ledger_totals`) behind
the three tables AND the Brevat overview, so a figure on the overview and the table it
summarizes cannot disagree. The OLD panes stay registered for the lifted agronomics farm
tabs until their model retires with them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._editable_table import editable_table, editable_table_error, field
from ._record_view import narrow
from ._registry import register
from ._viewscope import _row_values
from .job_manager import _document_named, _lcl_options, _options, _readable, money

#: Document names and the archetypes their rows are — imported by the write runtime,
#: never restated (the `JOB_LOG` rule).
SUPPLY_DOC = "invoices"
SALES_DOC = "sales"
#: The third invoice-shaped book. A credit is not a negative sale — it is its own
#: direction, the way a supply entry is — so it gets a document rather than a sign.
CREDITS_DOC = "credits"
OFFER_DOC = "offering"
#: What each alias HAS, as opposed to what it has been charged. A `sales` row is a payment
#: that happened; a subscription row is the standing fact a payment is generated FROM.
#: TASK-2026-08-24-010: the state of a service and the quantity it is billed at are
#: different facts that change at different times, so they are different rows.
SUBSCRIPTIONS_DOC = "subscriptions"
#: The supply-backed planting book (TASK-2026-08-14-002 batch re-point): `planting`
#: rows — which supply batch (a row address in this sandbox's `invoices`), on which
#: plot or cluster, on what day, drawing down how much. NOT `contracts`: that name
#: belongs to the network-contract vocabulary, and the pre-archetype 4-6 contract row
#: retired with its writer.
PLANTINGS_DOC = "plantings"
#: WHICH product, as opposed to what it costs. `offering_record` — `lcl_id, txa_id, title,
#: hyphae_ref` — is the archetype the class library already calls a `product_profile`
#: (`mint_class_library.py`: one member, and this is it). Its 217 live rows are FND's own
#: `agnet.product_profiles`, written by a script; nothing a client could reach ever wrote
#: one. See `docs/contracts/product_profile_denotation.md` for why this and not the
#: twelve-field agro_erp shape (a datum TEMPLATE, no minted archetype, zero live rows) or
#: `offer` (a price on a node, which says nothing about what the node is).
PRODUCTS_DOC = "product_profiles"
ENTRY_ARCHETYPE = "invoice"
OFFER_ARCHETYPE = "offer"
PRODUCT_ARCHETYPE = "offering_record"
PLANTING_ARCHETYPE = "planting"
#: `msn_id, lcl_id, nominal, utc` — the alias, the service NODE, how many, since when.
#: Not `invoice`: an invoice REQUIRES a price, and a subscription has none to give. Its
#: price is the offering's, joined on the service node, and restating it here would be a
#: second denotation of one number that drifts the first time an offer changes.
SUBSCRIPTION_ARCHETYPE = "subscription"

_SCHEMA = "mycite.v2.portal.workbench.tool.ledger.v1"
_SAVE_ROUTE = "/portal/api/v2/ledger"
_TENANT_DEFAULT = "fnd"


def entry_rows(document: Any, *, sandbox: str, archetype: Any, names: Any,
               authority: Any = None,
               accounts: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Invoice-shaped rows (supply or sale) as the table's fields.

    The twin-key rule the jobs table carries: the FIELD key (`party`) holds the stored
    node address for the edit select; the display twin (`from`/`to` is the caller's
    column choice, so both ride under `party_label`) holds what a human reads.
    """
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        node = next((v for v in values.get("msn_id", ()) if v), "")
        stamps = [v for v in values.get("utc", ()) if v]
        prices = [v for v in values.get("price", ()) if v]
        # The supply-backed planting optionals: WHAT arrived (a product leaf) and how
        # much. Present only on entries written as batches; blank columns otherwise.
        product = next((v for v in values.get("lcl_id", ()) if v), "")
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            "entry": row.datum_address,
            "party": node,
            # The ROSTER first, then the address space — `account_labels` says why. This
            # is the same fix `subscription_rows` took on 2026-08-26 and it was made in
            # ONE of the two row readers, so the Sales and Credits tabs went on printing
            # a grantee msn where the Subscriptions tab had started printing a name.
            "party_label": (
                (accounts or {}).get(node)
                or (names.label(node, key_field="msn_id") if node else "")),
            "when": _readable(authority, stamps[0]) if stamps else "",
            "amount": money(prices[0]) if prices else "",
            "amount_cents": int(prices[0]) if prices and prices[0].lstrip("-").isdigit() else 0,
            "product_node": product,
            "product": names.label(product, key_field="lcl_id") if product else "",
            "quantity": next((v for v in values.get("nominal", ()) if v), ""),
            "note": decode_label(next((v for v in values.get("title", ()) if v), "")),
        })
    return rows


def offer_rows(document: Any, *, sandbox: str, archetype: Any, names: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        node = next((v for v in values.get("lcl_id", ()) if v), "")
        prices = [v for v in values.get("price", ()) if v]
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            "offer": row.datum_address,
            # Twin keys, the jobs-table rule: the FIELD (`product_node`) holds the stored
            # lcl address for the edit select and the write; the COLUMN (`product`) holds
            # what a human reads.
            "product_node": node,
            "product": names.label(node, key_field="lcl_id") if node else "",
            "price": money(prices[0]) if prices else "",
            "price_cents": int(prices[0]) if prices and prices[0].lstrip("-").isdigit() else 0,
            "unit": next((v for v in values.get("nominal", ()) if v), ""),
            "note": decode_label(next((v for v in values.get("title", ()) if v), "")),
            # The allowance the price applies after; blank when the offer names none.
            "included_units": next((v for v in values.get("included_units", ()) if v), ""),
        })
    return rows


def product_rows(document: Any, *, sandbox: str, archetype: Any, names: Any,
                 taxon_photographs: dict[str, dict[str, str]] | None = None,
                 ) -> list[dict[str, Any]]:
    """`offering_record` rows as the catalog table's fields.

    By SHAPE, not by position — the same `archetype.covers` filter `offer_rows` and
    `entry_rows` use, and here it is load-bearing rather than incidental. A
    `product_profiles` document may also hold the twelve-pair agro_erp rows
    `product_document_view.build_product_rows` reads POSITIONALLY, and the two formats
    agree on their first two cells and diverge on the third: read positionally, an
    `offering_record`'s title babelette lands under `rotation_group`. Asking the archetype
    is the only question that separates them.

    The taxon column reads as a NAME when the sandbox's own index can name the node, and
    as the coordinate when it cannot — which is still what the cell says.
    """
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        lcl = [v for v in values.get("lcl_id", ())]
        node = next((v for v in lcl if v), "")
        taxon = next((v for v in values.get("txa_id", ()) if v), "")
        # The second lcl cell is the PICTURE, read positionally — the reading
        # `local_domain_log` and `project_artifact` already established, and the reason
        # the cell is not a second `txa_id`: an artifact slot is not a taxon.
        photograph = lcl[1] if len(lcl) > 1 else ""
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            "product": row.datum_address,
            # The twin-key rule the jobs table carries and every table in this file
            # repeats: the FIELD key holds the stored address the edit select writes back,
            # the display twin holds what a human reads.
            "product_node": node,
            "node": names.label(node, key_field="lcl_id") if node else "",
            "name": decode_label(next((v for v in values.get("title", ()) if v), "")),
            "taxon_node": taxon,
            "taxon": names.label(taxon, key_field="txa_id") if taxon else "",
            # A profile whose taxon is cited only once is a cascade that could go wrong
            # without leaving evidence — see `_txa_citation`. Shown so the gap is visible.
            "citation": next((v for v in values.get("hyphae_ref", ()) if v), ""),
            # The MEASURE a stock count is relative to, and the picture (2026-09-12). Both
            # optional: a profile written before them reads them as empty, not as absent.
            "unit": next((v for v in values.get("nominal", ()) if v), ""),
            "photograph": photograph,
            "photograph_name": names.label(photograph, key_field="lcl_id") if photograph else "",
            # THE TAXON's picture, which is a different fact from the product's own: the
            # plantae collection says what a Solanum lycopersicum looks like, and this
            # sandbox holds neither the collection nor the file (TASK-2026-09-12-001 A4).
            # Kept in its own field rather than filling `photograph`, because "this product
            # has no picture of its own" stays true and stays visible.
            **_taxon_picture(taxon_photographs, taxon),
        })
    return rows


def _taxon_picture(found: dict[str, dict[str, str]] | None, taxon: str) -> dict[str, str]:
    hit = (found or {}).get(taxon) if taxon else None
    if not hit:
        return {"taxon_photograph": "", "taxon_photograph_of": ""}
    return {"taxon_photograph": hit.get("slot", ""),
            "taxon_photograph_of": f"{hit.get('sandbox', '')}@{hit.get('msn', '')}"}


def offer_catalog(rows: list[dict[str, Any]], *, sandbox: str) -> Any:
    """The standing offers as the commerce port's own :class:`OfferingCatalog`.

    From the SAME :func:`offer_rows` the table shows, so a storefront and the operator's
    own pane cannot disagree. Rows the port would refuse — no unit, no product, a price
    that is not positive whole cents — are DROPPED rather than repaired, the `_offering`
    rule: a catalog is published, and a half-formed entry in one is a price a stranger
    acts on.
    """
    from micyte.ports.commerce_offering import OfferedItem, OfferingCatalog

    items = []
    for row in rows:
        try:
            items.append(OfferedItem(
                product_node=as_text(row.get("product_node")),
                name=as_text(row.get("product")) or as_text(row.get("product_node")),
                price_cents=int(row.get("price_cents") or 0),
                unit=as_text(row.get("unit")),
                description=as_text(row.get("note")),
            ))
        except ValueError:
            continue
    return OfferingCatalog(sandbox_id=sandbox, items=tuple(items))


#: The document naming who an alias IS. `ledger_write_runtime._rostered_aliases` reads the
#: same one to decide whether a subscription may be written at all.
ACCOUNTS_DOC = "accounts"


def account_labels(document: Any, *, sandbox: str, archetype: Any) -> dict[str, str]:
    """``grantee msn -> the name the roster calls them``.

    Because the msn ADDRESS SPACE cannot answer this. A grantee msn is deliberately not a
    registrar node — the two-address rule `verify_service_identity` states — so
    `_node_names` has no name for one, and `names.label` correctly returns the address
    unchanged. Measured 2026-08-26 on the live store: the index holds 45,208 addresses
    under `msn_id` and not one of the seven grantee msns is among them.

    So the Subscriptions tab rendered its first real row as
    `alias: 3-2-3-17-77-3-6-7-1-5` — accurate, and the "non human readable values"
    complaint the document manager was rebuilt over.

    The roster is where the name lives, and it is the same document the WRITER already
    treats as authoritative: you cannot subscribe someone who is not an account. Two
    readers of one fact, one document.
    """
    out: dict[str, str] = {}
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is not None and not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        msn = next((v for v in values.get("msn_id", ()) if v), "")
        label = next((v for v in values.get("title", ()) if v), "")
        if msn and label:
            out[msn] = label
    return out


def subscription_rows(document: Any, *, sandbox: str, archetype: Any,
                      names: Any, authority: Any = None,
                      accounts: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """What each alias HAS — the alias, the service node, the quantity, since when.

    The twin-key rule again: `party` / `service_node` hold the stored addresses the edit
    selects write back, `party_label` / `service` hold what a human reads. No price and no
    unit: both are the OFFER's, and :func:`micyte.tools.grantor_books.subscription_ledger`
    is where the two are joined. A row that carried its own copy would be a price nothing
    updates when the price list does.
    """
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        party = next((v for v in values.get("msn_id", ()) if v), "")
        service = next((v for v in values.get("lcl_id", ()) if v), "")
        stamps = [v for v in values.get("utc", ()) if v]
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            "subscription": row.datum_address,
            "party": party,
            # The ROSTER first: an alias is a grantee msn and the address space holds no
            # name for one. `names.label` is the fallback, and it returns the address.
            "party_label": (
                (accounts or {}).get(party)
                or (names.label(party, key_field="msn_id") if party else "")),
            "service_node": service,
            "service": names.label(service, key_field="lcl_id") if service else "",
            "quantity": next((v for v in values.get("nominal", ()) if v), ""),
            "since": _readable(authority, stamps[0]) if stamps else "",
        })
    return rows


def ledger_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What a book adds up to — entries and whole cents, from the SAME rows the table
    shows."""
    cents = sum(int(r.get("amount_cents") or 0) for r in rows)
    return {"entries": len(rows), "cents": cents, "total": money(str(cents))}


class _LedgerBase:
    """The shared build for the two invoice-shaped books; subclasses name the document,
    the action, and the column reading of `party` (a supplier is FROM, a customer TO)."""

    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    applies_to_archetype: tuple[str, ...] = (ENTRY_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT

    document_name = ""
    action = ""
    party_column = "party"
    add_label = ""
    empty_text = ""

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

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        doc_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=self.document_name)
        if not doc_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {self.document_name} document yet — installing the "
                "Brevat app provisions one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")
        document = read_document(store, tenant_id=self.tenant_id, document_id=doc_id)
        anchor_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name="anchor")
        authority = None
        if anchor_id:
            from ._hops_dates import chrono_authority

            authority = chrono_authority(
                read_document(store, tenant_id=self.tenant_id, document_id=anchor_id))

        entry_accounts_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=ACCOUNTS_DOC)
        entry_accounts = account_labels(
            read_document(store, tenant_id=self.tenant_id, document_id=entry_accounts_id),
            sandbox=sandbox, archetype=registry.get("channel_account"),
        ) if entry_accounts_id else {}

        rows = entry_rows(
            document, sandbox=sandbox, archetype=registry.get(ENTRY_ARCHETYPE),
            names=names, authority=authority, accounts=entry_accounts)
        # The display twin under the caller's column name (`from` / `to`).
        for row in rows:
            row[self.party_column] = row["party_label"]

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.tool_id,
            search_columns=(self.party_column, "when", "amount", "note"),
            facets=(),
            search_placeholder=f"Search {self.label.lower()}",
        )

        root = as_text((extra_query or {}).get("service_area"))
        options = _options(space, names, root)
        # The batch optionals (supply-backed planting): a product leaf and a received
        # amount, together or not at all — what turns an entry into a BATCH the planting
        # model can draw down. Offered on both books (the document is the direction).
        products = _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title=self.label,
            columns=["entry", self.party_column, "when", "amount", "product",
                     "quantity", "note"],
            fields=[
                field("party", kind="select", label=self.party_column,
                      options_key="site_options",
                      required_text="Pick the other party's node."),
                field("when", kind="date", label="when",
                      required_text="An entry needs a date."),
                field("amount", placeholder="$0.00",
                      required_text="An entry needs an amount.",
                      edit_hint="typed in dollars; stored as whole cents"),
                field("product_node", kind="select", label="product",
                      options_key="trade_options",
                      edit_hint="optional — with a quantity, makes this entry a batch"),
                field("quantity", placeholder="25 g / 500 slips",
                      edit_hint="optional — goes with the product"),
                field("note", placeholder="what this was for"),
            ],
            rows=rows, save_route=f"{_SAVE_ROUTE}/{self.action}",
            empty_text=self.empty_text,
            add_label=self.add_label,
            filters=controls,
            site_options=options,
            trade_options=products,
            service_area=root,
            options_truncated=max(0, len(space.children.get(root, ())) - len(options)),
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


class SupplyLedger(_LedgerBase):
    """What the instance bought in: invoice rows in its own `invoices` document."""

    tool_id = "supply_ledger"
    label = "Supply"
    summary = "What was bought in: who from, when, how much."
    document_name = SUPPLY_DOC
    action = "add_supply"
    party_column = "from"
    add_label = "Add supply"
    empty_text = "No supply entries yet — use + Add supply."
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=SUPPLY_DOC, archetype=ENTRY_ARCHETYPE,
            why="what this instance bought in — invoice rows, dated and priced"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="invoice", action="add_supply"),
    )


class SalesLedger(_LedgerBase):
    """What the instance sold: invoice-SHAPED rows in its own `sales` document."""

    tool_id = "sales_ledger"
    label = "Sales"
    summary = "What was sold: who to, when, how much."
    document_name = SALES_DOC
    action = "add_sale"
    party_column = "to"
    add_label = "Add sale"
    empty_text = "No sales yet — use + Add sale."
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            # archetype `invoice`, DELIBERATELY — see the module header: a sale row is
            # invoice-shaped and the document carries the direction.
            name=SALES_DOC, archetype=ENTRY_ARCHETYPE,
            why="what this instance sold — invoice-shaped rows; the document is the direction"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="sale", action="add_sale"),
    )


class CreditLedger(_LedgerBase):
    """What was credited TO a party: invoice-shaped rows in the sandbox's `credits`.

    The third direction, and the one the operator's no-negative rule needs. A free trial,
    a goodwill adjustment or a refund is recorded here at a POSITIVE amount; the charge
    stays in `sales` at full price. Nothing is stored below zero and the balance is
    `sales - credits`, computed by :func:`micyte.tools.grantor_books.account_statement`
    where it is shown.

    Same archetype as the other two on purpose — the mint's no-two-archetypes-per-shape
    check would refuse a twin, and the DOCUMENT is what carries direction. That precedent
    is `SalesLedger`'s and this is its third use, which is the point at which it stops
    being a precedent and starts being the rule.
    """

    tool_id = "credit_ledger"
    label = "Credits"
    summary = "What was credited: to whom, when, how much, and what for."
    document_name = CREDITS_DOC
    action = "add_credit"
    party_column = "to"
    add_label = "Add credit"
    empty_text = "No credits yet — use + Add credit."
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=CREDITS_DOC, archetype=ENTRY_ARCHETYPE,
            why="what this instance credited to a party — invoice-shaped rows, POSITIVE, "
                "with the document carrying the direction; a trial is a credit, not a "
                "negative sale"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="credit", action="add_credit"),
    )


class OfferLedger:
    """The standing offers: `offer` rows in the sandbox's own `offering` document."""

    tool_id = "offer_ledger"
    label = "Offering"
    summary = "The standing offers: which product, at what price, per what unit."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    applies_to_archetype: tuple[str, ...] = (OFFER_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=OFFER_DOC, archetype=OFFER_ARCHETYPE,
            why="the standing offers a storefront or the commerce port reads"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="offering", action="set_offer"),
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

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        doc_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=OFFER_DOC)
        if not doc_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {OFFER_DOC} document yet — installing the Brevat app "
                "provisions one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        document = read_document(store, tenant_id=self.tenant_id, document_id=doc_id)

        rows = offer_rows(
            document, sandbox=sandbox, archetype=registry.get(OFFER_ARCHETYPE),
            names=names)

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.tool_id,
            search_columns=("product", "price", "unit", "note"),
            facets=(),
            search_placeholder="Search offers",
        )
        products = _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title="Offering",
            columns=["offer", "product", "price", "unit", "included_units", "note"],
            fields=[
                field("product_node", kind="select", label="product",
                      options_key="trade_options",
                      required_text="Pick a product — mint one in the LCL Editor."),
                field("price", placeholder="$0.00",
                      required_text="An offer needs a price.",
                      edit_hint="typed in dollars; stored as whole cents"),
                field("unit", placeholder="per bunch",
                      edit_hint="what one of these IS — per bunch, per lb, each"),
                field("included_units", label="included", placeholder="0",
                      edit_hint="how many a subscription gets before the price applies"),
                field("note", placeholder="optional description"),
            ],
            rows=rows, save_route=f"{_SAVE_ROUTE}/set_offer",
            empty_text="Nothing offered yet — use + Set an offer.",
            add_label="Set an offer",
            filters=controls,
            trade_options=products,
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


def _row_tail_label_of(raw: Any) -> str:
    """A row's plain tail label, from its raw payload. See :class:`NameIndex`."""
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return as_text(raw[1][0])
    return ""


def _txa_options(store: Any, *, tenant_id: str, sandbox: str,
                 msn: str = "") -> list[dict[str, str]]:
    """The taxonomy nodes this sandbox READS, for the taxon picker.

    The sandbox's own ``txa``, or the one it DECLARES as a source — never somebody else's
    taken on a guess. The distinction is the whole of it: a client that holds no taxonomy
    and pins none still gets an EMPTY list and a taxon it cannot set, which is the honest
    state, because `_txa_citation` refuses to store a coordinate nothing can follow. What
    changed on 2026-09-12 is that a sandbox which HAS bound `taxonomy.txa` now sees it —
    until then the pin was an operator's decision the picker ignored, and a product
    profile in `brevat` could name no taxon at all.

    Read in the OWNER's namespace, never the consumer's: the cells do not change meaning
    because somebody else is reading them.
    """
    from ._sources import sourced_document

    found = sourced_document(store, tenant_id=tenant_id, sandbox=sandbox, name="txa", msn=msn)
    if not found:
        return []
    out: list[dict[str, str]] = []
    for row in getattr(found.document, "rows", ()) or ():
        raw = getattr(row, "raw", None)
        values = _row_values(ash._row_head(raw), namespace=found.namespace)
        address = next((v for v in values.get("txa_id", ()) if v), "")
        # The `NameIndex` rule, not a third one: prefer the plain row TAIL label and fall
        # back to the decoded title blob. The corpus carries taxon names both ways — the
        # `taxon_record` archetype declares a `title` babelette and the ingest also writes
        # the raw key into the tail — and a picker that read only one of them would offer
        # a picker over half a taxonomy.
        label = _row_tail_label_of(raw) or decode_label(
            next((v for v in values.get("title", ()) if v), ""))
        if address and label:
            out.append({"value": address, "label": f"{label} ({address})"})
    return sorted(out, key=lambda o: o["label"])


class ProductCatalog:
    """What the instance SELLS, as things rather than as prices: `offering_record` rows.

    The writer `offering_record` never had. Brevat's Products tab was
    `ProductDocumentViewer` — read-only, no `writes`, and pointed at the twelve-pair
    agro_erp shape that no instance in the live store holds. Measured 2026-09-02: the one
    farm instance
    Family Farm's instance holds no `product_profiles` document in `brevat` or in `system`
    (`strip_farm_simulation` deleted it), so the tab could not have filled from either
    sandbox and no surface could create one. `docs/contracts/product_profile_denotation.md`
    is the whole argument, including why not the other two things called a product.

    The `offer` join is unchanged: an offer still names an lcl node and this says what
    that node IS. Two documents rather than one grown archetype, for the reason
    `SubscriptionBook` gives about state and quantity — what a product is and what it
    costs change at different times, and a price restated here would be a second
    denotation of one number.
    """

    tool_id = "product_catalog"
    label = "Products"
    summary = "What this instance sells: which node, which taxon, and what it is called."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    applies_to_archetype: tuple[str, ...] = (PRODUCT_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=PRODUCTS_DOC, archetype=PRODUCT_ARCHETYPE,
            why="what this instance sells, structurally — the products its offers price"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="product_profile", action="add_product"),
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
        from micyte.core.instance_scope import resolve_msn

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        msn = resolve_msn()
        doc_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=PRODUCTS_DOC)
        if not doc_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {PRODUCTS_DOC} document yet — installing the Brevat "
                "app provisions one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        document = read_document(store, tenant_id=self.tenant_id, document_id=doc_id)

        # The taxon's picture, from whatever plantae collection this sandbox READS — its
        # own, or one it has pinned. A sandbox that pins none gets an empty map and rows
        # that say so, which is the same honest absence the taxon picker gives.
        from ._plantae import taxon_photographs as _taxon_photographs

        rows = product_rows(
            document, sandbox=sandbox, archetype=registry.get(PRODUCT_ARCHETYPE),
            names=names,
            taxon_photographs=_taxon_photographs(
                store, tenant_id=self.tenant_id, sandbox=sandbox, msn=msn))

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.tool_id,
            search_columns=("node", "name", "taxon"),
            facets=(),
            search_placeholder="Search products",
        )
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title="Products",
            columns=["product", "node", "name", "taxon", "unit"],
            fields=[
                field("product_node", kind="select", label="node",
                      options_key="trade_options",
                      required_text="Pick a node — mint one in the LCL Editor."),
                field("title", placeholder="Sungold cherry tomato",
                      required_text="A product needs a name.",
                      edit_hint="what you call it; stored as a title babelette"),
                field("taxon", kind="select", options_key="taxon_options",
                      edit_hint="optional — a taxon this sandbox reads: its own, or "
                                "the taxonomy it has bound as a source"),
                # The MEASURE. Optional here and load-bearing next door: a stock count is
                # relative to it, so twelve of this means twelve of whatever this says.
                field("unit", placeholder="lb",
                      edit_hint="optional — what one of these IS: lb, each, bunch. A stock "
                                "count is read against it."),
            ],
            rows=rows, save_route=f"{_SAVE_ROUTE}/add_product",
            empty_text="No products yet — use + Add a product.",
            add_label="Add a product",
            filters=controls,
            trade_options=_lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox),
            taxon_options=_txa_options(
                store, tenant_id=self.tenant_id, sandbox=sandbox, msn=msn),
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


class SubscriptionBook:
    """What each alias HAS: `subscription` rows in the sandbox's `subscriptions`.

    The book phase E reads. Its first step is "read the alias's services and quantities",
    and until this existed neither was expressible: a `grantor/grantee-<msn>` row is a
    `channel_account` — msn_id, title, lcl_id, utc — whose `title` is the service NAME as
    a STRING and whose `lcl_id` is the STATE. Measured on the live store, every grantee
    row said `title='email'` while the service nodes phase A minted are called
    `user_email` and `operational_email`, so the string could not be joined to a price
    even in principle.

    So the state ledger keeps its rows and this keeps the quantities. Two documents rather
    than a grown archetype, because a service being ENABLED and a service being BILLED AT
    A QUANTITY are different facts that change at different times — and `channel_account`
    is the agnet roster's too, and an archetype is minted deliberately.
    """

    tool_id = "subscription_book"
    label = "Subscriptions"
    summary = "What each alias has: the service, how many, since when."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    applies_to_archetype: tuple[str, ...] = (SUBSCRIPTION_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=SUBSCRIPTIONS_DOC, archetype=SUBSCRIPTION_ARCHETYPE,
            why="what each alias holds — the service NODE and the quantity a charge is "
                "computed from; the price it is computed AT stays in `offering`"),
    ))
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="subscription", action="set_subscription"),
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

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        doc_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=SUBSCRIPTIONS_DOC)
        if not doc_id:
            return editable_table_error(
                self.schema,
                f"{sandbox} has no {SUBSCRIPTIONS_DOC} document yet — installing the "
                "Grantor app provisions one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")
        document = read_document(store, tenant_id=self.tenant_id, document_id=doc_id)
        anchor_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name="anchor")
        authority = None
        if anchor_id:
            from ._hops_dates import chrono_authority

            authority = chrono_authority(
                read_document(store, tenant_id=self.tenant_id, document_id=anchor_id))

        accounts_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=ACCOUNTS_DOC)
        accounts = account_labels(
            read_document(store, tenant_id=self.tenant_id, document_id=accounts_id),
            sandbox=sandbox, archetype=registry.get("channel_account"),
        ) if accounts_id else {}

        rows = subscription_rows(
            document, sandbox=sandbox, archetype=registry.get(SUBSCRIPTION_ARCHETYPE),
            names=names, authority=authority, accounts=accounts)
        for row in rows:
            row["alias"] = row["party_label"]

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.tool_id,
            search_columns=("alias", "service", "quantity", "since"),
            facets=(),
            search_placeholder="Search subscriptions",
        )
        root = as_text((extra_query or {}).get("service_area"))
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title=self.label,
            columns=["subscription", "alias", "service", "quantity", "since"],
            fields=[
                field("party", kind="select", label="alias",
                      options_key="site_options",
                      required_text="Pick the alias this is for."),
                field("service_node", kind="select", label="service",
                      options_key="trade_options",
                      required_text="Pick a service — mint one in the LCL Editor."),
                field("quantity", placeholder="3",
                      required_text="A subscription needs a quantity.",
                      edit_hint="how many, counted in the unit the OFFER states"),
                field("since", kind="date",
                      required_text="A subscription needs a date."),
            ],
            rows=rows, save_route=f"{_SAVE_ROUTE}/set_subscription",
            empty_text="Nothing subscribed yet — use + Set a subscription.",
            add_label="Set a subscription",
            filters=controls,
            site_options=_options(space, names, root),
            trade_options=_lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox),
            service_area=root,
            editing={"datum_address": as_text(datum_address)} if datum_address else None,
        )


register(ProductCatalog())
register(SupplyLedger())
register(SalesLedger())
register(CreditLedger())
register(OfferLedger())
register(SubscriptionBook())

__all__ = [
    "CREDITS_DOC", "ENTRY_ARCHETYPE", "OFFER_ARCHETYPE", "OFFER_DOC", "PLANTINGS_DOC",
    "PLANTING_ARCHETYPE", "PRODUCTS_DOC", "PRODUCT_ARCHETYPE", "SALES_DOC",
    "SUBSCRIPTIONS_DOC", "SUBSCRIPTION_ARCHETYPE", "SUPPLY_DOC",
    "CreditLedger", "OfferLedger", "ProductCatalog", "SalesLedger", "SubscriptionBook",
    "SupplyLedger",
    "entry_rows", "ledger_totals", "offer_rows", "product_rows", "subscription_rows",
]
