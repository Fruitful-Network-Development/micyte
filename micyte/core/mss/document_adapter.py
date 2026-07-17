"""Adapter: ``AuthoritativeDatumDocument`` (the repo's raw-row model) → ``MssDatum``
closures the binary MSS codec can encode.

A document's datums reference the shared anthology base (rudis ``0-0-*`` + the
abstraction ladder) and other sandbox documents, so a document's canonical MSS is
its **transitive downward reference closure resolved across the whole tenant
catalog**, reindexed into an isolated anthology (per
``docs/contracts/mss_binary_sequence/``). Validated read-only against the live
``fnd`` corpus: **163/163 documents round-trip** through encode→decode.

Raw-row grammar parsed here: ``raw = [[address, t0, t1, …], [title]]``.
  - leading ``~`` ⇒ refs-only (the trailing tokens are references / a collection),
  - otherwise tuple-bearing: the trailing tokens pair as ``(reference, magnitude)``.
Reference tokens are datum addresses or ``rf.<addr>`` markers; magnitudes are
decimal, binary-string, or literal (coerced to an integer canonical value).
Dangling references (addresses absent from the catalog), upward references, and
malformed tokens are dropped and counted in :class:`MssAdapterReport` — they are
stale/legacy data (~0.5% of references), never silently mangled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.core.datum_semantics.engine import (
    is_datum_address,
    parse_datum_address,
)

from .document_codec import MssDatum


def _strip_rf(token: Any) -> Any:
    return token[3:] if isinstance(token, str) and token.startswith("rf.") else token


def _coerce_magnitude(token: Any) -> int | None:
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


def _row_head(raw: Any) -> list[Any] | None:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return None


def build_catalog_index(catalog: Any) -> dict[str, list[Any]]:
    """Address → row-head map across every document in the catalog (rows +
    anchor_rows; first occurrence wins). The shared anthology base appears as the
    ``anchor_rows`` of many documents, so this resolves cross-document references."""
    index: dict[str, list[Any]] = {}
    for document in catalog.documents:
        rows = list(document.rows) + list(getattr(document, "anchor_rows", ()) or [])
        for row in rows:
            address = row.datum_address
            if is_datum_address(address) and address not in index:
                head = _row_head(row.raw)
                if head is not None:
                    index[address] = head
    return index


def _resolve_ref(
    token: Any, layer: int, index: dict[str, list[Any]], report: MssAdapterReport
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


def _parse_row(address: str, head: list[Any], index: dict[str, list[Any]], report: MssAdapterReport):
    coords = parse_datum_address(address)
    layer = coords[0]
    body = head[1:]
    deps: list[str] = []
    if body and body[0] == "~":
        for token in body[1:]:
            ref = _resolve_ref(token, layer, index, report)
            if ref is not None:
                deps.append(ref)
        return MssDatum(*coords, refs=tuple(deps)), deps
    if len(body) % 2:
        report.dropped_malformed += 1
    tuples: list[tuple[str, int]] = []
    for i in range(0, len(body) - 1, 2):
        ref = _resolve_ref(body[i], layer, index, report)
        if ref is None:
            continue
        magnitude = _coerce_magnitude(body[i + 1])
        if magnitude is None:
            report.dropped_malformed += 1
            continue
        tuples.append((ref, magnitude))
        deps.append(ref)
    if tuples:
        return MssDatum(*coords, tuples=tuple(tuples)), deps
    return MssDatum(*coords, refs=()), deps


def _closure_from_seeds(
    seeds: list[str], index: dict[str, list[Any]], report: MssAdapterReport
) -> list[MssDatum]:
    """Transitive downward closure of ``seeds`` as ``MssDatum``s, resolved against
    ``index`` (which spans the whole tenant, so cross-document refs resolve)."""
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
    document: Any, *, index: dict[str, list[Any]], report: MssAdapterReport | None = None
) -> list[MssDatum]:
    """The document's transitive downward closure as ``MssDatum``s. Feed the result
    to :func:`core.mss.document_codec.mss_document_hash`."""
    report = report if report is not None else MssAdapterReport()
    seeds = [r.datum_address for r in document.rows if is_datum_address(r.datum_address)]
    closure = _closure_from_seeds(seeds, index, report)
    report.documents += 1
    return closure


def datum_closure_to_mss(
    datum_address: str, *, index: dict[str, list[Any]], report: MssAdapterReport | None = None
) -> list[MssDatum]:
    """The transitive downward closure of a SINGLE datum as ``MssDatum``s — the
    focus closure whose MSS hash is that datum's **canonical binary hyphae value**."""
    report = report if report is not None else MssAdapterReport()
    return _closure_from_seeds([datum_address], index, report)


def binary_hyphae_value(datum_address: str, *, index: dict[str, list[Any]]) -> str:
    """A datum's canonical binary **hyphae value**: the ``sha256:`` MSS hash of its
    downward focus closure (rudi-inclusive). This is the stable, content-derived key
    a hyphae-flag / family-root registry matches against (see ``core/hyphae_flags``
    and ``docs/wiki/60``)."""
    from .document_codec import mss_document_hash

    return mss_document_hash(datum_closure_to_mss(datum_address, index=index))


__all__ = [
    "MssAdapterReport",
    "binary_hyphae_value",
    "build_catalog_index",
    "datum_closure_to_mss",
    "document_closure_to_mss",
]
