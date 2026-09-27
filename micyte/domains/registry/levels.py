"""What each segment of an msn address means.

A SAMRAS address IS its path, and the path is the same everywhere in the registrar:

    3            nwh                      hemisphere
    3-2          united_states_of_america country
    3-2-3        state                    the CLASS of subdivision
    3-2-3-17     ohio                     STATE
    3-2-3-17-77  summit_county            COUNTY
    …-77-1       summit_county_cities     the CLASS of municipality
    …-1-6        hudson_city              MUNICIPALITY
    …-6-34       <street>                 STREET
    …-34-1       <number>_<street>        HOUSE
    …-1-3        <a_business>             OCCUPANT

The SHAPE was read off three live entities; their addresses are not reproduced,
:mod:`micyte.domains.registry.minting`'s docstring, which needs the same fact to refuse a
business minted where a street belongs. It was written down there in prose and nowhere as
data, so every surface that wanted "which city is this job in?" had to re-derive it by
counting hyphens — and a surface that counted wrong would be indistinguishable from a
surface reading a different corpus.

**These are POSITIONS, not types.** Nothing in an address space says a node is a city; the
space has no types at all. What this module encodes is where the registrar's own convention
puts one, which is exactly the claim :func:`mint_child`'s caller has to make and cannot
check. A node at :data:`MUNICIPALITY` is a municipality because that is where the corpus
keeps municipalities, and an address that does not reach that depth simply has no city —
answered as "" rather than as the nearest thing, because the nearest thing to a city one
level up is a county and returning it silently would put jobs in the wrong place on a map.
"""

from __future__ import annotations

from micyte.core.datum_ops.datum_resolve import as_text

#: The prefix every US street address shares — hemisphere / country / subdivision class.
#: The operator's own shorthand for the address space a job is booked in: "the recorded
#: version would assume the use prefix of the msn_id to be 3-2-3-<...>".
STATE_CLASS = "3-2-3"

#: Depth, counted the way :class:`~micyte.tools._address_space.AddressSpace` counts it:
#: zero at the roots, so a depth of *n* is an address of *n + 1* segments.
HEMISPHERE = 0
COUNTRY = 1
SUBDIVISION_CLASS = 2
STATE = 3
COUNTY = 4
MUNICIPAL_CLASS = 5
MUNICIPALITY = 6
STREET = 7
HOUSE = 8
OCCUPANT = 9

#: The levels a surface names to a person, in the order a person says them. The
#: `municipal class` layer — cities / townships / villages — is deliberately absent: it is
#: a filing decision of the registrar's, not part of anybody's address, and a picker that
#: made an operator choose "townships" before "Richfield" would be asking them to know how
#: the corpus is stored.
NAMED_LEVELS: tuple[tuple[str, int], ...] = (
    ("state", STATE),
    ("county", COUNTY),
    ("municipality", MUNICIPALITY),
    ("street", STREET),
    ("house", HOUSE),
    ("occupant", OCCUPANT),
)


def depth_of(address: str) -> int:
    """How deep ``address`` sits — ``-1`` for the empty address (the top)."""
    token = as_text(address)
    return len(token.split("-")) - 1 if token else -1


def ancestor(address: str, level: int) -> str:
    """The prefix of ``address`` at ``level``, or ``""`` when it does not reach it.

    Empty rather than the whole address: a house node asked for its municipality answers
    with a municipality or with nothing. Answering with itself would put a street address
    in a city filter, where it would be the only value that matched exactly one row.
    """
    token = as_text(address)
    if not token or level < 0:
        return ""
    parts = token.split("-")
    if len(parts) < level + 1:
        return ""
    return "-".join(parts[: level + 1])


def is_under(address: str, root: str) -> bool:
    """Is ``address`` ``root`` itself or somewhere beneath it?"""
    a, r = as_text(address), as_text(root)
    if not r:
        return bool(a)
    return a == r or a.startswith(r + "-")


__all__ = [
    "COUNTRY", "COUNTY", "HEMISPHERE", "HOUSE", "MUNICIPALITY", "MUNICIPAL_CLASS",
    "NAMED_LEVELS", "OCCUPANT", "STATE", "STATE_CLASS", "STREET", "SUBDIVISION_CLASS",
    "ancestor", "depth_of", "is_under",
]
