"""What the grantor's three books ADD UP TO — read views, never a second read model.

TASK-2026-08-24-005 phase B. The grantor sandbox keeps its commerce in the same books
every other instance keeps its trade in (`micyte.tools.ledger_books`), because FND selling
hosting is not a different kind of fact from a farm selling produce:

    offering   `offer`   rows   what a service COSTS, per unit          (R7)
    sales      `invoice` rows   what an alias was CHARGED               (R5)
    credits    `invoice` rows   what an alias was CREDITED, positive    (R6)
    invoices   `invoice` rows   what AWS charged FND, residue included  (R8, phase D)

In a farm sandbox `invoices` is what the farm bought and `sales` is what it sold. In the
grantor sandbox FND is the seller, so the same two names land on the correct meanings
without being redefined — and one read model keeps serving both.

**Two questions, two functions, and neither re-derives a total.** `entry_rows`,
`offer_rows` and `ledger_totals` already answer "what is in this book"; these answer "what
does it come to for THIS alias" and "what are we charging against what it costs". A figure
here and a figure on the books' own tables cannot disagree, because there is one place that
adds up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label

from . import _node_names as nn
from .job_manager import _readable
from .ledger_books import (
    CREDITS_DOC,
    ENTRY_ARCHETYPE,
    OFFER_ARCHETYPE,
    OFFER_DOC,
    SALES_DOC,
    SUBSCRIPTION_ARCHETYPE,
    SUBSCRIPTIONS_DOC,
    SUPPLY_DOC,
    entry_rows,
    ledger_totals,
    offer_rows,
    subscription_rows,
)

#: The sandbox FND keeps the hosting relationship in. Stated here because these views are
#: ABOUT that relationship; a farm has no use for them.
GRANTOR_SANDBOX = "grantor"

_TENANT_DEFAULT = "fnd"


def _read(store: Any, *, tenant_id: str, sandbox: str, name: str) -> Any:
    """One book, or ``None`` when the sandbox does not hold it.

    Absent is a STATE, not an error. A grantor sandbox that has never been credited holds
    no `credits` document, and a statement that refused to render because of it would be
    reporting the absence of a book as the absence of an account.
    """
    from ._viewscope import read_document
    from .job_manager import _document_named

    document_id = _document_named(
        store, tenant_id=tenant_id, sandbox=sandbox, name=name)
    if not document_id:
        return None
    return read_document(store, tenant_id=tenant_id, document_id=document_id)


def _context(store: Any, *, tenant_id: str, sandbox: str) -> tuple[Any, Any]:
    library = store.read_documents_by_sandbox(
        tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    names = nn.name_index_for(
        store, tenant_id=tenant_id, sandbox=sandbox, registry=registry)
    return registry, names


def _rows(document: Any, *, sandbox: str, registry: Any, names: Any,
          accounts: dict[str, str] | None = None, authority: Any = None) -> list[dict[str, Any]]:
    if document is None:
        return []
    return entry_rows(document, sandbox=sandbox, archetype=registry.get(ENTRY_ARCHETYPE),
                      names=names, accounts=accounts, authority=authority)


def _authority(store: Any, *, tenant_id: str, sandbox: str) -> Any:
    """The sandbox's clock, from its anchor — what turns a stored `utc` token into a day.

    `account_statement` passed none until 2026-09-16, so every `when` on a statement was
    the raw HOPS token: a reader wanting the day a trial credit was written could not
    parse it. The Sales and Credits tabs already build this; the statement now does too.
    """
    from ._hops_dates import chrono_authority

    anchor = _read(store, tenant_id=tenant_id, sandbox=sandbox, name="anchor")
    return chrono_authority(anchor) if anchor is not None else None


def account_statement(
    authority_db_file: Path, *, msn: str, sandbox: str = GRANTOR_SANDBOX,
    tenant_id: str = _TENANT_DEFAULT,
) -> dict[str, Any]:
    """One alias's charges, credits and balance — and nothing about anybody else.

    ``balance = sales - credits``, computed HERE rather than stored, which is what lets the
    no-negative rule hold: a trial is a positive `credits` row against a full-price `sales`
    row, so a fully-credited account reads zero without any stored value ever going below
    it. A balance that came out negative would mean an alias is owed money — real, and
    still not a negative datum: it is the SUBTRACTION that is signed, not any cell.
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    registry, names = _context(store, tenant_id=tenant_id, sandbox=sandbox)
    alias = as_text(msn)

    from .ledger_books import ACCOUNTS_DOC, account_labels

    roster = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=ACCOUNTS_DOC)
    accounts = ({} if roster is None else account_labels(
        roster, sandbox=sandbox, archetype=registry.get("channel_account")))

    authority = _authority(store, tenant_id=tenant_id, sandbox=sandbox)

    def mine(document_name: str) -> list[dict[str, Any]]:
        rows = _rows(_read(store, tenant_id=tenant_id, sandbox=sandbox, name=document_name),
                     sandbox=sandbox, registry=registry, names=names, accounts=accounts,
                     authority=authority)
        # The narrowing is the point of the function: a statement is one alias's, and a
        # view that filtered in the surface instead would be one refactor away from
        # showing the roster.
        return [row for row in rows if as_text(row.get("party")) == alias]

    charges, credits = mine(SALES_DOC), mine(CREDITS_DOC)
    charged, credited = ledger_totals(charges), ledger_totals(credits)
    owed = charged["cents"] - credited["cents"]
    from micyte.core.datum_ops.fiat_datum import format_cents

    return {
        "msn": alias,
        "label": names.label(alias, key_field="msn_id") if alias else "",
        "sandbox": sandbox,
        "charges": charges,
        "credits": credits,
        "charged": charged,
        "credited": credited,
        "balance_cents": owed,
        "balance": format_cents(str(owed)),
        # Stated rather than inferred from an empty list: "this alias has no charges" and
        # "this sandbox keeps no sales book" are different answers, and a statement that
        # showed $0.00 for the second would be reporting a missing book as a paid account.
        "books_present": {
            SALES_DOC: _read(store, tenant_id=tenant_id, sandbox=sandbox,
                             name=SALES_DOC) is not None,
            CREDITS_DOC: _read(store, tenant_id=tenant_id, sandbox=sandbox,
                               name=CREDITS_DOC) is not None,
        },
    }


