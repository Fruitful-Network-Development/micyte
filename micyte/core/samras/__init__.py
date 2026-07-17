"""Canonical public API for the SAMRAS structural abstraction.

This package re-exports the SAMRAS magnitude codec, structure model,
mutation operations, validation rules, and workspace adapter from
``micyte.core.structures.samras``. It is the canonical
import path for tool runtimes and adapters that need SAMRAS support
without entering the ``structures.*`` implementation tree.

The implementation is intentionally pure-stdlib and file-agnostic.
"""

from __future__ import annotations

from micyte.core.structures.samras import (
    InvalidSamrasStructure,
    SamrasMutationResult,
    SamrasStructure,
    SamrasStructureAuthority,
    SamrasWorkspaceNode,
    SamrasWorkspaceResource,
    add_child,
    add_root,
    address_depth,
    address_sort_key,
    as_text,
    child_counts_from_addresses,
    decode_canonical_bitstream,
    decode_legacy_fixed_header_bitstream,
    decode_legacy_hyphen_payload,
    decode_structure,
    derive_addresses_from_child_counts,
    encode_canonical_structure_from_addresses,
    encode_canonical_structure_from_values,
    find_structure_authorities,
    format_address,
    load_workspace_from_compact_payload,
    move_branch,
    parent_address,
    rebuild_structure_from_addresses,
    reconstruct_addresses_from_rows,
    reconstruct_structure_from_rows,
    remove_branch,
    select_preferred_structure_authority,
    set_child_count,
    validate_structure,
)

__all__ = [
    "InvalidSamrasStructure",
    "SamrasMutationResult",
    "SamrasStructure",
    "SamrasStructureAuthority",
    "SamrasWorkspaceNode",
    "SamrasWorkspaceResource",
    "add_child",
    "add_root",
    "address_depth",
    "address_sort_key",
    "as_text",
    "child_counts_from_addresses",
    "decode_canonical_bitstream",
    "decode_legacy_fixed_header_bitstream",
    "decode_legacy_hyphen_payload",
    "decode_structure",
    "derive_addresses_from_child_counts",
    "encode_canonical_structure_from_addresses",
    "encode_canonical_structure_from_values",
    "find_structure_authorities",
    "format_address",
    "load_workspace_from_compact_payload",
    "move_branch",
    "parent_address",
    "rebuild_structure_from_addresses",
    "reconstruct_addresses_from_rows",
    "reconstruct_structure_from_rows",
    "remove_branch",
    "select_preferred_structure_authority",
    "set_child_count",
    "validate_structure",
]
