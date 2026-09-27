"""PIM's Design tab — the client's own site, and the writing they publish to it.

The operator's ask, 2026-08-26: *"a sub tab of design that lets them author ... blog posts
or articles that are used by their website to load."*

## Where the writing lives, and why not here

The body is a LEAFLET in the site's shared pool, not a datum document, and that is a
measurement rather than a preference. A MOS writing holds 4096 printable-ASCII characters
(``note_books.NOTE_CHAR_BUDGET``); measured against the 33 live articles on 2026-08-26,
**27 exceed the budget** — median 6,926, longest 41,445 — and **12 carry characters
``unstorable`` refuses**. The title cell is no kinder: ``encode_label_bits`` RAISES
``UnicodeEncodeError`` on two of the live titles.

So this tab keeps no datum document. It reads and writes through the ``site_hosting``
port, which is the live truth of what the site actually serves — and a second copy in MOS
would be a denotation free to drift the first time a leaflet was edited from the dashboard,
which still edits them. Two denotations or none.

## It reaches nothing by itself

``micyte`` holds no filesystem write and no site tree. The port ARRIVES: the host resolves
the binding, reads the credential, closes an ``authorize`` over the request, constructs the
adapter and hands it over as host context. This module talks to whatever it is given
through the Protocol and nothing else — so a different filling (a hosted CMS, an object
store) needs no edit here.

When nothing is handed over, the tab says which of the three states it is in — declared,
bound, permitted — rather than showing an empty table. An empty table cannot tell "you have
written nothing" from "nobody has bound the port", and those want opposite actions. It is
the same distinction ``pim_overview`` draws for the mail seam and for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from micyte.ports.site_hosting import (
    OPERATION_ASSET_SWAP,
    OPERATION_ASSET_UPLOAD,
    OPERATION_CONTENT_REPLACE,
)
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.pim_design.v1"

#: The port this tab is a view of. Named once; the host answers for it.
PORT_ID = "site_hosting"

#: Its own query parameter. A nested hub sharing the parent's would make selecting a
#: sub-tab move the parent's tab too — the collision `agronomics_viewer._hub` avoids by
#: giving every level its own.
TAB_QUERY = "design_section"
DEFAULT_TAB = "articles"

#: Which piece the Posts tab has open. Its OWN parameter, for the same reason the tab has
#: one: a piece stays selected while the reader moves between tabs, and clearing it is how
#: the gallery comes back.
PIECE_QUERY = "piece"

#: The Site tab's own sub-tab parameter — its own, like every nested hub here.
SITE_QUERY = "site_section"

#: Where a publish and a retire are posted. The route judges the caller; this only says
#: which door.
#:
#: The three SITE writes name their action after the port operation they perform, taken from
#: the port rather than spelled again here — the grant an operator writes, the fence the
#: adapter checks and the door this form posts to then read as one word instead of three
#: that have to be kept in step. `_repoint_client_forms` rewrites the prefix for a client,
#: so both doors are reached through this one string.
_ROUTE = "/portal/api/v2/site"


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def site_port(host_context: dict[str, Any] | None) -> tuple[Any, str]:
    """``(port, why_not)`` — the site seam this render may use, or the reason it may not.

    The refusal is CARRIED, not swallowed. A tab that renders "nothing to show" over a
    binding the operator has not written teaches the client that they have published
    nothing, and they will believe it.

    ``why_not`` is CLIENT-FACING ONLY — this Design tab has exactly one reader, and it is
    not the operator (`grep` of every production caller of `site_port` and of
    `pim_overview.seam_state` turns up none on the operator's side; the Ports tab,
    `utilities_surfaces.py`, builds its own table from bindings and grants directly).
    Until 2026-08-29 the unbound case read "...Select one on Utilities > Ports, then
    write its grant" — an operator's instruction, on a tab only a client opens, naming a
    page (`masonlenehan.com` has zero nginx locations for `/portal/utilities`) the reader
    cannot reach and an action ("write its grant") the reader cannot take.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("port")
    if not callable(provider):
        return None, (
            "this portal did not offer a port to this render, so the site cannot be "
            "reached from here")
    try:
        port = provider(PORT_ID)
    except Exception as exc:  # the host's own refusal, in the host's own words
        return None, str(exc)
    if port is None:
        return None, (
            "your site is not connected here yet. Your operator is setting up the "
            "connection that lets this app reach it.")
    return port, ""


def _notice(title: str, text: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0,
            "count_label": "", "empty_text": text}


def _pieces(port: Any) -> tuple[list[Any], tuple[str, ...]]:
    """Every piece and the sub-topic vocabulary, read once for the whole tab."""
    pieces = list(port.list_articles())
    subtopics = tuple(getattr(port, "list_subtopics", lambda **_: ())())
    return pieces, subtopics


def _body_of(piece: Any) -> str:
    """The stored markdown. Carried in `extra`, and it is what makes editing possible.

    `list_articles` already returns it, so an edit form can be PREFILLED with what the
    piece actually says rather than asking an author to paste their own work back in.
    Without this an "edit" is a retype, and a retype of 1,078 characters is not an edit.
    """
    extra = getattr(piece, "extra", None)
    return str((extra or {}).get("body") or "") if isinstance(extra, dict) else ""


def _summary_of(piece: Any) -> str:
    extra = getattr(piece, "extra", None)
    return str((extra or {}).get("excerpt") or "") if isinstance(extra, dict) else ""


def _status(piece: Any) -> str:
    """What a client calls it. `hidden` is the flag; "Draft" is the word for it.

    A piece that is not public is a draft — it exists, it is saved, and nobody can read it
    yet. Printing "no" under a column headed `public` made an author work out the meaning
    of a double negative to learn whether their writing was live.
    """
    return "Draft — not on the site" if getattr(piece, "hidden", False) else "Published"


def _piece_options(pieces: list[Any]) -> list[dict[str, str]]:
    """Titles to choose from, addresses to send. Nobody should type a slug."""
    return [{"value": _as_text(getattr(p, "slug", "")),
             "label": (f"{_as_text(getattr(p, 'title', '')) or _as_text(getattr(p, 'slug', ''))}"
                       f"{'  ·  draft' if getattr(p, 'hidden', False) else ''}")}
            for p in pieces]


