"""Mailboxes — the ADDRESSES an instance holds, and the five acts that change them.

The operator's surface for the mailbox administration `email_provider` declared on
2026-08-28. Six operations were named there and an adapter implemented all six; only the
read (`alias.list`) had anywhere to be called from. `alias.create`, `alias.remove`,
`forwarding.set`, `identity.verify_request` and `identity.remind` were built, tested,
governable — and had **no grant in any config and no non-test caller anywhere**. A
capability nobody can reach is indistinguishable from one nobody built, except that it
costs the same to maintain.

## Whose surface this is

THE OPERATOR'S, and that is the whole reason it is a separate tool rather than five forms
added to PIM's Email tab. `pim_overview`'s own docstring states the client's side of it:
PIM employs `mailbox.list`, `message.fetch` and `alias.list` and nothing else, "so there is
no grant an operator could write that would let this tab change or send anything". That
constraint is the operator's standing rule, not an omission to tidy up — so the writes get
their own surface, behind their own door, and PIM's tab is untouched.

## It reaches nothing by itself

`micyte` holds no AWS client and no profile store. The port ARRIVES: the host resolves the
binding for the instance being rendered, reads the credential, closes an `authorize` over
the request and hands the adapter over as host context. This module talks to whatever it
is given through the Protocol and nothing else.

The READ is `list_aliases`, which is `_alias_rows` — the same function the legacy email
dashboard's own listing calls. A second reader here would be a second answer to "how far
has this address got through send-as", free to disagree with the one the dashboard shows.

## Nothing fires as a side effect of anything

Five acts, five forms, five separately grantable operations. `identity.verify_request` and
`identity.remind` SEND MAIL to a real person, so they are their own buttons with their own
confirmations and are never performed on the way to something else — the same rule the
Inbox pane keeps between triaging and replying. Adding an address does not send its owner
anything; the setup email is the button below it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.mailbox_admin.v1"

#: The port this tool is a view of. Named once; the host answers for it.
PORT_ID = "email_provider"

#: Where the five writes are posted. THE OPERATOR'S DOOR, and the only one — no client
#: vhost proxies `/portal/api/`, and none should: a client's PIM stays read-only, which is
#: why `_repoint_client_forms` rewrites the site routes and deliberately not these.
#:
#: Named here and nowhere else in MiCyte; the host registers exactly these five words, and
#: a test compares the two so a rename cannot half-happen.
ROUTE = "/portal/api/v2/mailbox"

#: One word per operation, in the order the route reads them.
ACTION_CREATE = "create"
ACTION_FORWARDING = "forwarding"
ACTION_REMOVE = "remove"
ACTION_VERIFY_REQUEST = "verify-request"
ACTION_REMIND = "remind"

#: Every action this surface can post. The host's route must know exactly these.
ACTIONS: tuple[str, ...] = (
    ACTION_CREATE, ACTION_FORWARDING, ACTION_REMOVE,
    ACTION_VERIFY_REQUEST, ACTION_REMIND,
)

#: The two that put words in somebody's inbox. Kept as a set rather than a comment so the
#: surface and its tests read the same list — a label that says "sends mail" is the only
#: warning an operator gets before it does.
SENDS_MAIL: frozenset[str] = frozenset({ACTION_VERIFY_REQUEST, ACTION_REMIND})
#: THE CLIENT'S THREE (operator, 2026-09-10): "the email tab should be properly configured
#: for a user to edit emails or re run the verifications to be sent for authorization /
#: adding an email to their Gmail". A client changes where their own address forwards and
#: re-sends the send-as setup (or a reminder) to its owner; they neither add an address
#: nor delete one — those stay the operator's, because they change what exists on a domain
#: FND answers for. PIM's Email tab composes exactly these forms (`client_address_forms`)
#: and the host serves them behind the client's own door; the create and remove forms are
#: never built for a client, and the client door refuses those two words outright.
CLIENT_ACTIONS: tuple[str, ...] = (ACTION_FORWARDING, ACTION_VERIFY_REQUEST, ACTION_REMIND)

#: The acts that must be TYPED to happen: every one but `create`. Named here and read by
#: the route, so the modal and the door cannot come to disagree about which acts are
#: gated — the modal is a courtesy to a person and the route is reachable without one.
#:
#: `create` is absent deliberately. Nothing existing changes, nobody is written to, and an
#: address added by mistake is removed by the form below it; gating it the same way as a
#: delete would teach an operator to type through confirmations.
CONFIRMED_ACTIONS: frozenset[str] = frozenset(
    {ACTION_FORWARDING, ACTION_REMOVE, ACTION_VERIFY_REQUEST, ACTION_REMIND})

#: Which domain's addresses are being shown. Its OWN parameter, like every nested hub
#: here: sharing the parent's would move the parent when a domain is picked.
DOMAIN_QUERY = "mailbox_domain"

#: And which address within it is open. The value is the WHOLE address, `local@domain`,
#: because the tabs share this parameter and a bare local part would open `info@` on
#: whichever domain the reader happened to be on.
ADDRESS_QUERY = "mailbox_address"

#: Said on the pane, not only in a docstring. An operator pressing a button should be able
#: to see from the screen which of them reaches a person.
SENDS_MAIL_NOTE = (
    "Two of the actions on an open address SEND AN EMAIL to the person behind it: "
    "“Send the setup email” and “Send a reminder”. Nothing else here does — adding an "
    "address, changing where it forwards and deleting it are all silent."
)


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def mail_port(host_context: dict[str, Any] | None) -> tuple[Any, str]:
    """``(adapter, why_not)`` — the mail seam this render may use, or why it may not.

    The refusal is CARRIED, not swallowed, for `pim_design.site_port`'s reason: a table
    that renders empty over a binding nobody granted teaches an operator that the instance
    has no addresses, and they will believe it.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("port")
    if not callable(provider):
        return None, (
            "this portal did not offer a port to this render, so the mailboxes cannot be "
            "reached from here")
    try:
        port = provider(PORT_ID)
    except Exception as exc:  # the host's own refusal, in the host's own words
        return None, str(exc)
    if port is None:
        return None, (
            "no extension is connected to the Email port on this instance. Select one on "
            "Utilities > Ports, configure its credential, then write its grant.")
    if not hasattr(port, "list_aliases"):
        # A fill may implement the mail and not the mailboxes — `site_hosting` already has
        # operations no adapter offers. Said plainly rather than shown as an empty table.
        return None, (
            "the extension connected to the Email port on this instance does not "
            "administer addresses, only the mail in them.")
    return port, ""


