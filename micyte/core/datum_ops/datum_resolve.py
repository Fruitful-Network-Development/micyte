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

from collections.abc import Container, Mapping
from typing import Any

from micyte.core.document_naming import (
    ANCHOR_DOCUMENT_NAMES,
    LOCAL_DOMAIN_DOCUMENT_NAMES,
)
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


def marker_buckets(head: list[Any]) -> dict[str, list[Any]]:
    """``{marker: [magnitude, …]}`` for a row head, markers lowercased, order kept.

    Every reader of a record row wants the same thing: the lcl refs in order, the
    nominals in order, the date. That walk — three list comprehensions over
    ``range(1, len(head) - 1, 2)``, or a hand-rolled ``setdefault`` loop — was written
    out separately in the consumption model, the inventory table, the synopsis, the
    contract tool, the record-viewer base and the write runtime. Six spellings of one
    grammar, and the row head is positional, so a seventh is how a reader ends up
    indexing a slot that moved.

    Bucketing by marker (rather than zipping positionally) is also what makes a reader
    survive an added pair: a magnitude the caller did not write occupies its own
    marker's slot and shifts nothing in another's.
    """
    buckets: dict[str, list[Any]] = {}
    for marker, magnitude in iter_marker_pairs(head):
        buckets.setdefault(marker.lower(), []).append(magnitude)
    return buckets


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


def resolve_coordinate(head: list[Any], *, sandbox: str = "") -> list[tuple[float, float]]:
    """Decode a family-4 ring head's HOPS coordinate tokens → ``(lon, lat)`` coords.

    ``sandbox`` resolves the marker by LOGICAL FIELD through the decoder ring. Without it
    this matched ``Markers.COORDINATE`` — ``rf.3-1-3``, the FARM numbering — and so decoded
    the two farm profiles and NONE of the 469 registrar boundaries, whose coordinate is
    ``rf.3-1-1``. Measured: 565 ring rows, 556 of them invisible.

    The default keeps the farm marker so no existing caller changes behaviour, and every
    caller that knows its sandbox should pass it. That is the same blindness
    ``hops_geospatial_filament`` has, and the two have to be fixed together: widening the
    scan while this stayed narrow would offer four tools against geometry they cannot read.
    """
    markers = {Markers.COORDINATE}
    if sandbox:
        try:
            markers.add(_fr.marker(sandbox, "coordinate"))
        except KeyError:
            pass
    coords: list[tuple[float, float]] = []
    for i in range(len(head) - 1):
        if as_text(head[i]) in markers:
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


#: The node kinds :func:`node_kind_index` reports. ``unmarked`` is a real answer, not a
#: fallback — see that function's note on why it must never be read as ``type``.
NODE_KIND_TYPE = "type"
NODE_KIND_INSTANCE = "instance"
NODE_KIND_UNMARKED = "unmarked"

#: Which marker a node address rides on, and therefore what the node IS. A definition row
#: carries its own address on exactly one of these, and the choice is the distinction.
_KIND_BY_MARKER = {
    Markers.NODE_ID: NODE_KIND_TYPE,        # rf.3-1-1  — structural / definition node
    Markers.LCL_ID: NODE_KIND_INSTANCE,     # rf.3-1-5  — a record's own identity
    Markers.LCL_ID_MYC: NODE_KIND_TYPE,     # rf.3-1-13 — registrar's lcl vocabulary, all types
}


def kind_of_marker(marker: object) -> str:
    """``"type"`` / ``"instance"`` for a marker that carries a node's OWN address, else ``""``.

    The table above, asked one marker at a time. It exists because "which marker means a
    type HERE" is a question a WRITER has to answer too — :func:`~micyte.core.datum_ops.
    local_domain.domain_markers` picks a namespace's node marker by asking it — and a
    second copy of the mapping in the writer is how a written row ends up meaning something
    the reader disagrees with.
    """
    return _KIND_BY_MARKER.get(as_text(marker).lower(), "")


