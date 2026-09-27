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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from micyte.core.datum_ops import datum_resolve as _dr
from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops import local_domain as _ld

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
    identity. The old fallback paired FND's msn with the farm instance's sandbox — a nonsense identity
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


def _upsert_documents_rows(
    authority_db: Path, entries: list[tuple[str, str, str, bool]]
) -> None:
    """Point the ``documents`` index at each ``(name, document_id, version_hash,
    is_anchor)``, in ONE transaction.

    One connection for the whole write, not one per document: these follow a
    catalog write that is itself a single transaction, so splitting them made the
    index able to describe a document set that never existed. ``busy_timeout`` is
    set here too — this is the only place in the agro path that opens the authority
    outside the adapter, so it is also the only place that could still raise
    "database is locked" the instant a reader was present.
    """
    if not entries:
        return
    now = int(time.time() * 1000)
    conn = sqlite3.connect(authority_db)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        for name, document_id, version_hash, is_anchor in entries:
            msn, sandbox = _doc_msn_sandbox(document_id)
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


def _upsert_documents_row(authority_db: Path, *, name: str, document_id: str, version_hash: str, is_anchor: bool) -> None:
    """Single-document sibling of :func:`_upsert_documents_rows`."""
    _upsert_documents_rows(authority_db, [(name, document_id, version_hash, is_anchor)])


# --------------------------------------------------------------------------- #
# LCL extension (reuse-by-title; mint absent)
# --------------------------------------------------------------------------- #
def _split_node(node: str) -> tuple[str, int]:
    """``"1-2-3"`` -> ``("1-2", 3)``; a bare root -> ``("<root>", n)``."""
    if "-" in node:
        parent, _, ordinal = node.rpartition("-")
        return parent, int(ordinal)
    return "<root>", int(node)


#: The families a local domain definition row lives in — see
#: :mod:`micyte.core.datum_ops.local_domain`. Imported rather than spelled so the address
#: arithmetic and the reader cannot drift.
class _LogRows:
    """The one shape `read_log` needs: something with ``.rows``."""

    __slots__ = ("rows",)

    def __init__(self, rows: Any) -> None:
        self.rows = rows


_NODE_FAMILY = _ld.NODE_FAMILY
_REF_FAMILY = _ld.REF_FAMILY
_FULL_FAMILY = _ld.FULL_FAMILY
ld_ROOT_LABEL = _ld.ROOT_LABEL
_DEFINITION_FAMILIES = _ld.DEFINITION_FAMILIES
_kind_of_marker = _dr.kind_of_marker
_NODE_KIND_TYPE = _dr.NODE_KIND_TYPE


def _markers_of(
    lcl_rows: Sequence[AuthoritativeDatumDocumentRow],
) -> tuple[str, str]:
    """``(type marker, title marker)`` this tree's own rows are written with.

    Read off the FIRST definition row rather than derived from a namespace, for the reason
    ``_root_type_marker`` gives: the only reader that can settle what a marker means here
    is the document. An empty tree falls back to the farm pair, which is what every caller
    got before this existed and what a fresh farm sandbox still wants.
    """
    title = ""
    for row in lcl_rows or ():
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else None
        if not isinstance(head, list) or len(head) < 5:
            continue
        node_marker, title_marker = str(head[1]), str(head[3])
        if not node_marker.startswith("rf.") or not title_marker.startswith("rf."):
            continue
        # The title marker is a fact about the ANCHOR, so the first definition row settles
        # it. The TYPE marker is not: a farm tree's first row may well be a record, which
        # rides the instance ref, and minting types on it would classify every new node as
        # a record. So the type marker is only taken from a row that reads as one.
        title = title or title_marker
        if _kind_of_marker(node_marker) == _NODE_KIND_TYPE:
            return node_marker, title_marker
    return RF_TXA_ID, title or RF_TITLE


