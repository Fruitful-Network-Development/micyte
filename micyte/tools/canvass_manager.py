"""Canvassing — the doors on one street, and which of them have been knocked.

The operator, 2026-09-02: *"CANVASSING TAB — track addresses already knocked; a subtab
that prompts a CITY and STREET and returns a table of addresses. One canvassing doc per
user. A met prospect becomes a customer entry or a partial one to finish later."*

## Why this is not a table of visits

Every other writable surface in this hub lists the rows a document holds. This one lists
the rows the REGISTRAR holds and marks the ones this instance has written about, and the
difference is the whole point: what a canvasser needs to see is the houses they have NOT
been to. A table of visits answers "where have I been", which is the easy half and the
half that is useless at the door.

So the rows come from :class:`~micyte.tools._address_space.AddressSpace` — the same
structure the job and contact forms resolve an address against — and the instance's own
``canvass_log`` is joined onto them by house address. A street nobody has canvassed draws
every door with an empty "last knock", which is exactly the picture that is wanted.

## THE PROMPT IS THE QUERY, NOT A FILTER

City and street are not :func:`~micyte.tools._record_view.narrow` facets. A facet is
counted over rows that already exist; here the rows do not exist until a street is named,
because the alternative is building 41,999 of them and letting the browser sort it out.

They still travel under the record-table facet SPELLING (``canvass_f_city``), and that is
deliberate rather than a borrowed shape: the canonical query keeps only the keys it names,
and ``shell_schemas`` decided that one table's own selection state is kept by SHAPE so
that a table growing a new control needs no shell change. This IS this table's own
selection state — it is in the URL, it survives a reload, and a bookmark re-opens the
street the operator was walking.

## What it can do at a door

Two writes, both already owned by somebody else's runtime where one existed:

* **the knock** — ``save_canvass``, a ``canvass_visit`` row appended to this sandbox's own
  ``canvass_log``. See :mod:`fnd_app.instances._shared.runtime.canvass_write_runtime`.
* **the prospect** — ``save_contact``, posted to the route ``contacts_manager`` declares.
  Not a second writer: the operator's "a customer entry or a partial one to finish later"
  is a contact with a name and an address and nothing else yet, which is precisely what
  that writer already makes, minting the person as the first occupant of the house. A
  second declaration of one action is refused by ``_write_owners`` on purpose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.domains.registry import levels as lv
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._place import humanise
from ._record_view import facet_param
from ._registry import register
from ._requirements import CRM
from ._viewscope import _row_values, read_document
from .job_manager import _document_named, _lcl_options, _readable

#: The document a sandbox keeps its knocks in, and the archetype every row in it must be.
#: Declared HERE, in micyte, and imported by the fnd write runtime — never the other way
#: round, the boundary `job_manager` states for `job_log`.
#:
#: ONE per instance, which is the operator's "one canvassing doc per user": a canvasser's
#: territory is not a project and not a campaign, it is everywhere they have been.
CANVASS_LOG = "canvass_log"
CANVASS_ARCHETYPE = "canvass_visit"

TOOL_ID = "canvass_manager"
_SCHEMA = "mycite.v2.portal.workbench.tool.canvass_manager.v1"
_SAVE_ROUTE = "/portal/api/v2/canvass/save_canvass"
#: The CONTACTS route, posted by this surface and declared by `contacts_manager`. An
#: action has one owning tool and a second surface that posts it is simply a caller —
#: `_registry._write_owners` raises on a second declaration precisely so that a second
#: door onto one write cannot quietly become a second authorization for it.
_CONTACT_ROUTE = "/portal/api/v2/contacts/save_contact"
_TENANT_DEFAULT = "fnd"

#: The table's own parameter namespace — its own, so the hub's five panes sharing one
#: surface query cannot read each other's selections.
FILTER_PREFIX = "canvass"

#: How many doors one screen may hold. A street is tens of houses, so this is a ceiling
#: rather than a page — and it is `AddressSpace`'s own level cap rather than a second
#: number, for the reason that module gives: a truncated level must say so rather than
#: look complete.
MAX_HOUSES = asp.MAX_LEVEL_NODES


def state_param() -> str:
    return facet_param(FILTER_PREFIX, "state")


def city_param() -> str:
    return facet_param(FILTER_PREFIX, "city")


def street_param() -> str:
    return facet_param(FILTER_PREFIX, "street")


def children_at(space: Any, parent: str, level: int) -> list[str]:
    """The children of ``parent`` that sit at ``level`` — BY ADDRESS, not by generation.

    An address space attaches a node to its nearest PRESENT ancestor, so where an
    intermediate node is unnamed a walk of `children` skips a level and hands back
    something deeper: `job_manager._municipalities` records the case where a STREET was
    offered as a town because the county above it is in no name table. A SAMRAS address IS
    its path, so which level a node is at is a fact about the address and is read off it.
    """
    token = as_text(parent)
    if not token:
        return []
    return [child for child in space.children.get(token, ())
            if lv.depth_of(child) == level]


def street_options(space: Any, names: Any, city: str) -> list[dict[str, str]]:
    """Every street in ``city``, each carrying the city it belongs to as ``parent``.

    ``parent`` for the same reason `city_options` carries one: the client filters the list
    it already holds rather than asking again, and a street left over from a previous city
    would be a street the write cannot resolve.
    """
    token = as_text(city)
    if not token:
        return []
    out = [{"value": street, "parent": token,
            "label": humanise(names.label(street, key_field="msn_id")) or street}
           for street in children_at(space, token, lv.STREET)]
    return sorted(out, key=lambda o: o["label"])


#: Labels a tree may give the branch that holds its canvassing outcomes. An instance
#: mints the branch itself in the LCL Editor; this only recognises it once it is there.
OUTCOME_BRANCH_LABELS = frozenset({"outcomes", "outcome", "canvassing", "canvass"})


def outcome_options(options: list[dict[str, str]]) -> list[dict[str, str]]:
    """The nodes offered as outcomes, from the sandbox's operator nodes.

    A tree that has grown an `outcomes` branch offers ITS descendants and nothing else:
    measured 2026-09-10 on a live instance, the unnarrowed list was 28 nodes and every
    one of them a trade or a kind — `driveway`, `roof_soft_wash`, `legal` — so a knock
    could be filed under a service nobody had sold. A tree with no such branch keeps
    offering everything, as the job manager's trade picker does, because a rule that
    hid every outcome on a tree that had not yet named a branch would leave the form
    with an empty select and no way to say why.

    ONE RULE, BOTH SIDES: the pane draws this list and the write runtime refuses a
    node outside it, so the door cannot be offered one vocabulary and hold another.
    """
    roots = [o["value"] for o in options
             if as_text(o.get("label")).lower() in OUTCOME_BRANCH_LABELS]
    if not roots:
        return list(options)
    return [o for o in options
            if any(as_text(o["value"]).startswith(root + "-") for root in roots)]


def latest_visits(
    document: Any, *, sandbox: str, archetype: Any, authority: Any,
    names: Any, outcomes: dict[str, str],
) -> dict[str, dict[str, str]]:
    """``house msn -> the most recent knock at it``, decoded for reading.

    LATEST, not all of them. The question a canvasser asks at a door is "when was I last
    here and what happened", and a house knocked four times would otherwise put four rows
    in a table whose subject is the house. The whole history stays in the document and
    renders through the archetype's own viewscope, which is where a log belongs.

    Ordered on the DECODED day rather than on the stored token: a HOPS magnitude does not
    sort as a date, so comparing tokens would pick whichever knock happened to encode
    highest. A row whose token no clock can read carries a blank day and loses to any
    dated one, rather than sorting to the front as an empty string would.
    """
    del names
    found: dict[str, dict[str, str]] = {}
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        house = next((v for v in values.get("msn_id", ()) if v), "")
        if not house:
            continue
        outcome = next((v for v in values.get("lcl_id", ()) if v), "")
        when = _readable(authority, next((v for v in values.get("utc", ()) if v), ""))
        # `_readable` hands back the raw token when no clock can decode it, so a token is
        # only a DAY when it looks like one — see `job_manager._month_of`, which checks
        # for the same reason rather than slicing.
        day = when if len(when) == 10 and when[4] == "-" and when[7] == "-" else ""
        entry = {
            "knocked": day,
            "knocked_token": when,
            "outcome": outcome,
            "result": humanise(outcomes.get(outcome, "")) or outcome,
            "note": decode_label(next((v for v in values.get("title", ()) if v), "")),
            "datum_address": row.datum_address,
        }
        prior = found.get(house)
        if prior is None or entry["knocked"] >= prior["knocked"]:
            found[house] = entry
    return found


def house_rows(
    space: Any, names: Any, street: str, visits: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Every door on ``street``, with who the registrar has there and the last knock.

    ``occupant`` is the "mark which are already occupants" half, and it is read off the
    space rather than off the contacts document on purpose: an occupant is a node UNDER
    the house — a person or a business — and the registrar holds the ones this instance
    never wrote as well as the ones it did. A door with somebody behind it is a different
    knock from a door with nobody known behind it, whoever put them there.
    """
    token = as_text(street)
    if not token:
        return []
    rows: list[dict[str, Any]] = []
    for house in children_at(space, token, lv.HOUSE)[:MAX_HOUSES]:
        residents = [child for child in space.children.get(house, ())
                     if lv.depth_of(child) == lv.OCCUPANT]
        occupants = [humanise(names.label(person, key_field="msn_id"))
                     for person in residents]
        visit = visits.get(house, {})
        rows.append({
            "house": house,
            # What the operator reads, and what `save_contact` is handed back as the
            # street line: the registrar's own token for the door. A stored token of the
            # form `<number>_<street>_<type>` round-trips through
            # `split_street_address`, which accepts an underscore separator precisely so
            # it survives the field an operator edits. (Named generically: `micyte/` is
            # the PUBLISHED package and carries no live address — the guard that catches
            # one exists because this tree ships to customers.)
            "address": humanise(names.label(house, key_field="msn_id")) or house,
            "street_line": names.label(house, key_field="msn_id") or house,
            "occupant": ", ".join(o for o in occupants if o),
            "occupants": len(residents),
            "knocked": as_text(visit.get("knocked")),
            "result": as_text(visit.get("result")),
            "outcome": as_text(visit.get("outcome")),
            "note": as_text(visit.get("note")),
        })
    return rows


