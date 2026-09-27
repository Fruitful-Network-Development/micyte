"""The P2P message — a routing header wrapped around a `.mss`.

The Network page's P2P tab is the messaging centre between instances. Everything
that crosses it is one of a small, closed set of kinds:

- a request to establish a contract channel, and the replies that settle it;
- updates to an existing contract;
- an offer of a published still, and the conveyance of one;
- a datum document sent as `.mss`, or a single datum's hyphae value.

The shape that makes this simple: **the payload is always a `.mss`, or nothing.**
There is no second serialization to learn, no second decoder to keep in step, and
no second set of trust-boundary guards to drift apart. A message is a small
header saying who and what, plus — for the kinds that carry data — the exact
envelope bytes the sender hashed.

Why the header is separate from the payload
-------------------------------------------
A receiver must be able to **route before it can decode**, and in an encrypted
channel it must be able to route before it can *decrypt*. So the header is
authenticated-but-clear associated data, and the `.mss` is the sealed plaintext.
That also keeps the payload byte-identical end to end, which is what lets the
receiver's integrity check mean anything: a `.mss` is content-addressed, so any
re-framing in transit would break the correspondence between the recorded hashes
and the bytes that arrived.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from micyte.core.mss.envelope import (
    KIND_DOCUMENT_SET,
    KIND_HYPHAE,
    KIND_NAMES,
    MssEnvelopeError,
    canonical_json,
    peek_kind,
)

MESSAGE_SCHEMA = "mycite.v2.network.p2p.message.v1"


class MessageKind(StrEnum):
    """What a message is for. A closed set — an unknown kind is refused, not relayed."""

    CONTRACT_REQUEST = "contract_request"
    CONTRACT_UPDATE = "contract_update"
    STILL_OFFER = "still_offer"
    MSS_DOCUMENT = "mss_document"
    MSS_HYPHAE = "mss_hyphae"


#: Which kinds carry a `.mss` payload, and which envelope kind each requires.
#: Stated as data rather than as branches so the rule is checkable in one place.
_REQUIRED_PAYLOAD: dict[MessageKind, int | None] = {
    MessageKind.CONTRACT_REQUEST: None,
    MessageKind.CONTRACT_UPDATE: None,
    MessageKind.STILL_OFFER: None,        # an offer names a still; it does not ship one
    MessageKind.MSS_DOCUMENT: KIND_DOCUMENT_SET,
    MessageKind.MSS_HYPHAE: KIND_HYPHAE,
}


class MessageError(ValueError):
    """A message violates the P2P grammar."""


@dataclass(frozen=True)
class Message:
    """One P2P message: a header, and for some kinds a `.mss` payload."""

    kind: MessageKind
    sender_msn_id: str
    recipient_msn_id: str
    #: The contract this message belongs to. Empty only for CONTRACT_REQUEST,
    #: which is what brings a contract into existence.
    contract_id: str = ""
    #: Kind-specific fields — the requested resources of a contract request, the
    #: name and update-check hash of a still offer. JSON-serializable only.
    body: dict[str, Any] | None = None
    #: The exact envelope bytes, unaltered. ``None`` for header-only kinds.
    payload: bytes | None = None
    #: Passed in rather than sampled, so a message is reproducible and a test
    #: does not have to freeze the clock.
    sent_at: str = ""

    def __post_init__(self) -> None:
        if not self.sender_msn_id or not self.recipient_msn_id:
            raise MessageError("a message needs both a sender and a recipient msn_id")
        if self.sender_msn_id == self.recipient_msn_id:
            raise MessageError("a message cannot be addressed to its own sender")
        if self.kind is not MessageKind.CONTRACT_REQUEST and not self.contract_id:
            raise MessageError(
                f"{self.kind.value} must name the contract it belongs to"
            )

        required = _REQUIRED_PAYLOAD[self.kind]
        if required is None:
            if self.payload is not None:
                raise MessageError(
                    f"{self.kind.value} carries no .mss payload, but one was attached"
                )
            return
        if not self.payload:
            raise MessageError(f"{self.kind.value} requires a .mss payload")
        # The declared envelope kind must match what the message kind promises,
        # and it is checked from the HEADER — no inflation, no trust.
        try:
            actual = peek_kind(self.payload)
        except MssEnvelopeError as exc:
            raise MessageError(f"{self.kind.value} payload is not a .mss: {exc}") from exc
        if actual != required:
            raise MessageError(
                f"{self.kind.value} requires a {KIND_NAMES[required]} .mss but the "
                f"payload declares {KIND_NAMES.get(actual, actual)}"
            )

    @property
    def carries_payload(self) -> bool:
        return self.payload is not None


def header_bytes(message: Message) -> bytes:
    """The routing header, as the bytes a channel authenticates.

    This is the **associated data** of a sealed message: readable by a receiver
    before it decrypts, so it can route; covered by the authentication tag, so
    none of it can be altered in flight. The payload is deliberately absent —
    it is the sealed part, and duplicating a digest of it here would only invite
    the two to disagree.
    """
    return canonical_json(
        {
            "schema": MESSAGE_SCHEMA,
            "kind": message.kind.value,
            "sender_msn_id": message.sender_msn_id,
            "recipient_msn_id": message.recipient_msn_id,
            "contract_id": message.contract_id,
            "sent_at": message.sent_at,
            "body": message.body or {},
        }
    ).encode("utf-8")


def parse_header(raw: bytes) -> dict[str, Any]:
    """Read a header back, checking its grammar rather than trusting it.

    A header arrives from another instance, so an unknown kind is **refused**
    here — a relay that passes along a kind it does not understand is how an
    unvetted message reaches a handler that assumes it was vetted.
    """
    import json

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MessageError(f"message header is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise MessageError("message header is not an object")
    if payload.get("schema") != MESSAGE_SCHEMA:
        raise MessageError(f"unknown message schema: {payload.get('schema')!r}")
    try:
        MessageKind(str(payload.get("kind")))
    except ValueError as exc:
        raise MessageError(f"unknown message kind: {payload.get('kind')!r}") from exc
    for field in ("sender_msn_id", "recipient_msn_id"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise MessageError(f"message header has no {field}")
    body = payload.get("body")
    if body is not None and not isinstance(body, dict):
        raise MessageError("message body is not an object")
    return payload


__all__ = [
    "MESSAGE_SCHEMA",
    "Message",
    "MessageError",
    "MessageKind",
    "header_bytes",
    "parse_header",
]
