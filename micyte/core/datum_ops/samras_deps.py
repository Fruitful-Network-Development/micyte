"""SAMRAS-magnitude dependency detection + recompile.

A SAMRAS magnitude row (e.g. anchor ``1-1-1`` = txa-SAMRAS, ``1-1-5`` = lcl-SAMRAS)
encodes the *prefix-closure* of a sheet's defined node set as a canonical bitstream
rooted at ``0-0-5``. When the node set changes (relocate/mint/drop), the magnitude
must be recomputed. This module lifts the ingest script's ``_prefix_closure`` /
``_build_magnitude_bitstream`` verbatim so the library and the script share one
implementation, and adds the helpers the ops layer needs.
"""

from __future__ import annotations

from typing import Any

from micyte.core.structures.samras.codec import (
    decode_canonical_bitstream,
    encode_canonical_structure_from_addresses,
)
from micyte.core.structures.samras.validation import InvalidSamrasStructure

# Anchor → node-source mapping (the ingest script's hardcoded agro_erp contract).
# Single source of truth: a SAMRAS magnitude at anchor address X encodes the node
# set defined by sheet ANCHOR_SAMRAS_SOURCE[X]. migrate (consistency check + verify)
# and compiler (housekeeping) both derive from this map rather than restating it.
# (Deferred: derive this from the anchor's babelette definitions per sandbox.)
ANCHOR_TXA_SAMRAS = "1-1-1"  # over the txa node set
ANCHOR_LCL_SAMRAS = "1-1-5"  # over the lcl node set
SAMRAS_ROOT_REF = "0-0-5"
ANCHOR_SAMRAS_SOURCE = {ANCHOR_TXA_SAMRAS: "txa", ANCHOR_LCL_SAMRAS: "lcl"}
TXA_ID_COLLECTION = "5-0-1"  # the RUDI id-collection rebuilt alongside a txa/lcl recompile


def prefix_closure(named_addresses: set[str]) -> set[str]:
    """Every ancestor prefix of every named node (what ``decode`` returns)."""
    full: set[str] = set()
    for addr in named_addresses:
        segments = addr.split("-")
        for depth in range(1, len(segments) + 1):
            full.add("-".join(segments[:depth]))
    return full


def build_magnitude_bitstream(named_addresses: set[str]) -> str:
    """Canonical SAMRAS bitstream over a node set; roundtrip-asserted.

    Identical to ``ingest_agro_erp_product_profiles._build_magnitude_bitstream``
    except it raises :class:`InvalidSamrasStructure` (library, not a CLI) on a
    roundtrip mismatch.
    """
    full = prefix_closure(named_addresses)
    structure = encode_canonical_structure_from_addresses(sorted(full))
    decoded = decode_canonical_bitstream(structure.bitstream)
    if set(decoded.addresses) != full:
        raise InvalidSamrasStructure("SAMRAS magnitude roundtrip address-set mismatch")
    return structure.bitstream


def closure_size(named_addresses: set[str]) -> int:
    """Number of addresses ``decode_canonical_bitstream`` will yield (closure size)."""
    return len(prefix_closure(named_addresses))


def recompiled_magnitude_raw(row: Any, named_addresses: set[str]) -> Any:
    """Return ``row.raw`` with its bitstream (head[2]) recomputed over the node set.

    Preserves head[0] (self address), head[1] (root ref ``0-0-5``) and the tail
    label verbatim; only the magnitude bitstream changes.
    """
    raw = row.raw
    if not (isinstance(raw, list) and raw and isinstance(raw[0], list) and len(raw[0]) >= 3):
        raise InvalidSamrasStructure(f"row {row.datum_address} is not a SAMRAS magnitude row")
    bits = build_magnitude_bitstream(named_addresses)
    head = list(raw[0])
    head[2] = bits
    return [head, *list(raw[1:])]