def _notice(title: str, text: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0,
            "count_label": "", "empty_text": text}


def _domains(port: Any, rows: list[dict[str, str]]) -> tuple[str, ...]:
    """Every domain this binding holds, ADDRESSES OR NOT.

    Asked of the adapter first and derived from the rows only as a fallback, because a
    domain with no address yet is exactly the one an operator is here to put the first
    address on — and deriving the list from the rows would hide it at the moment it is
    needed. `held_domains` is optional on a fill for `list_subtopics`' reason: an adapter
    that does not offer it still yields a usable surface, one domain narrower.
    """
    held = getattr(port, "held_domains", None)
    if callable(held):
        try:
            return tuple(_as_text(d) for d in held() if _as_text(d))
        except Exception:
            pass
    seen: list[str] = []
    for row in rows:
        domain = _as_text(row.get("domain")) or _as_text(row.get("send_as")).rpartition("@")[2]
        if domain and domain not in seen:
            seen.append(domain)
    return tuple(seen)


def _domain_of(row: dict[str, str]) -> str:
    """Which domain a listing row is on.

    `_alias_rows` carries it since 2026-08-29. The fallback reads it off `send_as`, which
    is `local@domain` — kept because a fill that predates the key would otherwise put
    every address under no domain at all, which is not a truer answer than a guessed one.
    """
    return _as_text(row.get("domain")) or _as_text(row.get("send_as")).rpartition("@")[2]


def _address_of(row: dict[str, str], *, domain: str) -> str:
    return _as_text(row.get("send_as")) or f"{_as_text(row.get('local_part'))}@{domain}"


