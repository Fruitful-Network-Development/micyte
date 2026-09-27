"""Job Synopsis — what the work adds up to, by trade or by month.

A DERIVATION, not a view: the job log holds one row per job and this is the question an
operator asks of the whole log — where the money came from, and whether last month was
better than the one before. Nothing here can be read off any single row, which is the line
`test_tool_registry_shape` draws between a tool that earns its registration and one that
belongs to an archetype's viewscope.

**Money stays money.** Pay is read as whole cents and summed as an integer, then formatted
once at the end. Sorting on the rendered string would put "$9.00" above "$120.00", and
re-parsing what was just formatted puts a figure through two conversions to get back where
it started — the rule `revenue_synopsis` already follows.

**A job whose pay cannot be read is COUNTED but not TOTALLED**, and the count of those is
reported. A booked job with no price yet is the ordinary case, not a defect, and silently
treating it as zero would make an honest total indistinguishable from a lossy one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.datum_ops.fiat_datum import format_cents
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from . import _node_names as nn
from ._registry import register
from ._requirements import CRM
from ._viewscope import rows_for_archetype
from .job_manager import JOB_ARCHETYPE, JOB_LOG

_SCHEMA = "mycite.v2.portal.workbench.tool.job_synopsis.v1"
_TENANT_DEFAULT = "fnd"

#: How the log can be grouped. `trade` answers "what pays"; `month` answers "when".
GROUPINGS = ("trade", "month")


def _cents(value: str) -> int | None:
    """Whole cents, or ``None`` when the cell does not carry a readable figure.

    ``None`` rather than 0, twice over. A job booked without a price yet is the ordinary
    case, and a zero would be added to a total that then reads as complete. And a cell
    that is not whole cents is UNREADABLE, not something to round: the field is declared
    as whole cents, so `185.00` is ambiguous between $1.85 and $185.00 — guessing either
    is worse than saying the job is unpriced, which the count then reports.
    """
    token = as_text(value).replace("$", "").replace(",", "")
    if not token:
        return None
    negative = token.startswith("-")
    digits = token[1:] if negative else token
    if not digits.isdigit():
        return None
    return -int(digits) if negative else int(digits)


def _month(stamp: str) -> str:
    """The grouping key for a HOPS chronological stamp.

    Grouped by the stamp's leading segments rather than by a decoded calendar month. The
    honest reason: a HOPS token decodes only against its sandbox's chronology authority,
    and a synopsis that silently fell back to string slicing when the authority was
    missing would report a different grouping than it claimed. This groups by what the
    token IS, and says so in the label.
    """
    token = as_text(stamp)
    if not token:
        return "(undated)"
    parts = token.split("-")
    return "-".join(parts[:2]) if len(parts) > 1 else token


class JobSynopsis:
    """Jobs and pay, grouped — a derivation over the whole log."""

    tool_id = "job_synopsis"
    label = "Job Synopsis"
    summary = "What the work adds up to, by trade or by period."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "synopsis"
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = CRM

    applies_to_archetype: tuple[str, ...] = (JOB_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    schema = _SCHEMA
    tenant_id = _TENANT_DEFAULT

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def empty(reason: str) -> dict[str, Any]:
            return {"schema": self.schema, "container": self.container, "items": [],
                    "item_count": 0, "title": "Jobs", "empty_text": reason}

        if authority_db_file is None:
            return empty("authority database not configured")
        sandbox = as_text(sandbox_id)
        if not sandbox:
            return empty("no sandbox selected")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        from ._viewscope import read_document

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
        document_id = store.document_id_for(
            tenant_id=self.tenant_id, sandbox=sandbox, name=JOB_LOG)
        if not document_id:
            return empty(f"{sandbox} has no job log yet")
        document = read_document(
            store, tenant_id=self.tenant_id, document_id=document_id)
        if document is None:
            return empty("the job log has no payload")

        library = store.read_documents_by_sandbox(
            tenant_id=self.tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        registry = arc.registry_for(library)
        archetype = registry.get(JOB_ARCHETYPE)
        if archetype is None:
            return empty(f"this store has no {JOB_ARCHETYPE} archetype")
        names = nn.name_index_for(
            store, tenant_id=self.tenant_id, sandbox=sandbox, registry=registry)

        grouping = as_text((extra_query or {}).get("job_group")) or GROUPINGS[0]
        if grouping not in GROUPINGS:
            return empty(f"unknown grouping {grouping!r}; expected one of {list(GROUPINGS)}")

        totals: dict[str, int] = {}
        counts: dict[str, int] = {}
        unpriced = 0
        jobs = 0
        # A SANDBOX token where a namespace is asked for, passed through unchanged — the
        # same reading `_job_rows` makes of the same log, and it has to stay the same
        # reading or the synopsis and the table would disagree about one document.
        for _record, values in rows_for_archetype(document, archetype, namespace=sandbox):
            jobs += 1
            if grouping == "trade":
                key = names.label(
                    next((v for v in values.get("lcl_id", ()) if v), ""), key_field="lcl_id")
            else:
                key = _month(next((v for v in values.get("utc", ()) if v), ""))
            counts[key] = counts.get(key, 0) + 1
            cents = _cents(next((v for v in values.get("price", ()) if v), ""))
            if cents is None:
                unpriced += 1
            else:
                totals[key] = totals.get(key, 0) + cents

        # Sorted on the INTEGER and rendered from the integer. Sorting the rendered string
        # would put "$9.00" above "$120.00".
        ranked = sorted(counts, key=lambda k: (-totals.get(k, 0), -counts[k], k))
        items = [
            {"label": f"{key} · {counts[key]} job{'' if counts[key] == 1 else 's'}",
             "figure": format_cents(totals[key]) if key in totals else "—"}
            for key in ranked
        ]
        return {
            "schema": self.schema,
            "container": self.container,
            "title": "Jobs by " + ("trade" if grouping == "trade" else "period"),
            "value_label": "paid",
            # The count is what makes a partial total legible. `unpriced` says how many
            # jobs are counted but not summed, so a total nobody can reconcile says why.
            "count_label": (
                f"{jobs} job{'' if jobs == 1 else 's'}"
                + (f" · {unpriced} unpriced" if unpriced else "")
            ),
            "items": items,
            "item_count": len(items),
            "jobs": jobs,
            "unpriced": unpriced,
            "grouping": grouping,
            "total": format_cents(sum(totals.values())) if totals else "—",
            "empty_text": "No jobs booked yet.",
        }


register(JobSynopsis())

__all__ = ["GROUPINGS", "JobSynopsis"]
