"""PIM's home — what this instance's PIM sandbox holds, and whether its seam is connected.

PIM is the CLIENT's application, on the client's own instance: the channel is where an
alias manages the services they pay for and collects API keys, the Use button binds a key
to one of their ports, and thereafter the relationship with those provider services is
facilitated here. The sandbox keeps datum record documents — analytics, contacts signed up
from the website, newsletter drafts — fed through the ports the client's own key permits.

## Why the home tab is the FIRST tool and not a placeholder

An app's hub must be one of its own tools; the contract refuses a hub that points at
somebody else's. PIM's first draft borrowed `contacts_manager` from quiar, which is wrong
twice: a tool belongs to exactly ONE lineage (`packages_by_tool` raises on a shared
claim), and quiar's contacts are a CRM's, while PIM's are *people who signed up on a
website*. Same word, different record.

So this is what PIM can honestly serve on day one, and it answers the question a client
actually has first: **is anything connected yet?** A tab showing an empty analytics table
cannot distinguish "no visitors" from "no key bound", and those want opposite actions.

## It reads, and does not reach

No network call and no port invocation. The seam's STATE is read from this instance's own
configuration — is a binding present, is a grant written — never by trying the seam and
seeing what happens. Probing to render a page would make a status row depend on somebody
else's uptime, and the answer "unavailable" would be indistinguishable from "not
configured", which is the distinction this whole panel exists to draw.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .pim_design import PimDesign, build_site_payload

_SCHEMA = "mycite.v2.portal.workbench.tool.pim_overview.v1"

#: The hub's own query parameter. Every nesting level owns one, so selecting a Design
#: sub-tab cannot move the tab the hub is on.
TAB_QUERY = "pim_tab"

#: The Analytics tab's OWN sub-tab parameter. Every nested hub in this
#: codebase gets one; sharing the parent's moves the parent when a sub-tab
#: is picked.
ANALYTICS_QUERY = "analytics_section"
DEFAULT_TAB = "home"

#: Where the Resources tab's arrangement forms post — the door as it is registered, and the
#: same address `_payment_pane`'s form already uses. The `/pim/` segment says which of the
#: two doors it is: this one resolves the instance from the sign-in header, while the
#: operator's `/portal/api/v2/<thing>` reads it from the body. The action is appended by the
#: form that uses it, under the OPERATION's own name, because the write gate judges a
#: request by that word and an undeclared one has no document kind to be measured against.
#:
#: NOT YET REACHABLE FROM A CLIENT'S OWN DOMAIN, and that is a fact about the HOST rather
#: than about this line. Read from `fnd_app/deploy/nginx-*.conf` on 2026-09-01: a client
#: vhost proxies `/dashboard/api/` to `/__fnd/` and, under `/portal/`, only
#: `/portal/static/` — so this address answers through the operator's compendium and
#: reaches the static site on `brockspressurewashing.com`. Closing that is the door's own
#: half of the work: an `/__fnd/pim/resources/<action>` registration beside
#: `/__fnd/pim/site/<action>`, or a `_repoint_client_forms` rule, either of which moves
#: with this constant rather than against it.
# `/__fnd/pim/...`, not `/portal/api/...`. A client vhost proxies `/dashboard/api/`
# to `/__fnd/` and proxies `/portal/api/` nowhere — verified 2026-09-03, a POST to
# /portal/api/v2/pim/resources/define_type on brockspressurewashing.com answers 404.
# The operator spelling still answers; the handler carries both routes.
_RESOURCES_ROUTE = "/__fnd/pim/resources"

# THE READINESS TABLE IS RETIRED (2026-08-28).
#
# `RECORD_KINDS` listed PIM's four record kinds against their archetype and the tool that
# opens each, and the home tab drew it. It answered a real question — "is anything
# connected yet?" — and it answered it in three ways, not one: a kind with no archetype
# has no surface however the seam is configured, which is a different fact from a seam
# nobody has bound, and they want opposite actions from opposite people.
#
# It was the wrong page for it. Operator, 2026-08-28: the home tab "should be a general
# page about services provided and storage used, perhaps also a small analytics overview
# on a single dashboard surface" — and what stood there was a developer's view of the
# app's own readiness, on the first screen a client sees.
#
# The distinction is NOT lost with it. It moved to where a client can act on it: each
# seam-fed tab says, in its own empty state, whether it holds nothing because nothing has
# arrived or because the port is not connected — and names the next step when it is the
# second. `_seam_pane` is the one builder for that, so Analytics and Email cannot come to
# describe an unconnected seam two different ways.


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _config(private_dir: Any) -> dict[str, Any]:
    if not private_dir:
        return {}
    path = Path(private_dir) / "config.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def seam_state(
    config: dict[str, Any], *, port_id: str = "email_provider", sandbox: str = "",
    bindings: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Declared / bound / permitted, as three separate answers, FOR THIS SANDBOX.

    They are three because they fail differently and are fixed by different people. A
    single "connected" would collapse "nobody has chosen an extension" into "nobody has
    written the grant", and an operator would go looking in the wrong file.

    ``sandbox`` is not optional in spirit, and leaving it out is how this reported
    another client's binding. `port_bindings` is PORTAL-WIDE — one list in one
    `config.json` for every instance the portal serves — so "the first binding for
    `email_provider`" is the first one anybody has, not this instance's. Rendered live
    on 2026-08-26, a freshly installed app sandbox's home tab named ANOTHER TENANT'S
    binding id as its own: not a crash and not an empty state, but a confident wrong
    answer that puts one client's configuration on another client's surface.

    A binding names the sandboxes it acts for. One that does not name yours is not
    yours, and that is the question asked here.

    What this still cannot fix, because the data cannot answer it: `sandbox_ids` holds
    NAMES, and a name is not an address — `oveure` is a sandbox two instances hold. So a
    binding for one instance's `oveure` would still match the other's. The pair
    `(msn, sandbox)` is the address everywhere else in this stack and `port_bindings`
    was never migrated to it. Recorded rather than papered over: narrowing by name is
    strictly better than not narrowing, and it is not the whole fence.

    ``next_step`` IS THE CLIENT'S SENTENCE, and only the client's. PIM has exactly one
    reader for this dict: `_seam_pane`, which feeds the Analytics and Email tabs a CLIENT
    opens. Until 2026-08-29 this field read "select an extension for this port on
    Ports" — which sounded like an operator's field because the file was first written
    for an imagined operator surface that reads `seam_state` — but a grep of every
    production caller found none: `utilities_surfaces.py`, the actual Ports tab, builds
    its own table from bindings and grants directly and never calls this function, and
    neither does anything else. An "operator wording" field with no operator reader is
    exactly the reader-with-no-writer this whole task exists to remove, so there is no
    second field here — ONE fact, ONE reader, ONE sentence, in the terms the reader who
    actually opens this tab can act on. (`masonlenehan.com` has zero nginx locations for
    `/portal/utilities`, confirming that reader is not the operator's Ports page.)
    """
    # The HOST's answer when it gave one. `port_bindings` is portal-wide and
    # `sandbox_ids` holds NAMES — every client's PIM sandbox is called `pim`, so a name
    # match is every instance at once. Only the host can narrow to the PAIR, because the
    # fence is the credential's `instance_msn_id`, and reading a credential is its job.
    # The config fallback is for a caller with no host context (a test, a script); it
    # narrows by name, which is better than not narrowing and is still not the address.
    prenarrowed = bindings is not None
    if prenarrowed:
        bindings = [b for b in bindings if isinstance(b, dict)]
    else:
        bindings = config.get("port_bindings")
        bindings = bindings if isinstance(bindings, list) else []
    wanted = _as_text(sandbox)

    def _acts_for(binding: dict[str, Any]) -> bool:
        if prenarrowed:
            # The host already narrowed to the PAIR, and its rows carry no `sandbox_ids`
            # to re-filter on. Asked as a flag rather than sniffed for the missing key:
            # a config binding that names NO sandboxes is NOBODY'S, and a key-sniff read
            # those two states as the same one.
            return True
        if not wanted:
            return True
        ids = binding.get("sandbox_ids")
        return wanted in {_as_text(x) for x in (ids if isinstance(ids, list) else [])}

    bound = next(
        (b for b in bindings
         if isinstance(b, dict) and _as_text(b.get("port_id")) == port_id
         and _acts_for(b)), None)
    binding_id = _as_text(bound.get("binding_id")) if bound else ""

    # `external_call_grants` is a LIST of grant objects in every config that has ever
    # shipped — `{actor_id, binding_ids, operations, services}`. Reading it as a dict
    # keyed `port:<binding_id>` returned {} every time, so `permitted` answered "no" for
    # every port on every instance, including bindings that were granted and working.
    # The mapping form is still accepted because a test fixture writes one.
    grants = config.get("external_call_grants")
    if isinstance(grants, dict):
        permitted = bool(binding_id) and bool(grants.get(f"port:{binding_id}"))
    else:
        permitted = bool(binding_id) and any(
            binding_id in (g.get("binding_ids") or [])
            for g in (grants if isinstance(grants, list) else [])
            if isinstance(g, dict)
        )

    return {
        "port": port_id,
        "declared": "yes",
        "bound": binding_id or "no",
        "permitted": "yes" if permitted else "no",
        "next_step": (
            "not connected yet — your operator hasn't turned this on" if not binding_id
            else "not connected yet — your operator is finishing the setup"
            if not permitted
            else "connected"
        ),
    }


# --- The client's own account -----------------------------------------------------
#
# WHAT THIS FILE MUST NOT DO. These panes need three facts PIM cannot reach for itself:
# which grantee address this instance's client authenticates as, what that account holds
# in the operator's books, and what the instance's records occupy. The first draft read
# them here — importing `fnd_app.instances...port_bindings` and naming the operator's msn
# as a constant — and broke two boundaries at once:
#
#   * `micyte/` is the package the repo split PUBLISHES. It must not import the FND
#     application (`test_micyte_fnd_boundary`), and it must not carry a live msn
#     (`test_public_package_has_no_live_instances`) — a customer address in a clone that
#     can never be recalled.
#   * and it is the same shape the `port` resolver already solved: a fact only the host
#     holds arrives through `host_context`, declared by `wants_host_context`.
#
# So the host computes them and hands them over. PIM renders what it is given and says
# what it was not.

