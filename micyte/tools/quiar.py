"""Quiar — the generalized CRM hub: the domain, the work, the people and the week.

    ┌─ Quiar ─[ DOMAIN ][ JOBS ][ CLIENTS ][ CANVASSING ][ CALENDAR ]─┐
    │  write what you know · book work and read one · keep people ·   │
    │           knock doors · see when                                │
    └─────────────────────────────────────────────────────────────────┘

**The domain is the first** (operator, 2026-08-19). It was five tabs. Overview
was a synopsis of tabs a click away, which is a third statement of facts two surfaces
already make; Projects grouped jobs into standing things, which the instance's own local
domain already does — a project is a node, and now a node can hold the document that says
what the project IS. Both folded into the Domain tab. `quiar_overview` and `project_manager`
stay REGISTERED tools and stay in the package manifest: the tabs went, the capability did
not.

## The JOB tab was a fifth tab for one day short of a week (2026-09-02 → 2026-09-06)

It was added because it said something no other tab could: JOBS is the `job_log`, a list of
`job_event` rows each holding exactly one `lcl_id`, while a JOB DOCUMENT is a different
shape — one `job` header over N `job_service` rows, written by `job_document_runtime`
because 17 of BPW's 57 pre-datum job leaflets carry two or three services each. Nothing
read one until that tab, and it is still the only surface on which a multi-service job is
legible at all.

All of that was true and none of it survived contact. Operator, 2026-09-06: *"There are
duplicate job tab."* `Jobs` and `Job` differ by one letter, sit next to each other, and the
second is a refusal — "Open a job to see it here" — until a job document happens to be
open, which nothing on the first one leads to. The distinction was real in the code and
invisible on the screen, and the screen is what an operator has.

So the capability stayed and the tab went, which is the same trade Overview and Projects
took: `_quiar_jobs_pane.JobsPane` stacks `job_document_view` ABOVE `job_manager` when a job
is open and renders the log alone when none is. `job_document_view` is untouched. See that
module's docstring for why the profile pane comes and goes rather than sitting there
saying "open a job".

A composite, not a new renderer: each tab is another tool's ``panel_payload``, carried under
the ``container:"tabbed"`` wrapper ``agronomics_viewer`` established. That is the seam — a
tab is a DECLARATION of a pane, so the CRM can be rearranged, or another vertical assembled
from the same parts, without touching the tools themselves. Every pane here is also still
reachable on its own from the menubar search.

Formerly ``handyman_erp``, whose own docstring already said *"Nothing in it is
handyman-specific… The NAME is the vertical; the parts are not."* Quiar is that sentence
taken at its word (TASK-2026-08-14-002 Phase 3): the generalized lineage is Quiar, the
package offered to trade instances is **Quiar – Freelancer**, and the parts are unchanged —
`job_manager` books work whose kind is an `lcl_id` the instance mints for itself,
`contacts_manager` edits `natural_entity_profile` rows, `project_manager` keeps the
standing things jobs are done against, and `calendar` reads whatever classes under `log`.

## The calendar tab is PINNED — the scoped-feature rule, implemented

The standalone `calendar` tool is the cross-sandbox surface: the instance's whole week,
with per-sandbox toggles. This hub's tab is the same payload builder pinned to the app's
own sandbox with no toggle — which is exactly what the package manifest's
``ScopedFeature("calendar", "app_sandbox")`` declares. One primitive, two declarations,
and `test_quiar_hub` pins that the tab and the tool agree about one sandbox's events.

## The cost, stated

A tabbed hub switches CLIENT-SIDE, so every tab's payload ships on the first response
whether or not it is opened. Five panes over a small instance is a few kilobytes; the same
shape over a market log would not be, which is why `calendar` caps itself and says when it
truncated rather than quietly shipping 44,316 rows into a tab nobody clicked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.instance_baseline import LCL_DOCUMENT
from micyte.ports.tool_package import (
    DocumentRequirement,
    SourceRequirement,
    ToolRequirement,
)
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._quiar_clients_pane import ClientsPane
from ._quiar_jobs_pane import JobsPane
from ._registry import register
from ._requirements import CRM
from .calendar_viewer import CalendarViewer
from .canvass_manager import CANVASS_ARCHETYPE, CANVASS_LOG, CanvassManager
from .lcl_editor import LclEditorViewer

TOOL_ID = "quiar"
_SCHEMA = "mycite.v2.portal.workbench.tool.quiar.v1"
_TENANT_DEFAULT = "fnd"

#: ``(tab id, label, a FACTORY for the tool that fills it)``. Order is the order of the
#: work: write down what you know, book it against that, know who it is for, see when.
#: Factories rather than classes so a tab can declare a configured instance — the calendar
#: tab is the standalone tool PINNED to this sandbox (see the module docstring).
TABS: tuple[tuple[str, str, Any], ...] = (
    ("domain", "Domain", LclEditorViewer),
    # ONE jobs tab. `Jobs` and `Job` sat here side by side until 2026-09-06 — the log of
    # `job_event` rows, and the view of a `job` document — and the operator read them as
    # what they looked like: "there are duplicate job tab". `JobsPane` is both, stacked,
    # with the profile appearing only when a job is actually open. See its docstring.
    ("jobs", "Jobs", JobsPane),
    # The client form that also STARTS A JOB stands above the contacts table here, at the
    # tab — the same move JobsPane makes for the job document (2026-09-17). The tool
    # itself stays the editable table it declares.
    ("contacts", "Clients", ClientsPane),
    # Knocking comes BEFORE a client exists, which is why it sits beside Clients rather
    # than inside it: a door you have knocked and nobody answered is not a contact.
    ("canvass", "Canvassing", CanvassManager),
    ("calendar", "Calendar", lambda: CalendarViewer(pinned=True)),
)

#: The query parameter the client switches on, kept distinct from `agronomics`' own so the
#: two hubs cannot read each other's active tab out of one URL. The TOKEN stays `erp_tab`
#: across the rename: it is a URL detail three test files and the shell's query round-trip
#: already speak, and renaming it buys nothing an operator can see.
TAB_QUERY = "erp_tab"
DEFAULT_TAB = "domain"


class Quiar:
    """The surfaces an instance that sells work needs, in one place."""

    tool_id = TOOL_ID
    label = "Quiar"
    # UI copy: the rail hover. One sentence from the user's side — the each-tab-is-
    # the-standalone-tool rule lives in the class docstring, not in a tooltip.
    summary = "Write your own tree of work, and book jobs and clients against it."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: empty so it follows the instance switcher — the same books the operator is looking at.
    icon = "quiar"
    #: What an instance must HOLD before this works. Read by the install ledger, which
    #: provisions what is missing rather than leaving an operator to run
    #: `bootstrap_handyman_sandbox` and then remember `promote_sandbox_to_instance`.
    #:
    #: Scoped to the instance kind this belongs to — see tools/_requirements. The `lcl` is
    #: added on top of CRM because the hub's kind pickers read it; a job's or project's
    #: kind is a node the instance mints for itself. `projects` is `project_manager`'s own
    #: requirement and is not restated here.
    requires = ToolRequirement(
        documents=(
            *CRM.documents,
            DocumentRequirement(
                name=LCL_DOCUMENT, archetype="local_domain_log",
                why="the kinds it defines for itself — a job's kind is a node in here"),
            # The canvassing log (2026-09-10). Stated on the hub because the pane that
            # writes it is not a package tool of its own: "one canvassing doc per user",
            # and an instance that lacks it can see every door and record nothing.
            DocumentRequirement(
                name=CANVASS_LOG, archetype=CANVASS_ARCHETYPE,
                why="where a knock is recorded — the house, the day, what came of it"),
        ),
        sources=(
            SourceRequirement(
                sandbox="registrar", document="legal_entity",
                why="the address space the customer and site pickers resolve names in"),
        ),
    )
    # No `writes`. The hub declares none of its own: each pane owns its writes, and an
    # action has ONE owning tool — `_write_owners` raises on a second declaration, which is
    # what stops a composite from quietly becoming a second authorization surface for a
    # write its panes already govern.

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = dict(extra_query or {})
        sandbox = as_text(sandbox_id)
        panes: list[dict[str, Any]] = []
        for tab_id, label, tool in TABS:
            # Each pane is built by its OWN tool, with the same arguments it would get
            # standalone. A pane that failed builds its own error envelope and the others
            # still render — one empty tab is legible, a blank hub is not.
            instance = tool()
            try:
                payload = instance.build_panel_payload(
                    authority_db_file=authority_db_file,
                    sandbox_id=sandbox,
                    # Only the pane the operator is editing gets the row address; handing it
                    # to every tab would open an edit row in every table at once.
                    document_id=document_id if query.get(TAB_QUERY) == tab_id else "",
                    datum_address=datum_address if query.get(TAB_QUERY) == tab_id else "",
                    extra_query=query,
                )
            except Exception as exc:  # pragma: no cover — defensive
                payload = {"schema": _SCHEMA, "error": f"{tab_id} pane failed: {exc}"}
            # `panel_payload`, NOT `payload`, and `tool_id` beside it. `renderTabbed` reads
            # exactly those two: a tab whose `panel_payload` is null renders the scaffold
            # placeholder "<label> — no sub-tools yet", and `tool_id` is what
            # `paintPanelInto` dispatches the pane's renderer on.
            panes.append({
                "id": tab_id,
                "label": label,
                "tool_id": instance.tool_id,
                "panel_payload": payload,
            })

        ids = [pane["id"] for pane in panes]
        active = as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in ids:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Quiar",
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
        }


register(Quiar())

__all__ = ["DEFAULT_TAB", "TABS", "TAB_QUERY", "Quiar"]
