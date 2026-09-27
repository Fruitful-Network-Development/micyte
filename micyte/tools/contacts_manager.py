"""Contacts — the people an instance keeps facts about, and the surface that edits them.

The old ``contacts_viewer`` was retired on 2026-08-06 because measured across all seven live
sandboxes it resolved NOTHING: it read an ``agro_erp`` document whose sandbox no longer
exists, and its rows were four positional ``title`` cells — name, email, phone, website by
POSITION, which is exactly what the archetype program replaced.

This reads the ``contacts`` class instead. Its one member is ``natural_entity_profile``,
extended in Phase 1 into what the operator specified: an msn address, the name parts (a
repeated ``ruiqi_id``, which is a ref-mag datum of a name and always was), plus email,
phone, birthday and website. Nothing here is positional; every cell is under its own marker.

**A contact is not a second archetype.** A person and a contact are one row — the operator's
tree files ``contacts`` under ``list > Record`` because a contact LIST is organised by
address, while the row itself is a person. That is why the class declares ``slot_grid``: one
contact is a card, and the row-count rule turns eighty of them into the list.

## Opening one client

The table is a list, and a list is not the whole question an operator has about a customer.
Until 2026-09-02 nothing on screen joined a contact to the work done for them: the answer to
*"what have we done for this one"* meant remembering their street address, switching to the
Jobs tab and searching for it — which finds the jobs whose CUSTOMER cell the job table
already resolved from this very document.

So the tab has two states, the shape PIM's Posts gallery uses for a piece: the list until
somebody is chosen, then that client's card and their work, with a way back. The join is by
NODE — a contact's ``msn_id`` against a job's ``site_msn`` — because that is the join
``job_manager.names_by_node`` already makes in the other direction, and a job is booked
against an address rather than against a contact row. Where two people share one house the
pane says so rather than presenting a household's work as one person's.
## SCHEDULE — a contact, and the job form already filled in       (2026-09-02)

The operator's "most important part": from a customer, book the work. Every row carries a
*Schedule* button, which writes nothing — it puts that row's address in ``contacts_seed``
and the next response draws ``job_manager``'s OWN booking row above this table, prefilled
with the person's name and the three parts of their address.

**The prefill is a mapping, not a lookup.** :data:`CONTACT_ROW_KEYS` already carries
``node_state``, ``node_city`` and ``node_address`` — "the state and city are prefixes of the
same node, the street line is the house's own title said out loud" — and ``_job_rows``
derives its ``site_*`` three off ``site_msn`` the same way. Both tables already agree about
what a place is; :data:`SCHEDULE_PREFILL` is only the two vocabularies laid side by side.

**And it is job_manager's form, not a copy of one.** ``_write_owners`` raises on a second
declaration of ``save_job``, so a booking form built here could not be authorized as one —
which is the point: an action has one owning tool and every other surface is a caller.
``quiar_overview`` embeds the same table for the same reason, and this follows it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.domains.registry import levels as lv
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _address_space as asp
from . import _node_names as nn
from ._editable_table import editable_table, editable_table_error, field, param_action
from ._export import table_export
from ._place import place_of, postal
from ._record_view import back, facet, facet_param, narrow, opened, pick, seed_param, views
from ._registry import register
from ._requirements import CONTACT_FIELDS, CRM
from ._row_map import region_map
from ._viewscope import _row_values, read_document
from .job_manager import JobManager, city_options, state_options

TOOL_ID = "contacts_manager"
CONTACTS = "contacts"
CONTACT_ARCHETYPE = "natural_entity_profile"

_SCHEMA = "mycite.v2.portal.workbench.tool.contacts_manager.v1"
_SAVE_ROUTE = "/portal/api/v2/contacts/save_contact"
_TENANT_DEFAULT = "fnd"

#: WHAT A CONTACT'S ADDRESS IS CALLED ON A JOB. Left is a key `contact_rows` builds, right
#: is a FIELD NAME `job_manager`'s booking row reads — the request keys `save_job` receives.
#:
#: A straight mapping and deliberately not a lookup. `CONTACT_ROW_KEYS` already carries the
#: three address parts for exactly this reason ("the state and city are prefixes of the same
#: node, the street line is the house's own title said out loud"), and `_job_rows` derives
#: its own three the same way off `site_msn` — so the two tables already agree about what a
#: place is, and re-deriving it here would be a second derivation free to drift from both.
#:
#: `name` -> `person` because a job's customer is a NAME, not a node: `save_job` matches an
#: occupant by name and mints one when the house has nobody on it. The contact IS that
#: occupant, so the name is the one that finds them.
SCHEDULE_PREFILL: tuple[tuple[str, str], ...] = (
    ("name", "person"),
    ("node_state", "site_state"),
    ("node_city", "site_city"),
    ("node_address", "site_address"),
)

#: This table's query namespace, and the param the *Schedule* button sets to one contact's
#: row address. Declared once here because three things must agree on it — the row action
#: that writes it, the builder that reads it, and the back button that clears it — and
#: because the canonical query keeps it by SHAPE (`<prefix>_seed`), so a hand-written
#: spelling that missed the shape would be a button that silently did nothing.
_FILTER_PREFIX = "contacts"
SCHEDULE_PARAM = seed_param(_FILTER_PREFIX)


def schedule_seed(contact: dict[str, Any]) -> dict[str, str]:
    """One contact row as `job_manager`'s create-row prefill — :data:`SCHEDULE_PREFILL`.

    Blanks are carried through rather than dropped: a contact with no street on file opens
    the form with an empty address, which is a form the operator can finish, and dropping
    the key would make it look like the seed had failed.
    """
    return {job_key: as_text(contact.get(row_key, "")) for row_key, job_key in SCHEDULE_PREFILL}



def client_form(
    *, sandbox: str, pick: list[dict[str, Any]], states: list[dict[str, str]],
    cities: list[dict[str, str]],
) -> dict[str, Any]:
    """The contact form that also STARTS A JOB — a `record_form` above the table.

    Operator, 2026-09-17: the contact form fields should link *"so that in addition to
    fields being used to add a contact via an added msn_id etc. but also start a job,
    giving them a more intuitive and coherent [form-field] selection of jobs needed …
    informed by the jobs and job types defined and configured in the local domain."*

    So: the person, said the way the table's add-row says them (name, email, phone, a state,
    a city, a street), and beneath them the jobs they need, drawn from the tree's own
    `services` branch by the ONE field both job surfaces draw it with
    (`_services.pick_field`). It posts the SAME action the add-row posts —
    ``save_contact`` — with a ``services`` list beside the person; the route judges the job
    write too and files a job document at the contact's own house. Nothing picked is a plain
    contact, so the two ways of adding one cannot write a contact two different ways.

    A tree with no `services` branch draws the form WITHOUT the pick and says where the
    branch is grown — the contact half still works, and the sentence is the one the job
    form gives (`_services.no_services_branch`).
    """
    from ._services import no_services_branch, pick_field

    fields: list[dict[str, Any]] = [
        {"key": "name", "type": "text", "value": "", "label": "Name — first middle last",
         "placeholder": "Jane Doe"},
        {"key": "email", "type": "text", "value": "", "label": "Email", "placeholder": "name@example.com"},
        {"key": "phone", "type": "text", "value": "", "label": "Phone", "placeholder": "330 555 0940"},
        {"key": "node_state", "type": "select", "value": "", "label": "State", "options": states},
        {"key": "node_city", "type": "select", "value": "",
         "label": "City — not narrowed by the state above; a mismatched pair is refused",
         "options": cities},
        {"key": "node_address", "type": "text", "value": "", "label": "Street address",
         "placeholder": "120 Maple Street"},
    ]
    if pick:
        fields.append(pick_field(pick, key="services", label="Jobs needed — tick what they asked for"))
        fields.append({"key": "when", "type": "text", "value": "",
                       "label": "Date for the work — YYYY-MM-DD, blank for today",
                       "placeholder": "2026-09-17"})
        fields.append({"key": "note", "type": "text", "value": "",
                       "label": "Note — on the job, optional", "placeholder": "front walk and driveway"})
    form: dict[str, Any] = {
        "schema": _SCHEMA, "container": "record_form",
        "title": ("Add a client — and the work they need" if pick else "Add a client"),
        "fields": fields,
        "submit_label": "Save client" + (" and file the job" if pick else ""),
        "submit_action": {"route": _SAVE_ROUTE, "sandbox_id": sandbox,
                          "success_label": "Saved"},
    }
    if not pick:
        form["notice"] = no_services_branch(sandbox)
    return form


def _contacts_document_id(store: Any, *, tenant_id: str, sandbox: str) -> str:
    return store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name=CONTACTS)


#: Every key a contact row carries — the seam the ROLODEX declares its columns against.
#: `test_rolodex_columns_resolve_against_the_primitive` pins both directions: the rolodex
#: may not name a key this list lacks, and this list may not drift from what
#: :func:`contact_rows` actually builds.
CONTACT_ROW_KEYS: tuple[str, ...] = (
    "datum_address", "identity", "row", "node", "address", "name", "email", "phone",
    "birthday", "website",
    # DERIVED from `node` — see micyte.tools._place. The `_msn` pair is what the place
    # facets match on; the titles are what they draw and what the search box reads.
    "city", "city_msn", "county", "county_msn",
    # What the address FIELD prefills with: the state and city are prefixes of the same
    # node, the street line is the house's own title said out loud.
    "node_state", "node_city", "node_address",
)


def contact_rows(document: Any, *, sandbox: str, archetype: Any,
                 names: Any = None) -> list[dict[str, Any]]:
    """Every row the contacts archetype covers, as the table's fields.

    The name parts are a RUN — `ruiqi_id` repeated — so they arrive as a list and are joined
    for display rather than collapsed to the first, which would silently drop a surname.
    """
    rows: list[dict[str, Any]] = []
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        parts = [decode_label(v) for v in values.get("ruiqi_id", ()) if v]
        node = next((v for v in values.get("msn_id", ()) if v), "")
        # WHERE, derived from the one address the row holds. Nothing about the city or the
        # county is stored; both are prefixes of `node`.
        where = place_of(names, node) if names else {}
        rows.append({
            "datum_address": row.datum_address,
            "identity": row.datum_address,
            # Named for its COLUMN as well as for the write. `columns=["row", ...]` and the
            # renderer reads `r["row"]`, so the first column drew blank on every contact —
            # invisible for as long as this table had no rows in it, and visible on all 118
            # the moment it did. `job_manager` carries the same twin under the name `job`.
            "row": row.datum_address,
            # TWO keys for one cell, the rule `job_manager` records: the renderer reads
            # `r[<column>]` and the edit row reads `r[<field.name>]`. So the ADDRESS column
            # carries the node's label — a house node's token, which is what a person
            # reading a contact list needs — and `node` keeps the raw msn address the select
            # has to match to prefill. Before this the column drew `3-2-3-17-77-1-6-35-1`.
            "node": node,
            # The address as a person writes it — house, then town — instead of
            # a street-and-number with no clue which town that is.
            "address": (postal(names, node) if names and node else node),
            "city": where.get("city", ""), "city_msn": where.get("city_msn", ""),
            "county": where.get("county", ""), "county_msn": where.get("county_msn", ""),
            "node_state": lv.ancestor(node, lv.STATE),
            "node_city": where.get("city_msn", ""),
            "node_address": where.get("house", ""),
            "name": " ".join(parts),
            "email": next((v for v in values.get("email", ()) if v), ""),
            "phone": next((v for v in values.get("nominal", ()) if v), ""),
            "birthday": next((v for v in values.get("utc", ()) if v), ""),
            "website": next((v for v in values.get("website", ()) if v), ""),
        })
    return rows


def unwritable_fields(sandbox: str) -> tuple[str, ...]:
    """Which of a contact's fields this sandbox's anchor cannot express, in declared order.

    Empty means every field resolves and a contact can be written here.

    Stated ONCE and imported by the write path, so the table's refusal and the save's
    refusal cannot disagree about which fields are missing — the reason `unmet_requirements`
    is the same function for the preview and the install.

    `writable_fields`, not `fields`: the registrar reaches `nominal` through a BORROW at
    3-1-31, and checking only what the anchor defines would refuse a contact on the one
    namespace where the whole thing works.
    """
    token = as_text(sandbox)
    if not token:
        return ()
    try:
        writable = _fr.writable_fields(token)
    except KeyError:
        # An undeclared sandbox has no namespace to check against. Refusing here would hide
        # the tool on a sandbox nobody has classified yet; the write still fails loudly, with
        # the field named. Not knowing is not the same as knowing it will not work.
        return ()
    return tuple(f for f in CONTACT_FIELDS if f not in writable)


#: What one client's drill-in draws about their work. Read-only and short: the customer
#: and the address are the same on every row here — that is what "this client's jobs"
#: means — so drawing either would be two columns of the one fact the pane already states
#: in its header.
_JOB_COLUMNS: tuple[str, ...] = ("date", "trade", "stage", "pay", "note")


def _client_options(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The narrowed contacts as ``{value: row address, label: name — address}``.

    Keyed on the ROW's own datum address rather than on its node: two people at one house
    is ordinary — a household — and a picker keyed on the node would offer the same value
    twice and open whichever of them sorted first.

    The address rides in the label because a contact list of one town is a list of people
    whose names repeat; ``Jane Doe`` twice, with nothing to tell them apart, is a picker
    that cannot be used to pick.
    """
    out: list[dict[str, str]] = []
    for row in rows:
        address = as_text(row.get("datum_address"))
        if not address:
            continue
        name = as_text(row.get("name")).strip()
        where = as_text(row.get("address")).strip()
        label = f"{name} — {where}" if name and where else (name or where or address)
        out.append({"value": address, "label": label})
    out.sort(key=lambda option: option["label"].casefold())
    return out


