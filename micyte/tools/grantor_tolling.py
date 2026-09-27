"""The TOLLING tab — what running the network actually costs, residue included.

R8 of the operator's depiction, and the half that names the hard part: *"a datum doc that
backs the TOLLING tab which will collect the overall aws cost incurred, especially those
items that arn't attributable to a client, like processing etc."*

The `grantor/invoices` book already holds it — projected from the operator tolling ledger
by `project_tolling_to_datum`, never typed by hand, so a figure here and the AWS bill
cannot drift. What was missing was a surface: `cost_summary` computed the numbers and
nothing showed them.

## Why the emphasis is on what is NOT attributable

Measured across four periods: **$317.66 total, of which $313.53 — 98.7% — is borne by FND
and $4.13 is billable to a client.** For 2026-08 alone, $64.96 of $72.93 was untagged
residue attributable to nobody.

That is the finding the whole grantor paradigm exists because of. The old per-grantee
invoice was AWS cost x margin, and on those numbers the entire client base billed
**$0.032 a month**. A tolling tab that showed only the attributable slice would reproduce
exactly that mistake in a nicer table, so the residue is not a footnote here: it is the
first column and the headline.

## Four tabs, because the operator's cost admin came home here (2026-08-30)

The operator's legacy `fruitfulnetworkdevelopment.com/dashboard/` is being retired, and
three of its tabs — `tolling_operator.js`, `tolling_admin.js`, `aws_operator.js` — were
the only callers of `/__fnd/tolling/*` and `/__fnd/aws/inventory`. Their replacement is
this tab rather than a second one, because both would have been reading the same cost:

* **Cost record** — the projected `grantor/invoices` book. What the grantor paradigm bills
  against.
* **Ledger** — the operator ledger the projection is made FROM, a period at a time, with
  the recompute that rebuilds it.
* **Billing rules** — the margins, waivers and pool splits the ledger is multiplied by.
* **Inventory** — the live AWS resource counts the cost lines are counts OF.

Putting the SOURCE and its PROJECTION under one tab is the point: they can disagree — the
projection is only as fresh as the last `project_tolling_to_datum` run — and a disagreement
split across two surfaces is one nobody compares.

## Still no hand-entered cost, and that has not changed

There is no ADD button and no editable amount. A cost row is a PROJECTION of the tolling
ledger; a hand-entered one is a number that disagrees with the bill it claims to mirror,
and nothing downstream could tell which was right. The grantor package provisions
`invoices` "with no writing surface offered" for this reason.

**What is now writable is the two things that were never costs.** Billing RULES are a rate
card — a decision, not a measurement — and a RECOMPUTE re-derives the ledger from the bill
rather than typing over it. Both post to the operator-only `/__fnd/tolling/*` routes, which
check a typed confirmation server-side; neither can put a figure into the ledger that AWS
did not report. So the invariant the read-only posture was protecting still holds: **every
number on this tab is derived, and the derivation is the only way in.**

## It reaches nothing by itself

`micyte` holds no filesystem read and may not name the FND application. The ledger, the
rules and the inventory ARRIVE through `host_context`, which resolves the caller's identity
against the same operator gate the routes sit behind and refuses in one place. This module
renders what it is handed and says what it was not handed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .grantor_books import GRANTOR_SANDBOX, cost_summary

_SCHEMA = "mycite.v2.portal.workbench.tool.grantor_tolling.v1"

#: How a cost line's bearer is read. The projection writes WHO BEARS the cost into
#: `msn_id` — the client for a `direct` line, FND for `shared_pool` and `residue` — so the
#: split is a fact in the row rather than a rule applied at read time.
_BORNE_BY_FND = ("shared_pool", "residue")

#: This hub's own tab parameter. Its OWN, like every nested hub in the portal: sharing the
#: parent's would make choosing a tab here move the parent's tab too.
TAB_QUERY = "tolling_section"
DEFAULT_TAB = "cost"

#: Which month the Ledger tab is showing. Separate from the tab parameter so a period stays
#: chosen while the reader moves between tabs — and so the recompute below the table always
#: names the month above it.
PERIOD_QUERY = "tolling_period"

TABS = ("cost", "ledger", "rules", "inventory")

#: The two operator actions, as addresses. The routes judge the caller and check the typed
#: confirmation; this only says which door. They are the SAME routes the retired legacy
#: tabs posted to — a new pair beside them would have been a second writer of one file.
REFRESH_ROUTE = "/__fnd/tolling/refresh"
BILLING_RULES_ROUTE = "/__fnd/tolling/billing-rules"

#: Rule keys the edit form draws, in the order it draws them: `(path, label, kind)`. The
#: PATH is the field key the form submits, and `merge_billing_rules` reads it as the place
#: in the rules document the value lands — which is what lets a flat form edit a nested
#: rule with no mapping table on the route. `kind` names where the options come from; the
#: allow-lists themselves are the host's, so a select cannot offer a mode the route rejects.
_RULE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("defaults.margin_pct",
     "Margin % added to a client's attributable cost", ""),
    ("defaults.minimum_invoice",
     "Minimum invoice (below this, nothing is billed)", ""),
    ("defaults.residue_handling",
     "Untagged residue — cost AWS attributes to nobody", "residue_handling"),
    ("defaults.residue_distribution_pct",
     "…if distributed: % spread across non-operator grantees", ""),
)


def attribution_of(note: str) -> str:
    """`direct` | `shared_pool` | `residue`, from the line's own note.

    The projection writes the attribution as the first word of the note (`"residue
    compute"`, `"shared_pool compute"`, `"direct data_transfer"`). Read rather than
    re-derived: deciding it here from the bearer msn would be a second definition of the
    split, free to disagree with the one that wrote the row.
    """
    head = str(note or "").strip().split(" ", 1)[0]
    return head if head in (*_BORNE_BY_FND, "direct") else "unknown"


def ledger_attribution_of(line: dict[str, Any]) -> str:
    """The same three words, read off a LEDGER line instead of a projected datum row.

    Not a second definition of the split — a second ENCODING of it. The ledger row keeps the
    attribution as a structured `{"type": ...}` because it is a JSON document with room for
    one; the projected datum row keeps the same word as the first token of its note because
    a fiat cell has nowhere structured to put it. Both READ what their own document stores,
    and both answer in the vocabulary the host names once.

    Anything else answers `unknown` rather than being folded into a bucket it might not
    belong in: a line silently counted as residue would inflate the one figure this whole
    tab exists to report honestly.
    """
    kind = str((line or {}).get("attribution", {}).get("type") or "").strip()
    return kind if kind in (*_BORNE_BY_FND, "direct") else "unknown"


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _notice(title: str, text: str) -> dict[str, Any]:
    """A pane that carries a REFUSAL, not an empty table.

    "You have no cost record" and "you may not see the cost record" want opposite next
    actions, and a table with no rows says the first while meaning the second.
    """
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0,
            "count_label": "", "empty_text": text}


def tolling_facts(
    host_context: dict[str, Any] | None,
    *,
    period: str = "",
    inventory: bool = False,
) -> tuple[dict[str, Any], str]:
    """``(facts, why_not)`` — the operator's cost record, or the reason this render has none.

    The refusal is CARRIED, the same way `pim_design.site_port` carries the site seam's. A
    tab that renders "no cost recorded" over a ledger the caller is simply not the operator
    for teaches them the network costs nothing, and they will believe it.

    Three states, distinguished: no host at all (this door hands tools no context — the
    failure that left PIM's Design tab refusing a working port for a day), a host that
    refused, and facts.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("tolling")
    if not callable(provider):
        return {}, ("This portal did not offer the cost record to this render, so the "
                    "tolling ledger cannot be reached from here.")
    try:
        facts = provider(period=period, inventory=inventory)
    except Exception as exc:
        # The host's own refusal, shown as itself. Flattening it would report an
        # unreadable ledger as an empty one.
        return {}, str(exc)
    if not isinstance(facts, dict) or not facts.get("permitted"):
        return {}, (_as_text((facts or {}).get("why_not"))
                    or "The cost record is the operator's, and was not offered here.")
    return facts, ""


def _period_pick(facts: dict[str, Any], period: str) -> dict[str, Any]:
    """The month picker. Offers periods the ledger has NO row for, deliberately.

    A month with no row is exactly the month a recompute is for, so a picker listing only
    computed periods hides the one the operator came to run — and on the 1st of a month,
    that is every operator.
    """
    computed = set(facts.get("periods_available") or ())
    return {
        "label": "Month",
        "param": PERIOD_QUERY,
        "options": [
            {"value": p, "label": p if p in computed else f"{p} — not computed yet"}
            for p in facts.get("refreshable_periods") or ()
        ],
    }


def _periods_pane(facts: dict[str, Any]) -> dict[str, Any]:
    """Every computed month, summed from its own rows.

    `total` is not stored anywhere: `summarize_ledger` adds the line items up. The split
    beside it is added up the same way and from the same lines, so the four attribution
    columns and the total cannot disagree — which they could when the split was read out of
    a `totals_by_attribution` written at compute time and the total was not.
    """
    rows = [{
        "period": _as_text(p.get("period")),
        "total": _as_text(p.get("total")),
        "residue": _as_text(p.get("residue")),
        "shared pool": _as_text(p.get("shared_pool")),
        "direct": _as_text(p.get("direct")),
        "lines": _as_text(p.get("line_count")),
    } for p in facts.get("periods") or ()]
    refreshed = _as_text(facts.get("last_refreshed_at"))
    return {
        "schema": _SCHEMA, "container": "record_table",
        "title": "The operator ledger, by month",
        "columns": ["period", "total", "residue", "shared pool", "direct", "lines"],
        "rows": rows, "row_count": len(rows),
        "count_label": f"{len(rows)} month{'' if len(rows) == 1 else 's'}",
        "notice": (
            f"Last rebuilt {refreshed}." if refreshed else
            "This ledger has never been rebuilt."),
        "empty_text": (
            "The ledger holds no month yet. Recompute below builds one from Cost Explorer "
            "and the request logs."),
        "pick": _period_pick(facts, _as_text(facts.get("period"))),
    }


def _lines_pane(facts: dict[str, Any]) -> dict[str, Any]:
    """One month's AWS lines, residue first — the same order the Cost record uses.

    Ordering by amount alone buries the unattributable lines among the attributable ones,
    which is how a $0.032 invoice got written in the first place.
    """
    period = _as_text(facts.get("period"))
    order = {"residue": 0, "shared_pool": 1, "direct": 2, "unknown": 3}
    rows = []
    for line in facts.get("lines") or ():
        try:
            amount = float(line.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        rows.append({
            "attribution": ledger_attribution_of(line),
            "category": _as_text(line.get("category")) or "—",
            "service": _as_text(line.get("service")) or "—",
            "amount": f"{amount:.4f}",
            "_sort": amount,
            "quantity": (f"{_as_text(line.get('usage_quantity'))} "
                         f"{_as_text(line.get('usage_unit'))}").strip() or "—",
        })
    rows.sort(key=lambda r: (order.get(r["attribution"], 9), -r["_sort"]))
    for row in rows:
        del row["_sort"]
    return {
        "schema": _SCHEMA, "container": "record_table",
        "title": f"What {period} was billed for" if period else "What was billed for",
        "columns": ["attribution", "category", "service", "amount", "quantity"],
        "rows": rows, "row_count": len(rows),
        "count_label": f"{len(rows)} line{'' if len(rows) == 1 else 's'}",
        "empty_text": (
            f"No line has been computed for {period}. Recompute below asks AWS what that "
            "month cost." if period else "No month is selected."),
    }


def _recompute_pane(facts: dict[str, Any]) -> dict[str, Any]:
    """The recompute, stated before it can be run.

    NOT a bare button, which is what the legacy tab offered beside a month dropdown. This
    one costs money to press — a fan-out of Cost Explorer queries, billed per request — it
    can take a while, and it REPLACES the month's ledger row and every invoice derived from
    it. All three belong on screen before the click, not in a docstring.

    The typed month is the confirmation, and it confirms the thing that is actually easy to
    get wrong: WHICH month. It also fails closed on a pane left open across a month
    boundary, when the period the form is asking about is no longer the period the reader
    thinks they are looking at.
    """
    period = _as_text(facts.get("period"))
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Recompute {period}" if period else "Recompute",
        "fields": [],
        "submit_label": f"Recompute {period}",
        "submit_action": {
            "route": REFRESH_ROUTE, "danger": True,
            "success_label": "Recomputed",
            "fixed": {"period": period},
            "confirm": {
                "expect": period, "key": "confirm",
                "text": (
                    f"This asks AWS Cost Explorer what {period} cost — a fan-out of "
                    "queries, billed per request, that can take a while to answer. It then "
                    f"REPLACES {period}'s ledger row and re-derives every grantee's invoice "
                    "from it through the billing rules. Nothing else changes, and no figure "
                    "is entered by hand: what lands is what AWS reported. The nightly job "
                    "already does this for the open months, so run it here when you need an "
                    "answer sooner than tomorrow, or after changing a rule."
                ),
            },
        },
    }


def _ledger_pane(facts: dict[str, Any], why_not: str) -> dict[str, Any]:
    if not facts:
        return _notice("Ledger", why_not)
    error = _as_text(facts.get("ledger_error"))
    panes = [{"panel_payload": _periods_pane(facts)},
             {"panel_payload": _lines_pane(facts)},
             {"panel_payload": _recompute_pane(facts)}]
    if error:
        # An unreadable ledger file answers as an EMPTY one from `read_ledger`, which would
        # put "no cost has ever been recorded" on screen over a file that is merely corrupt.
        panes.insert(0, {"panel_payload": _notice(
            "The ledger file could not be read",
            f"`read_ledger` reported {error!r}, so the months below are what could be "
            "parsed and not necessarily all of them. A recompute rewrites the month it "
            "names; it does not repair the rest of the file.")})
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": panes}


def _current_rules_pane(facts: dict[str, Any]) -> dict[str, Any]:
    """What is in force RIGHT NOW, beside the form that proposes replacing it.

    Prefilled inputs alone do not show this: an input showing 25 is indistinguishable from
    an input someone has already typed 25 into, and the operator is about to confirm a
    change by typing the value being replaced. The column they are typing from has to be
    readable while the form is being filled in.
    """
    rules = facts.get("rules") or {}
    defaults = rules.get("defaults") or {}
    rows = [
        {"rule": "Margin %", "in force": _as_text(defaults.get("margin_pct"))},
        {"rule": "Minimum invoice",
         "in force": _as_text(defaults.get("minimum_invoice")) or "—"},
        {"rule": "Untagged residue",
         "in force": _as_text(defaults.get("residue_handling")) or "—"},
        {"rule": "…% distributed if so",
         "in force": _as_text(defaults.get("residue_distribution_pct"))},
    ]
    for pool, rule in sorted((defaults.get("shared_pool_split") or {}).items()):
        rows.append({"rule": f"Shared pool · {pool}",
                     "in force": _as_text((rule or {}).get("mode")) or "—"})
    overrides = rules.get("per_grantee") or {}
    return {
        "schema": _SCHEMA, "container": "record_table",
        "title": "The rules in force",
        "columns": ["rule", "in force"],
        "rows": rows, "row_count": len(rows),
        "count_label": f"{len(overrides)} per-grantee override"
                       f"{'' if len(overrides) == 1 else 's'}",
        # Named because the edit below cannot show them and MUST NOT drop them. The write
        # merges rather than replaces for exactly this reason.
        "notice": (
            "Per-grantee waivers and margin overrides are not edited here; a save from "
            "this tab merges into them and leaves them standing."
            if overrides else
            "No grantee has a waiver or a margin override."),
        "empty_text": "No rules are configured.",
    }


def _rules_form_pane(facts: dict[str, Any]) -> dict[str, Any]:
    """The proposed change, gated on typing the margin it is replacing.

    The typed value is not a formality: it is the number the operator is about to change,
    so typing it is the act of reading it. And because the route re-reads the rules before
    comparing, a form drawn before somebody else's save is refused rather than quietly
    reverting them.
    """
    rules = facts.get("rules") or {}
    defaults = rules.get("defaults") or {}
    vocabulary = facts.get("vocabulary") or {}
    fields: list[dict[str, Any]] = []
    for path, label, kind in _RULE_FIELDS:
        leaf = path.rsplit(".", 1)[-1]
        field: dict[str, Any] = {"key": path, "label": label,
                                 "value": _as_text(defaults.get(leaf))}
        options = vocabulary.get(kind) if kind else None
        if options:
            field["type"] = "select"
            field["options"] = [{"value": o, "label": o} for o in options]
        fields.append(field)
    for pool, rule in sorted((defaults.get("shared_pool_split") or {}).items()):
        fields.append({
            "key": f"defaults.shared_pool_split.{pool}.mode",
            "label": f"Shared pool “{pool}” — how its cost is spread",
            "type": "select",
            "value": _as_text((rule or {}).get("mode")),
            "options": [{"value": o, "label": o}
                        for o in vocabulary.get("shared_pool_mode") or ()],
        })
    margin = _as_text(defaults.get("margin_pct"))
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Change the rules",
        "fields": fields,
        "submit_label": "Save billing rules",
        "submit_action": {
            "route": BILLING_RULES_ROUTE, "danger": True,
            "success_label": "Saved",
            "confirm": {
                "expect": margin, "key": "confirm",
                "text": (
                    "These rules decide what every client is charged: the next recompute "
                    "multiplies the ledger by them and rewrites every invoice. The file is "
                    f"replaced in place, so there is no earlier version to go back to. Type "
                    f"the margin in force now ({margin}) to confirm you have read the value "
                    "you are replacing — if it has changed since this form was drawn, the "
                    "save is refused rather than overwriting whoever changed it."
                ),
            },
        },
    }


