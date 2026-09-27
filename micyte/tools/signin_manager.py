"""Client sign-ins — the operator's surface for the accounts their clients log in with.

Replaces the legacy static dashboard's `grantees_operator.js` and `credentials_operator.js`
tabs, which were the operator's ONLY way to send a client a reset link, turn an account off,
set a password or create a sign-in. The dashboard is being retired; the routes those tabs
called are not, and this is their face.

## It builds nothing it can reach for

Every fact here arrives through `host_context`, because `micyte` holds no filesystem read
and no network client, and the two stores this question spans are both the host's: the
grantee leaflets say who the clients are, and Keycloak says what state each account is in.
Reaching Keycloak needs an authorization resolved from the live request's headers, which a
published-package tool has no way to build — the same reason `pim_design` is handed its
`port` rather than constructing one.

The reader is `fnd_app...signin_directory.read_signins`, which the operator's PROFILE page
also calls. That is deliberate and it is the point: the profile page lists the sign-ins and
this surface acts on them, and two readings of one realm is how one surface comes to offer a
reset against an account the other says does not exist.

## OPERATOR ONLY

Not by a flag this module sets — by the host declining to hand the directory to anybody
else. A caller the host has not recognised as the operator gets no reader, and this surface
then says so plainly instead of drawing an empty table. An empty table cannot tell "you may
not see this" from "there is nothing here", and only one of those is worth acting on.

## No password is in this payload

The vault route `/__fnd/admin/credentials` answers "and what is the password", behind its
own operator gate, on its own request — and it WITHHOLDS the value once the account is
`claimed`, because after the client changes their password the stored string opens nothing
and handing it to the operator is worse than handing them nothing. This surface carries
neither: not the live value, not the stale one. What it shows is whether a value is recorded
and whether it is still current, and the vault is the door to the value. A secret does not
ride in a page body, a proxy log, or a screenshot of this page.

## A button that cannot work is not offered

`POST /__fnd/admin/signin/reset` asks Keycloak to send the client its own reset link, and
Keycloak sends it to the address ON the account. For an account with an unverified address —
or no address at all — that call succeeds, sends nothing, and reports success. So the reset
form is drawn only where `reset email` reads `ready`; elsewhere its place is taken by the
reason, and by the thing that DOES work (setting a password here and handing it over). The
same principle as a tab that explains its missing environment factor rather than vanishing:
a control that disappears teaches nothing, and one that lies teaches something false.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.signin_manager.v1"

#: The routes this surface is a face for. They existed before it and are unchanged: the
#: legacy dashboard called exactly these.
SIGNIN_ROUTE = "/__fnd/admin/signin"
CREDENTIALS_ROUTE = "/__fnd/admin/credentials"

#: Its own query parameters — one per level, for `pim_design`'s reason: a nested surface
#: sharing its parent's parameter makes selecting here move the parent too.
TAB_QUERY = "signin_section"
ACCOUNT_QUERY = "signin_account"
GRANTEE_QUERY = "signin_grantee"
DEFAULT_TAB = "accounts"

#: What a row's `password` column says. Never a value — see the module docstring.
_VAULT_WORDS: dict[str, str] = {
    "unclaimed": "in the vault",
    "claimed": "the client changed it — the vault withholds",
    "unknown": "recorded, but not known to be current",
}


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def read_directory(host_context: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """``(directory, why_not)`` — the sign-in list this render may draw, or why it may not.

    The refusal is CARRIED rather than swallowed, exactly as `pim_design.site_port` carries
    the port's. A surface that rendered "no accounts" over a gate it did not pass would
    teach the reader that their realm is empty, and they would believe it.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("signin_accounts")
    if not callable(provider):
        return None, (
            "this portal did not offer the client sign-in directory to this render. It is "
            "handed only to a caller the host has recognised as the operator, so either "
            "this is not the operator's instance or the request carried no operator "
            "identity.")
    try:
        directory = provider()
    except Exception as exc:  # the host's own refusal, in the host's own words
        return None, str(exc)
    if not isinstance(directory, dict):
        return None, "the host answered with a shape this surface cannot read."
    if not directory.get("permitted", True):
        return None, _as_text(directory.get("why_not")) or (
            "this surface is the operator's, and this caller is not the operator.")
    return directory, ""


def _notice(title: str, text: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0,
            "count_label": "", "empty_text": text}


