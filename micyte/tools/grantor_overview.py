"""The grantor application's home — what FND charges, and what running it costs.

TASK-2026-08-24-005 phase B. The operator's depiction puts this on the FND instance and
nowhere else: *"since the grantor application is only on the FND instance, the actual
application UI provided should allow me to change the prices of services"*.

## Why an application and not another channel tab

`micyte.channels` refuses, by construction, any channel that declares writes — *"the open
session routes are GET-only ... 'no write path exists' is the only safe posture"*. The
grantor CHANNEL is the client's read-only view of their own row. Setting a price is a
write, so it cannot live there.

So the two are different things wearing one name, and this is the operator's half: an app
tied to the `grantor` sandbox, whose tabs are the ordinary ledger books, writing through
the same `datum_write_policy` chokepoint as every other write in the product. The channel
keeps its refusal intact.

## What the home tab answers first

**Are we charging more than this costs?** — which is the question the whole task exists
for. FND's per-grantee invoice was AWS cost x margin until now, and for 2026-08 that model
made the entire client base billable for $0.032, because $64.96 of the $72.93 was untagged
residue attributable to no client.

So the home tab shows what is BILLED against measured overhead, and says plainly when
either side is absent. An empty cost column beside a real price list would read as "we
have no costs", which is the most flattering possible lie for a page whose job is to stop
prices being set by accident.

**The rate card is not the revenue, and this tab used to add it up.** The notice read
"Priced $15.00 against measured overhead $317.66 — margin -$302.66" on the day the
operator's first prices went in. Every part of that was wrong: nobody had subscribed, so
the true billed figure was $0.00; the $15.00 was $5.00 `per month` added to $1.00
`per domain` added to $1.00 `per GB`; and it was subtracted from four AWS billing periods.
`pricing_sheet` now reports `billed_cents` from the subscription join, and the rate card is
shown as what it is — a list of rates, counted, never totalled.

It does NOT show a per-service overhead share. There is no such share: `1-3 service` and
`1-4 cost_category` are independent branches, and most cost attributes to no service any
more than it attributes to a client. A column invented by an allocation rule nobody chose,
printed beside a real price, is the confusion the two-branch split was made to avoid.

## The second pane: which clients take money on their own sites

Added 2026-09-02, the day after clients gained the ability to connect their own PayPal
from PIM's Payment tab. That write landed with no operator-side read at all: eight clients
could each connect, disconnect or misconfigure a merchant account and no screen said so.

WHY HERE and not on the two surfaces it was weighed against. `grantor_permissions` reads
what this HOST permits on its own bindings; a client's PayPal is neither a binding of this
host nor a permission — its three columns (declared / bound / granted) have no answer for
it. Utilities > Key Pass Wallet is closer — it is the operator-gated cross-tenant surface
and it already reports that a payment secret is on file — but it answers per ALIAS in a
fixed row shape (family, state, fingerprint) with nowhere to put a domain, and the
environment lives there as four characters inside a fingerprint string, which is exactly
the subtle badge this must not be. This tab is the grantor app's home; the app is the
operator's side of the hosting relationship and installs on the FND instance and nowhere
else. A fact about the whole client base belongs on the hub, not inside a tab about
something else.

AND THE TWO PANES ARE NOT ONE FIGURE. Nothing here adds a client's takings to FND's
margin, and nothing should: what a client's site collects is THEIR money, routed to their
own merchant account, and what FND bills them is the pane above. Two facts about one
relationship, shown together and never summed — the mistake the notice above was rewritten
to stop making.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .grantor_books import GRANTOR_SANDBOX, pricing_sheet

_SCHEMA = "mycite.v2.portal.workbench.tool.grantor_overview.v1"

#: PayPal's two worlds, SAID rather than badged. The operator's question is not "is a
#: field set", it is "is this client taking real money" — and a client who believes they
#: are while bound to sandbox is a support call, not a styling detail. So the word carries
#: the consequence, and the cell is read at a glance instead of decoded.
_ENVIRONMENT_WORDS: dict[str, str] = {
    "live": "LIVE — real money",
    "sandbox": "SANDBOX — test payments only, nothing reaches the client",
}

#: A connected block with no environment recorded. NOT "unknown":
#: `_resolve_paypal_credentials_for_domain` reads an absent environment as `sandbox` when
#: it routes a real checkout, so the site IS in sandbox whatever the leaflet omits, and
#: "unknown" would hide a live consequence behind a missing field. Only a hand-edited
#: leaflet reaches this state — the connect form always writes the environment.
_ENVIRONMENT_UNSTATED = "SANDBOX — not recorded, and the checkout route defaults to it"

_PAYMENT_COLUMNS = ["client", "domain", "connected", "environment"]


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _client_payments(host_context: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    """``(roster, why_not)`` — the host's answer, or the reason there is not one.

    THREE REFUSALS, NOT ONE, and none of them may arrive as an empty table. "This render
    was handed no reader" (a sign-in that is not the operator's), "the reader refused" and
    "the portal could not read its own store" send someone to three different places — and
    "no client has connected PayPal", the real state they must never be confused with, is
    a table of rows rather than an empty one. The same distinction `grantor_permissions`
    draws for the matrix, kept because an empty table cannot tell them apart.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("client_payments")
    if not callable(provider):
        return {}, (
            "this portal did not offer a client payment reader to this render. The pane "
            "is the operator's own — a sign-in that is not the operator is not shown "
            "which of every client's sites takes money.")
    try:
        data = provider()
    except Exception as exc:  # the host's own refusal, in the host's own words
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "the client payment reader answered with something that is not a roster"
    if not data.get("readable"):
        return {}, (_as_text(data.get("why_not"))
                    or "this portal could not read which clients it hosts")
    return data, ""


