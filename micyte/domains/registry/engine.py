"""The browser engine: where the registry comes from, and what unlocks the live one.

Two modes, one gate
-------------------
An instance with no contract is **not** cut off from the registry. It reads the
authority instance's published still — a `.mss` snapshot, browsable with no
authority database of its own. That is ``cached`` mode, and it is available to
everyone.

To be *findable by others*, or to have the browser track the shifting IP of a
running instance that has no DNS, the operator switches to ``linked``. That
switch is gated on exactly one thing: **a held contract with the authority
instance**. Not on hosting, not on uptime, not on where the instance runs.
Substrate is irrelevant to standing — a laptop with a contract is a full linked
member, and an always-on hosted instance without one browses the same snapshot as
everybody else.

Why the gate is a function and not a flag
-----------------------------------------
``linked`` is derived from contract state on every read, never stored. A stored
"is linked" boolean would go stale the moment a contract was revoked, and the
failure would be silent and in the permissive direction. Deriving it means a
revoked contract closes the door on the next look.

The authority instance is a **parameter**, not a constant. FND is the authorized
registrar today, but the platform is domain-agnostic and the standardization is
opt-in: a deployment that answers to a different registrar, or to none, must not
need a code change. Hard-coding the msn here would quietly make the network
module mandatory.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from micyte.core.mss.envelope import KIND_DOCUMENT_SET, MssEnvelopeError, peek_kind
from micyte.core.mss.still import Still, decode_still, still_to_documents, verify_still
from micyte.core.references import ReferenceGrant

#: What a contract with the authority instance *is*, in the vocabulary of §11b.
#: Recorded here so a reader of the code meets the term where the gate lives.
AUTHORITY_ROLE = "authorized registrar"


class EngineMode(StrEnum):
    """How the browser sources the registry."""

    CACHED = "cached"
    LINKED = "linked"


@dataclass(frozen=True)
class RegistrySource:
    """Where a directory came from — provenance the operator can see.

    A cached directory is a *snapshot of a moment*, and a browser that hides
    that invites the operator to read stale data as live. So the source travels
    with the directory rather than being reconstructable only from a filename.
    """

    mode: EngineMode
    source_msn: str = ""
    name: str = ""
    created_at: str = ""
    document_count: int = 0
    #: ``compute_mss_hash`` per document — the cheap update-check index a
    #: consumer compares against the publisher's contact card before re-pulling.
    version_hashes: tuple[tuple[str, str], ...] = ()
    #: Non-empty when the still's carried rows did not re-hash to their recorded
    #: identity. A directory with problems is still browsable; it is just not
    #: provably faithful, and the surface must say so.
    integrity_problems: tuple[str, ...] = ()

    @property
    def is_faithful(self) -> bool:
        return not self.integrity_problems


@dataclass(frozen=True)
class RegistryDirectory:
    """Reconstructed documents plus where they came from.

    ``documents`` are ordinary ``AuthoritativeDatumDocument`` objects, so every
    existing payload builder works over a cached directory unchanged — that is
    the whole point of carrying a still faithfully rather than inventing a
    directory format.

    View-state only. The still contract forbids loading a still into MOS: a
    snapshot is transport, never truth.
    """

    documents: tuple[Any, ...]
    source: RegistrySource


def authority_contract(
    grants: Iterable[ReferenceGrant], *, self_msn_id: str, authority_msn_id: str
) -> ReferenceGrant | None:
    """The held contract with the authority instance, if there is a live one.

    "Held" means *this* instance is the consumer and the authority is the owner,
    and the contract has not been refused. A grant the other way round — the
    authority reading this instance — is a different relationship and does not
    unlock the live registry here.
    """
    if not self_msn_id or not authority_msn_id or self_msn_id == authority_msn_id:
        return None
    for grant in grants:
        if (
            grant.consumer_msn_id == self_msn_id
            and grant.owner_msn_id == authority_msn_id
            and not grant.is_refused
        ):
            return grant
    return None


def resolve_engine_mode(
    grants: Iterable[ReferenceGrant],
    *,
    self_msn_id: str,
    authority_msn_id: str,
    requested: EngineMode | str | None = None,
) -> tuple[EngineMode, str]:
    """``(mode, why)`` — the mode the browser may actually run in.

    ``requested`` is the operator's toggle. It can always fall *back* to cached
    (a linked-capable instance may choose a snapshot), but it can never grant
    linked: without the contract, linked is refused and the reason is returned
    rather than silently downgraded. A UI that shows "linked" while serving a
    snapshot is worse than one that shows neither.
    """
    contract = authority_contract(
        grants, self_msn_id=self_msn_id, authority_msn_id=authority_msn_id
    )
    wanted = EngineMode(requested) if requested else None

    # The authority instance holds the registry itself, which is strictly more
    # than a contract with the authority grants. Without this it read as
    # "no contract with the authorized registrar" — not merely unhelpful but
    # false, and it left the registrar's own browser empty while every other
    # instance could browse the snapshot it publishes.
    #
    # This is NOT a third mode. `linked` already means "the live registry"; the
    # only thing that differs is that the gate is satisfied by identity rather
    # than by a grant.
    if self_msn_id and self_msn_id == authority_msn_id:
        if wanted is EngineMode.CACHED:
            return EngineMode.CACHED, (
                "this instance IS the authorized registrar, but the operator "
                "selected a published snapshot"
            )
        return EngineMode.LINKED, (
            f"this instance IS the {AUTHORITY_ROLE} ({authority_msn_id}) — its "
            "registry is local, so there is no contract to hold"
        )

    if contract is None:
        if wanted is EngineMode.LINKED:
            return EngineMode.CACHED, (
                f"linked mode needs a held contract with the {AUTHORITY_ROLE} "
                f"({authority_msn_id}); this instance holds none, so the browser "
                "is reading a published still"
            )
        return EngineMode.CACHED, (
            "no contract with the authorized registrar — browsing its published "
            "still, which needs no contract"
        )

    if wanted is EngineMode.CACHED:
        return EngineMode.CACHED, (
            f"linked is available (contract {contract.contract_id or '?'}) but the "
            "operator selected the cached snapshot"
        )
    return EngineMode.LINKED, (
        f"held contract with the {AUTHORITY_ROLE} ({authority_msn_id})"
        + (f" — {contract.contract_id}" if contract.contract_id else "")
    )


def directory_from_documents(
    documents: Iterable[Any], *, mode: EngineMode = EngineMode.LINKED
) -> RegistryDirectory:
    """A directory sourced from documents already in hand (the live MOS path)."""
    docs = tuple(documents)
    return RegistryDirectory(
        documents=docs,
        source=RegistrySource(mode=mode, document_count=len(docs)),
    )


def _directory_from_still(still: Still, *, verify: bool) -> RegistryDirectory:
    problems = tuple(verify_still(still)) if verify else ()
    return RegistryDirectory(
        documents=tuple(still_to_documents(still)),
        source=RegistrySource(
            mode=EngineMode.CACHED,
            source_msn=still.source_msn,
            name=still.name,
            created_at=still.created_at,
            document_count=len(still.documents),
            version_hashes=tuple(
                (d.document_name, d.version_hash) for d in still.documents
            ),
            integrity_problems=problems,
        ),
    )


def directory_from_mss(blob: bytes, *, verify: bool = True) -> RegistryDirectory:
    """Load a cached directory from a published `.mss`.

    ``verify`` re-derives every carried document's version hash and records any
    drift on the source rather than raising. That distinction is deliberate: a
    still whose rows no longer match its recorded identity is *suspect*, not
    unreadable, and refusing to render it would leave the operator with nothing
    to inspect. The surface shows the warning; the decision stays with them.

    A blob of the wrong kind, by contrast, IS refused — the header declares it,
    so there is nothing to weigh up.
    """
    kind = peek_kind(blob)
    if kind != KIND_DOCUMENT_SET:
        raise MssEnvelopeError(
            "a registry directory is a document_set .mss; this blob declares kind "
            f"{kind}"
        )
    return _directory_from_still(decode_still(blob), verify=verify)


__all__ = [
    "AUTHORITY_ROLE",
    "EngineMode",
    "RegistryDirectory",
    "RegistrySource",
    "authority_contract",
    "directory_from_documents",
    "directory_from_mss",
    "resolve_engine_mode",
]
