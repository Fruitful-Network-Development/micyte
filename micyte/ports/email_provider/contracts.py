"""Email provider port — the mail an instance receives, and the mail it sends. CONTRACT ONLY.

The Oveure refinement (TASK-2026-08-14-002) built the outbound half and stopped there, at
the operator's explicit wish: the seam AVAILABLE and unused. TASK-2026-08-18-003 adds the
half a conversation needs — reading what arrived — because answering mail you cannot read
is not a feature, and a port that could only speak would have made every consumer reach
around it for the other direction.

There is still NO peripheral, NO route and NO HTTP client here; ``micyte`` may hold no
network client at all. An implementation lives host-side, takes its ``authorize`` gate at
construction, and judges the operation INSIDE the function that opens the network — the
Keycloak-admin order the AST sweep verifies, and the order a live probe taught: checking
the credential first tells an ungranted caller whether one is configured.

Four operations, at the grain worth withholding
-----------------------------------------------
An operation is what an operator would refuse SEPARATELY, and here the four differ sharply
in what they can cost:

* :data:`OPERATION_MAILBOX_LIST` — what has arrived. Discloses who wrote, and when.
* :data:`OPERATION_MESSAGE_FETCH` — one message's contents. Discloses what they said.
* :data:`OPERATION_MESSAGE_SEND` — words leave the box under the instance's name, to
  whoever the caller names. The only one a stranger ever sees.
* :data:`OPERATION_MESSAGE_FORWARD` — words leave the box to an address configured in
  advance. Separate from ``send`` precisely because "hand this to the owner" and "write
  to anyone" are the same act only if nobody wrote down the difference.

The SERVICE token is the provider a grant names. ``aws_ses`` is the token a DIRECT AWS
adapter would carry; an intermediary that sends on the instance's behalf carries its own,
because a grant over one vendor is never a grant over another — and "FND relays this for
me" is a different disclosure from "I hold the SES keys".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: What has arrived, without opening any of it.
OPERATION_MAILBOX_LIST = "mailbox.list"

#: One message, opened.
OPERATION_MESSAGE_FETCH = "message.fetch"

#: The call that sends the operator's words off-box, to an address the caller chooses.
OPERATION_MESSAGE_SEND = "message.send"

#: The call that hands a received message to an address configured in advance.
OPERATION_MESSAGE_FORWARD = "message.forward"

# ---------------------------------------------------------------------------
# ADMINISTRATION — the mailboxes themselves, as opposed to the mail in them.
#
# The four above are about MESSAGES. These six are about the mailbox: what
# addresses exist on a grantee's domain, where each hands its mail on to, and
# whether the person behind one has confirmed they may send AS it.
#
# They are declared here because they were not declared anywhere. The capability
# was real and live — `POST /__fnd/email/grantee/{add,edit,remove,resend-setup,
# send-reminder}` and `GET /__fnd/email/dashboard` — but those routes were guarded
# by a session scope and reached AWS directly, with no port in front. So an operator
# could neither grant nor withhold any of it, it did not appear on the Ports
# surface, and PIM had nothing to call. Four of those six doors (add, edit, remove,
# and the dashboard read) were deleted 2026-08-29 with the client dashboard they
# served, which leaves this port as the governed way to reach the capability —
# which is what declaring it here was for.
#
# SEPARATE FROM `message.send`, deliberately. `identity.verify_request` and
# `identity.remind` do send mail — an operational handoff to the personal address
# behind a mailbox — and an operator must be able to permit that without thereby
# permitting arbitrary correspondence. The reverse matters more: PIM employs
# neither `message.send` nor `message.forward` and must not start.

#: Which addresses exist on this grantee's domains, where each forwards, and how far
#: each has got through send-as confirmation. A read.
OPERATION_ALIAS_LIST = "alias.list"

#: Bring a new address into existence on a domain this grantee owns.
OPERATION_ALIAS_CREATE = "alias.create"

#: Take one away. Separate from create because deleting an address that has been
#: given out is not the same risk as adding one nobody knows yet.
OPERATION_ALIAS_REMOVE = "alias.remove"

#: Change where an existing address hands its mail on to. The single most requested
#: thing a client does with their mail, and the one that silently redirects
#: correspondence if it is wrong — so it is its own permission, not part of `alias.create`.
OPERATION_FORWARDING_SET = "forwarding.set"

#: Send the setup handoff to the personal address behind a mailbox, so its owner can
#: confirm they may send AS the domained address. SENDS MAIL, to a person, which is
#: why it is not folded into `alias.create` and why it is not `message.send`.
OPERATION_IDENTITY_VERIFY_REQUEST = "identity.verify_request"

#: Nudge an owner who has not finished. Also sends mail, and separately refusable —
#: an operator may want the setup handoff without a reminder cadence.
OPERATION_IDENTITY_REMIND = "identity.remind"

#: The provider a DIRECT adapter would bind — the stack's mail already rides AWS (SES).
SERVICE_AWS_SES = "aws_ses"


class EmailProviderError(ValueError):
    """A message is malformed before any provider is asked."""


class EmailProviderUnavailable(RuntimeError):
    """The provider could not answer, and the reason is the message.

    Raised, never returned as an empty list. An empty mailbox and an unreachable one are
    different facts, and the one that reads as "nothing arrived" is the one that gets a
    customer's question ignored.
    """


def _required(value: object, *, field_name: str) -> str:
    token = "" if value is None else str(value).strip()
    if not token:
        raise EmailProviderError(f"{field_name} is required")
    return token


@dataclass(frozen=True)
class EmailMessage:
    """What a send WOULD carry: addressee, subject, body. All required — an email
    with an implied half is one two readers read differently.

    ``in_reply_to`` and ``references`` are what make a reply a REPLY. Without them the
    answer arrives in the customer's client as a new message from a stranger, beside the
    question they asked, and the two never join. Empty on a message that begins a
    conversation; carried through from :class:`InboundMessage` on one that continues it.
    """

    to: str
    subject: str
    body: str
    in_reply_to: str = ""
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("to", "subject", "body"):
            if not str(getattr(self, name) or "").strip():
                raise EmailProviderError(f"email_message.{name} is required")
        object.__setattr__(self, "in_reply_to", str(self.in_reply_to or "").strip())
        object.__setattr__(
            self,
            "references",
            tuple(
                token
                for token in (str(r or "").strip() for r in (self.references or ()))
                if token
            ),
        )

    @property
    def is_reply(self) -> bool:
        return bool(self.in_reply_to)


@dataclass(frozen=True)
class MailboxEntry:
    """One message's existence, WITHOUT its contents — what a listing may disclose.

    Deliberately not a truncated :class:`InboundMessage`. Listing and reading are
    separately grantable operations, so the listing type must not be able to carry a body:
    a shape that CAN hold one is a shape somebody will fill, and then the cheaper grant
    quietly buys the dearer one.

    ``mailbox`` is the address the message was DELIVERED to, which is not the ``To:``
    header. Measured on live captured mail: several messages carry an empty ``To:``
    (bcc, or an envelope-only recipient), so a consumer filtering "addressed to info@"
    on the header silently drops real mail. The provider is required to answer with the
    envelope recipient, and an entry cannot be built without one.
    """

    message_key: str
    mailbox: str
    sender: str
    subject: str
    received_at: str

    def __post_init__(self) -> None:
        for name in ("message_key", "mailbox", "sender"):
            object.__setattr__(
                self, name,
                _required(getattr(self, name), field_name=f"mailbox_entry.{name}"))
        # A subject may honestly be absent; a date may not be parseable. Both are
        # normalised rather than refused — refusing here would hide a real message
        # behind a formatting complaint.
        object.__setattr__(self, "subject", str(self.subject or "").strip())
        object.__setattr__(self, "received_at", str(self.received_at or "").strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_key": self.message_key,
            "mailbox": self.mailbox,
            "sender": self.sender,
            "subject": self.subject,
            "received_at": self.received_at,
        }


@dataclass(frozen=True)
class InboundMessage:
    """One received message, opened.

    ``message_id`` / ``references`` are carried so a reply can thread — see
    :class:`EmailMessage`. ``body_text`` is the plain-text reading; HTML is deliberately
    absent from this contract, because the only consumer of a received body so far is a
    model reading it as prose, and handing rendered HTML to any other consumer is the
    mistake ``mail_browser`` already fences behind a sandboxed iframe.
    """

    message_key: str
    mailbox: str
    sender: str
    subject: str
    received_at: str
    body_text: str
    message_id: str = ""
    references: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("message_key", "mailbox", "sender"):
            object.__setattr__(
                self, name,
                _required(getattr(self, name), field_name=f"inbound_message.{name}"))
        for name in ("subject", "received_at", "body_text", "message_id"):
            object.__setattr__(self, name, str(getattr(self, name) or "").strip())
        for name in ("references", "recipients"):
            object.__setattr__(
                self, name,
                tuple(t for t in (str(v or "").strip() for v in (getattr(self, name) or ())) if t))
        object.__setattr__(self, "headers", dict(self.headers or {}))

    @property
    def entry(self) -> MailboxEntry:
        """The listing row for this message — one derivation, so a list and a read of the
        same message can never disagree about who sent it."""
        return MailboxEntry(
            message_key=self.message_key, mailbox=self.mailbox, sender=self.sender,
            subject=self.subject, received_at=self.received_at)

    def reply_subject(self) -> str:
        """``Re:`` the original, without stacking a second one on a reply to a reply."""
        subject = self.subject or "(no subject)"
        return subject if subject.lower().startswith("re:") else f"Re: {subject}"

    def reply_references(self) -> tuple[str, ...]:
        """The References chain a reply should carry: the original's, plus its id."""
        if not self.message_id:
            return self.references
        return (*self.references, self.message_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_key": self.message_key,
            "mailbox": self.mailbox,
            "sender": self.sender,
            "subject": self.subject,
            "received_at": self.received_at,
            "body_text": self.body_text,
            "message_id": self.message_id,
            "references": list(self.references),
            "recipients": list(self.recipients),
        }


