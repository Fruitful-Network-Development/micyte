"""Narrowing a record table — search and facets, stated once for every table that has one.

A table with more rows than a screen needs two things: a text search, and a way to say
"only this trade" or "only this month". Both are the same question asked of the rows a tool
has already built, so neither belongs to jobs or to contacts. A tool declares WHICH of its
columns are searchable and which are facets; everything about what a filter *means* is here.

That is deliberate and it is the whole reason this module exists. A search written into
``contacts_manager`` would be copied into ``job_manager`` the same day, and the CSV export
would then be a THIRD narrowing — three implementations of one rule, each free to drift, and
the one that drifts silently is the export, because a spreadsheet full of the wrong rows
looks exactly like a spreadsheet full of the right ones.

## The rules, in the one place they are stated

* **Search reads the DISPLAY cell**, not the stored token. A job's customer cell is resolved
  from the *contacts* document — the row itself holds `3-2-3-17-77-1-6-34-1`. Searching what
  is stored would make a search for a customer's first name miss the row whose customer column says their full name,
  which is the row the operator is looking at while they type.
* **A facet offers only values that survive the OTHER filters.** Options are counted over the
  rows that pass everything except that facet, so picking one can never yield an empty table,
  and the count beside a value is the number of rows that value will actually leave.
* **An unmatched facet value narrows to NOTHING.** Ignoring it would show the whole table
  under a filter the operator believes is applied — and the export button beside it would
  then take the whole table out of the building. It is kept in the select, marked, and
  reported in ``unmatched``.
* **Blank is not a value.** A row whose facet cell is empty is not offered as an option,
  because "" in a dropdown reads as "no filter" and would then mean its opposite.
* **A facet's VALUE and its LABEL are two different things.** The value is what the URL
  carries and what a row is matched on; the label is what the dropdown draws. They are the
  same string for most facets and deliberately not for a place — `3-2-3-17-77-1-6` matches
  Hudson whatever anybody renames it to, and a filter keyed on the name would stop
  matching the day the name was corrected. See ``titles`` on :func:`facet`.
* **Opening one row is the same vocabulary.** :func:`pick` and :func:`back` are the two
  halves of a drill-in — a list, then the one thing it lists, with a way home — and they
  are namespaced by the table's prefix like everything else here, so two tables sharing a
  surface query cannot read each other's selection. They live beside :func:`narrow`
  because the picker offers the NARROWED rows: a search that cuts the table and leaves the
  picker offering everything is a filter that only half applies.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.state_machine.portal_shell.shell_schemas import (
    RECORD_TABLE_FACET_INFIX,
    RECORD_TABLE_OPEN_SUFFIX,
    RECORD_TABLE_SEARCH_SUFFIX,
    RECORD_TABLE_SEED_SUFFIX,
    RECORD_TABLE_VIEW_SUFFIX,
)

#: The query parameter a table's search box posts under, suffixed onto the table's prefix,
#: and the infix for a facet's own parameter. Namespaced by the table's prefix so the ERP's
#: three tabs — every one of them an ``editable_table`` living in ONE surface query —
#: cannot read each other's filters, the reason ``quiar`` keeps its own ``erp_tab`` rather
#: than sharing ``agronomics``'.
#:
#: IMPORTED, not declared. The canonical query has to recognise these two spellings to
#: keep them across a round trip, and it could not import this module — so they live in
#: `shell_schemas`, which both sides already import, and there is one declaration instead
#: of two that agree until they do not.
SEARCH_SUFFIX = RECORD_TABLE_SEARCH_SUFFIX
FACET_INFIX = RECORD_TABLE_FACET_INFIX
VIEW_SUFFIX = RECORD_TABLE_VIEW_SUFFIX
OPEN_SUFFIX = RECORD_TABLE_OPEN_SUFFIX
#: WHICH ROW is seeding a form on this surface — see :func:`seed_param`. Here with the
#: other three because it is the same vocabulary and the canonical query recognises it by
#: the same shape rule; a param the round trip drops is a button that does nothing.
SEED_SUFFIX = RECORD_TABLE_SEED_SUFFIX


def search_param(prefix: str) -> str:
    return f"{as_text(prefix)}{SEARCH_SUFFIX}"


def facet_param(prefix: str, column: str) -> str:
    return f"{as_text(prefix)}{FACET_INFIX}{as_text(column)}"


def view_param(prefix: str) -> str:
    return f"{as_text(prefix)}{VIEW_SUFFIX}"


def open_param(prefix: str) -> str:
    return f"{as_text(prefix)}{OPEN_SUFFIX}"


def opened(prefix: str, query: dict[str, Any] | None) -> str:
    """WHICH ROW of this table the reader has open, or ``""`` for the list itself."""
    return as_text((query or {}).get(open_param(prefix))).strip()


def pick(prefix: str, options: list[dict[str, str]], *,
         label: str = "Open", go_label: str = "Open") -> dict[str, Any] | None:
    """The FORWARD half of a drill-in: choose a row's subject and open it.

    ``None`` when there is nothing to choose between, because the renderer draws the bar
    exactly when the key is there and a select with no options is a control that cannot
    do anything — the same absent-not-empty rule ``editable_table`` follows for filters.

    It exists because a table draws every cell as escaped text, so there is no clickable
    row. Before it, the only way to act on a listed thing was to read its address out of
    a column and type it into a form underneath.

    The options are the caller's NARROWED rows, not everything it holds: searching for a
    street and then finding the picker still offering all 118 names is a filter that only
    half applies.
    """
    if not options:
        return None
    return {"label": label, "param": open_param(prefix), "options": list(options),
            "go_label": go_label}


def back(prefix: str, *, label: str = "Back") -> dict[str, Any]:
    """The way out of a drill-in. Clearing the parameter IS the return.

    One statement of the pair, so the control that sets the parameter and the control
    that clears it cannot come to disagree about its name — which reads, on screen, as a
    ← that does nothing.
    """
    return {"label": label, "param": open_param(prefix), "value": ""}
def seed_param(prefix: str) -> str:
    """The parameter naming the row of this table a form elsewhere is prefilled FROM.

    Narrowing is what the rest of this module is about and this is not narrowing: the
    table's rows are unchanged, and what the parameter selects is which one a *second*
    surface opens against. It lives here anyway because it is one more of this table's own
    query keys, namespaced by the same prefix and recognised by the same shape rule — and
    the failure it would otherwise share is the one this module records: a param the
    canonical query does not name is a control that silently does nothing.
    """
    return f"{as_text(prefix)}{SEED_SUFFIX}"


def views(prefix: str, *, query: dict[str, Any] | None,
          options: tuple[tuple[str, str], ...],
          default: str = "") -> dict[str, Any]:
    """Which FACE of one table is drawn — ``(id, label)`` pairs, and which is active.

    Narrowing and drawing are separate questions, and this is deliberately only the second
    one: every view of a table shows the SAME narrowed rows, so switching to a map can
    never quietly show a different set than the table did. That is the whole reason the
    switch lives beside :func:`narrow` instead of inside it.

    An id the caller does not offer falls back to the default and says so in ``unknown``.
    A facet does the opposite — an unmatched facet narrows to nothing, because ignoring it
    would show the whole table under a filter the operator believes is applied. There is no
    such hazard here: a view id names a renderer, not a subset, so the wrong one has no
    face to draw and the honest answer is the default one, reported.
    """
    offered = [(as_text(i), as_text(label) or as_text(i)) for i, label in options]
    if not offered:
        return {}
    fallback = as_text(default) or offered[0][0]
    asked = as_text((query or {}).get(view_param(prefix))).strip()
    known = {i for i, _label in offered}
    active = asked if asked in known else fallback
    control: dict[str, Any] = {
        "param": view_param(prefix),
        "value": active,
        "options": [{"id": i, "label": label, "active": i == active}
                    for i, label in offered],
    }
    if asked and asked not in known:
        control["unknown"] = asked
    return control


def facet(column: str, *, label: str = "", all_label: str = "",
          titles: dict[str, str] | None = None,
          order: tuple[str, ...] | None = None) -> dict[str, Any]:
    """One faceted column. ``all_label`` is what the unfiltered option says.

    ``titles`` maps a cell's VALUE to what the dropdown draws for it, so a facet can
    operate on something an operator would never read. The city filter is the case that
    forced it: the operator's rule is that *"filtering functions would merely operate on
    msn_id's but visually it would use the titles given to these parent nodes"*, so the
    option's value is `3-2-3-17-77-1-6` and its label is *Hudson City*. Keyed on the value
    rather than replacing the column, because the value is what the URL carries and a
    bookmarked filter has to keep matching after somebody corrects a title.

    ``order`` is an explicit sequence of values, for facets whose natural order is neither
    alphabetical nor by count. Months are why: sorted by count, *June 2026* lands between
    *April* and *May*, and a chronological dropdown that is not in chronological order
    reads as a bug in the dates. Values the order does not name follow it, in the default
    order — so a caller who orders some of them is not silently dropping the rest.
    """
    name = as_text(column)
    spec: dict[str, Any] = {
        "column": name,
        "label": as_text(label) or name.replace("_", " "),
        "all_label": as_text(all_label) or f"All {as_text(label) or name}",
    }
    if titles:
        spec["titles"] = dict(titles)
    if order:
        spec["order"] = list(order)
    return spec


def _cell(row: Any, column: str) -> str:
    return as_text((row or {}).get(column)).strip()


def narrow(
    rows: list[dict[str, Any]],
    *,
    query: dict[str, Any] | None,
    param_prefix: str,
    search_columns: tuple[str, ...] = (),
    facets: tuple[dict[str, str], ...] = (),
    search_placeholder: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """``(narrowed rows, the controls that produced them)``.

    The controls travel in the payload and the renderer draws them; it does not re-decide
    what they mean. A client that filtered its own copy would be the second implementation
    this module exists to prevent, and the download beside it could then disagree with the
    screen it was approved from.
    """
    query = dict(query or {})
    typed = as_text(query.get(search_param(param_prefix))).strip()
    needle = typed.casefold()

    chosen: dict[str, str] = {}
    for spec in facets:
        value = as_text(query.get(facet_param(param_prefix, spec["column"]))).strip()
        if value:
            chosen[spec["column"]] = value

    def passes(row: dict[str, Any], *, skip: str = "") -> bool:
        if needle and not any(needle in _cell(row, c).casefold() for c in search_columns):
            return False
        for column, value in chosen.items():
            if column == skip:
                continue
            if _cell(row, column) != value:
                return False
        return True

    narrowed = [row for row in rows if passes(row)]

    facet_controls: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for spec in facets:
        column = spec["column"]
        # Counted over the rows that pass everything EXCEPT this facet, which is what makes
        # every option a live one and every count the number it is about to leave.
        counts: dict[str, int] = {}
        for row in rows:
            if not passes(row, skip=column):
                continue
            token = _cell(row, column)
            if token:
                counts[token] = counts.get(token, 0) + 1
        titles: dict[str, str] = spec.get("titles") or {}
        wanted: list[str] = list(spec.get("order") or ())
        ranked = [t for t in wanted if t in counts]
        ranked += sorted((t for t in counts if t not in wanted),
                         key=lambda t: (-counts[t], t))

        def drawn(token: str, _titles: dict[str, str] = titles) -> str:
            # `_titles` bound as a default: the closure is built once per facet inside a
            # loop over them, and a late-bound `titles` would give every facet the LAST
            # one's labels — which reads as the city dropdown listing months.
            return _titles.get(token) or token

        options = [
            {"value": token, "label": drawn(token), "count": counts[token]}
            for token in ranked
        ]
        value = chosen.get(column, "")
        if value and value not in counts:
            unmatched.append(f"{spec['label']} = {drawn(value)}")
            options.insert(0, {"value": value, "label": f"{drawn(value)} — no rows",
                               "count": 0})
        facet_controls.append({
            "param": facet_param(param_prefix, column),
            "column": column,
            "label": spec["label"],
            "all_label": spec["all_label"],
            "value": value,
            "options": options,
        })

    params = [search_param(param_prefix)] + [f["param"] for f in facet_controls]
    controls = {
        "param_prefix": as_text(param_prefix),
        "search": {
            "param": search_param(param_prefix),
            "value": typed,
            "placeholder": as_text(search_placeholder) or "Search",
            # Named so the placeholder is not the only statement of what is searched. A box
            # that silently covers four of seven columns is a box that looks broken on the
            # other three.
            "columns": list(search_columns),
        },
        "facets": facet_controls,
        "matched": len(narrowed),
        "total": len(rows),
        "active": bool(needle or chosen),
        "params": params,
        # Said out loud rather than left as an empty table: a filter that matches nothing and
        # a table that holds nothing look identical, and only one of them is the operator's
        # own doing.
        "unmatched": unmatched,
    }
    return narrowed, controls


__all__ = ["FACET_INFIX", "OPEN_SUFFIX", "SEARCH_SUFFIX", "VIEW_SUFFIX", "back", "facet",
           "facet_param", "narrow", "open_param", "opened", "pick", "search_param",
           "view_param", "views"]
__all__ = ["FACET_INFIX", "SEARCH_SUFFIX", "SEED_SUFFIX", "VIEW_SUFFIX", "facet",
           "facet_param", "narrow", "search_param", "seed_param", "view_param", "views"]
