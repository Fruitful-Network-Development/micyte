"""Where a row IS, derived from the one address it actually holds.

The operator, 2026-08-18: *"when viewing customer tables or job tables things like the
msn_id are the only true datum values held, but from that value a table can derive an
entry's displayed city or county; therefore filtering functions would merely operate on
msn_id's but visually it would use the titles given to these parent nodes."*

That is two rules and this module is both of them.

**The filter's value is the msn prefix.** `3-2-3-17-77-1-6` is Hudson whatever anybody
renames it to, and a facet keyed on the LABEL would silently stop matching the day a title
was corrected. It would also merge two towns that happen to share a name across counties —
`main_street` is ambiguous across two of them in this very corpus.

**What is drawn is the title the registrar holds**, made readable and nothing more.
`hudson_city` becomes *Hudson City*, not *Hudson*: the second is a nicer word and a
different claim, and a surface that quietly improves the corpus's own names is a surface
whose filters an operator cannot reconcile against the browser.

A row whose msn does not reach a level has no value at that level — "" — and
:func:`micyte.tools._record_view.narrow` never offers a blank as a facet option, so an
address with no city is left out of the city filter rather than gathered under an empty one.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.domains.registry import levels as lv

#: Words a title case would otherwise mangle. Bounded on purpose: this is a readability
#: pass over the registrar's own tokens, not a style guide for them.
_UPPER = {"llc", "inc", "ltd", "llp", "pc", "co", "us", "usa", "ne", "nw", "se", "sw"}


def humanise(token: str) -> str:
    """A registrar token as the words it is made of. ``<number>_<street>_<type>`` -> ``<Number> <Street> <Type>``.

    Returned unchanged when there is nothing to change, so a value that is already a
    sentence — or an address the index could not name, which comes back as itself — is not
    put through a transformation that would make it look like a name.
    """
    text = as_text(token).strip()
    if not text or " " in text:
        return text
    words = [w for w in text.replace("-", " ").replace("_", " ").split(" ") if w]
    if not words:
        return text
    out: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in _UPPER:
            out.append(lowered.upper())
        elif word[0].isdigit():
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def label_at(names: Any, address: str, level: int) -> tuple[str, str]:
    """``(msn prefix, readable title)`` for ``address``'s ancestor at ``level``.

    Both or neither: an address that does not reach the level has no prefix to filter on
    and no title to show, and returning one without the other would put a labelled option
    in a dropdown that can never match a row.
    """
    prefix = lv.ancestor(address, level)
    if not prefix:
        return "", ""
    return prefix, humanise(names.label(prefix, key_field="msn_id"))


def place_of(names: Any, address: str) -> dict[str, str]:
    """Every place key and title a row's msn can answer for.

    One call per row rather than one per column: `names.label` is a dict lookup, but the
    two levels are read off the SAME address and computing them apart is how a table ends
    up filtering on a county the city it displays does not sit in.
    """
    county_msn, county = label_at(names, address, lv.COUNTY)
    city_msn, city = label_at(names, address, lv.MUNICIPALITY)
    house_msn, house = label_at(names, address, lv.HOUSE)
    return {
        "county_msn": county_msn, "county": county,
        "city_msn": city_msn, "city": city,
        "house_msn": house_msn, "house": house,
    }


def postal(names: Any, address: str) -> str:
    """The address as a person writes it: ``1511 Carriage Hill Drive, Hudson City``.

    The house alone was what the jobs and contacts tables drew, and forty-three rows of
    street addresses with no town in any of them is a list nobody can sort by where the
    work is. The city is DERIVED from the same msn the house came from, so the two halves
    of the cell cannot disagree.
    """
    where = place_of(names, address)
    house = where["house"] or humanise(names.label(as_text(address), key_field="msn_id"))
    city = where["city"]
    if house and city and house != city:
        return f"{house}, {city}"
    return house or city


__all__ = ["humanise", "label_at", "place_of", "postal"]
