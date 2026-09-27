"""The ``editable_table`` container — a record table with an inline create/edit row.

One container, one renderer, many record types (the modern ledgers, jobs, projects), and
the field set travels in the PAYLOAD rather than living in the renderer. It used to be
the other way round: ``renderInventoryTable`` hardcoded one record type's inputs, its
save route and its sandbox, so the second writable record table would have been a second
near-identical renderer — and the first thing a copy does is stop matching its original.

The contract:

* ``columns`` are the display columns. **Column 0 is the record's server-assigned
  identity** (the batch node, the sale lot) — the operator never types it, and the edit row
  shows ``(new)`` / ``(edit)`` there instead of an input. Pass ``identity_column=False``
  for a table whose first column is data: the row's address is still carried and still
  edited against, it is simply not drawn, and the ``(new)``/``(edit)`` marker moves into
  the actions cell.
* ``fields`` supply the remaining columns, in order, one per column. A field names the
  request key it posts under, so the form and the write route cannot disagree about what a
  value is called.
* ``computed_columns`` are shown after those and are never typed — a figure the server
  derived, like an offer's on-hand. They are outside ``columns`` precisely so the
  one-field-per-column check keeps meaning what it says, and so a derived number cannot be
  given an input box the write route would ignore.
* ``save_route`` is where the row POSTs, and ``sandbox_id`` is the farm it names. A payload
  with no sandbox does not fall back to one: it disables saving and says why. A default
  farm here is not a default, it is a guess about whose books to write in.
* ``row_actions`` are the per-row buttons. The renderer used to know two of them by name —
  the supply batch's *Retire* toggle and its *Plan into plots* jump — so a third record
  type's action would have been a third branch inside a renderer that is supposed to be
  record-type-agnostic. They are declarations now: :func:`toggle_action`,
  :func:`nav_action`, :func:`post_action`, :func:`param_action`.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops import local_domain as _ld

from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

#: Every family an lcl definition row lives in — see
#: :mod:`micyte.core.datum_ops.local_domain`.
_LCL_FAMILIES = _ld.DEFINITION_PREFIXES

#: Field kinds the renderer knows. Anything else is refused at build time rather than
#: rendered as a bare text box that quietly loses the caller's intent.
#:
#: ``datetime`` is a day AND A TIME OF DAY, drawn as ``<input type="datetime-local">`` and
#: posted as ``YYYY-MM-DDTHH:MM``. It exists because a 2pm appointment could not be said at
#: all: ``date`` draws a bare day, and the only writer of a ``utc`` cell encoded it at
#: midnight, always (:func:`micyte.tools._hops_dates.day_to_hops_token`). The STORAGE never
#: needed changing — the token carries a full moment and the decoders already kept the hour
#: — so this is the write side catching up with what the cell could always hold.
KINDS = ("text", "select", "date", "datetime", "address")

#: The kinds that carry a MOMENT. The renderer blanks these when it seeds an edit row and
#: when it re-posts a row for an action, because a write route reads an omitted stamp as
#: "keep the one on file" and retiring a batch must not re-stamp it to today. Named once
#: here so the renderer's two copies of that rule cannot learn about one new stamp kind and
#: not the other — which is exactly what adding ``datetime`` beside ``date`` would
#: otherwise have cost.
STAMP_KINDS = ("date", "datetime")

#: What an ``address`` field posts, suffixed onto its own name. Three request keys for one
#: column, because a street address is one thing a person says and three the registrar
#: stores. Declared here so the renderer, the write route and the row builder cannot
#: disagree about what the parts are called.
ADDRESS_PARTS: tuple[str, ...] = ("state", "city", "address")


def field(
    name: str,
    *,
    kind: str = "text",
    label: str = "",
    placeholder: str = "",
    options_key: str = "",
    datalist_key: str = "",
    required_text: str = "",
    edit_hint: str = "",
    state_options_key: str = "",
    city_options_key: str = "",
) -> dict[str, Any]:
    """One editable column.

    ``options_key`` / ``datalist_key`` name a sibling key of the payload holding
    ``[{value, label}]`` — carried by reference so a long option list (a farm's ~2,900
    products) is serialized once even when several fields draw on it.

    ``required_text`` is the message shown when the field is empty on save; supplying it is
    what makes a field required, so there is no way to mark one required without saying what
    the operator should do about it.

    An ``address`` field is one COLUMN and three controls: a state, a city that follows it,
    and the street address typed out. It posts ``<name>_state``, ``<name>_city`` and
    ``<name>_address`` — :data:`ADDRESS_PARTS` — and ``keys`` carries that list so the
    renderer's save collector never has to know which kinds are composite. Its options come
    from ``state_options_key`` and ``city_options_key``; each city option carries a
    ``parent`` naming the state it belongs to, which is what makes the second select follow
    the first without a round trip.

    The kind exists because the alternative was a picker over the whole address space. The
    live one offered 400 nodes taken breadth-first from the root, whose first three entries
    were the northern and southern HEMISPHERES — the operator's *"drop down selections that
    aren't address based"*, exactly.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown editable-table field kind {kind!r}; expected one of {KINDS}")
    if kind == "address" and not (state_options_key and city_options_key):
        raise ValueError(
            f"address field {name!r} needs both state_options_key and city_options_key; "
            "without them it draws two empty selects and refuses every save")
    spec = {
        "name": name,
        "kind": kind,
        "label": label or name.replace("_", " "),
        "placeholder": placeholder,
        "options_key": options_key,
        "datalist_key": datalist_key,
        "required_text": required_text,
        "edit_hint": edit_hint,
        # What this field POSTS. One key for almost everything; a composite says so here
        # rather than making the collector special-case its kind.
        "keys": [name],
    }
    if kind == "address":
        spec["keys"] = [f"{name}_{part}" for part in ADDRESS_PARTS]
        spec["state_options_key"] = state_options_key
        spec["city_options_key"] = city_options_key
    return spec


