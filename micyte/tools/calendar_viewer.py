"""Calendar — every dated thing an instance holds, on one schedule.

``agro_calendar`` reads ``network_map_viewer.SOURCE_SANDBOX``, a module CONSTANT naming the
registrar. That is right for the network's own schedule and wrong for everything else: a
handyman instance opening the calendar saw nothing at all, because its jobs are not in the
registrar and nothing else was looked at.

This is the general one. Its sources are resolved from the sandbox rather than named in
code, and Phase 1's class layer is what makes that expressible: **every document whose
archetype classes under ``log``** is a log, so a job log, an event log, an invoice and a
market log are all the same question. A sandbox that grows a new kind of log gets it on the
calendar with no code — which is the property the archetype program exists for.

## Two kinds of when, kept apart

A ``job_event`` carries a ``utc``: a HOPS-chronological token naming ONE MOMENT. It appears
on its day.

A registrar ``event_log_entry`` carries an ``ic_stamp``: a CADENCE — a weekday and an hour
that recurs, with ``tiu_magnitude`` minutes of duration. It appears on every matching day.

They are different shapes and this module does not flatten them into one. An event that
recurs and an appointment that happens are not the same fact, and a calendar that renders
one as the other is lying about a farm's opening hours or about when somebody's driveway
gets washed. The network's cadence rendering already exists and is reached through
``agro_calendar``; nothing here reinterprets it.

## What it deliberately does not hold

Planting windows and contract spans OCCUPY time rather than recurring or happening, and the
operator ruled them out on 2026-07-29. They are named in the payload rather than silently
absent, because a calendar that omits a source looks broken rather than scoped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_class as ac
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _node_names as nn
from ._hops_dates import chrono_authority, hops_token_to_datetime
from ._registry import register
from ._requirements import ANY_LOG
from ._viewscope import _row_values, read_document

TOOL_ID = "calendar"
CONTAINER = "calendar"
_SCHEMA = "mycite.v2.portal.workbench.tool.calendar.v1"
_TENANT_DEFAULT = "fnd"

#: The class every source of this calendar sits under. Not a list of document names: a
#: sandbox names its own documents, and `job_log` here is `work_log` in the next instance.
LOG_CLASS = "log"

#: How many events are built before the calendar stops. A month grid is a view; 44,316
#: market observations are not, and the market logs class under `log` exactly like the
#: three-row job log does.
MAX_EVENTS = 2000

#: Named in the payload rather than silently absent — the operator's 2026-07-29 ruling.
EXCLUDED_SOURCES: tuple[dict[str, str], ...] = (
    {"source": "planting windows", "surface": "the PLAN tab's planting calendar"},
    {"source": "contract spans", "surface": "the Contracts tool"},
)


def _notice(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": CONTAINER, "notice": message,
            "events": [], "sources": [], "excluded": [dict(x) for x in EXCLUDED_SOURCES]}


#: The field a row must declare to be datable HERE. `ic_stamp` is deliberately absent: it
#: is a CADENCE (a weekday and an hour that recurs), which this calendar does not flatten
#: into a moment — see the module docstring.
TIME_FIELD = "utc"


def log_documents(store: Any, *, tenant_id: str, sandbox: str) -> dict[str, str]:
    """``document name -> archetype``, for every document in ``sandbox`` that is a LOG
    **and whose archetype declares a time field**.

    Read by CLASS, so this needs no list of document names and no per-instance
    configuration. A document whose rows match nothing, or whose archetype classes
    elsewhere, is simply not a source.

    The second half of that condition is not a nicety. A `sources` manifest classes under
    `network_log` and carries no `utc` at all, so without it the calendar reported
    a farm's lcl as 471 UNDATED rows — a coverage note about a document that could
    never have produced an event, which reads as a fault where there is none. Asking the
    ARCHETYPE what fields it declares answers this before a single row is read.
    """
    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    classes, _problems = ac.load_classes(library)

    shapes: dict[str, Any] = {}
    for _document_id, name, raw in store.iter_document_rows_by_sandbox(
        tenant_id=tenant_id, sandbox=sandbox
    ):
        counts = shapes.setdefault(name, {})
        shape = ash.row_shape(raw, sandbox=sandbox)
        counts[shape] = counts.get(shape, 0) + 1

    out: dict[str, str] = {}
    for name, counts in shapes.items():
        from collections import Counter

        archetype_name = registry.primary_archetype_of(Counter(counts))
        if not archetype_name:
            continue
        if LOG_CLASS not in classes.lineage_of(archetype_name):
            continue
        archetype = registry.get(archetype_name)
        if archetype is None or TIME_FIELD not in archetype.declared_fields:
            continue
        out[name] = archetype_name
    return out


def build_calendar_payload(
    store: Any, *, tenant_id: str, sandbox: str, names: Any = None
) -> dict[str, Any]:
    """Every dated row in the sandbox's log documents, as one list of events."""
    if not sandbox:
        return _notice("no sandbox in focus, so there is nothing to schedule")

    sources = log_documents(store, tenant_id=tenant_id, sandbox=sandbox)
    if not sources:
        return _notice(f"{sandbox} holds no log documents yet")

    with_ids: dict[str, str] = {}
    for name in sources:
        found = store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name=name)
        if found:
            with_ids[name] = found
    # The anchor by FLAG, not by the literal name `anchor`: in a system sandbox it is called
    # `anthology`, and asking for the name found nothing — so every instance's calendar
    # reported "no HOPS-chronological row" and showed an empty month with a fault message.
    anchor_id = store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name="anchor")

    # The clock is the SANDBOX's own, resolved by label. Without it a token cannot become a
    # day, and the calendar says so rather than showing an empty month.
    authority = None
    if anchor_id:
        authority = chrono_authority(
            read_document(store, tenant_id=tenant_id, document_id=anchor_id)
        )
    if authority is None:
        return _notice(
            f"{sandbox}'s anchor has no HOPS-chronological row, so its dates cannot be read"
        )

    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    if names is None:
        names = nn.name_index_for(store, tenant_id=tenant_id, sandbox=sandbox, registry=registry)

    events: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    truncated = False
    for name, archetype_name in sorted(sources.items()):
        document_id = with_ids.get(name)
        if not document_id:
            continue
        archetype = registry.get(archetype_name)
        document = read_document(store, tenant_id=tenant_id, document_id=document_id)
        dated = undated = 0
        for row in getattr(document, "rows", ()) or ():
            shape = ash.row_shape(row.raw, sandbox=sandbox)
            if archetype is None or not archetype.covers(shape):
                continue
            values = _row_values(ash._row_head(row.raw), namespace=sandbox)
            stamps = [v for v in values.get("utc", ()) if v]
            moment = hops_token_to_datetime(authority, stamps[0]) if stamps else None
            if moment is None:
                # An undated row is COUNTED, not dropped. Before the write path encoded
                # dates, every job row was one of these — and an empty calendar looked like
                # "no work booked" rather than "nothing here can be read".
                undated += 1
                continue
            if len(events) >= MAX_EVENTS:
                truncated = True
                break
            ends = hops_token_to_datetime(authority, stamps[1]) if len(stamps) > 1 else None
            events.append({
                "document": name,
                "archetype": archetype_name,
                "datum_address": row.datum_address,
                "starts": moment.isoformat(),
                "ends": ends.isoformat() if ends else "",
                "day": moment.date().isoformat(),
                "title": decode_label(next((v for v in values.get("title", ()) if v), "")),
                "who": names.label(
                    next((v for v in values.get("msn_id", ()) if v), ""), key_field="msn_id"),
                "where": names.label(
                    next((v for v in values.get("site_msn", ()) if v), ""), key_field="msn_id"),
                "kind": names.label(
                    next((v for v in values.get("lcl_id", ()) if v), ""), key_field="lcl_id"),
                "price": next((v for v in values.get("price", ()) if v), ""),
            })
            dated += 1
        coverage.append({"document": name, "archetype": archetype_name,
                         "dated": dated, "undated": undated})

    events.sort(key=lambda e: e["starts"])
    return {
        "schema": _SCHEMA,
        "container": CONTAINER,
        "sandbox_id": sandbox,
        "title": "Calendar",
        "events": events,
        "event_count": len(events),
        # Which documents were read and what came back, so "3 events" is checkable rather
        # than taken on trust — and so a log full of rows nothing could date SAYS so.
        "sources": coverage,
        "undated": sum(c["undated"] for c in coverage),
        "truncated": truncated,
        "max_events": MAX_EVENTS,
        "excluded": [dict(x) for x in EXCLUDED_SOURCES],
        "ics_route": "/portal/api/v2/calendar/event.ics",
    }


