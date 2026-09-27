"""Hyphae — the ``.mss`` payload that carries **one datum**, not a document.

A datum's *hyphae value* is its transitive downward reference closure,
rudi-inclusive: the datum, everything it references, everything those reference,
down to the rudimentary ``0-0-*`` base. That closure is what makes a single datum
meaningful in isolation — hand someone a bare row and its references dangle; hand
them the closure and it stands on its own.

This is the second of the two ``.mss`` payload kinds
(:data:`~core.mss.envelope.KIND_HYPHAE`). It differs from the document-set kind
only in **seed set** — one address instead of every row of a document — which is
why the two share a container rather than each inventing one:
``document_closure_to_mss`` and ``datum_closure_to_mss`` are already the same
function over different seeds.

Why this kind carries the closure rather than raw rows
------------------------------------------------------
The document-set kind carries rows verbatim because a snapshot of a few documents
cannot always supply the tenant-wide closure its rows reference. A hyphae payload
is the opposite case: the closure **is** the payload, resolved at build time, so
it is self-contained by construction. Carrying it in MSS form is therefore both
possible and right — and it is only possible at all because
``core/mss/magnitude.py`` made the token projection injective. Before that, a
hyphae payload would have arrived with 28.7% of its display text destroyed.

Identity
--------
``hyphae_value`` is ``mss_document_hash`` over the closure — the same content-
derived key a hyphae-flag / family-root registry matches against. It is recorded
in the payload and re-derivable from it, so faithfulness is provable the same way
a still's is: rebuild the hash and compare.

A hyphae names its document
---------------------------
A datum address is a **document-local coordinate**: 7,241 addresses in the live
corpus are claimed by two or more documents, so ``4-1-1`` alone does not identify a
row. A hyphae therefore records the ``document_id`` its focus datum came from, and
that document is what the closure resolves through — the recipient is told *whose*
``4-1-1`` this is, and the canonical id says which **version** of that document, so
the hash can be reproduced rather than merely compared.

The document must actually **carry** the address, not merely reference it. Naming
the document you happen to be looking at is the specific mistake the ambiguity
invites: publishing ``system/anthology``'s ``1-1-1`` as though it came from the
boundary document that references it.

Schema ``…hyphae.v2``. ``v1`` had no such field and is refused rather than decoded
with an empty one: a payload that cannot say which document it came from is the
ambiguity this fixed, and accepting it silently would preserve it. Nothing ever
published a v1 hyphae — it had no callers outside its own tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .document_adapter import CatalogEntry, datum_closure_to_mss, document_scoped_index
from .document_codec import MSS_DOC_POLICY, MssDatum, MssTuple, mss_document_hash
from .envelope import (
    KIND_HYPHAE,
    MSS_MAX_DECOMPRESSED_BYTES,
    MssEnvelopeError,
    canonical_json,
    decode_envelope,
    encode_envelope,
)

HYPHAE_SCHEMA = "mycite.v2.mos.hyphae.v2"

#: Refused by name, so the message can say what the payload cannot answer.
_SUPERSEDED_SCHEMAS = {"mycite.v2.mos.hyphae.v1": "it does not name the document its "
                                                  "focus datum came from"}


@dataclass(frozen=True)
class Hyphae:
    """One datum's focus closure, published by ``source_msn`` from ``document_id``."""

    source_msn: str
    datum_address: str
    #: The canonical id of the document this datum came from — sandbox, name AND
    #: version hash, so the recipient can reproduce the value rather than trust it.
    document_id: str
    datums: tuple[MssDatum, ...] = ()
    hyphae_value: str = ""
    created_at: str = ""
    schema: str = HYPHAE_SCHEMA
    policy: str = MSS_DOC_POLICY


# --------------------------------------------------------------------------- #
# Build / reconstruct
# --------------------------------------------------------------------------- #
def build_hyphae(
    datum_address: str,
    *,
    index: dict[str, CatalogEntry],
    document: Any,
    source_msn: str,
    created_at: str = "",
) -> Hyphae:
    """Resolve ``datum_address``'s downward closure **within ``document``** and record
    its hyphae value.

    ``document`` is required. It is what makes the published closure answerable: a
    bare address is a document-local coordinate that several documents may claim, so
    without one this published whichever row the tenant index happened to hold and
    said nothing about which.

    ``created_at`` is passed in rather than sampled so the artifact is
    reproducible — the same datum must produce the same bytes.
    """
    scoped = document_scoped_index(document, index)
    if not scoped.carries(datum_address):
        # Referencing a datum is not holding it. A hyphae that named the document it
        # was read THROUGH rather than the one it came FROM would be a wrong answer to
        # the exact question this field exists to answer.
        raise MssEnvelopeError(
            f"{datum_address}: {getattr(document, 'document_id', '?')} does not carry "
            "this address, so it cannot publish it")
    closure = datum_closure_to_mss(datum_address, index=index, document=document)
    if not closure:
        raise MssEnvelopeError(
            f"{datum_address}: no closure resolved (address absent from the catalog)"
        )
    return Hyphae(
        source_msn=source_msn,
        datum_address=datum_address,
        document_id=str(getattr(document, "document_id", "")),
        datums=tuple(closure),
        hyphae_value=mss_document_hash(closure),
        created_at=created_at,
    )


