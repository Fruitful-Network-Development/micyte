"""Where the next row of a document goes — by ARITY, which is what an address says.

A datum address is ``<layer>-<value group>-<iteration>`` and the value group IS the tuple
count: ``document_codec`` states it outright ("the VG number = tuple count"), and a row
that gains a third (reference, magnitude) pair MOVES from ``4-2-N`` to ``4-3-N``. It is not
a convention a writer chooses. Until 2026-09-11 four write runtimes minted the next address
by the document's DOMINANT family instead — the family with the most rows, iteration one
past the highest — so a job row carrying six pairs was filed at ``4-1-N`` beside a blank
carrying none, and BPW's job log holds 44 such rows (TASK-2026-08-31-002, audit of
2026-09-01). Every reader that folds by shape still read them, which is why nobody saw it;
the codec would have said the address and the row disagree.

ONE minter, here, so the four cannot drift again. The iteration is per family, the way
``fiat_datum._next_iteration`` and the lcl builder already count — ``4-2-*`` and ``4-3-*``
coexist in one document each numbered from 1, and ``reindex_into_isolated_anthology``
preserves the value group verbatim.

The head is ``[address, marker, magnitude, marker, magnitude, …]``: the cell after the
address opens the first pair. A head with NO pairs is the structural blank ``[["4-1-1"]]``
every document is created with, and it keeps its family: value group 0 is "refs-only",
which the blank is not, and re-homing it would move the one row every sandbox's tooling
knows by address.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

_ADDRESS_RE = re.compile(r"^(\d+)-(\d+)-(\d+)$")

#: The layer a datum row lives at.
ROW_LAYER = 4


def value_group_of(head: Sequence[Any]) -> int:
    """The tuple count of a row head: the (marker, magnitude) pairs after the address."""
    cells = max(0, len(head) - 1)
    return cells // 2


def family_of(head: Sequence[Any], *, layer: int = ROW_LAYER) -> str:
    """``"<layer>-<value group>"`` for ``head`` — ``4-1`` for a head with no pairs (the
    structural blank), ``4-<n>`` for one carrying ``n``."""
    return f"{layer}-{max(1, value_group_of(head))}"


def highest_iteration(addresses: Iterable[Any], family: str) -> int:
    """The highest iteration any address in ``family`` reaches, ``0`` when none does."""
    highest = 0
    prefix = f"{family}-"
    for address in addresses:
        text = str(address or "")
        if text.startswith(prefix) and _ADDRESS_RE.fullmatch(text):
            highest = max(highest, int(text.rsplit("-", 1)[1]))
    return highest


def next_row_address(addresses: Iterable[Any], *, head: Sequence[Any],
                     layer: int = ROW_LAYER) -> str:
    """The address a row with ``head`` takes among ``addresses``: its own family, one past
    the highest iteration that family already reaches."""
    family = family_of(head, layer=layer)
    return f"{family}-{highest_iteration(addresses, family) + 1}"


def readdressed(rows: Iterable[tuple[str, Sequence[Any]]], *,
                layer: int = ROW_LAYER) -> dict[str, str]:
    """``{old address: new address}`` for every row whose family disagrees with its head.

    Rows already in the right family KEEP their address, and new addresses are minted
    one past what the family already holds — so a document with ``4-1-1`` (the blank) and
    six-pair rows at ``4-1-2..45`` yields ``4-1-2 -> 4-6-1`` and so on, and the blank stays.
    The mapping is empty for a document that already obeys the rule, which is how a
    re-address verb knows it has nothing to do.
    """
    listed = [(str(address), list(head)) for address, head in rows]
    taken = [address for address, _head in listed]
    moves: dict[str, str] = {}
    counters: dict[str, int] = {}
    for address, head in listed:
        family = family_of(head, layer=layer)
        if address.startswith(f"{family}-"):
            continue
        if family not in counters:
            counters[family] = highest_iteration(taken, family)
        counters[family] += 1
        moves[address] = f"{family}-{counters[family]}"
    return moves


__all__ = [
    "ROW_LAYER",
    "family_of",
    "highest_iteration",
    "next_row_address",
    "readdressed",
    "value_group_of",
]
