"""The contract channel — how a held contact is born, and how it ends.

A contract between two instances is what the whole network module turns on: it is
the gate to linked mode, the thing the Utilities page registers as a *holding*,
and the relationship every P2P message belongs to. This module is its lifecycle.

The states, and why these
-------------------------
``proposed``   one side has asked; nothing is granted yet
``offered``    the owner has answered with terms; still nothing is granted
``active``     both sides agreed — **the only state that grants anything**
``refused``    declined before it ever became active
``revoked``    withdrawn after being active
``expired``    lapsed rather than withdrawn

``refused``, ``revoked`` and ``expired`` are kept distinct even though all three
grant nothing, because they answer different questions for an operator looking at
a register: *was this ever a relationship?*, *did someone end it?*, *did it just
lapse?* Collapsing them into one "inactive" would throw away the only information
a register exists to show.

Read-side compatibility, stated plainly
---------------------------------------
``core/references.py`` already reads contracts on disk, and it treats *every*
status except an explicit refusal as declaring the relationship — including
``pending``, where the live FND→farm contract sits. That is correct for what it
does: it answers "is this cross-instance reference legitimate?", and a contract
that exists answers that regardless of where its negotiation got to.

This module answers a different question — "may this channel carry traffic, and
may the browser go linked?" — and for that, only ``active`` counts. The two are
deliberately not merged: a negotiation in progress is a legitimate declaration
and *not* a live channel, and one predicate cannot honestly be both.

Transitions are total and explicit
----------------------------------
Every legal move is in one table. A move that is not in it raises rather than
being ignored, because a silently-dropped transition leaves both sides believing
different things about a relationship — which is the one failure a channel
protocol cannot recover from on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from micyte.core.references import REFUSED_STATUSES


class ChannelState(StrEnum):
    PROPOSED = "proposed"
    OFFERED = "offered"
    ACTIVE = "active"
    REFUSED = "refused"
    REVOKED = "revoked"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL

    @property
    def grants_channel(self) -> bool:
        """Only ``active`` may carry traffic or unlock linked mode."""
        return self is ChannelState.ACTIVE


_TERMINAL = frozenset(
    {ChannelState.REFUSED, ChannelState.REVOKED, ChannelState.EXPIRED}
)


class ChannelEvent(StrEnum):
    PROPOSE = "propose"
    OFFER = "offer"
    ACCEPT = "accept"
    REFUSE = "refuse"
    REVOKE = "revoke"
    EXPIRE = "expire"


#: (state, event) -> next state. Total by construction: anything absent is illegal.
_TRANSITIONS: dict[tuple[ChannelState, ChannelEvent], ChannelState] = {
    (ChannelState.PROPOSED, ChannelEvent.OFFER): ChannelState.OFFERED,
    (ChannelState.PROPOSED, ChannelEvent.ACCEPT): ChannelState.ACTIVE,
    (ChannelState.PROPOSED, ChannelEvent.REFUSE): ChannelState.REFUSED,
    (ChannelState.PROPOSED, ChannelEvent.EXPIRE): ChannelState.EXPIRED,
    (ChannelState.OFFERED, ChannelEvent.ACCEPT): ChannelState.ACTIVE,
    (ChannelState.OFFERED, ChannelEvent.REFUSE): ChannelState.REFUSED,
    (ChannelState.OFFERED, ChannelEvent.OFFER): ChannelState.OFFERED,  # revised terms
    (ChannelState.OFFERED, ChannelEvent.EXPIRE): ChannelState.EXPIRED,
    (ChannelState.ACTIVE, ChannelEvent.REVOKE): ChannelState.REVOKED,
    (ChannelState.ACTIVE, ChannelEvent.EXPIRE): ChannelState.EXPIRED,
}


class ChannelError(ValueError):
    """An illegal transition, or a malformed channel."""


@dataclass(frozen=True)
class Channel:
    """One contract channel between two instances."""

    contract_id: str
    owner_msn_id: str
    consumer_msn_id: str
    state: ChannelState = ChannelState.PROPOSED
    #: ``rc.<owner_msn>.<resource>`` names the owner shares with the consumer.
    resources: tuple[str, ...] = ()
    #: Names the key-agreement suite in use, never a key. A secret must not sit
    #: in a value object that gets logged, registered and rendered.
    suite: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.owner_msn_id or not self.consumer_msn_id:
            raise ChannelError("a channel needs both an owner and a consumer msn_id")
        if self.owner_msn_id == self.consumer_msn_id:
            raise ChannelError("an instance cannot hold a contract channel with itself")

    @property
    def is_open(self) -> bool:
        return self.state.grants_channel

    def counterparty_of(self, msn_id: str) -> str:
        """The other side, from ``msn_id``'s point of view."""
        if msn_id == self.owner_msn_id:
            return self.consumer_msn_id
        if msn_id == self.consumer_msn_id:
            return self.owner_msn_id
        raise ChannelError(f"{msn_id} is not a party to {self.contract_id or 'this channel'}")


def apply_event(channel: Channel, event: ChannelEvent, *, at: str = "") -> Channel:
    """The channel after ``event``, or raise.

    Raising on an illegal move is the point. A revoked channel that quietly
    accepted an ``accept`` would reopen itself, and neither side would have a
    record of how.
    """
    key = (channel.state, event)
    if key not in _TRANSITIONS:
        raise ChannelError(
            f"cannot {event.value} a channel in state {channel.state.value}"
            + (" (it is terminal)" if channel.state.is_terminal else "")
        )
    return replace(
        channel, state=_TRANSITIONS[key], updated_at=at or channel.updated_at
    )


def legal_events(channel: Channel) -> tuple[ChannelEvent, ...]:
    """What may be done to this channel next — what a UI should offer, and only that."""
    return tuple(
        event for (state, event) in _TRANSITIONS if state is channel.state
    )


def state_from_contract_status(status: str) -> ChannelState:
    """Map an on-disk ``mycite.portal.contract.v2`` status onto a channel state.

    The stored vocabulary is looser than this state machine and predates it, so
    the mapping is explicit rather than assumed. Anything unrecognised becomes
    ``proposed`` — a declared relationship that grants no channel — because the
    safe reading of an unknown status is *not yet active*, never *active*.
    """
    token = (status or "").strip().lower()
    if token in REFUSED_STATUSES:
        return {
            "revoked": ChannelState.REVOKED,
            "expired": ChannelState.EXPIRED,
        }.get(token, ChannelState.REFUSED)
    if token in {"active", "accepted", "established"}:
        return ChannelState.ACTIVE
    if token in {"offered", "proposed_terms"}:
        return ChannelState.OFFERED
    return ChannelState.PROPOSED


__all__ = [
    "Channel",
    "ChannelError",
    "ChannelEvent",
    "ChannelState",
    "apply_event",
    "legal_events",
    "state_from_contract_status",
]
