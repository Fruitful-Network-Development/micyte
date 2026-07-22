#!/usr/bin/env python3
"""Shared agro_erp datum-document helpers (constants, encoders, doc rebuild/mint).

Extracted verbatim from the retired one-shot ``ingest_agro_erp_ledger.py`` (the
2026-06 ledger ingest, long applied) so the LIVE consumers — ``agro_write_runtime``,
``add_agro_erp_contract``, ``edit_agro_erp_farm_profile``, ``add_product_unit_weight``
— stop depending on a superseded migration script. Pure helpers; no CLI, no writes
of its own beyond the ``documents``-index upsert callers invoke explicitly.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import time
from pathlib import Path

from micyte.core.datum_ops import field_registry as _fr

# Re-exported for one-stop importing by the write-path consumers.
from micyte.core.document_naming import (
    format_canonical_document_id,
    parse_canonical_document_id,
)
from micyte.core.mss import compute_mss_hash
from micyte.core.structures.hops import (  # noqa: F401  (re-exports)
    build_chronology_authority,
    encode_utc_datetime_as_hops,
    schema_from_anchor_payload,
)
from micyte.core.structures.samras.codec import (
    decode_canonical_bitstream,
    encode_canonical_structure_from_addresses,
)
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
TENANT = "fnd"
TITLE_BITS = 512            # niu-baciloid-256-64 title width
NOMINAL_BITS = 136          # nominal-256-17 = 17 bytes x 8 bits

# Reference (rf.) markers (positional pairs shape). Single-sourced from the field
# registry (the FARM/agro namespace) — one definition of each token, network-wide.
RF_LCL_ID = _fr.marker(_fr.FARM, "lcl_id")     # rf.3-1-5 — record identity + cross-doc refs
RF_TXA_ID = _fr.marker(_fr.FARM, "txa_id")     # rf.3-1-1 — structural/type parents
RF_TITLE = _fr.marker(_fr.FARM, "title")       # rf.3-1-2 — title-babelette (512-bit ASCII)
RF_COORD = _fr.marker(_fr.FARM, "coordinate")  # rf.3-1-3 — HOPS coordinate (plot polygons)
RF_UTC = _fr.marker(_fr.FARM, "utc")           # rf.3-1-6 — HOPS-UTC (dates)
RF_NOMINAL = _fr.marker(_fr.FARM, "nominal")   # rf.3-1-7 — weight/cost/amount placeholders

# Agro anchor addresses.
ANCHOR_HOPS_CHRONO_MAG = "1-1-6"   # HOPS-chronological magnitude (the agro clock)
ANCHOR_LCL_SAMRAS = "1-1-5"        # lcl-SAMRAS magnitude (recompiled on lcl mints)
ANCHOR_TIME_PRIMITIVE = "0-0-1"    # time-ordinal-position (chronological mag base)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def _encode_label_bits(label: str, *, bits: int = TITLE_BITS) -> str:
    raw = "".join(format(b, "08b") for b in label.encode("ascii"))
    if len(raw) > bits:
        raise ValueError(f"label {label!r} exceeds {bits} bits ({bits // 8} chars)")
    return raw.ljust(bits, "0")


def _decode_label_bits(bits: str) -> str:
    chars = []
    for i in range(0, len(bits), 8):
        byte = int(bits[i:i + 8], 2)
        if byte == 0:
            break
        chars.append(chr(byte))
    return "".join(chars)


def _prefix_closure(named_addresses: set[str]) -> set[str]:
    full: set[str] = set()
    for addr in named_addresses:
        segments = addr.split("-")
        for depth in range(1, len(segments) + 1):
            full.add("-".join(segments[:depth]))
    return full


def _build_magnitude_bitstream(named_addresses: set[str]) -> str:
    full = _prefix_closure(named_addresses)
    structure = encode_canonical_structure_from_addresses(sorted(full))
    decoded = decode_canonical_bitstream(structure.bitstream)
    if set(decoded.addresses) != full:
        raise SystemExit("SAMRAS magnitude roundtrip address-set mismatch")
    return structure.bitstream


def _row(datum_address: str, raw) -> AuthoritativeDatumDocumentRow:
    return AuthoritativeDatumDocumentRow(datum_address=datum_address, raw=raw)


def _as_rows(document: AuthoritativeDatumDocument) -> list[AuthoritativeDatumDocumentRow]:
    out: list[AuthoritativeDatumDocumentRow] = []
    for r in document.rows:
        if isinstance(r, AuthoritativeDatumDocumentRow):
            out.append(r)
        else:
            out.append(AuthoritativeDatumDocumentRow(datum_address=r["datum_address"], raw=r["raw"]))
    return out


def _rebuild_document(
    *,
    existing: AuthoritativeDatumDocument,
    overlay: dict[str, AuthoritativeDatumDocumentRow],
    name: str,
) -> tuple[AuthoritativeDatumDocument, str]:
    """Existing rows kept in order with overlay replacements applied in place;
    overlay rows for never-seen addresses appended. Re-derives canonical id from
    the content hash (order-independent; idempotent)."""
    out: list[AuthoritativeDatumDocumentRow] = []
    seen: set[str] = set()
    for r in _as_rows(existing):
        a = r.datum_address
        if a in overlay:
            out.append(overlay[a])
            seen.add(a)
        else:
            out.append(r)
    for a, r in overlay.items():
        if a not in seen:
            out.append(r)
    return _finalize(dataclasses.replace(existing, rows=tuple(out)), name)


def _doc_msn_sandbox(document_id: str) -> tuple[str, str]:
    """(msn_id, sandbox) from an lv. id — the doc's OWN identity, never a guess.

    Lets the write path target whatever farm sandbox a candidate document already lives in —
    the sandbox is not part of the MSS hash, so re-finalizing preserves it. New farms (a
    distinct sandbox/msn) flow through automatically once their docs carry their own id.

    Raises on a non-lv/blank id rather than inventing one: every caller passes a real
    document id (a loaded doc, or a placeholder minted with an explicit msn+sandbox), so a
    missing sandbox here is a malformed candidate, not a case to answer with one farm's
    identity. The old fallback paired FND's msn with Trapp's sandbox — a nonsense identity
    once each farm became its own instance.
    """
    p = parse_canonical_document_id(document_id)
    if not p.sandbox:
        raise ValueError(f"cannot derive msn/sandbox from id {document_id!r}")
    return p.msn_id, p.sandbox


def _finalize(candidate: AuthoritativeDatumDocument, name: str) -> tuple[AuthoritativeDatumDocument, str]:
    msn, sandbox = _doc_msn_sandbox(candidate.document_id)
    placeholder = format_canonical_document_id(
        prefix="lv", msn_id=msn, sandbox=sandbox, name=name, version_hash="0" * 64
    )
    candidate = dataclasses.replace(candidate, document_id=placeholder)
    identity = compute_mss_hash(candidate)
    real_hash = identity["version_hash"]
    if real_hash.startswith("sha256:"):
        real_hash = real_hash[len("sha256:"):]
    real_id = format_canonical_document_id(
        prefix="lv", msn_id=msn, sandbox=sandbox, name=name, version_hash=real_hash
    )
    return dataclasses.replace(candidate, document_id=real_id), real_hash


def _make_new_doc(
    name: str,
    rows: list[AuthoritativeDatumDocumentRow],
    *,
    metadata: dict,
    sandbox: str,
    msn_id: str,
) -> tuple[AuthoritativeDatumDocument, str]:
    slug = sandbox.replace("_", "-")
    candidate = AuthoritativeDatumDocument(
        document_id=format_canonical_document_id(
            prefix="lv", msn_id=msn_id, sandbox=sandbox, name=name, version_hash="0" * 64),
        source_kind="sandbox_source",
        document_name=name,
        relative_path=f"sandbox/{slug}/lv.{msn_id}.{sandbox}.{name}.json",
        canonical_name=name,
        tool_id=sandbox,
        is_anchor=False,
        document_metadata=metadata,
        rows=tuple(rows),
    )
    return _finalize(candidate, name)


def _upsert_documents_row(authority_db: Path, *, name: str, document_id: str, version_hash: str, is_anchor: bool) -> None:
    msn, sandbox = _doc_msn_sandbox(document_id)
    now = int(time.time() * 1000)
    conn = sqlite3.connect(authority_db)
    try:
        conn.execute(
            "DELETE FROM documents WHERE tenant_id=? AND msn_id=? AND sandbox=? AND name=?",
            (TENANT, msn, sandbox, name),
        )
        conn.execute(
            "INSERT INTO documents (tenant_id, document_id, prefix, msn_id, sandbox, name, "
            "version_hash, is_anchor, origin, created_at) VALUES (?, ?, 'lv', ?, ?, ?, ?, ?, 'local', ?)",
            (TENANT, document_id, msn, sandbox, name, f"sha256:{version_hash}", 1 if is_anchor else 0, now),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# LCL extension (reuse-by-title; mint absent)
# --------------------------------------------------------------------------- #
class LclBuilder:
    """Extends the lcl node-address tree with reuse-by-title idempotency."""

    def __init__(self, lcl_rows: list[AuthoritativeDatumDocumentRow]):
        self.label_to_node: dict[str, str] = {}
        self.node_set: set[str] = set()
        self.max_42 = 0
        self.child_max: dict[str, int] = {}
        for r in lcl_rows:
            if not r.datum_address.startswith("4-2-"):
                continue
            self.max_42 = max(self.max_42, int(r.datum_address.split("-")[2]))
            head = r.raw[0]
            node = str(head[2]) if len(head) >= 3 else None
            label = str(r.raw[1][0]) if len(r.raw) > 1 and r.raw[1] else ""
            if not node:
                continue
            self.node_set.add(node)
            self.label_to_node.setdefault(label.lower(), node)
            parent = node.rsplit("-", 1)[0] if "-" in node else "<root>"
            ordn = int(node.rsplit("-", 1)[1]) if "-" in node else int(node)
            self.child_max[parent] = max(self.child_max.get(parent, 0), ordn)
        self.overlay: dict[str, AuthoritativeDatumDocumentRow] = {}
        self._next_42 = self.max_42 + 1

    def _add_row(self, node: str, label: str, marker: str) -> None:
        key = f"4-2-{self._next_42}"
        self._next_42 += 1
        self.overlay[key] = _row(
            key, [[key, marker, node, RF_TITLE, _encode_label_bits(label)], [label]]
        )
        self.node_set.add(node)
        self.label_to_node[label.lower()] = node
        parent = node.rsplit("-", 1)[0] if "-" in node else "<root>"
        ordn = int(node.rsplit("-", 1)[1]) if "-" in node else int(node)
        self.child_max[parent] = max(self.child_max.get(parent, 0), ordn)

    def ensure(self, node: str, label: str, marker: str) -> str:
        """Ensure a fixed-address titled node exists; reuse by title."""
        if label.lower() in self.label_to_node:
            return self.label_to_node[label.lower()]
        self._add_row(node, label, marker)
        return node

    def mint_child(self, parent: str, label: str, marker: str) -> str:
        """Mint (or reuse-by-title) the next contiguous child under ``parent``."""
        if label.lower() in self.label_to_node:
            return self.label_to_node[label.lower()]
        nxt = self.child_max.get(parent, 0) + 1
        node = f"{parent}-{nxt}"
        self._add_row(node, label, marker)
        return node