class LclBuilder:
    """Extends the lcl node-address tree with reuse-by-title idempotency.

    **Two families, one node.** A definition row lives at ``4-2-N`` when the node denotes
    nothing and at ``4-3-N`` when it denotes a document — the value_group IS the tuple
    count (:mod:`micyte.core.datum_ops.local_domain`), so the third ``(reference,
    magnitude)`` pair moves the row. A node carries EXACTLY ONE of them, which is what lets
    every reader keep matching by shape instead of by address.

    **The markers are read off the document, not assumed.** Which ref spells a TYPE varies
    by anchor — the farm stack says ``txa_id`` (``rf.3-1-1``), the registrar's ``lcl`` says
    ``lcl_id`` (``rf.3-1-13``) — and the title babelette moves with it (``rf.3-1-2`` vs
    ``rf.3-1-3``). Writing the farm pair into a registrar-numbered sandbox produced rows
    whose cells mean ``coordinate`` and ``msn_id``: harmless while nothing read the fold,
    wrong the moment an archetype had to recognise them. So a new row joins the tree it is
    being added to rather than the namespace this module was written against.
    """

    def __init__(self, lcl_rows: list[AuthoritativeDatumDocumentRow]):
        # ONE read of the same rows, so "which trailing reference is the document" has one
        # answer here and on every surface. Building a second classifier from position
        # would be the drift this whole module exists to avoid.
        _log = _ld.read_log(_LogRows(tuple(lcl_rows)))
        self.label_to_node: dict[str, str] = {}
        #: (parent, label) -> node. `mint_child` reuses through THIS, not `label_to_node`:
        #: two records with the same name under different parents are two records, and a
        #: global lookup silently handed back the first parent's child for both.
        self.child_label_to_node: dict[tuple[str, str], str] = {}
        self.node_set: set[str] = set()
        #: node -> the document slot it denotes ("" is absent, not stored).
        self.slot_by_node: dict[str, str] = {}
        #: node -> the icon slot it wears ("" is absent, not stored).
        self.icon_by_node: dict[str, str] = {}
        #: node -> the datum address of its one definition row, so a writer can replace
        #: exactly it rather than appending a second.
        self.row_by_node: dict[str, str] = {}
        self.max_42 = 0
        self.child_max: dict[str, int] = {}
        highest: dict[str, int] = {}
        for r in lcl_rows:
            family, _, tail = str(r.datum_address).rpartition("-")
            if family not in _DEFINITION_FAMILIES or not tail.isdigit():
                continue
            highest[family] = max(highest.get(family, 0), int(tail))
            head = r.raw[0]
            node = str(head[2]) if len(head) >= 3 else None
            label = str(r.raw[1][0]) if len(r.raw) > 1 and r.raw[1] else ""
            if not node:
                continue
            self.node_set.add(node)
            self.label_to_node.setdefault(label.lower(), node)
            parent, ordn = _split_node(node)
            self.child_label_to_node.setdefault((parent, label.lower()), node)
            self.child_max[parent] = max(self.child_max.get(parent, 0), ordn)
            self.row_by_node.setdefault(node, str(r.datum_address))
            # Classified by the LOG, never by position: on a subdivided tree the FIRST
            # trailing reference is the ICON, so `pointer_of` here recorded a glyph as
            # the document a node denotes.
            slot = _log.slot_of(node)
            icon = _log.icon_of(node)
            if slot and node not in self.slot_by_node:
                self.slot_by_node[node] = slot
            if icon and node not in self.icon_by_node:
                self.icon_by_node[node] = icon
        # `max_42` kept under its old name: three callers read it, and it has always meant
        # "the last node-family iteration", which is still exactly what it is.
        self.max_42 = highest.get(_NODE_FAMILY, 0)
        self.type_marker, self.title_marker = _markers_of(lcl_rows)
        #: THE FLOOR (2026-09-08). Every node wears a glyph, so a row minted without one
        #: wears this. It is the sandbox's `circle` slot when it holds one, else the
        #: first glyph on the branch — and `""` on a tree with no glyph branch at all,
        #: which is the pre-migration shape and keeps writing `4-2`: a default glyph
        #: that does not exist would be a dangling reference in every node at once.
        self.default_glyph: str = _log.default_glyph()
        #: Whether this tree carries the canonical base structure (a `local_domain`
        #: root). A canonical tree has ONE root, and `mint_root` refuses to give it a
        #: second; the operator's tree lives under `objects`.
        self.canonical: bool = _log.canonical
        self.object_root: str = _log.object_root
        self.overlay: dict[str, AuthoritativeDatumDocumentRow] = {}
        self._next: dict[str, int] = {
            family: highest.get(family, 0) + 1 for family in _DEFINITION_FAMILIES
        }
        self._next[_NODE_FAMILY] = self.max_42 + 1

    @property
    def _next_42(self) -> int:
        """The next node-family iteration. Read by `insert_node`, which mints its own row."""
        return self._next[_NODE_FAMILY]

    def _add_row(self, node: str, label: str, marker: str,
                 extra: Sequence[tuple[str, Any]] = (), slot: str = "",
                 icon: str = "") -> None:
        """Write this node's ONE definition row, in the family its arity requires.

        Icon FIRST, then the document. The order is the reader's contract, not a taste: a
        ``4-4`` row carries two cells whose marker is identical, so only their position
        distinguishes them once a tree has not yet subdivided its branches.
        """
        # Never below the floor where there is a glyph to wear: a row minted with no
        # icon wears the sandbox's default. `""` only on a tree with no glyph branch.
        icon = icon or self.default_glyph
        trailing = [pair for pair in ((marker, icon), (marker, slot)) if pair[1]]
        family = (_FULL_FAMILY if len(trailing) == 2
                  else _REF_FAMILY if trailing else _NODE_FAMILY)
        key = f"{family}-{self._next[family]}"
        self._next[family] += 1
        head: list[Any] = [key, marker, node, self.title_marker, _encode_label_bits(label)]
        for extra_marker, extra_magnitude in extra:
            head += [extra_marker, extra_magnitude]
        for extra_marker, magnitude in trailing:
            head += [extra_marker, magnitude]
        if icon:
            self.icon_by_node[node] = icon
        if slot:
            self.slot_by_node[node] = slot
        self.overlay[key] = _row(key, [head, [label]])
        self.row_by_node[node] = key
        self.node_set.add(node)
        self.label_to_node[label.lower()] = node
        parent, ordn = _split_node(node)
        self.child_label_to_node[(parent, label.lower())] = node
        self.child_max[parent] = max(self.child_max.get(parent, 0), ordn)

    def ensure(self, node: str, label: str, marker: str) -> str:
        """Ensure a fixed-address titled node exists; reuse by title.

        The NODE is checked first, and an already-defined one is returned untouched whatever
        its title. Without that, asking for a concept at an address that is already defined
        under a different title appends a SECOND definition row for one node — live, one farm's
        ``1-1-6-1`` is titled ``invoice_instance`` while ``save_invoice`` asks for ``invoice``.
        Two definition rows make a node's label order-dependent and its kind ambiguous.

        The title lookup stays GLOBAL here on purpose: this is asked for a concept at a fixed
        address, so when the concept already lives elsewhere the caller must get the real node.
        """
        if node in self.node_set:
            return node
        if label.lower() in self.label_to_node:
            return self.label_to_node[label.lower()]
        self._add_row(node, label, marker)
        return node

    #: What `_split_node` calls the parent of a top-level node. A sentinel rather than
    #: `""`, so `child_max` can count roots in the same dict it counts every other
    #: generation in — and so a caller cannot accidentally address it as a real parent.
    ROOT_PARENT = "<root>"

    def mint_root(self, label: str, marker: str,
                  extra: Sequence[tuple[str, Any]] = ()) -> str:
        """Mint (or reuse) the next TOP-LEVEL node titled ``label`` — ``"2"``, ``"3"``, …

        A SAMRAS tree may have several roots, and the corpus's largest one does:
        ``taxonomy/txa`` holds ``1 cytota``, ``2``, ``3`` and ``4``. Nothing could write
        that shape. ``mint_child`` joins ``parent + "-" + n`` and so cannot express a
        bare ordinal; ``_split_node`` already files roots under :data:`ROOT_PARENT`, so
        the count was there the whole time with no way to reach it.

        Reuse is by label among the roots, the same idempotency ``mint_child`` gives
        within a parent — asking twice for the same top-level branch returns the one that
        exists rather than growing a second with the same name.
        """
        key = (self.ROOT_PARENT, label.lower())
        if key in self.child_label_to_node:
            return self.child_label_to_node[key]
        if self.canonical:
            # ONE root (2026-09-08). The operator's tree is the `objects` branch's
            # children; a second top-level node would be a second namespace beside the
            # one every reader finds by label. Refused rather than redirected: a caller
            # that asked for a ROOT and got a child of `objects` would go on believing
            # the tree has two roots.
            raise ValueError(
                f"this local domain has one root ({ld_ROOT_LABEL}); a top-level branch "
                f"is a child of its objects branch ({self.object_root or '?'}) — mint it "
                "there")
        node = str(self.child_max.get(self.ROOT_PARENT, 0) + 1)
        self._add_row(node, label, marker, extra)
        return node

    def mint_new_child(self, parent: str, label: str, marker: str,
                       extra: Sequence[tuple[str, Any]] = (), slot: str = "",
                       icon: str = "") -> str:
        """Mint the next child of ``parent`` titled ``label``, WITHOUT reuse-by-title.

        ``mint_child``'s idempotency is right for a vocabulary — asking twice for the type
        ``services`` must give one node. It is wrong for a DOCUMENT slot: two documents may
        honestly share a title ("Invoice", "Invoice"), and reusing the slot would hand the
        second one the first one's name and silently overwrite it.
        """
        nxt = self.child_max.get(parent, 0) + 1
        node = f"{parent}-{nxt}"
        self._add_row(node, label, marker, extra, slot, icon)
        return node

    def mint_child(self, parent: str, label: str, marker: str,
                   extra: Sequence[tuple[str, Any]] = ()) -> str:
        """Mint (or reuse) the next contiguous child of ``parent`` titled ``label``.

        Reuse is scoped to ``(parent, label)``. A global title lookup made
        ``mint_child("1-1", "notes")`` and ``mint_child("1-2", "notes")`` the same node, so the
        second caller got a child of a parent it never named and one of the two records was
        lost. Scoping keeps idempotency where it belongs — re-minting under the same parent
        still returns the same node, including a retired sibling's label, which is what the
        effective-dating invariant relies on.

        ``extra`` appends further ``(marker, magnitude)`` pairs to the definition row's head —
        how a node minted as a record CONTAINER carries its ``rf.3-1-8`` VIEW marker from the
        start. Declaring one that way writes a new row rather than editing a live definition
        row, which is the whole reason the container is minted instead of stamped. Empty by
        default, so every existing caller writes exactly the head it always has.
        """
        key = (parent, label.lower())
        if key in self.child_label_to_node:
            return self.child_label_to_node[key]
        nxt = self.child_max.get(parent, 0) + 1
        node = f"{parent}-{nxt}"
        self._add_row(node, label, marker, extra)
        return node
