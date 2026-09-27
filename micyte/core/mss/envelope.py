"""The ``.mss`` envelope — one container for every datum artifact that leaves an instance.

Why one format
--------------
Three parallel artifact shapes were doing one job:

===========================  =============================================  ==================
shape                        what                                           where
===========================  =============================================  ==================
``micyte-<msn>.bin``         ``micyte.offering.mss.v1``, a hand-rolled      micyte.com
                             presentation projection
``.mstl``                    the faithful document snapshot                 instance→instance
``MYC1`` / ``mss_binary_v*``  the closure/hash codec                        (unused in prod)
===========================  =============================================  ==================

Each carried its own framing, its own guards, and its own decoder. This module
collapses them: **one envelope, one decoder, a declared payload kind.** A `.mss`
file holds the MSS form of one or more datum documents
(:data:`KIND_DOCUMENT_SET`), a single datum's focus closure — its hyphae value
(:data:`KIND_HYPHAE`), or a derived, consumer-shaped view of documents
(:data:`KIND_PROJECTION`). The same bytes serve a website fetching a public resource,
an instance acquiring a resource from another instance, and a P2P channel
conveying a document — because in all three cases the question is the same: *what
is in this blob, and can I trust it enough to decode it?*

Self-describing, always
-----------------------
The kind and the format version live in the **header**, never inferred from the
payload or the filename. A decoder must not have to guess what it is holding —
that is precisely why the predecessor still was framed ``MSTL`` rather than
``MYC1``, and the rule survives the consolidation rather than being dropped by it.

Encryption lives outside
------------------------
A symmetric channel wraps these bytes; it must not alter them. If a transport
re-encoded the payload, the content-addressing would stop meaning anything —
the recorded hashes would no longer describe what was actually sent. So the
envelope is what gets encrypted, never what does the encrypting.

The decoder is a trust boundary
-------------------------------
A `.mss` arrives from *another* instance. Every guard the still decoder earned in
review is enforced here, for every kind:

- **bounded decompression** — incremental gunzip against a ceiling, because a
  blob's expansion ratio is only observable *while* decompressing;
- **framing checked before payload** — magic, version, kind and declared length
  are all validated before a single byte is inflated;
- **grammar checked, not trusted** — a malformed payload raises
  :class:`MssEnvelopeError` here, not a ``KeyError`` from deep inside a builder.
"""

from __future__ import annotations

import gzip
import io
import json
import struct
from typing import Any

#: Container magic. Distinct from ``MYC1`` (the raw MSS bitstream) so a decoder
#: can never mistake a framed artifact for a bare bitstream.
MSS_MAGIC = b"MSSF"
MSS_FORMAT_VERSION = 1

#: Payload kinds. Wire constants — appending is safe, renumbering is a break.
KIND_DOCUMENT_SET = 1   # one or more datum documents (the still)
KIND_HYPHAE = 2         # one datum's downward focus closure, rudi-inclusive
#: A **derived, consumer-shaped view** of documents — the hosted-channel convention's
#: resource binary ("a projection of documents, never an origin"). Its own kind, because
#: the header must never lie about what it holds: a projection carried as
#: :data:`KIND_DOCUMENT_SET` would hand a decoder a payload with no ``documents`` list
#: under a kind that promises one, and the mismatch would surface as a ``KeyError``
#: inside a builder rather than a refusal at the boundary. Same rule that made the
#: predecessor still ``MSTL`` rather than ``MYC1``.
#:
#: Why a projection is a different artifact from a still, and not a smaller one: a still
#: carries rows **verbatim** so ``version_hash`` re-derives, which makes it faithful and
#: makes it big — the agnet snapshot is 2.35 MB framed and **76 MB inflated**. That is
#: the right shape for another instance and the wrong shape for a browser. A projection
#: is derived, so it is identified by the hashes of what it was derived *from* rather
#: than by re-deriving them.
KIND_PROJECTION = 3

KIND_NAMES = {
    KIND_DOCUMENT_SET: "document_set",
    KIND_HYPHAE: "hyphae",
    KIND_PROJECTION: "projection",
}

#: Ceiling on the decompressed payload. For scale: the FND directory set is 91KB
#: and the whole registrar sandbox 5.25MB, so this is ~50× the largest real
#: artifact and still small enough to refuse a bomb.
MSS_MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024

#: ``MSS_MAGIC`` + uint32 version + uint32 kind + uint32 length.
_HEADER = struct.Struct(">III")
_HEADER_SIZE = len(MSS_MAGIC) + _HEADER.size


class MssEnvelopeError(ValueError):
    """The blob or payload violates the ``.mss`` container grammar."""


