"""What a viewscope may WRITE, decided by the declaration and the anchor.

Editing a datum row through its viewscope is the missing verb: the slot declaration already
says what a row's fields ARE, and until now saying it back required a bespoke write tool per
document kind (``job_manager`` -> ``save_job``, ``contacts_manager`` -> ``save_contact``,
``registrar_write_runtime`` -> ``save_profile_entry``, each with its own hardcoded
field->marker table).

Two questions have to be answered before a cell can be written, and BOTH are already
answered by data:

1. **May this slot be typed into?** The PRIMITIVE says so — see
   :data:`viewscope.EDITABLE_PRIMITIVES`. A ``node_chip`` is an address of another node, a
   ``map_ring`` is geometry, a ``symbol`` is an icon leaflet, a ``reference`` names another
   document. Each is chosen, not typed.

2. **How is the value ENCODED?** The sandbox's own ANCHOR says so. Each field address
   ``3-1-N`` carries a backing radix as its first magnitude, and that radix IS the encoding:
   ``2-1-1`` is the ASCII babelette, ``2-0-4`` is HOPS chronology, ``2-0-2`` is SAMRAS.

Measured across the live library before this was written: of the 56 slots editable by
primitive, only 8 fields carry the ASCII radix — ``title``, ``dns``, ``email``, ``website``,
``resource_kind``, ``instance_endpoint``, ``jurisdiction_type``, ``tiu_magnitude``. The rest
are refused, and refusing them is the point:

* ``utc`` and ``ic_stamp`` are HOPS tokens decodable only against this sandbox's own
  chronology. A text box would accept "2026-08-14", which is not a magnitude — the job
  writer calls ``day_to_hops_token`` precisely because "a `utc` cell holding '2026-03-16' is
  not a date, it is a broken cell".
* ``mss_source_binary`` is a PINNED CONTENT HASH. Typing one is a claim about a document's
  content that nothing checked — re-pin only what you can explain.
* ``price`` is whole cents. A text box would take "12.50" and store twelve.

So this module writes the values it can round-trip and NAMES the encoding it is refusing for
everything else. Adding a radix here is how a new value kind becomes editable; the refusal
is a stated reason, never a missing input.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label
from micyte.core.datum_ops.labels import encode_label_bits

#: The ASCII babelette. A magnitude backed by this radix is a label bit-string, and
#: ``encode_label_bits``/``decode_label_bits`` round-trip against it.
ASCII_RADIX = "2-1-1"

#: A SAMRAS lcl address — a node in the sandbox's OWN local domain.
#:
#: Writable from 2026-08-28, and it is the one non-ASCII radix that can be, because there
#: is nothing to encode: the stored magnitude IS the address (`registrar/legal_entity`
#: holds `rf.3-1-13, 1-1-1` verbatim). Every other radix here is a representation of
#: something — a chronology token, a coordinate run — and writing one means computing it.
#:
#: It is a CHOICE, never free text. The reader offers the sandbox's own lcl nodes as
#: options and the writer refuses an address the local domain does not define, because a
#: typo would otherwise file an instance under a node nobody named — and a node nobody
#: named renders as nothing, which reads as "not set".
LCL_RADIX = "2-0-5"

#: The address family the anchor declares field babelettes in.
FIELD_BABELETTE_PREFIX = "3-1-"

#: What each non-ASCII radix means, so a refusal can say what the value IS rather than only
#: that it is not editable. Unknown radices are refused too, by their address.
RADIX_MEANING: dict[str, str] = {
    "2-0-1": "a HOPS coordinate run",
    "2-0-2": "a SAMRAS address",
    "2-0-3": "a SAMRAS ruiqi address",
    "2-0-4": "a HOPS chronology token, readable only against this sandbox's own anchor",
    "2-0-5": "a SAMRAS lcl address",
    "2-0-6": "a SAMRAS taxon address",
    "2-1-2": "an identification babelette",
}


class NotWritable(ValueError):
    """Raised when a slot cannot be written, carrying the reason an operator should read."""


def backing_radices(anchor: Any) -> dict[str, str]:
    """``field address -> backing radix``, read from a sandbox's own anchor.

    The anchor row for a field address carries its radix as the first magnitude:
    ``["3-1-3", "2-1-1", "0"]`` with the tail ``["title-babelette"]``. Read per SANDBOX and
    never from a constant, because a namespace is a claim about an anchor's numbering and
    two sandboxes do not have to agree — ``common_name`` and ``view`` have no registrar row
    at all and are declared in the taxonomy and farm anchors instead.
    """
    out: dict[str, str] = {}
    for row in getattr(anchor, "rows", ()) or ():
        address = str(getattr(row, "datum_address", "") or "")
        if not address.startswith(FIELD_BABELETTE_PREFIX):
            continue
        raw = getattr(row, "raw", None)
        head = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else []
        if len(head) >= 2:
            out[address] = str(head[1])
    return out


def refusal_for(*, primitive: str, address: str, radices: dict[str, str]) -> str:
    """Why this slot cannot be written, or "" when it can be.

    Ordered so the operator reads the most specific true thing: a chip is refused as a chip
    even if its radix is also unwritable.
    """
    from micyte.core.datum_ops.viewscope import EDITABLE_PRIMITIVES, NOT_EDITABLE_BECAUSE

    if primitive not in EDITABLE_PRIMITIVES:
        return NOT_EDITABLE_BECAUSE.get(
            primitive, f"{primitive} slots are not editable"
        )
    if not address:
        return "this field has no address in this sandbox's anchor"
    radix = radices.get(address, "")
    if not radix:
        return f"this sandbox's anchor declares no babelette at {address}"
    if radix in (ASCII_RADIX, LCL_RADIX):
        return ""
    meaning = RADIX_MEANING.get(radix, f"backed by radix {radix}")
    return f"this value is {meaning} — it is not free text"


def encode_value(value: str, *, radix: str) -> str:
    """The magnitude to store for ``value``, for a radix this module can write.

    Raises :class:`NotWritable` rather than falling back, because a fallback here writes a
    human-readable word where every reader expects bits and decodes it to nothing.
    """
    if radix == LCL_RADIX:
        # Stored VERBATIM. An address is already its own representation, and encoding it
        # would put label bits where every reader expects a node. Whether the address is
        # one this sandbox DEFINES is a separate question, asked by the caller against
        # the local domain — this function knows radices, not vocabularies.
        return value
    if radix != ASCII_RADIX:
        meaning = RADIX_MEANING.get(radix, f"radix {radix}")
        raise NotWritable(f"cannot encode {meaning}")
    return encode_label_bits(value)


def decode_value(magnitude: str, *, radix: str) -> str:
    """The human value behind a stored magnitude, for a radix this module can read.

    An lcl address decodes to ITSELF — it is the address, and turning it into the node's
    label here would hand the writer back a label it cannot store.
    """
    if radix != ASCII_RADIX:
        return str(magnitude or "")
    return decode_label(str(magnitude or ""))


__all__ = [
    "ASCII_RADIX",
    "LCL_RADIX",
    "RADIX_MEANING",
    "NotWritable",
    "backing_radices",
    "decode_value",
    "encode_value",
    "refusal_for",
]