#: How many rows a NON-ACTIVE sandbox may hold before the instance merge skips it. The
#: cost of a calendar is the shape fold over every row the sandbox holds — measured on the
#: live store: agnet's market logs fold in 8.4s while `system`'s six documents fold in
#: 0.01s — and a merge that included agnet unconditionally made every OTHER sandbox's
#: calendar cost agnet's price. The active sandbox is never skipped (the operator asked
#: for it); a skipped one is NAMED in the notes and keeps its chip, because silently
#: absent reads as "nothing scheduled there".
MERGE_ROW_BUDGET = 20_000


def _sandbox_row_count(store: Any, *, tenant_id: str, sandbox: str) -> int | None:
    """Total datum rows the sandbox holds, or ``None`` when the store cannot answer.

    One indexed count — cheap where the fold is not. ``None`` (an adapter without the
    SQL seam, as in unit stubs) is treated as WITHIN budget: not knowing a sandbox is
    heavy is not knowing, and skipping on ignorance would hide small sandboxes too.
    """
    connect = getattr(store, "_connect", None)
    if connect is None:
        return None
    # Per DOCUMENT, not one JOIN: the joined COUNT planned as a full covering-index scan
    # of every row the store holds — measured 4.3s per sandbox through the adapter, three
    # times, which made the guard cost more than the fold it guards against. A document-id
    # equality seeks the index; a sandbox's documents are a short list.
    with connect() as connection:
        docs = [
            row["document_id"] for row in connection.execute(
                "SELECT document_id FROM documents WHERE tenant_id = ? AND sandbox = ?",
                (tenant_id, sandbox),
            )
        ]
        total = 0
        for document_id in docs:
            # tenant_id INCLUDED although the document_id alone identifies the rows: the
            # index is (tenant_id, document_id), and without its leading column the plan
            # degrades to a full index SCAN — measured 0.022s per document against 0.000s
            # for the SEARCH this form gets.
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM datum_row_semantics "
                "WHERE tenant_id = ? AND document_id = ?",
                (tenant_id, document_id),
            ).fetchone()
            total += int(row["n"]) if row else 0
    return total