def _table(rows: list[dict[str, str]], *, domain: str, open_address: str) -> dict[str, Any]:
    """The addresses on one domain, and the way into one of them.

    The `pick` control is what makes this a list rather than a printout: a record_table
    draws every cell as escaped text, so there is no clickable row — without it the only
    way to act on an address would be to read it out of a column and retype it into a
    form underneath.
    """
    drawn = [{
        "address": _address_of(row, domain=domain),
        "forwards to": _as_text(row.get("forward_to")) or "—",
        # The ROLE decides whether the delete is even offered: only a profile tagged
        # `user` is removable, and the adapter refuses the rest. Shown so a refusal is
        # legible before it happens rather than after.
        "role": _as_text(row.get("role")) or "—",
        "send-as": (_as_text(row.get("send_as_label"))
                    or _as_text(row.get("send_as_stage")) or "not_started"),
    } for row in rows]
    verified = sum(1 for row in drawn
                   if _as_text(row["send-as"]).lower().startswith("verif"))
    pane: dict[str, Any] = {
        "schema": _SCHEMA, "container": "record_table", "title": f"Addresses on {domain}",
        "columns": ["address", "forwards to", "role", "send-as"],
        "rows": drawn, "row_count": len(drawn),
        "count_label": (f"{len(drawn)} address(es) · {verified} verified"
                        if drawn else "no addresses"),
        "notice": SENDS_MAIL_NOTE,
        "empty_text": (
            f"No address exists on {domain} yet. The form below adds the first one."),
    }
    if drawn:
        pane["pick"] = {
            "label": "Open an address",
            "param": ADDRESS_QUERY,
            "options": [{"value": row["address"],
                         "label": f"{row['address']}  ·  {row['send-as']}"}
                        for row in drawn],
            "go_label": "Open",
        }
    if open_address:
        # Clearing the parameter IS the return, the same way the Posts gallery comes back.
        pane["back"] = {"label": "All addresses", "param": ADDRESS_QUERY, "value": ""}
    return pane


def _create_form(*, domain: str, domains: tuple[str, ...],
                 sandbox: str) -> dict[str, Any]:
    """Add an address. The one act here that carries no typed confirmation.

    It is not destructive and it is not a send: nothing existing changes, nobody is
    written to, and an address created by mistake is removed by the form below. Gating it
    the same way as a delete would teach an operator to type through confirmations.
    """
    # A SELECT when the binding's domains are known, a text field when they are not. The
    # binding fences which domains it may act on and refuses the rest in its own words, so
    # this is a typo guard rather than the fence.
    domain_field: dict[str, Any] = {
        "key": "domain", "label": "Domain", "value": domain,
        "placeholder": ", ".join(domains) or "the domain this connection holds",
    }
    if domains:
        domain_field["type"] = "select"
        domain_field["options"] = [{"value": d, "label": d} for d in domains]
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Add an address",
        "fields": [
            domain_field,
            {"key": "local_part", "label": "The part before the @",
             "placeholder": "info"},
            {"key": "forward_to", "label": "Where its mail should go",
             "placeholder": "someone@example.com"},
        ],
        "submit_label": "Add this address (sends no email)",
        "submit_action": {
            "route": f"{ROUTE}/{ACTION_CREATE}", "sandbox_id": sandbox,
            "success_label": "Added",
        },
    }


