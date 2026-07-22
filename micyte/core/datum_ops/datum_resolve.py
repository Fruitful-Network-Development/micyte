"""Shared datum reference-resolution primitives (consolidation spine, Phase 2).

Single-sources the four things every agro_erp viewer/tool needs and that were
previously copy-pasted across the tool modules and ingest scripts:

* :class:`Markers` — the one ``rf.3-1-X`` reference-marker registry (was redeclared
  under inconsistent names: ``_LCL_MARKER`` vs ``_RF_LCL_ID``, ``_HOPS_MARKER`` vs
  ``_HOPS_COORD_MARKER``, ``RF_TITLE`` vs ``_TITLE_MARKER`` …). Re-exports the three
  in :mod:`.labels` so there is exactly one definition of each token.
* :func:`iter_marker_pairs` — the canonical ``(marker, magnitude)`` head walk, the
  loop reimplemented in contracts (×2), product_document and the invoice reader.
* :class:`NameIndex` + :func:`cached_index` — node-address → display-name resolution
  built by SHAPE (``refs._is_definition_head``, every prefix — not the hardcoded
  ``4-2-*`` the old ``LclNameIndex`` used, which silently returned nothing for
  invoice/contact definitions). One process-lifetime cache keyed on ``document_id``
  (content-hash derived) so contracts/txa stop rebuilding the 1.6k-entry decode.
* :func:`decode_label` / :func:`encode_label` / :func:`resolve_coordinate` — the
  title codec + HOPS ring decode (was hand-rolled as ``_decode_title_bits`` /
  ``_encode_bits`` / ``_ring_coords``).

Layering: this is ``core`` and must not import ``state_machine`` — the label decode
is implemented here over the same 8-bit ASCII encoding :mod:`.labels` produces
(canonical: stop at the first NUL byte), so no ``BinaryTextLens`` dependency.
"""

from __future__ import annotations

from typing import Any

from micyte.core.structures.hops import decode_hops_coordinate_token
from micyte.core.structures.samras.structure import as_text

from . import field_registry as _fr
from . import labels as _labels
from .refs import _head, _is_definition_head


class Markers:
    """The agro_erp ``rf.3-1-X`` reference-marker vocabulary, single-sourced.

    Each marker types the *following* magnitude slot in a row head. ``NODE_ID`` /
    ``LCL_ID`` carry node-address references; the rest carry encoded literals
    (title blob, HOPS coordinate/UTC tokens, msn id, nominal value).
    """

    NODE_ID = _labels.RF_NODE_ID      # rf.3-1-1 — txa node-id reference
    TITLE = _labels.RF_TITLE          # rf.3-1-2 — 512-bit ASCII title babelette
    COORDINATE = _fr.marker(_fr.FARM, "coordinate")   # rf.3-1-3 — HOPS lon/lat token
    MSN = _fr.marker(_fr.FARM, "msn_id")              # rf.3-1-4 — msn-id literal
    LCL_ID = _labels.RF_LCL_ID                        # rf.3-1-5 — lcl node-id reference
    UTC = _fr.marker(_fr.FARM, "utc")                 # rf.3-1-6 — HOPS-UTC date token
    NOMINAL = _fr.marker(_fr.FARM, "nominal")         # rf.3-1-7 — nominal-256-17 value
    VIEW = _fr.marker(_fr.FARM, "view")               # rf.3-1-8 — record-view token: flags a
    #                                   node as an instance-container the local_domain tool
    #                                   can expand into a record table (product/invoice/…).
    LCL_ID_MYC = _fr.marker(_fr.REGISTRAR, "lcl_id")  # rf.3-1-13 — registrar (mycelium) lcl
    #                                   node-id reference (that sandbox's rf.3-1-1/3-1-5
    #                                   slots are coordinate/identification, so the agro
    #                                   markers cannot double).

    # Markers whose magnitude is a node-address REFERENCE (not a literal).
    NODE_REF = frozenset({NODE_ID, LCL_ID, LCL_ID_MYC})

    @classmethod
    def is_node_ref(cls, marker: object) -> bool:
        return as_text(marker).lower() in cls.NODE_REF