def _gallery(pieces: list[Any]) -> dict[str, Any]:
    """The list of everything written, and the way into one of them.

    The `pick` control is what makes this a gallery rather than a printout: a record_table
    draws every cell as escaped text, so there is no clickable row, and before this the
    only way to act on a piece was to read its address out of a column and type it into a
    form underneath. Choosing a title and pressing Open is the same act without the
    transcription.
    """
    # NO STATUS COLUMN. The gallery is published pieces only since 2026-08-29, so a
    # column reading "Published" on every row is a column that says nothing — it was
    # load-bearing when drafts sat in the same list and stopped being so when they moved.
    rows = [{
        "title": _as_text(getattr(piece, "title", "")),
        "sub-topic": _as_text(getattr(piece, "subtopic", "")),
        "date": _as_text(getattr(piece, "date", "")),
        "web address": _as_text(getattr(piece, "url", "")),
    } for piece in pieces]
    drafts = sum(1 for p in pieces if getattr(p, "hidden", False))
    live = len(rows) - drafts
    return {
        "schema": _SCHEMA, "container": "record_table", "title": "Your posts",
        "columns": ["title", "sub-topic", "date", "web address"],
        "rows": rows, "row_count": len(rows),
        # The COUNT an author wants: how much is live, and how much is waiting.
        "count_label": (f"{live} published" + (f" · {drafts} draft" if drafts else "")),
        # Says DRAFTS, not "Write" — the standalone Write tab folded into Drafts the same
        # day this gallery split off Pages/Images (2026-08-29), and this string still said
        # "Write" for a tab that no longer exists until this fix.
        "empty_text": "Nothing written yet. The Drafts tab is where a first piece starts.",
        "pick": {
            "label": "Open a post",
            "param": PIECE_QUERY,
            "options": _piece_options(pieces),
            "go_label": "Open",
        } if pieces else None,
    }


def _piece_pane(piece: Any, subtopics: tuple[str, ...], *, sandbox: str,
                sent: dict[str, Any] | None = None) -> dict[str, Any]:
    """ONE piece, opened: what it says, and the three things that can be done to it.

    Everything here is prefilled from the stored piece, so editing is editing rather than
    re-entry, and the address is carried in `fixed`/`value` rather than typed. The three
    acts are separated because they carry different weight — a save is routine, a change
    of visibility is reversible, and a retire removes the only copy of the words.
    """
    slug = _as_text(getattr(piece, "slug", ""))
    title = _as_text(getattr(piece, "title", "")) or slug
    hidden = bool(getattr(piece, "hidden", False))
    vocabulary = ", ".join(subtopics)
    sent = sent if isinstance(sent, dict) else {}
    issue = sent.get(slug) or {}
    was_sent = bool(issue)

    facts = {
        "schema": _SCHEMA, "container": "record_table", "title": title,
        "columns": ["fact", "value"],
        "rows": [
            {"fact": "status", "value": _status(piece)},
            {"fact": "sub-topic", "value": _as_text(getattr(piece, "subtopic", ""))},
            {"fact": "date", "value": _as_text(getattr(piece, "date", ""))},
            {"fact": "address", "value": slug},
            {"fact": "web address", "value": _as_text(getattr(piece, "url", "")) or "—"},
        ],
        "row_count": 5,
        "count_label": _status(piece),
        # The way back to the gallery. Clearing the parameter IS the return.
        "back": {"label": "All posts", "param": PIECE_QUERY, "value": ""},
    }

    edit = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Edit this post",
        "fields": [
            {"key": "body", "label": (
                "The writing (Markdown — the first '# ' line is the title)" if not was_sent
                else "The writing — this went to your list on "
                     f"{_as_text(issue.get('sent_at'))[:10] or 'an earlier day'}, so saving "
                     "makes a NEW piece. Give it a different first '# ' line."),
             "type": "textarea", "value": _body_of(piece)},
            {"key": "summary", "label": "Summary (one line, shown on the tile)",
             "value": _summary_of(piece)},
            {"key": "subtopic", "label": "Sub-topic",
             "value": _as_text(getattr(piece, "subtopic", "")),
             "placeholder": vocabulary or "writing"},
            {"key": "date", "label": "Date", "value": _as_text(getattr(piece, "date", "")),
             "placeholder": "YYYY-MM-DD"},
        ],
        "submit_label": "Save changes" if not was_sent else "Save as a new piece",
        "submit_action": {
            "route": f"{_ROUTE}/publish", "sandbox_id": sandbox,
            "success_label": "Saved",
            # `prior_slug` is what makes this an EDIT and not a second copy. Changing the
            # first heading moves the piece's address; naming the old one is how the site
            # knows to take the old address down instead of leaving both.
            #
            # A SENT PIECE IS NOT EDITED, IT IS FORKED (2026-09-14). What went out is in
            # other people's mail and cannot be changed, so the save must not move or
            # retire it: `prior_slug` is withheld and `fork_of` names what this came from,
            # which is what the door refuses on when the title has not moved.
            "fixed": ({"fork_of": slug, "hidden": True} if was_sent
                      else {"prior_slug": slug, "hidden": hidden}),
        },
    }

    retire = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Delete this post",
        "fields": [],
        "submit_label": "Delete permanently",
        "submit_action": {
            "route": f"{_ROUTE}/retire", "sandbox_id": sandbox, "danger": True,
            "success_label": "Deleted", "fixed": {"slug": slug},
            "confirm": {"expect": "retire", "key": "confirm",
                        "text": f"This removes “{title}” and the page it is served at. "
                                "The site holds the only copy of the writing. To keep it "
                                "but take it off the site, use Publish or unpublish."},
        },
    }

    # NEITHER A SEND NOR A VISIBILITY CONTROL HERE ANY MORE (2026-09-14). Both moved to
    # the tab that is ABOUT them, where the choice is made against a list of what has
    # already gone out or is already up. This pane offered "send to subscribers" with no
    # sight of what had been sent, which is how somebody sends a second issue believing it
    # is the first. An act offered in two places is an act whose two surfaces drift.
    #
    # What is left is what belongs to ONE piece and nothing else: what it says, editing it,
    # and removing it altogether.
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": facts}, {"panel_payload": edit},
                      {"panel_payload": retire}]}


def _chronological(pieces: list[Any], *, key) -> list[Any]:
    """Newest first, by the day the VIEW is about.

    The Newsletter view orders by when a piece was SENT and the Website view by the piece's
    own date, because those are different days and a reader of either is asking "what
    happened most recently HERE". Ordering both by the article's date would put an issue
    sent last week below one written last year that went out this morning.
    """
    return sorted(pieces, key=lambda p: _as_text(key(p)), reverse=True)


def _cards(pieces: list[Any], *, title: str, columns: list[str], row: Any,
           count_label: str, empty_text: str,
           pick_label: str = "Open a piece") -> dict[str, Any]:
    """One gallery, three captions.

    The table IS the card list: `pick` is what makes it a gallery rather than a printout —
    a record_table draws every cell as escaped text, so choosing a title and pressing Open
    is the only way into a piece that does not ask somebody to read an address out of a
    column and retype it.
    """
    return {
        "schema": _SCHEMA, "container": "record_table", "title": title,
        "columns": columns,
        "rows": [row(p) for p in pieces], "row_count": len(pieces),
        "count_label": count_label,
        "empty_text": empty_text,
        "pick": {"label": pick_label, "param": PIECE_QUERY,
                 "options": _piece_options(pieces), "go_label": "Open"} if pieces else None,
    }


def _piece_status(piece: Any, sent: dict[str, Any]) -> str:
    """What became of one piece, in the two facts that are true of it independently.

    A piece can be on the site AND have gone to the list; those are not points on a scale,
    and picking one to display would hide the other. "Draft" is what is left when neither
    is true — an absence, said as one word.
    """
    marks = []
    if not getattr(piece, "hidden", False):
        marks.append("on the site")
    if _as_text(getattr(piece, "slug", "")) in sent:
        marks.append("sent")
    return " · ".join(marks) or "draft"


