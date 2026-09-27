"""Job Manager — book and review a handyman instance's work.

An `editable_table` over the sandbox's `job_log`: who, where, which trade, when, what it
paid, a note. Nothing here knows what pressure washing is. The trade is an `lcl_id` the
instance defines for itself with `lcl_editor`, so a new trade is a row in that sandbox's
own `lcl` document and no code at all — which is the property the archetype program was
built for.

**AN ADDRESS IS SAID, NOT PICKED.** (2026-08-18) The customer and site pickers used to be
two `<select>`s over the whole address space, offered breadth-first from its root: live,
the first three options were `1 neg`, `2 neh`, `3 nwh` — the hemispheres. The operator:
*"when a user creates a job they should only need to select a state, city, and then enter
an address… The user shouldn't have to deal with drop down selections that aren't address
based."*

So the address column is one `address` field — a state, a city that follows it, and the
street typed out — and the write resolves that against the registrar, minting the street
and the house when it does not hold them and minting the customer as the first occupant
`<house>-1` when nobody is on that house yet. Two of the three controls are still
selects, because a city is a place the registrar already knows and a job booked in a town
nobody has named would be a job nobody can later find by browsing.

**WHAT THE TABLE SHOWS IS DERIVED FROM THE ONE ADDRESS IT HOLDS.** The row stores
`3-2-3-17-77-1-6-34-1` and nothing else about where the work is; the city, the county and
the postal line are read off that prefix through :mod:`micyte.tools._place`, and the place
facets match on the prefix while drawing the title. Filtering on the title would break the
day somebody corrected one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.core.instance_baseline import is_local_domain
from micyte.domains.registry import levels as lv
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._editable_table import editable_table, editable_table_error, field
from ._export import table_export
from ._place import humanise, place_of, postal
from ._record_view import facet, facet_param, narrow, views
from ._registry import register
from ._requirements import CRM
from ._row_gallery import card_gallery, card_line
from ._row_map import region_map as _region_map
from ._services import pick_field
from ._viewscope import _row_values, rows_for_archetype

#: The document a sandbox keeps its jobs in, and the archetype every row in it must be.
#: Declared HERE, in micyte, and imported by the fnd write runtime — never the other way
#: round. `micyte` is a wheel and may not import the application; the same boundary sent
#: `viewscope_view`'s runtime to `micyte/tools/_viewscope.py` on 2026-08-06.
JOB_LOG = "job_log"
JOB_ARCHETYPE = "job_event"

_SCHEMA = "mycite.v2.portal.workbench.tool.job_manager.v1"
_SAVE_ROUTE = "/portal/api/v2/jobs/save_job"
#: Where a job that holds SEVERAL services is filed. Same route family, different action
#: and a different writer: `job_event` declares exactly one `lcl_id`, so a two-trade job is
#: a different DOCUMENT rather than a wider row. See
#: `fnd_app/instances/_shared/runtime/job_document_runtime.py`.
_DOCUMENT_ROUTE = "/portal/api/v2/jobs/save_job_document"
_TENANT_DEFAULT = "fnd"

#: How many addresses a picker over the raw address space may offer. The job form no
#: longer has one — see the module docstring — but `project_manager` and `ledger_books`
#: still do, and they import the cap from here rather than each choosing their own.
MAX_PICKER_OPTIONS = 400

#: Month names for the `date` column. `strftime("%b")` is locale-dependent and the
#: registrar's dates are not: a books entry that reads differently on a differently
#: configured host is a books entry two people cannot discuss.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _job_log_id(store: Any, *, tenant_id: str, sandbox: str) -> str:
    return store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name=JOB_LOG)


def _document_named(
    store: Any, *, tenant_id: str, sandbox: str, name: str, msn_id: str = ""
) -> str:
    """One document of ``(msn, sandbox)`` by name — or by the ANCHOR FLAG.

    Asking for the literal `"anchor"` finds nothing in a sandbox whose anchor is called
    `anthology`, which is every instance's once its documents live in `system`. The flag is
    what an anchor IS; the name is what it happens to be called there.
    """
    from micyte.core.document_naming import ANCHOR_DOCUMENT_NAMES
    from micyte.core.instance_scope import resolve_msn

    msn = resolve_msn(msn_id)
    anchor_wanted = name in ANCHOR_DOCUMENT_NAMES
    clause = "is_anchor = 1" if anchor_wanted else "name = ?"
    params: list = [tenant_id, sandbox]
    if not anchor_wanted:
        params.append(name)
    if msn:
        params.append(msn)
    with store._connect() as connection:
        row = connection.execute(
            f"SELECT document_id FROM documents WHERE tenant_id=? AND sandbox=? AND {clause}"
            + (" AND msn_id=?" if msn else ""),
            tuple(params),
        ).fetchone()
    return row["document_id"] if row else ""


def _options(space: Any, names: Any, root: str) -> list[dict[str, str]]:
    """Every named address under ``root``, deepest label first.

    NOT what the job form uses any more — see the module docstring; an address is said,
    not picked. It survives because `project_manager` and `ledger_books` import it, and
    they still offer a node picker bounded by a `service_area` root. Bounded is the
    operative word: called with no root it walks from the top of the space and its first
    options are hemispheres, which is exactly the failure the job form was fixed for.
    """
    del names
    token = as_text(root)
    if token and token not in space.depth_of:
        return []
    out: list[dict[str, str]] = []
    stack = list(space.children.get(token, ()))
    while stack and len(out) < MAX_PICKER_OPTIONS:
        address = stack.pop(0)
        trail = [step["label"] for step in space.path(address)]
        depth_from_root = len(trail) - (space.depth_of.get(token, -1) + 1)
        out.append({
            "value": address,
            "label": " / ".join(trail[-min(depth_from_root, 3):]) or address,
        })
        stack.extend(space.children.get(address, ()))
    return out


def _municipalities(space: Any) -> dict[str, list[tuple[str, str]]]:
    """``{state: [(municipality, its county)]}`` — one pass over the whole space.

    By SEGMENT COUNT, not by walking four levels of `children`. An address space attaches a
    node to its nearest PRESENT ancestor, so where an intermediate node is unnamed the walk
    skips a level and hands back something deeper: it offered
    `3-2-3-17-47-3-1-1` — a street — as a town, because the county above it is not in any
    name table. A SAMRAS address IS its path, so the level is a fact about the address and
    is read off the address.

    The `cities / townships / villages` layer between a county and its towns is passed
    THROUGH rather than offered. It is a filing decision of the registrar's, not part of
    anybody's address, and a picker that made an operator choose "townships" before
    "Richfield" would be asking them to know how the corpus is stored.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    prefix = lv.STATE_CLASS + "-"
    for address in space.depth_of:
        if not address.startswith(prefix) or lv.depth_of(address) != lv.MUNICIPALITY:
            continue
        out.setdefault(lv.ancestor(address, lv.STATE), []).append(
            (address, lv.ancestor(address, lv.COUNTY)))
    for towns in out.values():
        towns.sort(key=lambda pair: asp.sort_key(pair[0]))
    return out