def _jobs_for(authority_db_file: Path | None, *, sandbox: str,
              node: str) -> tuple[list[dict[str, Any]], str]:
    """``(this client's jobs, why not)`` — the jobs table's OWN rows, cut to one customer.

    Built by `job_manager`, not here. A job's date is a HOPS token decoded against the
    sandbox's own clock, its trade is an `lcl` address resolved through the name index and
    its pay is cents rendered as dollars — none of the three is a cell on the row, and a
    second derivation of them in this module is the drift `_record_view` exists to
    prevent: two screens showing one job for different money.

    THE CUT IS ON `person_msn`, the customer node, which is the same key the jobs table
    itself resolved the customer's NAME from — so what comes back is exactly the rows
    whose CUSTOMER column says this client, and the two screens cannot disagree about
    whose work a job is. Cutting on `site_msn` would have been a looser question ("work at
    this house"), and on a household it would hand one occupant the other's jobs.

    ``narrowed=False`` on purpose. The Jobs tab's filters ride in the same surface query
    this pane is built from, so a narrowed call would cut a client's history by whichever
    trade or month the tab beside it happens to be filtered to — a history silently
    missing rows, under a filter nobody set here. ``exported=False`` for the reason
    `build_table` states: a download whose href cannot express the cut it is under.

    The whole log is read to answer for one client, and that is paid ONCE per drill-in
    rather than on every render of the Clients table — the list itself never calls this.
    """
    who = as_text(node)
    if not who:
        return [], ("This client has no address in the network yet, and a job is booked "
                    "against one — so there is nothing to look their work up by.")
    payload = JobManager().build_table(
        authority_db_file=authority_db_file, sandbox_id=sandbox,
        narrowed=False, exported=False)
    if payload.get("error"):
        # The jobs table's own refusal, in its own words — "no job log yet", "no sandbox
        # selected". Flattening it to an empty list would report a missing document as a
        # client who has never had work done.
        return [], as_text(payload["error"])
    return [row for row in (payload.get("rows") or ())
            if as_text(row.get("person_msn")) == who], ""


