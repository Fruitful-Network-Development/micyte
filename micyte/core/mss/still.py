"""Still — a full, content-addressed snapshot of datum documents for interchange.

A **still** (``stl.<msn>.<name>``) is the *full* snapshot form of the
still/capture/live contract: an immutable, API-servable, content-addressed copy of
one or more datum documents. It is **transport, not truth** — MOS ``lv.`` remains
the only canonical runtime form, and a still is never loaded whole into MOS
(``knowledge/still_capture_live_contract.md`` §3–§5). Browsing a still is
view-state only.

A still is the ``.mss`` :data:`~core.mss.envelope.KIND_DOCUMENT_SET` payload
--------------------------------------------------------------------------
The container is no longer this module's own: framing, bounded decompression and
the trust-boundary guards all live in ``core/mss/envelope.py``, and a still is
simply the document-set payload carried inside it. That consolidation is the
point — one format, one decoder, a declared kind — and it replaces the private
``MSTL`` framing this module shipped first. Legacy ``MSTL`` blobs still decode,
because one was published before the consolidation.

Why the rows are carried **verbatim**
-------------------------------------
The still contract makes *role* (``stl.``) and *codec* orthogonal: an MSS-binary
still and a human-readable still are both legal (contract §3). This module
carries rows exactly as the document holds them, for two reasons that outlast the
magnitude fix:

1. **Faithfulness is provable.** Each document records its ``compute_mss_hash``
   version hash, which hashes the raw rows — so re-hashing a decoded document
   must reproduce the recorded hash, and the same hash is the cheap update-check
   index the contact card publishes (contract §6).
2. **A still is self-contained.** The MSS bitstream form encodes a *closure*
   resolved across the whole tenant catalog; a snapshot of eight documents cannot
   always supply that closure. Rows carry without it.

Historically there was a third reason, now retired: the MSS magnitude path used
to be lossy for exactly the values a directory reads (2,297 of 8,003 live head
values unrecoverable — the leading zero of an 8-bit-aligned bit-string was
destroyed). ``core/mss/magnitude.py`` made that projection injective, so the
bitstream is no longer a lossy option — it is merely the wrong shape for a
snapshot.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)

from .datum_identity import compute_mss_hash
from .envelope import (
    KIND_DOCUMENT_SET,
    MSS_MAX_DECOMPRESSED_BYTES,
    MssEnvelopeError,
    canonical_json,
    decode_envelope,
    encode_envelope,
    frame_compressed,
)

STILL_POLICY = "mos.still_v1"
STILL_SCHEMA = "mycite.v2.mos.still.v1"

#: **Legacy** framing, superseded by the ``.mss`` envelope. One artifact was
#: published under it, so :func:`decode_still` still reads it; nothing writes it.
STILL_MAGIC = b"MSTL"
STILL_FORMAT_VERSION = 1

#: Retained name for the envelope's ceiling, so existing callers keep working.
STILL_MAX_DECOMPRESSED_BYTES = MSS_MAX_DECOMPRESSED_BYTES

#: One format, one error type. The name survives the consolidation because it
#: reads better at still call sites, but a still container error and a ``.mss``
#: container error are now the same thing — which is the whole point.
StillFormatError = MssEnvelopeError


@dataclass(frozen=True)
class StillDocument:
    """One document inside a still, carried faithfully.

    ``rows``/``anchor_rows`` are ``[{"datum_address": …, "raw": …}]`` — the raw
    row payload verbatim, so ``version_hash`` re-derives exactly.
    """

    document_id: str
    document_name: str
    source_kind: str
    relative_path: str = ""
    canonical_name: str = ""
    tool_id: str = ""
    document_metadata: dict[str, Any] | None = None
    rows: tuple[dict[str, Any], ...] = ()
    anchor_rows: tuple[dict[str, Any], ...] = ()
    version_hash: str = ""


@dataclass(frozen=True)
class Still:
    """A snapshot of one or more documents published by ``source_msn``."""

    source_msn: str
    name: str
    documents: tuple[StillDocument, ...] = ()
    created_at: str = ""
    schema: str = STILL_SCHEMA
    policy: str = STILL_POLICY


# --------------------------------------------------------------------------- #
# Row normalization
# --------------------------------------------------------------------------- #
def _row_to_dict(row: Any) -> dict[str, Any] | None:
    """``AuthoritativeDatumDocumentRow`` | dict → the carried row shape.

    ``AuthoritativeDatumDocument.rows`` is typed to hold either, so both are
    accepted. Returns ``None`` for a row with no datum address; the caller
    decides what that means (see :func:`_rows_of` — it is a hard error).
    """
    if isinstance(row, AuthoritativeDatumDocumentRow):
        address, raw = row.datum_address, row.raw
    elif isinstance(row, dict):
        address, raw = row.get("datum_address", ""), row.get("raw")
    else:
        address, raw = getattr(row, "datum_address", ""), getattr(row, "raw", None)
    if not isinstance(address, str) or not address:
        return None
    return {"datum_address": address, "raw": raw}


def _rows_of(document: Any, attribute: str) -> tuple[dict[str, Any], ...]:
    """Carry every row, or refuse.

    An address-less row cannot be carried (nothing addresses it on the far
    side), but silently dropping it would make the recorded ``version_hash`` a
    hash of *fewer rows than the source document has* — so it would no longer
    equal the hash the publishing instance advertises on its contact card, and
    every consumer's update-check would read as permanent drift. A still that
    cannot be faithful must fail loudly at build time instead.
    """
    out: list[dict[str, Any]] = []
    for index, row in enumerate(getattr(document, attribute, ()) or ()):
        carried = _row_to_dict(row)
        if carried is None:
            raise StillFormatError(
                f"{getattr(document, 'document_name', '?')}: {attribute}[{index}] has no "
                "datum_address — refusing to drop it, as the recorded version_hash would "
                "then not match the source document's published hash"
            )
        out.append(carried)
    return tuple(out)


def _carried_rows(value: Any, *, document_name: str, field: str) -> tuple[dict[str, Any], ...]:
    """Validate and normalize the row list read out of a decoded payload.

    A still is read from *another* instance, so its grammar is checked rather
    than trusted: a malformed row must surface as :class:`StillFormatError` here,
    not as a ``KeyError`` from deep inside a payload builder later. Normalizing
    to exactly ``{datum_address, raw}`` also drops any foreign extra keys, so a
    decoded still re-encodes to the same canonical bytes.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        raise StillFormatError(f"{document_name}: {field} is not a list")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise StillFormatError(f"{document_name}: {field}[{index}] is not an object")
        address = row.get("datum_address")
        if not isinstance(address, str) or not address:
            raise StillFormatError(
                f"{document_name}: {field}[{index}] has no datum_address"
            )
        out.append({"datum_address": address, "raw": row.get("raw")})
    return tuple(out)