def _articles_count(pieces: list[Any], sent: dict[str, Any]) -> str:
    live = sum(1 for p in pieces if not getattr(p, "hidden", False))
    mailed = sum(1 for p in pieces if _as_text(getattr(p, "slug", "")) in sent)
    parts = [f"{len(pieces)} piece" + ("" if len(pieces) == 1 else "s")]
    if live:
        parts.append(f"{live} on the site")
    if mailed:
        parts.append(f"{mailed} sent")
    return " · ".join(parts)


def _start_form(subtopics: tuple[str, ...], *, sandbox: str) -> dict[str, Any]:
    """Where a new piece begins. ONE outcome — an article artifact, kept off the site.

    The destination select went with the 2026-09-14 split: a piece is written here, then
    SENT from the Newsletter tab or PUT UP from the Website tab, each against a list of
    what is already there. Choosing a destination at the moment of writing meant choosing
    it before there was anything to choose it against — and it meant a first draft could
    reach 39 people as a side effect of being written down.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Write a new piece",
        "fields": [
            {"key": "body",
             "label": "The writing (Markdown — the first '# ' line is the title)",
             "type": "textarea",
             "placeholder": "# A Title\n\nThe first paragraph."},
            {"key": "summary", "label": "Summary (one line, shown on the tile)"},
            {"key": "subtopic", "label": "Sub-topic",
             "placeholder": ", ".join(subtopics) or "writing"},
            {"key": "date", "label": "Date", "placeholder": "YYYY-MM-DD — blank is today"},
        ],
        "submit_label": "Save",
        "submit_action": {"route": f"{_ROUTE}/publish", "sandbox_id": sandbox,
                          "success_label": "Saved", "fixed": {"visibility": "draft"}},
    }


def _articles_pane(port: Any, why_not: str, *, sandbox: str, open_slug: str = "",
                   subscribers: dict[str, Any] | None = None,
                   sent: dict[str, Any] | None = None,
                   contacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """EVERY article artifact, and the place a new one starts.

    The main view, and deliberately the one that hides nothing: a piece is here whether it
    is on the site, out to the list, both, or neither. The older Posts tab showed published
    pieces only and the older Drafts tab showed the rest, which meant an author looking for
    something they had written had to remember which state they left it in.

    The `status` column is load-bearing HERE in a way it was not on the published-only
    gallery: with everything in one list it is the column that answers what became of each.
    """
    if port is None:
        return _notice("Articles", why_not)
    try:
        pieces, subtopics = _pieces(port)
    except Exception as exc:
        return _notice("Articles", str(exc))
    sent = sent if isinstance(sent, dict) else {}

    if open_slug:
        chosen = next((p for p in pieces
                       if _as_text(getattr(p, "slug", "")) == open_slug), None)
        if chosen is not None:
            return _piece_pane(chosen, subtopics, sandbox=sandbox, sent=sent)

    ordered = _chronological(pieces, key=lambda p: getattr(p, "date", ""))
    gallery = _cards(
        ordered, title="Your writing",
        columns=["title", "status", "sub-topic", "date"],
        row=lambda p: {
            "title": _as_text(getattr(p, "title", "")),
            "status": _piece_status(p, sent),
            "sub-topic": _as_text(getattr(p, "subtopic", "")),
            "date": _as_text(getattr(p, "date", "")),
        },
        count_label=_articles_count(ordered, sent),
        empty_text="Nothing written yet. Start one below and it lands here.")
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": gallery},
                      {"panel_payload": _start_form(subtopics, sandbox=sandbox)}]}


def _newsletter_pane(port: Any, why_not: str, *, sandbox: str, open_slug: str = "",
                     subscribers: dict[str, Any] | None = None,
                     sent: dict[str, Any] | None = None,
                     contacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """What has gone to the list, newest first — and the way to send one more.

    THE RECORD AND THE ACT ON ONE PAGE. Before this, "what have I sent" lived on a
    different tab from "send something", and the second had no sight of the first: an
    author could send a second issue without the first ever being in front of them.

    BUILT FROM THE SENT ISSUES, NOT FROM THE ARTICLES. Every issue this instance has sent
    is here, including one sent the other way — by mailing `news@<domain>`, which a Lambda
    captures and dispatches. Such an issue has no article behind it, so a list built by
    filtering articles would leave the author's own newsletter off their newsletter page.
    The `on the site` column is the join, read the other way round: it says which of these
    a reader can also find on the website.
    """
    if port is None:
        return _notice("Newsletter", why_not)
    try:
        pieces, _subtopics = _pieces(port)
    except Exception as exc:
        return _notice("Newsletter", str(exc))
    sent = sent if isinstance(sent, dict) else {}
    facts = subscribers if isinstance(subscribers, dict) else {}
    count = int(facts.get("count") or 0)

    by_slug = {_as_text(getattr(p, "slug", "")): p for p in pieces}
    issues = sorted(sent.items(), key=lambda kv: _as_text(kv[1].get("sent_at")), reverse=True)
    people = "1 subscriber" if count == 1 else f"{count} subscribers"
    rows = []
    for slug, issue in issues:
        piece = by_slug.get(slug)
        rows.append({
            "title": (_as_text(issue.get("subject"))
                      or _as_text(getattr(piece, "title", "")) or slug),
            "sent": _as_text(issue.get("sent_at"))[:10],
            "people": str(issue.get("target_count") or ""),
            # Three answers, not two. A piece can be on the site, kept off it, or not be
            # an article at all — and the third is the one an author would otherwise have
            # no way to notice about their own inbound-sent issue.
            "on the site": ("yes" if piece is not None and not getattr(piece, "hidden", False)
                            else "no" if piece is not None else "not an article yet"),
        })
    history = {
        "schema": _SCHEMA, "container": "record_table", "title": "Sent to your list",
        "columns": ["title", "sent", "people", "on the site"],
        "rows": rows, "row_count": len(rows),
        "count_label": f"{len(rows)} sent · {people}",
        "empty_text": ("Nothing has gone to your list yet. Choose a piece below to send "
                       "the first one."),
        "pick": {"label": "Open a sent piece", "param": PIECE_QUERY,
                 "options": _piece_options([by_slug[s] for s, _ in issues if s in by_slug]),
                 "go_label": "Open"} if any(s in by_slug for s, _ in issues) else None,
    }
    panes = [{"panel_payload": history},
             {"panel_payload": _send_form(pieces, sent, facts, sandbox=sandbox)}]
    orphans = [(slug, issue) for slug, issue in issues if slug not in by_slug]
    if orphans:
        panes.append({"panel_payload": _post_sent_form(orphans, sandbox=sandbox)})
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": panes}


def _post_sent_form(orphans: list[Any], *, sandbox: str) -> dict[str, Any]:
    """Put an issue that is not an article onto the site, as one.

    ONLY FOR ISSUES WITH NO ARTICLE. Anything sent from the Articles tab already has one —
    offering this for those would be offering to make a duplicate of a piece the author
    can already see. What this is for is an issue mailed to `news@<domain>`, which lives
    only in the private store and is on nobody's site.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Put a sent issue on your website",
        "fields": [
            {"key": "slug", "label": "Which issue", "type": "select", "value": "",
             "options": [{"value": slug,
                          "label": (_as_text(issue.get("subject")) or slug)}
                         for slug, issue in orphans]},
        ],
        "submit_label": "Put it up",
        "submit_action": {"route": f"{_ROUTE}/newsletter.post", "sandbox_id": sandbox,
                          "success_label": "Published"},
    }


