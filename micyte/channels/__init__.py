"""Hosted channels — an instance's outward-facing resource interfaces.

The third member of the component taxonomy (hosted-channel convention
2026-08-02 §1), beside :mod:`micyte.tools` (surfaces offered against the
document in focus) and :mod:`micyte.automation` (condition-triggered writers):

* a TOOL is engaged by the operator against their own data;
* a ROUTINE runs unattended and writes;
* a CHANNEL is a session surface the OUTSIDE world engages — open (any caller)
  or closed (contract-holding instances) — terminating at a sandbox this
  instance hosts for it.

A channel is deliberately panel-shaped (`build_panel_payload`, same call shape
as a tool) so the operator views their channel through the same overlay the
palette already opens — the internal rendering and the public session serve
one payload from one builder, and the two cannot drift. What a channel is NOT:

* routed — it carries no ``route`` and no surface id; engagement happens from
  the interface search and the rail's channel section, never a bookmark;
* a writer — a channel declares no writes, and the open session routes are
  GET-only by construction (an anonymous request resolves to the operator
  identity, so "no write path exists" is the only safe posture).

The register enforces the taxonomy both ways, exactly as the other two do: a
tool or routine landing here is refused, and the mirror refusals live in
:func:`micyte.tools.register` / :func:`micyte.automation.register`.

The Protocol is ``runtime_checkable`` and :func:`register` isinstance-checks
it, so — the standing trap — a NEW attribute added to the Protocol later
un-registers every channel that lacks it. Grow the contract with ``getattr``
defaults, never with new Protocol members (see ``micyte/tools/_contract.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

ACCESS_CLASSES = ("open", "closed")


@runtime_checkable
class HostedChannel(Protocol):
    """Protocol every hosted channel implements."""

    channel_id: str
    label: str
    summary: str
    #: "open" (any outside party) or "closed" (contract-gated instances).
    access: str
    #: The channel's own sandbox on the hosting instance (anchor + channel_profile
    #: + sources; the positive kind marker, never inferred).
    sandbox: str
    #: The session's tab vocabulary, in display order.
    tabs: tuple[str, ...]

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        """Return the session payload (container-dispatched, like a tool panel)."""
        ...


# channel_id -> HostedChannel instance.
CHANNEL_REGISTRY: dict[str, HostedChannel] = {}


def register(channel: HostedChannel) -> HostedChannel:
    """Add a channel to the registry, or raise. Returns the channel for fluent use."""
    if not isinstance(channel, HostedChannel):
        raise TypeError(
            f"register() expected a HostedChannel, got {type(channel).__name__}"
        )
    if hasattr(channel, "tool_id"):
        raise TypeError(
            f"{getattr(channel, 'tool_id', '?')!r} declares tool_id: a surface offered "
            "against the document in focus belongs in micyte.tools. Registering it here "
            "would offer it to the outside world."
        )
    if hasattr(channel, "routine_id"):
        raise TypeError(
            f"{getattr(channel, 'routine_id', '?')!r} declares routine_id: a "
            "condition-triggered writer belongs in micyte.automation. A channel "
            "writes nothing."
        )
    if hasattr(channel, "route"):
        raise TypeError(
            f"{channel.channel_id!r} declares a route: a channel is engaged from the "
            "interface search and the rail, never bookmarked — no route, no surface id "
            "(the 2026-06-05 no-new-root-surfaces ruling)."
        )
    if getattr(channel, "writes", ()):
        raise TypeError(
            f"{channel.channel_id!r} declares writes: a channel is read-only by "
            "construction. Its open sessions carry the operator's identity for an "
            "anonymous caller, so the only safe write path is none."
        )
    if channel.access not in ACCESS_CLASSES:
        raise ValueError(
            f"{channel.channel_id!r} declares access={channel.access!r}; "
            f"expected one of {ACCESS_CLASSES}."
        )
    CHANNEL_REGISTRY[channel.channel_id] = channel
    return channel


def get(channel_id: str) -> HostedChannel | None:
    """Look up a channel by id, or None when absent."""
    return CHANNEL_REGISTRY.get(channel_id)


def all_channels() -> list[HostedChannel]:
    """Every registered channel, sorted by channel_id for stability."""
    return [CHANNEL_REGISTRY[k] for k in sorted(CHANNEL_REGISTRY)]


def open_channels() -> list[HostedChannel]:
    """The channels any outside party may engage — the public allowlist's source."""
    return [c for c in all_channels() if c.access == "open"]


def channel_ids() -> tuple[str, ...]:
    return tuple(sorted(CHANNEL_REGISTRY))


from . import agnet as _agnet  # noqa: E402,F401  (self-registration)
from . import convention as _convention  # noqa: E402,F401  (self-registration)
from . import grantor as _grantor  # noqa: E402,F401  (self-registration)

# ONE closed channel is instantiated: `grantor` (2026-08-21), FND's hosting
# relationship served as a channel — closed because it is served per ALIAS, never
# to the world. `county_line_records` was closed too (hosted by FND on
# behalf of an entity with no instance of its own) and was retired 2026-08-04: the
# instance's posture is one open channel until a counterparty exists to engage a
# closed one. `ACCESS_CLASSES` still carries "closed" and `register` still accepts
# it — the taxonomy is emptied of a member, not narrowed. The transport stays
# proven by `fnd_app/tests/_channel_fixtures.py`, which registers its own.