# --------------------------------------------------------------------------- #
# Build / reconstruct
# --------------------------------------------------------------------------- #
def build_still_document(document: Any) -> StillDocument:
    """Snapshot one ``AuthoritativeDatumDocument``, recording its version hash."""
    rows = _rows_of(document, "rows")
    metadata = getattr(document, "document_metadata", None) or {}
    identity = compute_mss_hash(
        AuthoritativeDatumDocument(
            document_id=str(getattr(document, "document_id", "")),
            source_kind=str(getattr(document, "source_kind", "")),
            document_name=str(getattr(document, "document_name", "")),
            relative_path=str(getattr(document, "relative_path", "")),
            document_metadata=dict(metadata),
            rows=tuple(
                AuthoritativeDatumDocumentRow(
                    datum_address=r["datum_address"], raw=r["raw"]
                )
                for r in rows
            ),
        )
    )
    return StillDocument(
        document_id=str(getattr(document, "document_id", "")),
        document_name=str(getattr(document, "document_name", "")),
        source_kind=str(getattr(document, "source_kind", "")),
        relative_path=str(getattr(document, "relative_path", "")),
        canonical_name=str(getattr(document, "canonical_name", "")),
        tool_id=str(getattr(document, "tool_id", "")),
        document_metadata=dict(metadata),
        rows=rows,
        anchor_rows=_rows_of(document, "anchor_rows"),
        version_hash=str(identity["version_hash"]),
    )