def _send_form(pieces: list[Any], sent: dict[str, Any], facts: dict[str, Any], *,
               sandbox: str) -> dict[str, Any]:
    """Choose a piece and send it. The count is the label, and at zero there is no button.

    UNSENT PIECES ONLY in the list. A sent issue is terminal — the adapter refuses a second
    send of one and says so — so offering it here would be offering an act that can only
    refuse. Sending "again" is writing a new piece, which is what the Articles tab is for.
    """
    count = int(facts.get("count") or 0)
    address = _as_text(facts.get("list_address"))
    people = "1 person" if count == 1 else f"{count} people"
    unsent = [p for p in pieces if _as_text(getattr(p, "slug", "")) not in sent]
    if not count:
        where = _as_text(facts.get("signup_url"))
        return _notice(
            "Send to your list",
            "Nobody has subscribed yet, so there is nobody to send to. The signup form on "
            + (where or "your site")
            + " is live — anyone who fills it in appears here and on Contacts.")
    if not pieces:
        # NOT THE SAME AS "all sent". An instance with no writing at all and one whose
        # every piece has gone out are opposite situations that both leave this list
        # empty, and the first needs to be told to write something rather than that
        # everything is done.
        return _notice(
            "Send to your list",
            f"You have {people} waiting, and nothing written yet. Write a piece on the "
            "Articles tab and it can go out from here.")
    if not unsent:
        return _notice(
            "Send to your list",
            "Every piece you have written has already gone out. A sent issue is final; "
            "write a new piece on the Articles tab to send another.")
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Send to your list",
        "fields": [
            {"key": "slug", "label": "Which piece", "type": "select", "value": "",
             "options": _piece_options(
                 _chronological(unsent, key=lambda p: getattr(p, "date", "")))},
        ],
        "submit_label": f"Send to {people}",
        "submit_action": {
            "route": f"{_ROUTE}/article.send", "sandbox_id": sandbox, "danger": True,
            "success_label": "Sent",
            "confirm": {"expect": "send", "key": "confirm",
                        "text": (f"This sends the piece to {people}"
                                 + (f" from {address}" if address else "")
                                 + ". A published page can be taken back down; mail "
                                   "cannot. Type send to confirm.")},
        },
    }