def canonical_json(payload: Any) -> str:
    """Deterministic JSON — the bytes the container compresses.

    Sorted keys and no incidental whitespace, so the same logical artifact always
    produces the same bytes and is genuinely content-addressed.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def encode_envelope(kind: int, payload: Any) -> bytes:
    """Frame ``payload`` as a ``.mss`` of the given kind.

    Deterministic: gzip's mtime is pinned to 0, so the same payload always
    produces the same bytes. A spurious byte difference would churn every
    consumer's update-check.
    """
    if kind not in KIND_NAMES:
        raise MssEnvelopeError(f"unknown .mss payload kind: {kind}")
    body = gzip.compress(canonical_json(payload).encode("utf-8"), mtime=0)
    return MSS_MAGIC + _HEADER.pack(MSS_FORMAT_VERSION, kind, len(body)) + body


def frame_compressed(kind: int, body: bytes) -> bytes:
    """Frame an **already-gzipped** canonical-JSON body as a ``.mss``.

    Exists for one job: adopting a body that was framed by a superseded
    container. Re-framing lets that legacy path reuse this module's bounded
    decompression and grammar checks instead of keeping a second copy of the
    guards, where the two could drift apart. Do not use it to build new
    artifacts — :func:`encode_envelope` owns that, and owns determinism with it.
    """
    if kind not in KIND_NAMES:
        raise MssEnvelopeError(f"unknown .mss payload kind: {kind}")
    return MSS_MAGIC + _HEADER.pack(MSS_FORMAT_VERSION, kind, len(body)) + body


def _decompress_bounded(body: bytes, limit: int) -> str:
    """gunzip ``body``, refusing to expand past ``limit`` bytes.

    Read incrementally rather than via :func:`gzip.decompress` so a hostile or
    corrupt artifact cannot exhaust memory before its size is known.
    """
    chunks: list[bytes] = []
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise MssEnvelopeError(
                        f".mss payload expands past the {limit}-byte ceiling "
                        "(refusing to decompress further)"
                    )
                chunks.append(chunk)
    except MssEnvelopeError:
        raise
    except Exception as exc:
        raise MssEnvelopeError(f".mss payload is not gzip: {exc}") from exc
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MssEnvelopeError(f".mss payload is not utf-8: {exc}") from exc


def peek_kind(blob: bytes) -> int:
    """The declared payload kind, without inflating anything.

    Lets a router (an API handler, a channel receiver) dispatch on kind before
    committing to the cost of decoding.
    """
    if len(blob) < _HEADER_SIZE or blob[: len(MSS_MAGIC)] != MSS_MAGIC:
        raise MssEnvelopeError("not a .mss container (bad magic)")
    _version, kind, _length = _HEADER.unpack(blob[len(MSS_MAGIC) : _HEADER_SIZE])
    return int(kind)


def decode_envelope(
    blob: bytes,
    *,
    expect_kind: int | None = None,
    max_decompressed_bytes: int = MSS_MAX_DECOMPRESSED_BYTES,
) -> tuple[int, dict[str, Any]]:
    """Inverse of :func:`encode_envelope` → ``(kind, payload)``.

    ``expect_kind`` makes the caller's assumption explicit: a handler that can
    only deal with one kind should say so rather than discover the mismatch
    downstream.
    """
    if len(blob) < _HEADER_SIZE or blob[: len(MSS_MAGIC)] != MSS_MAGIC:
        raise MssEnvelopeError("not a .mss container (bad magic)")
    version, kind, length = _HEADER.unpack(blob[len(MSS_MAGIC) : _HEADER_SIZE])
    if version != MSS_FORMAT_VERSION:
        raise MssEnvelopeError(f"unsupported .mss format version: {version}")
    if kind not in KIND_NAMES:
        raise MssEnvelopeError(f"unknown .mss payload kind: {kind}")
    if expect_kind is not None and kind != expect_kind:
        raise MssEnvelopeError(
            f"expected a {KIND_NAMES[expect_kind]} .mss but this is "
            f"{KIND_NAMES[kind]}"
        )
    body = blob[_HEADER_SIZE:]
    if len(body) != length:
        raise MssEnvelopeError(
            f".mss payload length mismatch: header={length} actual={len(body)}"
        )
    text = _decompress_bounded(body, max_decompressed_bytes)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MssEnvelopeError(f".mss payload is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise MssEnvelopeError(".mss payload is not an object")
    return int(kind), payload


__all__ = [
    "KIND_DOCUMENT_SET",
    "KIND_HYPHAE",
    "KIND_NAMES",
    "KIND_PROJECTION",
    "MSS_FORMAT_VERSION",
    "MSS_MAGIC",
    "MSS_MAX_DECOMPRESSED_BYTES",
    "MssEnvelopeError",
    "canonical_json",
    "decode_envelope",
    "encode_envelope",
    "frame_compressed",
    "peek_kind",
]