#: Every key a canvass row carries — the seam the renderer declares its columns against.
#: `test_canvass_rows_carry_the_declared_keys` pins both directions, the rule
#: `JOB_ROW_KEYS` and `CONTACT_ROW_KEYS` already state: the surface may not name a key
#: this list lacks, and this list may not drift from what :func:`house_rows` builds.
CANVASS_ROW_KEYS: tuple[str, ...] = (
    "house", "address", "street_line", "occupant", "occupants",
    "knocked", "result", "outcome", "note",
)


def _panel_error(message: str) -> dict[str, Any]:
    """The same container, carrying a reason instead of a street.

    Its own envelope rather than `editable_table_error`'s: the renderer keyed on
    `container` would otherwise draw an editable table's chrome around a canvassing
    refusal, and a pane that says one thing and looks like another is worse than a pane
    that says nothing.
    """
    # `record_table`, not `canvass`: nothing renders a `canvass` container, so a refusal
    # in one would have been an invisible refusal — the worst kind. The rest of this pane
    # draws through containers that exist for the same reason.
    return {"schema": _SCHEMA, "container": "record_table", "title": "Canvassing",
            "error": message, "empty_text": message,
            "columns": [], "rows": [], "row_count": 0}


class CanvassManager:
    """The doors on one street, and the knocks this instance has recorded on them.

    A PANE of :mod:`micyte.tools.quiar`, not a registered tool. Nothing here is reachable
    on its own from the menubar and nothing should be: a canvassing surface with no CRM
    behind it has nowhere to put the customer it produces, which is the only reason to
    knock. Its write is declared beside the runtime that performs it, the way the
    viewscope editor's is, so the action still has exactly one owner.
    """

    tool_id = TOOL_ID
    label = "Canvassing"
    summary = "Walk a street: who is at each door, and which ones you have knocked."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: What the payload actually IS. This said `canvass` until 2026-09-10 — a container
    #: nothing renders — while the payload had been a composite since 2026-09-03; the
    #: registry's renderer check caught it the day the pane was registered.
    container = "composite"
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    filter_prefix = FILTER_PREFIX
    #: Scoped to the instance kind this belongs to, as `job_manager` is: a canvasser's
    #: prospect becomes a contact, and a knock is filed beside the jobs it may lead to.
    #: Without this a registered pane is universal, and a farm would be offered it.
    requires = CRM
    #: THE KNOCK, declared where the document is owned. The gate resolves the owner of
    #: `save_canvass` from the register, so this class is REGISTERED (below) even though
    #: it is not offered on its own — `LIVE_TOOL_IDS` decides what the palette lists, the
    #: register decides who owns a write, and those are different questions. Until
    #: 2026-09-10 nothing declared this and nothing performed it: the save route named a
    #: runtime that did not exist.
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="canvass", action="save_canvass"),
    )
    #: What the renderer draws, declared here rather than inline so
    #: `CANVASS_ROW_KEYS` can be checked against it — a column naming a key nothing
    #: builds is a column that is blank on every row forever.
    table_columns: tuple[str, ...] = ("address", "occupant", "knocked", "result", "note")

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id, datum_address
        if authority_db_file is None:
            return _panel_error("authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            # The rule `_editable_table` states: a default here is not a default, it is a
            # guess about whose canvassing this is.
            return _panel_error("no sandbox selected")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from .job_manager import city_options, state_options

        query = dict(extra_query or {})
        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")

        chosen_city = as_text(query.get(city_param()))
        chosen_street = as_text(query.get(street_param()))
        chosen_state = as_text(query.get(state_param())) or lv.ancestor(
            chosen_city, lv.STATE)
        # A stale street left behind by a changed city would list another town's doors
        # under this one's name. Dropped HERE, where the payload can say the street picker
        # is waiting, rather than by a write refusing an address the screen offered.
        if chosen_street and not lv.is_under(chosen_street, chosen_city):
            chosen_street = ""

        outcomes = {o["value"]: o["label"]
                    for o in _lcl_options(store, tenant_id=self.tenant_id, sandbox=sandbox)}

        log_id = _document_named(
            store, tenant_id=self.tenant_id, sandbox=sandbox, name=CANVASS_LOG)
        visits: dict[str, dict[str, str]] = {}
        if log_id:
            anchor_id = _document_named(
                store, tenant_id=self.tenant_id, sandbox=sandbox, name="anchor")
            authority = None
            if anchor_id:
                from ._hops_dates import chrono_authority

                authority = chrono_authority(
                    read_document(store, tenant_id=self.tenant_id, document_id=anchor_id))
            visits = latest_visits(
                read_document(store, tenant_id=self.tenant_id, document_id=log_id),
                sandbox=sandbox, archetype=registry.get(CANVASS_ARCHETYPE),
                authority=authority, names=names, outcomes=outcomes)

        rows = house_rows(space, names, chosen_street, visits) if chosen_street else []
        offered = len(children_at(space, chosen_street, lv.HOUSE)) if chosen_street else 0

        # WHAT TO DO NEXT, in the words of the person reading it. Three different states
        # look identical as an empty table, and only one of them is anything to worry
        # about — so each says which it is rather than leaving a blank pane to be read as
        # a fault.
        if not chosen_city:
            empty_text = "Pick a city, then a street, to see the doors on it."
        elif not chosen_street:
            empty_text = (
                f"Pick a street in {humanise(names.label(chosen_city, key_field='msn_id'))}.")
        elif not rows:
            empty_text = (
                "No addresses are on file for this street yet. Adding a client at one "
                "puts it on the map for good — use + Client on the door you knocked.")
        else:
            empty_text = ""

        knocked = sum(1 for row in rows if row["knocked"])
        # A `composite` of two containers that ALREADY HAVE CLIENT RENDERERS, rather than
        # a `canvass` container that has none. This payload was written for a bespoke
        # renderer nobody wrote — measured 2026-09-03, `__MYCITE_V2_CONTAINER_RENDERERS`
        # has no `canvass` entry, so the pane would have drawn NOTHING at all. A surface
        # that renders is worth more than a shape that is exactly right and invisible;
        # `record_form` takes the three cascading pickers and the outcome, `record_table`
        # takes the doors. The keys below are unchanged so a bespoke renderer, if one is
        # ever written, still finds everything it needs.
        table = {
            "schema": self.schema,
            "container": "record_table",
            "title": "Canvassing",
            "sandbox_id": sandbox,
            "columns": list(self.table_columns),
            "rows": rows,
            "row_count": len(rows),
            # Said, not left to be counted off a truncated list — the rule
            # `AddressSpace.level` states about its own cap.
            "offered": offered,
            "truncated": max(0, offered - len(rows)),
            "knocked_count": knocked,
            "params": {"state": state_param(), "city": city_param(),
                       "street": street_param()},
            "chosen": {"state": chosen_state, "city": chosen_city,
                       "street": chosen_street},
            "state_options": state_options(space, names),
            "city_options": city_options(space, names),
            "street_options": street_options(space, names, chosen_city),
            # The sandbox's OWN vocabulary, exactly as a trade is: an instance adds
            # `come_back_saturday` in the LCL Editor and it is an outcome here, with no
            # code anywhere. One list, because an lcl node is an lcl node — the jobs table
            # offers the same one for its trade, its stage and its lead source.
            "outcome_options": sorted(
                ({"value": o["value"], "label": humanise(o["label"])}
                 for o in outcome_options(
                     [{"value": a, "label": lbl} for a, lbl in outcomes.items()])),
                key=lambda o: o["label"]),
            "save_route": _SAVE_ROUTE,
            "contact_route": _CONTACT_ROUTE,
            "empty_text": empty_text,
            # Recording a knock needs somewhere to put it. Said as the thing the reader
            # can do about it — reinstalling Quiar provisions the log — rather than as the
            # name of a script only the operator can run.
            "notice": "" if log_id else (
                "This instance has no canvassing log yet, so knocks cannot be recorded. "
                "Re-install Quiar from the app gallery and it will be created."),
            "writable": bool(log_id),
        }
        where = {
            "schema": self.schema,
            "container": "record_form",
            "title": "Which street",
            "count_label": (f"{knocked} of {len(rows)} knocked" if rows else ""),
            "fields": [
                {"key": "state", "label": "State", "type": "select",
                 "value": chosen_state, "options": state_options(space, names)},
                {"key": "city", "label": "City", "type": "select",
                 "value": chosen_city, "options": city_options(space, names)},
                {"key": "street", "label": "Street", "type": "select",
                 "value": chosen_street,
                 "options": street_options(space, names, chosen_city)},
            ],
            "submit_label": "Show the doors",
            # A GET, not a write: choosing a street is navigation, and the three params
            # are the ones this pane already reads itself.
            "submit_action": {"params": {"state": state_param(), "city": city_param(),
                                         "street": street_param()},
                              "success_label": "Loaded"},
        }
        panes = [{"panel_payload": where}, {"panel_payload": table}]
        if rows and log_id:
            panes += [{"panel_payload": pane}
                      for pane in self._door_forms(rows, sandbox=sandbox,
                                                   outcomes=table["outcome_options"])]
        return {"schema": self.schema, "container": "composite", "direction": "column",
                "panes": panes}

    def _door_forms(self, rows: list[dict[str, Any]], *, sandbox: str,
                    outcomes: list[dict[str, str]]) -> list[dict[str, Any]]:
        """The two things a canvasser does at a door, as forms under the street's table.

        Drawn ONLY when a street is chosen and the log exists: a knock form over no doors
        would offer an empty select, and one over an instance with no log would post to a
        refusal the table's notice already states.

        Two forms, not one, because they are two writes with two owners: the knock is
        this pane's (`save_canvass`); the prospect is `contacts_manager`'s
        (`save_contact`, posted here as a caller, never declared twice). Each names the
        door by the registrar's own address, chosen from the doors on screen, so nobody
        types a house number the space would then have to resolve.
        """
        from datetime import UTC, datetime

        doors = [{"value": r["house"],
                  "label": r["address"] + (f" — {r['occupant']}" if r["occupant"] else "")}
                 for r in rows]
        knock = {
            "schema": self.schema, "container": "record_form",
            "title": "Record a knock",
            "fields": [
                {"key": "house", "label": "Which door", "type": "select",
                 "value": doors[0]["value"], "options": doors},
                {"key": "outcome", "label": "What came of it", "type": "select",
                 "value": outcomes[0]["value"] if outcomes else "", "options": outcomes},
                {"key": "day", "label": "Day",
                 "value": datetime.now(UTC).date().isoformat(), "placeholder": "YYYY-MM-DD"},
                {"key": "note", "label": "Note (optional)", "value": "",
                 "placeholder": "Who answered, what they said, when to come back"},
            ],
            "submit_label": "Record the knock",
            "submit_action": {"route": _SAVE_ROUTE, "sandbox_id": sandbox,
                              "success_label": "Recorded"},
        }
        prospect = {
            "schema": self.schema, "container": "record_form",
            "title": "Add a client at a door",
            "fields": [
                {"key": "name", "label": "Their name", "value": "",
                 "placeholder": "First and last — the rest can be filled in later"},
                {"key": "node", "label": "Which door", "type": "select",
                 "value": doors[0]["value"], "options": doors},
            ],
            "submit_label": "Add the client",
            "submit_action": {"route": _CONTACT_ROUTE, "sandbox_id": sandbox,
                              "success_label": "Added"},
        }
        return [knock, prospect]


# Registered so the gate can resolve the owner of `save_canvass`; kept out of
# `LIVE_TOOL_IDS`, so the palette and the search still do not offer it on its own.
register(CanvassManager())

__all__ = [
    "CANVASS_ARCHETYPE",
    "CANVASS_LOG",
    "CANVASS_ROW_KEYS",
    "MAX_HOUSES",
    "OUTCOME_BRANCH_LABELS",
    "CanvassManager",
    "children_at",
    "city_param",
    "house_rows",
    "latest_visits",
    "outcome_options",
    "state_param",
    "street_options",
    "street_param",
]