def _owning_msn(document: Any) -> str:
    """The msn a document's canonical id names, or ``""``.

    `lv.<msn>.<sandbox>.<name>.<hash>`. Parsed through the naming contract rather than by
    splitting on dots, because which segment is the msn is the contract's fact and a
    hand-split is one rename away from reading the sandbox as an address.
    """
    from micyte.core.document_naming import CanonicalNameError, parse_canonical_document_id

    if document is None:
        return ""
    try:
        return parse_canonical_document_id(as_text(document.document_id)).msn_id
    except (CanonicalNameError, AttributeError):
        return ""


def cost_summary(
    authority_db_file: Path, *, sandbox: str = GRANTOR_SANDBOX,
    tenant_id: str = _TENANT_DEFAULT,
) -> dict[str, Any]:
    """What AWS charged FND, split the way the operator asked for it.

    R8's *"especially those items that aren't attributable to a client"*. The split is the
    row's `msn_id`: a cost row against a CLIENT msn is billable to them, a row against
    FND's own is overhead FND absorbs. That is not a convention imposed here — it is what
    `project_tolling_to_datum` writes, because the `invoice` archetype requires an `msn_id`
    and the instance that pays a residue line is FND.

    Measured on the live ledger's four periods, 2026-08-24: **$317.66 total, $313.53
    (98.7%) borne by FND, $4.13 billable across the whole client base.** A tolling tab that
    showed only the billable side would make hosting look almost free.
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops.fiat_datum import format_cents

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    registry, names = _context(store, tenant_id=tenant_id, sandbox=sandbox)
    book = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=SUPPLY_DOC)
    rows = _rows(book, sandbox=sandbox, registry=registry, names=names)

    # WHOSE sandbox this is, taken from the book's own canonical address rather than from
    # the request's instance scope. `lv.<msn>.<sandbox>.<name>.<hash>` carries the owning
    # msn, so the answer is a property of the document being read — not of who is asking,
    # which is what a scope lookup would have made it.
    operator = _owning_msn(book)
    borne, billable = 0, 0
    for row in rows:
        cents = int(row.get("amount_cents") or 0)
        if operator and as_text(row.get("party")) != operator:
            billable += cents
        else:
            borne += cents
    total = borne + billable
    return {
        "sandbox": sandbox,
        "projected": book is not None and bool(rows),
        "entries": len(rows),
        "total_cents": total, "total": format_cents(str(total)),
        "borne_by_fnd_cents": borne, "borne_by_fnd": format_cents(str(borne)),
        "billable_cents": billable, "billable": format_cents(str(billable)),
        # The percentage IS the finding, so it is computed here rather than left to a
        # surface to divide two numbers and possibly divide them differently.
        "borne_by_fnd_pct": round(100 * borne / total, 1) if total else None,
        "note": "" if rows else (
            f"No cost has been projected into {sandbox}/{SUPPLY_DOC} yet. Run "
            "`project_tolling_to_datum.py` — until then this tab shows what each grantee "
            "is invoiced and nothing about what serving them costs."),
    }


def pricing_sheet(
    authority_db_file: Path, *, sandbox: str = GRANTOR_SANDBOX,
    tenant_id: str = _TENANT_DEFAULT,
) -> dict[str, Any]:
    """The standing offers, and what the whole operation costs to run.

    **Totals, not a per-service allocation, and that is deliberate.** The obvious surface
    would put each service's share of AWS cost beside its price. There is no such share:
    `1-3 service` and `1-4 cost_category` are independent branches with nothing linking
    them, and the measurement that settles it is the same one that made this task
    necessary — for 2026-08, $64.96 of $72.93 (89.1%) of AWS cost was untagged residue
    attributable to no client, and by the same token to no service. A per-service overhead
    column would be a number invented by an allocation rule nobody chose, printed next to a
    real price.

    So it reports what is real: what is actually BILLED on one side, measured overhead on
    the other, and the difference. The margin becomes a number the operator READS rather
    than an allocation they have to trust.

    **Billed, not the price list added up.** The first version of this summed
    `price_cents` across the offers and called the result "priced revenue". It is not
    revenue, and the sum is not money:

      * a price list is a list of RATES, and revenue is quantity x rate. Nobody had
        subscribed to anything, so the true figure was $0.00 while the surface said $15.00;
      * the addends have different denominators -- $5.00 `per month` + $1.00 `per domain`
        + $1.00 `per GB` adds a month to a domain to a gigabyte;
      * and it was then subtracted from a cost book spanning four AWS billing periods,
        which has no period in common with a rate card.

    The extension already exists and there is deliberately only one of it, in
    `subscription_ledger` -- *"the extension is COMPUTED, here, from the two rows, and
    there is exactly one place that multiplies"*. This function asks it rather than
    growing a second.

    **The absence is named in BOTH directions.** The original refused a margin when the
    cost book was unprojected, on the grounds that an empty cost column beside a real price
    list reads as "we have no costs" -- the most flattering possible lie. The same
    discipline was never applied to the revenue side, which is the side flattery actually
    comes from. `books_present` now says which of the three books exist, so a reader can
    tell "no alias has subscribed" (a real, unflattering zero) from "this sandbox keeps no
    subscription book" (an unknown).
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops.fiat_datum import format_cents

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    registry, names = _context(store, tenant_id=tenant_id, sandbox=sandbox)

    offering = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=OFFER_DOC)
    offers = ([] if offering is None else offer_rows(
        offering, sandbox=sandbox, archetype=registry.get(OFFER_ARCHETYPE), names=names))

    # The one place that multiplies quantity by rate lives in `subscription_ledger`. Asking
    # it costs a second read of the offering document and buys the guarantee that the home
    # tab and the subscription tab can never disagree about what a grantee owes.
    held = subscription_ledger(authority_db_file, sandbox=sandbox, tenant_id=tenant_id)
    billed = int(held["total_cents"])

    cost_book = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=SUPPLY_DOC)
    costs = _rows(cost_book, sandbox=sandbox, registry=registry, names=names)
    overhead = ledger_totals(costs)

    return {
        "sandbox": sandbox,
        "offers": offers,
        "offers_count": len(offers),
        # What the rate card SAYS, and never a total: no two rows share a denominator.
        "billed_cents": billed,
        "billed": format_cents(str(billed)),
        "subscriptions": held["subscriptions"],
        "held_unpriced": held["unpriced"],
        "books_present": {
            "offering": offering is not None,
            "subscriptions": _read(
                store, tenant_id=tenant_id, sandbox=sandbox,
                name=SUBSCRIPTIONS_DOC) is not None,
            "supply": cost_book is not None,
        },
        "overhead_cents": overhead["cents"],
        # `format_cents`, NOT `ledger_totals`'s own `total`. The two disagree about the
        # dollar sign — `ledger_totals` formats through `job_manager.money`, which renders
        # "0.00", while `fiat_datum.format_cents` renders "$0.00" — and a payload whose
        # `priced` says "$0.00" beside an `overhead` saying "0.00" invites a reader to
        # think one of them is not money. One formatter per payload; the wider question of
        # which of the two the product should keep is TASK-2026-08-24-008.
        "overhead": format_cents(str(overhead["cents"])),
        "overhead_entries": overhead["entries"],
        # The honest half. Until phase D projects `tolling_ledger.json` into this book the
        # cost side is EMPTY, and an empty cost side next to a real price list would read
        # as "we have no costs" — the most flattering possible lie. So the absence is
        # named, and a margin is offered only when there is something to subtract.
        "overhead_projected": cost_book is not None and bool(costs),
        "margin_cents": (billed - overhead["cents"]) if costs else None,
        "margin": format_cents(str(billed - overhead["cents"])) if costs else "",
        "note": "" if costs else (
            f"No cost has been projected into {sandbox}/{SUPPLY_DOC} yet, so no margin is "
            "shown. What AWS charges FND is measured in the operator tolling ledger; "
            "projecting it here is what makes these two figures comparable."),
        # A zero that is TRUE reads exactly like a zero that is missing, so it is named.
        # The margin is still shown: FND billing nothing while spending real money is the
        # unflattering direction, and the number the operator most needs.
        "billed_note": "" if held["subscriptions"] else (
            "No alias holds a subscription yet, so nothing is billed. The prices below are "
            "the standing rate card, not revenue -- a rate is charged per month, per "
            "domain or per GB, and those do not add up to a figure."),
    }


