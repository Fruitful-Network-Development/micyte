"""The fiat abstraction — a cent defined as a mass of gold, and the price reference it backs.

A price is not text. It is what every other value in this system already is: a reference to
a datum, carrying a magnitude. The datum being referenced is what says the magnitude means
*cents*, and this module is the chain that defines one.

::

    0-0-8  mass-incramental-unit  (rudi)         the increment
    0-0-9  gold                   (rudi)         the substance
      |
      +-- L1     [1-1-N, 0-0-8, 4600]            4600 increments of mass.
      |                                          No substance yet, no money yet.
      +-- L2vg2  [2-2-N, 1-1-N, 1, 0-0-9, 1]     one of those masses, OF GOLD.
      |                                          This is the cent.
      +-- L3vg1  [3-1-N, 2-2-N, 0]               the type, not a value.
                                                 What a price row points at.

    a price row: [..., "rf.3-1-N", "450", ...]   = $4.50

**The value group is the tuple count.** One reference/magnitude pair is value group 1; two
pairs is value group 2. The system anthology already holds it that way (``1-2-1``
``USD-cent-babel`` carries two pairs in vg 2), which is why "layer 2, value group 2" and
"two references" are one statement rather than two constraints that happen to agree.

**Why gold and not a currency.** The predecessor this supersedes, ``USD-cent-babel``, stored
a market peg: ``0-0-8 x 93177261268202440000000`` of gold per cent, an 18-decimal fixed
point worth roughly $3,340/oz on the day it was written. A market rate written into a datum
is right once and wrong every day after, and nothing in the row says which day it was. The
magnitude here is a **declaration** — a cent *is* this much gold — so it is wrong only when
somebody changes it on purpose.

**Why the address is discovered and never hardcoded.** :data:`PREFERRED_FIAT_FIELD` is the
address to *provision* into a fresh anchor; it is not the address to *read* from an existing
one. Anchors are numbered per sandbox (the same ``rf.3-1-1`` is a node id in one and a HOPS
coordinate in another), a still can arrive from a network that numbered its own differently,
and the same constant that reads a row is the one that writes it — so a hardcoded address
delivers a blind read and a bad write together. :func:`find_fiat_chain` therefore identifies
the babelette by **what it is made of**, and a sandbox with no chain gets a refusal rather
than a default.

Pure: stdlib only, no I/O, no store, no ``state_machine``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "FIAT_BABELETTE_LABEL",
    "FIAT_UNIT_LABEL",
    "GOLD",
    "GOLD_MASS_INCREMENTS",
    "MASS_UNIT_LABEL",
    "MIU",
    "PREFERRED_FIAT_FIELD",
    "FiatChain",
    "FiatChainError",
    "FiatPrecisionError",
    "abstraction_closure",
    "chain_rows_for_anchor",
    "fiat_marker",
    "find_fiat_chain",
    "format_cents",
    "parse_cents",
    "referenced_addresses",
]

#: The mass-incremental-unit rudi. The increment a mass is counted in.
MIU = "0-0-8"

#: The gold rudi. Live anchors label this ``fiat-currency-unit``, which states the
#: relationship backwards — fiat is not a primitive, it is the abstraction two layers up
#: that this module builds. Relabelling it is a live datum write and is proposed
#: separately; the address is what this module matches on, and the address is not in doubt.
GOLD = "0-0-9"

#: How many mass increments make the gold behind one cent. A declaration, not a quote.
#:
#: ``miu`` is the **nanogram** — the system anthology says so directly (``1-1-8``
#: ``nanogram-babel`` = ``0-0-8 x 1``, with ``2-1-9 miu-babel-gram`` = ``1-1-8 x 1e9``
#: confirming it). So a cent is **4600 ng = 4.6 micrograms of gold**, declared, and it stays
#: that whatever gold does. The superseded ``USD-cent-babel`` implied ~93 µg because it was
#: quoting a market rate; this does not, which is the point.
GOLD_MASS_INCREMENTS = 4600

#: Where to PROVISION the price babelette in an anchor that has none. Verified free —
#: neither defined as a row nor referenced as an ``rf.`` marker — in every live namespace,
#: which is what makes one uniform address safe here where the rest of the 3-1 numbering
#: could not be made uniform. Reading uses :func:`find_fiat_chain`, never this.
PREFERRED_FIAT_FIELD = "3-1-21"

MASS_UNIT_LABEL = f"miu-babel-{GOLD_MASS_INCREMENTS}"
FIAT_UNIT_LABEL = "fiat-baciloid-gold-cent"
#: Carries both "fiat" and "babelette" so the recognition layer binds the currency lens to
#: it, and cannot collide with the ``fiat-currency-unit`` rudi label, which has no
#: "babelette" in it.
FIAT_BABELETTE_LABEL = "fiat-babelette"

_ADDRESS_RE = re.compile(r"^([0-9]+)-([0-9]+)-([0-9]+)$")
#: A stored cent magnitude, with no redundant leading zero. The exclusion is deliberate:
#: a leading zero is meaningless in an integer and *significant* in the bit strings that
#: fill neighbouring magnitudes, so accepting one lets a 512-bit title babelette render as
#: a plausible price ("0101010101" would read as $1,010,101.01). Refusing is what keeps a
#: mis-bound lens visibly wrong instead of quietly convincing.
_CENTS_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")


class FiatChainError(ValueError):
    """A price could not be represented, or an anchor could not carry the chain."""


class FiatPrecisionError(FiatChainError):
    """The amount carried more precision than whole cents can hold.

    A subclass rather than a message, because callers translate this refusal into their own
    vocabulary and the two cases deserve different words: a job's pay of ``"three hundred"``
    is not an amount at all, while ``"2.675"`` IS one and is simply finer than the store can
    represent. `job_manager.to_cents` tells them apart on the TYPE — sniffing the message
    text for "whole cents" would make the wording of an error message load-bearing.
    """


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _strip_marker(value: object) -> str:
    """``rf.3-1-21`` / ``ref.3-1-21`` -> ``3-1-21``; anything else unchanged."""
    token = _text(value)
    lowered = token.lower()
    if lowered.startswith("rf.") or lowered.startswith("ref."):
        return token.split(".", 1)[1].strip()
    return token


def fiat_marker(address: object) -> str:
    """The ``rf.`` marker naming a price babelette at ``address``."""
    return "rf." + _strip_marker(address)


def _parse_address(value: object) -> tuple[int, int, int] | None:
    match = _ADDRESS_RE.fullmatch(_text(value))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _rows_of(doc: Any) -> tuple[Any, ...]:
    if doc is None:
        return ()
    rows = getattr(doc, "rows", None)
    if rows is None:
        rows = doc if isinstance(doc, (list, tuple)) else ()
    return tuple(rows)


def _head_of(row: Any) -> list[Any]:
    raw = getattr(row, "raw", row)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _label_of(row: Any) -> str:
    raw = getattr(row, "raw", row)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return _text(raw[1][0])
    return ""


def _address_of(row: Any) -> str:
    addr = getattr(row, "datum_address", None)
    if addr is not None:
        return _text(addr)
    head = _head_of(row)
    return _text(head[0]) if head else ""


def _pairs(row: Any) -> list[tuple[str, str]]:
    """The ``(reference, magnitude)`` tuples of a row's head, in head order."""
    head = _head_of(row)
    return [
        (_strip_marker(head[i]), _text(head[i + 1]))
        for i in range(1, len(head) - 1, 2)
    ]


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FiatChain:
    """The three addresses a sandbox's anchor holds the fiat abstraction at.

    Addresses, not magnitudes: the magnitudes are fixed by this module, and what varies per
    sandbox is only *where* the rows were allocated.
    """

    mass_address: str
    unit_address: str
    babelette_address: str

    def __post_init__(self) -> None:
        for name in ("mass_address", "unit_address", "babelette_address"):
            if not _parse_address(getattr(self, name)):
                raise FiatChainError(f"{name} must be a datum address, got {getattr(self, name)!r}")

    @property
    def marker(self) -> str:
        """The ``rf.`` marker a price row references."""
        return fiat_marker(self.babelette_address)

    @property
    def addresses(self) -> tuple[str, ...]:
        return (self.mass_address, self.unit_address, self.babelette_address)