def build_still(
    documents: list[Any], *, source_msn: str, name: str, created_at: str = ""
) -> Still:
    """Snapshot ``documents`` into a still published by ``source_msn``.

    ``created_at`` is passed in rather than sampled so a still is reproducible:
    the same documents must produce the same bytes.
    """
    return Still(
        source_msn=source_msn,
        name=name,
        created_at=created_at,
        documents=tuple(build_still_document(d) for d in documents),
    )


def still_document_to_document(entry: StillDocument) -> AuthoritativeDatumDocument:
    """Reconstruct the ``AuthoritativeDatumDocument`` a still document carries.

    The result is view-state only — the still contract forbids loading a still
    into MOS (§4 rule 2, §5).
    """
    return AuthoritativeDatumDocument(
        document_id=entry.document_id,
        source_kind=entry.source_kind,
        document_name=entry.document_name,
        relative_path=entry.relative_path,
        canonical_name=entry.canonical_name,
        tool_id=entry.tool_id,
        document_metadata=dict(entry.document_metadata or {}),
        rows=tuple(
            AuthoritativeDatumDocumentRow(datum_address=r["datum_address"], raw=r["raw"])
            for r in entry.rows
        ),
        anchor_rows=tuple(
            AuthoritativeDatumDocumentRow(datum_address=r["datum_address"], raw=r["raw"])
            for r in entry.anchor_rows
        ),
    )


def still_to_documents(still: Still) -> list[AuthoritativeDatumDocument]:
    """Every document in the still, reconstructed. Feed straight to a payload
    builder (e.g. ``tools.network_map_viewer.build_network_map_payload``)."""
    return [still_document_to_document(entry) for entry in still.documents]


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #
def _still_to_payload(still: Still) -> dict[str, Any]:
    return {
        "schema": still.schema,
        "policy": still.policy,
        "source_msn": still.source_msn,
        "name": still.name,
        "created_at": still.created_at,
        "documents": [
            {
                "document_id": d.document_id,
                "document_name": d.document_name,
                "source_kind": d.source_kind,
                "relative_path": d.relative_path,
                "canonical_name": d.canonical_name,
                "tool_id": d.tool_id,
                "document_metadata": d.document_metadata or {},
                "rows": list(d.rows),
                "anchor_rows": list(d.anchor_rows),
                "version_hash": d.version_hash,
            }
            for d in still.documents
        ],
    }


def _payload_to_still(payload: Any) -> Still:
    if not isinstance(payload, dict):
        raise StillFormatError("still payload is not an object")
    schema = str(payload.get("schema", ""))
    if schema != STILL_SCHEMA:
        raise StillFormatError(f"unknown still schema: {schema!r}")
    documents_raw = payload.get("documents")
    if not isinstance(documents_raw, list):
        raise StillFormatError("still payload has no documents list")
    documents: list[StillDocument] = []
    for entry in documents_raw:
        if not isinstance(entry, dict):
            raise StillFormatError("still document entry is not an object")
        name = str(entry.get("document_name", ""))
        metadata = entry.get("document_metadata") or {}
        if not isinstance(metadata, dict):
            raise StillFormatError(f"{name}: document_metadata is not an object")
        documents.append(
            StillDocument(
                document_id=str(entry.get("document_id", "")),
                document_name=name,
                source_kind=str(entry.get("source_kind", "")),
                relative_path=str(entry.get("relative_path", "")),
                canonical_name=str(entry.get("canonical_name", "")),
                tool_id=str(entry.get("tool_id", "")),
                document_metadata=dict(metadata),
                rows=_carried_rows(entry.get("rows"), document_name=name, field="rows"),
                anchor_rows=_carried_rows(
                    entry.get("anchor_rows"), document_name=name, field="anchor_rows"
                ),
                version_hash=str(entry.get("version_hash", "")),
            )
        )
    return Still(
        source_msn=str(payload.get("source_msn", "")),
        name=str(payload.get("name", "")),
        created_at=str(payload.get("created_at", "")),
        documents=tuple(documents),
        schema=schema,
        policy=str(payload.get("policy", STILL_POLICY)),
    )