def _client_pane(row: dict[str, Any], *, prefix: str, jobs: list[dict[str, Any]],
                 why_not: str, housemates: int) -> dict[str, Any]:
    """ONE client: what is known about them, and the work done for them.

    Two panes and a way back, the shape the Posts gallery uses for a piece: the list until
    something is chosen, then that thing. Clearing the parameter IS the return.

    Every contact field is drawn even when it is empty, and that is the point of the pane
    rather than an oversight — this list is what a flyer run is cut from, so "no address
    on file" is the fact worth seeing, and a card that hid its blanks would report a
    client with nothing to reach them by as a client with nothing to say about them.
    """
    name = as_text(row.get("name")).strip()

    def value(key: str) -> str:
        return as_text(row.get(key)).strip() or "—"

    facts = {
        "schema": _SCHEMA, "container": "record_table",
        "title": name or as_text(row.get("address")) or "This client",
        "columns": ["fact", "value"],
        "rows": [
            {"fact": "address", "value": value("address")},
            {"fact": "city", "value": value("city")},
            {"fact": "county", "value": value("county")},
            {"fact": "email", "value": value("email")},
            {"fact": "phone", "value": value("phone")},
            {"fact": "birthday", "value": value("birthday")},
            {"fact": "website", "value": value("website")},
        ],
        "row_count": 7,
        "back": back(prefix, label="All clients"),
    }
    if housemates > 1:
        # A HOUSEHOLD IS NOT A CUSTOMER. Two contacts at one house are two occupant nodes,
        # so the work below is this person's alone and the other's is under their own
        # name — which is right, and is also exactly what would read as missing history to
        # somebody who thinks of the address as the customer. Said out loud for that
        # reader rather than left to be discovered as an absence.
        facts["notice"] = (
            f"{housemates} people are listed at this address. The work below is this "
            "one's — open the others to see theirs.")

    work = {
        "schema": _SCHEMA, "container": "record_table",
        "title": f"Work for {name}" if name else "Work at this address",
        "columns": list(_JOB_COLUMNS),
        "rows": [{column: as_text(job.get(column)) for column in _JOB_COLUMNS}
                 for job in jobs],
        "row_count": len(jobs),
        "count_label": f"{len(jobs)} job(s)",
        # Written for whoever opens the Clients tab, which is the person who books the
        # work — so it says what is true and what to do, and names no other surface by a
        # name only an operator would recognise.
        "empty_text": why_not or "No work booked at this address yet.",
    }

    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": facts}, {"panel_payload": work}]}


