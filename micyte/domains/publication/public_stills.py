"""Enforced publication — a datum document is public **iff its contact card says so**.

Not to be confused with the tenant-profile publication in ``service.py`` beside
this file. That one is about an FND grantee's public *profile page*. This one is
the msn contact card's ``public_stills[]`` allowlist: which of an instance's datum
documents may be served to a requester it does not know.

The rule, and why it is a function rather than a convention
-----------------------------------------------------------
**Publication is a card mutation. There is no other publish path.** An operator
cannot make a document public by copying a `.mss` somewhere, because "somewhere"
is not consulted — :func:`is_public` is, and it reads the card.

That is the difference between an enforced rule and a documented one. A rule that
lives in prose gets followed until the day someone drops a file in a served
directory; a rule that lives in the only function authorized to hand a blob out
cannot be bypassed by accident. So the serve path here **fails closed**: an
unknown name is refused, an empty card serves nothing, and there is no "public by
default" branch to get wrong.

The allowlist doubles as the discovery index
--------------------------------------------
Each entry carries the still's ``mss_hash``. A consumer compares the hash it
captured against the one the card advertises and re-pulls the bytes only when
they differ. That is the whole update-check protocol, and it is why the hash
belongs on the card rather than being computed at serve time: a consumer has to
be able to decide *not* to fetch.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

#: The card field this module owns.
PUBLIC_STILLS_FIELD = "public_stills"


class PublicationError(ValueError):
    """A publication request is malformed, or a serve request was refused."""


@dataclass(frozen=True)
class PublishedStill:
    """One entry of ``contact_card.public_stills[]``."""

    name: str
    msn: str
    mss_hash: str
    version: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise PublicationError("a published still needs a name")
        if not self.msn.strip():
            raise PublicationError(f"{self.name}: a published still needs its publisher's msn")
        if not self.mss_hash.strip():
            raise PublicationError(
                f"{self.name}: a published still needs its mss_hash — it is the "
                "update-check index a consumer compares before re-pulling"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "msn": self.msn,
            "mss_hash": self.mss_hash,
            "version": self.version,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> PublishedStill:
        if not isinstance(payload, dict):
            raise PublicationError("a public_stills entry is not an object")
        return cls(
            name=str(payload.get("name", "")),
            msn=str(payload.get("msn", "")),
            mss_hash=str(payload.get("mss_hash", "")),
            version=str(payload.get("version", "")),
            updated_at=str(payload.get("updated_at", "")),
        )


@dataclass(frozen=True)
class ContactCard:
    """The publishable subset of an msn profile, plus its publication allowlist.

    ``active`` is deliberately absent from anything this module writes: it is
    **derived** from contract status, never hand-set, and a publication surface
    that let an operator type it in would turn a relational fact into an opinion.
    """

    msn_id: str
    name: str = ""
    entity_kind: str = ""
    website: str = ""
    public_stills: tuple[PublishedStill, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "msn_id": self.msn_id,
            "name": self.name,
            "entity_kind": self.entity_kind,
            "website": self.website,
            PUBLIC_STILLS_FIELD: [entry.to_dict() for entry in self.public_stills],
        }

    @classmethod
    def from_dict(cls, payload: Any) -> ContactCard:
        if not isinstance(payload, dict):
            raise PublicationError("a contact card is not an object")
        raw = payload.get(PUBLIC_STILLS_FIELD) or []
        if not isinstance(raw, list):
            raise PublicationError(f"{PUBLIC_STILLS_FIELD} is not a list")
        return cls(
            msn_id=str(payload.get("msn_id", "")),
            name=str(payload.get("name", "")),
            entity_kind=str(payload.get("entity_kind", "")),
            website=str(payload.get("website", "")),
            public_stills=tuple(PublishedStill.from_dict(entry) for entry in raw),
        )


def is_public(card: ContactCard, name: str) -> bool:
    """The single authorization predicate. Everything else defers to this."""
    return any(entry.name == name for entry in card.public_stills)


def published(card: ContactCard, name: str) -> PublishedStill | None:
    """The allowlist entry for ``name``, or ``None`` if it is not published."""
    for entry in card.public_stills:
        if entry.name == name:
            return entry
    return None


def publish(card: ContactCard, entry: PublishedStill) -> ContactCard:
    """Add or update an allowlist entry — the only affordance that publishes.

    Re-publishing an existing name **replaces** it in place rather than appending
    a duplicate, so a re-export updates the advertised ``mss_hash`` instead of
    leaving two entries with the same name and different hashes for a consumer to
    choose between.
    """
    if entry.msn != card.msn_id:
        raise PublicationError(
            f"{entry.name}: an instance publishes its own stills — entry msn "
            f"{entry.msn!r} is not the card's {card.msn_id!r}"
        )
    kept = [existing for existing in card.public_stills if existing.name != entry.name]
    kept.append(entry)
    return replace(card, public_stills=tuple(sorted(kept, key=lambda e: e.name)))


def unpublish(card: ContactCard, name: str) -> ContactCard:
    """Remove an entry. Idempotent: unpublishing what is not published is not an error.

    Idempotence is the right shape here — the caller's intent is "this must not be
    public", and that intent is satisfied either way. Raising would make a
    double-click look like a failure.
    """
    return replace(
        card,
        public_stills=tuple(entry for entry in card.public_stills if entry.name != name),
    )


def serve(card: ContactCard, name: str, blobs: dict[str, bytes]) -> bytes:
    """The bytes of a published still, or refuse.

    Fails closed in both directions, and the order matters: the **allowlist** is
    checked first, so a document that happens to be on disk but is not published
    is refused as *not public* rather than leaking its existence through a
    different error. Only then is the blob looked up.
    """
    entry = published(card, name)
    if entry is None:
        raise PublicationError(
            f"{name!r} is not published — a datum document is public only while "
            "its contact card lists it"
        )
    blob = blobs.get(name)
    if blob is None:
        raise PublicationError(
            f"{name!r} is listed on the card but its bytes are missing — the "
            "allowlist and the exported stills have drifted"
        )
    return blob


def catalog(card: ContactCard) -> list[dict[str, Any]]:
    """The public listing an unidentified requester may read.

    Exactly the allowlist, nothing derived from local state — the card *is* the
    published surface, so serving anything more here would publish by a second
    path and break the one-path rule.
    """
    return [entry.to_dict() for entry in card.public_stills]


def drift(card: ContactCard, available: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(listed_but_missing, held_but_unpublished)`` — what the operator should see.

    Both halves are worth surfacing and neither is an error. The first is a
    broken promise: consumers will ask for something that cannot be served. The
    second is just privacy — a held-but-unlisted document is correctly private,
    and the surface should say so rather than nagging.
    """
    held = set(available)
    listed = {entry.name for entry in card.public_stills}
    return tuple(sorted(listed - held)), tuple(sorted(held - listed))


__all__ = [
    "PUBLIC_STILLS_FIELD",
    "ContactCard",
    "PublicationError",
    "PublishedStill",
    "catalog",
    "drift",
    "is_public",
    "publish",
    "published",
    "serve",
    "unpublish",
]