def _website_pane(port: Any, why_not: str, *, sandbox: str, open_slug: str = "",
                  subscribers: dict[str, Any] | None = None,
                  sent: dict[str, Any] | None = None,
                  contacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the site is carrying, newest first — and the way to take one off it.

    "Remove from showing up on the website to be consumed" is the operator's phrase, and it
    is exactly `hidden`: the writing is kept, the page stops being served. It is NOT a
    retire, which removes the only copy of the words — that stays on the piece's own view,
    behind a typed confirmation, where it cannot be reached by picking from a list.
    """
    if port is None:
        return _notice("Website", why_not)
    try:
        pieces, _subtopics = _pieces(port)
    except Exception as exc:
        return _notice("Website", str(exc))
    live = [p for p in pieces if not getattr(p, "hidden", False)]
    ordered = _chronological(live, key=lambda p: getattr(p, "date", ""))
    listing = _cards(
        ordered, title="On your website",
        columns=["title", "date", "web address"],
        row=lambda p: {
            "title": _as_text(getattr(p, "title", "")),
            "date": _as_text(getattr(p, "date", "")),
            "web address": _as_text(getattr(p, "url", "")) or "—",
        },
        count_label=f"{len(ordered)} on the site",
        empty_text=("Nothing is on your website yet. Anything you have written can be put "
                    "up from here."))
    panes = [{"panel_payload": listing}]
    for form in (_shelve_form(ordered, sandbox=sandbox),
                 _put_up_form([p for p in pieces if getattr(p, "hidden", False)],
                              sandbox=sandbox)):
        if form is not None:
            panes.append({"panel_payload": form})
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": panes}


def _shelve_form(live: list[Any], *, sandbox: str) -> dict[str, Any] | None:
    """Take a piece off the site without losing it. ``None`` when nothing is up."""
    if not live:
        return None
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Take one off the website",
        "fields": [
            {"key": "slug", "label": "Which piece", "type": "select", "value": "",
             "options": _piece_options(live)},
        ],
        "submit_label": "Take it off",
        "submit_action": {
            "route": f"{_ROUTE}/visibility", "sandbox_id": sandbox,
            "success_label": "Taken off",
            # THE WRITING IS KEPT. `visibility` republishes the piece from its stored text
            # with `hidden` set, so this is undone by the form below it — which is the
            # whole difference between this and the delete on a piece's own view.
            "fixed": {"visibility": "draft"},
        },
    }


def _put_up_form(shelved: list[Any], *, sandbox: str) -> dict[str, Any] | None:
    """Put a piece that is not on the site onto it. ``None`` when everything already is."""
    if not shelved:
        return None
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Put one on the website",
        "fields": [
            {"key": "slug", "label": "Which piece", "type": "select", "value": "",
             "options": _piece_options(
                 _chronological(shelved, key=lambda p: getattr(p, "date", "")))},
        ],
        "submit_label": "Put it up",
        "submit_action": {"route": f"{_ROUTE}/visibility", "sandbox_id": sandbox,
                          "success_label": "Published",
                          "fixed": {"visibility": "public"}},
    }


def _contacts_pane(port: Any, why_not: str, *, sandbox: str, open_slug: str = "",
                   subscribers: dict[str, Any] | None = None,
                   sent: dict[str, Any] | None = None,
                   contacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Who signed up to this site's list, who left it, and who never joined.

    Operator, 2026-09-14: *"Each of these sites should keep a contact datum doc they can
    visit as a tab on PIM to see form field entries of those that have signed up or
    unsubscribed via the newsletters unsubscribe link."* Then, 2026-09-15: a sub tab on
    the authoring tab. It arrives here from PIM's top level, beside the writing that is
    addressed to these people — the Newsletter view's subscriber count and this table are
    now two readings of one roster, on one tab, instead of two tabs apart.

    THE ROSTER THEIR OWN WRITERS KEEP, read — not a second store beside it. The public
    subscribe endpoint and the unsubscribe link both write this leaflet; a copy of it in
    the books would be two denotations of one fact, and the copy is the one that goes
    stale. So this shows the FORM FIELDS those writers recorded, which is what was asked
    for.

    ## THE PORT IS NOT WHAT THIS PANE NEEDS

    Every other view here reads the site seam; this one reads a HOST FACT. So `port is
    None` must NOT blank it — a tool in the published package cannot open a roster on the
    host's disk, and the host says why when it cannot either. The `why_not` that matters
    is the one that arrives WITH the fact.

    ## THREE STATES, BECAUSE THERE ARE THREE (2026-09-15)

    "Not on the list" used to print as "unsubscribed", because one boolean was carrying
    three situations. Measured across every live roster on 2026-09-15: one client's tab
    reported their unsubscribe link had been used 1,171 times when it had been used ONCE
    — the other 1,170 rows were a bulk import nobody had ever asked. Another's said 60
    people had left a list they were never on; every one of them had sent a message or
    booked a job. The counts are separated now because a client acts differently on
    "nobody has joined" than on "everybody left".

    UNSUBSCRIBED ROWS ARE STILL SHOWN, not filtered away. Their row is kept precisely so
    that "left" stays distinguishable from "never joined" — it is what stops the next
    import re-adding somebody who asked to be taken off — and a client is entitled to see
    that the link in their own newsletter worked.
    """
    del port, why_not, sandbox, open_slug, subscribers, sent
    facts = contacts
    # ABSENT IS NOT EMPTY. A host that sent no `contacts` fact at all is an instance with
    # no site connection — there is no domain to key a roster by, so there is no roster.
    # That is a different answer from a roster that exists and has nobody in it, which is
    # a CONFIGURED tab with news on it.
    if not isinstance(facts, dict):
        facts = {"why_not": "this instance has no site connection, so it has no list"}
    rows = [r for r in (facts.get("rows") or []) if isinstance(r, dict)]
    reason = _as_text(facts.get("why_not"))
    live = int(facts.get("subscribed") or 0)
    gone = int(facts.get("unsubscribed") or 0)
    never = int(facts.get("never_subscribed") or 0)
    total = int(facts.get("total") or len(rows))
    people = "1 subscriber" if live == 1 else f"{live} subscribers"
    # EACH GROUP IS NAMED ONLY WHEN IT EXISTS. A label reading "· 0 unsubscribed" invites
    # the reader to wonder what it is warning them about; an absent clause says nothing,
    # which is the true thing to say about an empty group.
    parts = [people]
    if gone:
        parts.append(f"{gone} unsubscribed")
    if never:
        parts.append(f"{never} not on the list")
    count_label = " · ".join(parts)
    # THE CAP IS SAID OUT LOUD. TFF's roster is 1,194 rows; the payload carries 200 of
    # them and the counts beside it are the FULL ones. A table that silently shows a
    # prefix while its own label reports the whole is the defect this sentence removes.
    notice = ""
    if facts.get("truncated"):
        notice = (f"Showing the first {len(rows)} of {total}. The people on your list come "
                  "first, then anyone who has unsubscribed.")
    return {
        "schema": _SCHEMA,
        "container": "record_table",
        "title": "Contacts",
        "count_label": count_label if rows else "",
        "columns": ["email", "name", "phone", "zip", "status", "when", "how"],
        "rows": rows,
        "row_count": len(rows),
        "notice": notice,
        "empty_text": (
            reason
            or "Nobody has filled in your signup form yet. Anyone who does appears here, "
               "and anyone who later uses the unsubscribe link stays here with the day "
               "they left."),
        # AN EMPTY ROSTER IS A CONFIGURED TAB. `configured: bool(rows)` would omit this
        # view from the instance that needs it most — the client with a working signup
        # form and nobody on it, who is entitled to learn exactly that. What makes it
        # unconfigured is being unable to READ the roster at all: no site domain to match
        # on, no entity filed, or a leaflet that would not open. Those arrive as `why_not`
        # from the host and are a different sentence.
        "configured": not reason,
        "why_not": reason,
    }


def _page_options(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pages to choose from, SOURCE names to send.

    The two are not the same string and confusing them is how an edit silently addresses
    nothing: `/about` is what a reader sees, and `about.html` (static) or `about`
    (manifest) is the key `save_site_content` opens. So the label carries the address a
    person recognises and the value carries the one the write needs.
    """
    return [{"value": entry["page"], "label": f"{entry['label']} — {entry['path']}"}
            for entry in entries if entry.get("page")]


def _text_edit_form(options: list[dict[str, str]], *, sandbox: str) -> dict[str, Any]:
    """Change words that are already on a page.

    ONE `{old, new}` pair, which is the whole of what the port offers and deliberately so:
    the backend places it only where it occurs unambiguously, and refuses otherwise. A
    replacement that matched nothing comes back as a refusal naming the page, never as a
    "Changed" over a page that did not change.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Change words on a page",
        "fields": [
            {"key": "page", "label": "Which page", "type": "select",
             "value": options[0]["value"] if options else "", "options": options},
            # BOTH textareas. A heading is short and a paragraph is not, and a single-line
            # input for the second makes the long case the awkward one.
            {"key": "old", "label": "The words as they read now",
             "type": "textarea",
             "placeholder": "Copy them from the page exactly — spacing and punctuation "
                            "included."},
            {"key": "new", "label": "What they should say", "type": "textarea"},
        ],
        "submit_label": "Change the page",
        "submit_action": {
            "route": f"{_ROUTE}/{OPERATION_CONTENT_REPLACE}", "sandbox_id": sandbox,
            "success_label": "Changed",
        },
    }


#: The three galleries the store keys, the word this surface calls one of their entries,
#: and the title of the form that swaps one.
#:
#: The KEY is the FENCE'S OWN WORD. `save_site_content` looks a swap's target up under
#: `gallery[kind]` and refuses anything else by name, and `_swap_kind` derives exactly
#: these three from a reference. Held as one table so the Images listing below and the
#: forms beside it cannot come to disagree about what a site is made of.
_GALLERIES: tuple[tuple[str, str, str], ...] = (
    ("image", "image", "Swap an image on a page"),
    ("icon_file", "icon", "Swap an icon on a page"),
    ("icon_sprite", "sprite icon", "Swap a sprite icon on a page"),
)


def _image_swap_form(options: list[dict[str, str]], refs: list[dict[str, str]], *,
                     kind: str, title: str, noun: str, sandbox: str) -> dict[str, Any]:
    """Put a different picture where one already is — through the FENCED door.

    What a page holds is the image's REFERENCE, a string in its source, so both sides are
    chosen from the gallery above rather than typed: the reference has to match the
    source character for character and nobody should be transcribing a path to find that
    out.

    THIS POSTED TO `content.replace` UNTIL 2026-09-02, and that hole is why the form is
    worth its own docstring. `asset.swap` refuses a target that is not in this site's own
    gallery — "'x.avif' is not in your image gallery" — where a text replacement applies
    no such check at all, so the one visible swap control walked around a fence that was
    built, tested and grantable. Measured the same day: `asset.swap` appeared ZERO times
    in the portal's static JS, so nothing anywhere reached it.

    ONE FORM PER GALLERY, which is the shape the fence forces rather than a preference.
    The store keys the check by gallery, and a static form cannot derive that key from a
    choice the reader has not made yet — so the kind rides in `submit_action.fixed`, and
    the options offered are exactly the ones that kind fences. The single mixed list this
    replaced offered a sprite symbol as the replacement for a photo: `asset.swap` refuses
    that by name, and `content.replace` performed it.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": title,
        "fields": [
            {"key": "page", "label": "Which page", "type": "select",
             "value": options[0]["value"] if options else "", "options": options},
            {"key": "old", "label": f"The {noun} on it now", "type": "select",
             "options": refs},
            {"key": "new", "label": "Use this one instead", "type": "select",
             "options": refs},
        ],
        "submit_label": "Swap it",
        "submit_action": {
            "route": f"{_ROUTE}/{OPERATION_ASSET_SWAP}", "sandbox_id": sandbox,
            "success_label": "Swapped",
            # WHICH GALLERY THE TARGET MUST BE IN — the one this form's own options came
            # from. Sent rather than left to the route's default, which is `image`: an
            # icon swap without it is refused as a picture missing from the picture
            # gallery, which names the wrong shelf and so reads as a bug in the app.
            "fixed": {"kind": kind},
        },
    }


def _image_upload_form(*, sandbox: str) -> dict[str, Any]:
    """Add a picture the site did not have.

    ITS OWN PERMISSION and its own form. Swapping a photo changes which of this client's
    files a page points at; this puts a new file at a public URL, which is how a site
    comes to serve something nobody reviewed — so an operator may grant the swap above and
    withhold this, and the two must not share a submit.

    The file is pasted as a `data:` URL because the shared form container collects text
    inputs and posts JSON: a file picker here would be a second submit path for one
    button, and the byte-carrying half of it would be the one nothing else tests. What the
    file IS is decided from its bytes at the store, not from the label in the URL.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Add an image",
        "fields": [
            {"key": "name", "label": "Call it", "value": "",
             "placeholder": "letters, digits, - and _ (no dots, no slashes)"},
            {"key": "data", "label": "The picture, as a data: URL", "type": "textarea",
             "placeholder": "data:image/png;base64,iVBORw0KGgo…"},
        ],
        "submit_label": "Add it",
        "submit_action": {
            "route": f"{_ROUTE}/{OPERATION_ASSET_UPLOAD}", "sandbox_id": sandbox,
            "success_label": "Added",
        },
    }