def find_fiat_chain(anchor_doc: Any) -> FiatChain | None:
    """The fiat chain an anchor holds, identified STRUCTURALLY, or ``None``.

    Matched on what the rows are made of, never on where they sit or what they are called:

    * a layer-1 row over :data:`MIU` with magnitude :data:`GOLD_MASS_INCREMENTS`;
    * a layer-2 value-group-2 row whose two pairs are that row at magnitude 1 and
      :data:`GOLD` at magnitude 1;
    * a layer-3 value-group-1 row pointing at it with magnitude 0.

    So a sandbox that allocated the chain at different iterations, and a still that arrived
    from a network that numbered its own anchor differently, both read correctly. If several
    chains somehow exist, the one with the lowest babelette address wins — deterministically,
    so two readers of one document never disagree.
    """
    rows = _rows_of(anchor_doc)
    if not rows:
        return None

    mass: set[str] = set()
    for row in rows:
        parsed = _parse_address(_address_of(row))
        if not parsed or parsed[0] != 1:
            continue
        pairs = _pairs(row)
        if len(pairs) == 1 and pairs[0][0] == MIU and pairs[0][1] == str(GOLD_MASS_INCREMENTS):
            mass.add(_address_of(row))
    if not mass:
        return None

    units: dict[str, str] = {}
    for row in rows:
        parsed = _parse_address(_address_of(row))
        if not parsed or parsed[0] != 2 or parsed[1] != 2:
            continue
        pairs = _pairs(row)
        if len(pairs) != 2:
            continue
        (mass_ref, mass_mag), (gold_ref, gold_mag) = pairs
        if mass_ref in mass and mass_mag == "1" and gold_ref == GOLD and gold_mag == "1":
            units[_address_of(row)] = mass_ref
    if not units:
        return None

    found: list[FiatChain] = []
    for row in rows:
        parsed = _parse_address(_address_of(row))
        if not parsed or parsed[0] != 3 or parsed[1] != 1:
            continue
        pairs = _pairs(row)
        if len(pairs) == 1 and pairs[0][0] in units and pairs[0][1] == "0":
            found.append(FiatChain(
                mass_address=units[pairs[0][0]],
                unit_address=pairs[0][0],
                babelette_address=_address_of(row),
            ))
    if not found:
        return None
    return sorted(found, key=lambda c: _parse_address(c.babelette_address) or (0, 0, 0))[0]