#: Row-action modes the renderer knows. Same posture as :data:`KINDS`: an unknown mode is
#: refused where it is declared, not rendered as a button that does nothing.
ACTION_MODES = ("post", "toggle", "nav", "param")


def post_action(
    key: str, *, label: str, title: str = "", extra: dict[str, Any], confirm: str = ""
) -> dict[str, Any]:
    """A button that re-posts the row with ``extra`` merged in.

    The row's current field values travel with it, so the write route sees the same shape
    a save does and needs no second entry point. ``confirm`` is the browser prompt shown
    first — supply it for anything that removes a record.
    """
    if not extra:
        raise ValueError(f"row action {key!r} posts nothing; give it the keys it should send")
    return {"key": key, "mode": "post", "label": label, "title": title or label,
            "extra": dict(extra), "confirm": confirm}


def toggle_action(
    key: str, *, field: str, on: dict[str, Any], off: dict[str, Any], title: str = ""
) -> dict[str, Any]:
    """A two-state button whose label and payload follow the row's own ``field``.

    ``on`` is what the button offers when the row's ``field`` is falsey (e.g. Retire), and
    ``off`` what it offers when it is set (Unretire). Each is ``{label, extra}``.
    """
    for state, spec in (("on", on), ("off", off)):
        if not spec.get("label") or not spec.get("extra"):
            raise ValueError(f"row action {key!r} needs a label and extra for its {state} state")
    return {"key": key, "mode": "toggle", "field": field, "title": title,
            "on": {"label": on["label"], "extra": dict(on["extra"])},
            "off": {"label": off["label"], "extra": dict(off["extra"])}}


def nav_action(key: str, *, label: str, title: str = "") -> dict[str, Any]:
    """A button that leaves the takeover rather than writing anything."""
    return {"key": key, "mode": "nav", "label": label, "title": title or label}


def param_action(
    key: str, *, label: str, param: str, value_key: str = "datum_address", title: str = ""
) -> dict[str, Any]:
    """A button that puts one of the ROW's own values into a surface query param.

    Writes nothing and posts nothing: it re-asks the server for this surface with the row
    named, which is how a table hands one of its rows to something built beside it. The
    Contacts table's *Schedule* is the first — it names the contact, and the next response
    draws `job_manager`'s own booking row prefilled from that person.

    ``param`` must be one the canonical query KEEPS, or the round trip drops it and the
    button silently does nothing. :func:`micyte.tools._record_view.seed_param` is what
    produces one of the shape the shell recognises.
    """
    if not param:
        raise ValueError(f"row action {key!r} sets no parameter; name the one it carries")
    return {"key": key, "mode": "param", "label": label, "title": title or label,
            "param": param, "value_key": value_key or "datum_address"}


