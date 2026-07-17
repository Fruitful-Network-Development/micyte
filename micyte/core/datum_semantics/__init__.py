"""Datum-address / hyphae / MSS-semantics engine (canonical home).

This is the pure, store-agnostic intra-document datum-address engine: address
parsing/formatting, MSS version identity, hyphae-chain semantics, and the
iteration-shift edit-remap previews (insert / delete / move). It depends only
on :mod:`micyte.core.datum_documents` (datum-document value types)
plus the standard library, so it belongs in ``core``.

It previously lived at ``micyte.adapters.sql.datum_semantics``; that
path is now a thin back-compat shim re-exporting from here.
"""

from __future__ import annotations

from .engine import (
    EDIT_REMAP_POLICY,
    HYPHAE_CHAIN_POLICY,
    MSS_VERSION_HASH_POLICY,
    build_document_semantics,
    build_document_version_identity,
    build_minimum_complete_path,
    compile_hyphae_value,
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
    "build_minimum_complete_path",
    "compile_hyphae_value",
    "datum_address_sort_key",
    "dumps_json",
    "format_datum_address",
    "is_datum_address",
    "parse_datum_address",
    "preview_document_delete",
    "preview_document_insert",
    "preview_document_move",
]