#: PIM'S FEATURES — one entry per tab that can be turned off per instance.
#:
#: ONE SOURCE, MANY INSTANCES. Every instance renders PIM from this file; there is no
#: per-instance copy to drift. What differs between clients is CONFIGURATION, and this is
#: where the vocabulary of that configuration lives: which tabs an instance is entitled
#: to, and what each needs in order to work.
#:
#: `requires` names the port a tab reads through. UNTIL 2026-09-10 a tab whose port was
#: unbound or unpermitted still appeared when switched on and said which factor was
#: lacking ("a tab that vanishes teaches nothing"). The operator then asked for the
#: opposite — "Omit tabs that are not configured; e.g. authoring, payment, and/or
#: newsletter" — so a pane that reports `configured: False` is NOT drawn, and what the old
#: rule protected is kept in one place: Home carries a "Not shown" note naming each
#: omitted tab and the seam's next step, so the work order is still stated on the one
#: tab every instance has. The PANE still decides (one vocabulary): a seam pane is
#: configured when its port answered, Payment when PayPal is connected, Newsletter when
#: the instance has one, Authoring and Design when the site seam answers.
#:
#: `default_on` is what an install gets when nobody has configured it. Every tab defaults
#: on: an instance that holds a service and is shown nothing has been silently downgraded.
#:
#: `held` names the services in the grantor's books that UNLOCK the tab; `()` means the
#: tab is PIM's own and stands for every client. The two are different sentences about
#: absence and both are honest: "you do not pay for this" (held, and the tab never
#: appears) and "you pay for this and it is not connected yet" (requires, and the pane
#: says so). A tab is drawn only when it is switched on AND, if it names services, the
#: account holds one of them.
#:
#: ## WHY THE FOUR SERVICE TABS ARE IN THIS TABLE (2026-08-29)
#:
#: `domain`, `newsletter`, `storage` and `payment` used to live in a second map,
#: `SERVICE_TABS`, appended by a second loop AFTER this table had been filtered by the
#: instance's toggles. That second loop consulted the account and never the toggles, and
#: it cost two things:
#:
#:   1. A BUG. A feature skipped here for being OFF was not recorded as placed, so the
#:      service loop re-added it. `email` was in both tables, so `features={"email":
#:      False}` on an account holding `user_email` still rendered an Email tab —
#:      "OFF IS ABSENT" was false for the one id that appeared twice. The reason review
#:      missed it: the only toggle test used `design`, whose service (`site_hosting`) is
#:      deliberately not a service tab, so the one combination that could break was the
#:      one combination never exercised.
#:   2. A SECOND, QUIETER GAP in the same promise. The four service tabs could not be
#:      switched off at all — "features are configuration" held for six tabs and not for
#:      the other four, with nothing in the code saying which kind a tab was.
#:
#: So there is ONE table and one loop. Every tab PIM can draw is configurable, defaults
#: on, and a service-derived tab still appears only when the service is held — the toggle
#: narrows what a client is shown, it never grants them a surface they do not pay for.
#:
#: `base_service` and `site_hosting` name no tab, and that is deliberate rather than
#: missing: `base_service` IS the account, whose surface is Home, and `site_hosting`
#: already has THREE surfaces — Analytics, Authoring, and the Site tab that took Pages and
#: Images on 2026-08-29 — so a fourth door saying "your site" would just be a fourth door
#: to the same three.
#:
#: `email` names no service either, though `user_email` and `operational_email` are sold.
#: It is a port-backed tab like Analytics: PIM declares `email_provider`, and the pane
#: states the seam. Giving it a `held` set would ALSO have fixed the resurrection bug, by
#: hiding the tab from every client who buys no mailbox — which is a change to what eight
#: live instances show, not a bug fix, so it is left as a question for the operator rather
#: than smuggled in with one.
FEATURES: tuple[dict[str, Any], ...] = (
    # ORDER (2026-09-16): what a client DOES, then what they CHECK, then what they
    # MANAGE. Analytics sat second because it was built second — a developer's
    # order, not a client's. A client opens PIM to write or change their site, then
    # to see how it went, then to manage the connections behind it. The ids are
    # PERSISTED and untouched; only the strip's order moves.
{"id": "home", "label": "Home", "requires": "", "held": (), "default_on": True,
     "why": "what this account holds and what its records occupy"},
{"id": "design", "label": "Authoring", "requires": "site_hosting", "held": (),
     "default_on": True, "why": "the writing this client publishes to their site"},
    # LABELLED "Design", ID STAYS `site`. The operator, 2026-09-07: *"The site tab
    # existing instead of the 'design' tab."* They are right about the word — every
    # instruction they have written for this surface calls it the design tab, including
    # TASK-2026-09-01-010, which was written on 2026-09-01, AFTER `design` was relabelled
    # "Authoring" (9b2b83ea) and this tab split off Pages/Images (d6d59d12). The rename
    # happened to the vocabulary and never to the operator.
    #
    # The ID CANNOT FOLLOW THE LABEL, for two reasons and both are load-bearing:
    #   1. `design` is already taken, by the Authoring tab, whose id is likewise the name
    #      it used to wear.
    #   2. Ids are PERSISTED, not presentational: `features_for_instance` reads
    #      `installed_packages.pim.installs[*].features` out of each instance's own
    #      config.json, keyed by these ids. Renaming one silently un-configures every
    #      instance that had switched it off — the switch reads as "absent", and absent
    #      means default_on. A relabel is free; a re-key is a migration.
    # So id and label deliberately disagree here, and this comment is the reason they do.
{"id": "site", "label": "Design", "requires": "site_hosting", "held": (),
     "default_on": True,
     "why": "the pages this site serves and the images it draws from"},
{"id": "resources", "label": "Resources", "requires": "", "held": (),
     "default_on": True,
     "why": "the images, documents and profiles kept alongside the site"},
{"id": "analytics", "label": "Analytics", "requires": "site_hosting", "held": (),
     "default_on": True, "why": "visits to this instance's own site"},
{"id": "email", "label": "Email", "requires": "email_provider", "held": (),
     "default_on": True,
     "why": "this instance's own addresses and where each forwards"},
{"id": "domain", "label": "Domain", "requires": "", "held": ("domain_kept",),
     "default_on": True,
     "why": "the domain this instance keeps and what is standing at it"},
    # NEWSLETTER AND STORAGE ARE INCLUDED, so neither is gated on a subscription any more
    # (2026-09-01 repricing). Both were `held`-gated, and `storage_gb` had ZERO
    # subscriptions across all seven clients — so the Storage tab has never rendered for
    # anybody. A tab gated on a line nobody buys is a tab that does not exist; now that
    # storage is part of the plan rather than an add-on, what it shows is usage against
    # the included amount, which every account has.
    # `newsletter` RETIRED as a PIM tab on 2026-09-14. Its two jobs — "what has gone out"
    # and "send one" — are now the Authoring tab's Newsletter view, where they sit beside
    # the writing they are about and against a list of what has already been sent. Two
    # surfaces for one act is how the two drift, and this one could only ever list.
    #
    # The ID IS NOT REUSED. `features_for_instance` keys a client's switches by these ids,
    # so handing `newsletter` to a different tab would silently turn the new one off for
    # anybody who had turned the old one off. An unknown id is ignored, which is exactly
    # the right behaviour for a retired one.
    # `contacts` RETIRED as a PIM tab on 2026-09-15, one day after it arrived here. The
    # operator: *"Contacts should be an added sub tab on the authoring tab of the PIM
    # application."* Its job — who filled in the form, who left — belongs beside the
    # writing that is addressed to those people, so it is now the Authoring tab's fourth
    # view (`pim_design.TABS`). The subscriber count on the send form and the table that
    # count comes from are on one screen instead of two tabs apart.
    #
    # THE ID IS NOT REUSED, the same rule that retired `newsletter`. `features_for_instance`
    # keys a client's switches by these ids, so handing `contacts` to a different tab would
    # silently turn the new one off for anybody who had turned the old one off. An unknown
    # id is ignored, which is exactly the right behaviour for a retired one.
{"id": "storage", "label": "Storage", "requires": "", "held": (),
     "default_on": True, "why": "what this instance uses, against what the plan includes"},
    # `held` was `("payment_processing",)` until 2026-09-02, and that became a
    # chicken-and-egg the day this tab stopped being a pointer at the Grantor card and
    # became the place a client CONNECTS their PayPal: the tab appeared only for clients
    # already holding the paid service, and holding it starts with connecting an account
    # on the tab they could not see. Measured on BPW — eight tabs rendered, `payment` not
    # among them. Off is still expressible per instance, through `features`, which is
    # where a decision about one client belongs; a service they have not bought yet is
    # not that decision.
{"id": "payment", "label": "Payment", "requires": "", "held": (),
     "default_on": True, "why": "what this site has taken, and the PayPal it takes it with"},
)

#: The features an instance may switch off. Derived, so adding a tab above adds it here —
#: and `set_pim_features.py` refuses any id that is not in it, so the writer cannot drift
#: from the table it writes for.
FEATURE_IDS: frozenset[str] = frozenset(f["id"] for f in FEATURES)