def _next_iteration(rows: tuple[Any, ...], layer: int, value_group: int) -> int:
    used = [
        parsed[2]
        for parsed in (_parse_address(_address_of(r)) for r in rows)
        if parsed and parsed[0] == layer and parsed[1] == value_group
    ]
    return (max(used) + 1) if used else 1


def chain_rows_for_anchor(
    anchor_doc: Any, *, babelette_address: str = PREFERRED_FIAT_FIELD
) -> tuple[list[list[Any]], FiatChain]:
    """The rows to ADD so ``anchor_doc`` carries the chain, and where they land.

    Idempotent: an anchor that already holds a chain yields no rows and its existing
    addresses, so provisioning twice is provisioning once.

    Layer-1 and layer-2 iterations are allocated after whatever the anchor already holds.
    The babelette address is requested rather than allocated, because it becomes an ``rf.``
    marker that record documents carry — a marker that moved between provisionings would
    mismap every price written before the move.

    Raises :class:`FiatChainError` if that address is already taken. Refusing is the whole
    point: the same ``3-1-N`` means a different field in every namespace, so quietly picking
    the next free one would write prices against whatever that address means here.
    """
    existing = find_fiat_chain(anchor_doc)
    if existing is not None:
        return [], existing

    rows = _rows_of(anchor_doc)
    target = _strip_marker(babelette_address)
    parsed = _parse_address(target)
    if not parsed or parsed[0] != 3 or parsed[1] != 1:
        raise FiatChainError(
            f"the price babelette must be a layer-3 value-group-1 address, got {target!r}")

    taken = {_address_of(r) for r in rows}
    if target in taken:
        raise FiatChainError(
            f"{target} is already defined in this anchor; the price babelette needs an "
            f"address the sandbox does not already mean something else by")
    referenced = {ref for r in rows for ref, _ in _pairs(r)}
    if target in referenced:
        raise FiatChainError(
            f"{target} is already referenced in this anchor; provisioning the price "
            f"babelette there would redefine a field already in use")

    mass_address = f"1-1-{_next_iteration(rows, 1, 1)}"
    unit_address = f"2-2-{_next_iteration(rows, 2, 2)}"
    chain = FiatChain(
        mass_address=mass_address, unit_address=unit_address, babelette_address=target)
    new_rows = [
        [[mass_address, MIU, str(GOLD_MASS_INCREMENTS)], [MASS_UNIT_LABEL]],
        [[unit_address, mass_address, "1", GOLD, "1"], [FIAT_UNIT_LABEL]],
        [[target, unit_address, "0"], [FIAT_BABELETTE_LABEL]],
    ]
    return new_rows, chain


