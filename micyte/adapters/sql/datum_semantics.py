"""Back-compat shim. Canonical home is now
:mod:`micyte.core.datum_semantics`.

The datum-address / hyphae / MSS-semantics engine was relocated into ``core``
(it depends only on ``ports`` + the standard library, so it was never SQL-
coupled). This module is preserved so existing and external importers keep
working; new code should import from ``micyte.core.datum_semantics``.
"""

from __future__ import annotations

from micyte.core.datum_semantics import (
    EDIT_REMAP_POLICY,
    HYPHAE_CHAIN_POLICY,
    MSS_VERSION_HASH_POLICY,
    build_document_semantics,
    build_document_version_identity,
    datum_address_sort_key,
    dumps_json,
    format_datum_address,
    is_datum_address,
    parse_datum_address,
    preview_document_delete,
    preview_document_insert,
    preview_document_move,
)

__all__ = [
    "EDIT_REMAP_POLICY",
    "HYPHAE_CHAIN_POLICY",
    "MSS_VERSION_HASH_POLICY",
    "build_document_semantics",
    "build_document_version_identity",
    "datum_address_sort_key",
    "dumps_json",
    "format_datum_address",
    "is_datum_address",
    "parse_datum_address",
    "preview_document_delete",
    "preview_document_insert",
    "preview_document_move",
]