def hyphae_to_datums(hyphae: Hyphae) -> list[MssDatum]:
    """The carried closure. View-state only — a hyphae is transport, not truth."""
    return list(hyphae.datums)


def hyphae_tokens(hyphae: Hyphae) -> dict[str, dict[str, Any]]:
    """The closure decoded back to **usable** form: address → its tokens.

    This is the "make it reliable and usable" step a consumer runs after
    decoding — the counterpart of what the website's renderer modules do to a
    decoded offering. Each entry is ``{"title": …, "refs": [...], "tuples":
    [(ref, token), ...]}`` with magnitudes already inverted to their original
    tokens via the kind discriminator.
    """
    out: dict[str, dict[str, Any]] = {}
    for datum in hyphae.datums:
        out[datum.address] = {
            "title": datum.title,
            "refs": list(datum.refs),
            "tuples": [(item.ref, item.token) for item in datum.tuples],
        }
    return out


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #
def _mag_to_hex(magnitude: int) -> str:
    """A magnitude as a lowercase hex string.

    Magnitudes are **not** JSON numbers, and cannot be. A text magnitude is the
    token's UTF-8 read as one big-endian integer, so ``"akron_city"`` is already
    ~2^80 — far past the 2^53 where a JSON number silently becomes a lossy float.
    Round-tripping through ``JSON.parse`` in a browser would corrupt every text
    token longer than six bytes, which is most of them.

    Hex rather than decimal for a second reason: CPython caps integer/decimal
    *string* conversion at 4,300 digits, and the corpus holds tokens whose
    magnitudes exceed that. Power-of-two bases are exempt from the cap.
    """
    return format(magnitude, "x")


def _hex_to_mag(value: Any, *, where: str) -> int:
    if not isinstance(value, str) or not value:
        raise MssEnvelopeError(f"{where}: magnitude is not a hex string")
    try:
        magnitude = int(value, 16)
    except ValueError as exc:
        raise MssEnvelopeError(f"{where}: magnitude is not valid hex") from exc
    if magnitude < 0:
        raise MssEnvelopeError(f"{where}: magnitude is negative")
    return magnitude



def _datum_to_payload(datum: MssDatum) -> dict[str, Any]:
    return {
        "address": datum.address,
        "refs": list(datum.refs),
        "tuples": [[t.ref, t.kind, _mag_to_hex(t.magnitude)] for t in datum.tuples],
        "title": datum.title,
    }


def _payload_to_datum(entry: Any) -> MssDatum:
    """Read one datum out of a decoded payload, checking its grammar.

    A hyphae arrives from another instance, so nothing here is trusted: a
    malformed entry raises :class:`MssEnvelopeError` at decode rather than
    surfacing as an ``IndexError`` from inside a consumer later.
    """
    if not isinstance(entry, dict):
        raise MssEnvelopeError("hyphae datum entry is not an object")
    address = entry.get("address")
    if not isinstance(address, str) or address.count("-") != 2:
        raise MssEnvelopeError(f"hyphae datum has a bad address: {address!r}")
    try:
        layer, group, iteration = (int(part) for part in address.split("-"))
    except ValueError as exc:
        raise MssEnvelopeError(f"hyphae datum address is not numeric: {address!r}") from exc

    refs_raw = entry.get("refs") or []
    if not isinstance(refs_raw, list) or not all(isinstance(r, str) for r in refs_raw):
        raise MssEnvelopeError(f"{address}: refs is not a list of addresses")

    tuples_raw = entry.get("tuples") or []
    if not isinstance(tuples_raw, list):
        raise MssEnvelopeError(f"{address}: tuples is not a list")
    tuples: list[MssTuple] = []
    for item in tuples_raw:
        if not isinstance(item, list) or len(item) != 3:
            raise MssEnvelopeError(f"{address}: a tuple is not [ref, kind, magnitude]")
        ref, kind, magnitude = item
        if not isinstance(ref, str) or not isinstance(kind, int) or isinstance(kind, bool):
            raise MssEnvelopeError(f"{address}: a tuple has a bad field type")
        if kind < 0:
            raise MssEnvelopeError(f"{address}: a tuple kind is negative")
        tuples.append(MssTuple(ref, kind, _hex_to_mag(magnitude, where=address)))

    title = entry.get("title")
    if title is not None and not isinstance(title, str):
        raise MssEnvelopeError(f"{address}: title is neither a string nor null")

    return MssDatum(
        layer, group, iteration, refs=tuple(refs_raw), tuples=tuple(tuples), title=title
    )