def _scoped(route: str, grantee_msn: str) -> str:
    """A write route with the grantee it acts on named IN THE ADDRESS.

    `_resolve_grantee_scope` reads `?grantee=` off the query string, not the body — so a
    form that posted the msn as a field would be answered `missing_grantee` no matter what
    it sent. The address is where the scope goes.
    """
    return f"{route}?{urlencode({'grantee': grantee_msn})}"


def _vault_word(account: dict[str, Any]) -> str:
    """What the `password` column says for one account. NEVER a value.

    `claim_state` is the vault route's own answer, resolved by the host through the same
    `signin_vault.claim_state` the route calls — so this column and the vault cannot
    disagree about whether a recorded string still opens the account.
    """
    if not account.get("password_recorded"):
        return "none recorded"
    return _VAULT_WORDS.get(_as_text(account.get("claim_state")), "recorded")


def _account_key(account: dict[str, Any]) -> str:
    """How a row is ADDRESSED in the query. The username, because it is what an operator
    reads off the table and what a link is worth sharing; the `user_id` the routes take is
    carried in the row rather than in the URL."""
    return account["username"]


def _directory_pane(directory: dict[str, Any]) -> dict[str, Any]:
    """Every account, and the way into one of them."""
    accounts = list(directory.get("accounts") or [])
    realm_read = bool(directory.get("realm_read"))
    rows = [{
        "client": account["grantee"],
        "username": account["username"],
        "site": account["domain"],
        "sign-in": account["sign_in"] or "—",
        "reset email": account["reset_email"] or "—",
        "password": _vault_word(account),
    } for account in accounts]
    ready = sum(1 for a in accounts if a["reset_email"] == "ready")
    off = sum(1 for a in accounts if a["sign_in"] == "OFF")
    notice = ""
    if not realm_read:
        # The realm could not be read. Say it once, loudly, because EVERY action below
        # depends on a `user_id` that only the realm carries — and a table of names with
        # no buttons under it reads as a surface that is broken rather than one that is
        # waiting.
        notice = (
            "Keycloak could not be read just now, so no account state is known and no "
            "action can be offered — the write routes take the realm's own user id, and "
            "nothing here has one. The clients listed are from the grantee leaflets.")
    elif off:
        notice = f"{off} sign-in{'' if off == 1 else 's'} disabled."
    return {
        "schema": _SCHEMA, "container": "record_table", "title": "Client sign-ins",
        "columns": ["client", "username", "site", "sign-in", "reset email", "password"],
        "rows": rows, "row_count": len(rows),
        "count_label": (
            f"{len(rows)} account{'' if len(rows) == 1 else 's'}"
            + (f" · {ready} can be sent a reset link" if realm_read else "")),
        "empty_text": (
            "No grantee leaflets resolved. That is a deployment fault rather than an empty "
            "realm — check MYCITE_GRANTEE_LEAFLETS / MYCITE_GRANTEE_ROOT."),
        "notice": notice,
        # Choosing a name and pressing Open is the same act as reading a username out of a
        # column and typing it into a form underneath, minus the transcription.
        "pick": {
            "label": "Open an account",
            "param": ACCOUNT_QUERY,
            "options": [{"value": _account_key(a),
                         "label": f"{a['grantee']} · {a['username']}"
                                  + ("" if a["sign_in"] != "OFF" else "  ·  disabled")}
                        for a in accounts if a["user_id"]],
            "go_label": "Open",
        } if any(a["user_id"] for a in accounts) else None,
    }


def _reset_pane(account: dict[str, Any]) -> dict[str, Any]:
    """Send the client Keycloak's own reset link — or say why that would send nothing.

    THE STATE IS LOAD-BEARING. Keycloak mails the reset link to the address on the account,
    so for `unverified` or `no address` the call returns 200 having delivered nothing. An
    operator who presses it and is told "Sent" stops chasing the problem, which is the worst
    outcome available here. So the form exists only where it works, and where it does not the
    reason stands in its place beside the thing that does.
    """
    state = account["reset_email"]
    if state == "ready":
        return {
            "schema": _SCHEMA, "container": "record_form",
            "title": "Send a password reset link",
            "fields": [],
            "submit_label": "Send the reset email",
            "submit_action": {
                "route": _scoped(f"{SIGNIN_ROUTE}/reset", account["grantee_msn"]),
                "success_label": "Sent",
                # `mode: email` is the route's default; sent explicitly so the request says
                # what it is asking for rather than relying on a default to stay put.
                "fixed": {"user_id": account["user_id"], "mode": "email"},
            },
        }
    if state == "unverified":
        why = (
            f"{account['email']} is on this account and nobody has confirmed it. Keycloak "
            "sends its reset link to that address, so pressing send would report success "
            "and deliver nothing. Set a password below and give it to them directly, or "
            "have them confirm the address first.")
    elif state == "no address":
        why = (
            "This account carries no email address, and Keycloak's reset link has nowhere "
            "to go — the call would report success and send nothing. Set a password below "
            "and give it to them directly.")
    else:
        why = (
            "The realm could not be read, so whether a reset email would arrive is unknown "
            "— and an action offered on an unknown is a guess with a button on it.")
    return _notice("Send a password reset link", why)