@runtime_checkable
class EmailProviderPort(Protocol):
    """The seam a binding fills. ``provider_id`` is the service token a grant names.

    Every method is judged by the external-call gate FIRST, in its own body — the port
    states the order, the sweep enforces it.
    """

    @property
    def provider_id(self) -> str: ...

    def list_inbound(self, *, mailbox: str = "", limit: int = 0) -> tuple[MailboxEntry, ...]:
        """What has arrived for ``mailbox`` (or every mailbox this binding may read).

        Raises :class:`EmailProviderUnavailable` rather than returning ``()`` when the
        provider could not be reached.
        """

    def fetch_inbound(self, message_key: str) -> InboundMessage:
        """One message, opened. Raises when the key is outside what this binding may read."""

    def send_message(self, message: EmailMessage) -> str:
        """Send; return the provider's message id."""

    # ---- administration -------------------------------------------------------
    #
    # A binding may fill these and leave them unfilled; `site_hosting` already has
    # operations no adapter implements (`content.replace`, `asset.upload`). What the
    # port owes is a NAME an operator can grant or withhold, and a shape the filling
    # adapter must match if it offers one at all.

    def list_aliases(self, *, domain: str = "") -> tuple[dict[str, str], ...]:
        """Every address on ``domain``: its local part, where it forwards, its send-as stage.

        Each row also names the ``domain`` it is on. ``domain=""`` merges every domain a
        binding holds, and a merged row that cannot say which one it came from is a row an
        administration surface cannot act on: the alternative — splitting ``send_as`` — is
        empty precisely on the addresses whose send-as has not been set up.
        """

    def create_alias(self, *, domain: str, local_part: str, forward_to: str) -> dict[str, str]:
        """Bring an address into existence, forwarding to ``forward_to``."""

    def remove_alias(self, *, domain: str, local_part: str) -> dict[str, str]:
        """Take an address away."""

    def set_forwarding(self, *, domain: str, local_part: str, forward_to: str) -> dict[str, str]:
        """Change where an existing address hands its mail on to."""

    def request_identity_verification(self, *, domain: str, local_part: str) -> dict[str, str]:
        """Send the setup handoff so the owner can confirm send-as. SENDS MAIL."""

    def remind_identity_verification(self, *, domain: str, local_part: str) -> dict[str, str]:
        """Nudge an owner who has not finished confirming. SENDS MAIL."""

    def forward_message(self, message: InboundMessage, *, to: str, note: str = "") -> str:
        """Hand ``message`` to a pre-configured address, attributed.

        ``note`` rides along so the recipient can see WHY it was handed over. A forward
        that arrives with no account of itself is indistinguishable from the automatic
        forwarding the mail stack already does, and the person reading it cannot tell
        which system decided.
        """


__all__ = [
    "OPERATION_ALIAS_CREATE",
    "OPERATION_ALIAS_LIST",
    "OPERATION_ALIAS_REMOVE",
    "OPERATION_FORWARDING_SET",
    "OPERATION_IDENTITY_REMIND",
    "OPERATION_IDENTITY_VERIFY_REQUEST",
    "OPERATION_MAILBOX_LIST",
    "OPERATION_MESSAGE_FETCH",
    "OPERATION_MESSAGE_FORWARD",
    "OPERATION_MESSAGE_SEND",
    "SERVICE_AWS_SES",
    "EmailMessage",
    "EmailProviderError",
    "EmailProviderPort",
    "EmailProviderUnavailable",
    "InboundMessage",
    "MailboxEntry",
]