def _pages_pane(port: Any, why_not: str, *, sandbox: str = "") -> dict[str, Any]:
    """Every page of this client's site, and the control that changes what one says.

    MERGED 2026-08-29. This was two tabs — "Pages" and "Site" — reading the same eight
    pages through two different port calls and showing three columns each. Measured on
    Mason Lenehan's live instance: eight rows in one, the same eight in the other, no row
    in either that the other did not also describe. Two tabs that answer one question make
    a reader check both to find out they did not need to.

    So the two reads are JOINED on the path rather than shown side by side. `list_pages`
    knows the title and whether a page can be edited in place; `list_site_content` knows
    which file answers it. Neither knows the other's half, which is exactly why this is a
    join and not a choice between them.

    NO LONGER READ ONLY, and that is the whole of the 2026-08-29 change here. The
    paragraph this docstring used to carry said the typing happens in an iframe elsewhere
    and that "eight rows with an Edit button that refused would be worse than no button".
    The button no longer refuses: `content.replace` is implemented, granted on every live
    binding, and was reachable from nowhere — so what stood here was a table describing a
    capability the client held and could not use.

    The form is offered only where the site actually has an editor. `editable` is a fact
    about the SITE, so a site outside it still gets its table and gets told why the form
    is absent, rather than being handed a control that would answer `not_editable`.
    """
    if port is None:
        return _notice("Pages", why_not)
    try:
        pages = port.list_pages()
    except Exception as exc:
        return _notice("Pages", str(exc))

    # The second read is ADDITIVE: its absence costs a column, not the table. A site whose
    # host cannot enumerate files still has pages worth listing, and a failure here that
    # emptied the tab would report "no pages" for a site that has eight.
    files: dict[str, str] = {}
    enabled: Any = None
    try:
        content = port.list_site_content()
        enabled = content.get("enabled")
        for entry in (content.get("pages") or []):
            if isinstance(entry, dict):
                files[_as_text(entry.get("path")) or "/"] = _as_text(entry.get("page"))
    except Exception:
        files = {}

    rows = []
    options: list[dict[str, str]] = []
    editable = False
    for page in pages:
        path = _as_text(getattr(page, "path", "")) or "/"
        # The SOURCE name, from whichever read carries it. `list_pages` puts it in
        # `extra`; the site-content read has it under `page`. Falling back to the path
        # would look right and address nothing — `/about` is not a key any source has.
        source_name = (_as_text((getattr(page, "extra", None) or {}).get("page"))
                       if isinstance(getattr(page, "extra", None), dict) else "")
        source_name = source_name or files.get(path, "")
        rows.append({
            "page": path,
            "title": _as_text(getattr(page, "title", "")),
            "file": source_name,
            "source": _as_text(getattr(page, "kind", "")),
            "editable in place": "yes" if getattr(page, "editable", False) else "no",
        })
        if getattr(page, "editable", False):
            editable = True
            if source_name:
                options.append({"page": source_name, "path": path,
                                "label": _as_text(getattr(page, "title", "")) or path})

    table = {
        "schema": _SCHEMA, "container": "record_table", "title": "Pages",
        "columns": ["page", "title", "file", "source", "editable in place"],
        "rows": rows, "row_count": len(rows),
        "count_label": f"{len(rows)} page{'' if len(rows) == 1 else 's'}",
        "notice": _pages_notice(rows, editable=editable, offering=bool(options)),
        "empty_text": (
            "This site is not set up for in-place editing yet."
            if enabled is False
            else "This site has no pages the host can see."),
    }
    if not options:
        return table
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": table},
                      {"panel_payload": _text_edit_form(_page_options(options),
                                                        sandbox=sandbox)}]}


def _pages_notice(rows: list[dict[str, str]], *, editable: bool, offering: bool) -> str:
    """The sentence under the table, and it must not promise a control that is absent.

    Three states, because there are three: the form is here, the site has no in-place
    editor at all, or it has one and this host could not name the source file any page
    answers from — which looks identical to the second from the table and is not.
    """
    if not rows:
        return ""
    if offering:
        return ("Change the words on any of these below. This is what your site has; the "
                "pieces you publish to it are the Authoring tab.")
    if editable:
        return ("These pages can be edited, but this connection could not say which file "
                "each one is written in, so the edit form is not offered here.")
    return ("This site is not set up for editing text from here yet. This is what your "
            "site has; the pieces you publish to it are the Authoring tab.")