def _rules_pane(facts: dict[str, Any], why_not: str) -> dict[str, Any]:
    if not facts:
        return _notice("Billing rules", why_not)
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": _current_rules_pane(facts)},
                      {"panel_payload": _rules_form_pane(facts)}]}


def _inventory_pane(facts: dict[str, Any], why_not: str) -> dict[str, Any]:
    """What the account actually holds — the things the cost lines are counts OF.

    A cost line reading "AWSSecretsManager-Secrets" is a number until you know the account
    holds 41 secrets; then it is a number per secret, and the operator can act on it.
    """
    if not facts:
        return _notice("Inventory", why_not)
    inventory = facts.get("inventory")
    if not isinstance(inventory, dict):
        return _notice("Inventory", "The resource counts were not read for this render.")
    if not inventory.get("ok"):
        return _notice("Inventory", (
            "AWS did not answer the inventory request: "
            f"{_as_text(inventory.get('error')) or 'no reason given'}. That is not the "
            "same as an account holding nothing, so nothing is drawn as zero."))
    rows = []
    for key, value in sorted(inventory.items()):
        if key in ("ok", "cached"):
            continue
        # A count, a list, or a nested map — the peripheral answers differently per
        # service, so the SHAPE is reported rather than assumed into an integer.
        if isinstance(value, (list, tuple)):
            shown = str(len(value))
        elif isinstance(value, dict):
            shown = str(len(value))
        else:
            shown = _as_text(value)
        rows.append({"resource": key.replace("_", " "), "count": shown})
    return {
        "schema": _SCHEMA, "container": "record_table",
        "title": "What the account holds",
        "columns": ["resource", "count"],
        "rows": rows, "row_count": len(rows),
        "count_label": ("from cache, up to 15 minutes old"
                        if inventory.get("cached") else "read live just now"),
        "empty_text": "AWS answered, and reported no resources of any counted kind.",
    }