def build_instance_calendar_payload(
    store: Any, *, tenant_id: str, sandboxes: Any, active_sandbox: str = ""
) -> dict[str, Any]:
    """The whole instance's schedule: every sandbox's dated rows, merged and TAGGED.

    Composed from :func:`build_calendar_payload` per sandbox — one primitive, so the
    instance view and a pinned single-sandbox tab cannot disagree about what a sandbox's
    events are (the drift test in `test_quiar_hub` holds them to it). Each event and each
    coverage row carries its ``sandbox``; the renderer's toggles are client-side chips
    over that tag, exactly like its existing per-document filter — the events already
    ship in the payload, so a toggle is a view decision, not a second request.

    A sandbox whose payload is a NOTICE (no logs, no clock) contributes a note instead of
    events — named rather than dropped, because a sandbox silently absent from its own
    instance's calendar looks like an empty week rather than an unreadable one.
    """
    names = [as_text(s) for s in (sandboxes or ()) if as_text(s)]
    if not names:
        return _notice("this instance has no sandboxes to schedule")

    events: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    notes: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    truncated = False
    for sandbox in names:
        if sandbox != as_text(active_sandbox):
            count = _sandbox_row_count(store, tenant_id=tenant_id, sandbox=sandbox)
            if count is not None and count > MERGE_ROW_BUDGET:
                notes.append({
                    "sandbox": sandbox,
                    "note": (
                        f"{sandbox} holds {count:,} rows — more than this merge reads "
                        f"({MERGE_ROW_BUDGET:,}). Open its own calendar to see it."
                    ),
                })
                counts[sandbox] = 0
                continue
        payload = build_calendar_payload(store, tenant_id=tenant_id, sandbox=sandbox)
        if payload.get("notice"):
            notes.append({"sandbox": sandbox, "note": as_text(payload["notice"])})
            counts[sandbox] = 0
            continue
        tagged = [{**event, "sandbox": sandbox} for event in payload.get("events", ())]
        counts[sandbox] = len(tagged)
        for event in tagged:
            if len(events) >= MAX_EVENTS:
                truncated = True
                break
            events.append(event)
        coverage.extend(
            {**row, "sandbox": sandbox} for row in payload.get("sources", ()))
        truncated = truncated or bool(payload.get("truncated"))

    events.sort(key=lambda e: e["starts"])
    return {
        "schema": _SCHEMA,
        "container": CONTAINER,
        "sandbox_id": as_text(active_sandbox) or (names[0] if names else ""),
        "title": "Calendar",
        "events": events,
        "event_count": len(events),
        "sources": coverage,
        "undated": sum(int(c.get("undated") or 0) for c in coverage),
        "truncated": truncated,
        "max_events": MAX_EVENTS,
        "excluded": [dict(x) for x in EXCLUDED_SOURCES],
        "ics_route": "/portal/api/v2/calendar/event.ics",
        # The toggle chips' data: every sandbox asked, with what it contributed — including
        # the zeros, because a chip absent for an empty sandbox is indistinguishable from a
        # sandbox the calendar never read.
        "sandboxes": [{"id": s, "event_count": counts.get(s, 0)} for s in names],
        "sandbox_notes": notes,
    }


