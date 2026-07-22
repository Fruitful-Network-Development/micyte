from __future__ import annotations

from typing import Any

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)

# Address-parsing / hashing / reference-walk helpers are single-sourced from the
# canonical datum-semantics engine in core, so this module cannot drift from it.
# The engine exposes the public spellings of what used to be local underscored
# copies here; aliasing keeps this module's internal call sites unchanged.
from micyte.core.datum_semantics.engine import (
    MSS_VERSION_HASH_POLICY,
    _row_local_refs,
    _sha256_token,
)
from micyte.core.datum_semantics.engine import (
    datum_address_sort_key as _datum_address_sort_key,
)
from micyte.core.datum_semantics.engine import (
    format_datum_address as _format_datum_address,
)
from micyte.core.datum_semantics.engine import (
    parse_datum_address as _parse_datum_address,
)


def compute_mss_hash(datum_document: AuthoritativeDatumDocument) -> dict[str, Any]:
    """Return the canonical MSS version identity for a datum document.

    Produces the same version_hash as build_document_version_identity in
    fnd_app/packages/adapters/sql/datum_semantics.py. The hash is deterministic
    over sorted rows serialized with canonical JSON (sort_keys, no whitespace).

    Returns dict with keys: policy, version_hash, canonical_payload.
    """
    payload: dict[str, Any] = {
        "policy": MSS_VERSION_HASH_POLICY,
        "source_kind": datum_document.source_kind,
        "document_metadata": datum_document.document_metadata or {},
        "rows": [
            {"datum_address": row.datum_address, "raw": row.raw}
            for row in sorted(datum_document.rows, key=lambda r: _datum_address_sort_key(r.datum_address))
        ],
    }
    return {
        "policy": MSS_VERSION_HASH_POLICY,
        "version_hash": _sha256_token(prefix=MSS_VERSION_HASH_POLICY, payload=payload),
        "canonical_payload": payload,
    }


def derive_hyphae_chain(
    datum_doc: AuthoritativeDatumDocument,
    datum_address: str,
) -> list[str]:
    """Return the hyphae rudi chain for datum_address: [0-0-1, ..., 0-0-K].

    K is the highest rudi datum iteration (layer=0, value_group=0) reachable in
    the transitive dependency closure of datum_address. Every position 1..K is
    included even if not directly referenced by datum_address.

    Raises ValueError if datum_address is not present in datum_doc.
    """
    address_map: dict[str, AuthoritativeDatumDocumentRow] = {
        row.datum_address: row for row in datum_doc.rows
    }
    if datum_address not in address_map:
        raise ValueError(f"datum_address not found in document: {datum_address!r}")

    known_addresses = set(address_map)
    dependency_map: dict[str, tuple[str, ...]] = {
        addr: _row_local_refs(row, known_addresses=known_addresses)
        for addr, row in address_map.items()
    }

    closure: list[str] = []
    seen: set[str] = set()

    def _walk(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        for dep in sorted(dependency_map.get(current, ()), key=_datum_address_sort_key):
            _walk(dep)
        closure.append(current)

    _walk(datum_address)

    rudi_in_doc = {addr for addr in address_map if _parse_datum_address(addr)[:2] == (0, 0)}
    reachable_rudi_iters = [
        _parse_datum_address(item)[2]
        for item in closure
        if item in rudi_in_doc
    ]
    if not reachable_rudi_iters:
        return []

    max_k = max(reachable_rudi_iters)
    return [
        _format_datum_address(0, 0, k)
        for k in range(1, max_k + 1)
        if _format_datum_address(0, 0, k) in rudi_in_doc
    ]
