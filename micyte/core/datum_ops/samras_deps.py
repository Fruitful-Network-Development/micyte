"""SAMRAS-magnitude dependency detection, recompile, and denotation coherence.

A SAMRAS magnitude row encodes the *prefix-closure* of a sheet's defined node set as a
canonical bitstream rooted at ``0-0-5``. When the node set changes (relocate/mint/drop),
the magnitude must be recomputed. This module lifts the ingest script's
``_prefix_closure`` / ``_build_magnitude_bitstream`` verbatim so the library and the
script share one implementation, and adds the helpers the ops layer needs.

**Which anchor row holds which structure is DISCOVERED, never assumed.** There used to be
an ``ANCHOR_SAMRAS_SOURCE = {"1-1-1": "txa", "1-1-5": "lcl"}`` here, with a comment
deferring exactly this. That map is the agro_erp anchor's layout and is wrong elsewhere:
in the *registrar* anchor ``1-1-1`` is ``HOPS-spacial``, ``1-1-5`` is
``HOPS-chornological``, ``lcl-SAMRAS`` lives at ``1-1-6``, and there is a fourth structure
(``ruiqi-SAMRAS``) the map never mentioned. Everything that consulted the map was therefore
blind to that sandbox — which is how the registrar's anchor came to denote 53 of its lcl's
66 defined nodes with nothing noticing. :func:`discover_samras_structures` reads the row's
own tail label instead (``lcl-SAMRAS`` → the sheet named ``lcl``), which is the rule the
SAMRAS structure viewer already used to render these trees, so there is now one rule rather
than one rule and one fossil.

:func:`check_denotation` is the standing check that a stored magnitude still matches the
node set it claims to denote.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from micyte.core.structures.samras.codec import (
    decode_canonical_bitstream,
    encode_canonical_structure_from_addresses,
)
from micyte.core.structures.samras.validation import InvalidSamrasStructure

from .node_addrs import parse_node_addr
from .refs import defined_node_addrs

SAMRAS_ROOT_REF = "0-0-5"
SAMRAS_LABEL_SUFFIX = "-SAMRAS"
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


# --------------------------------------------------------------------------- #
# Which anchor row holds which structure — discovered from the row itself
# --------------------------------------------------------------------------- #
# Row-shape readers. Deliberately NOT imported from micyte/tools/_shared/utilities.py:
# core must not depend on tools. Six lines beats a boundary violation.
def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _tail_label(row: Any) -> str:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return "" if raw[1][0] is None else str(raw[1][0]).strip()
    return ""


def _addr_key(addr: str) -> tuple[int, ...]:
    out: list[int] = []
    for seg in str(addr).split("-"):
        out.append(int(seg) if seg.isdigit() else 0)
    return tuple(out)


@dataclass(frozen=True)
class SamrasStructureRef:
    """One ``*-SAMRAS`` structure an anchor carries.

    ``name`` is the label minus the suffix and is also the name of the sheet whose defined
    node set the magnitude denotes (``lcl-SAMRAS`` → ``lcl``).
    """

    name: str
    magnitude_addr: str
    bitstream: str


def discover_samras_structures(anchor: Any) -> list[SamrasStructureRef]:
    """Every node-address SAMRAS structure ``anchor`` carries, in address order.

    A structure is a row whose tail label ends in ``-SAMRAS`` and whose magnitude
    (``head[2]``) is a non-empty binary string. HOPS magnitudes are excluded because their
    labels do not end in the suffix — which is the whole point: the *label* says what the
    row is, so no per-sandbox address table is needed. Cheap by design: no decode.
    """
    out: list[SamrasStructureRef] = []
    for row in getattr(anchor, "rows", ()) or ():
        label = _tail_label(row)
        if not label.endswith(SAMRAS_LABEL_SUFFIX):
            continue
        head = _head(row)
        bitstream = "" if len(head) < 3 or head[2] is None else str(head[2]).strip()
        if not bitstream or any(bit not in "01" for bit in bitstream):
            continue
        out.append(SamrasStructureRef(
            name=label[: -len(SAMRAS_LABEL_SUFFIX)],
            magnitude_addr=("" if not head else str(row.datum_address).strip()),
            bitstream=bitstream,
        ))
    out.sort(key=lambda ref: _addr_key(ref.magnitude_addr))
    return out


def samras_magnitude_addr(anchor: Any, name: str) -> str:
    """The anchor address holding ``name``'s SAMRAS magnitude, or ``""`` when absent.

    The write-side companion of :func:`discover_samras_structures`. A recompile that
    hardcodes its target address writes the new bitstream over whatever happens to live
    there — in the registrar anchor, ``1-1-5`` is the chronological HOPS magnitude.
    """
    token = str(name).strip()
    for ref in discover_samras_structures(anchor):
        if ref.name == token:
            return ref.magnitude_addr
    return ""


# --------------------------------------------------------------------------- #
# Denotation coherence
# --------------------------------------------------------------------------- #
#: A magnitude that no longer matches its node set, or will not decode. Both are
#: regressions with a mechanical fix (recompile / re-encode), so a gate may fail on them.
DENOTATION_FAULTS = ("stale", "undecodable")
#: A node set that cannot be SAMRAS-encoded at all. Real, but the fix is a decision about
#: the DATA, so this is a reported open condition rather than a gate failure — a
#: permanently-red check trains everyone to ignore it.
DENOTATION_OPEN = ("uncompilable",)


@dataclass(frozen=True)
class DenotationFinding:
    """What one structure's stored magnitude says versus what its sheet defines.

    ``status`` is one of five, because "divergent" is four different situations and only
    two of them are anybody's mistake:

    ``coherent``
        The recompile equals the stored bitstream. Nothing to do.
    ``stale``
        The node set encodes fine and differs from what is stored — a recompile was
        skipped. ``undenoted`` names the defined nodes the magnitude leaves out.
    ``uncompilable``
        The defined node set cannot be encoded (``detail`` carries the codec's own
        message, e.g. *child ordinals must be contiguous for 1-3*). The stored magnitude
        is whatever last compiled, so ``undenoted`` still names what is invisible.
    ``undecodable``
        The stored bitstream itself will not decode.
    ``unpaired``
        No sheet of that name defines anything — the documented structure-only case
        (``msn`` has no defining document in most sandboxes). Not a fault.
    """

    sandbox: str
    structure: str
    magnitude_addr: str
    status: str
    defined_count: int
    denoted_count: int
    undenoted: tuple[str, ...]
    detail: str

    @property
    def is_fault(self) -> bool:
        return self.status in DENOTATION_FAULTS

    def summary(self) -> str:
        where = f"{self.sandbox}." if self.sandbox else ""
        head = (f"{where}{self.structure} @{self.magnitude_addr} {self.status}: "
                f"defined={self.defined_count} denoted={self.denoted_count}")
        if self.undenoted:
            head += f" undenoted={len(self.undenoted)}"
        return f"{head} — {self.detail}" if self.detail else head


def _undenoted(bitstream: str, defined: set[str]) -> tuple[tuple[str, ...], int, str]:
    """``(undenoted, denoted_count, decode_error)`` for a bitstream worth decoding."""
    try:
        denoted = set(decode_canonical_bitstream(bitstream).addresses)
    except InvalidSamrasStructure as exc:
        return (), 0, str(exc)
    return tuple(sorted(defined - denoted, key=parse_node_addr)), len(denoted), ""


def check_denotation(
    anchor: Any,
    sheets: Mapping[str, Any],
    *,
    sandbox: str = "",
    deep: bool = False,
) -> list[DenotationFinding]:
    """One finding per ``*-SAMRAS`` structure the anchor carries.

    ``sheets`` maps document name → document; only the names the anchor actually names are
    consulted, so passing a whole sandbox catalog is fine.

    The coherent path does **no decode**: when the recompile equals the stored bitstream the
    denoted set is by definition the defined set's prefix closure, whose size
    :func:`closure_size` gives directly. That matters — re-encoding the 4,084-node taxonomy
    txa costs ~0.26 s while the registrar lcl costs nothing, so the cost is paid only where
    there is a divergence to enumerate. ``deep`` additionally decodes ``unpaired``
    magnitudes, which is the only way a structure with no defining document can be caught
    being undecodable; it is off by default because those are the large ones.
    """
    findings: list[DenotationFinding] = []
    for ref in discover_samras_structures(anchor):
        doc = sheets.get(ref.name)
        defined = defined_node_addrs(doc) if doc is not None else set()
        if not defined:
            denoted_count, detail = 0, f"no {ref.name} definitions in this sandbox"
            status = "unpaired"
            if deep:
                _, denoted_count, decode_error = _undenoted(ref.bitstream, set())
                if decode_error:
                    status, detail = "undecodable", decode_error
                else:
                    detail = f"{detail}; magnitude denotes {denoted_count}"
            else:
                detail = f"{detail} ({len(ref.bitstream)} bits, not decoded)"
            findings.append(DenotationFinding(
                sandbox=sandbox, structure=ref.name, magnitude_addr=ref.magnitude_addr,
                status=status, defined_count=0, denoted_count=denoted_count,
                undenoted=(), detail=detail))
            continue

        try:
            expected = build_magnitude_bitstream(defined)
        except InvalidSamrasStructure as exc:
            undenoted, denoted_count, decode_error = _undenoted(ref.bitstream, defined)
            detail = str(exc)
            if decode_error:
                detail = f"{detail}; stored magnitude also will not decode: {decode_error}"
            findings.append(DenotationFinding(
                sandbox=sandbox, structure=ref.name, magnitude_addr=ref.magnitude_addr,
                status="uncompilable", defined_count=len(defined),
                denoted_count=denoted_count, undenoted=undenoted, detail=detail))
            continue

        if expected == ref.bitstream:
            findings.append(DenotationFinding(
                sandbox=sandbox, structure=ref.name, magnitude_addr=ref.magnitude_addr,
                status="coherent", defined_count=len(defined),
                denoted_count=closure_size(defined), undenoted=(), detail=""))
            continue

        undenoted, denoted_count, decode_error = _undenoted(ref.bitstream, defined)
        if decode_error:
            findings.append(DenotationFinding(
                sandbox=sandbox, structure=ref.name, magnitude_addr=ref.magnitude_addr,
                status="undecodable", defined_count=len(defined), denoted_count=0,
                undenoted=(), detail=decode_error))
            continue
        findings.append(DenotationFinding(
            sandbox=sandbox, structure=ref.name, magnitude_addr=ref.magnitude_addr,
            status="stale", defined_count=len(defined), denoted_count=denoted_count,
            undenoted=undenoted,
            detail="a RecompileMagnitude is missing"))
    return findings


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


def recompiled_anchor_rows(anchor: Any, node_set: set[str], *, name: str = "lcl") -> list[Any]:
    """The anchor's rows with ``name``'s SAMRAS magnitude recompiled for ``node_set``.

    The PURE half of the runtime's ``_recompiled_anchor``, in core so the SEED can call
    it. A copied anchor keeps the source sandbox's magnitude verbatim, and until
    2026-09-08 nothing on the provisioning path recomputed it: four live sandboxes drew
    47–6,412 of somebody else's nodes, every one labelled ``(undefined)``, because the
    tree viewer draws what the MAGNITUDE denotes and the document defined six rows. The
    seed writes the rows; this is the other half of that write.

    The target row is DISCOVERED by its tail label, never assumed — ``lcl-SAMRAS`` sits
    at ``1-1-5`` in a farm anchor and ``1-1-6`` in the registrar's, and a hardcoded
    address once overwrote the registrar's chronological magnitude. Only the bitstream
    moves: ``recompiled_magnitude_raw`` keeps the self address, the root ref and the
    label verbatim, and round-trips the encode before returning.

    Raises ``InvalidSamrasStructure`` when the anchor carries no such row, rather than
    returning the rows unchanged: the silent no-op is the worse half of the same defect,
    a seed that reports success over an anchor it could not correct.
    """
    from micyte.core.datum_documents import AuthoritativeDatumDocumentRow

    addr = samras_magnitude_addr(anchor, name)
    if not addr:
        raise InvalidSamrasStructure(
            f"anchor carries no {name}-SAMRAS magnitude row to recompile")
    out: list[Any] = []
    for row in getattr(anchor, "rows", ()) or ():
        if str(getattr(row, "datum_address", "")) != addr:
            out.append(row)
            continue
        out.append(AuthoritativeDatumDocumentRow(
            datum_address=addr, raw=recompiled_magnitude_raw(row, set(node_set))))
    return out
