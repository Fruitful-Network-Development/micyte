"""Title-label codec for node-definition rows (512-bit ASCII babelette).

Lifted verbatim from ``ingest_agro_erp_product_profiles`` /
``promote_lcl_taxonomy`` so the manipulation library and the scripts share one
implementation: a node's human title is stored as the magnitude of an
``rf.3-1-2`` pair — ASCII, per-char 8-bit, right-zero-padded to 512 bits — with
the plaintext echoed in the row tail.
"""

from __future__ import annotations

from . import field_registry as _fr

TITLE_BITS = 512  # niu-baciloid-256-64: 64 chars x 8-bit ASCII

# The reference-design markers used by agro_erp definition rows. Single-sourced from the
# field registry (the FARM/agro namespace) so the numbering lives in exactly one place.
RF_NODE_ID = _fr.marker(_fr.FARM, "txa_id")  # rf.3-1-1 — SAMRAS-babelette-txa_id
RF_LCL_ID = _fr.marker(_fr.FARM, "lcl_id")   # rf.3-1-5 — SAMRAS-babelette-lcl_id
RF_TITLE = _fr.marker(_fr.FARM, "title")     # rf.3-1-2 — title-babelette (512-bit ASCII)


def encode_label_bits(label: str, *, bits: int = TITLE_BITS) -> str:
    """ASCII → per-char 8-bit, right-zero-padded to ``bits`` (raises if too long)."""
    raw = "".join(format(b, "08b") for b in label.encode("ascii"))
    if len(raw) > bits:
        raise ValueError(f"label {label!r} exceeds {bits} bits ({bits // 8} chars)")
    return raw.ljust(bits, "0")


def label_for_encoding(label: str) -> str:
    """≤64-char ASCII-safe label; drops a doubled flattened tail when over-length."""
    if len(label.encode("ascii", errors="strict")) <= TITLE_BITS // 8:
        return label
    head = label.rsplit("-", 1)[0]
    return head if len(head) <= TITLE_BITS // 8 else head[: TITLE_BITS // 8]
