"""GRANTOR — the closed channel FND serves its clients through (operator, 2026-08-21).

    "Actual channels can be thought of as the serving up of a sandbox isolated
    application, provided by the host, accessible under the authority and identity
    provided by the contract and payload alias."

Grantor is that, for the hosting relationship itself. The sandbox holds the channel's
books: an ``accounts`` roster (one ``channel_account`` row per client grantee — a place
exists before anyone takes it up) and one SERVICE document per grantee, named
``grantee-<msn>``, whose rows are (service, state) in the roster's own field vocabulary
— msn names the alias holder, title the service, lcl_id the state node the channel
mints (``enabled`` / ``disabled`` / ``locked_enabled``), utc the stamp.

Two postures from ONE builder:

* **admin** (the operator's, the default in the authenticated portal — the closed-
  channel session route is operator-only there): a gallery of grantee alias cards and a
  TOLLING tab reading the operator's existing tolling invoices. Selecting a card drills
  into that grantee's view; the admin can back out. Email is LOCKED-enabled for now.
* **grantee** (the drill-in today; a contract-admitted alias session later): the alias
  profile line + the service document — toggles drawn from data, the Email row locked
  on, and the API key block: the key a grantee copies to link the FND email extension
  as a usable port. The convention this establishes: a port is an extension you add,
  enabled by a key you hold.

File posture (the agnet precedent — a channel may read the host files that live beside
its store): tolling invoices under ``<db_parent>/utilities/tools/tolling/`` and service
keys under ``<db_parent>/utilities/tools/fnd_service/keys/``. Absent files are stated,
never invented. Payment execution, storage quotas, per-alias extra tabs and the remote
alias session stay recorded deferrals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from micyte.core.document_naming import CanonicalNameError, parse_canonical_document_id

from . import register

CHANNEL_ID = "grantor"
SANDBOX = "grantor"
CONTAINER = "grantor_session"
SESSION_SCHEMA = "mycite.v2.channel.grantor.session.v1"
TABS = ("grantees", "tolling")
DEFAULT_TAB = "grantees"

#: The service rows a grantee document carries today, and how each may move.
#: ``locked`` means the toggle is drawn but refuses — the state is FND's for now.
SERVICES = (
    {"service": "email", "label": "Email", "locked": True,
     "note": "Locked enabled — expose the API key below to link the FND email "
             "extension as a usable port."},
    {"service": "storage", "label": "Cloud storage", "locked": True,
     "note": "Eventual — adjusting space is not provisioned yet."},
)

_TENANT = "fnd"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decode(value: object) -> str:
    from micyte.core.datum_ops.datum_resolve import decode_label

    try:
        return decode_label(_as_text(value)) or _as_text(value)
    except Exception:
        return _as_text(value)


def _pairs(row: Any) -> dict[str, str]:
    """``marker -> value`` from a row's head cells."""
    raw = getattr(row, "raw", None) or []
    head = raw[0] if raw else []
    out: dict[str, str] = {}
    for index in range(1, len(head) - 1, 2):
        marker = _as_text(head[index])
        if marker.startswith("rf."):
            out[marker] = _as_text(head[index + 1])
    return out


def _markers() -> dict[str, str]:
    from micyte.core.datum_ops import field_registry as fr

    namespace = fr.namespace_for_sandbox(SANDBOX)
    return {
        field: "rf." + fr.address(namespace, field)
        for field in ("msn_id", "title", "lcl_id", "utc")
    }


def _grantor_documents(authority_db_file: Path) -> dict[str, Any]:
    """name -> FULL document, for every document the grantor sandbox holds.

    The index names them; each is read individually (they are all small) rather
    than through the whole-catalog parse the agnet session still pays for.
    """
    from micyte.adapters.sql import open_mos_store
    from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest

    store = open_mos_store(Path(authority_db_file), cache=True)
    index = store.read_document_index(
        AuthoritativeDatumDocumentRequest(tenant_id=_TENANT))
    out: dict[str, Any] = {}
    for entry in index.documents:
        document_id = _as_text(getattr(entry, "document_id", ""))
        try:
            parsed = parse_canonical_document_id(document_id)
        except CanonicalNameError:
            continue
        if parsed.sandbox != SANDBOX:
            continue
        document = store.read_authoritative_document(
            tenant_id=_TENANT, document_id=document_id)
        if document is not None:
            out[parsed.name] = document
    return out