class CalendarViewer:
    """This instance's own schedule, read by CLASS rather than from a named document.

    Two declarations over one primitive (the scoped-feature rule): the REGISTERED
    instance is unpinned and reads the whole instance — every sandbox sharing the active
    msn, with client-side toggle chips. A hub embedding this as a tab constructs
    ``CalendarViewer(pinned=True)``, which is the same builder held to the active sandbox
    with no toggles — what the Quiar manifest's ``ScopedFeature("calendar",
    "app_sandbox")`` declares.
    """

    tool_id = TOOL_ID
    label = "Calendar"
    # UI copy: the rail hover, one sentence. The discovery rule (sources are
    # whatever classes under `log`, so a new kind of log needs no code) and the
    # moment-vs-cadence rule stay here in the code, not in a tooltip.
    summary = "Everything dated in your logs — jobs, events, invoices — on one schedule."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = CONTAINER
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: is empty so it follows the instance switcher — unlike `agro_calendar`, whose source is
    #: a constant, this one genuinely answers a different question in a different sandbox.
    #: Scoped to instances that keep dated records — see tools/_requirements. Declaring
    #: nothing made the instance gate trivially true, so this sat on every rail: on a farm
    #: with nothing to draw, and on the registrar beside `agro_calendar`, which is exactly
    #: the pair of Calendars scoping was introduced to separate.
    requires = ANY_LOG
    icon = "calendar"

    def __init__(self, *, pinned: bool = False) -> None:
        #: Pinned = the active sandbox only, no toggles — the app-tab declaration.
        self.pinned = bool(pinned)

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id, datum_address, extra_query
        if authority_db_file is None:
            return _notice("authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            return _notice("no sandbox selected")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        if self.pinned:
            return build_calendar_payload(store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox)
        from micyte.core.instance_scope import use_instance

        from ._sandboxes import instance_msn_and_sandboxes

        msn, sandboxes = instance_msn_and_sandboxes(
            store, tenant_id=_TENANT_DEFAULT, active_sandbox=sandbox)
        if len(sandboxes) <= 1:
            # One sandbox is one sandbox: the merged shape would only add a single
            # always-on chip, which is a control that cannot do anything.
            return build_calendar_payload(store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox)
        if not msn:
            # No scope and no unique holder: merging by bare NAMES would read `system`
            # across four instances or raise mid-merge. The active sandbox alone is the
            # honest answer.
            return build_calendar_payload(store, tenant_id=_TENANT_DEFAULT, sandbox=sandbox)
        # Re-entered even when the request already carries it (harmless): the names the
        # merge iterates include `system`, and a bare-name read outside the scope RAISES.
        with use_instance(msn):
            return build_instance_calendar_payload(
                store, tenant_id=_TENANT_DEFAULT, sandboxes=sandboxes,
                active_sandbox=sandbox)


register(CalendarViewer())

__all__ = ["EXCLUDED_SOURCES", "LOG_CLASS", "MAX_EVENTS", "TIME_FIELD", "CalendarViewer",
           "build_calendar_payload", "build_instance_calendar_payload", "log_documents"]