def _address_forms(row: dict[str, str], *, domain: str,
                   sandbox: str) -> list[dict[str, Any]]:
    """The four acts on ONE address, each its own form, each its own permission.

    Separated because they carry different weight and different grants: redirecting
    correspondence that is already flowing is not the risk of adding an address nobody
    knows yet, and two of these put a message in a person's inbox. One button doing two of
    them would collapse permissions an operator wrote down separately.
    """
    address = _address_of(row, domain=domain)
    local = _as_text(row.get("local_part")) or address.partition("@")[0]
    forwards = _as_text(row.get("forward_to"))
    fixed = {"domain": domain, "local_part": local}
    stage = _as_text(row.get("send_as_label")) or _as_text(row.get("send_as_stage"))
    # WHO the two sending actions write to. Named once: a confirmation that says "the
    # owner" and a button that names an address would be describing the same person two
    # ways, and the operator would have to trust that they matched.
    recipient = forwards or "the address behind this mailbox"

    facts = {
        "schema": _SCHEMA, "container": "record_table", "title": address,
        "columns": ["fact", "value"],
        "rows": [
            {"fact": "forwards to", "value": forwards or "—"},
            {"fact": "role", "value": _as_text(row.get("role")) or "—"},
            {"fact": "send-as", "value": stage or "not_started"},
            {"fact": "profile", "value": _as_text(row.get("profile_id")) or "—"},
        ],
        "row_count": 4,
        "count_label": stage or "not_started",
        "back": {"label": "All addresses", "param": ADDRESS_QUERY, "value": ""},
    }

    forwarding = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Change where it forwards",
        "fields": [{"key": "forward_to", "label": "Where its mail should go from now on",
                    "value": forwards}],
        "submit_label": "Change forwarding (sends no email)",
        "submit_action": {
            "route": f"{ROUTE}/{ACTION_FORWARDING}", "sandbox_id": sandbox,
            "success_label": "Changed", "danger": True, "fixed": dict(fixed),
            "confirm": {
                "expect": address, "key": "confirm",
                "text": (
                    f"Mail written to {address} stops arriving at "
                    f"{forwards or 'its current destination'} and goes to whatever is "
                    "typed above instead. Nobody is told — the sender sees nothing "
                    f"different. Type {address} to confirm."),
            },
        },
    }

    verify = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Send the setup email",
        "fields": [],
        # The button SAYS what pressing it does. "Request verification" is a phrase that
        # could mean a status check; this one cannot be misread.
        "submit_label": f"SEND AN EMAIL to {recipient}",
        "submit_action": {
            "route": f"{ROUTE}/{ACTION_VERIFY_REQUEST}", "sandbox_id": sandbox,
            "success_label": "Sent", "fixed": dict(fixed),
            "confirm": {
                "expect": address, "key": "confirm",
                "text": (
                    f"THIS SENDS AN EMAIL to {recipient} — a real message to a real "
                    f"person, asking them to confirm they may send as {address}. It is "
                    "not a status check and it cannot be recalled. "
                    f"Type {address} to confirm."),
            },
        },
    }

    remind = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Send a reminder",
        "fields": [],
        "submit_label": f"SEND A SECOND EMAIL to {recipient}",
        "submit_action": {
            "route": f"{ROUTE}/{ACTION_REMIND}", "sandbox_id": sandbox,
            "success_label": "Sent", "fixed": dict(fixed),
            "confirm": {
                "expect": address, "key": "confirm",
                "text": (
                    f"THIS SENDS ANOTHER EMAIL to {recipient}, nudging them to finish "
                    "the setup they were already asked to do. The mail routes refuse a "
                    "second reminder within 24 hours, and that refusal comes back here. "
                    f"Type {address} to confirm."),
            },
        },
    }

    remove = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Delete this address",
        "fields": [],
        "submit_label": "Delete permanently (sends no email)",
        "submit_action": {
            "route": f"{ROUTE}/{ACTION_REMOVE}", "sandbox_id": sandbox,
            "success_label": "Deleted", "danger": True, "fixed": dict(fixed),
            "confirm": {
                "expect": address, "key": "confirm",
                "text": (
                    f"{address} stops existing and the forwarder map is rebuilt without "
                    "it, so mail sent to it bounces. Anything already delivered stays in "
                    "the mail store; nothing else about this is reversible. To keep the "
                    "address and only change where it goes, use “Change where it "
                    f"forwards”. Type {address} to confirm."),
            },
        },
    }

    return [facts, forwarding, verify, remind, remove]


def client_address_forms(row: dict[str, str], *, domain: str,
                         sandbox: str) -> list[dict[str, Any]]:
    """The facts and the CLIENT's three acts on one address — the same forms the
    operator's surface builds, minus the two that add or remove an address.

    One builder, not a second copy: the confirmation texts, the "SENDS AN EMAIL" labels
    and the routes are the ones the operator reads, so a client and the operator cannot
    be told two different things about what a button does. The routes name the
    operator's door; the host repoints them to the client's (`_repoint_client_forms`).
    """
    facts, forwarding, verify, remind, _remove = _address_forms(
        row, domain=domain, sandbox=sandbox)
    return [facts, forwarding, verify, remind]