def iter_marker_pairs(head: list[Any]):
    """Yield ``(marker, magnitude)`` for each pair in a datum row head.

    A head is ``[self_address, marker, magnitude, marker, magnitude, …]`` — the
    canonical positional ``2N+1`` pair model. Marker is returned stripped; the
    magnitude is returned verbatim (callers decode per the marker's kind).
    """
    for i in range(1, len(head) - 1, 2):
        yield as_text(head[i]), head[i + 1]


# Canonical title encode (re-export) + decode (inverse, NUL-terminated).
encode_label = _labels.encode_label_bits


def decode_label(bits: object) -> str:
    """Decode a fixed-width ASCII title/nominal babelette to text.

    Only a genuine binary babelette — char-set ⊆ {0,1} and length a non-zero multiple
    of 8 — is decoded; any other value (a plain label, or a short all-binary literal
    like ``"1011"``) is returned as-is, so callers may pass either an encoded blob or an
    already-plain label safely. Decoding stops at the first NUL byte and DROPS
    non-printable control bytes (restoring the safety of the replaced ``BinaryTextLens``,
    which never leaked raw control chars into rendered strings).
    """
    text = as_text(bits)
    if not text or len(text) % 8 or set(text) - {"0", "1"}:
        return text
    out: list[str] = []
    for i in range(0, len(text), 8):
        byte = int(text[i : i + 8], 2)
        if byte == 0:
            break
        if 32 <= byte <= 126:  # printable ASCII only — never leak control chars
            out.append(chr(byte))
    return "".join(out)


def resolve_coordinate(head: list[Any]) -> list[tuple[float, float]]:
    """Decode a family-4 ring head's ``rf.3-1-3`` HOPS tokens → ``(lon, lat)`` coords."""
    coords: list[tuple[float, float]] = []
    for i in range(len(head) - 1):
        if as_text(head[i]) == Markers.COORDINATE:
            decoded = decode_hops_coordinate_token(as_text(head[i + 1]))
            if decoded:
                coords.append((decoded["longitude"]["value"], decoded["latitude"]["value"]))
    return coords


def rewrite_title(raw: Any, label: str) -> list[Any]:
    """Re-encode a datum row's ``rf.3-1-2`` title from plain ASCII, in lock-step.

    A binary-title row is ``[head, [echo_label, …], …]`` where the head magnitude
    after the :data:`Markers.TITLE` marker is the canonical 512-bit blob and the
    tail's first element echoes the plain text. Return a NEW raw row with that blob
    re-encoded from ``label`` (via :func:`encode_label`) and the tail echo synced —
    **preserving** every other head slot, the rest of the tail (``tail[1:]``), and
    any trailing raw elements (a record sidecar). The marker is found by the
    canonical marker-only walk (odd head positions, as :func:`iter_marker_pairs`),
    so a TITLE token that happens to sit in a magnitude (data) slot is never
    mistaken for the marker.

    Single sources the retitle discipline previously copy-pasted in
    ``portal_datum_workbench_mutation_runtime._update_primary_value`` and
    ``scripts/edit_agro_erp_farm_profile.build``.

    Raises ``ValueError`` when ``raw`` is not a canonical binary-title row — a list
    head with a TITLE marker and a *list* tail (``primary_value_unsupported_shape``
    / ``not_a_title_row`` / ``title_slot_missing``) — or when ``label`` does not
    encode (``title_invalid``: >64 chars or non-ASCII). It never converts a
    record-shape (dict) tail or drops sidecar data.
    """
    if not (isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], (list, tuple))):
        raise ValueError("primary_value_unsupported_shape")
    tail = raw[1] if len(raw) > 1 else None
    if not isinstance(tail, (list, tuple)):
        # Record-shape (dict) or tail-less row: not a plain binary-title row —
        # refuse rather than clobber its named magnitudes.
        raise ValueError("not_a_title_row")
    head = list(raw[0])
    title_index = -1
    for marker_pos in range(1, len(head) - 1, 2):  # markers at odd slots (iter_marker_pairs)
        if as_text(head[marker_pos]) == Markers.TITLE:
            title_index = marker_pos + 1
            break
    if title_index < 0:
        raise ValueError("title_slot_missing")
    try:
        head[title_index] = encode_label(label)
    except (ValueError, UnicodeEncodeError) as exc:
        # encode_label raises ValueError (>64 chars) / UnicodeEncodeError (non-ASCII).
        raise ValueError(f"title_invalid: {exc}") from exc
    new_tail = [label, *list(tail)[1:]]
    return [head, new_tail, *list(raw)[2:]]


