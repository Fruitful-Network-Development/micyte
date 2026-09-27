"""Adapter: ``AuthoritativeDatumDocument`` (the repo's raw-row model) → ``MssDatum``
closures the binary MSS codec can encode.

A document's datums reference the shared anthology base (rudis ``0-0-*`` + the
abstraction ladder) and other sandbox documents, so a document's canonical MSS is
its **transitive downward reference closure resolved against the tenant catalog**,
reindexed into an isolated anthology (per ``docs/contracts/mss_binary_sequence/``).
Validated read-only against the live ``fnd`` corpus: **163/163 documents round-trip**
through encode→decode.

**A closure resolves from its own document first.** A datum address is a
*document-local coordinate* — layer/value-group/iteration — and the live corpus has
7,241 addresses that two or more documents each claim as their own (7,056 of them at
layer 4: sibling monthly lot documents all number their lots ``4-1-N``). A single
tenant-wide address→row map therefore cannot answer "what is 4-1-1" without picking
one document's answer for every other document too, which is what
:func:`build_catalog_index` does and must keep doing: it is the right answer for the
**461,806** references that genuinely cross documents (the shared base above all).
It is the wrong answer for the addresses a document carries itself. So
:func:`document_closure_to_mss` resolves through :func:`document_scoped_index` — the
document's own rows, then its anchor rows, then the catalog — and the tenant index is
consulted only for what the document does not carry. Before that rule existed, 627 of
630 live documents hashed a closure containing other documents' rows: a county
boundary's 25-datum closure held 13 datums it did not contain.

Raw-row grammar parsed here: ``raw = [[address, t0, t1, …], [title]]``.
  - leading ``~`` ⇒ refs-only (the trailing tokens are references / a collection),
  - otherwise tuple-bearing: the trailing tokens pair as ``(reference, magnitude)``.
Reference tokens are datum addresses or ``rf.<addr>`` markers; magnitudes are
carried through the **injective** ``(kind, magnitude)`` codec in
``core/mss/magnitude.py``, so the original token is recoverable rather than merely
comparable. The ``[title]`` slot is carried too — v2 read ``raw[0]`` only and
dropped it silently.

Dangling references (addresses absent from the catalog), upward references, and
malformed tokens are dropped and counted in :class:`MssAdapterReport` — they are
stale/legacy data (~0.5% of references), never silently mangled.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from micyte.core.datum_semantics.engine import (
    is_datum_address,
    parse_datum_address,
)

from .document_codec import MssDatum, MssTuple
from .magnitude import encode_magnitude


def _strip_rf(token: Any) -> Any:
    return token[3:] if isinstance(token, str) and token.startswith("rf.") else token


def _coerce_magnitude(token: Any) -> int | None:
    """The **superseded** v2 projection, kept only as executable documentation.

    This is the non-injective function that lost 28.7% of the live corpus's head
    values: an 8-bit-aligned ``0``/``1`` string is ``.isdigit()``, so it took the
    decimal branch and its leading zero was destroyed. Nothing calls it any more —
    the adapter uses :func:`core.mss.magnitude.encode_magnitude`. It survives so
    the regression tests can demonstrate the loss they exist to prevent.
    """
    if isinstance(token, bool):
        return int(token)
    if isinstance(token, int):
        return token
    if isinstance(token, str):
        if token.lstrip("-").isdigit():
            return int(token)
        if token and set(token) <= {"0", "1"}:
            return int(token, 2)
        # Literal text → its canonical byte value (the lens-decoded form is display).
        return int.from_bytes(token.encode("utf-8"), "big") if token else 0
    return None


@dataclass
class MssAdapterReport:
    dropped_dangling: int = 0      # reference to an address absent from the catalog
    dropped_upward: int = 0        # reference to an equal/higher layer (not downward)
    dropped_malformed: int = 0     # non-address token / odd body / uncoercible magnitude
    documents: int = 0
    datums: int = 0


@dataclass(frozen=True)
class CatalogEntry:
    """One indexed row: its head tokens and its title slot.

    v2 indexed the head alone, which is why ``raw[1]`` was never encoded. The
    title travels with the head now so the closure can carry it.
    """

    head: list[Any]
    title: str | None = None


def _row_head(raw: Any) -> list[Any] | None:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return None


def _row_title(raw: Any) -> str | None:
    """The ``[title]`` slot of ``raw = [[address, …], [title]]``.

    Tolerant of both the documented list form and a bare string, because the
    corpus holds both; anything else is treated as no title rather than guessed
    at.
    """
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    slot = raw[1]
    if isinstance(slot, str):
        return slot
    if isinstance(slot, list) and slot and isinstance(slot[0], str):
        return slot[0]
    return None


def _absorb(index: dict[str, CatalogEntry], rows: Any) -> dict[str, CatalogEntry]:
    """Absorb one row sequence into ``index``, first occurrence winning.

    Shared by the tenant index and the per-document view so the two cannot drift on
    what counts as an indexable row — a divergence there would show up as a hash that
    moves for no reason anyone could name.
    """
    for row in rows or ():
        address = row.datum_address
        if is_datum_address(address) and address not in index:
            head = _row_head(row.raw)
            if head is not None:
                index[address] = CatalogEntry(head=head, title=_row_title(row.raw))
    return index


def build_catalog_index(catalog: Any) -> dict[str, CatalogEntry]:
    """Address → :class:`CatalogEntry` across every document in the catalog (rows +
    anchor_rows; first occurrence wins). The shared anthology base appears as the
    ``anchor_rows`` of many documents, so this resolves cross-document references.

    Tenant-wide is what this is *for*, and it stays that way. Where two documents claim
    the same address it necessarily answers for one of them; a document that wants its
    own answer asks through :func:`document_scoped_index`.
    """
    index: dict[str, CatalogEntry] = {}
    for document in catalog.documents:
        _absorb(index, document.rows)
        _absorb(index, getattr(document, "anchor_rows", ()) or ())
    return index


def document_local_index(document: Any) -> dict[str, CatalogEntry]:
    """Address → entry from ONE document's rows and anchor rows — what its closure can
    resolve without the tenant catalog. The write path uses this: reading the catalog
    to hash one document costs the 139 MB blob the append door exists to avoid."""
    index: dict[str, CatalogEntry] = {}
    _absorb(index, getattr(document, "rows", ()) or ())
    _absorb(index, getattr(document, "anchor_rows", ()) or ())
    return index


def binary_identity(document: Any) -> dict[str, Any]:
    """The document's ``mos.mss_binary_v3`` hash over its self-resolved closure, with the
    count of references the closure could not carry. ``dropped`` of all zeros means the
    encoding is lossless for this document; anything else names what the id flip
    (TASK-2026-09-17-001) still has to resolve for it."""
    from .document_codec import MSS_DOC_POLICY, encode_document, reindex_into_isolated_anthology

    report = MssAdapterReport()
    closure = document_closure_to_mss(document, index=document_local_index(document), report=report)
    canonical, _address_map = reindex_into_isolated_anthology(closure)
    encoded = encode_document(canonical)
    return {
        "policy": MSS_DOC_POLICY,
        "mss_hash": encoded.hash,
        "datums": len(canonical),
        "dropped": {
            "dangling": report.dropped_dangling,
            "upward": report.dropped_upward,
            "malformed": report.dropped_malformed,
        },
    }


class DocumentScopedIndex(Mapping[str, CatalogEntry]):
    """The catalog index as ONE document sees it: its own rows in front.

    A view, not a merge. ``{**index, **own}`` would copy 45,842 entries per closure and
    the coherence gate builds 1,417 of them — two dict lookups per address beat 64
    million inserts.
    """

    __slots__ = ("_index", "_own")

    def __init__(self, own: dict[str, CatalogEntry], index: Mapping[str, CatalogEntry]):
        self._own = own
        self._index = index

    def __getitem__(self, address: str) -> CatalogEntry:
        entry = self._own.get(address)
        return entry if entry is not None else self._index[address]

    def __contains__(self, address: object) -> bool:
        return address in self._own or address in self._index

    def __iter__(self) -> Iterator[str]:
        yield from self._own
        for address in self._index:
            if address not in self._own:
                yield address

    def __len__(self) -> int:
        return len(self._own) + sum(1 for a in self._index if a not in self._own)

    def carries(self, address: str) -> bool:
        """Whether the DOCUMENT holds this address itself, rather than the catalog
        answering for it. The question a publisher has to ask before claiming a datum
        came from a document — and the same one this view answers when it resolves."""
        return address in self._own


def document_scoped_index(
    document: Any, index: Mapping[str, CatalogEntry]
) -> DocumentScopedIndex:
    """``document``'s own rows, then its anchor rows, then ``index``.

    Anchor rows are part of the document and are preferred for the same reason its
    rows are: ``registrar/3-2-3-17-77-1-1`` carries ``1-1-1`` as *HOPS-spacial* while
    ``system/anthology`` won that address with *HOPS-chornological*. Reading through the
    winner would put a row the document does not contain into the hash that identifies
    it. The precedence inside the document — rows before its own anchor rows — is the
    one :func:`build_catalog_index` already applies.
    """
    own = _absorb({}, document.rows)
    _absorb(own, getattr(document, "anchor_rows", ()) or ())
    return DocumentScopedIndex(own, index)


def _resolve_ref(
    token: Any, layer: int, index: Mapping[str, CatalogEntry], report: MssAdapterReport
) -> str | None:
    """Strip an ``rf.`` marker and validate a reference: it must be a datum address,
    present in the catalog, and strictly downward. Drops are counted in ``report``;
    returns the clean address or ``None``."""
    ref = _strip_rf(token)
    if not is_datum_address(ref):
        report.dropped_malformed += 1
        return None
    if ref not in index:
        report.dropped_dangling += 1
        return None
    if parse_datum_address(ref)[0] >= layer:
        report.dropped_upward += 1
        return None
    return ref


def _parse_row(
    address: str, entry: CatalogEntry, index: Mapping[str, CatalogEntry],
    report: MssAdapterReport,
):
    coords = parse_datum_address(address)
    layer = coords[0]
    body = entry.head[1:]
    title = entry.title
    deps: list[str] = []
    if body and body[0] == "~":
        for token in body[1:]:
            ref = _resolve_ref(token, layer, index, report)
            if ref is not None:
                deps.append(ref)
        return MssDatum(*coords, refs=tuple(deps), title=title), deps
    if len(body) % 2:
        report.dropped_malformed += 1
    tuples: list[MssTuple] = []
    for i in range(0, len(body) - 1, 2):
        ref = _resolve_ref(body[i], layer, index, report)
        if ref is None:
            continue
        encoded = encode_magnitude(body[i + 1])
        if encoded is None:
            report.dropped_malformed += 1
            continue
        kind, magnitude = encoded
        tuples.append(MssTuple(ref, kind, magnitude))
        deps.append(ref)
    if tuples:
        return MssDatum(*coords, tuples=tuple(tuples), title=title), deps
    return MssDatum(*coords, refs=(), title=title), deps


def _closure_from_seeds(
    seeds: list[str], index: Mapping[str, CatalogEntry], report: MssAdapterReport
) -> list[MssDatum]:
    """Transitive downward closure of ``seeds`` as ``MssDatum``s, resolved against
    ``index`` — normally a :class:`DocumentScopedIndex`, so the document answers for
    the addresses it carries and the tenant catalog for the rest."""
    out: dict[str, MssDatum] = {}
    work = [a for a in seeds if is_datum_address(a)]
    while work:
        address = work.pop()
        if address in out or address not in index:
            continue
        datum, deps = _parse_row(address, index[address], index, report)
        out[address] = datum
        work.extend(deps)
    report.datums += len(out)
    return list(out.values())


def document_closure_to_mss(
    document: Any, *, index: Mapping[str, CatalogEntry],
    report: MssAdapterReport | None = None,
) -> list[MssDatum]:
    """The document's transitive downward closure as ``MssDatum``s, resolved from the
    document first. Feed the result to
    :func:`core.mss.document_codec.mss_document_hash`."""
    report = report if report is not None else MssAdapterReport()
    scoped = document_scoped_index(document, index)
    seeds = [r.datum_address for r in document.rows if is_datum_address(r.datum_address)]
    closure = _closure_from_seeds(seeds, scoped, report)
    report.documents += 1
    return closure


def datum_closure_to_mss(
    datum_address: str, *, index: Mapping[str, CatalogEntry], document: Any = None,
    report: MssAdapterReport | None = None,
) -> list[MssDatum]:
    """The transitive downward closure of a SINGLE datum as ``MssDatum``s — the
    focus closure whose MSS hash is that datum's **canonical binary hyphae value**.

    ``document`` scopes the resolution the way :func:`document_closure_to_mss` does,
    and a caller that has the containing document should pass it: a bare address is
    genuinely ambiguous when several documents claim it, and without the document this
    answers for whichever one the catalog index happens to hold.
    """
    report = report if report is not None else MssAdapterReport()
    scoped = document_scoped_index(document, index) if document is not None else index
    return _closure_from_seeds([datum_address], scoped, report)


def binary_hyphae_value(
    datum_address: str, *, index: Mapping[str, CatalogEntry], document: Any = None
) -> str:
    """A datum's canonical binary **hyphae value**: the ``sha256:`` MSS hash of its
    downward focus closure (rudi-inclusive). This is the stable, content-derived key
    a hyphae-flag / family-root registry matches against (see ``core/hyphae_flags``
    and ``docs/wiki/60``). Pass ``document`` when the datum is being read as part of
    one — see :func:`datum_closure_to_mss`."""
    from .document_codec import mss_document_hash

    return mss_document_hash(
        datum_closure_to_mss(datum_address, index=index, document=document))


__all__ = [
    "CatalogEntry",
    "DocumentScopedIndex",
    "MssAdapterReport",
    "binary_hyphae_value",
    "binary_identity",
    "build_catalog_index",
    "datum_closure_to_mss",
    "document_closure_to_mss",
    "document_local_index",
    "document_scoped_index",
]