def editable_table(
    *,
    schema: str,
    sandbox_id: str,
    title: str,
    columns: list[str],
    fields: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    save_route: str,
    empty_text: str,
    add_label: str,
    row_actions: list[dict[str, Any]] | None = None,
    computed_columns: list[dict[str, str]] | None = None,
    filters: dict[str, Any] | None = None,
    export: dict[str, Any] | None = None,
    views: dict[str, Any] | None = None,
    region_map: dict[str, Any] | None = None,
    gallery: dict[str, Any] | None = None,
    identity_column: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """Assemble the payload, refusing a field set that cannot fill the columns.

    ``len(fields) == len(columns) - 1`` is checked here rather than left to the renderer,
    because a mismatch shows up as a table whose cells are one column out — which reads as
    a data problem, not a payload one.

    ``filters`` is the controls half of :func:`micyte.tools._record_view.narrow` — a search
    box and some facets — and ``rows`` are the rows it already narrowed. Both are OPTIONAL
    and absent by default, so the tables that have no filter bar (supply batches, sales)
    serialize byte-for-byte what they did before.

    ``export`` is ``{route, tool_id, label}``: the CSV of the rows on screen. It carries the
    tool id rather than a document name because what leaves is the TABLE — the derived
    customer name, the decoded date, the dollars — and none of that is in the document. The
    route rebuilds this same payload from the same params, so the download and the screen
    are one call, not two selections that have to agree.

    ``views`` (from :func:`micyte.tools._record_view.views`) says WHICH FACE is drawn;
    ``region_map`` (from :func:`micyte.tools._row_map.region_map`) and ``gallery`` (from
    :func:`micyte.tools._row_gallery.card_gallery`) are the faces that are not the table —
    the same narrowed rows drawn as the places they are in, and drawn one card each. One
    key per face rather than a single blob because they answer different questions, and
    because a table can legitimately declare a switch whose face comes back empty: a book
    of work with no addresses in it has a Map button and no polygons.

    The rows are narrowed ONCE, before ANY face is built, so no face can show a set
    another does not. That is the same reason ``rows`` here are already-narrowed rows
    rather than everything plus a filter spec.
    """
    expected = len(columns) - (1 if identity_column else 0)
    if len(fields) != expected:
        raise ValueError(
            "editable_table needs one field per column"
            + (" after the identity column" if identity_column else "")
            + f": {expected} expected, {len(fields)} given"
        )
    for action in row_actions or ():
        if action.get("mode") not in ACTION_MODES:
            raise ValueError(
                f"unknown row-action mode {action.get('mode')!r}; expected one of {ACTION_MODES}"
            )
    return {
        "schema": schema,
        "container": "editable_table",
        "sandbox_id": sandbox_id,
        "title": title,
        "columns": columns,
        # Whether column 0 is the record's own address. False for the tables an operator
        # reads rather than reconciles: the operator, 2026-08-18, on the jobs table —
        # "there shouldn't be a presence of lcl_id for job tables despite that being the
        # main organizing datum value of each entry. i.e. dates should be the first column
        # in human readable forms and filters alike". The address is still on every row
        # (`datum_address`), so editing and row actions are unaffected; it is not DRAWN.
        "identity_column": bool(identity_column),
        "fields": fields,
        "rows": rows,
        "row_count": len(rows),
        "save_route": save_route,
        "empty_text": empty_text,
        "add_label": add_label,
        "row_actions": list(row_actions or ()),
        "computed_columns": list(computed_columns or ()),
        # Absent, not empty, when there is no filter bar: the renderer draws the bar exactly
        # when the key is there, so `{}` would give every table a control strip with nothing
        # in it.
        **({"filters": dict(filters)} if filters else {}),
        **({"export": dict(export)} if export else {}),
        # Same absent-not-empty rule: a table with one face declares no switch at all,
        # rather than a switch with one button on it.
        **({"views": dict(views)} if views else {}),
        **({"region_map": dict(region_map)} if region_map else {}),
        **({"gallery": dict(gallery)} if gallery else {}),
        **extra,
    }


def editable_table_error(schema: str, message: str) -> dict[str, Any]:
    """The same container, carrying a reason instead of a table."""
    return {"schema": schema, "container": "editable_table", "error": message,
            "columns": [], "fields": [], "rows": [], "row_count": 0}


def node_options(lcl_doc: Any, *prefixes: str) -> list[dict[str, str]]:
    """``[{value: node, label: 'name (node)'}]`` for lcl definition nodes under ``prefixes``.

    What fills a ``select``/``datalist`` field: the farm's own products, its own contacts.
    Written out once in the inventory table and again — identically — the moment a second
    writable record table existed, which is the point at which a private helper stops being
    private.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in getattr(lcl_doc, "rows", ()) or ():
        # Both definition families: a node that denotes a document keeps its row at
        # `4-3-*` (micyte.core.datum_ops.local_domain), and a picker blind to it would
        # silently drop exactly the nodes an operator has attached something to.
        if not _as_text(row.datum_address).startswith(_LCL_FAMILIES):
            continue
        head = _row_head(row)
        if len(head) < 3:
            continue
        node = _as_text(head[2])
        if node in seen or not any(node.startswith(p) and node != p for p in prefixes):
            continue
        seen.add(node)
        out.append({"value": node, "label": f"{_row_tail_label(row) or node} ({node})"})
    out.sort(key=lambda o: o["value"])
    return out


__all__ = [
    "ACTION_MODES",
    "ADDRESS_PARTS",
    "KINDS",
    "STAMP_KINDS",
    "editable_table",
    "editable_table_error",
    "field",
    "nav_action",
    "node_options",
    "param_action",
    "post_action",
    "toggle_action",
]
