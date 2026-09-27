"""A job DOCUMENT, drawn: the header over the services it holds.

``job_document_runtime`` writes a job as a document rather than a row — one ``job`` header
carrying who it is for, where, when and what it totalled, and one ``job_service`` row per
trade. Nothing read one until this. The writer's whole justification is that the row COUNT
varies while no row's arity does, so a reader that drew only one of the two shapes would
show a five-service job as either a header with nothing under it or five trades with
nobody attached to them.

Two panes, both :func:`~._viewscope.build_viewscope_payload`, stacked: the header over the
list. The model is ``farm_profile_viewer``, which composes an identity viewscope beside a
derived map for the same reason — a document that is several things at once is drawn by
NAMING each of them, not by adding a renderer that knows about jobs. No JavaScript: the
``composite``, ``viewscope_slot_grid`` and ``viewscope_record_line`` containers all have
client renderers already.

Not a registered tool. It is Quiar's ``Job`` tab (see :data:`~.quiar.TABS`) — one entry,
against the six shared files plus a live config key a registration costs — and it derives
nothing: both panes are the document's own stored values through the archetypes that
already describe them, which is the state ``test_every_registered_tool_writes_or_derives``
exists to keep out of the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._shared.utilities import as_text as _as_text
from ._viewscope import build_viewscope_payload

_SCHEMA = "mycite.v2.portal.workbench.tool.job_document.v1"
_TENANT_DEFAULT = "fnd"

#: The two archetypes a job document's rows carry, and the ONE thing in this module that
#: is a second copy of something. The writer names them too
#: (``job_document_runtime.JOB_HEADER_ARCHETYPE`` / ``JOB_SERVICE_ARCHETYPE``) and cannot
#: be imported from here: ``micyte`` is the published package and
#: ``test_micyte_fnd_boundary`` asserts ZERO edges from ``micyte.tools`` into ``fnd_app``,
#: transitively. So the agreement is pinned by a test that may import both
#: (``test_a_job_document_draws_as_its_two_archetypes``) rather than by an import — a
#: reader naming a shape the writer does not produce draws an empty pane and reports
#: nothing wrong with it.
JOB_HEADER_ARCHETYPE = "job"
JOB_SERVICE_ARCHETYPE = "job_service"

#: The container this view emits when it ACTUALLY DREW a job — as opposed to the
#: ``synopsis`` refusal it emits for every state that is not a job document. Named here,
#: on the writer's side, because :mod:`._quiar_jobs_pane` decides whether to stack this
#: above the job log, and a reader matching a string literal against a writer's shape is a
#: coincidence that holds until the shape moves.
DRAWN_CONTAINER = "composite"

#: The container a pane that did NOT draw carries — see :func:`_synopsis`.
REFUSAL_CONTAINER = "synopsis"

#: THE KEY THAT ANSWERS "IS THIS A JOB", and the reason it exists rather than the reader
#: inferring it. ``container`` cannot answer: a document that EXISTS but is not a job still
#: gets the full composite, because BOTH panes are always drawn (see below) and one of them
#: is then the sentence "This document is not a job." A reader keying on the container
#: therefore stacked that sentence above the job log for every non-job document open in the
#: shell — which is precisely the standing refusal the tab merge existed to remove.
#:
#: So the writer states it. Pinned by ``test_the_reader_and_the_writer_agree_about_a_job``.
HOLDS_A_JOB = "holds_a_job"


def _synopsis(title: str, text: str) -> dict[str, Any]:
    """An honest sentence that actually PAINTS.

    ``build_viewscope_payload`` says no by returning ``container: ""`` with a ``reason``,
    and no client renderer is registered under the empty key: ``paintPanelInto`` falls
    through ``__MYCITE_V2_TOOL_RENDERERS`` and ``__MYCITE_V2_CONTAINER_RENDERERS`` (which
    hold ``viewscope_slot_grid`` / ``_record_line`` / ``_tree`` / ``_glyph_canvas``, and
    nothing for ``""``) to "No renderer for ``<code></code>``". A refusal handed straight
    to a pane therefore reads as a broken pane. ``synopsis`` is an existing container
    whose ``empty_text`` is exactly this sentence, so a refusal draws as a refusal and
    this adds no JavaScript.
    """
    return {"schema": _SCHEMA, "container": REFUSAL_CONTAINER, "title": title,
            "items": [], "empty_text": text}


class JobDocumentView:
    """One job document: its header, and every service booked on it."""

    tool_id = "job_document"
    label = "Job"
    summary = "One job: who it is for and when, over each service booked on it."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = DRAWN_CONTAINER
    applies_to_archetype: tuple[str, ...] = (JOB_HEADER_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
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
        # `datum_address` is accepted and dropped: no viewscope container renderer reads a
        # selected row, so carrying one would be a key nothing consumes. `extra_query` is
        # accepted because `quiar.build_panel_payload` hands it to every tab's tool
        # unconditionally, not because anything here reads a query param.
        del datum_address, extra_query
        if authority_db_file is None:
            return _synopsis(self.label, "This instance's records are not available yet.")
        target = _as_text(document_id)
        if not target:
            # A viewscope is ABOUT a selection, and resolving "some job in this sandbox"
            # would draw a job nobody chose — the empty-render failure `viewscope_view`
            # refuses for the same reason. Say what is needed; an empty grid here would
            # read as a job that has no services, which is a different fact.
            return _synopsis(
                self.label,
                "Open a job to see it here — what it is for and when, over each "
                "service booked on it.")

        # BOTH ARCHETYPES ARE NAMED, and that is the load-bearing line in this file.
        # `build_viewscope_payload` otherwise falls back to `registry.primary_archetype`,
        # which is the archetype of the document's most numerous SUBSTANTIVE row — and a
        # job document is 1 header + N services. For N >= 2 the services win outright, so
        # the document plainly opened draws the trades and never the job; for N == 1 it is
        # a 1-1 tie broken by `Counter.most_common` iteration order, which is worse
        # because it looks decided. `document_metadata["archetype"]` does not rescue it
        # either — the writer does set it to `job`, but the reader consults it only when
        # NOTHING matched (_viewscope.py:455-467), and here both shapes match.
        #
        # The cost is that the archetype library is read twice per render: 34 documents,
        # well under a megabyte through `read_documents_by_sandbox` (which exists because
        # the catalog read costs ~350 MB to look at 0.3% of the store). That is the price
        # of naming both archetypes, and the same price `farm_profile_viewer` pays for its
        # identity pane.
        header = self._pane(
            authority_db_file, target, JOB_HEADER_ARCHETYPE,
            title=self.label, refusal="This document is not a job.")
        # The header keeps its GRID. `_viewscope.py:503-506` promotes a `slot_grid` to a
        # `record_line` when more than one row matched — a document holding 53
        # jurisdictions is a directory of them rather than one subject — and with `job`
        # named exactly one row matches, so the promotion cannot fire and a job is drawn
        # as the single thing it is. The services need no such care: `job_service` classes
        # under `record`, whose container is already `record_line`, so a job with one
        # service and a job with five draw as the same list.
        services = self._pane(
            authority_db_file, target, JOB_SERVICE_ARCHETYPE,
            title="Services", refusal="No services are recorded on it.")
        # BOTH PANES ALWAYS, even when one of them is only a sentence. Collapsing to a
        # single refusal when the header does not draw would make the Services region
        # appear and disappear with the document, and a region that vanishes teaches
        # nothing about why. "on it" rather than "on this job" for the same reason: the
        # sentence has to stay true beside a header that has just said this document is
        # not a job.
        return {
            "schema": _SCHEMA,
            "container": DRAWN_CONTAINER,
            # Whether the HEADER resolved — the services pane is not consulted, because a
            # job booked with no service rows yet is still a job.
            HOLDS_A_JOB: _as_text(header.get("container")) != REFUSAL_CONTAINER,
            # Stacked, not side by side: the header is the caption for the list under it.
            # A two-column split would set a four-field grid beside a table and give each
            # of them half a pane.
            "direction": "column",
            "title": self.label,
            "sandbox_id": _as_text(sandbox_id),
            "document_id": target,
            "panes": [
                {"tool_id": "viewscope", "label": self.label, "panel_payload": header},
                {"tool_id": "viewscope", "label": "Services", "panel_payload": services},
            ],
        }

    def _pane(
        self, authority_db_file: Path | None, document_id: str, archetype: str, *,
        title: str, refusal: str,
    ) -> dict[str, Any]:
        """One archetype of one document, or a sentence saying why it did not draw."""
        payload = build_viewscope_payload(
            authority_db_file=Path(authority_db_file) if authority_db_file else None,
            tenant_id=self.tenant_id,
            document_id=document_id,
            archetype=archetype,
        )
        if _as_text(payload.get("container")):
            return payload
        # The one refusal this pane can phrase for whoever is reading it is "the document
        # holds no rows of this shape" — for the services pane that is the writer's own
        # refusal ("a job document holding none cannot be told apart from one written
        # before services were recorded") seen from the reading side. The primitive marks
        # exactly that case by carrying an `archetypes` key (the shapes it DID find) beside
        # the reason; both refusals that carry it — "this document has no 'job' rows" and
        # "no archetype matches this document's rows" — say the same thing to a reader.
        # Keyed on the key rather than on the sentence, and
        # `test_a_document_that_is_not_a_job_says_so_in_the_readers_words` drives the real
        # primitive to this branch, so renaming it fails a test instead of silently
        # reverting this pane to the primitive's own wording.
        #
        # Every other reason — an id that is not canonical, a store with no archetype
        # library — is about the STORE rather than about this job, and is passed through
        # in the words the primitive already chose rather than guessed at a second time.
        if "archetypes" in payload:
            return _synopsis(title, refusal)
        return _synopsis(title, _as_text(payload.get("reason")) or refusal)


__all__ = ["JOB_HEADER_ARCHETYPE", "JOB_SERVICE_ARCHETYPE", "JobDocumentView"]
