"""Reachability — liveness is an answer at an address, not a flag.

Two prior documents disagreed about IP addresses in the registry, and both were
right about different layers. This module implements the resolution:

**The card and the registry carry DNS only.** For an instance with a domain, DNS
already maps domain to address; a second, static IP column would simply rot the
first time the address changed, and nothing would notice.

**The linked-mode transport resolves an address at contact time.** An instance
with no DNS still has to be reachable, and its address moves. That is a live
property of a connection attempt, not a column — so it is resolved when needed
and never persisted.

The consequence worth stating plainly: **there is no "online" boolean to set.**
An instance is live if and only if it answers at the address its registry entry
reports. Unreachable *is* offline. This is not the same as the contact card's
``active``, which is derived from contract status — an instance can hold a live
contract (``active``) and be offline at the same time, because its process is
down or its address is stale. Conflating the two produces a directory that
confidently reports the wrong thing.

Resolution itself is a **port**. This module decides *what liveness means* and
leaves *how to reach the network* to a caller — which keeps the registry domain
free of sockets, keeps it testable without a network, and keeps a lone-laptop
instance from acquiring a transport dependency it never uses.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

#: Returned when nothing has been attempted. Distinct from "attempted and
#: failed", because a browser must not paint an unprobed node as offline.
UNKNOWN = "unknown"
LIVE = "live"
OFFLINE = "offline"


@dataclass(frozen=True)
class Reachability:
    """The outcome of trying to reach one node."""

    msn_id: str
    status: str = UNKNOWN
    #: The address actually used. For a domained instance this is its DNS name;
    #: for a DNS-less one it is whatever the transport resolved *this time*.
    address: str = ""
    #: Why, when the status is not LIVE. Surfaced to the operator — "offline"
    #: with no reason is indistinguishable from "never checked".
    detail: str = ""

    @property
    def is_live(self) -> bool:
        return self.status == LIVE

    @property
    def was_probed(self) -> bool:
        return self.status != UNKNOWN


class ReachabilityResolver(Protocol):
    """How the linked-mode transport reaches a node.

    Implemented outside this domain — the registry decides what liveness means,
    not how a socket gets opened.
    """

    def resolve(self, msn_id: str, *, dns: str = "") -> Reachability:
        """Attempt to reach ``msn_id``, optionally starting from its DNS name."""
        ...


def dns_reachability(msn_id: str, dns: str) -> Reachability:
    """The cached-mode answer: a DNS name is an *address*, not a liveness probe.

    Cached mode has no live awareness by construction — it is reading a snapshot.
    So a node with a domain reports :data:`UNKNOWN` with its address filled in,
    and a node without one reports :data:`UNKNOWN` with an explicit reason. What
    it must never do is infer "live" from the mere presence of a DNS record: a
    domain that resolves says nothing about whether a process is listening.
    """
    address = (dns or "").strip()
    if address:
        return Reachability(msn_id=msn_id, status=UNKNOWN, address=address)
    return Reachability(
        msn_id=msn_id,
        status=UNKNOWN,
        detail="no DNS on the card; reachable only through linked mode",
    )


def is_live(
    msn_id: str,
    *,
    dns: str = "",
    resolver: ReachabilityResolver | Callable[..., Reachability] | None = None,
) -> Reachability:
    """Resolve one node's liveness, through ``resolver`` when linked.

    Without a resolver this is cached mode and the honest answer is
    :data:`UNKNOWN` — a snapshot cannot know. A resolver that raises is reported
    as :data:`OFFLINE` with the reason attached, because a transport failure is
    exactly what "not reachable" means; it is not an error to propagate up into
    a directory render.
    """
    if resolver is None:
        return dns_reachability(msn_id, dns)
    call = resolver.resolve if hasattr(resolver, "resolve") else resolver
    try:
        return call(msn_id, dns=dns)
    except Exception as exc:  # a transport failure IS the answer, not an error to raise
        return Reachability(
            msn_id=msn_id, status=OFFLINE, address=dns, detail=f"{type(exc).__name__}: {exc}"
        )


__all__ = [
    "LIVE",
    "OFFLINE",
    "UNKNOWN",
    "Reachability",
    "ReachabilityResolver",
    "dns_reachability",
    "is_live",
]