class MailboxAdmin:
    """The operator's view of an instance's addresses, and the five acts on them."""

    tool_id = "mailbox_admin"
    label = "Mailboxes"
    summary = (
        "The addresses an instance holds: which exist on each domain it keeps, where each "
        "forwards, and how far each has got through send-as confirmation — with the five "
        "administrative acts behind the operator's own door."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    #: Launched by ADDRESS, never offered for a document in focus: what it shows is not in
    #: the store at all.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: The host resolves the binding and hands the seam over. See the module docstring.
    wants_host_context = True
    # No `writes`: nothing here writes a datum row. What the five acts change is a profile
    # store and a Lambda's forward map, through a port, governed by an external-call grant
    # rather than by `datum_write_policy`.

    def build_panel_payload(
        self, *, authority_db_file: Path | None = None, sandbox_id: str = "",
        document_id: str = "", datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del authority_db_file, document_id, datum_address
        query = dict(extra_query or {})
        sandbox = _as_text(sandbox_id)
        port, why_not = mail_port(host_context)
        if port is None:
            return _notice(self.label, why_not)
        try:
            rows = [dict(row) for row in port.list_aliases()]
        except Exception as exc:
            # The seam's own refusal — "may not 'alias.list'" is a permission answer, and
            # flattening it to an empty table would report it as having no addresses.
            return _notice(self.label, str(exc))

        domains = _domains(port, rows)
        if not domains:
            return _notice(
                self.label,
                "this mail connection holds no domain, so there is no address space to "
                "administer. The credential's `domain` is what names it.")

        open_address = _as_text(query.get(ADDRESS_QUERY))
        active = _as_text(query.get(DOMAIN_QUERY))
        if active not in domains:
            # A saved link to a domain this binding no longer holds opens the first one
            # rather than an empty pane that reads like a fault.
            active = (open_address.rpartition("@")[2]
                      if open_address.rpartition("@")[2] in domains else domains[0])

        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": self.label,
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": DOMAIN_QUERY,
            "tabs": [
                {"id": domain, "label": domain,
                 "tool_id": f"mailbox_admin_domain_{index}",
                 "panel_payload": self._domain_pane(
                     rows, domain=domain, sandbox=sandbox,
                     domains=domains, open_address=open_address)}
                for index, domain in enumerate(domains)
            ],
        }

    def _domain_pane(self, rows: list[dict[str, str]], *, domain: str, sandbox: str,
                     domains: tuple[str, ...], open_address: str) -> dict[str, Any]:
        """One domain: its addresses, then either the open one's acts or the add form.

        Two states behind one tab, the same shape the Posts gallery uses: the list until
        something is chosen, then that thing with a way back. The add form is not drawn
        beside an open address — the question "which address" is already answered, and a
        second form asking it again is how the wrong one gets typed.
        """
        mine = [row for row in rows if _domain_of(row) == domain]
        panes: list[dict[str, Any]] = [
            {"panel_payload": _table(mine, domain=domain, open_address=open_address)}]
        chosen = next((row for row in mine
                       if _address_of(row, domain=domain) == open_address), None)
        if chosen is not None:
            panes += [{"panel_payload": pane}
                      for pane in _address_forms(chosen, domain=domain, sandbox=sandbox)]
        else:
            panes.append({"panel_payload": _create_form(
                domain=domain, domains=domains, sandbox=sandbox)})
        return {"schema": _SCHEMA, "container": "composite", "direction": "column",
                "panes": panes}


register(MailboxAdmin())

__all__ = [
    "ACTIONS",
    "ACTION_CREATE",
    "ACTION_FORWARDING",
    "ACTION_REMIND",
    "ACTION_REMOVE",
    "ACTION_VERIFY_REQUEST",
    "ADDRESS_QUERY",
    "CONFIRMED_ACTIONS",
    "DOMAIN_QUERY",
    "PORT_ID",
    "ROUTE",
    "SENDS_MAIL",
    "SENDS_MAIL_NOTE",
    "MailboxAdmin",
    "mail_port",
]