def _state_labels(documents: dict[str, Any]) -> dict[str, str]:
    """lcl node -> label, from the channel's own local domain DEFINITION rows.

    A definition row's FIRST pair carries the node (TYPE-marked ``rf.3-1-1``, or the
    lcl_id marker in the legacy instance-marked shape) and the title rides its own
    pair. Read positionally, never through a marker->value dict: a tree row carries
    ``rf.3-1-1`` twice (node first, icon ref second) and a dict keeps the icon.
    """
    markers = _markers()
    node_markers = {"rf.3-1-1", markers["lcl_id"]}
    labels: dict[str, str] = {}
    for name in ("lcl_domain", "lcl"):
        document = documents.get(name)
        if document is None:
            continue
        for row in getattr(document, "rows", ()) or ():
            head = (getattr(row, "raw", None) or [[]])[0]
            if len(head) < 3 or _as_text(head[1]) not in node_markers:
                continue
            node = _as_text(head[2])
            title = ""
            for index in range(3, len(head) - 1, 2):
                if _as_text(head[index]) == markers["title"]:
                    title = _decode(head[index + 1])
                    break
            if node and title:
                labels.setdefault(node, title)
    return labels


def _roster(documents: dict[str, Any], states: dict[str, str]) -> list[dict[str, Any]]:
    markers = _markers()
    rows: list[dict[str, Any]] = []
    accounts = documents.get("accounts")
    for row in getattr(accounts, "rows", ()) or () if accounts is not None else ():
        pairs = _pairs(row)
        msn = pairs.get(markers["msn_id"], "")
        if not msn:
            continue
        state_node = pairs.get(markers["lcl_id"], "")
        rows.append(
            {
                "msn": msn,
                "title": _decode(pairs.get(markers["title"], "")) or msn,
                "state": states.get(state_node, state_node),
                "service_document": f"grantee-{msn}",
                "has_service_document": f"grantee-{msn}" in documents,
            }
        )
    return rows


def _instrument_state_nodes(states: dict[str, str]) -> dict[str, str]:
    """``lcl node -> state label`` for the instrument-state branch, from the definition
    labels already read. ``{}`` on a tree minted before the branch existed.

    The BRANCH is what tells an instrument row from a service row in one grantee document
    — both are `channel_account` rows — and it is found by LABEL, the way every branch
    on a canonical tree is (`grantor_books.INSTRUMENT_STATE_LABEL`).
    """
    branch = next((node for node, label in states.items()
                   if label.strip().lower() == "instrument_state"), "")
    if not branch:
        return {}
    return {node: label.strip().lower() for node, label in states.items()
            if node.rsplit("-", 1)[0] == branch and node != branch}


def _instrument(documents: dict[str, Any], *, msn: str, states: dict[str, str]) -> dict[str, Any]:
    """The card on file for ``msn`` — the RECORD, as a person may be shown it.

    ``recorded`` is the field that keeps two absences apart. Every grantee onboarded
    before 2026-09-16 has NO instrument row, and that is a different fact from a row
    that says `absent`: the first means nobody has asked this account for a card, the
    second means the account was asked and holds none. A surface that collapsed them
    would tell seven present clients something happened that did not.

    The LATEST row wins — the grantee document is an append-path document and a
    replaced card is a new row after the old.
    """
    from micyte.core.payment_instrument import STATE_ABSENT, STATE_SENTENCES

    markers = _markers()
    by_node = _instrument_state_nodes(states)
    document = documents.get(f"grantee-{msn}")
    latest: dict[str, Any] | None = None
    for row in getattr(document, "rows", ()) or () if document is not None else ():
        pairs = _pairs(row)
        node = pairs.get(markers["lcl_id"], "")
        if node not in by_node:
            continue
        state = by_node[node]
        latest = {
            "recorded": True,
            "state": state,
            "recogniser": "" if state == STATE_ABSENT else _decode(pairs.get(markers["title"], "")),
            "sentence": STATE_SENTENCES.get(state, ""),
            "since": pairs.get(markers["utc"], ""),
        }
    if latest is not None:
        return latest
    return {
        "recorded": False,
        "state": STATE_ABSENT,
        "recogniser": "",
        "sentence": "No card has been recorded for this account.",
        "since": "",
    }