def state_options(space: Any, names: Any) -> list[dict[str, str]]:
    """The states an address can be placed in — those that hold at least one municipality.

    Not all 51. Thirty-one of them hold nothing, and offering one would put the operator in
    front of an empty city select with no way forward and no reason given. A state the
    registrar has not filled is not a state a job can be booked in yet, and the form says so
    by not listing it rather than by failing afterwards.
    """
    held = _municipalities(space)
    return sorted(
        ({"value": state, "label": humanise(names.label(state, key_field="msn_id"))}
         for state in held),
        key=lambda o: o["label"])


def city_options(space: Any, names: Any) -> list[dict[str, str]]:
    """Every municipality, each carrying the state it belongs to as ``parent``.

    One flat list rather than a request per state: the cascade is a client-side filter on
    `parent`, so choosing a state is instant and the payload is built once. The county rides
    in the label because `main_street` is ambiguous across two towns in this very corpus and
    two towns can share a name across counties.
    """
    found: list[tuple[str, str, str, str]] = []
    for state, towns in _municipalities(space).items():
        for municipality, county in towns:
            found.append((
                municipality, state,
                humanise(names.label(municipality, key_field="msn_id")),
                humanise(names.label(county, key_field="msn_id"))))
    # The county rides in the label only where the name alone is ambiguous. It is there so
    # an operator can tell two Richfields apart, and on the several hundred names where
    # there is only one it is thirty characters of noise on every line of a 500-line
    # dropdown — and a dropdown nobody can scan is the thing this whole change is about.
    seen: dict[str, int] = {}
    for _address, _state, name, _county in found:
        seen[name] = seen.get(name, 0) + 1
    out: list[dict[str, str]] = [
        {"value": municipality, "parent": state,
         "label": name if seen[name] == 1 else f"{name} — {county}"}
        for municipality, state, name, county in found
    ]
    return sorted(out, key=lambda o: o["label"])


def _lcl_options(store: Any, *, tenant_id: str, sandbox: str) -> list[dict[str, str]]:
    """The sandbox's OWN classification nodes — its job types.

    Read from `<sandbox>/lcl`, which `lcl_editor` writes. An instance adds "gutter
    cleaning" there and it appears here; nothing in this file changes.
    """
    out: list[dict[str, str]] = []
    raws: list[Any] = []
    for _id, name, raw in store.iter_document_rows_by_sandbox(
        tenant_id=tenant_id, sandbox=sandbox
    ):
        if not is_local_domain(name):
            continue
        raws.append(raw)
        values = _row_values(ash._row_head(raw), namespace=sandbox)
        address = next((v for v in values.get("lcl_id", ()) if v), "")
        label = next((v for v in values.get("title", ()) if v), "")
        if address and label:
            out.append({"value": address, "label": label})
    # THE TREE'S OWN `services` BRANCH FIRST (2026-09-17). On a tree that has grown one,
    # its jobs are what a job is booked as — not every operator node: measured on the
    # first trade instance on 2026-09-10, this offered 28 "trades" including `outcomes/no_answer` and
    # `kind/legal`. One reading (`_services`) for this select, the several-services
    # form and the contact form; a tree with no branch keeps the older rule below.
    from micyte.core.datum_ops import local_domain as _ld

    from ._services import service_options

    log = _ld.read_log(type("Doc", (), {
        "rows": tuple(type("Row", (), {"raw": raw, "datum_address": ""})() for raw in raws)})())
    offered = service_options(log)
    if offered:
        # `path`, so the one-line select says which trade a job type is under.
        return [{"value": o["value"], "label": o["path"]} for o in offered]
    return sorted(_operators_nodes(out, raws), key=lambda o: o["label"])


def _operators_nodes(options: list[dict[str, str]], raws: list[Any]) -> list[dict[str, str]]:
    """``options`` narrowed to the operator's OWN vocabulary — everything the base
    structure is not.

    ONLY THE OPERATOR'S NODES ARE JOB TYPES (2026-09-08). On a canonical tree the log's
    structure — `meta`, `glyphs`, the reserved slots, the class vocabularies — is defined
    by rows shaped exactly like a service, and offering `glyphs` as a trade is the kind of
    picker nobody can use. What the operator grew is the `objects` subtree (the branch
    node itself is not a trade) and, on a tree whose base was retrofitted beside an older
    root, that older root too: the rule is "not part of the base", not "under one
    address". A tree with no base keeps offering everything, as it always did.

    Pure, over the raw rows the caller already read, so the rule can be pinned without a
    store: which rows are the log's is a question of SHAPE, not of where they came from.
    """
    from micyte.core.datum_ops import local_domain as _ld

    rows = tuple(type("Row", (), {"raw": raw, "datum_address": ""})() for raw in raws)
    log = _ld.read_log(type("Doc", (), {"rows": rows})())
    if not (log.canonical and log.object_root):
        return options
    base, objects = log.root, log.object_root

    def operators(value: str) -> bool:
        if value == objects:
            return False
        if value.startswith(objects + "-"):
            return True
        return not (value == base or value.startswith(base + "-"))

    return [o for o in options if operators(o["value"])]