def canonical_still_json(still: Still) -> str:
    """Deterministic JSON for the still — the bytes the container compresses."""
    return canonical_json(_still_to_payload(still))


def encode_still(still: Still) -> bytes:
    """Frame a still as a ``.mss`` of kind ``document_set``.

    Deterministic: the same still always produces the same bytes, so a still is
    genuinely content-addressed and a consumer's update-check never churns.
    """
    return encode_envelope(KIND_DOCUMENT_SET, _still_to_payload(still))


def _legacy_mstl_payload(blob: bytes, limit: int) -> dict[str, Any]:
    """Read the payload out of a pre-consolidation ``MSTL`` blob.

    Kept because one such artifact was published (the FND registry still) before
    the ``.mss`` envelope existed. Only the *framing* differed — the compressed
    body is byte-identical in both — so this re-frames the body as a ``.mss`` and
    hands off, rather than duplicating the bounded-decompression and grammar
    guards where they could drift apart.
    """
    if len(blob) < 12:
        raise StillFormatError("not a still container (truncated legacy header)")
    version, length = struct.unpack(">II", blob[4:12])
    if version != STILL_FORMAT_VERSION:
        raise StillFormatError(f"unsupported still format version: {version}")
    body = blob[12:]
    if len(body) != length:
        raise StillFormatError(
            f"still payload length mismatch: header={length} actual={len(body)}"
        )
    return decode_envelope(
        frame_compressed(KIND_DOCUMENT_SET, body),
        expect_kind=KIND_DOCUMENT_SET,
        max_decompressed_bytes=limit,
    )[1]


def decode_still(
    blob: bytes, *, max_decompressed_bytes: int = STILL_MAX_DECOMPRESSED_BYTES
) -> Still:
    """Inverse of :func:`encode_still`. Raises :class:`StillFormatError` on any
    framing, size or schema violation.

    Accepts both the current ``.mss`` container and the legacy ``MSTL`` framing.
    """
    if blob[:4] == STILL_MAGIC:
        return _payload_to_still(_legacy_mstl_payload(blob, max_decompressed_bytes))
    _kind, payload = decode_envelope(
        blob,
        expect_kind=KIND_DOCUMENT_SET,
        max_decompressed_bytes=max_decompressed_bytes,
    )
    return _payload_to_still(payload)


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def verify_still(still: Still) -> list[str]:
    """Re-derive every document's version hash from the carried rows and report
    drift. An empty list means the still is byte-faithful to its source.

    This is the still's equivalent of the offering exporter's
    encode→decode→reconstruct self-check.
    """
    problems: list[str] = []
    for entry in still.documents:
        if not entry.version_hash:
            problems.append(f"{entry.document_name}: no recorded version_hash")
            continue
        rebuilt = compute_mss_hash(still_document_to_document(entry))["version_hash"]
        if rebuilt != entry.version_hash:
            problems.append(
                f"{entry.document_name}: version_hash drift "
                f"(recorded {entry.version_hash}, rebuilt {rebuilt})"
            )
    return problems


def verify_still_round_trip(still: Still) -> list[str]:
    """Full self-check: encode → decode must reproduce the still, and every
    decoded document must re-hash to its recorded identity."""
    problems = verify_still(still)
    decoded = decode_still(encode_still(still))
    if canonical_still_json(decoded) != canonical_still_json(still):
        problems.append("container round-trip drifted (encode -> decode != original)")
    problems.extend(verify_still(decoded))
    return problems


__all__ = [
    "STILL_FORMAT_VERSION",
    "STILL_MAGIC",
    "STILL_MAX_DECOMPRESSED_BYTES",
    "STILL_POLICY",
    "STILL_SCHEMA",
    "Still",
    "StillDocument",
    "StillFormatError",
    "build_still",
    "build_still_document",
    "canonical_still_json",
    "decode_still",
    "encode_still",
    "still_document_to_document",
    "still_to_documents",
    "verify_still",
    "verify_still_round_trip",
]