def _service_rows(
    documents: dict[str, Any], *, msn: str, states: dict[str, str]
) -> list[dict[str, Any]]:
    markers = _markers()
    declared: dict[str, str] = {}
    instrument_nodes = _instrument_state_nodes(states)
    document = documents.get(f"grantee-{msn}")
    for row in getattr(document, "rows", ()) or () if document is not None else ():
        pairs = _pairs(row)
        state_node = pairs.get(markers["lcl_id"], "")
        if state_node in instrument_nodes:
            # An instrument row, not a service — same archetype, different branch. It
            # has its own block; drawn here it would appear as a service called
            # "Visa ending 4242, expires 04/29" in the state "present".
            continue
        service = _decode(pairs.get(markers["title"], ""))
        if service:
            declared[service] = states.get(state_node, state_node)
    out: list[dict[str, Any]] = []
    for spec in SERVICES:
        state = declared.get(spec["service"], "")
        out.append(
            {
                "service": spec["service"],
                "label": spec["label"],
                "state": state or "undeclared",
                "enabled": state in {"enabled", "locked_enabled"},
                "locked": bool(spec["locked"]),
                "note": spec["note"],
            }
        )
    # A service the DOCUMENT declares beyond the known set still renders — the
    # document is the datum, this tuple is only presentation order.
    for service, state in declared.items():
        if service not in {spec["service"] for spec in SERVICES}:
            out.append(
                {
                    "service": service,
                    "label": service,
                    "state": state,
                    "enabled": state in {"enabled", "locked_enabled"},
                    "locked": True,
                    "note": "",
                }
            )
    return out


def _service_key(authority_db_file: Path, *, msn: str) -> dict[str, Any]:
    """The grantee's service key block. The KEY IS SHOWN — exposing a copyable key is
    the depiction's point; the file is 0600 beside the store and this session is the
    operator's (or, later, the alias's own).

    The read moved to ``micyte.core.keypass`` on 2026-08-24 and the payload did not
    change. It had been a second implementation of the same path resolution, and the
    Key Pass Wallet was about to be a third — which is the shape
    ``doctrine/capability_before_surface.md`` exists to stop, and the one that produced
    a catalog prefix guard covering 1 of 4 write paths.

    The wallet reads the SAME file through ``held_instruments`` and gets only a
    recogniser. Two readings, two function names, one resolution of where the file is.
    """
    from micyte.core.keypass import service_key_for_handover

    return service_key_for_handover(
        Path(authority_db_file).parent, alias_msn=msn)


def _tolling_dir(authority_db_file: Path) -> Path:
    return Path(authority_db_file).parent / "utilities" / "tools" / "tolling"


def _invoice_summary(authority_db_file: Path, *, msn: str) -> dict[str, Any]:
    directory = _tolling_dir(authority_db_file)
    matches = sorted(directory.glob(f"tolling.*.{msn}.json")) if directory.is_dir() else []
    if not matches:
        return {"present": False, "note": "No tolling invoice derived for this alias."}
    try:
        record = json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return {"present": False, "note": "The invoice file could not be read."}
    monthly = record.get("monthly") or []
    latest = monthly[-1] if monthly else {}
    return {
        "present": True,
        "currency": _as_text(record.get("currency")) or "USD",
        "period": _as_text(latest.get("period")),
        "subtotal": latest.get("subtotal_billable", 0),
        "billable_lines": len(latest.get("billable_lines") or []),
        "last_refreshed_at": _as_text(record.get("last_refreshed_at")),
    }