def subscription_ledger(
    authority_db_file: Path, *, msn: str = "", sandbox: str = GRANTOR_SANDBOX,
    tenant_id: str = _TENANT_DEFAULT,
) -> dict[str, Any]:
    """What each alias holds, at what the price list says — the JOIN, in one place.

    TASK-2026-08-24-010, and the answer to phase E's first step: *read the alias's services
    and quantities*. Two documents meet here on the service NODE:

        `subscriptions`   (alias, service node, quantity, since)   what is held
        `offering`        (service node, price, unit)              what it costs

    Neither carries the other's half. A subscription that stored its own price would go
    stale the first time R7's pricing surface changed one, and an offer that stored a
    quantity would be a price list that knows who its customers are. So the extension —
    quantity x unit price — is COMPUTED, here, from the two rows, and there is exactly one
    place that multiplies.

    A subscription whose service the offering does not price is reported, not dropped, with
    ``priced=False`` and no amount. That is a real state and a real question for the
    operator — the grantee holds something nobody has priced — and a row silently missing
    from a billing run is the expensive way to find out.
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops.fiat_datum import format_cents

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    registry, names = _context(store, tenant_id=tenant_id, sandbox=sandbox)

    offering = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=OFFER_DOC)
    offers = ([] if offering is None else offer_rows(
        offering, sandbox=sandbox, archetype=registry.get(OFFER_ARCHETYPE), names=names))
    #: service node -> the offer that prices it. LAST wins: `offering` is an append-path
    #: document, so a re-priced service is a NEW row and the newest is the current price.
    priced_by_node = {
        as_text(offer.get("product_node")): offer
        for offer in offers if as_text(offer.get("product_node"))
    }

    # The roster names the aliases; the msn address space cannot — see
    # `ledger_books.account_labels`. Read here too so the ledger's lines and the
    # Subscriptions table say the same word for the same party.
    from .ledger_books import ACCOUNTS_DOC, account_labels

    roster = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=ACCOUNTS_DOC)
    accounts = ({} if roster is None else account_labels(
        roster, sandbox=sandbox, archetype=registry.get("channel_account")))

    held = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=SUBSCRIPTIONS_DOC)
    subscriptions = ([] if held is None else subscription_rows(
        held, sandbox=sandbox, archetype=registry.get(SUBSCRIPTION_ARCHETYPE),
        names=names, accounts=accounts))
    wanted = as_text(msn)
    if wanted:
        subscriptions = [row for row in subscriptions if row.get("party") == wanted]

    lines: list[dict[str, Any]] = []
    total = 0
    unpriced = 0
    for row in subscriptions:
        offer = priced_by_node.get(as_text(row.get("service_node")))
        line = dict(row)
        if offer is None:
            unpriced += 1
            line.update({"priced": False, "unit": "", "unit_price": "",
                         "unit_price_cents": 0, "amount": "", "amount_cents": 0})
            lines.append(line)
            continue
        unit_cents = int(offer.get("price_cents") or 0)
        count = int(row["quantity"]) if as_text(row.get("quantity")).isdigit() else 0
        # The INCLUDED allowance (2026-09-11): the offer may say the first N units are in
        # the base price, and only what a subscription holds beyond that is billed. This
        # is the one place that multiplies, so it is the one place that subtracts.
        included_text = as_text(offer.get("included_units"))
        included = int(included_text) if included_text.isdigit() else 0
        billable = max(0, count - included)
        extended = unit_cents * billable
        total += extended
        line.update({
            "priced": True,
            # The unit is the OFFER's word, never restated on the subscription.
            "unit": as_text(offer.get("unit")),
            "unit_price": format_cents(str(unit_cents)),
            "unit_price_cents": unit_cents,
            "included_units": included,
            "billable_units": billable,
            "amount": format_cents(str(extended)),
            "amount_cents": extended,
        })
        lines.append(line)

    return {
        "sandbox": sandbox,
        "msn": wanted,
        "lines": lines,
        "subscriptions": len(lines),
        "unpriced": unpriced,
        "total_cents": total,
        "total": format_cents(str(total)),
    }


__all__ = ["GRANTOR_SANDBOX", "account_statement", "cost_summary", "pricing_sheet",
           "subscription_ledger"]


# --------------------------------------------------------------------------- #
# The payment instrument RECORD (TASK-2026-09-16-001)
# --------------------------------------------------------------------------- #
#: The lcl branch whose children are the instrument STATES — `present`, `absent`,
#: `expired`, `failing` — minted under the grantor's object node by
#: `fnd_app/scripts/mint_instrument_states.py`. Found by LABEL, never by address: the
#: live tree is canonical (`1-3 objects / 1-3-1 grantor / …`) and a fixture's is not, and
#: every reader here finds a branch the way `read_log` finds `meta`.
INSTRUMENT_STATE_LABEL = "instrument_state"

#: The title an `absent` row carries. A `channel_account` row REQUIRES a title, and an
#: absent instrument has no recogniser to put there — so it says what it is. ASCII, so
#: the title babelette can hold it.
ABSENT_TITLE = "no card on file"


def instrument_state_nodes(log: Any) -> dict[str, str]:
    """``state label -> lcl node`` for the instrument-state branch, or ``{}`` when the
    tree has not minted one.

    Empty is a STATE: a grantor tree minted before 2026-09-16 has no branch, and a reader
    that raised here would make every present grantee's document unreadable for the sake
    of a row none of them carries.
    """
    from micyte.core.datum_ops.node_addrs import parent_of

    entries = getattr(log, "entries", None) or {}
    branch = next((node for node, entry in entries.items()
                   if as_text(getattr(entry, "label", "")).lower() == INSTRUMENT_STATE_LABEL),
                  "")
    if not branch:
        return {}
    return {
        as_text(entry.label).lower(): node
        for node, entry in entries.items()
        if parent_of(node) == branch and as_text(entry.label)
    }


def instrument_rows(document: Any, *, sandbox: str, archetype: Any,
                    state_nodes: dict[str, str], authority: Any = None) -> list[dict[str, Any]]:
    """The instrument rows of one grantee document, oldest first.

    A `channel_account` row whose ``lcl_id`` is one of the instrument-state nodes. The
    BRANCH is what tells an instrument row from a service row — the same rule that tells a
    slot from an artifact on a local domain: "which KIND that is comes from the branch the
    address sits under". The recogniser rides in ``title``; ``utc`` is the day it was
    recorded. Nothing else is carried, because nothing else may be.
    """
    from ._viewscope import _row_values

    by_node = {node: label for label, node in state_nodes.items()}
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        node = next((v for v in values.get("lcl_id", ()) if v), "")
        if node not in by_node:
            continue
        stamps = [v for v in values.get("utc", ()) if v]
        rows.append({
            "datum_address": row.datum_address,
            "state": by_node[node],
            "state_node": node,
            "recogniser": decode_label(next((v for v in values.get("title", ()) if v), "")),
            "when": _readable(authority, stamps[0]) if stamps else "",
        })
    rows.sort(key=lambda r: tuple(int(p) for p in as_text(r["datum_address"]).split("-")
                                  if p.isdigit()))
    return rows


def instrument_record(
    authority_db_file: Path, *, msn: str, sandbox: str = GRANTOR_SANDBOX,
    tenant_id: str = _TENANT_DEFAULT,
) -> Any:
    """The card on file for one alias, as an ``InstrumentRecord`` — or ``None``.

    ``None`` means NO ROW: the honest state of every grantee onboarded before the record
    existed, and a different answer from a row that says ``absent``. Surfaces word the
    two differently ("no card has been recorded for this account" against "no card is on
    file"), which is why this returns nothing rather than inventing an absent record.

    The LATEST row wins. The grantee document is an append-path document, so a replaced
    card is a new row after the old one, and reading the last is reading the current.
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops import local_domain as ld
    from micyte.core.payment_instrument import (
        STATE_ABSENT,
        InstrumentRecord,
        InstrumentRecordError,
        parse_recogniser,
    )

    from ._hops_dates import chrono_authority
    from ._viewscope import local_domain_document_id, read_document

    alias = as_text(msn)
    if not alias:
        return None
    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    lcl_id = local_domain_document_id(store, tenant_id=tenant_id, sandbox=sandbox)
    log = ld.read_log(read_document(store, tenant_id=tenant_id, document_id=lcl_id)
                      if lcl_id else None)
    nodes = instrument_state_nodes(log)
    if not nodes:
        return None
    document = _read(store, tenant_id=tenant_id, sandbox=sandbox, name=f"grantee-{alias}")
    if document is None:
        return None
    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    anchor = _read(store, tenant_id=tenant_id, sandbox=sandbox, name="anchor")
    authority = chrono_authority(anchor) if anchor is not None else None
    rows = instrument_rows(document, sandbox=sandbox, archetype=registry.get("channel_account"),
                           state_nodes=nodes, authority=authority)
    if not rows:
        return None
    latest = rows[-1]
    state = latest["state"]
    if state == STATE_ABSENT:
        return InstrumentRecord(alias=alias, state=state, arrived_at=latest["when"])
    try:
        brand, last4, month, year = parse_recogniser(latest["recogniser"])
    except InstrumentRecordError:
        # A present row whose title is not a recogniser cannot be shown as a card. Said
        # as absent-with-a-date rather than crashed: the row exists, it just describes
        # nothing a person could recognise.
        return InstrumentRecord(alias=alias, state=STATE_ABSENT, arrived_at=latest["when"])
    return InstrumentRecord(alias=alias, state=state, brand=brand, last4=last4,
                            exp_month=month, exp_year=year, arrived_at=latest["when"])
