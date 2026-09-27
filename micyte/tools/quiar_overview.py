"""Overview — what the books say, and what is coming.

    ┌─ Overview ──────────────────────────────────────────┐
    │  THE BOOKS          THIS MONTH                      │
    │  paid   $4,310.00   paid       $780.00              │
    │  booked        43   booked           7              │
    │  average  $107.75   still to come    3              │
    ├─────────────────────────────────────────────────────┤
    │  UPCOMING WORK              [ + Book a job ]        │
    │  (new) │ customer │ address │ trade │ when │ pay    │
    └─────────────────────────────────────────────────────┘

Three panes, and the third one is the point. The operator asked for "a job creation form
field" on the home page, and this does not build one: it embeds ``job_manager``'s own table
with its create row already open. The form that appears is the real form, posting the real
route, owned by the tool that declares the write — and inline editing of the upcoming rows
comes with it, unbought.

A second booking form would have been a second write surface for one action.
``_write_owners`` RAISES on a second declaration of ``save_job`` precisely so that cannot
happen quietly, and the composite pattern the ERP is already assembled from exists so it
never has to.

## What the figures are, and what they are not

**Money stays money.** Cents are summed as integers and formatted once at the end —
:mod:`job_synopsis`'s rule, imported rather than restated. A job whose pay cannot be read is
COUNTED but not TOTALLED, and the count of those is reported, because a booked job with no
price yet is the ordinary case and silently treating it as zero would make an honest total
indistinguishable from a lossy one.

**"This month" is a calendar month**, resolved through the sandbox's own chronology
authority. ``job_synopsis`` groups by the HOPS token's leading segments and says so in its
label, for the honest reason that it holds no clock to decode them with. This tool reads the
anchor, so it can answer the question the operator actually asked — and when the anchor
carries no chronological row it says the month is unreadable rather than grouping by
something that is not a month.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.datum_ops.fiat_datum import format_cents
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._hops_dates import chrono_authority, hops_token_to_date
from ._registry import register
from ._requirements import CRM
from ._viewscope import _row_values, read_document
from .job_manager import JOB_ARCHETYPE, JOB_LOG, JobManager
from .job_synopsis import _cents

TOOL_ID = "quiar_overview"
_SCHEMA = "mycite.v2.portal.workbench.tool.quiar_overview.v1"
_SYNOPSIS_SCHEMA = "mycite.v2.portal.workbench.tool.quiar_overview.figures.v1"
_TENANT_DEFAULT = "fnd"

#: How many upcoming jobs the pane lists. A home page answers "what is next", not "what is
#: everything" — the Jobs tab is one click away and holds the whole log, narrowable.
UPCOMING_LIMIT = 12


def _figure(label: str, figure: str) -> dict[str, str]:
    return {"label": label, "figure": figure}


def _synopsis(title: str, items: list[dict[str, str]], *, count_label: str = "",
              value_label: str = "", empty_text: str = "Nothing yet.") -> dict[str, Any]:
    """A figures widget, in the ``synopsis`` container the PLAN tab already renders.

    Reused rather than given a container of its own: label-and-figure is exactly what this
    is, and a second renderer for the same shape is the thing this codebase keeps paying for.
    """
    return {
        "schema": _SYNOPSIS_SCHEMA,
        "container": "synopsis",
        "title": title,
        "items": items,
        "item_count": len(items),
        "count_label": count_label,
        "value_label": value_label,
        "empty_text": empty_text,
    }


def job_figures(
    store: Any, *, tenant_id: str, sandbox: str, today: date,
) -> dict[str, Any]:
    """Every figure the overview reports, from one pass over the job log.

    ``month_readable`` is False when the sandbox's anchor carries no HOPS-chronological row.
    The all-time figures are still true in that case — they need no clock — so they are
    reported and only the month is withheld, with the reason. Withholding both would hide a
    total that is perfectly readable behind a date that is not.
    """
    log_id = store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name=JOB_LOG)
    # The anchor by its FLAG, through the shared lookup: `anchor` here, `anthology` in a
    # system sandbox, and this asked for the literal name.
    anchor_id = store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name="anchor")
    log = {"document_id": log_id} if log_id else None
    anchor = {"document_id": anchor_id} if anchor_id else None
    if log is None:
        return {"error": f"{sandbox} has no job log yet — onboarding creates one"}

    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    archetype = registry.get(JOB_ARCHETYPE)
    if archetype is None:
        return {"error": f"this store has no {JOB_ARCHETYPE} archetype"}
    document = read_document(store, tenant_id=tenant_id, document_id=log["document_id"])
    if document is None:
        return {"error": "the job log has no payload"}

    authority = None
    if anchor is not None:
        authority = chrono_authority(
            read_document(store, tenant_id=tenant_id, document_id=anchor["document_id"]))

    total_cents = 0
    jobs = priced = unpriced = 0
    month_cents = 0
    month_jobs = month_priced = 0
    ahead = 0
    undated = 0
    for record in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(record.raw, sandbox=sandbox)
        if not archetype.covers(shape):
            continue
        jobs += 1
        values = _row_values(ash._row_head(record.raw), namespace=sandbox)
        cents = _cents(next((v for v in values.get("price", ()) if v), ""))
        if cents is None:
            unpriced += 1
        else:
            priced += 1
            total_cents += cents

        stamps = [v for v in values.get("utc", ()) if v]
        day = hops_token_to_date(authority, stamps[0]) if (authority and stamps) else None
        if day is None:
            undated += 1
            continue
        if day.year == today.year and day.month == today.month:
            month_jobs += 1
            if cents is not None:
                month_priced += 1
                month_cents += cents
        if day >= today:
            ahead += 1

    # Averaged over the jobs that HAVE a price, not over every job. Dividing a partial total
    # by a full count reports an average lower than any job in the book, which is a figure
    # nobody can reconcile against the rows they are looking at.
    average = format_cents(round(total_cents / priced)) if priced else "—"
    return {
        "jobs": jobs,
        "priced": priced,
        "unpriced": unpriced,
        "undated": undated,
        "total": format_cents(total_cents) if priced else "—",
        "average": average,
        "month_jobs": month_jobs,
        "month_total": format_cents(month_cents) if month_priced else "—",
        "upcoming": ahead,
        "month_readable": authority is not None,
        "month_label": today.strftime("%B %Y"),
    }


class QuiarOverview:
    """The instance's books at a glance, and the next job's form already open."""

    tool_id = TOOL_ID
    label = "Overview"
    summary = (
        "What the work adds up to, what this month has done, and what is coming — with the "
        "booking form already open on the upcoming list."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "composite"
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = CRM
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT
    icon = "quiar"
    # No `writes`. The upcoming pane IS `job_manager`'s table, posting `job_manager`'s route;
    # declaring `save_job` here would be a second owner of one action and `_write_owners`
    # raises on exactly that.

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del document_id
        if authority_db_file is None:
            return {"schema": self.schema, "container": self.container, "panes": [],
                    "error": "authority database not configured"}
        sandbox = as_text(sandbox_id)
        if not sandbox:
            return {"schema": self.schema, "container": self.container, "panes": [],
                    "error": "no sandbox selected"}

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        today = date.today()
        figures = job_figures(
            store, tenant_id=self.tenant_id, sandbox=sandbox, today=today)
        if figures.get("error"):
            return {"schema": self.schema, "container": self.container, "panes": [],
                    "error": figures["error"]}

        books = _synopsis(
            "The books",
            [
                _figure("paid", figures["total"]),
                _figure("jobs booked", str(figures["jobs"])),
                _figure("average per job", figures["average"]),
            ],
            value_label="all time",
            count_label=(
                f"{figures['unpriced']} unpriced" if figures["unpriced"] else "every job priced"
            ),
        )
        if figures["month_readable"]:
            month = _synopsis(
                figures["month_label"],
                [
                    _figure("paid", figures["month_total"]),
                    _figure("jobs booked", str(figures["month_jobs"])),
                    _figure("still to come", str(figures["upcoming"])),
                ],
                value_label="this month",
                count_label=(
                    f"{figures['undated']} undated" if figures["undated"] else "every job dated"
                ),
            )
        else:
            # Named, not blank. An anchor with no chronological row makes every date in the
            # log unreadable, and a month pane showing three dashes looks like a quiet month.
            month = _synopsis(
                "This month", [],
                empty_text=(
                    f"{sandbox}'s anchor has no HOPS-chronological row, so its dates cannot "
                    "be read — the all-time figures beside this need no clock and are exact."
                ),
            )

        upcoming = JobManager().build_table(
            authority_db_file=authority_db_file,
            sandbox_id=sandbox,
            datum_address=as_text(datum_address),
            extra_query=extra_query,
            title="Upcoming work",
            date_from=today.isoformat(),
            # The create row, open. This is the "job creation form field" — job_manager's
            # own, not a copy of it.
            seed_new=True,
            # No filter bar and no export here: these rows are already cut by `date_from`,
            # which is not one of the filter params, so an export href built from those
            # params would take the WHOLE log while the screen showed the next twelve jobs.
            narrowed=False,
            exported=False,
            empty_text="Nothing booked from today onward — the row above books the next one.",
        )
        rows = upcoming.get("rows")
        if isinstance(rows, list) and len(rows) > UPCOMING_LIMIT:
            upcoming["truncated_to"] = UPCOMING_LIMIT
            upcoming["rows"] = rows[:UPCOMING_LIMIT]
            upcoming["row_count"] = UPCOMING_LIMIT
            upcoming["availability_note"] = (
                f"The next {UPCOMING_LIMIT} of {len(rows)} jobs from today onward. The Jobs "
                "tab holds the whole log, and can be narrowed."
            )

        return {
            "schema": self.schema,
            "container": self.container,
            "direction": "column",
            "title": "Overview",
            "sandbox_id": sandbox,
            "panes": [
                {
                    "label": "",
                    "weight": 1,
                    "panel_payload": {
                        "schema": self.schema,
                        "container": "composite",
                        "widgets": True,
                        "panes": [
                            {"label": "", "panel_payload": books},
                            {"label": "", "panel_payload": month},
                        ],
                    },
                },
                {"label": "", "weight": 3, "tool_id": JobManager.tool_id,
                 "panel_payload": upcoming},
            ],
        }


register(QuiarOverview())

__all__ = ["UPCOMING_LIMIT", "QuiarOverview", "job_figures"]