def _enable_pane(account: dict[str, Any]) -> dict[str, Any]:
    """Turn the sign-in on or off. One button, not a switch.

    A select reading "enabled / disabled" makes the operator work out which way it is
    currently set before deciding what to do; a button that names the act does not. Disabling
    goes behind the typed confirmation because it locks a client out of their own instance
    with no warning to them; enabling does not, because nothing is lost by it.
    """
    if account["enabled"] is None:
        return _notice(
            "Turn this sign-in off",
            "The realm could not be read, so whether this account is enabled is unknown. "
            "Nothing is offered against an unknown state.")
    if account["enabled"]:
        return {
            "schema": _SCHEMA, "container": "record_form",
            "title": "Turn this sign-in off",
            "fields": [],
            "submit_label": "Disable",
            "submit_action": {
                "route": _scoped(f"{SIGNIN_ROUTE}/toggle", account["grantee_msn"]),
                "danger": True, "success_label": "Disabled",
                "fixed": {"user_id": account["user_id"], "enabled": False},
                "confirm": {
                    "expect": account["username"], "key": "confirm",
                    "text": (
                        f"{account['grantee']} will be signed out of their instance and "
                        f"unable to sign back in. Their data is untouched and turning it "
                        f"back on is one press — but nobody tells them, so they find out "
                        f"by failing to log in."),
                },
            },
        }
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Turn this sign-in back on",
        "fields": [],
        "submit_label": "Enable",
        "submit_action": {
            "route": _scoped(f"{SIGNIN_ROUTE}/toggle", account["grantee_msn"]),
            "success_label": "Enabled",
            "fixed": {"user_id": account["user_id"], "enabled": True},
        },
    }