def features_for_instance(private_dir: Any, msn_id: str) -> dict[str, bool]:
    """``feature id -> on``, for one instance. Absent configuration means every tab.

    Read from this app's OWN install record for this instance
    (`installed_packages.pim.installs[*].features`), which is the grain the setting
    belongs at: a feature is on for a client, not for a build.

    Every unknown id is ignored and every unlisted feature keeps its default, so a
    configuration written against an older build cannot turn off a tab that did not exist
    then, nor silently hide one added since.
    """
    defaults = {f["id"]: bool(f["default_on"]) for f in FEATURES}
    if private_dir is None or not _as_text(msn_id):
        return defaults
    try:
        import json as _json
        from pathlib import Path as _Path

        raw = _json.loads((_Path(private_dir) / "config.json").read_text(encoding="utf-8"))
        installs = ((raw.get("installed_packages") or {}).get("pim") or {}).get("installs")
        for entry in installs or []:
            if not isinstance(entry, dict):
                continue
            if _as_text(entry.get("msn_id")) != _as_text(msn_id):
                continue
            configured = entry.get("features")
            if isinstance(configured, dict):
                for key, value in configured.items():
                    if key in defaults:
                        defaults[key] = bool(value)
            break
    except (OSError, ValueError, TypeError):
        # An unreadable config must not silently strip a client's tabs. Defaults stand.
        return {f["id"]: bool(f["default_on"]) for f in FEATURES}
    return defaults


def plan_of(context: dict[str, Any]) -> dict[str, Any]:
    """``{plan, balance, trial, instrument}`` from the host's ``account`` fact.

    The four things a client asks about their own account after "what do I hold":
    which plan, what do I owe, when does the trial end, what card is on file. All four
    ride on the one fact the host already hands over, so Home cannot say something
    about a client that the Grantor card says differently.
    """
    account = context.get("account")
    if not isinstance(account, dict):
        return {"plan": {}, "balance": "", "trial": {}, "instrument": {}}
    return {
        "plan": account.get("plan") if isinstance(account.get("plan"), dict) else {},
        "balance": _as_text(account.get("balance")),
        "trial": account.get("trial") if isinstance(account.get("trial"), dict) else {},
        "instrument": (account.get("instrument")
                       if isinstance(account.get("instrument"), dict) else {}),
    }


