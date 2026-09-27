"""The same rows a table draws, drawn one card each.

A record table is a complete index: every declared column has a cell on every row, and a
blank one is drawn blank because a books view has to account for what it does not hold. A
gallery is the other kind of index — the scannable one. Same rows, same order, same
narrowing; a different amount of each row on screen.

That is the whole distinction, and it is why this is a THIRD face rather than a second
table. The operator, 2026-09-02: *"a subtab of preview cards that TOGGLES to a map view.
Opening a job in either setting shows the SAME job profile view. One view, two indexes."*
Two indexes, one view: the card carries no editor of its own, it opens the record the
table's own row does — see the `data-inv-open` binding in the renderer.

## There is no image slot here, deliberately

If "preview card" is read as a PHOTOGRAPH, nothing in the corpus can fill it. The
``job_event`` archetype is ``msn_id, site_msn, lcl_id, utc+, price?, title?, project_ref?,
status_ref?, lead_ref?`` (``scripts/mint_archetype_sandbox.py``) — no image field, no
attachment field — and ``save_job`` has no path that would write one. A card built with an
empty picture frame on it would claim a field exists and is unset; this one is built from
what a job HAS. Photographs need a field first, and that is a change to the archetype and
to the write route, not to a renderer.

## A blank line is dropped, not drawn empty

A card is a preview. A column of em-dashes is noise on a card in a way it is not in a
table, where the empty cell is how the operator sees the gap. So a line whose cell is
blank is left off, and cards are legitimately different heights. The TABLE face is where
every declared column is accounted for on every row — which is the reason both faces
exist rather than one of them replacing the other.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text


def card_line(column: str, *, label: str = "") -> dict[str, str]:
    """One labelled line on a card: the ROW column it reads, and what it is called.

    The same value/label split :func:`micyte.tools._record_view.facet` states — the column
    is what the row carries and the label is what a person reads, and the jobs table has
    four columns whose names differ from their headings.
    """
    name = as_text(column)
    return {"column": name, "label": as_text(label) or name.replace("_", " ")}


def card_gallery(
    rows: list[dict[str, Any]],
    *,
    title_column: str,
    subtitle_column: str = "",
    badge_column: str = "",
    lines: tuple[dict[str, str], ...] = (),
    untitled_text: str = "",
    empty_text: str = "",
    open_label: str = "Open",
) -> dict[str, Any]:
    """One card per row, in the order the rows are already in.

    ``rows`` are the rows the table is ALREADY showing — narrowed once, upstream, exactly
    as :func:`micyte.tools._row_map.region_map` takes them. Building this from anything
    else is the one failure the ordering makes unreachable: a gallery holding a job the
    table beside it is filtering out.

    ``title_column``/``subtitle_column``/``badge_column`` are the three cells a card leads
    with — who, where, and what it paid, for a job. ``lines`` are the rest, declared with
    :func:`card_line`, and a blank one is dropped.

    ``untitled_text`` is what the heading says when the title cell is empty. Written out
    rather than left blank because a card with no heading reads as a rendering fault, and
    a job whose address has no named occupant yet is a real row, not a broken one.

    A row with no ``datum_address`` gets a card with none, and the renderer draws no open
    affordance for it — a button that opens nothing is worse than an absent one.
    """
    cards: list[dict[str, Any]] = []
    for row in rows:
        row = row or {}
        drawn: list[dict[str, str]] = []
        for spec in lines:
            value = as_text(row.get(spec["column"])).strip()
            if value:
                drawn.append({"label": spec["label"], "value": value})
        cards.append({
            "datum_address": as_text(row.get("datum_address")),
            "title": as_text(row.get(title_column)).strip() or as_text(untitled_text),
            "subtitle": (as_text(row.get(subtitle_column)).strip()
                         if subtitle_column else ""),
            "badge": (as_text(row.get(badge_column)).strip() if badge_column else ""),
            "lines": drawn,
        })
    return {
        "cards": cards,
        "card_count": len(cards),
        # Said here rather than reused from the table's own `empty_text`: "No jobs booked
        # yet — use + Book a job" is the right sentence under an empty TABLE and the wrong
        # one under a gallery the operator reached by filtering to a county with no work
        # in it.
        "empty_text": as_text(empty_text) or "Nothing to show here.",
        "open_label": as_text(open_label) or "Open",
    }


__all__ = ["card_gallery", "card_line"]
