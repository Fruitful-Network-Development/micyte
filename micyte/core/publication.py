"""Has this datum document been compiled into a resource, and is that copy current?

A datum document becomes a public resource by two separate steps, and conflating
them is how a surface ends up lying:

1. It is **carried in a still** — an ``.mss`` snapshot this instance holds. Being
   in a still is what "compiled into a resource" means; the still is the artifact
   a consumer actually fetches.
2. That still is **listed on the contact card** as public. A held-but-unlisted
   still is *correctly private*, not a mistake, and a surface that nagged about it
   would be wrong.

So the verdict has to distinguish four states, not two — and one of them,
``published_stale``, is the only one an operator can act on and the only one no
timestamp can find. It is decided by comparing the live document's
``version_hash`` against the hash the still recorded for that same document: two
artifacts, two hashes, one comparison. A still that carries an older version of a
document is advertising content the instance no longer has, and consumers reading
it get the old bytes while believing they are current.

This module is PURE over `(documents, stills, public_names)`. It never reads the
filesystem — the caller supplies the decoded stills — so it stays inside the
micyte core and can be exercised without a private directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "HELD_PRIVATE",
    "PUBLISHED_CURRENT",
    "PUBLISHED_STALE",
    "UNPUBLISHED",
    "DocumentPublication",
    "build_publication_index",
]

#: Carried by a still the contact card lists, at the version the store holds now.
PUBLISHED_CURRENT = "published_current"
#: Carried by a listed still, but at a DIFFERENT version than the store holds.
#: The card advertises content this instance has since changed.
PUBLISHED_STALE = "published_stale"
#: Carried by a still this instance holds but does not list. Correctly private.
HELD_PRIVATE = "held_private"
#: In no still at all.
UNPUBLISHED = "unpublished"

_VERDICT_LABEL = {
    PUBLISHED_CURRENT: "public",
    PUBLISHED_STALE: "public · stale",
    HELD_PRIVATE: "held, private",
    UNPUBLISHED: "not compiled",
}


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _bare_hash(value: object) -> str:
    """Strip one ``sha256:`` family marker, lowercased.

    Both spellings occur in the corpus — the documents index stores
    ``sha256:<hex>`` and the MSS identity returns a bare hex — so comparing them
    unnormalized reports every document as stale.
    """
    text = _as_text(value).lower()
    return text[len("sha256:") :] if text.startswith("sha256:") else text


@dataclass(frozen=True)
class DocumentPublication:
    """What became of one document's journey into a resource."""

    verdict: str
    #: Every still carrying this document, listed first.
    stills: tuple[str, ...] = ()
    #: The still the verdict is about, when there is one.
    still: str = ""
    #: The version the still carries, when it differs from the live one.
    still_version_hash: str = ""

    @property
    def label(self) -> str:
        return _VERDICT_LABEL.get(self.verdict, self.verdict)

    @property
    def is_public(self) -> bool:
        return self.verdict in {PUBLISHED_CURRENT, PUBLISHED_STALE}

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "label": self.label,
            "public": self.is_public,
            "still": self.still,
            "stills": list(self.stills),
            "still_version_hash": self.still_version_hash,
        }


def _document_keys(document: Any) -> tuple[str, ...]:
    """Every identity a still might have recorded this document under.

    Exactly two, and the second is the weakest key that is still a DENOTATION:

    * ``id:<document_id>`` — exact, and the only match a still built from the
      current store will need.
    * ``sandbox:<sandbox>/<name>`` — for a still built before the document's
      content changed, since the hash is a segment of the id and so the id moves
      on every edit. A sandbox may hold only one document of a given name, so
      this pair still names one document.

    There is deliberately **no bare-name key**. Six sandboxes in this corpus hold
    a document called ``anchor``; matching on the name alone reported every one of
    them as carried by a still that in fact carries only ``agnet``'s — ten
    confident, entirely false "published, stale" verdicts. A name is not a
    denotation, and a lookup that silently widens into one is worse than a miss:
    a miss says "not published", which is at least a claim someone can check.
    """
    document_id = _as_text(getattr(document, "document_id", ""))
    canonical = _as_text(getattr(document, "canonical_name", "")) or _as_text(
        getattr(document, "document_name", "")
    )
    keys = [f"id:{document_id}"] if document_id else []
    segments = document_id.split(".")
    if len(segments) >= 4 and canonical:
        keys.append(f"sandbox:{segments[2]}/{canonical}")
    return tuple(keys)


def build_publication_index(
    documents: Any,
    *,
    stills: Any,
    public_names: Any = (),
) -> dict[str, DocumentPublication]:
    """``document_id -> DocumentPublication`` for every document in ``documents``.

    ``stills`` is ``{still_name: Still}`` already decoded by the caller.
    ``public_names`` is the contact card's allowlist — the names it lists, nothing
    more. A still absent from it is private, which is a legitimate state.

    Every document gets an entry, including ``unpublished`` ones: a surface that
    only carried the published ones would leave "not published" and "not computed"
    looking identical, and those are different facts.
    """
    public = {_as_text(name) for name in (public_names or ()) if _as_text(name)}

    # key -> [(still_name, recorded_version_hash)], strongest key first at lookup.
    carried: dict[str, list[tuple[str, str]]] = {}
    for still_name, still in dict(stills or {}).items():
        name = _as_text(still_name)
        for entry in tuple(getattr(still, "documents", ()) or ()):
            recorded = _bare_hash(getattr(entry, "version_hash", ""))
            for key in _document_keys(entry):
                carried.setdefault(key, []).append((name, recorded))

    index: dict[str, DocumentPublication] = {}
    for document in tuple(documents or ()):
        document_id = _as_text(getattr(document, "document_id", ""))
        if not document_id:
            continue
        hits: list[tuple[str, str]] = []
        for key in _document_keys(document):
            if key in carried:
                hits = carried[key]
                break
        if not hits:
            index[document_id] = DocumentPublication(verdict=UNPUBLISHED)
            continue

        live_hash = _bare_hash(document_id.rsplit(".", 1)[-1])
        # A still the card lists decides the verdict; a private one only ever
        # yields `held_private`, so a document in both is reported as public.
        names = tuple(dict.fromkeys(name for name, _ in hits))
        listed = [(name, recorded) for name, recorded in hits if name in public]
        if not listed:
            return_still = names[0] if names else ""
            index[document_id] = DocumentPublication(
                verdict=HELD_PRIVATE, stills=names, still=return_still
            )
            continue
        current = next((name for name, recorded in listed if recorded == live_hash), "")
        if current:
            index[document_id] = DocumentPublication(
                verdict=PUBLISHED_CURRENT, stills=names, still=current
            )
            continue
        stale_name, stale_hash = listed[0]
        index[document_id] = DocumentPublication(
            verdict=PUBLISHED_STALE,
            stills=names,
            still=stale_name,
            still_version_hash=stale_hash,
        )
    return index