def _connected_word(row: dict[str, Any]) -> str:
    """The CONNECTED column, in words rather than a tick — `_state_word`'s rule next door.

    "no" is not the useful answer for a client whose leaflet already carries a client id:
    they began the form and stopped, and asking them to begin is the wrong conversation.
    The reading itself is never recomputed here. `grantee_payment_runtime.connection` owns
    "both halves or neither"; this only names what it decided.
    """
    if _as_text(row.get("why_not")):
        return "cannot tell"
    if row.get("connected"):
        return "yes"
    if row.get("half_connected"):
        return "NO — a client ID is on file with no secret"
    return "no"


def _environment_word(row: dict[str, Any]) -> str:
    if not row.get("connected"):
        # Nothing is routed to either world, so neither is the answer. The house em dash
        # rather than an empty cell, which reads as a value somebody forgot to fill in.
        return "—"
    return _ENVIRONMENT_WORDS.get(
        _as_text(row.get("environment")), _ENVIRONMENT_UNSTATED)


def _payments_pane(host_context: dict[str, Any] | None) -> dict[str, Any]:
    """Every client site this portal routes, and whether it takes money. READ ONLY.

    There is no connect, disconnect or edit here and there must not be. The credential is
    the CLIENT'S, entered by them in their own app against their own merchant account, and
    an operator control over another party's payment key is a capability nobody asked for.
    This says what is true and offers no verb.
    """
    empty: dict[str, Any] = {
        "schema": _SCHEMA, "container": "record_table", "title": "Client payments",
        "columns": _PAYMENT_COLUMNS, "rows": [], "row_count": 0,
    }
    roster, why_not = _client_payments(host_context)
    if why_not:
        return {**empty, "empty_text": why_not}

    clients = [c for c in (roster.get("clients") or ()) if isinstance(c, dict)]
    rows = [{
        "client": _as_text(client.get("label")) or "—",
        "domain": _as_text(client.get("domain")) or "—",
        "connected": _connected_word(client),
        "environment": _environment_word(client),
        # THE ROW AN OPERATOR OPENS THIS FOR: connected, and not to live. Drawn
        # differently rather than only counted, because "1 in sandbox" sends somebody to
        # read a config file while a marked row names the client.
        "is_flagged": (bool(client.get("connected"))
                       and _as_text(client.get("environment")) != "live"),
    } for client in clients]

    connected = sum(1 for c in clients if c.get("connected"))
    live = sum(1 for c in clients if c.get("connected")
               and _as_text(c.get("environment")) == "live")
    unreadable = sum(1 for c in clients if _as_text(c.get("why_not")))
    notice = (
        f"{connected} of {len(clients)} client site(s) have their own PayPal connected — "
        f"{live} taking real money and {connected - live} in sandbox, where a payment is a "
        "test and nothing reaches the client. The credential is the client's own, entered "
        "on their Payment tab; this reports it and cannot change it."
    )
    if unreadable:
        notice = (
            f"{notice} {unreadable} site(s) could not be checked — the connected column "
            "says so rather than reporting them as unconnected.")
    refused = roster.get("refused") or []
    if refused:
        notice = (
            f"{notice} {len(refused)} binding(s) in this config could not be read, so "
            "their sites are absent from this table entirely: "
            f"{'; '.join(f'{r[0]}: {r[1]}' for r in refused)}.")
    return {
        **empty,
        "rows": rows,
        "row_count": len(rows),
        "row_class_key": "is_flagged",
        "count_label": f"{connected} of {len(rows)} connected",
        "empty_text": (
            "No client site is connected to this portal, so there is nobody to have "
            "connected PayPal. A client appears here once their site_hosting binding is "
            "configured on Utilities > Ports — not when they connect a key."
        ),
        "notice": notice,
    }