def _images_pane(port: Any, why_not: str, *, sandbox: str = "") -> dict[str, Any]:
    """The images and icons this site draws from, and the two things a client does to them.

    Read under `content.replace` — `list_site_content` authorizes that operation, and this
    docstring used to add "the same permission a swap needs". That second half stopped
    being true on 2026-09-02: a swap is `asset.swap` now, its own permission because its
    fence is its own. So THIS PANE CAN DRAW A SWAP FORM THE HOST WILL REFUSE — an operator
    holding `content.replace` and not `asset.swap` sees the gallery, sees the control, and
    gets the gate's own 403 on submit. Nothing here can tell: the tool is handed a port,
    never a grant, and `host_context["bindings"]` carries ids only. Better a refusal in
    the gate's words than a control silently withheld for a reason this surface guessed.

    The controls are SEPARATE because their permissions are. A swap points a page at a
    different file this client already has; an upload puts a new file at a public URL.
    `enabled` and `upload` are the seam's own answers about which of the two this site
    supports, so a control appears only where it would work — and the swap is offered once
    per gallery that holds something, because the fence is keyed by gallery.
    """
    if port is None:
        return _notice("Images", why_not)
    try:
        content = port.list_site_content()
    except Exception as exc:
        return _notice("Images", str(exc))
    gallery = content.get("gallery") or {}
    rows: list[dict[str, str]] = []
    # KEPT APART BY GALLERY, because that is how the swap is fenced: the store looks a
    # target up under its own kind, so a list that had lost which shelf a reference came
    # off could only guess. The table below still reads as one list.
    refs: dict[str, list[dict[str, str]]] = {}
    for kind, label, _title in _GALLERIES:
        for ref in (gallery.get(kind) or []):
            text = _as_text(ref)
            if not text:
                continue
            name = text.rsplit("/", 1)[-1]
            rows.append({
                "kind": label,
                # The leaflet name is the useful half; the directory is the same for
                # every row and reading it forty times teaches nothing.
                "name": name,
                "reference": text,
            })
            # The VALUE is the whole reference, because that is the string the page's
            # source holds and a swap has to match it exactly. The label is the short
            # name, because that is the half a person recognises.
            refs.setdefault(kind, []).append(
                {"value": text, "label": f"{name} ({label})"})

    table = {
        "schema": _SCHEMA, "container": "record_table", "title": "Images",
        "count_label": f"{len(rows)} asset(s)",
        "columns": ["kind", "name", "reference"], "rows": rows, "row_count": len(rows),
        "empty_text": "No images or icons are registered for this site yet.",
    }
    options = _page_options([
        {"page": _as_text(entry.get("page")), "path": _as_text(entry.get("path")) or "/",
         "label": _as_text(entry.get("label")) or _as_text(entry.get("path")) or "/"}
        for entry in (content.get("pages") or []) if isinstance(entry, dict)
    ])
    panes: list[dict[str, Any]] = [{"panel_payload": table}]
    if content.get("enabled") and options:
        # ONE SWAP PER GALLERY THIS SITE ACTUALLY HAS. A kind with nothing in it gets no
        # form, for the reason the Pages notice gives one tab over: a control whose only
        # answer is a refusal teaches a client the app is broken.
        for kind, label, title in _GALLERIES:
            if not refs.get(kind):
                continue
            panes.append({"panel_payload": _image_swap_form(
                options, refs[kind], kind=kind, title=title, noun=label,
                sandbox=sandbox)})
    if content.get("upload"):
        panes.append({"panel_payload": _image_upload_form(sandbox=sandbox)})
    if len(panes) == 1:
        return table
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": panes}


#: ``(tab id, label, builder)``. Writing first: it is the one that does something.
#: TWO, on the operator's instruction (2026-08-29): "it should only be the gallery and
#: the draft sub tabs". Pages and Images were never authoring — they are what the site is
#: MADE of, not what this client writes — and they moved to the Site tab, where "what
#: does my site consist of" is already the question being answered.
#:
#: LOAD-BEARING since 2026-08-29: `PimDesign.build_panel_payload` builds its `panes` list
#: FROM this tuple. Before that fix it built the list by hand and never read `TABS` at
#: all — a second, unread description of the tab set, free to say "Posts, Drafts" while
#: the hand-built list said something else, with nothing to notice the two had diverged.
#: Each entry carries its own builder because `_posts_pane` and `_drafts_pane` share one
#: signature (`port, why_not, *, sandbox, open_slug`) and differ only in which one runs —
#: designed that way so the loop needs no per-tab branch.
TABS: tuple[tuple[str, str, Callable[..., dict[str, Any]]], ...] = (
    # THREE VIEWS OF ONE ARTICLE (2026-09-14), not three kinds of thing. A piece of writing
    # is an article artifact; the other two tabs answer "which of these went to the list"
    # and "which of these is on the site", and each offers the one act that is about it.
    #
    # `posts`/`drafts` were the older split and it cut the wrong way: it separated pieces
    # by whether they were finished, so an author looking for something they wrote had to
    # remember which state they had left it in. These separate by DESTINATION, which is
    # what the author was choosing between in the first place.
    ("articles", "Articles", _articles_pane),
    ("newsletter", "Newsletter", _newsletter_pane),
    ("website", "Website", _website_pane),
    # THE FOURTH VIEW (2026-09-15), at the operator's instruction. Last, because it is WHO
    # the first three are addressed to — and beside them rather than a tab away, so the
    # number on the send form and the table it counts are on one screen. It arrived from
    # PIM's top level; `pim_overview`'s `contacts` feature id is RETIRED, not moved, for
    # the reason written beside it there.
    ("contacts", "Contacts", _contacts_pane),
)


#: What the frame is allowed to do. The client's site is a THIRD-PARTY ORIGIN to this
#: portal — `brockspressurewashing.com` is not the operator's vhost — which decides both
#: halves of this value.
#:
#: `allow-same-origin` IS granted, and it does not mean what it looks like: it gives the
#: frame ITS OWN origin (the client's domain), not this portal's. Without it the document
#: is opaque, `localStorage` throws on access, and a site whose JS touches it renders
#: half-drawn — which would make the tab a picture of a broken site rather than of the
#: site. The escape that makes `allow-scripts allow-same-origin` dangerous needs the frame
#: to be SAME-ORIGIN WITH THE EMBEDDER, so that it can reach its own frame element and
#: drop the sandbox. That is `v2_portal_network_browser`'s situation, not this one.
#:
#: What is withheld is what a marketing page has no business doing from inside a
#: dashboard: `allow-top-navigation` (a framed page must not be able to steer the operator
#: away from the portal) and `allow-modals`.
_FRAME_SANDBOX = "allow-scripts allow-same-origin allow-forms allow-popups"