def node_kind_index(document: Any | None) -> dict[str, str]:
    """node_address → ``"type"`` | ``"instance"``, from which marker carries the address.

    The distinction is already in the corpus and has never been read. ``agro_write_runtime``
    mints a subtype container on :data:`Markers.NODE_ID` and the record under it on
    :data:`Markers.LCL_ID`; the registrar's ``lcl`` is a pure vocabulary and rides
    :data:`Markers.LCL_ID_MYC` throughout, so every node in it is a type. Live at the time
    of writing: farm A 65 type / 4 instance, farm B 19 / 3, registrar 65 / 0.

    It is what an editing surface needs in order to offer the right verb — "define a type
    here" against "create a record here" — so the tree has to carry it before anything can
    write from the tree.

    A node whose address rides neither marker is **absent from the map**, and the caller must
    read that as ``unmarked`` rather than as a type. Guessing "type" would let a generic
    create path mint records under a node nothing has established is a container; a node the
    corpus has not classified is one a human still has to look at. `parcel_1..3` in a farm's lcl are
    marked as types while the identically-shaped `field_1` is marked an instance, so the
    marking is known to be imperfect and the reader must not paper over it.

    Mirrors :func:`view_token_index`: same definition rows, same canonical marker walk.

    The other two SAMRAS structures answer honestly rather than emptily, which is worth
    knowing before reading a result:

    * **txa** carries every node on :data:`Markers.NODE_ID`, so a taxonomy reads as types
      throughout (4,084 of them). That is right — a taxon IS a definition — and it stays
      inert because txa carries no VIEW markers, so nothing there can take a record.
    * **msn** (``administrative`` / ``address_nodes``) carries its nodes on a marker that is
      neither, so it comes back EMPTY: a gazetteer address is not a type or a record in this
      sense, and saying nothing is the correct answer for it.
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
            kind = _KIND_BY_MARKER.get(as_text(marker).lower())
            # The node's OWN address, not a reference it happens to carry to another node:
            # a row may cite other nodes further along its head, and those say nothing about
            # what this node is.
            if kind is not None and as_text(magnitude) == node:
                out[node] = kind
                break
    return out


#: Documents a node-reference scan skips by default. An lcl definition row carries its own node
#: address on a node-ref marker — that is what MAKES it a definition, not a reference to
#: something else — and the anchor holds bitstreams, not addresses.
#:
#: Derived from the reserved NAME SETS, never from one literal each. It was
#: ``{"lcl", "anchor"}``: it therefore did not skip ``anthology`` (every instance's own
#: anchor) and it stopped skipping the local domain the moment that document was renamed —
#: at which point every node's own definition row read as a citation of itself and every
#: delete refused with "1 row(s) cite nodes here".
_NOT_REFERENCES: frozenset[str] = frozenset(
    ANCHOR_DOCUMENT_NAMES | set(LOCAL_DOMAIN_DOCUMENT_NAMES))


def references_to_node(
    documents: Mapping[str, Any], node: str, *, exclude: Container[str] = _NOT_REFERENCES
) -> list[tuple[str, str]]:
    """``(document_name, datum_address)`` for every row that CITES ``node``, sorted.

    A node address in a magnitude slot behind a :data:`Markers.NODE_REF` marker is a reference:
    a contract naming its referent plot, a feature naming the object it draws, a record naming
    the node it is. Anything that would remove or empty a node has to know who is pointing at
    it first — ``agro_write_runtime._contracted_nodes`` is this question asked about one
    document, and this is the same question asked about the whole sandbox.

    Only markers the vocabulary declares node-carrying are followed, so a title babelette that
    happens to read like an address is never mistaken for a citation.
    """
    wanted = as_text(node)
    hits: list[tuple[str, str]] = []
    if not wanted:
        return hits
    for name, document in (documents or {}).items():
        if name in exclude or document is None:
            continue
        for row in getattr(document, "rows", ()) or ():
            head = _head(getattr(row, "raw", None))
            if head is None:
                continue
            if any(Markers.is_node_ref(marker) and as_text(magnitude) == wanted
                   for marker, magnitude in iter_marker_pairs(head)):
                hits.append((as_text(name), as_text(getattr(row, "datum_address", ""))))
    return sorted(hits)


__all__ = [
    "NODE_KIND_INSTANCE",
    "NODE_KIND_TYPE",
    "NODE_KIND_UNMARKED",
    "Markers",
    "NameIndex",
    "cached_index",
    "decode_label",
    "encode_label",
    "iter_marker_pairs",
    "kind_of_marker",
    "marker_buckets",
    "node_kind_index",
    "references_to_node",
    "resolve_coordinate",
    "rewrite_title",
    "view_token_index",
]