def account_of(context: dict[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    """``(services, monthly total, why not)`` from the host's ``account`` fact.

    The refusal is CARRIED. "You hold no services" and "this instance is not paired to a
    grantee account" are opposite situations, and an empty table states the first.
    """
    account = context.get("account")
    if not isinstance(account, dict):
        return [], "", "this portal did not tell this render what the account holds"
    lines = [line for line in (account.get("services") or []) if isinstance(line, dict)]
    return lines, _as_text(account.get("total")), _as_text(account.get("why_not"))


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _month_label(period: object, *, long: bool = False) -> str:
    """`2026-07` as a person says it. A chart axis reading "7/26" makes the reader do
    arithmetic to find last month."""
    token = _as_text(period)
    if len(token) < 7 or "-" not in token:
        return token
    year, _, month = token.partition("-")
    try:
        name = _MONTHS[int(month) - 1]
    except (ValueError, IndexError):
        return token
    return f"{name} {year}" if long else name


def _seconds(ms: object) -> str:
    """Milliseconds as a person reads a duration. `5775` is not a length of time."""
    n = _int(ms)
    if not n:
        return "—"
    secs = round(n / 1000)
    return f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60}s"


def _int(value: object) -> int:
    """A figure from a payload, as a number. Charts need arithmetic, tables needed text."""
    try:
        return int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0


def _pretty(value: object) -> str:
    """A machine key as a person would say it: `human_vs_bot` keys, origin names."""
    token = _as_text(value).replace("_", " ").strip()
    return {"human": "People", "bot": "Machines",
            "direct": "Typed or bookmarked", "search": "Search",
            "social": "Social", "referral": "Another site",
            "internal": "Your own pages"}.get(_as_text(value), token.capitalize() or "—")


class PimOverview:
    """PIM's home: what the sandbox holds, and whether the seam that fills it is live."""

    tool_id = "pim_overview"
    label = "PIM"
    summary = (
        "This instance's own record of its provider-service relationship: what the PIM "
        "sandbox keeps, and whether the FND seam that feeds it is bound and permitted."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Launched by ADDRESS as a hub, not offered for a document in focus.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    container = "tabbed"
    wants_surface_query = True
    #: `private_dir` and the port the Design tab is a view of — see build_panel_payload.
    wants_host_context = True

    # ---- the panes -------------------------------------------------------------
    #
    # Every pane answers ONE question and says why when it cannot. The pattern the
    # whole app follows: a table that renders empty cannot be told from a seam that is
    # not connected, and those want opposite actions from opposite people.

    def _plan_pane(self, context: dict[str, Any]) -> dict[str, Any]:
        """Your plan: what you are on, when the trial ends, the card on file, the balance.

        THE PANE A BASE ACCOUNT NEVER HAD. Measured 2026-09-16: a client holding only
        `base_service` — no site, no mailbox, the exact account self-serve onboarding
        produces — was shown Home, Resources, Storage and Payment, and the Payment tab is
        about THEIR merchant account. Nowhere on their own app could they see what they
        pay FND, whether their trial was running, or which card would be charged.

        Four rows, each one an answer. The card row carries the recogniser and the
        state's sentence, never anything a charge could be made with — the vault
        reference is not in this store and does not reach this render.
        """
        _lines, total, why_not = account_of(context)
        facts = plan_of(context)
        plan, balance, trial, instrument = (
            facts["plan"], facts["balance"], facts["trial"], facts["instrument"])
        rows: list[dict[str, str]] = []
        if plan:
            rows.append({"item": "plan",
                         "detail": f"Base account, {_as_text(plan.get('monthly'))} a month"
                         if _as_text(plan.get("monthly")) else "Base account"})
        elif not why_not:
            rows.append({"item": "plan", "detail": "No plan is recorded against this account yet."})
        if trial:
            ends = _as_text(trial.get("ends"))
            left = trial.get("days_left")
            if trial.get("active"):
                noun = "day" if left == 1 else "days"
                rows.append({"item": "trial", "detail": f"Free until {ends} — {left} {noun} left"})
            else:
                rows.append({"item": "trial", "detail": f"Ended {ends}"})
        if instrument:
            sentence = _as_text(instrument.get("sentence"))
            recogniser = _as_text(instrument.get("recogniser"))
            rows.append({"item": "card on file",
                         "detail": f"{recogniser} — {sentence}" if recogniser else sentence})
        if balance:
            rows.append({"item": "balance", "detail": balance})
        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Your plan",
            # The same rule as the tile: a total over nothing is not a figure.
            "count_label": (f"{total}/month" if total and _lines else ""),
            "columns": ["item", "detail"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": why_not or "Nothing is recorded against this account yet.",
            "notice": ("Nothing is charged while a trial is running. After it ends, each "
                       "month is charged to the card on file."
                       if trial and trial.get("active") else ""),
        }

    def _services_pane(self, context: dict[str, Any]) -> dict[str, Any]:
        lines, total, why_not = account_of(context)
        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Services",
            "count_label": (f"{len(lines)} service(s) · {total}/month" if lines else ""),
            "columns": ["service", "quantity", "monthly"],
            "rows": lines,
            "row_count": len(lines),
            "empty_text": why_not or "No services are recorded against this account.",
        }

    def _storage_pane(self, context: dict[str, Any]) -> dict[str, Any]:
        used = context.get("storage")
        used = used if isinstance(used, dict) else {}
        g = lambda k: _as_text(used.get(k)) or "—"  # noqa: E731
        # WHAT IS USED, BESIDE WHAT IS INCLUDED. A figure with no ceiling next to it asks
        # the reader to already know their plan; the two together are the whole answer to
        # "am I near a limit", which is the only question this pane is opened with.
        rows = [
            {"measure": "website files", "value": g("site_used"),
             "included": g("site_included"), "used": g("site_pct")},
            {"measure": "records (documents & analytics)", "value": g("datum_used"),
             "included": g("datum_included"), "used": g("datum_pct")},
            {"measure": "documents", "value": g("documents"), "included": "—", "used": "—"},
            {"measure": "sandboxes", "value": g("sandboxes"), "included": "—", "used": "—"},
        ]
        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Storage",
            # BOTH READINGS. Usage leads, because "am I near a limit" is the question the
            # pane is opened with — but the document count stays, because the Home
            # dashboard embeds this pane and that count is what it summarised before.
            # Dropping it there would have been a silent regression in a second surface.
            "count_label": (f"{g('site_used')} of site, {g('datum_used')} of records "
                            f"· {g('documents')} document(s)"),
            "columns": ["measure", "value", "included", "used"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": "This instance keeps no documents yet.",
            "notice": (
                "Website files and records are both included in your plan at the amounts "
                "shown. Nothing is charged for storage below those, and we would talk to "
                "you long before you reached them."
            ),
        }

    def _seam_pane(self, title: str, state: dict[str, str], *,
                   what: str, rows: list[dict[str, str]] | None = None,
                   columns: list[str] | None = None) -> dict[str, Any]:
        """A record table fed through a PORT, or the reason it holds nothing.

        One builder for every seam-fed tab, so Analytics and Email cannot come to
        describe an unconnected seam two different ways.

        The empty text reads ``state['next_step']`` — `seam_state`'s only field for this
        fact, worded for the one reader who opens this pane: the client. See
        `seam_state`'s docstring for why there is no separate operator wording to choose
        between here.
        """
        connected = state.get("permitted") == "yes"
        rows = rows or []
        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": title,
            "count_label": f"{len(rows)} row(s)" if connected else "not connected",
            "columns": columns or ["record"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": (
                f"Nothing yet — {what}." if connected
                else f"{what.capitalize()}. This is {state['next_step']}."
            ),
            "seam": state,
            # WHETHER THE TAB IS DRAWN AT ALL (2026-09-10): the hub omits a pane that
            # says it is not configured, and Home names it. The pane still decides —
            # one vocabulary — so a caller that reached the adapter overrides this.
            "configured": connected,
            "why_not": "" if connected else _as_text(state.get("next_step")),
        }

    def _analytics_pane(self, state: dict[str, str],
                        context: dict[str, Any] | None = None,
                        *, query: dict[str, Any] | None = None) -> dict[str, Any]:
        """A month of a small site's life, drawn.

        REBUILT 2026-08-29. This was three tables of figures — the tab answered "what were
        August's numbers" and nothing else, while the legacy dashboard it replaces drew
        five charts, top pages, top referrers and a per-visitor log. A client comparing the
        two saw the old one as the real dashboard and this as a stub, and they were right.

        THE MONTH STRIP LEADS, and that is the argument of this tab. A single 72 set large
        is the template answer and says nothing; 72 drawn beside July's 56 says the only
        thing a proprietor actually wants to know. It is also the period control, so the
        chart and the navigator are one object rather than a chart plus a dropdown.

        Then, in order of how often the question is asked: where they came from, what they
        read, and who they were. The donuts the operator asked for are kept and DEMOTED to
        the last row — a part-to-whole with three slices reads fine as a ring, and five
        rings for ninety-five sessions is decoration.

        Everything below comes from `analytics_summary`, which is the same builder the
        legacy dashboard's own route calls, so the two cannot disagree about a month.
        """
        facts = (context or {}).get("analytics")
        facts = facts if isinstance(facts, dict) else {}
        months = [m for m in (facts.get("months") or []) if isinstance(m, dict)]
        why_not = _as_text(facts.get("why_not"))

        reader = (context or {}).get("analytics_summary")
        live: dict[str, Any] = {}
        if callable(reader):
            try:
                got = reader(90)
                live = got if isinstance(got, dict) else {}
            except Exception:
                live = {}

        if not months and not live:
            pane = self._seam_pane(
                "Analytics", state,
                what=why_not or "visits to this instance's own site, month by month",
                columns=["period", "visitors", "sessions", "views", "bots"])
            # CONFIGURED is whether the site seam ANSWERS, not what the config says of
            # it: the two disagreed on 2026-08-29 and tabs went dark over a working port.
            port = (context or {}).get("port")
            if callable(port):
                try:
                    if port("site_hosting") is not None:
                        pane["configured"], pane["why_not"] = True, ""
                except Exception:
                    pass
            return pane

        campaigns = (context or {}).get("campaigns")
        campaigns = campaigns if isinstance(campaigns, dict) else {}
        campaign_rows = [c for c in (campaigns.get("campaigns") or [])
                         if isinstance(c, dict)]

        panes: list[dict[str, Any]] = [
            {"panel_payload": self._month_strip(months)},
            {"panel_payload": self._arrivals_chart(live)},
            {"panel_payload": self._reading_chart(live)},
        ]
        rings = self._audience_rings(live)
        if rings:
            panes.append({"panel_payload": rings})
        reading = self._interest_pane(live)
        if reading:
            panes.append({"panel_payload": reading})
        journeys = self._journeys_pane(live)
        if journeys:
            panes.append({"panel_payload": journeys})

        subtabs = [
            {"id": "overview", "label": "Overview", "tool_id": "pim_analytics_overview",
             "panel_payload": {"schema": _SCHEMA, "container": "composite",
                               "direction": "column", "panes": panes}},
            {"id": "months", "label": "Months", "tool_id": "pim_analytics_months",
             "panel_payload": self._months_table(months)},
            {"id": "visitors", "label": "Visitors", "tool_id": "pim_analytics_visitors",
             "panel_payload": self._visitor_log(context)},
            {"id": "campaigns", "label": "Campaigns", "tool_id": "pim_analytics_campaigns",
             "panel_payload": self._campaigns_table(campaign_rows)},
        ]
        return {
            "schema": _SCHEMA, "container": "tabbed", "title": "Analytics",
            "configured": True, "why_not": "",
            "active_tab": (_as_text((query or {}).get(ANALYTICS_QUERY))
                           if _as_text((query or {}).get(ANALYTICS_QUERY))
                           in {"overview", "months", "visitors", "campaigns"}
                           else "overview"),
            "tab_query_param": ANALYTICS_QUERY,
            "tabs": subtabs,
        }

    def _month_strip(self, months: list[dict[str, Any]]) -> dict[str, Any]:
        """THE SIGNATURE. Every month this site has, as columns on one scale.

        One scale across all of them, deliberately: normalising each column to its own
        height would draw a forty-visitor month exactly like a four-hundred-visitor one
        and answer nothing. The bot share is drawn INSIDE each column rather than beside
        it, because it is part of the same traffic and a second column would read as twice
        the month.
        """
        ordered = sorted(months, key=lambda m: _as_text(m.get("period")))
        series = [{
            "key": _as_text(m.get("period")),
            "label": _month_label(m.get("period")),
            "count": _int(m.get("visitors")),
            "secondary": _int(m.get("bots")),
        } for m in ordered if _as_text(m.get("period"))]
        latest = series[-1] if series else {}
        prior = series[-2] if len(series) > 1 else {}
        move = ""
        if latest and prior:
            delta = latest["count"] - prior["count"]
            prior_name = _month_label(prior["key"], long=True)
            move = (f"up {delta} on {prior_name}" if delta > 0
                    else f"down {abs(delta)} on {prior_name}" if delta < 0
                    else f"level with {prior_name}")
        return {
            "schema": _SCHEMA, "container": "chart", "mode": "series",
            "title": "People, month by month",
            "count_label": move,
            "series": series,
            "active": latest.get("key", ""),
            "note": ("The shaded foot of each column is automated traffic — search "
                     "crawlers and the like — which is counted separately from people."),
            "empty_text": "No months recorded yet.",
        }

    def _arrivals_chart(self, live: dict[str, Any]) -> dict[str, Any]:
        """Where the last ninety days of sessions came from, as one proportion bar.

        One bar rather than a ring: these are parts of a single whole and the reader wants
        the SHARES, which a common baseline gives away for free.
        """
        widgets = live.get("widgets") if isinstance(live.get("widgets"), dict) else {}
        series = [{"key": _pretty(s.get("key")), "count": _int(s.get("count"))}
                  for s in (widgets.get("origin_distribution") or [])
                  if isinstance(s, dict)]
        return {
            "schema": _SCHEMA, "container": "chart", "mode": "split",
            "title": "How people arrived", "count_label": "last 90 days",
            "series": series,
            "empty_text": "No arrivals recorded in the last 90 days.",
        }

    def _reading_chart(self, live: dict[str, Any]) -> dict[str, Any]:
        """The pages and the referrers, as ranked bars off a shared baseline."""
        pages = [{"key": _as_text(s.get("key")) or "/", "count": _int(s.get("count"))}
                 for s in (live.get("top_pages") or []) if isinstance(s, dict)][:8]
        refs = [{"key": _as_text(s.get("key")), "count": _int(s.get("count"))}
                for s in (live.get("top_referrers") or []) if isinstance(s, dict)][:8]
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "row",
            "panes": [
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "chart", "mode": "rank",
                    "title": "What they read", "series": pages,
                    "count_label": f"{len(pages)} page(s)",
                    "empty_text": "No page views recorded yet."}},
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "chart", "mode": "rank",
                    "title": "Where they came from", "series": refs,
                    "count_label": f"{len(refs)} source(s)",
                    "note": "Your own domain appears here when someone moves between "
                            "your pages.",
                    "empty_text": "No referrers recorded yet."}},
            ],
        }

    def _audience_rings(self, live: dict[str, Any]) -> dict[str, Any] | None:
        """Devices and human-vs-bot, as rings. Two, not five.

        A ring is a good shape for a part-to-whole with two or three slices and a poor one
        for a ranked list, which is why the referrers above are bars. Returns `None` when
        neither has anything, so an empty row is never drawn.
        """
        widgets = live.get("widgets") if isinstance(live.get("widgets"), dict) else {}
        devices = [{"key": _pretty(s.get("key")), "count": _int(s.get("count"))}
                   for s in (widgets.get("device_split") or []) if isinstance(s, dict)]
        split = [{"key": _pretty(s.get("key")), "count": _int(s.get("count"))}
                 for s in (widgets.get("human_vs_bot") or []) if isinstance(s, dict)]
        if not devices and not split:
            return None
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "row",
            "panes": [
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "chart", "mode": "donut",
                    "title": "Devices", "series": devices,
                    "empty_text": "No devices recorded yet."}},
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "chart", "mode": "donut",
                    "title": "People and machines", "series": split,
                    "note": "Machines are search crawlers and scrapers. They are excluded "
                            "from every other figure on this tab.",
                    "empty_text": "Nothing recorded yet."}},
            ],
        }

    def _interest_pane(self, live: dict[str, Any]) -> dict[str, Any] | None:
        """What people were interested in, and which pages lose them.

        Both were on the legacy dashboard and both are already derived — they arrive in
        the same payload as everything above. They are the two figures that suggest an
        ACTION rather than reporting a state: a subject people keep returning to is worth
        writing more of, and a page most people leave from is worth a second look.

        Returns `None` when neither has anything, so a client whose site is too new for
        either is not shown two empty boxes.
        """
        interests = [{"key": _as_text(c.get("category")).replace("_", " ").capitalize(),
                      "count": _int(c.get("hits"))}
                     for c in (live.get("interest_profile_categories") or [])
                     if isinstance(c, dict)][:6]
        dead = [d for d in (live.get("dead_end_pages") or []) if isinstance(d, dict)][:6]
        if not interests and not dead:
            return None
        rows = [{
            "page": _as_text(d.get("page_path")) or "/",
            "arrivals": _as_text(d.get("entry_count")),
            "left straight away": (
                f"{round(float(d.get('single_page_session_rate') or 0) * 100)}%"),
            "time on page": _seconds(d.get("average_active_time_ms")),
        } for d in dead]
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "row",
            "panes": [
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "chart", "mode": "rank",
                    "title": "What interests them", "series": interests,
                    "count_label": "by page views",
                    "note": "Grouped from the pages people opened.",
                    "empty_text": "Not enough reading yet to group."}},
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "record_table",
                    "title": "Pages people leave from",
                    "columns": ["page", "arrivals", "left straight away", "time on page"],
                    "rows": rows, "row_count": len(rows),
                    "count_label": f"{len(rows)} page(s)",
                    "note": ("Where a visit both started and ended. A high share is worth "
                             "a look — it can mean the page answered everything, or that "
                             "it offered nowhere to go next."),
                    "empty_text": "No single-page visits recorded yet."}},
            ],
        }

    def _journeys_pane(self, live: dict[str, Any]) -> dict[str, Any] | None:
        """The last two figures the legacy dashboard carried, and the hardest to read.

        ABANDONED INTENT is a visit that reached a page meaning "I want to get in touch"
        and left without doing it — the nearest thing this stack has to a lost customer.
        CONVERSION-ASSISTING PAGES are the pages such visits passed through on their way
        to actually doing it.

        Both derive from the same rollup as everything else. Kept LAST and returning
        `None` when neither has anything, because at a small site's traffic they are
        usually empty, and two empty boxes above the fold would make a working tab look
        like a broken one.
        """
        abandoned = live.get("abandoned_intent_sessions")
        abandoned = abandoned if isinstance(abandoned, dict) else {}
        lost = _int(abandoned.get("count"))
        assists = [a for a in (live.get("conversion_assisting_pages") or [])
                   if isinstance(a, dict)][:6]
        if not lost and not assists:
            return None
        sample = [s for s in (abandoned.get("sample") or []) if isinstance(s, dict)][:6]
        lost_rows = [{
            "started at": _as_text(s.get("entry_page")) or _as_text(s.get("page_path")) or "—",
            "pages seen": _as_text(s.get("page_count")) or "—",
            "arrived by": _as_text((s.get("arrival") or {}).get("label")
                                   if isinstance(s.get("arrival"), dict)
                                   else s.get("origin_type")) or "—",
            "when": _as_text(s.get("started_at"))[:10] or "—",
        } for s in sample]
        assist_rows = [{
            "page": _as_text(a.get("page_path")) or "/",
            "assisted": _as_text(a.get("assist_count")) or _as_text(a.get("count")) or "—",
        } for a in assists]
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "row",
            "panes": [
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "record_table",
                    "title": "Visits that stopped short",
                    "columns": ["started at", "pages seen", "arrived by", "when"],
                    "rows": lost_rows, "row_count": len(lost_rows),
                    "count_label": f"{lost} visit(s)",
                    "note": ("Someone reached a page about getting in touch and left "
                             "without doing it. A few is normal; a pattern is worth a "
                             "look at that page."),
                    "empty_text": "Nobody stopped short in this window."}},
                {"panel_payload": {
                    "schema": _SCHEMA, "container": "record_table",
                    "title": "Pages that helped",
                    "columns": ["page", "assisted"],
                    "rows": assist_rows, "row_count": len(assist_rows),
                    "count_label": f"{len(assist_rows)} page(s)",
                    "note": "Pages people passed through before getting in touch.",
                    "empty_text": "No assisted visits recorded yet."}},
            ],
        }

    def _months_table(self, months: list[dict[str, Any]]) -> dict[str, Any]:
        """The figures behind the strip. A chart that cannot be checked is a claim."""
        rows = [{
            "period": _as_text(m.get("period")),
            "people": _as_text(m.get("visitors")),
            "visits": _as_text(m.get("sessions")),
            "page views": _as_text(m.get("views")),
            "automated": _as_text(m.get("bots")),
        } for m in sorted(months, key=lambda m: _as_text(m.get("period")), reverse=True)]
        return {
            "schema": _SCHEMA, "container": "record_table", "title": "Months",
            "columns": ["period", "people", "visits", "page views", "automated"],
            "rows": rows, "row_count": len(rows),
            "count_label": f"{len(rows)} month(s)",
            "note": "The numbers the chart is drawn from.",
            "empty_text": "No months recorded yet.",
        }

    def _visitor_log(self, context: dict[str, Any] | None) -> dict[str, Any]:
        """WHO CAME. The log the legacy dashboard called Visitor records.

        One row per person for a month, with when they first and last appeared, how many
        visits they made and how they arrived. It is the thing a proprietor reads when a
        number surprises them, and PIM had no equivalent at all.
        """
        reader = (context or {}).get("analytics_records")
        data: dict[str, Any] = {}
        if callable(reader):
            try:
                got = reader("")
                data = got if isinstance(got, dict) else {}
            except Exception:
                data = {}
        leaflet = data.get("leaflet") if isinstance(data.get("leaflet"), dict) else {}
        visitors = [v for v in (leaflet.get("visitors") or []) if isinstance(v, dict)]
        rows = []
        for v in visitors:
            sessions = [s for s in (v.get("sessions") or []) if isinstance(s, dict)]
            first = next((s for s in sessions if isinstance(s.get("arrival"), dict)), {})
            arrival = (first.get("arrival") or {}) if isinstance(first, dict) else {}
            rows.append({
                "who": _as_text(v.get("label")) or "—",
                "visits": str(len(sessions)),
                "arrived by": _as_text(arrival.get("label")) or "—",
                "first seen": _as_text(v.get("first_seen_at"))[:10],
                "last seen": _as_text(v.get("last_seen_at"))[:10],
                "returning": "yes" if v.get("returning_from_prior_month") else "",
            })
        period = _as_text(data.get("period"))
        returning = sum(1 for r in rows if r["returning"])
        return {
            "schema": _SCHEMA, "container": "record_table",
            "title": f"Visitors · {period}" if period else "Visitors",
            "columns": ["who", "visits", "arrived by", "first seen", "last seen",
                        "returning"],
            "rows": rows, "row_count": len(rows),
            "count_label": (f"{len(rows)} people"
                            + (f" · {returning} returning" if returning else "")),
            "note": ("One row per person for this month. Names are labels this site "
                     "assigns; nobody is identified by anything they did not give you."),
            "empty_text": ("No visitor records for this month yet. They are written as "
                           "the month goes on."),
        }

    def _campaigns_table(self, campaign_rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [{
            "campaign": _as_text(c.get("label")) or _as_text(c.get("campaign")),
            "source": _as_text(c.get("source")),
            "medium": _as_text(c.get("medium")),
            "lands on": _as_text(c.get("target")) or _as_text(c.get("lands_on")),
            "token": _as_text(c.get("token")),
            "created": _as_text(c.get("created"))[:10],
        } for c in campaign_rows]
        return {
            "schema": _SCHEMA, "container": "record_table", "title": "Campaigns",
            "columns": ["campaign", "source", "medium", "lands on", "token", "created"],
            "rows": rows, "row_count": len(rows),
            "count_label": f"{len(rows)} link(s)",
            "empty_text": ("No tracked links yet. A campaign is a token on a QR code or "
                           "a flyer that says which piece of print a visit came from."),
        }

    def _email_pane(self, state: dict[str, str],
                    context: dict[str, Any] | None = None,
                    query: dict[str, Any] | None = None) -> dict[str, Any]:
        """This instance's own addresses: where each forwards, its send-as stage — and,
        since 2026-09-10, the three acts a client may take on one of them.

        Operator, 2026-09-10: "the email tab should be properly configured for a user to
        edit emails or re run the verifications to be sent for authorization / adding an
        email to their Gmail". So an address opens (the `pick` control, the same one the
        operator's Mailboxes surface uses) onto the SAME forms that surface builds —
        `mailbox_admin.client_address_forms`: change where it forwards, send the setup
        email, send a reminder. Not a second copy: the confirmation texts and the "SENDS
        AN EMAIL" labels are the operator's, and the routes name the operator's door,
        which the host repoints to the client's (`_repoint_client_forms`). Adding and
        deleting an address stay the operator's and are never offered here.

        PIM employs `forwarding.set`, `identity.verify_request` and `identity.remind`
        for these (and still none of `message.send`, `message.forward`, `alias.create`,
        `alias.remove`), each a separate grant the seam judges when the button is
        pressed — a refusal comes back in the gate's words on the form's status line.

        The seam's own refusal to LIST is shown as itself — "may not 'alias.list'" is a
        permission answer, and flattening it to an empty table would report no mail.
        """
        from micyte.tools.mailbox_admin import (
            ADDRESS_QUERY,
            _address_of,
            _domain_of,
            client_address_forms,
        )

        port = (context or {}).get("port")
        adapter = None
        if callable(port):
            try:
                adapter = port("email_provider")
            except Exception:
                adapter = None
        columns = ["address", "forwards to", "send-as"]
        what = "this instance's own addresses and where each forwards"
        if adapter is None or not hasattr(adapter, "list_aliases"):
            return self._seam_pane("Email", state, what=what, columns=columns)
        try:
            listed = [dict(row) for row in adapter.list_aliases()]
        except Exception as exc:
            pane = self._seam_pane("Email", state, what=str(exc), columns=columns)
            # The adapter ANSWERED — with a refusal. That is a configured seam whose
            # grant is missing, which the pane says; the tab stays so it can be read.
            pane["configured"] = True
            pane["why_not"] = ""
            return pane
        sandbox = _as_text((context or {}).get("sandbox_id"))
        rows = []
        for row in listed:
            domain = _domain_of(row)
            address = _address_of(row, domain=domain) if domain else (
                _as_text(row.get("send_as")) or _as_text(row.get("local_part")))
            rows.append({
                "address": address,
                "forwards to": _as_text(row.get("forward_to")) or "—",
                # The LABEL beside the code where there is one — "Verified — can send
                # as this address" is what a client can act on; `verified` is what the
                # code calls it.
                "send-as": (_as_text(row.get("send_as_label"))
                            or _as_text(row.get("send_as_stage")) or "not_started"),
                "_domain": domain, "_row": row,
            })
        drawn = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        # A COUNT that answers the question the tab is opened with. "4 row(s)" says how
        # many addresses; what somebody wants to know is how many are finished — the
        # send-as stage is the only thing on this tab that has a pending state.
        done = sum(1 for r in drawn if _as_text(r.get("send-as")).lower().startswith("verif"))
        table = self._seam_pane("Email", state, rows=drawn, what=what, columns=columns)
        table["configured"] = True
        table["why_not"] = ""
        open_address = _as_text((query or {}).get(ADDRESS_QUERY))
        if drawn:
            table["count_label"] = (
                f"{len(drawn)} address(es) · {done} verified"
                if done != len(drawn) else f"{len(drawn)} address(es) · all verified")
            table["notice"] = (
                "Open an address to change where it forwards or to re-send its setup "
                "email. An address that is not verified cannot send as itself yet — its "
                "owner finishes that from the setup email, which two of the buttons on an "
                "open address SEND; nothing else here sends anything.")
            table["pick"] = {
                "label": "Open an address",
                "param": ADDRESS_QUERY,
                "options": [{"value": r["address"],
                             "label": f"{r['address']}  ·  {r['send-as']}"} for r in drawn],
                "go_label": "Open",
            }
        chosen = next((r for r in rows if r["address"] == open_address), None)
        if chosen is None:
            return table
        table["back"] = {"label": "All addresses", "param": ADDRESS_QUERY, "value": ""}
        forms = client_address_forms(chosen["_row"], domain=chosen["_domain"], sandbox=sandbox)
        return {
            "schema": _SCHEMA, "container": "composite", "direction": "column",
            "title": "Email", "configured": True, "why_not": "",
            "panes": [{"panel_payload": table}, *({"panel_payload": f} for f in forms)],
        }

    def _domain_pane(self, context: dict[str, Any]) -> dict[str, Any]:
        """The domain this instance keeps, and what is actually standing at it.

        It was ONE row — "domain kept: masonlenehan.com" — which is a fact a client can
        read off their own address bar. A tab that says something they already know is a
        tab that teaches them the app has nothing to say.

        Everything here comes from host facts the other tabs already carry: the site the
        credential fences on, how many pages that site serves, how many assets it draws
        from, and whether its text can be edited in place. Nothing new is read; what was
        missing was putting them where the question is asked.
        """
        account = context.get("account")
        domain = _as_text((account or {}).get("domain")) if isinstance(account, dict) else ""
        if not domain:
            return {
                "schema": _SCHEMA, "container": "record_table", "title": "Domain",
                "count_label": "", "columns": ["fact", "value"], "rows": [], "row_count": 0,
                # NAMED NO PAGE. Until 2026-08-29 this read "...configures on Ports" —
                # an operator-only screen `masonlenehan.com` has zero nginx locations
                # for, so a client reading it was told to visit a page they structurally
                # cannot open. Said in the client's own terms instead: what is missing,
                # and who is setting it up.
                "empty_text": (
                    "No domain is recorded for this instance yet. Your operator sets "
                    "this up as part of connecting your site."),
            }

        rows = [{"fact": "domain kept", "value": domain},
                {"fact": "site answers at", "value": f"https://{domain}/"}]

        site = context.get("site")
        if isinstance(site, dict):
            pages = [p for p in (site.get("pages") or []) if isinstance(p, dict)]
            if pages:
                rows.append({"fact": "pages served", "value": str(len(pages))})
            if site.get("enabled") is not None:
                rows.append({
                    "fact": "text editable in place",
                    "value": "yes" if site.get("enabled") else "not set up",
                })

        resources = context.get("resources")
        types = [t for t in ((resources or {}).get("types") or [])
                 if isinstance(t, dict)] if isinstance(resources, dict) else []
        filed = sum(len(t.get("rows") or []) for t in types)
        if filed:
            rows.append({"fact": "files it draws from", "value": str(filed)})

        return {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Domain",
            "count_label": domain,
            "columns": ["fact", "value"],
            "rows": rows,
            "row_count": len(rows),
            "notice": (
                "The domain itself is kept by FND on your behalf. Changing where it "
                "points is an operator action, not one this app performs."),
            "empty_text": "",
        }

    def _resources_pane(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """This instance's resources, in SUBTABS its own local domain names.

        The operator's instruction: "use subtabs that are derived from artifact typing
        defined in their lcl samras PIM sandbox documents". So the tabs are read from the
        `resource_type` branch of the instance's OWN `pim` local domain — not from the
        shared type tree, which offers twelve types at depth 1 and several of those are
        the operator's. An instance shows the types it owns something of, and adding a
        node in the Domain editor adds a subtab with no code here.

        A NESTED `tabbed` container, the same shape Design uses for Writing and Pages. The
        rows arrive as host facts because both halves are the host's to read: the branch
        lives in the store and the files under `/srv/webapps`, and a tool in the published
        package may reach neither.
        """
        facts = (context or {}).get("resources")
        facts = facts if isinstance(facts, dict) else {}
        types = [t for t in (facts.get("types") or []) if isinstance(t, dict)]
        why_not = _as_text(facts.get("why_not"))
        if not types:
            return {
                "schema": _SCHEMA,
                "container": "record_table",
                "title": "Resources",
                "columns": ["name", "kind", "size"],
                "rows": [],
                "row_count": 0,
                "empty_text": why_not or (
                    "This instance's PIM domain names no resource types yet."),
            }
        panes = []
        for entry in types:
            label = _as_text(entry.get("label")) or "resources"
            rows = [r for r in (entry.get("rows") or []) if isinstance(r, dict)]
            reason = _as_text(entry.get("why_not"))
            panes.append({
                "id": label.lower().replace(" ", "_"),
                # The COUNT in the label. A row of subtabs with no numbers makes
                # somebody open each to find out which has anything in it.
                "label": (f"{label.replace('_', ' ').title()} ({len(rows)})"
                          if rows else label.replace("_", " ").title()),
                "tool_id": f"{self.tool_id}_resources_{label.lower()}",
                "panel_payload": {
                    "schema": _SCHEMA,
                    "container": "record_table",
                    "title": label.replace("_", " ").title(),
                    "count_label": f"{len(rows)} item(s)",
                    "columns": ["name", "kind", "size", "file"],
                    "rows": rows,
                    "row_count": len(rows),
                    # A type the instance named and holds nothing of still gets its tab.
                    # Dropping it would answer "why is there no Documents tab?" with
                    # silence, when the answer is "you have no documents".
                    "empty_text": reason or f"No {label} are filed for this instance yet.",
                },
            })
        # THE ORGANISATION PANE, first among the type subtabs. The types below say what an
        # instance HOLDS; this one says how it is ARRANGED, and it is the half a client can
        # change. Placed first because a client opening Resources to file something looks
        # for the shape before the contents.
        panes.insert(0, self._resource_graph_pane(facts))
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Resources",
            "active_tab": panes[0]["id"],
            "tab_query_param": "resource_tab",
            # `tabs`, which is what `renderTabbed` reads. Named `panes` first, and the
            # container drew "No tabs to display" over five real subtabs — a payload that
            # is correct in every value and wrong in one key.
            "tabs": panes,
        }

    def _resource_graph_pane(self, facts: dict[str, Any]) -> dict[str, Any]:
        """The instance's resource branch as a tree it can rearrange — and the forms that do it.

        WHAT A ROW IS. A resource entry reads as three lcl ids — its own node address, the
        icon it wears, and the thing it stands for — and a GROUPING is the same row
        denoting nothing: the empty parent with a title that the arrangement is made of.
        `grouping` arrives already derived, so this pane does not carry a second copy of
        that rule.

        The indent is drawn from `parent`, not from a nested payload: `record_table` takes
        flat rows, and nesting the tree here would mean the order and the structure could
        disagree.

        THE DOOR WAS BUILT, 2026-09-01, and the three forms below are the other half of
        it. This paragraph used to read "READ-ONLY UNTIL THE DOOR IS BUILT … drawing them
        before that exists would put buttons in front of a client that answer 404", and
        the reason is kept rather than deleted because it is still the rule these forms
        obey. `/portal/api/v2/pim/resources/<action>` now takes `define_type`,
        `rename_node` and `move_node` behind three checks — the datum-write gate, the
        sign-in, and the branch scope read fresh from the store — and what is drawn here is
        exactly those three actions and nothing that door would answer 404 or 409 to. When
        the graph names no root the branch is unwritable, so the table ships alone: a form
        whose every submission is refused is the same mistake in a newer coat.

        TWO THINGS THE DOOR ENFORCES THAT THESE FORMS RESTATE. The actions keep the
        OPERATION's own names — `add_grouping` was written on the door first and would have
        been DENIED on every request, because `authorize_datum_write` judges the tool that
        DECLARES an action and an undeclared one has no document kind to be measured
        against. And the instance is NOT a field: it is resolved from the sign-in header
        server-side, so there is no msn input here and there must never be one.

        WHICH FIELD MAY DEFAULT. `define_type` names its PARENT and may omit it, so its
        parent select opens on the branch root — a new grouping at the top of the branch is
        the common case. The other two name the node they act ON and open on nothing,
        because the door's `node or root` fallback would make an unnamed rename rename the
        branch ROOT, and the root is found by its label: that orphans the whole branch from
        this very tab, permanently and with a 200.
        """
        graph = (facts or {}).get("graph")
        graph = graph if isinstance(graph, dict) else {}
        nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
        why_not = _as_text(graph.get("why_not"))
        root = _as_text(graph.get("root"))

        depth: dict[str, int] = {root: 0}
        # An option label says the PATH, not the bare name. Two groupings may each hold a
        # `logo.svg`, and a picker offering `logo.svg` twice asks the client to guess which
        # row they meant. The table's indent cannot be borrowed for it: a browser collapses
        # leading spaces inside an <option>, so the nesting has to be spelled out.
        trail: dict[str, str] = {}
        rows = []
        # Nodes that may TAKE a child. `move_node` refuses a parent that is not a type node
        # or that holds a writing, so offering a filed entry as a destination would be
        # offering a refusal.
        parents: list[dict[str, str]] = []
        # Every node the door would accept as a subject — filed entries included, because
        # renaming a resource is as much this tab's business as renaming a folder.
        subjects: list[dict[str, str]] = []
        for entry in nodes:
            node = _as_text(entry.get("node"))
            parent = _as_text(entry.get("parent"))
            level = depth.get(parent, 0) + 1
            depth[node] = level
            label = _as_text(entry.get("label")) or node
            above = trail.get(parent)
            trail[node] = f"{above} / {label}" if above else label
            denotes = _as_text(entry.get("slot")) or _as_text(entry.get("artifact"))
            rows.append({
                # The indent IS the arrangement, and a client reads it before they read a
                # column. Two spaces per level, in the label itself, because record_table
                # draws text and not a tree.
                "name": ("  " * (level - 1)) + label,
                "address": node,
                "holds": "grouping" if entry.get("grouping") else (denotes or "—"),
                "icon": _as_text(entry.get("icon")) or "—",
            })
            subjects.append({"value": node, "label": trail[node]})
            if entry.get("grouping"):
                parents.append({"value": node, "label": trail[node]})
        table = {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Arrangement",
            "count_label": f"{len(rows)} node(s)",
            "columns": ["name", "address", "holds", "icon"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": why_not or (
                "Your resources are not grouped yet. Groupings are folders you name — "
                "icons, images, memos, logos — and each one holds the files it stands "
                "for."),
        }
        return {
            "id": "arrangement",
            "label": f"Arrangement ({len(rows)})" if rows else "Arrangement",
            "tool_id": f"{self.tool_id}_resources_arrangement",
            # A COMPOSITE, not a bare table. The arrangement and the acts on it are one
            # pane, so a client who has just read where a thing sits does not go looking
            # elsewhere for the control that moves it.
            "panel_payload": {
                "schema": _SCHEMA,
                "container": "composite",
                "direction": "column",
                "panes": [{"panel_payload": table},
                          *self._arrangement_forms(root, parents, subjects)],
            },
        }

    def _arrangement_forms(self, root: str, parents: list[dict[str, str]],
                           subjects: list[dict[str, str]]) -> list[dict[str, Any]]:
        """The writes this tab offers, or none where the branch cannot take one.

        Each posts to `/portal/api/v2/pim/resources/<action>` under the ACTION's own name,
        which is the word the datum-write gate measures the request against.

        DRAWN ONLY WHERE THEY CAN LAND. No root means the domain names no resource branch
        and the door answers every action 409, so nothing is offered. No nodes yet means
        there is nothing to rename or move, so only the add form is drawn and the table's
        empty state beside it says what a grouping is for.
        """
        if not root:
            return []
        # The branch root offered by NAME, rather than through the blank "—" option every
        # select carries. `move_node` reads its destination literally and an empty one is
        # refused as out of scope, so "top level" has to be a value a client can pick.
        top = {"value": root, "label": "Top level — not inside a grouping"}
        add = {
            "schema": _SCHEMA,
            "container": "record_form",
            "title": "Add a grouping",
            "fields": [
                {"key": "label", "label": "What to call it",
                 "placeholder": "images, logos, memos…"},
                # `node` is the PARENT for this action — the door's own field name for it,
                # kept so the form and the route cannot drift on what the word means.
                {"key": "node", "label": "Put it inside", "type": "select",
                 "value": root, "options": [top, *parents]},
            ],
            "submit_label": "Add grouping",
            "submit_action": {
                "route": f"{_RESOURCES_ROUTE}/define_type",
                "success_label": "Added",
            },
        }
        if not subjects:
            return [{"panel_payload": add}]
        rename = {
            "schema": _SCHEMA,
            "container": "record_form",
            "title": "Rename",
            "fields": [
                # NO DEFAULT. The door falls back to the branch root when no node is named,
                # and the root is found by its label — so a rename that defaulted would
                # rename the branch out from under the tab that reads it.
                {"key": "node", "label": "Which one", "type": "select",
                 "value": "", "options": subjects},
                {"key": "label", "label": "New name"},
            ],
            "submit_label": "Rename",
            "submit_action": {
                "route": f"{_RESOURCES_ROUTE}/rename_node",
                "success_label": "Renamed",
            },
        }
        move = {
            "schema": _SCHEMA,
            "container": "record_form",
            "title": "Move",
            "fields": [
                {"key": "node", "label": "Which one", "type": "select",
                 "value": "", "options": subjects},
                {"key": "new_parent", "label": "Into", "type": "select",
                 "value": root, "options": [top, *parents]},
                # `descendants` has no default at the WRITER, deliberately: "follow" and
                # "promote" produce different trees and it refuses to guess which was
                # meant. Drawing the choice satisfies that rather than dodging it — what
                # the writer refuses is a caller deciding silently, and a labelled select
                # opened on the ordinary meaning of "move" is not silent.
                {"key": "descendants", "label": "What goes with it", "type": "select",
                 "value": "follow", "options": [
                     {"value": "follow",
                      "label": "Everything inside it comes along"},
                     {"value": "promote",
                      "label": "Move it alone — leave what was inside it where it is"},
                 ]},
            ],
            "submit_label": "Move",
            "submit_action": {
                "route": f"{_RESOURCES_ROUTE}/move_node",
                "success_label": "Moved",
            },
        }
        return [{"panel_payload": add}, {"panel_payload": rename},
                {"panel_payload": move}]

    def _payment_pane(self, context: dict[str, Any]) -> dict[str, Any]:
        """The client's own PayPal: what it has taken, and the form that connects it.

        Operator, 2026-09-01: "make sure the payment tab allows for a user to see
        activity … Configuration of PayPal happens in the utilities port page tab. Each
        client can do this themselves." So this is THEIR money coming in — what FND
        charges them stays on the Grantor card, which is all the old pane could say; it
        returned `rows: []` under every condition.

        THE FORM IS HERE AND NOT ON UTILITIES, and that is a correction rather than a
        preference. Measured 2026-09-02: `/portal/utilities` answers **404 on every
        client vhost** — bpw, tff, cvcc, masonlenehan — because a client vhost proxies
        `/dashboard/`, `/dashboard/profile` and `/portal/static/` and nothing else. A
        form placed there is a form no client can open, and an empty state naming it is
        the "never send a client to a page they cannot reach" defect this file has
        already been fixed for once. PIM is the client's app; the connection lives where
        the person making it is.

        THREE EMPTY STATES, NOT ONE. "We could not read it", "your PayPal is not
        connected" and "connected, nothing taken yet" are different answers and the same
        empty table. The middle one is the only one with something to do about it.
        """
        fact = context.get("payment")
        fact = fact if isinstance(fact, dict) else {}
        why_not = _as_text(fact.get("why_not"))
        connected = bool(fact.get("connected"))
        environment = _as_text(fact.get("environment"))

        rows = [
            {
                "when": _as_text(line.get("when")) or "—",
                "what": _as_text(line.get("what")) or "—",
                "who": _as_text(line.get("who")) or "—",
                "amount": _as_text(line.get("amount")) or "—",
                "status": _as_text(line.get("status")) or "—",
            }
            for line in (fact.get("payments") or []) if isinstance(line, dict)
        ]
        total = _as_text(fact.get("total"))
        if why_not:
            empty_text = why_not
        elif not connected:
            empty_text = (
                "Your PayPal account is not connected yet. Enter your PayPal credentials "
                "below and the payments your site takes will be listed here."
            )
        else:
            empty_text = "Your site has not taken any payments yet."

        takings = {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Payments received",
            "count_label": (f"{len(rows)} payment(s) · {total}"
                            if rows and total else ""),
            "columns": ["when", "what", "who", "amount", "status"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": empty_text,
            "notice": (
                "These are the payments your website has taken through your own PayPal "
                "connection. What FND charges you is on your Grantor card, on your "
                "Profile page."
            ),
        }

        # THE SECRET IS NEVER PRE-FILLED — it is not in the payload at all, and a blank
        # password field on a connected account is the honest control: you may replace
        # the key, and you cannot read it back. The client id IS shown; PayPal's own
        # design makes it public.
        connect = {
            "schema": _SCHEMA,
            "container": "record_form",
            "title": ("Your PayPal connection" if connected
                      else "Connect your PayPal account"),
            "count_label": (f"Connected · {environment or 'sandbox'}" if connected
                            else "Not connected"),
            "fields": [
                {"key": "client_id", "label": "PayPal client ID",
                 "value": _as_text(fact.get("client_id"))},
                {"key": "client_secret", "label": (
                    "PayPal secret (enter it again to replace it)" if connected
                    else "PayPal secret"), "type": "password", "value": ""},
                {"key": "environment", "label": "Which PayPal account",
                 "type": "select", "value": environment or "sandbox",
                 "options": [
                     {"value": "sandbox",
                      "label": "Sandbox — test payments, no real money"},
                     {"value": "live", "label": "Live — real payments"},
                 ]},
            ],
            "submit_label": "Save connection",
            "submit_action": {
                # `/__fnd/pim/...`, the path a client vhost actually proxies. `/portal/api/` is
                # the operator's and reaches the static site from a client domain — the
                # defect `fnd_client_site` records costing PIM its whole authoring tab.
                "route": "/__fnd/pim/payment/connect",
                "success_label": "Connected",
            },
            "notice": (
                "These are YOUR PayPal credentials, from your own PayPal account. FND "
                "does not hold a key on your behalf — your website's checkout is simply "
                "routed to the account you connect here. Find them in PayPal under "
                "Developer > Apps and Credentials."
            ),
        }
        return {"schema": _SCHEMA, "container": "composite", "direction": "column",
                # OMITTED when not connected (2026-09-10): a client connects their PayPal
                # from the operator's onboarding, not from a tab they cannot use yet.
                "configured": connected,
                "why_not": "" if connected else (
                    why_not or "your PayPal account is not connected yet"),
                "panes": [{"panel_payload": connect}, {"panel_payload": takings}]}
    def _home_pane(self, private_dir: Any, sandbox: str = "",
                   bindings: list[dict[str, Any]] | None = None,
                   context: dict[str, Any] | None = None) -> dict[str, Any]:
        """What this account is, at a glance, and then the detail behind it.

        Operator, 2026-08-28: "the home tab should be a general page about services
        provided and storage used, perhaps also a small analytics overview on a single
        dashboard surface". And 2026-08-29: "the landing tab is not very styled or good
        info".

        Both are fair. It was three stacked tables — services, storage, months — with no
        hierarchy, so the first thing a client saw was a grid of numbers with nothing
        saying which mattered. A table is where you go to CHECK a figure; it is not how
        you learn how the month went.

        So the glance comes first, as tiles: what they pay, how the month is going, what
        their records occupy. Each tile that has somewhere to go carries the tab it opens,
        so "381 people this month" is the way into Analytics rather than a dead number.
        The tables stay underneath, because a glance that cannot be checked is a claim.
        """
        context = context if isinstance(context, dict) else {}
        return {
            "schema": _SCHEMA,
            "container": "composite",
            "direction": "column",
            "panes": [
                {"panel_payload": self._glance_tiles(context)},
                # The plan before the services: "what am I on" is answered before "what
                # do I hold", and the trial and the card live with the plan.
                {"panel_payload": self._plan_pane(context)},
                {"panel_payload": self._services_pane(context)},
                {"panel_payload": self._storage_pane(context)},
            ],
        }

    def _glance_tiles(self, context: dict[str, Any]) -> dict[str, Any]:
        """The four figures worth knowing before reading anything.

        Derived from the same host facts the tables below show, so a tile and the row it
        summarises cannot disagree. A tile with nothing to say is DROPPED rather than
        shown as zero — "0 people" on an instance whose analytics are not connected reads
        as a bad month rather than as an absent seam, and those are opposite situations.
        """
        tiles: list[dict[str, Any]] = []

        held, total, _why = account_of(context)
        # ONLY WHEN SOMETHING IS HELD. `subscription_ledger` totals an empty book to
        # "$0.00", which is a string and therefore true — so an account holding nothing
        # drew "$0.00 per month" as its first tile, against this function's own rule.
        # Measured in a browser on 2026-09-16 on a provisioned test instance.
        if total and held:
            tiles.append({"value": total, "label": "per month", "tab": "home"})
        if held:
            tiles.append({"value": str(len(held)), "label": "services", "tab": "home"})
        facts = plan_of(context)
        if facts["trial"].get("active"):
            tiles.append({"value": str(facts["trial"].get("days_left")),
                          "label": "trial days left", "tab": "home"})
        if facts["balance"]:
            tiles.append({"value": facts["balance"], "label": "balance", "tab": "home"})

        analytics = context.get("analytics")
        months = [m for m in ((analytics or {}).get("months") or [])
                  if isinstance(m, dict)] if isinstance(analytics, dict) else []
        if months:
            latest = sorted(months, key=lambda m: _as_text(m.get("period")))[-1]
            tiles.append({
                "value": _as_text(latest.get("visitors")) or "0",
                "label": f"people in {_as_text(latest.get('period'))}",
                "tab": "analytics",
            })

        storage = context.get("storage")
        if isinstance(storage, dict) and _as_text(storage.get("documents")):
            tiles.append({"value": _as_text(storage.get("documents")),
                          "label": "documents", "tab": "home"})

        resources = context.get("resources")
        types = [t for t in ((resources or {}).get("types") or [])
                 if isinstance(t, dict)] if isinstance(resources, dict) else []
        filed = sum(len(t.get("rows") or []) for t in types)
        if filed:
            tiles.append({"value": str(filed), "label": "files", "tab": "resources"})

        return {
            "schema": _SCHEMA,
            "container": "stat_tiles",
            "title": "Your account",
            "tiles": tiles,
        }

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        private_dir: Any = None,
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        """PIM's tabs. The hub is a TABULAR, which is what makes the package an app.

        ``private_dir`` used to be a plain keyword nothing passed. Every call site —
        `build_tool_panels`, the instrument face, the export route — supplies four
        arguments and none of them is this one, so the seam row rendered
        "bound=no, permitted=no" on an instance where the port was both. The kind of
        wrong answer that is indistinguishable from the true one.

        It now arrives in ``host_context``, which is the declared way for a tool to be
        handed facts only the host holds. The keyword is kept so a direct caller that
        passes it still works, and the context wins when both are present.
        """
        del authority_db_file, document_id, datum_address
        context = host_context if isinstance(host_context, dict) else {}
        private_dir = context.get("private_dir", private_dir)
        query = dict(extra_query or {})
        sandbox = _as_text(sandbox_id)

        email = seam_state(_config(private_dir), port_id="email_provider",
                           sandbox=sandbox, bindings=context.get("bindings"))
        site = seam_state(_config(private_dir), port_id="site_hosting",
                          sandbox=sandbox, bindings=context.get("bindings"))

        design = PimDesign()

        # BUILT FROM THE FEATURE TABLE, not from a written-out list, and from ONE pass
        # over it. One source for every instance; what differs per client is which of
        # these is switched on, which services the account holds, and whether the seam
        # each needs is answering. See `FEATURES`.
        #
        # There used to be a SECOND pass here, appending a tab per paid service out of a
        # second map. It consulted the account and not the toggles, so a feature this pass
        # had just skipped for being OFF was re-added by that one: `email` sat in both
        # tables, and `features={"email": False}` on an account holding `user_email` still
        # rendered an Email tab. One table and one pass is why that cannot recur for the
        # next id somebody lists twice — there is no second place to list it.
        builders = {
            "home": lambda: self._home_pane(
                private_dir, sandbox, context.get("bindings"), context=context),
            "analytics": lambda: self._analytics_pane(site, context, query=query),
            "email": lambda: self._email_pane(email, context, query=query),
            "design": lambda: design.build_panel_payload(
                sandbox_id=sandbox, extra_query=query, host_context=context),
            "site": lambda: build_site_payload(context, sandbox=sandbox),
            "resources": lambda: self._resources_pane(context),
            "domain": lambda: self._domain_pane(context),
            "storage": lambda: self._storage_pane(context),
            "payment": lambda: self._payment_pane(context),
        }
        enabled = features_for_instance(private_dir, _as_text(context.get("msn_id")))
        # WHAT THE CLIENT PAYS FOR, from the grantor's books — the host's fact, never
        # PIM's to read. A tab whose `held` names a service this account does not carry is
        # not drawn: a client who takes a new service gets its tab, and one who does not
        # is not shown a door to something they do not buy, which is the same rule the
        # gallery follows about apps.
        held, _total, _why = account_of(context)
        held_services = {_as_text(line.get("service")) for line in held}

        def answers(port_id: str) -> bool:
            """Whether the host hands this instance a live adapter for ``port_id`` — the
            same test every seam pane makes, asked here for the two tabs whose builders
            live in `pim_design` and return no `configured` of their own."""
            port = context.get("port")
            if not callable(port):
                return False
            try:
                return port(port_id) is not None
            except Exception:
                return False

        panes = []
        not_shown: list[dict[str, str]] = []
        for feature in FEATURES:
            fid = feature["id"]
            if not enabled.get(fid, feature["default_on"]):
                # OFF for this instance. Absent entirely — a client who was never given a
                # feature should not be shown a locked door advertising it.
                continue
            unlocked_by = feature["held"]
            if unlocked_by and not held_services.intersection(unlocked_by):
                # NOT HELD. Also absent, and for a different reason the operator may want
                # to state elsewhere: this one is the account's answer, not the toggle's.
                continue
            build = builders.get(fid)
            if build is None:
                continue
            # ON BUT UNCONFIGURED IS OMITTED (2026-09-10), and the PANE says whether it
            # is: `configured` is the pane's own answer, from the adapter it reached or
            # the fact it was handed — never a second reading of the config here, which
            # is what went dark over answering ports on 2026-08-29. The two panes built
            # elsewhere (`pim_design`) carry no such field, so the site seam is asked for
            # them the way their own builders ask it.
            payload = build()
            configured = payload.get("configured") if isinstance(payload, dict) else None
            if configured is None:
                configured = answers("site_hosting") if fid in ("design", "site") else True
            if fid != "home" and configured is False:
                why = _as_text(payload.get("why_not")) if isinstance(payload, dict) else ""
                not_shown.append({"tab": feature["label"],
                                  "why": why or "not configured for this instance"})
                continue
            panes.append({
                "id": fid, "label": feature["label"],
                "tool_id": design.tool_id if fid in ("design", "site") else self.tool_id,
                "panel_payload": payload,
            })
        if not_shown and panes and panes[0]["id"] == "home":
            # The work order the old rule kept on every dark tab, kept on the one tab
            # every instance has. Said as a table: which tab, and what would show it.
            home = panes[0]["panel_payload"]
            if isinstance(home, dict) and isinstance(home.get("panes"), list):
                home["panes"].append({"panel_payload": {
                    "schema": _SCHEMA, "container": "record_table", "title": "Not shown",
                    "columns": ["tab", "why"], "rows": not_shown,
                    "row_count": len(not_shown),
                    "count_label": f"{len(not_shown)} tab(s) not configured",
                    # THE CLIENT'S SENTENCE. This read "switched on for this instance
                    # and not configured yet … not drawn" — an operator's work order,
                    # on the first screen a client sees (F7, 2026-09-16). The rows'
                    # `why` cells were already the client's words; the notice was not.
                    "notice": ("These parts of your account are not set up yet. Each "
                               "row says what would turn it on."),
                }})

        drawn = [pane["id"] for pane in panes]
        active = _as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in drawn:
            # The default, and then whatever IS drawn. `home` is a feature like any other
            # and an instance may switch it off — which left `active_tab: "home"` naming a
            # tab this payload does not carry, so the shell opened on nothing. Harmless
            # while nothing could write a toggle; `set_pim_features.py` is now that
            # writer, so the unreachable case became a reachable one.
            active = DEFAULT_TAB if DEFAULT_TAB in drawn else (drawn[0] if drawn else "")
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "PIM",
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
        }


register(PimOverview())