def _preview_pane(port: Any, why_not: str, *, domain: str) -> dict[str, Any]:
    """The client's actual site, drawn, with their own pages to move it between.

    The operator, 2026-09-01: *"I eventually want to be able to actually see the website
    in the design PIM tab."* Until now this tab answered that with two tables. A table of
    page paths is a DESCRIPTION of a site; the acceptance criterion this pane exists for
    says the client sees their site, and only the site is the site.

    ## The address is resolved, never accepted

    The frame's URL is built from ``account.domain`` — the domain this instance's own
    account record keeps, the same fact the Domain tab draws "site answers at" from. It is
    NEVER taken from a query parameter, and that is a fence rather than a tidiness: a URL
    this pane would accept is a URL an operator could be handed in a link, and a dashboard
    that frames whatever it is told to frame is a phishing surface wearing the client's own
    chrome. There is no parameter to supply, so there is nothing to smuggle.

    The page list comes from ``page.list`` for the same reason — the client moves the frame
    between pages the PORT says their site has, not paths they type.

    ## What this pane deliberately does NOT do yet

    It does not turn a click in the frame into an image swap. It cannot: the frame is
    cross-origin, so this portal can neither read its DOM nor see where a click landed, and
    the plan's own note ("the overlay is NOT injected script") is the reason — an overlay
    that could locate an element would have to be script running INSIDE the client's site.
    Reaching that needs the site served back through this origin, which is a different and
    much larger decision than drawing the site.

    So the swap stays where it already works and is already fenced: the Images pane, beside
    this one. What changes is that the client can now SEE the page they are changing while
    they change it, which is the whole of what was missing.
    """
    if port is None:
        return _notice("Your site", why_not)
    if not domain:
        return _notice("Your site", (
            "No domain is recorded for this instance yet, so there is no address to show "
            "your site from. Your operator sets this up as part of connecting your site."))

    # ADDITIVE, exactly like `_pages_pane`'s second read: a site whose pages cannot be
    # enumerated is still a site worth drawing. Losing this costs the picker, not the frame.
    pages: list[dict[str, str]] = []
    try:
        for page in port.list_pages():
            path = _as_text(getattr(page, "path", "")) or "/"
            pages.append({
                "path": path,
                "label": _as_text(getattr(page, "title", "")) or path,
            })
    except Exception:
        pages = []

    return {
        "schema": _SCHEMA, "container": "site_preview", "title": "Your site",
        "site_url": f"https://{domain}/",
        "domain": domain,
        "pages": pages,
        "sandbox_attr": _FRAME_SANDBOX,
        "notice": (
            "This is your live site, as anyone visiting it sees it. To change a picture "
            "on it, use the Images tab beside this one; to change wording, use Pages."),
        # A frame that fails to paint is indistinguishable from a blank pane, so the
        # renderer is given the words to say it and the address it tried.
        "empty_text": f"Could not draw https://{domain}/ here.",
    }


def build_site_payload(host_context: Any, *, sandbox: str = "") -> dict[str, Any]:
    """What the client's site is MADE of: its pages, and the images it draws from.

    MOVED here from the Authoring hub on 2026-08-29. Both were always answers to "what
    does my site consist of", not "what have I written" — and sitting under Authoring they
    made that tab four things instead of one. The operator put it plainly: Authoring
    should be the gallery and the drafts.

    Same port, same refusals, same panes — only the tab they hang under changed. Exported
    as a function rather than a method so PIM's hub can compose it without constructing a
    tool it does not otherwise use.
    """
    port, why_not = site_port(host_context)
    # The sandbox is CARRIED now rather than dropped. It was discarded while these two
    # panes were read-only tables; every form under them submits `sandbox_id`, and the
    # host checks that claim against the binding — so a form built without it posts a
    # blank sandbox and the seam it names resolves to nothing.
    sandbox = _as_text(sandbox)
    # The DOMAIN, from the account record — the same fact `pim_overview`'s Domain pane
    # draws "site answers at" from, read here rather than re-derived so the two cannot
    # disagree about where this client's site answers.
    context = host_context if isinstance(host_context, dict) else {}
    account = context.get("account")
    domain = _as_text(account.get("domain")) if isinstance(account, dict) else ""
    return {
        # "Design" since 2026-09-07 — the pane's heading has to agree with the tab that
        # opens it, or the client clicks Design and lands on something calling itself
        # Site. The hub's `FEATURES` entry carries the reason the id stayed `site`.
        "schema": _SCHEMA, "container": "tabbed", "title": "Design",
        # THE SITE OPENS FIRST. It was `pages` until 2026-09-07, which meant a tab called
        # Design opened on a table of file names. The operator asked to see the website;
        # the first thing the tab draws is now the website.
        "active_tab": "preview", "tab_query_param": SITE_QUERY,
        "tabs": [
            {"id": "preview", "label": "Your site", "tool_id": "pim_design_preview",
             "panel_payload": _preview_pane(port, why_not, domain=domain)},
            {"id": "pages", "label": "Pages", "tool_id": "pim_design_pages",
             "panel_payload": _pages_pane(port, why_not, sandbox=sandbox)},
            {"id": "images", "label": "Images", "tool_id": "pim_design_images",
             "panel_payload": _images_pane(port, why_not, sandbox=sandbox)},
        ],
    }


class PimDesign:
    """The client's site, from their own application."""

    tool_id = "pim_design"
    label = "Design"
    summary = "Your site's pages, and the writing you publish to it."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    #: Reached as a PIM tab, never offered for a document in focus — it opens on no
    #: document at all, because what it shows is not in the store.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: The host resolves the binding and hands the seam over. See the module docstring.
    wants_host_context = True
    # No icon: it is a composed pane, dark on the rail, so there is no slot for one. The
    # hub it lives in carries the app's icon.
    # No `writes`: nothing here writes a datum row. The publish goes to a SITE through a
    # port, which is governed by a grant rather than by `datum_write_policy`.

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
        port, why_not = site_port(host_context)
        open_slug = _as_text(query.get(PIECE_QUERY))
        # BUILT FROM TABS, not by hand — see the constant's own comment. Posts (published
        # first: an author arrives asking what is on their site far more often than for a
        # blank page) and Drafts (everything not on it, and where a new one starts) share
        # one call shape, so this loop needs no per-tab branch.
        # The LIST, from the host: who a send would reach and what it would go out as.
        # A tool in the published package cannot read a roster on the host's disk, which
        # is why this arrives as a fact rather than being looked up here.
        facts = host_context if isinstance(host_context, dict) else {}
        subscribers = facts.get("subscribers")
        # WHICH PIECES HAVE GONE OUT, from the host. A tool in the published package cannot
        # read the private newsletter store, so "sent" arrives as a fact and is JOINED to
        # the articles by slug — the same address the send files an issue under.
        sent = facts.get("sent_issues")
        sent = sent if isinstance(sent, dict) else {}
        # WHO FILLED IN THE FORM, from the host, for the same reason: the roster is a file
        # on the host's disk and this package may not open it. It is the fact the Contacts
        # view is entirely made of, and it carries its own `why_not` — so a missing one is
        # "no site connection" and an empty one is "nobody yet", which are opposite news.
        contacts = facts.get("contacts")
        panes = [
            {"id": tab_id, "label": label, "tool_id": f"pim_design_{tab_id}",
             "panel_payload": builder(port, why_not, sandbox=sandbox, open_slug=open_slug,
                                      subscribers=subscribers, sent=sent,
                                      contacts=contacts)}
            for tab_id, label, builder in TABS
        ]
        active = _as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        # Links to the tabs this hub used to carry. `site` merged into `pages`, then
        # `pages` and `images` moved to the Site tab, `writing` folded into Drafts, and on
        # 2026-09-14 Posts/Drafts became Articles/Newsletter/Website. A saved link should
        # open the nearest thing that still exists rather than falling to the default and
        # looking like it worked — `posts` was "what is published", which is now Website;
        # `drafts` was "everything else, and where a new one starts", which is Articles.
        active = {"site": "website", "pages": "website", "images": "website",
                  "posts": "website", "writing": "articles",
                  "drafts": "articles"}.get(active, active)
        if active not in [pane["id"] for pane in panes]:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Design",
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
        }


register(PimDesign())

__all__ = ["DEFAULT_TAB", "PIECE_QUERY", "PORT_ID", "SITE_QUERY", "TABS",
           "TAB_QUERY", "PimDesign", "build_site_payload", "site_port"]