def job_document_form(
    *, sandbox: str, trades: list[dict[str, str]],
    states: list[dict[str, str]], cities: list[dict[str, str]],
    pick: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The pane that books a job holding SEVERAL services — a `record_form`, not a table row.

    ## Why a separate pane and not another column

    The jobs table is an ``editable_table``, and its create row cannot grow a repeat.
    ``_editable_table.KINDS`` is ``("text", "select", "date", "address")`` and :func:`field`
    RAISES on anything else, and :func:`editable_table` raises again unless
    ``len(fields) == len(columns) - 1`` — one field per column, in column order. A group
    that repeats N times has no column count, so expressing it there means a new field kind
    AND a new renderer branch. ``record_form`` already has a renderer (`lcl_editor`,
    `pim_design`, `signin_manager` and four others live in it), so this is additive: no
    JavaScript changes at all.

    ## Why the services are a TEXTAREA

    The same answer `lcl_editor._define_record_type_form` gives for a declared record type's
    field list: *"the number of fields is the thing the tenant is choosing: a fixed set of
    inputs cannot express it, and a repeating-row widget would be a bespoke renderer for one
    form."* One service per line, parsed server-side by
    ``job_document_runtime.parse_service_lines``, so the client stays dumb and the syntax
    lives with the rules. Real trades from THIS sandbox go in the placeholder, because a
    syntax nobody can see an example of is a syntax nobody uses.

    ## The address, and the cost of saying it here

    The three keys are the table's own — ``site_state``/``site_city``/``site_address``, the
    ``ADDRESS_PARTS`` an ``address`` field posts — so the form and the write route cannot
    disagree about what a value is called. What is MISSING is the cascade: `record_form`'s
    selects are independent, so the city list is not narrowed by the chosen state the way
    the table's is. That is not silently wrong — `resolve_address` refuses a city that is
    not under the chosen state ("a stale city left behind by a changed state would book the
    work in the wrong half of the country"), and each city label already carries its county
    where the name is ambiguous. It is stated on the field rather than left to be found.
    """
    if not trades:
        # An empty state written for whoever reads it. The trade list is not something
        # this tool ships — it is the instance's own lcl — so the answer is where to go,
        # not "no options". A form whose one required field can never be satisfied would
        # be a control that teaches the operator the button is unreliable.
        return {
            "schema": _SCHEMA, "container": "record_table",
            "title": "A job with several services",
            "columns": [], "rows": [], "row_count": 0, "count_label": "",
            "empty_text": (
                "This sandbox defines no trades yet, so there is nothing to bill a "
                "service against. A trade is a node the instance mints for itself in the "
                "Domain editor (LCL); add one there and it appears here and in the table "
                "above, with no code at all."),
        }
    # Real trades from THIS sandbox, so the example is one the operator can retype. The
    # second line shows the EMPTY counter on purpose: 40 of the 57 leaflets being restored
    # carry no counter at all, and a placeholder that only ever showed one would read as a
    # requirement.
    examples = [t["label"] for t in trades[:2]] or [""]
    sample = "\n".join(
        f"{label} | 2 | 350.00" if index == 0 else f"{label} |  | 120.00"
        for index, label in enumerate(examples))
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "A job with several services",
        "fields": [
            {"key": "title", "type": "text", "value": "",
             "label": "Name for this job — becomes its slot on the domain tree",
             "placeholder": "Spring wash, 77 Parmalee"},
            # `text`, not `date`: `record_form` renders text, select and textarea and
            # nothing else, and `_encoded_day` reads YYYY-MM-DD or MM-DD-YYYY either way.
            # A `date` kind here would be renderer work for a format the writer already
            # accepts in words.
            {"key": "when", "type": "text", "value": "",
             "label": "Date — YYYY-MM-DD", "placeholder": "2026-09-02"},
            {"key": "person", "type": "text", "value": "",
             "label": "Customer — needed only when the registrar has nobody at the address",
             "placeholder": "Jane Doe"},
            {"key": "site_state", "type": "select", "value": "", "label": "State",
             "options": states},
            {"key": "site_city", "type": "select", "value": "",
             "label": "City — not narrowed by the state above; a mismatched pair is refused",
             "options": cities},
            {"key": "site_address", "type": "text", "value": "", "label": "Street address",
             "placeholder": "77 Parmalee Drive"},
            # THE SELECTION FIRST, off the tree's `services` branch (2026-09-17), drawn
            # by the same field the contact form draws — one shape, `_services.pick_field`.
            # The textarea stays for what a checkbox cannot say: a counter and a price per
            # service. Either may be used; a service named in both is one service.
            *([pick_field(pick, key="services_pick", label="Jobs needed — pick from the tree")]
              if pick else []),
            {"key": "services", "type": "textarea", "value": "",
             "label": (("Counters and prices — optional, one per line, "
                        "'trade | counters | price'") if pick else
                       ("Services — one per line, "
                        "'trade | counters | price'. Counters and price are optional")),
             "placeholder": sample},
            {"key": "pay", "type": "text", "value": "",
             "label": "Total for the job, in dollars — optional", "placeholder": "$0.00"},
            {"key": "note", "type": "text", "value": "",
             "label": "Note — one description, on the job rather than per service",
             "placeholder": "front walk and driveway"},
        ],
        "submit_label": "File this job",
        "submit_action": {
            "route": _DOCUMENT_ROUTE, "sandbox_id": sandbox, "success_label": "Filed",
        },
    }


def money(stored: str) -> str:
    """Whole cents as the dollars a column headed `pay` is asking for.

    `price` is a fiat magnitude in whole cents, so the cell holding a $350 job says
    ``35000``. That was invisible while the log held two rows and unreadable the moment it
    held forty-three: a money column showing `35000` next to `1300` cannot be scanned, and
    the difference between them is not the one it looks like.

    **One formatter, from 2026-08-25** (TASK-2026-08-24-008, the display twin of the two
    money PARSERS closed the day before). This used to do its own integer arithmetic and
    its own sign rule and render `350.00`, while
    :func:`~micyte.core.datum_ops.fiat_datum.format_cents` rendered the same input
    `$350.00` — and the operator saw both, in one portal and sometimes in one payload:
    `grantor_books.account_statement` returned `balance: "$12.00"` beside
    `charged.total: "12.00"`, and `brevat` prepended a `$` of its OWN to this function's
    output to make up the difference.

    The dollar sign was never a reason for two functions. What IS a reason to keep this
    name is the second half: anything that is not a whole number of cents comes back
    untouched, for the reason :func:`_readable` returns an undecodable date token — a cell
    nobody can read should look like one, not like an empty column. `format_cents` raises
    instead, which is right for a figure in a payload and wrong for a cell in a table,
    where it would take the whole panel down.

    So this is `format_cents` for the arithmetic and the spelling, plus the pass-through
    for the cell.
    """
    from micyte.core.datum_ops.fiat_datum import FiatChainError, format_cents

    text = as_text(stored).strip()
    try:
        return format_cents(text)
    except FiatChainError:
        return text


def to_cents(amount: str) -> str:
    """A typed dollar amount as whole cents. ``""`` for empty; ``ValueError`` for junk.

    Never float: ``float("0.29") * 100`` is 28.999999999999996, and a books entry that
    rounds the wrong way once is a books entry nobody can reconcile.

    **One parser, from 2026-08-24.** This used to do its own ``Decimal(text) * 100`` and
    ``to_integral_value()``, which meant the product held TWO money parsers that disagreed
    about the half-cent: ``fiat_datum.parse_cents`` REFUSES a third decimal place — "rounding
    it would decide, silently and in the farm's favour or against it, which half-cent it
    meant" — while this one rounded, and with ``ROUND_HALF_EVEN``, so the decision was not
    even consistently directional (``4.505`` -> 450, ``4.515`` -> 452).

    The one that rounded was the one that WROTE: every ledger and job entry comes through
    here, while ``parse_cents``'s only callers were the display lens. Measured before
    changing it — nothing legitimately needed the rounding:

    * both market-report importers validate with a two-decimal regex BEFORE calling this
      (``MONEY_RE`` in each), so a third decimal never reaches it;
    * ``save_job`` and the three ledger writers take TYPED operator input, which is exactly
      the case ``parse_cents`` refuses on purpose;
    * ``bpw_import_from_xlsx.cents`` is the one caller that could see a float artifact from
      a spreadsheet, and it already treats a refusal as "no value".

    The signature is unchanged — ``str`` out, ``""`` for empty, ``ValueError`` for junk —
    because that is what its callers handle. Only the half-cent verdict moved.
    """
    from micyte.core.datum_ops.fiat_datum import (
        FiatChainError,
        FiatPrecisionError,
        parse_cents,
    )

    text = as_text(amount).strip()
    if not text:
        return ""
    try:
        return str(parse_cents(text))
    except FiatPrecisionError:
        # An amount, but finer than the store can hold — worth saying so, because the
        # person who typed it can fix it. Told apart by TYPE, not by reading the message.
        raise ValueError(
            f"{amount!r} is not an amount of money in whole cents; "
            "two decimal places at most") from None
    except FiatChainError:
        # Keep this module's own vocabulary. A parser refactor should not change the words
        # an operator sees on a job form.
        raise ValueError(f"{amount!r} is not an amount of money") from None


def _readable(authority: Any, token: str) -> str:
    """A stored HOPS token as ``YYYY-MM-DD``, or ``YYYY-MM-DDTHH:MM`` when it has an hour.

    Falling back to the raw token rather than to an empty string: a row written before the
    write path encoded dates holds something no clock can read, and showing nothing there
    would make it look like the job has no date at all rather than a date nobody can read.

    MIDNIGHT COMES BACK AS A BARE DAY. Every job in the live log was written by the day-only
    encoder, which meant midnight and nothing else, so rendering `T00:00` on all of them
    would announce a time of day nobody chose — and the `date` column would start saying
    `12:00 am` for forty-three jobs booked before a time could be typed. A job genuinely at
    midnight is indistinguishable from a job with no time, which is the price of not
    carrying a second cell to say which; for a trade instance nobody books midnight, and
    the alternative is two cells of one kind.
    """
    from ._hops_dates import hops_token_to_datetime

    moment = hops_token_to_datetime(authority, token)
    if moment is None:
        return as_text(token)
    if (moment.hour, moment.minute) == (0, 0):
        return moment.date().isoformat()
    return f"{moment.date().isoformat()}T{moment.hour:02d}:{moment.minute:02d}"


def _month_of(readable: str) -> str:
    """``YYYY-MM`` from a decoded ``YYYY-MM-DD``, else ``""``.

    Checked rather than sliced: `_readable` falls back to the raw HOPS token when no clock
    can decode it, and slicing that would put `3-2` in a dropdown labelled *month*.
    """
    token = as_text(readable)
    if len(token) >= 7 and token[4] == "-" and token[:4].isdigit() and token[5:7].isdigit():
        return token[:7]
    return ""


def spoken_clock(hhmm: str) -> str:
    """``14:00`` as ``2pm``; ``14:30`` as ``2:30pm``. Anything else comes back as itself.

    The minutes are dropped when there are none, because ``2pm`` is what the operator says
    and ``2:00pm`` is what a machine says. Twelve-hour, because this column is read by
    somebody deciding whether they can fit another job in before dinner.
    """
    token = as_text(hhmm)
    parts = token.split(":")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return token
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return token
    suffix = "am" if hour < 12 else "pm"
    twelve = hour % 12 or 12
    return f"{twelve}{f':{minute:02d}' if minute else ''}{suffix}"


def spoken_date(iso: str) -> str:
    """``2026-04-28`` as ``28 Apr 2026``; ``2026-04-28T14:00`` as ``28 Apr 2026, 2pm``.

    Anything else comes back as itself.

    The operator, 2026-08-18: *"dates should be the first column in human readable forms
    and filters alike, even if those values are represented by event datum ref mag tuples
    that employ the use of chronological HOPS."* The cell IS a HOPS magnitude — that is what
    lets the calendar read it and the .ics export carry it — and this is the only place it
    is turned into the words the operator asked for.

    The ISO form stays on the row beside this one, under the `when` key, because that is
    what the `datetime` input needs to prefill. Two keys for one cell is the rule this table
    already follows for customer, address and trade.
    """
    token = as_text(iso)
    # The time, if there is one, is split off FIRST so the day half is measured the way it
    # always was — a length check that a `T14:00` on the end would otherwise fail, turning
    # every timed job's date column back into a raw ISO string.
    day_part, _, time_part = token.partition("T")
    if len(day_part) != 10 or day_part[4] != "-" or day_part[7] != "-":
        return token
    year, month, day = day_part[:4], day_part[5:7], day_part[8:]
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return token
    index = int(month)
    if not 1 <= index <= 12:
        return token
    said = f"{int(day)} {MONTHS[index - 1]} {year}"
    if not time_part:
        return said
    clock = spoken_clock(time_part)
    # An unreadable time makes the whole cell unreadable rather than half-readable: a date
    # shown without the time it carries is a booking an operator would arrive at wrong.
    return f"{said}, {clock}" if clock != time_part else token


def spoken_month(token: str) -> str:
    """``2026-04`` as ``April 2026`` — what the month FACET draws over its own value."""
    text = as_text(token)
    if len(text) != 7 or text[4] != "-" or not (text[:4].isdigit() and text[5:].isdigit()):
        return text
    index = int(text[5:])
    if not 1 <= index <= 12:
        return text
    full = ("January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December")
    return f"{full[index - 1]} {text[:4]}"


def _people(store: Any, *, tenant_id: str, sandbox: str, registry: Any) -> dict[str, str]:
    """``{msn node: person's name}`` from the sandbox's own contacts document.

    A job's customer is a PERSON, and the msn name index only knows what a node is called —
    which, for someone at their own house, is their street address. So the jobs table read

        CUSTOMER                  ADDRESS
        <house_token>             <house_token>

    twice over, for forty-three rows, with the customer's name sitting in the contacts
    document one tab away. The instance's contacts are where person names live, so that is
    what is asked. A node with no contact still falls back to its label — the answer is then
    "we only know the address", which is true and is a space to fill.
    """
    from ._viewscope import read_document
    from .contacts_manager import CONTACT_ARCHETYPE, CONTACTS, contact_rows

    document_id = _document_named(store, tenant_id=tenant_id, sandbox=sandbox, name=CONTACTS)
    if not document_id:
        return {}
    return names_by_node(contact_rows(
        read_document(store, tenant_id=tenant_id, document_id=document_id),
        sandbox=sandbox, archetype=registry.get(CONTACT_ARCHETYPE)))


def names_by_node(contacts: Any) -> dict[str, str]:
    """``{node: name}`` from contact rows — the FIRST named contact at each node.

    First wins so a second person at one address does not silently rename the first. Two
    people at one node is ordinary — a household — and neither of them is "the customer";
    the operator picks which by editing the job. A contact with no name never claims the
    node, or the fallback to the node's own label would be lost to a blank.
    """
    out: dict[str, str] = {}
    for row in contacts or ():
        node, name = as_text(row.get("node")), as_text(row.get("name")).strip()
        if node and name and node not in out:
            out[node] = name
    return out


def _job_rows(document: Any, *, sandbox: str, names: Any, archetype: Any,
              authority: Any = None, people: dict[str, str] | None = None,
              projects: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # A SANDBOX token where a namespace is asked for, passed through unchanged. Every
    # sandbox this table addresses is one whose name IS its namespace, so it reads
    # correctly; the eight instances holding a `system` sandbox are the ones it would not,
    # and resolving the pair here is a change with its own evidence, not a tidy-up.
    for row, values in rows_for_archetype(document, archetype, namespace=sandbox):
        stamps = [v for v in values.get("utc", ()) if v]
        node = next((v for v in values.get("msn_id", ()) if v), "")
        who = (people or {}).get(node) or humanise(names.label(node, key_field="msn_id"))
        site_msn = next((v for v in values.get("site_msn", ()) if v), "")
        # WHERE, derived from the one address the row actually holds. The county and the
        # city are prefixes of `site_msn`; nothing about either is stored. See _place.
        where = place_of(names, site_msn)
        # The Phase 3b optionals. Same twin-key rule as person/customer below: the FIELD
        # key carries the stored address (what the edit row's select must prefill and the
        # write route receives), the DISPLAY twin carries what a human reads.
        trade_addr = next((v for v in values.get("lcl_id", ()) if v), "")
        project_addr = next((v for v in values.get("project_ref", ()) if v), "")
        status_addr = next((v for v in values.get("status_ref", ()) if v), "")
        lead_addr = next((v for v in values.get("lead_ref", ()) if v), "")
        # DECODED for display. The cell is a HOPS-chronological magnitude — which is what
        # makes it readable by the calendar and exportable as an .ics — and a token is not
        # something an operator can check a booking against. It is also what the `datetime`
        # input needs to prefill, so an edit that did not touch the date must not rewrite it
        # as something else.
        # TWO key sets, deliberately, because the renderer reads two different things:
        #
        #   rowHtml   reads `r[<column>]` — so a display cell needs a key named for its
        #             COLUMN (`date`, `customer`, `address`, `trade`), which is also its
        #             header text.
        #   the edit row reads `r[<field.name>]` — the request keys `save_job` receives
        #             (`when`, `person`, `site_state`/`site_city`/`site_address`,
        #             `job_type`), which cannot be renamed without renaming what the write
        #             route reads.
        #
        # They were never reconciled, so the live jobs table rendered its WHEN, PAY and NOTE
        # columns and left CUSTOMER, ADDRESS and TRADE blank — the three whose column name
        # and field name differ. The payload was correct throughout; only opening the table
        # showed it. `test_every_editable_table_column_resolves` now covers every such table.
        when_iso = _readable(authority, stamps[0]) if stamps else ""
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            # NOT a column any more. The operator, 2026-08-18: "there shouldn't be a
            # presence of lcl_id for job tables despite that being the main organizing
            # datum value of each entry." It is still on the row, because editing a job and
            # acting on one are both addressed by it.
            "job": row.datum_address,
            # ---- the date, first and in words ------------------------------------------
            "date": spoken_date(when_iso),
            "when": when_iso,
            # ---- who and where ---------------------------------------------------------
            "person": who,
            "customer": who,
            # The customer's own node, kept beside the name it resolves to. NOT a column
            # and not a facet: it is the JOIN. `people` above is `{contact node: name}`
            # from the contacts document, so this cell is exactly the key that decided
            # what the customer column says — and the Clients tab's drill-in reads it to
            # show a client the jobs whose customer column names them. Deriving that join
            # from the NAME instead would break on two customers called Jane Doe, and
            # deriving it from `site_msn` would hand one occupant the household's work.
            "person_msn": node,
            # The address as a person writes it: house, then town, both derived from
            # `site_msn`. The cell used to read a bare house token and say nothing
            # about which town that is in — forty-three rows of it.
            "address": postal(names, site_msn),
            # What the address FIELD prefills with. The state and the city are prefixes of
            # the same node; the street line is the house's own title, said out loud.
            "site_msn": site_msn,
            "site_state": lv.ancestor(site_msn, lv.STATE),
            "site_city": where["city_msn"],
            "site_address": where["house"],
            # DERIVED, and faceted on rather than shown: the value is the msn prefix and
            # the dropdown draws the title. A filter keyed on the name would stop matching
            # the day somebody corrected one.
            "city": where["city"], "city_msn": where["city_msn"],
            "county": where["county"], "county_msn": where["county_msn"],
            # ---- what, and what it paid ------------------------------------------------
            # THE FIELD KEY CARRIES WHAT IS STORED; the column carries the title. That is
            # the rule this row states three cells above, and `job_type` was the one place
            # that broke it — it held the LABEL, so the edit row's trade select prefilled
            # with nothing and a job edited without re-picking its trade was refused for
            # having none.
            #
            # QUALIFIED by address space. The index is flat and the spaces overlap —
            # live, 16 addresses are named in both txa and lcl — so an unqualified lookup
            # can label a trade with a taxonomy name.
            "job_type": trade_addr,
            "trade": humanise(names.label(trade_addr, key_field="lcl_id")),
            # edit keys (addresses) + display twins (titles) for the Phase 3b optionals
            "project": project_addr,
            "status": status_addr,
            "lead": lead_addr,
            "belongs": humanise((projects or {}).get(project_addr, project_addr)),
            "stage": (
                humanise(names.label(status_addr, key_field="lcl_id")) if status_addr else ""),
            "arrived": (
                humanise(names.label(lead_addr, key_field="lcl_id")) if lead_addr else ""),
            # NOT a column — a facet key. Derived from the DECODED date rather than sliced
            # off the stored token, because a HOPS token's leading segments are not a
            # calendar month and a dropdown offering "3-2" as a month would be a lie about
            # what the operator is filtering by. Blank when the date will not decode, and a
            # blank facet cell is never offered as an option.
            "month": _month_of(when_iso),
            "span": _readable(authority, stamps[1]) if len(stamps) > 1 else "",
            "pay": money(next((v for v in values.get("price", ()) if v), "")),
            "note": decode_label(next((v for v in values.get("title", ()) if v), "")),
        })
    return rows


#: Every key a job row carries — the seam a host of this table declares its columns
#: against, and what `contacts_manager.CONTACT_ROW_KEYS` is for contacts.
#: `test_a_job_rows_keys_are_the_declared_ones` pins both directions: a search or a facet
#: may not name a key this list lacks, and this list may not drift from what
#: :func:`_job_rows` actually builds.
JOB_ROW_KEYS: tuple[str, ...] = (
    "datum_address", "identity", "job",
    "date", "when", "person", "customer", "person_msn", "address",
    "site_msn", "site_state", "site_city", "site_address",
    "city", "city_msn", "county", "county_msn",
    "job_type", "trade", "project", "status", "lead", "belongs", "stage", "arrived",
    "month", "span", "pay", "note",
)


def by_date(rows: list[dict[str, Any]], *, ascending: bool = False) -> list[dict[str, Any]]:
    """The rows in date order, with the undated ones last however it is sorted.

    The operator, 2026-08-18: jobs *"should primarily be organized by date"*. Most recent
    first, because every job in the live book is in the past and a books view opens on what
    just happened; the upcoming pane on the Overview asks for ``ascending`` instead, which
    is the same rule pointed at the future.

    An undated job — or one whose token no clock could decode — sorts LAST in both
    directions. An empty string would otherwise sort to the very front of an ascending list
    and read as the oldest work on record.
    """
    dated = [r for r in rows if as_text(r.get("when"))]
    undated = [r for r in rows if not as_text(r.get("when"))]
    dated.sort(key=lambda r: as_text(r.get("when")), reverse=not ascending)
    return dated + undated


class JobManager:
    """Book, edit and review jobs against the sandbox's own job log."""

    tool_id = "job_manager"
    label = "Jobs"
    summary = "Book work: who, where, which trade, when, what it paid."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = CRM

    applies_to_archetype: tuple[str, ...] = ("job_event",)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    #: The books LEAVE from here, as the CSV of whatever the table is currently showing.
    #: Declared on the tool, and the route refuses any tool that has not — see
    #: `_export.table_export`.
    exportable = True
    #: The prefix this table's filter parameters are namespaced under. Its own, so the ERP's
    #: three tables cannot read each other's filters out of one surface query — the reason
    #: `handyman_erp` keeps its own `erp_tab` rather than sharing `agronomics`'.
    filter_prefix = "jobs"
    #: THE FACES of this one table, in switch order, and the operator's own words for the
    #: middle one: *"a subtab of preview cards that TOGGLES to a map view. Opening a job in
    #: either setting shows the SAME job profile view. One view, two indexes."*
    #:
    #: Declared on the class rather than written inline at the `views(...)` call, for the
    #: same reason `table_columns` is: it is the list a test can check the RENDERER against.
    #: A face id the renderer cannot build used to be silent — `setView` hid the map and
    #: showed the table whatever was pressed — so the switch could offer a button that did
    #: nothing and look correct. `test_every_declared_face_has_a_renderer` reads both.
    view_options: tuple[tuple[str, str], ...] = (
        ("table", "Table"), ("gallery", "Cards"), ("map", "Map"))
    #: WHAT A CARD SAYS — the heading, the line under it, the figure on the right, and the
    #: labelled lines below. Declared here for the same reason `search_columns` is: these
    #: are ROW keys, and a card line naming a column nobody BUILDS is a line that never
    #: draws — silently, because a blank line is dropped rather than drawn empty.
    #: `test_a_card_only_names_columns_a_job_row_carries` reads both lists.
    #:
    #: NO IMAGE. `job_event` declares none and `save_job` writes none; see `_row_gallery`.
    card_title_column = "customer"
    card_subtitle_column = "address"
    card_badge_column = "pay"
    card_lines: tuple[tuple[str, str], ...] = (
        ("date", ""), ("trade", ""), ("stage", ""), ("belongs", "project"),
        ("arrived", "lead"), ("note", ""))
    #: The display columns, declared HERE rather than written inline at the one call site, so
    #: `search_columns` below can be checked against them. A search box silently covering a
    #: column that was renamed is a box that looks broken and reports nothing —
    #: `test_a_search_column_is_a_column_this_table_shows` is what catches it.
    #: One VALUE column per editable field, in field order — the edit row renders one
    #: cell per field after the identity column, so a field without a column (or out of
    #: order) skews every row above and below it while editing. `stage`/`belongs`/
    #: `arrived` are the display twins of the `status`/`project`/`lead` fields.
    #: THE DATE IS THE FIRST COLUMN and the row's own address is not a column at all —
    #: the operator's ruling of 2026-08-18. One VALUE column per editable field, in field
    #: order and with no identity column in front of them, so a field without a column (or
    #: out of order) skews every row above and below it while editing. `date`/`customer`/
    #: `address`/`trade`/`stage`/`belongs`/`arrived` are the display twins of the
    #: `when`/`person`/`site`/`job_type`/`status`/`project`/`lead` fields.
    table_columns: tuple[str, ...] = (
        "date", "customer", "address", "trade", "stage", "pay", "note",
        "belongs", "arrived")
    search_columns: tuple[str, ...] = (
        "customer", "address", "city", "county", "trade", "stage", "belongs", "arrived",
        "note", "date", "pay")
    #: DERIVED beside the row rather than shown — see `_month_of` and
    #: :mod:`micyte.tools._place`. A facet on a column nobody displays is legitimate; a
    #: facet on a column nobody BUILDS is a dropdown that offers nothing forever. The two
    #: `_msn` keys are what the place facets MATCH on; `city` and `county` are what they
    #: draw and what the search box reads.
    derived_columns: tuple[str, ...] = (
        "month", "city", "city_msn", "county", "county_msn")
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="job_event", action="save_job"),
        # A job that holds SEVERAL services is a different DOCUMENT, so it is a different
        # declared write — its own document kind, its own action, judged on its own. The
        # `job` archetype is the header row's, which is the row a reader opens the
        # document for; `job_event` above is untouched and still serves an instance that
        # books single-trade work.
        DeclaredWrite(document_kind="job", action="save_job_document"),
        # Minting an address is a SEPARATE declared write. Booking a job is an entry in
        # one instance's books; naming a place the world did not have adds a node every
        # instance's browser shows forever, and the two should not share an authorization.
        DeclaredWrite(document_kind="record", action="create_site"),
    )

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The jobs table, and beneath it the pane that can express several services.

        A `composite` of two payloads the shell already renders, the shape `lcl_editor`
        uses for its object pane — NOT a nested `tabbed`, because this tool is itself a tab
        inside Quiar and a tab strip inside a tab strip is a place an operator loses track
        of where they are.

        The panes are built INDEPENDENTLY. The table refuses a sandbox with no `job_log`,
        and a job document does not live in the job log — so the second pane still works
        there, and folding the table's refusal into the whole tool would hide a capability
        behind an unrelated missing document. Each pane says its own thing; that is what a
        composite is for.
        """
        del document_id
        table = self.build_table(
            authority_db_file=authority_db_file, sandbox_id=sandbox_id,
            datum_address=datum_address, extra_query=extra_query)
        pane = self._services_pane(
            authority_db_file=authority_db_file, sandbox_id=sandbox_id, table=table)
        if pane is None:
            return table
        return {
            "schema": self.schema, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": table}, {"panel_payload": pane}],
        }

    def _services_pane(
        self, *, authority_db_file: Path | None, sandbox_id: str, table: dict[str, Any],
    ) -> dict[str, Any] | None:
        """The several-services form, or ``None`` when there is nothing to build it from.

        The pickers come off the TABLE'S OWN PAYLOAD when it built one, so the two panes
        cannot offer different trades or different towns out of two reads of one store —
        the failure `_job_rows` records for its two key sets, in a cheaper form. When the
        table refused, they are read here instead, because the refusal it carries
        ("no job log yet") says nothing about whether this instance has trades.
        """
        sandbox = as_text(sandbox_id)
        if authority_db_file is None or not sandbox:
            return None
        trades = table.get("trade_options")
        states = table.get("state_options")
        cities = table.get("city_options")
        if trades is None or states is None or cities is None:
            from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

            store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
            registry = arc.registry_for(store.read_documents_by_sandbox(
                tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX))
            names = nn.name_index_for(
                store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
            space = asp.address_space_for(names, key_field="msn_id")
            trades = _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)
            states = state_options(space, names)
            cities = city_options(space, names)
        # The pick off the tree, read ONCE here; the table's trade select above read the
        # same branch through `_lcl_options`, so the two cannot offer different jobs.
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter as _Store

        from ._services import offered_services

        try:
            pick, _log = offered_services(
                _Store(Path(authority_db_file)), tenant_id=self.tenant_id, sandbox=sandbox,
                msn_id=as_text(table.get("msn_id")))
        except Exception:
            pick = []
        return job_document_form(
            sandbox=sandbox, trades=list(trades), states=list(states),
            cities=list(cities), pick=pick)

    def build_table(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        title: str = "Jobs",
        date_from: str = "",
        seed_new: bool = False,
        seed: dict[str, str] | None = None,
        narrowed: bool = True,
        exported: bool = True,
        empty_text: str = "No jobs booked yet — use + Book a job.",
    ) -> dict[str, Any]:
        """The jobs table, with the knobs a HOST of it needs.

        The ERP's overview embeds this same table as its "upcoming work" pane — the real
        form, posting the real route, owned by the tool that declares the write. A second
        booking form would be a second write surface for one action, and ``_write_owners``
        raises on a second declaration precisely so that cannot happen quietly.

        That pane passes ``narrowed=False, exported=False``. Not decoration: its rows are
        already cut by ``date_from``, which is NOT one of the filter params, so an export
        button there would build its href from the filter params alone and take the whole
        log out of the building while the screen showed six upcoming jobs. A download whose
        href cannot express the cut it is under does not get offered.

        ``seed`` PREFILLS that create row, keyed by FIELD NAME — ``person``, ``site_state``,
        ``site_city``, ``site_address`` — which is what the renderer's edit row reads. It is
        how the Contacts table's *Schedule* books from a contact: `contacts_manager` maps
        that row's own keys across and hands them here, so the form the operator sees is
        this one, posting this route, owned by the tool that declares the write. Only
        meaningful with ``seed_new``; a row already open for EDIT is never overwritten by
        it, because the record on file outranks a prefill.
        """
        if authority_db_file is None:
            return editable_table_error(self.schema, "authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            # A default sandbox here is not a default, it is a guess about whose books to
            # write in — the rule `_editable_table` states and `save_invoice` follows.
            return editable_table_error(self.schema, "no sandbox selected")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        log_id = _job_log_id(store, tenant_id=self.tenant_id, sandbox=sandbox)
        if not log_id:
            return editable_table_error(
                self.schema, f"{sandbox} has no job log yet — onboarding creates one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")

        document = read_document(store, tenant_id=self.tenant_id, document_id=log_id)
        anchor_id = _document_named(store, tenant_id=self.tenant_id, sandbox=sandbox, name="anchor")
        authority = None
        if anchor_id:
            from ._hops_dates import chrono_authority

            authority = chrono_authority(
                read_document(store, tenant_id=self.tenant_id, document_id=anchor_id))
        # The sandbox's projects, as address -> name: the display twin of `project_ref`
        # and the picker's options, from ONE read so the two cannot disagree.
        projects_map: dict[str, str] = {}
        from .project_manager import PROJECTS

        projects_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=PROJECTS)
        if projects_id:
            projects_doc = read_document(
                store, tenant_id=self.tenant_id, document_id=projects_id)
            for prow in getattr(projects_doc, "rows", ()) or ():
                pvalues = _row_values(ash._row_head(prow.raw), namespace=sandbox)
                # `named`, not `title`: `title` is this function's own parameter, and
                # rebinding it here would put the last project's name in the header.
                named = decode_label(
                    next((v for v in pvalues.get("title", ()) if v), ""))
                if named:
                    projects_map[prow.datum_address] = named

        rows = _job_rows(
            document, sandbox=sandbox, names=names, archetype=registry.get("job_event"),
            authority=authority,
            people=_people(store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry),
            projects=projects_map)

        # Only the jobs on or after a given day. String comparison on `YYYY-MM-DD` is a date
        # comparison; an undated job — or one whose token no clock could decode — carries a
        # blank `when` and is left OUT of an upcoming list rather than sorted to the front of
        # it, which is what an empty string would do.
        cut = as_text(date_from)
        if cut:
            rows = [r for r in rows if as_text(r.get("when")) >= cut]
        # ORGANIZED BY DATE, always — the operator's ruling. An upcoming list reads forward
        # from today; the book reads back from the most recent thing that happened.
        rows = by_date(rows, ascending=bool(cut))

        # The place titles the facets DRAW, gathered from the rows that carry them. Built
        # from the rows rather than from the space so a dropdown can only ever offer a
        # place some job is actually at — which is the same rule `narrow` follows for
        # every other facet, applied to a value nobody could read.
        # NOT `title` as the loop variable: `title` is this function's own parameter, and
        # the first cut of this rebound it — so the table's header drew the word "county"
        # where its name belongs. Found on a screenshot, not by a test.
        place_titles: dict[str, str] = {}
        for entry in rows:
            for key, shown in (("city_msn", "city"), ("county_msn", "county")):
                if entry.get(key):
                    place_titles[as_text(entry[key])] = (
                        as_text(entry[shown]) or as_text(entry[key]))
        month_titles = {
            as_text(r["month"]): spoken_month(as_text(r["month"])) for r in rows if r.get("month")}

        # ONE RULE FOR EVERY FACET: the value is what the row STORES and the label is the
        # title it resolves to. Place, month, trade, stage and project all follow it now —
        # so a bookmarked filter keeps matching after somebody renames a trade, exactly as
        # it does after somebody corrects a town's name.
        def titles_for(key: str, shown: str) -> dict[str, str]:
            return {as_text(r[key]): as_text(r[shown]) or as_text(r[key])
                    for r in rows if r.get(key)}

        trade_titles = titles_for("job_type", "trade")
        stage_titles = titles_for("status", "stage")
        project_titles = titles_for("project", "belongs")

        controls: dict[str, Any] | None = None
        if narrowed:
            rows, controls = narrow(
                rows, query=extra_query, param_prefix=self.filter_prefix,
                search_columns=self.search_columns,
                # WHERE first, because that is what an operator narrows by when they are
                # looking at a book of work. The value is the msn prefix and the label is
                # the registrar's own title for it — the operator's rule, exactly:
                # "filtering functions would merely operate on msn_id's but visually it
                # would use the titles given to these parent nodes".
                facets=(facet("county_msn", label="county", all_label="All counties",
                              titles=place_titles),
                        facet("city_msn", label="city", all_label="All cities",
                              titles=place_titles),
                        facet("job_type", label="trade", all_label="All trades",
                              titles=trade_titles),
                        # Newest first, and stated: sorted by count, June 2026 lands
                        # between April and May, and a chronological dropdown out of
                        # chronological order reads as a fault in the dates.
                        facet("month", label="month", all_label="All months",
                              titles=month_titles,
                              order=tuple(sorted(month_titles, reverse=True))),
                        facet("status", label="status", all_label="All statuses",
                              titles=stage_titles),
                        facet("project", label="project", all_label="All projects",
                              titles=project_titles)),
                search_placeholder="Search jobs",
            )

        # THE OTHER FACES of the same narrowed rows. Built after `narrow` and from its
        # output, never from `rows` before it: a card or a shaded county showing work the
        # table beside it is filtering out is the one failure this ordering makes
        # unreachable.
        view_switch: dict[str, Any] | None = None
        mapped: dict[str, Any] | None = None
        cards: dict[str, Any] | None = None
        if narrowed:
            view_switch = views(self.filter_prefix, query=extra_query,
                                options=self.view_options)
            mapped = _region_map(
                rows, store=store, tenant_id=self.tenant_id, level="county",
                facet_param=facet_param(self.filter_prefix, "county_msn"),
                active=as_text((extra_query or {}).get(
                    facet_param(self.filter_prefix, "county_msn"))))
            # WHAT A JOB HAS, and nothing it does not. No photograph: `job_event` declares
            # no image field and `save_job` has no path that would write one, so a card
            # with a picture frame on it would be claiming a field exists and is unset.
            # See the docstring of `_row_gallery`.
            cards = card_gallery(
                rows,
                title_column=self.card_title_column,
                subtitle_column=self.card_subtitle_column,
                badge_column=self.card_badge_column,
                lines=tuple(card_line(column, label=label)
                            for column, label in self.card_lines),
                # A job at an address the registrar has nobody on yet is a real row, not a
                # broken one, and a card with no heading reads as a rendering fault.
                untitled_text="(no customer named)",
                empty_text="No jobs match — clear a filter, or book one from the table.")

        trades = _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)

        editing = {"datum_address": as_text(datum_address)} if datum_address else None
        if editing is None and seed_new:
            # A CREATE row, seeded open. `{"datum_address": ""}` is what the renderer reads
            # as "new" — the same shape its own + button builds. `seed` fills whichever of
            # this table's FIELD keys the host could answer for; the rest draw empty, so a
            # contact with no address on file still opens a usable form rather than none.
            editing = {"datum_address": "", **{k: as_text(v) for k, v in (seed or {}).items()}}
        return editable_table(
            schema=self.schema, sandbox_id=sandbox, title=title,
            columns=list(self.table_columns),
            # NO IDENTITY COLUMN. The date is column 0 and the row's address is carried on
            # the row without being drawn — the operator's ruling of 2026-08-18.
            identity_column=False,
            fields=[
                # A MOMENT, not a day (2026-09-02). A trade instance books APPOINTMENTS —
                # "Tuesday at 2" — and until this kind existed the form drew a bare
                # `<input type="date">` and the write encoded midnight, always, so a time of
                # day was not expressible anywhere in the product. The cell is unchanged:
                # the `utc` babelette always carried a full moment and the decoders always
                # kept the hour; only the write side could not set one.
                #
                # THE TIME IS NOW PART OF WHAT A BOOKING IS, and the refusal says so. A
                # `datetime-local` input yields "" until BOTH halves are filled — a day with
                # no time posts nothing at all — so there is no honest way to offer it as
                # optional here, and a form that looked optional would refuse every
                # half-filled save with a message about the date. `save_job` still accepts a
                # bare `YYYY-MM-DD` from its other callers (the .xlsx importers, the .ics
                # path), which is what every job already in the log says: midnight.
                field("when", kind="datetime", label="date",
                      required_text="A job needs a day and a time — pick both.",
                      edit_hint="the day and the time you are due there; stored against "
                                "this sandbox's own chronology"),
                # A NAME, not a node. The customer is minted as the first occupant of the
                # house when nobody is on it yet, and matched by name when somebody is —
                # so what the operator types here is what the registrar ends up calling
                # them. Optional, because an address that already has an occupant does not
                # need one supplied; `save_job` says so when it does.
                field("person", label="customer", placeholder="e.g. Jane Doe",
                      edit_hint="the person or business at this address; needed only when "
                                "the registrar has nobody there yet"),
                field("site", kind="address", label="address",
                      placeholder="120 Maple Street",
                      state_options_key="state_options", city_options_key="city_options",
                      required_text="A job needs a state, a city and a street address.",
                      edit_hint="the street address as you would write it; the registrar "
                                "learns it if it does not hold it yet"),
                field("job_type", kind="select", label="trade", options_key="trade_options",
                      required_text="Pick a trade — add one in the LCL Editor."),
                # `stage` is the DISPLAY column; the field posts `status` (the lcl
                # address), the twin-key rule person/customer follow. Both selects offer
                # the sandbox's own lcl nodes — a pipeline is minted the way trades are.
                field("status", kind="select", label="stage", options_key="trade_options",
                      edit_hint="optional — where this job sits in your pipeline"),
                field("pay", placeholder="$0.00",
                      edit_hint="typed in dollars; stored as whole cents against this "
                                "sandbox's fiat datum"),
                field("note", placeholder="front walk and driveway"),
                # In COLUMN ORDER with `belongs` and `arrived` — see table_columns.
                field("project", kind="select", label="project",
                      options_key="project_options",
                      edit_hint="optional — the standing thing this job is done against"),
                field("lead", kind="select", label="lead source",
                      options_key="trade_options",
                      edit_hint="optional — how the work arrived"),
            ],
            rows=rows, save_route=_SAVE_ROUTE,
            empty_text=empty_text,
            add_label="Book a job",
            filters=controls,
            views=view_switch,
            region_map=mapped,
            gallery=cards,
            export=table_export(self.tool_id) if exported else None,
            state_options=state_options(space, names),
            city_options=city_options(space, names),
            trade_options=trades,
            project_options=[
                {"value": address, "label": label}
                for address, label in sorted(projects_map.items(), key=lambda kv: kv[1])
            ],
            editing=editing,
        )

register(JobManager())

def table_pane(payload: dict) -> dict:
    """The TABLE half of whatever `build_panel_payload` returned.

    It returns a `composite` since 2026-09-03 — the table over the multi-service booking
    form — and sixteen tests read the table's keys off the top level. One named way
    through, so the next reshape changes this function and nothing else; reaching into
    `panes[0]` at sixteen call sites is how a shape becomes unchangeable.
    """
    if payload.get("container") != "composite":
        return payload
    for pane in payload.get("panes") or ():
        inner = (pane or {}).get("panel_payload") or {}
        if inner.get("container") == "editable_table":
            return inner
    return payload


__all__ = ["JOB_ROW_KEYS", "MAX_PICKER_OPTIONS", "JobManager", "by_date", "city_options", "job_document_form", "money", "names_by_node", "spoken_clock", "spoken_date", "spoken_month", "state_options", "table_pane", "to_cents"]