def _tolling_rows(
    authority_db_file: Path, roster: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = []
    for account in roster:
        summary = _invoice_summary(authority_db_file, msn=account["msn"])
        rows.append(
            {
                "msn": account["msn"],
                "title": account["title"],
                **summary,
            }
        )
    directory = _tolling_dir(authority_db_file)
    # What each grantee is INVOICED, beside what serving them COSTS. Two figures, because
    # one of them alone is the thing this whole task exists to correct: the per-grantee
    # invoice was AWS cost x margin, and 98.7% of four months' AWS cost is borne by FND
    # rather than attributable to any client. A tab showing only the invoices would make
    # hosting look almost free.
    #
    # Operator-side only, and by CONSTRUCTION rather than by stripping: `_viewer_session`
    # returns before `build_session_payload` ever calls this, so a grantee session cannot
    # carry the figure even if somebody later forgets to remove it. What an alias may see
    # is their own invoice; what the whole estate costs is not that.
    cost: dict[str, Any] = {}
    try:
        from micyte.tools.grantor_books import cost_summary

        cost = cost_summary(Path(authority_db_file), sandbox=SANDBOX)
    except Exception:
        # A read model that cannot answer must not take the tab down with it. An absent
        # cost book is already a STATE this reports; an unreadable one is the same to a
        # viewer, and the tolling rows above are still true either way.
        cost = {}
    return {
        "rows": rows,
        "cost": cost,
        "note": ""
        if directory.is_dir()
        else "The tolling ledger directory is absent on this host — charges are "
             "derived where FND's operator tolling runs.",
    }


def _viewer_session(
    payload: dict[str, Any],
    documents: dict[str, Any],
    roster: list[dict[str, Any]],
    states: dict[str, str],
    *,
    viewer_msn: str,
) -> dict[str, Any]:
    """An alias's own session: their row, and nothing about anybody else.

    Three things are deliberately ABSENT, and their absence is the point rather than an
    oversight:

    * **the roster.** A viewer never learns that other aliases exist, let alone who.
      This is the whole defect being fixed: the payload used to carry every account.
    * **the service key.** ``_service_key`` returns it IN FULL because the operator's
      job is to hand it over. Serving a credential down a channel is a different act
      from displaying one to the person who mints it, and it needs its own decision —
      the operator's — not a side effect of narrowing a roster.
    * **the invoice.** What an alias owes is theirs to see, and how it is presented is
      a question about billing rather than about admission. Adding it here would settle
      that question by accident.

    So this is a NARROWING, never a widening: everything here was already visible to
    this alias about this alias. Turning any of the three on is a separate, deliberate
    change with the operator's name on it.
    """
    account = next((row for row in roster if row["msn"] == viewer_msn), None)
    payload["posture"] = "grantee"
    # The TAB VOCABULARY is the operator's and does not survive the narrowing. It reads
    # ("grantees", "tolling"): the first is the roster this viewer must not have, and
    # the second opens onto an invoice deliberately absent below. Leaving them would
    # advertise two tabs that cannot open and would tell the viewer, by their names
    # alone, that a roster of other aliases exists.
    payload["channel"] = {**payload["channel"], "tabs": []}
    payload["active_tab"] = ""
    if account is None:
        # A peer holding a live contract but no roster row. Say so plainly: they are
        # admitted, they simply have no account. Silence here would read as an error.
        payload["viewer"] = {
            "msn": viewer_msn,
            "note": "This channel holds no account for your alias.",
        }
        return payload
    payload["viewer"] = {
        "msn": account["msn"],
        "title": account["title"],
        "state": account["state"],
        "services": _service_rows(documents, msn=viewer_msn, states=states),
        # Their own card on file: brand, last four, expiry, state. Theirs to see, and
        # nothing here could charge it — the vault reference is not in this store.
        "instrument": _instrument(documents, msn=viewer_msn, states=states),
    }
    return payload


def build_session_payload(
    authority_db_file: Path | None,
    *,
    channel: GrantorChannel,
    tab: str = "",
    grantee: str = "",
    viewer_msn: str = "",
) -> dict[str, Any]:
    """The channel's session, in one of TWO postures.

    ``grantee`` is the OPERATOR asking about an alias: a query parameter, the operator's
    to choose, and the drill-in it opens carries operator readings — the alias's full
    service key (so it can be handed over) and their invoice.

    ``viewer_msn`` is an ALIAS asking about themselves: a verified identity supplied by
    the host after admission, never by the caller. It is not the drill-in narrowed to
    one row; it is a different reading, and mixing them is the error the operator
    corrected on PIM — the operator's view of a client is not the client's view of
    themselves.

    When ``viewer_msn`` is set it WINS: ``grantee`` is ignored entirely, because a
    viewer session about somebody else is not a thing this channel offers.
    """
    payload: dict[str, Any] = {
        "container": CONTAINER,
        "schema": SESSION_SCHEMA,
        "channel": {
            "channel_id": channel.channel_id,
            "label": channel.label,
            "summary": channel.summary,
            "access": channel.access,
            "tabs": list(channel.tabs),
        },
        "active_tab": tab if tab in TABS else DEFAULT_TAB,
        "posture": "admin",
    }
    if authority_db_file is None:
        payload["error"] = "no authority store configured"
        return payload
    db = Path(authority_db_file)
    documents = _grantor_documents(db)
    if "channel_profile" not in documents:
        payload["error"] = (
            "the grantor sandbox is not bootstrapped on this instance")
        return payload
    states = _state_labels(documents)
    roster = _roster(documents, states)

    if viewer_msn:
        return _viewer_session(payload, documents, roster, states, viewer_msn=viewer_msn)

    payload["grantees"] = {
        "cards": [
            {
                **account,
                "open": account["msn"] == _as_text(grantee),
            }
            for account in roster
        ],
        "empty_note": "" if roster else "The roster holds no accounts yet.",
    }
    selected = _as_text(grantee)
    if selected:
        account = next((a for a in roster if a["msn"] == selected), None)
        if account is None:
            payload["grantee_view"] = {
                "msn": selected,
                "note": "The roster holds no account for this alias.",
            }
        else:
            payload["posture"] = "admin_drill_in"
            payload["grantee_view"] = {
                "msn": account["msn"],
                "title": account["title"],
                "state": account["state"],
                "services": _service_rows(documents, msn=selected, states=states),
                "instrument": _instrument(documents, msn=selected, states=states),
                "api_key": _service_key(db, msn=selected),
                "tolling": _invoice_summary(db, msn=selected),
            }
    if payload["active_tab"] == "tolling":
        payload["tolling"] = _tolling_rows(db, roster)
    return payload


class GrantorChannel:
    channel_id = CHANNEL_ID
    label = "Grantor"
    summary = (
        "FND's hosting relationship, served as a channel: each client alias's "
        "profile, services and charges."
    )
    access = "closed"
    sandbox = SANDBOX
    tabs = TABS
    default_tab = DEFAULT_TAB
    #: The session follows ?grantor_tab= and ?grantee= (the drill-in).
    wants_surface_query = True
    #: This channel has a per-viewer reading, so the host hands it the VERIFIED
    #: counterparty on the contract route. Opt-in, like `wants_surface_query`: a
    #: channel with no grantee posture must not be silently given an identity it has
    #: no rule for.
    wants_viewer_identity = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        extra_query: dict[str, str] | None = None,
        viewer_msn: str = "",
    ) -> dict[str, Any]:
        del sandbox_id, document_id, datum_address
        query = dict(extra_query or {})
        # A VIEWER's session is about the viewer, full stop. `grantee` is a query
        # parameter and therefore the caller's to choose; honouring it for an admitted
        # peer let them name somebody else and receive that alias's drill-in — service
        # key included. When a viewer is known, the query is not consulted at all.
        if viewer_msn:
            return build_session_payload(
                authority_db_file, channel=self,
                tab=_as_text(query.get("grantor_tab")), viewer_msn=viewer_msn)
        return build_session_payload(
            authority_db_file,
            channel=self,
            tab=_as_text(query.get("grantor_tab")),
            grantee=_as_text(query.get("grantee")),
        )


CHANNEL = register(GrantorChannel())
