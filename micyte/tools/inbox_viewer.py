"""Inbox — the mail this instance received, judged against its own domain tree.

Oveure's fifth tab. Every other pane in this hub reads the authority store and renders
what it found; this one CANNOT, and the reason is the boundary that lets MiCyte ship
standalone: the mail lives in FND's account, behind an adapter in ``fnd_app``, and
``micyte/tools/`` may not reach there (``test_micyte_fnd_boundary``).

So the pane declares ROUTES and the client fetches. That is not a workaround — it is the
same shape the ask relay already has (``note_books``' ``ask`` control names its route and
the reply arrives client-side), and it keeps the honest property that a payload built
here can contain no message anybody has not been authorized to read. The refusal, when
there is one, arrives from the gate with the gate's own words.

What the tab does NOT do
------------------------
It does not send as a side effect of anything. Loading the list, opening a message, and
asking for a triage are three separate calls, and answering is a fourth — each its own
declared function, each separately grantable. A pane that triaged-and-replied on one
button would collapse four permissions an operator wrote down into one they did not.

It also renders nothing when no port is connected. An inbox with no connection behind it
is not an empty inbox: the pane says which it is, because "no mail" and "nothing is
connected" send an operator to different places.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text

_SCHEMA = "mycite.v2.portal.workbench.tool.inbox.v1"

#: The routes the client calls. Named here and nowhere else in MiCyte; the host registers
#: exactly these, and a test compares the two so a rename cannot half-happen.
LIST_ROUTE = "/portal/api/v2/fnd_service/list"
MESSAGE_ROUTE = "/portal/api/v2/fnd_service/message"
TRIAGE_ROUTE = "/portal/api/v2/fnd_service/triage"
SEND_ROUTE = "/portal/api/v2/fnd_service/send"
FORWARD_ROUTE = "/portal/api/v2/fnd_service/forward"

#: Why a pane with no connection says so rather than showing an empty list.
UNCONNECTED_TEXT = (
    "No mail connection on this instance yet. Connect an extension to the Email port on "
    "Utilities > Ports, configure it with the mailbox it acts for, and permit the "
    "functions you want. Nothing here reads mail until all three are done."
)


def inbox_payload(*, sandbox: str, providers: tuple[str, ...] = ()) -> dict[str, Any]:
    """The pane. Holds no message and no binding — both are the host's to answer.

    Deliberately stateless: which bindings exist and which functions are permitted change
    when an operator edits config, and a payload that had baked them in would go stale
    between a render and a click. The client asks, every time, and is told.
    """
    return {
        "schema": _SCHEMA,
        "container": "inbox",
        "title": "Inbox",
        "sandbox_id": as_text(sandbox),
        "routes": {
            "list": LIST_ROUTE,
            "message": MESSAGE_ROUTE,
            "triage": TRIAGE_ROUTE,
            "send": SEND_ROUTE,
            "forward": FORWARD_ROUTE,
        },
        "providers": list(providers),
        "unconnected_text": UNCONNECTED_TEXT,
        "empty_text": "Nothing has arrived for this mailbox.",
        # Said on the pane, not only in a docstring: the operator pressing Triage should
        # be able to see from the screen that it will not send anything.
        "triage_note": (
            "Triage reads the message, judges it against this sandbox's domain tree, and "
            "drafts a reply. It sends nothing — that is the button beside it."
        ),
    }


__all__ = [
    "FORWARD_ROUTE",
    "LIST_ROUTE",
    "MESSAGE_ROUTE",
    "SEND_ROUTE",
    "TRIAGE_ROUTE",
    "UNCONNECTED_TEXT",
    "inbox_payload",
]