def referenced_addresses(doc: Any) -> set[str]:
    """Every datum address a document's rows reference, markers stripped.

    ``rf.3-1-21`` and ``3-1-21`` are the same target written two ways; a caller asking what
    a document depends on wants one answer.
    """
    out: set[str] = set()
    for row in _rows_of(doc):
        for ref, _ in _pairs(row):
            if _parse_address(ref):
                out.add(ref)
    return out


def abstraction_closure(anchor_doc: Any, addresses: object) -> list[Any]:
    """The anchor rows that DEFINE ``addresses``, plus the rudi prefix they stand on.

    What makes a published still stand alone. A catalog whose prices are magnitudes against
    ``rf.3-1-21`` is unreadable without the rows that say what ``3-1-21`` is, and shipping
    the farm's whole anchor to say so would carry its lcl-SAMRAS bitstream along with it.

    Walks the reference edges from each requested address down to the rudis, keeps exactly
    what it reaches, and — per the MOS canonical-value rule — keeps the **whole** rudi
    prefix ``0-0-1..0-0-K`` rather than only the rudis actually reached, because the
    canonical value is anchored to the universal rudi starting position. Returns the
    anchor's own row objects, in document order.

    Not fiat-specific despite living here: it is the *minimum-but-complete abstraction
    path* the canonical-datum wiki specifies and nothing else implemented. Its natural
    long-term home is beside ``core/mss/datum_identity.derive_hyphae_chain``, which
    computes the fully-inclusive variant.
    """
    rows = _rows_of(anchor_doc)
    by_address = {_address_of(r): r for r in rows}
    wanted = {_strip_marker(a) for a in (addresses or ()) if _strip_marker(a)}

    keep: set[str] = set()
    frontier = [a for a in wanted if a in by_address]
    while frontier:
        addr = frontier.pop()
        if addr in keep:
            continue
        keep.add(addr)
        for ref, _ in _pairs(by_address[addr]):
            if ref in by_address and ref not in keep:
                frontier.append(ref)

    max_rudi = 0
    for addr in list(keep):
        parsed = _parse_address(addr)
        if parsed and parsed[0] == 0 and parsed[1] == 0:
            max_rudi = max(max_rudi, parsed[2])
    if max_rudi:
        for row in rows:
            parsed = _parse_address(_address_of(row))
            if parsed and parsed[0] == 0 and parsed[1] == 0 and 1 <= parsed[2] <= max_rudi:
                keep.add(_address_of(row))

    return [r for r in rows if _address_of(r) in keep]


# --------------------------------------------------------------------------- #
# The only place money changes representation
# --------------------------------------------------------------------------- #
def parse_cents(value: object) -> int:
    """``"$4.50"`` -> ``450``. Integer cents, never a float.

    Accepts what an operator types — a leading ``$``, thousands separators, whitespace, a
    bare integer, a leading ``-`` — and refuses everything else. Refuses in particular a
    third decimal place: ``"$4.505"`` is not a price this system can store, and rounding it
    would decide, silently and in the farm's favour or against it, which half-cent it meant.
    """
    token = _text(value).replace(",", "").replace("$", "").replace(" ", "")
    if not token:
        raise FiatChainError("a price is required")
    negative = token.startswith("-")
    if negative:
        token = token[1:]
    if not token:
        raise FiatChainError(f"{value!r} is not a price")

    whole, sep, frac = token.partition(".")
    if sep:
        if not frac.isdigit():
            raise FiatChainError(f"{value!r} is not a price")
        if len(frac) > 2:
            raise FiatPrecisionError(
                f"{value!r} is not a price in whole cents; two decimal places at most")
        frac = frac.ljust(2, "0")
    else:
        frac = "00"
    if whole and not whole.isdigit():
        raise FiatChainError(f"{value!r} is not a price")
    cents = int(whole or "0") * 100 + int(frac)
    return -cents if negative else cents


def format_cents(value: object) -> str:
    """``450`` -> ``"$4.50"``. The lens's display form, and the surfaces' too.

    A magnitude that is not whole cents is refused rather than rendered approximately: a
    price cell that shows a number it cannot round-trip is worse than one that shows the
    problem.
    """
    token = _text(value)
    if not token:
        return ""
    if not _CENTS_RE.fullmatch(token):
        raise FiatChainError(f"{value!r} is not a whole-cent magnitude")
    cents = int(token)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"