def _password_pane(account: dict[str, Any]) -> dict[str, Any]:
    """Set the password, in Keycloak and in the vault together.

    Behind the typed confirmation because it is IRREVERSIBLE in the way that matters:
    Keycloak stores hashes, so the password being replaced cannot be recovered, and a client
    signed in nowhere else finds out when their own password stops working.

    The value is NOT prefilled and no current value is shown. Leaving the field blank asks
    the route to generate one that satisfies the realm's policy; either way the password
    comes back in the route's own response, which is a reply to one request rather than a
    string sitting in this page's body.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Set a password",
        "fields": [
            {"key": "password", "label": "Password (leave blank to generate one)",
             "placeholder": "blank generates one that meets the realm's policy"},
            {"key": "temporary", "label": "What happens at their next sign-in",
             "type": "select", "value": "",
             "options": [
                 # The route reads `bool(body.get("temporary", False))`, so the FALSE
                 # option's value has to be a falsy string: `"no"` is truthy in Python and
                 # would force a password change while claiming not to.
                 {"value": "", "label": "Permanent — this is their password until they "
                                        "change it"},
                 {"value": "1", "label": "Temporary — Keycloak makes them choose a new one"},
             ]},
        ],
        "submit_label": "Set the password",
        "submit_action": {
            "route": _scoped(f"{CREDENTIALS_ROUTE}/set", account["grantee_msn"]),
            "danger": True, "success_label": "Set",
            "fixed": {"user_id": account["user_id"]},
            "confirm": {
                "expect": account["username"], "key": "confirm",
                "text": (
                    f"This replaces the password on {account['username']} in Keycloak and "
                    f"records the new one in the vault. Keycloak stores hashes, so whatever "
                    f"is on the account now cannot be recovered — if {account['grantee']} "
                    f"chose it themselves, they are locked out until you hand them the new "
                    f"one."),
            },
        },
    }


def _forget_pane(account: dict[str, Any]) -> dict[str, Any]:
    """Drop the recorded password from the vault, leaving the account untouched.

    Confirmed because the vault is the only place a viewable password exists — Keycloak
    stores hashes — so forgetting one is the end of it. The account keeps working; what is
    lost is the operator's ability to read the value back.
    """
    if not account.get("password_recorded"):
        return _notice(
            "Forget the recorded password",
            "Nothing is recorded for this account, so there is nothing to forget. A value "
            "lands in the vault when a password is set or generated here.")
    when = account.get("password_set_at") or "an unrecorded date"
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Forget the recorded password",
        "fields": [],
        "submit_label": "Forget it",
        "submit_action": {
            "route": f"{CREDENTIALS_ROUTE}/forget",
            "danger": True, "success_label": "Forgotten",
            "fixed": {"user_id": account["user_id"]},
            "confirm": {
                "expect": account["username"], "key": "confirm",
                "text": (
                    f"The value recorded on {when} is deleted from the vault. The sign-in "
                    f"itself is untouched and {account['grantee']} keeps using it — what "
                    f"ends is your ability to read the password back, because Keycloak "
                    f"stores only hashes and the vault is the one place a readable value "
                    f"lives."),
            },
        },
    }


def _account_pane(account: dict[str, Any]) -> dict[str, Any]:
    """ONE account, opened: what state it is in, and the four things that can be done to it."""
    facts = {
        "schema": _SCHEMA, "container": "record_table",
        "title": f"{account['grantee']} · {account['username']}",
        "columns": ["fact", "value"],
        "rows": [
            {"fact": "client", "value": account["grantee"]},
            {"fact": "username", "value": account["username"]},
            {"fact": "site", "value": account["domain"] or "—"},
            {"fact": "email on the account", "value": account["email"] or "— none —"},
            {"fact": "address confirmed",
             "value": "yes" if account["email_verified"] else "no"},
            {"fact": "sign-in", "value": account["sign_in"] or "unknown"},
            {"fact": "reset email", "value": account["reset_email"] or "unknown"},
            # The password COLUMN, never the password. See the module docstring.
            {"fact": "password", "value": _vault_word(account)},
            {"fact": "role",
             "value": "a second account for a separate role" if not account["from_leaflet"]
                      else "this client's own sign-in"},
        ],
        "row_count": 9,
        "count_label": account["sign_in"] or "state unknown",
        "notice": (
            "The password itself is not shown here or anywhere in this page. The "
            f"credential vault ({CREDENTIALS_ROUTE}) answers that on its own request, and "
            "withholds the recorded value once the client has changed their own — a stale "
            "string hands you something that opens nothing."),
        # Clearing the parameter IS the way back to the list.
        "back": {"label": "All sign-ins", "param": ACCOUNT_QUERY, "value": ""},
    }
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": facts},
                      {"panel_payload": _reset_pane(account)},
                      {"panel_payload": _enable_pane(account)},
                      {"panel_payload": _password_pane(account)},
                      {"panel_payload": _forget_pane(account)}]}


def _accounts_tab(directory: dict[str, Any], why_not: str, *,
                  open_account: str = "") -> dict[str, Any]:
    """The list, or one account from it — the two-state shape the profile page uses."""
    if directory is None:
        return _notice("Client sign-ins", why_not)
    accounts = list(directory.get("accounts") or [])
    if open_account:
        chosen = next((a for a in accounts if _account_key(a) == open_account), None)
        if chosen is not None and chosen["user_id"]:
            return _account_pane(chosen)
        # A stale link — the account was deleted, or the realm went unreadable between the
        # link being made and being followed. Say so over the list rather than drawing an
        # empty pane that reads as a fault.
        pane = _directory_pane(directory)
        pane["notice"] = (
            f"No account named {open_account!r} can be acted on right now — it may have "
            "been removed, or the realm may be unreadable. Here is what the directory "
            "answers now." + (f" {pane['notice']}" if pane.get("notice") else ""))
        return pane
    return _directory_pane(directory)


def _create_tab(directory: dict[str, Any], why_not: str, *,
                grantee_msn: str = "") -> dict[str, Any]:
    """Create a sign-in — which is per CLIENT, so the client is chosen before the form.

    The scope rides in the route's query string (`_scoped`), and a form cannot rewrite its
    own address from a field. So the client is picked first and the form is drawn against
    that choice, which also means the operator can see whose account they are about to
    create rather than trusting a dropdown they set three fields ago.
    """
    if directory is None:
        return _notice("New sign-in", why_not)
    accounts = list(directory.get("accounts") or [])
    clients: dict[str, str] = {}
    for account in accounts:
        if account["grantee_msn"]:
            clients.setdefault(account["grantee_msn"], account["grantee"])
    picker = {
        "schema": _SCHEMA, "container": "record_table", "title": "New sign-in",
        "columns": ["client", "site", "accounts"],
        "rows": [{
            "client": label,
            "site": next((a["domain"] for a in accounts if a["grantee_msn"] == msn), ""),
            "accounts": str(sum(1 for a in accounts if a["grantee_msn"] == msn)),
        } for msn, label in clients.items()],
        "row_count": len(clients),
        "count_label": f"{len(clients)} client{'' if len(clients) == 1 else 's'}",
        "empty_text": "No client resolved, so there is nobody to create a sign-in for.",
        "notice": (
            "A sign-in belongs to one client's Keycloak group. Choose the client, then the "
            "form below is addressed to them."),
        "pick": {
            "label": "Create a sign-in for",
            "param": GRANTEE_QUERY,
            "options": [{"value": msn, "label": label} for msn, label in clients.items()],
            "go_label": "Choose",
        } if clients else None,
    }
    if not grantee_msn or grantee_msn not in clients:
        return picker
    label = clients[grantee_msn]
    form = {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"New sign-in for {label}",
        "fields": [
            # USERNAME is the direct route and the operator's stated rule (2026-08-24):
            # "all log in information should be username and password based, rather than a
            # provided email or even a personal email". The group prefix is added by the
            # route, so what is typed here is the part after it.
            {"key": "username", "label": "Username (the client's group prefix is added)",
             "placeholder": "finance"},
            # An address supplied here is recorded as a CONTACT address, not as the
            # identity — and it is what decides whether a reset email will ever be
            # sendable for this account.
            {"key": "email", "label": "Email (optional — a contact address, not the login)",
             "placeholder": "someone@example.org"},
        ],
        "submit_label": "Create the sign-in",
        "submit_action": {
            "route": _scoped(f"{SIGNIN_ROUTE}/create", grantee_msn),
            "success_label": "Created",
        },
    }
    picker["back"] = {"label": "All clients", "param": GRANTEE_QUERY, "value": ""}
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": picker}, {"panel_payload": form}]}


class SigninManager:
    """The operator's client sign-ins, with the actions on them."""

    tool_id = "signin_manager"
    label = "Client sign-ins"
    summary = (
        "Every account a client signs in with, and the acts on it: send Keycloak's own "
        "reset link, turn a sign-in off, set a password, forget a recorded one, create a "
        "sign-in. The operator's alone — the host hands the directory to nobody else — and "
        "no password is in what it draws."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    #: Launched by ADDRESS from the operator's profile page, not offered for a document in
    #: focus — nothing here is in the store at all.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: The whole subject arrives through the host. See the module docstring.
    wants_host_context = True
    # No `writes`: nothing here writes a datum row. Every act posts to an operator-gated
    # FND route that talks to Keycloak and the credential vault, governed by the operator
    # gate and the grantee scope rather than by `datum_write_policy`.

    def build_panel_payload(
        self, *, authority_db_file: Path | None = None, sandbox_id: str = "",
        document_id: str = "", datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del authority_db_file, document_id, datum_address
        query = dict(extra_query or {})
        directory, why_not = read_directory(host_context)
        panes = [
            {"id": "accounts", "label": "Sign-ins", "tool_id": "signin_manager_accounts",
             "panel_payload": _accounts_tab(
                 directory, why_not, open_account=_as_text(query.get(ACCOUNT_QUERY)))},
            {"id": "create", "label": "New sign-in", "tool_id": "signin_manager_create",
             "panel_payload": _create_tab(
                 directory, why_not, grantee_msn=_as_text(query.get(GRANTEE_QUERY)))},
        ]
        active = _as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in [pane["id"] for pane in panes]:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": self.label,
            "sandbox_id": _as_text(sandbox_id),
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
            # STATED, so a reader of the payload (and a test) can tell "the operator saw an
            # empty realm" from "this caller was refused" without parsing prose.
            "permitted": directory is not None,
        }


register(SigninManager())

__all__ = ["ACCOUNT_QUERY", "CREDENTIALS_ROUTE", "DEFAULT_TAB", "GRANTEE_QUERY",
           "SIGNIN_ROUTE", "TAB_QUERY", "SigninManager", "read_directory"]