class NameIndex:
    """node_address → display name, built from a document's *definition* rows.

    A definition row's head is ``[addr, <node-ref marker>, <node_addr>, rf.3-1-2,
    <title blob>]`` (every prefix family, recognized by shape — txa ``4-2-*``, lcl
    ``4-2-*``, farm_profile ``7-*`` features, …). The index prefers the plain row
    tail label, falling back to the decoded title blob.
    """

    def __init__(self, document: Any | None):
        self._by_node: dict[str, str] = {}
        if document is None:
            return
        for row in getattr(document, "rows", ()) or ():
            head = _head(getattr(row, "raw", None))
            if head is None or not _is_definition_head(head):
                continue
            node = as_text(head[2])
            if not node:
                continue
            raw = row.raw
            label = ""
            if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
                label = as_text(raw[1][0])
            if not label and len(head) >= 5:
                label = decode_label(head[4])
            self._by_node.setdefault(node, label)

    def resolve(self, node_addr: object) -> str:
        return self._by_node.get(as_text(node_addr), "")

    def __len__(self) -> int:
        return len(self._by_node)


# Process-lifetime cache keyed on document_id (content-hash derived → no stale risk).
# Bounded: document_ids are content-hash derived, so every write mints a fresh key and
# superseded versions would otherwise accumulate unboundedly over the portal's lifetime.
# Cap with FIFO eviction of the oldest entry (dicts preserve insertion order).
_INDEX_CACHE: dict[str, NameIndex] = {}
_INDEX_CACHE_MAX = 64


def cached_index(document: Any | None) -> NameIndex:
    """A :class:`NameIndex` for ``document``, memoized on its ``document_id``."""
    if document is None:
        return NameIndex(None)
    key = as_text(getattr(document, "document_id", ""))
    cached = _INDEX_CACHE.get(key)
    if cached is None:
        cached = NameIndex(document)
        if key:
            _INDEX_CACHE[key] = cached
            if len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
                _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    return cached


def view_token_index(document: Any | None) -> dict[str, str]:
    """node_address → record-view token, from a document's :data:`Markers.VIEW` pairs.

    A node-definition row may carry a trailing ``rf.3-1-8`` pair whose magnitude is an
    ASCII token (``product`` / ``invoice`` / ``contract`` / ``contacts``) declaring that
    the node is an instance-container the ``local_domain`` tool can expand into a record
    table. The token is read off the same definition rows :class:`NameIndex` walks, by the
    canonical marker walk (so it is robust to extra head pairs and prefix family). Returns
    only the nodes that carry a VIEW token (empty dict when none / ``document is None``).
    """
    out: dict[str, str] = {}
    if document is None:
        return out
    for row in getattr(document, "rows", ()) or ():
        head = _head(getattr(row, "raw", None))
        if head is None or not _is_definition_head(head):
            continue
        node = as_text(head[2])
        if not node:
            continue
        for marker, magnitude in iter_marker_pairs(head):
            if marker == Markers.VIEW:
                token = decode_label(magnitude).strip()
                if token:
                    out[node] = token
                break
    return out


__all__ = [
    "Markers",
    "NameIndex",
    "cached_index",
    "decode_label",
    "encode_label",
    "iter_marker_pairs",
    "resolve_coordinate",
    "rewrite_title",
    "view_token_index",
]