class GrantorTolling:
    """What the network costs to run, and how little of it any client can be billed."""

    tool_id = "grantor_tolling"
    label = "Tolling"
    summary = (
        "The AWS cost record: every line, what it was for, and whether it attributes to a "
        "client at all. Projected from the operator tolling ledger — no cost is entered by "
        "hand, because a typed one disagrees with the bill. The ledger it is projected "
        "from, the billing rules it is multiplied by, and the account inventory it counts "
        "are the operator's own tabs beside it."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: A hub tab launched by ADDRESS, like the overview it sits beside.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    #: Which tab, and which month. See TAB_QUERY / PERIOD_QUERY.
    wants_surface_query = True
    #: The ledger, the rules and the inventory are the HOST's — `micyte` may not name the
    #: FND application, and the operator gate is a question about the live request.
    wants_host_context = True
    # No `writes`: nothing here writes a datum row. The two actions post to the operator's
    # own `/__fnd/tolling/*` routes, which are governed by the operator gate and a typed
    # confirmation rather than by `datum_write_policy`.

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del document_id, datum_address
        query = dict(extra_query or {})
        active = _as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in TABS:
            active = DEFAULT_TAB

        # The inventory half is asked for ONLY by the tab that draws it. It fans out one
        # list call per AWS service, and a payload built eagerly would have charged every
        # render of this tool for a panel nobody opened.
        facts, why_not = tolling_facts(
            host_context,
            period=_as_text(query.get(PERIOD_QUERY)),
            inventory=(active == "inventory"),
        )

        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": self.label,
            "sandbox_id": _as_text(sandbox_id),
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": [
                # The PROJECTION first, and it is the default: the grantor paradigm bills
                # against this book, and it is the answer to "what does the network cost"
                # without needing a month chosen first.
                {"id": "cost", "label": "Cost record",
                 "tool_id": "grantor_tolling_cost",
                 "panel_payload": self.cost_pane(
                     authority_db_file=authority_db_file, sandbox_id=sandbox_id)},
                # And the ledger it is projected FROM, which is where a disagreement
                # between the two would show.
                {"id": "ledger", "label": "Ledger",
                 "tool_id": "grantor_tolling_ledger",
                 "panel_payload": _ledger_pane(facts, why_not)},
                {"id": "rules", "label": "Billing rules",
                 "tool_id": "grantor_tolling_rules",
                 "panel_payload": _rules_pane(facts, why_not)},
                {"id": "inventory", "label": "Inventory",
                 "tool_id": "grantor_tolling_inventory",
                 "panel_payload": _inventory_pane(facts, why_not)},
            ],
        }

    def cost_pane(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
    ) -> dict[str, Any]:
        """The projected `grantor/invoices` book — the tab as it stood before the
        operator's cost admin joined it, unchanged."""
        empty = {
            "schema": _SCHEMA, "container": "record_table", "title": self.label,
            "columns": ["attribution", "category", "amount", "quantity", "bearer"],
            "rows": [], "row_count": 0,
        }
        if authority_db_file is None:
            return {**empty, "empty_text": "The authority database is not configured.",
                    "notice": "No store to read the cost record from."}

        sandbox = str(sandbox_id or "").strip() or GRANTOR_SANDBOX
        summary = cost_summary(Path(authority_db_file), sandbox=sandbox)
        if not summary.get("projected"):
            return {
                **empty,
                "empty_text": (
                    "No cost has been projected yet. The tolling tab reads "
                    "`grantor/invoices`, which `project_tolling_to_datum` writes from the "
                    "operator tolling ledger — it is not typed here."
                ),
                "notice": summary.get("note") or "The cost book is empty.",
            }

        rows = self._lines(Path(authority_db_file), sandbox)
        # Residue first, because it is the finding. Sorting by amount alone would bury the
        # unattributable lines among the attributable ones, which is how a $0.032 invoice
        # got written in the first place.
        order = {"residue": 0, "shared_pool": 1, "direct": 2, "unknown": 3}
        rows.sort(key=lambda r: (order.get(r["attribution"], 9), -r["amount_cents"]))

        return {
            **empty,
            "rows": rows,
            "row_count": len(rows),
            "count_label": f"{summary['entries']} cost line{'' if summary['entries'] == 1 else 's'}",
            "notice": (
                f"{summary['total']} total — {summary['borne_by_fnd']} "
                f"({summary['borne_by_fnd_pct']}%) borne by FND, "
                f"{summary['billable']} attributable to a client."
            ),
            "tolling": {
                "total_cents": summary["total_cents"],
                "borne_by_fnd_cents": summary["borne_by_fnd_cents"],
                "billable_cents": summary["billable_cents"],
                "borne_by_fnd_pct": summary["borne_by_fnd_pct"],
                "entries": summary["entries"],
            },
            "empty_text": "The cost book holds no lines.",
        }

    def _lines(self, db: Path, sandbox: str) -> list[dict[str, Any]]:
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from .grantor_books import _context, _read, _rows
        from .ledger_books import SUPPLY_DOC

        store = SqliteSystemDatumStoreAdapter(db)
        registry, names = _context(store, tenant_id="fnd", sandbox=sandbox)
        book = _read(store, tenant_id="fnd", sandbox=sandbox, name=SUPPLY_DOC)
        out = []
        for row in _rows(book, sandbox=sandbox, registry=registry, names=names):
            note = str(row.get("note") or "")
            attribution = attribution_of(note)
            out.append({
                "attribution": attribution,
                "category": row.get("product") or "—",
                "amount": row.get("amount") or "",
                "amount_cents": int(row.get("amount_cents") or 0),
                "quantity": row.get("quantity") or "—",
                # WHO BEARS it, which for residue and shared_pool is FND itself. Shown
                # rather than implied, because "FND" appearing on 47 of 50 lines is the
                # point of the tab.
                "bearer": row.get("party_label") or row.get("party") or "—",
            })
        return out


register(GrantorTolling())

__all__ = [
    "BILLING_RULES_ROUTE", "DEFAULT_TAB", "PERIOD_QUERY", "REFRESH_ROUTE", "TABS",
    "TAB_QUERY", "GrantorTolling", "attribution_of", "ledger_attribution_of",
    "tolling_facts",
]
