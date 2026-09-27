"""Quiar's JOBS tab — one tab for jobs, not two.

The hub carried `Jobs` and `Job` side by side until 2026-09-06. Operator, that day:
*"There are duplicate job tab."* They are not a duplicate in the code — `Jobs` is
`job_manager`'s `job_log` of `job_event` ROWS, and `Job` is `job_document_view` drawing a
`job` DOCUMENT, which is a different shape written by a different runtime. But the labels
differ by one letter, they sit next to each other, and the second one is empty until a job
document happens to be open, which no affordance on the first one leads to. Two tabs about
jobs, one of them usually blank, is a duplicate to the person reading the screen, and the
person reading the screen is right: nothing on it distinguishes them.

So they are one tab, and the operator's own specification of it (TASK-2026-08-31-003) is
already the resolution:

    "a subtab of preview cards that TOGGLES to a map view. Opening a job in either
     setting shows the SAME job profile view. One view, two indexes."

The indexes are `job_manager`'s three faces — Table, Cards, Map — which already exist. The
job profile is `job_document_view`. This module is the sentence that joins them: the log
below, and above it the job that is open, when one is.

## Why the document pane comes and goes

`job_document_view` answers a REFUSAL — a `synopsis` saying "Open a job to see it here" —
for every state that is not a job document: no store, nothing selected, or a document of
some other kind. Stacking that above the table would put a permanent instruction where a
job should be, which is the blank second tab again with extra steps.

So the pane is included only when the view actually drew A JOB — and that is a key the
writer sets (`job_document_view.HOLDS_A_JOB`), not a shape this module infers.

The first cut of this DID infer it, from `container == "composite"`, and it was wrong in
the one way that matters: a document that exists but is not a job still returns the full
composite, because `job_document_view` draws BOTH panes always so that neither appears and
disappears. Its header pane then reads "This document is not a job." — and keying on the
container stacked exactly that sentence above the job log for every non-job document open
in the shell, which is the standing refusal this merge existed to remove, restored by the
fix for it. The e2e test caught it; the payload assertion had passed.

A reader and a writer agreeing about a fact through a name the writer sets is the
difference between a contract and a coincidence.

## What this does NOT do

It does not merge the two job MODELS. A `job_event` row and a `job` document are still two
shapes mid-migration (TASK-2026-08-31-002 is p0 and additive by design). This merges the
two SURFACES, which is what was asked and all that was asked — the tab count stops lying
about how many kinds of job-viewing there are, without pretending the model question is
settled.

No new renderer and no new JavaScript: `renderComposite` paints each pane through
`paintPanelInto(pane.panel_payload, body, pane.tool_id)`, which is the same dispatch
`renderTabbed` uses for a tab. A composite pane may therefore hold another composite, and
the job profile is one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .job_document_view import HOLDS_A_JOB, JobDocumentView
from .job_manager import JobManager

_SCHEMA = "mycite.v2.portal.workbench.tool.quiar_jobs.v1"

#: No client renderer is registered under this id, which is the point: `paintPanelInto`
#: tries the tool hint first and falls through to the CONTAINER renderer when there is
#: none. So the tab paints as the composite it declares itself to be, and each pane inside
#: still dispatches on its own tool_id.
TOOL_ID = "quiar_jobs"


class JobsPane:
    """The job log, and the job document that is open above it."""

    tool_id = TOOL_ID
    label = "Jobs"

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        table = JobManager().build_panel_payload(
            authority_db_file=authority_db_file, sandbox_id=sandbox_id,
            document_id=document_id, datum_address=datum_address, extra_query=extra_query)
        profile = JobDocumentView().build_panel_payload(
            authority_db_file=authority_db_file, sandbox_id=sandbox_id,
            document_id=document_id, datum_address=datum_address, extra_query=extra_query)

        panes: list[dict[str, Any]] = []
        if profile.get(HOLDS_A_JOB):
            # Labels only when there are two panes to tell apart. A lone table under a
            # header that says "Every job" is a caption on the only thing in the room.
            panes.append({"label": "The job you opened",
                          "tool_id": JobDocumentView.tool_id, "panel_payload": profile})
            panes.append({"label": "Every job",
                          "tool_id": JobManager.tool_id, "panel_payload": table})
        else:
            panes.append({"label": "", "tool_id": JobManager.tool_id,
                          "panel_payload": table})

        return {
            "schema": _SCHEMA,
            "container": "composite",
            # The log is a wide table and the profile is a header over a list; side by
            # side, each gets half a screen and neither is readable.
            "direction": "column",
            "title": "Jobs",
            "panes": panes,
        }


__all__ = ["TOOL_ID", "JobsPane"]