class ContactsManager:
    """The sandbox's own contact list, editable."""

    tool_id = TOOL_ID
    label = "Contacts"
    summary = "People this instance keeps facts about: name, email, phone, birthday, website."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "editable_table"
    #: Scoped to the instance kind this belongs to — see tools/_requirements — AND to the
    #: anchors that can express a contact. `replace` rather than a second literal, so the
    #: document half cannot drift from the constant every other handyman tool references.
    #:
    #: The fields matter because holding the file is not the same as being able to write it:
    #: a farm holds `contacts` + `job_log`, passed the document gate, drew this table, and
    #: failed every save on a namespace that never defined `email`.
    requires = replace(CRM, fields=CONTACT_FIELDS)

    applies_to_archetype: tuple[str, ...] = (CONTACT_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    icon = "contacts_manager"
    #: The list LEAVES from here, as the CSV of whatever the table is currently showing —
    #: which is what makes a narrowed export possible at all: `address` is the node's LABEL,
    #: resolved through the name index, and no `ExportSpec` over the contacts document can
    #: name it. Refused by the route for any tool that has not declared this.
    exportable = True
    #: Namespaced apart from the jobs table's, so the ERP's tabs cannot read each other's
    #: filters out of the one surface query they share.
    filter_prefix = _FILTER_PREFIX
    #: Declared rather than written inline at the call site, so `search_columns` can be
    #: checked against the columns this table actually shows — a search box quietly covering
    #: a renamed column reports nothing at all.
    #: NO IDENTITY COLUMN — the operator's ruling of 2026-08-18 about the row's own datum
    #: address showing up as data. It drew `4-1-2` in front of every contact's name.
    table_columns: tuple[str, ...] = (
        "name", "address", "email", "phone", "birthday", "website")
    search_columns: tuple[str, ...] = (
        "name", "address", "city", "county", "email", "phone", "website")
    #: DERIVED beside the row rather than shown — see :mod:`micyte.tools._place`. The
    #: `_msn` keys are what the place facets MATCH on; the titles are what they draw.
    derived_columns: tuple[str, ...] = ("city", "city_msn", "county", "county_msn")
    writes: tuple[DeclaredWrite, ...] = (
        DeclaredWrite(document_kind="contact", action="save_contact"),
    )
    # `create_site` is NOT declared here. `job_manager` owns it, and `_write_owners` RAISES
    # on a second declaration — an action has one owning tool, and a second surface that
    # posts the same route is simply a caller of it.

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id
        if authority_db_file is None:
            return editable_table_error(self.schema, "authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            # The rule `_editable_table` states: a default here is not a default, it is a
            # guess about whose contact list is being edited.
            return editable_table_error(self.schema, "no sandbox selected")
        unwritable = unwritable_fields(sandbox)
        if unwritable:
            # REFUSED HERE, not at the rail, because this tool is also a PANE of the ERP.
            # Gating only the rail would leave a farm's Handyman hub drawing a full contact
            # table whose every save returned `write_failed` — the silent failure this whole
            # check exists to end. The composite needs no change: each pane builds itself.
            return editable_table_error(
                self.schema,
                f"{sandbox}'s anchor cannot express a contact: it defines no "
                f"{', '.join(unwritable)}. Contacts need those fields added to the anchor "
                "before this instance can keep them.")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        contacts_id = _contacts_document_id(store, tenant_id=self.tenant_id, sandbox=sandbox)
        if not contacts_id:
            return editable_table_error(
                self.schema, f"{sandbox} has no contacts document yet — onboarding creates one")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)
        space = asp.address_space_for(names, key_field="msn_id")

        document = read_document(store, tenant_id=self.tenant_id, document_id=contacts_id)
        rows = contact_rows(
            document, sandbox=sandbox, archetype=registry.get(CONTACT_ARCHETYPE), names=names)

        # WHO IS BEING SCHEDULED, found in the WHOLE list and before `narrow` runs. The
        # operator pressed Schedule on a row that was on screen at the time, but the filters
        # travel in the same query and a facet applied afterwards would take the contact out
        # of `rows` — and the booking form would then vanish mid-booking with nothing said.
        scheduling = as_text((extra_query or {}).get(SCHEDULE_PARAM))
        booking_for = next(
            (r for r in rows if as_text(r.get("datum_address")) == scheduling), None
        ) if scheduling else None

        # The place titles the facets DRAW, gathered from the rows that carry them — the
        # same rule `narrow` follows for every other facet, applied to a value nobody could
        # read. A dropdown can only offer a place some contact is actually at.
        place_titles: dict[str, str] = {}
        for row in rows:
            for key, title in (("city_msn", "city"), ("county_msn", "county")):
                if row.get(key):
                    place_titles[as_text(row[key])] = as_text(row[title]) or as_text(row[key])

        # Held before `narrow` rebinds it: the drill-in resolves against every contact the
        # sandbox holds, not the filtered set. Opening a client and then typing in the
        # search box would otherwise close the client — and it would read as the browser
        # losing the page rather than as the filter doing what filters do.
        every = rows

        rows, controls = narrow(
            rows, query=extra_query, param_prefix=self.filter_prefix,
            search_columns=self.search_columns,
            # WHERE, by msn prefix, drawn as the registrar's own title. The facet used to
            # be on the address LABEL, which gave a 118-contact list a dropdown of 118
            # street addresses — one option per row, which narrows nothing.
            facets=(facet("county_msn", label="county", all_label="All counties",
                          titles=place_titles),
                    facet("city_msn", label="city", all_label="All cities",
                          titles=place_titles)),
            search_placeholder="Search contacts",
        )

        # ONE CLIENT, OPENED. The table lists people and the job log lists work, and until
        # this nothing on screen joined them: reading what had been done for a customer
        # meant remembering their street address, opening the Jobs tab and searching for
        # it. The join is the one the jobs table already makes to name a customer at all —
        # a contact's `node` against a job's `site_msn` — pointed the other way.
        open_address = opened(self.filter_prefix, extra_query)
        chosen = next((r for r in every
                       if as_text(r.get("datum_address")) == open_address), None) \
            if open_address else None
        if chosen is not None:
            node = as_text(chosen.get("node"))
            jobs, why_not = _jobs_for(authority_db_file, sandbox=sandbox, node=node)
            # HOW MANY CONTACTS SHARE THE HOUSE this one is an occupant of. Derived here
            # rather than kept on the row: `place_of` already computes the house msn per
            # row and `CONTACT_ROW_KEYS` deliberately carries the city and county prefixes
            # and not this one, so adding a key for a question only this pane asks would
            # widen a declaration every reader of that list has to keep in step.
            house = lv.ancestor(node, lv.HOUSE)
            return _client_pane(
                chosen, prefix=self.filter_prefix, jobs=jobs, why_not=why_not,
                housemates=sum(1 for r in every if house
                               and lv.ancestor(as_text(r.get("node")), lv.HOUSE) == house))

        # The same rows, drawn as the counties they live in. Built from `narrow`'s output
        # so the map can never show a customer the table beside it is filtering out.
        county_param = facet_param(self.filter_prefix, "county_msn")
        mapped = region_map(
            rows, store=store, tenant_id=self.tenant_id, level="county",
            facet_param=county_param,
            active=as_text((extra_query or {}).get(county_param)))

        # A LINK TO A CONTACT THAT IS NO LONGER THERE. Falling through to the table in
        # silence would show the list under a request the reader made and nothing
        # honoured — the same failure a dropped facet is, one door along.
        stale = ("The client that link opened is not in this list any more — the row may "
                 "have been deleted, or moved to another address. Here is everyone this "
                 "instance keeps.") if open_address else ""
        # The way IN to one client, offered over the rows ON SCREEN — see
        # `_record_view.pick`. This table draws every cell as escaped text, exactly as a
        # `record_table` does, so no row is clickable and this is the affordance.
        # Absent, not empty, when there is nobody to open: the renderer draws the bar
        # exactly when the key is there.
        picker = pick(self.filter_prefix, _client_options(rows),
                      label="Open a client", go_label="Open")

        editing = {"datum_address": as_text(datum_address)} if datum_address else None
        table = editable_table(
            schema=self.schema, sandbox_id=sandbox, title="Contacts",
            filters=controls,
            **({"pick": picker} if picker else {}),
            **({"notice": stale} if stale else {}),
            views=views(self.filter_prefix, query=extra_query,
                        options=(("table", "Table"), ("map", "Map"))),
            region_map=mapped,
            export=table_export(self.tool_id),
            columns=list(self.table_columns),
            identity_column=False,
            fields=[
                field("name", label="name", placeholder="first middle last",
                      required_text="A contact needs a name."),
                # REQUIRED, because the archetype requires it and because it is what the
                # operator meant by contacts "integrating msn_id's": a contact is a person
                # AT AN ADDRESS in the network, not a free-floating name. The pre-write
                # check refuses a row without one, so an optional field here would have
                # produced a form that looks fine and a save that always fails.
                #
                # SAID, not picked, since 2026-08-18 — the same field the jobs table uses,
                # and for the same reason. The select it replaces offered 400 nodes taken
                # breadth-first from the top of the space, so its first three options were
                # the hemispheres. The contact is minted as the first occupant of the house
                # when the registrar has nobody there yet, which is where a contact belongs:
                # An occupant sits UNDER a house node, not at it.
                field("node", kind="address", label="address",
                      placeholder="120 Maple Street",
                      state_options_key="state_options", city_options_key="city_options",
                      required_text="A contact needs a state, a city and a street address.",
                      edit_hint="the street address as you would write it; the registrar "
                                "learns it if it does not hold it yet"),
                field("email", placeholder="name@example.com"),
                field("phone", placeholder="330 555 0940"),
                field("birthday", kind="date", label="birthday"),
                field("website", placeholder="example.com"),
            ],
            rows=rows, save_route=_SAVE_ROUTE,
            empty_text="No contacts yet — use + Add a contact.",
            add_label="Add a contact",
            # SCHEDULE. One button per contact, and it writes nothing: it names the row in
            # the surface query and the next response draws `job_manager`'s booking form
            # above this table, prefilled from that person. A form of its own here would
            # have been a second write surface for `save_job`, which `_write_owners` refuses
            # — see the module docstring, and `quiar_overview`, which embeds the same table
            # for the same reason.
            row_actions=[param_action(
                "schedule", label="Schedule", param=SCHEDULE_PARAM,
                title="Book a job for this contact, at this address")],
            state_options=state_options(space, names),
            city_options=city_options(space, names),
            editing=editing,
        )
        if booking_for is None:
            return table
        return self._booking_composite(
            table, contact=booking_for, sandbox=sandbox,
            authority_db_file=authority_db_file, extra_query=extra_query)

    def _booking_composite(
        self, table: dict[str, Any], *, contact: dict[str, Any], sandbox: str,
        authority_db_file: Path | None, extra_query: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """The contacts table with `job_manager`'s own booking row open above it.

        A COMPOSITE rather than a second container: `paintPanelInto` dispatches a pane on
        its `container`, so the jobs pane is drawn by the one renderer that knows the
        booking form and this table is drawn by the one it always was. The tool still
        DECLARES `editable_table` — that is what it is, and what every sweep over the
        editable tables must keep checking it as; this is the same table with something
        stood in front of it while one contact is being scheduled.

        The jobs pane is asked for `narrowed=False, exported=False` for the reason
        `quiar_overview`'s is: nothing on screen here is the whole job log, so a filter bar
        and an export href built from the filter params would describe a different set.
        """
        seed = schedule_seed(contact)
        who = as_text(contact.get("name")) or as_text(contact.get("address")) or "this contact"
        booking = JobManager().build_table(
            authority_db_file=authority_db_file, sandbox_id=sandbox,
            extra_query=extra_query,
            title=f"Book a job for {who}",
            seed_new=True, seed=seed, narrowed=False, exported=False,
            empty_text=f"No jobs booked for {who} yet — the row above books the first.",
        )
        if booking.get("error"):
            # An error ENVELOPE is not a pane: the editable table's renderer draws the
            # message and returns, so the ← bar below would never be bound and the operator
            # would be stranded on a booking form that cannot exist. Said on the contacts
            # table instead, where every other control still works.
            return {**table, "availability_note":
                    f"{who} cannot be scheduled here yet — {booking['error']}"}
        # A WAY BACK OUT, set on the built payload the way `quiar_overview` sets its own
        # truncation note. `back` is the editable table's own ← bar and it clears the params
        # it names, so leaving is the same one round trip that arriving was. Without it the
        # only exit from a booking is the browser's Back button, and the form would reopen
        # on the next transition because the param is still in the query.
        booking["back"] = {"label": "Back to contacts", "params": [SCHEDULE_PARAM]}
        return {
            "schema": self.schema,
            "container": "composite",
            "direction": "column",
            "title": "Contacts",
            "sandbox_id": sandbox,
            "panes": [
                {"label": "", "weight": 2, "tool_id": JobManager.tool_id,
                 "panel_payload": booking},
                {"label": "", "weight": 3, "panel_payload": table},
            ],
        }


register(ContactsManager())

__all__ = ["CONTACTS", "CONTACT_ARCHETYPE", "SCHEDULE_PARAM",
           "SCHEDULE_PREFILL", "ContactsManager", "client_form", "contact_rows",
           "schedule_seed", "unwritable_fields"]