class GrantorOverview:
    """The grantor app's home: the standing offer, and what it is measured against."""

    tool_id = "grantor_overview"
    label = "Grantor"
    summary = (
        "What FND bills for hosting and what hosting costs FND: what aliases actually "
        "hold, against measured overhead, beside the standing rate card. Prices are set "
        "on the Offering tab; the cost side is projected from the operator tolling ledger."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Launched by ADDRESS as a hub, not offered for a document in focus.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    #: The client payment roster is the HOST's: it is read from this deployment's port
    #: bindings and its grantee secret store, and `micyte` may reach neither. Declared
    #: rather than reached for — the seam `grantor_permissions` already takes.
    wants_host_context = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        """The standing offer against measured overhead, and who can take money.

        A composite rather than one table: they are two facts about one relationship and
        neither is a column of the other. Priced first, because the margin is the question
        this tab was built for; the roster below it is the one nothing else could answer.
        """
        del document_id, datum_address
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [
                {"panel_payload": self.pricing_pane(
                    authority_db_file=authority_db_file, sandbox_id=sandbox_id)},
                {"panel_payload": _payments_pane(host_context)},
            ],
        }

    def pricing_pane(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
    ) -> dict[str, Any]:
        """What is priced, against what it costs — the tab as it stood, unchanged."""
        if authority_db_file is None:
            return {
                "schema": _SCHEMA, "container": "record_table", "title": self.label,
                "columns": ["service", "price", "per"], "rows": [], "row_count": 0,
                "empty_text": "The authority database is not configured.",
                "notice": "No store to read the books from.",
            }
        sandbox = str(sandbox_id or "").strip() or GRANTOR_SANDBOX
        sheet = pricing_sheet(Path(authority_db_file), sandbox=sandbox)
        rows = [
            {"service": row.get("product") or row.get("product_node"),
             "price": row.get("price"),
             "per": row.get("unit") or "—",
             "note": row.get("note") or ""}
            for row in sheet["offers"]
        ]
        # Two figures, and EITHER is allowed to be absent. A margin computed against an
        # unprojected cost book subtracts zero; one computed from the rate card invents a
        # revenue nobody was charged.
        count = f"{sheet['offers_count']} service{'' if sheet['offers_count'] == 1 else 's'}"
        if sheet["overhead_projected"]:
            notice = (
                f"Billed {sheet['billed']} against measured overhead "
                f"{sheet['overhead']} over {sheet['overhead_entries']} cost entries "
                f"— margin {sheet['margin']}. {count} priced."
            )
        else:
            notice = f"Billed {sheet['billed']}, {count} priced. {sheet['note']}"
        if sheet["billed_note"]:
            notice = f"{notice} {sheet['billed_note']}"
        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": self.label,
            "count_label": f"{len(rows)} service{'' if len(rows) == 1 else 's'} priced",
            "columns": ["service", "price", "per", "note"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": (
                "No service is priced yet. A service is an lcl node under the grantor "
                "local domain's `service` branch, and an offer is what puts a price on "
                "one — set them on the Offering tab."
            ),
            "notice": notice,
            "pricing": {
                "billed_cents": sheet["billed_cents"],
                "offers_count": sheet["offers_count"],
                "subscriptions": sheet["subscriptions"],
                "held_unpriced": sheet["held_unpriced"],
                "books_present": sheet["books_present"],
                "overhead_cents": sheet["overhead_cents"],
                "overhead_projected": sheet["overhead_projected"],
                "margin_cents": sheet["margin_cents"],
            },
        }


register(GrantorOverview())