def _hyphae_to_payload(hyphae: Hyphae) -> dict[str, Any]:
    return {
        "schema": hyphae.schema,
        "policy": hyphae.policy,
        "source_msn": hyphae.source_msn,
        "datum_address": hyphae.datum_address,
        "document_id": hyphae.document_id,
        "hyphae_value": hyphae.hyphae_value,
        "created_at": hyphae.created_at,
        "datums": [_datum_to_payload(d) for d in hyphae.datums],
    }


def _payload_to_hyphae(payload: dict[str, Any]) -> Hyphae:
    schema = str(payload.get("schema", ""))
    if schema in _SUPERSEDED_SCHEMAS:
        raise MssEnvelopeError(
            f"superseded hyphae schema {schema!r}: {_SUPERSEDED_SCHEMAS[schema]}")
    if schema != HYPHAE_SCHEMA:
        raise MssEnvelopeError(f"unknown hyphae schema: {schema!r}")
    datums_raw = payload.get("datums")
    if not isinstance(datums_raw, list):
        raise MssEnvelopeError("hyphae payload has no datums list")
    document_id = payload.get("document_id")
    if not isinstance(document_id, str) or not document_id:
        # Defaulting to "" here would decode the ambiguity back in: the payload would
        # look well-formed and answer "which document?" with silence.
        raise MssEnvelopeError("hyphae payload names no document_id")
    return Hyphae(
        source_msn=str(payload.get("source_msn", "")),
        datum_address=str(payload.get("datum_address", "")),
        document_id=document_id,
        datums=tuple(_payload_to_datum(entry) for entry in datums_raw),
        hyphae_value=str(payload.get("hyphae_value", "")),
        created_at=str(payload.get("created_at", "")),
        schema=schema,
        policy=str(payload.get("policy", MSS_DOC_POLICY)),
    )


def canonical_hyphae_json(hyphae: Hyphae) -> str:
    """Deterministic JSON for the hyphae — the bytes the container compresses."""
    return canonical_json(_hyphae_to_payload(hyphae))


def encode_hyphae(hyphae: Hyphae) -> bytes:
    """Frame a hyphae as a ``.mss`` of kind ``hyphae``."""
    return encode_envelope(KIND_HYPHAE, _hyphae_to_payload(hyphae))


def decode_hyphae(
    blob: bytes, *, max_decompressed_bytes: int = MSS_MAX_DECOMPRESSED_BYTES
) -> Hyphae:
    """Inverse of :func:`encode_hyphae`."""
    _kind, payload = decode_envelope(
        blob, expect_kind=KIND_HYPHAE, max_decompressed_bytes=max_decompressed_bytes
    )
    return _payload_to_hyphae(payload)


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def verify_hyphae(hyphae: Hyphae) -> list[str]:
    """Re-derive the hyphae value from the carried closure and report drift.

    An empty list means the payload is faithful to what its publisher hashed.
    """
    problems: list[str] = []
    if not hyphae.document_id:
        problems.append(f"{hyphae.datum_address}: names no document, so the address "
                        "does not identify a row")
    if not hyphae.hyphae_value:
        problems.append(f"{hyphae.datum_address}: no recorded hyphae_value")
        return problems
    if not any(d.address == hyphae.datum_address for d in hyphae.datums):
        problems.append(
            f"{hyphae.datum_address}: the focus datum is absent from its own closure"
        )
    rebuilt = mss_document_hash(list(hyphae.datums))
    if rebuilt != hyphae.hyphae_value:
        problems.append(
            f"{hyphae.datum_address}: hyphae_value drift "
            f"(recorded {hyphae.hyphae_value}, rebuilt {rebuilt})"
        )
    return problems


def verify_hyphae_round_trip(hyphae: Hyphae) -> list[str]:
    """Full self-check: encode → decode must reproduce the payload, and the
    decoded closure must re-hash to its recorded identity."""
    problems = verify_hyphae(hyphae)
    decoded = decode_hyphae(encode_hyphae(hyphae))
    if canonical_hyphae_json(decoded) != canonical_hyphae_json(hyphae):
        problems.append("container round-trip drifted (encode -> decode != original)")
    problems.extend(verify_hyphae(decoded))
    return problems


__all__ = [
    "HYPHAE_SCHEMA",
    "Hyphae",
    "build_hyphae",
    "canonical_hyphae_json",
    "decode_hyphae",
    "encode_hyphae",
    "hyphae_to_datums",
    "hyphae_tokens",
    "verify_hyphae",
    "verify_hyphae_round_trip",
]
