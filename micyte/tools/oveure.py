"""Oveure — the knowledge and automation hub: the domain, the mail, and the seams.

    ┌─ Oveure ─[ DOMAIN ][ INBOX ][ CONFIG ]─┐
    │  write the tree · answer what arrived ·  │
    │       see what runs on its behalf        │
    └──────────────────────────────────────────┘

The third lineage of TASK-2026-08-14-002, and the smallest: a composite in the seam
``agronomics_viewer`` established and ``quiar``/``brevat`` carry — each tab another tool's
``panel_payload`` under ``container:"tabbed"``.

**Three tabs, and the domain is the first** (operator, 2026-08-19). It was five. Overview
was a synopsis of two tabs a click away, which is a third statement of a fact two surfaces
already made; Notes was a flat shelf of the same documents the tree hangs on, so the same
writing appeared in two places with two different names for it. Both folded into the
Domain surface, where a writing is shown ON the node it is about. ``note_manager`` was
retired with the name convention on 2026-08-20: it listed documents by a ``note_`` prefix
that no document on the corpus carries any more, and a shelf that can only ever be empty
teaches an operator the tool is broken.

The documents GALLERY went the same way later the same day, and for a better reason than
tidiness: under the local domain log a document is a SLOT — an ordinary node on the
reserved ``documents`` branch — so the tree already lists every document, including the
ones nothing points at. What the gallery had that the tree did not was search and a way to
find the unassigned; both are now filters over the picture. One surface, one shape.

* **Domain** — `lcl_editor`, whole and full-bleed: the sandbox's own SAMRAS sheet is
  Oveure's substrate, and every instance already holds one. The tree is the navigation,
  the selection and the editing surface, and its writings are drawn on it. Its writes keep
  their governed `/agro` and `/notes` routes. Documents are created, titled, attached and
  searched here — a node DENOTES one by naming its slot in its own definition row
  (`micyte.core.datum_ops.local_domain`), so the association is a cell rather than a
  filename.
* **Inbox** — `inbox_viewer`: the mail that arrived, judged against the DOMAIN tab's own
  tree. The one pane that reads nothing itself — the mail lives in FND's account behind
  the boundary micyte may not cross — so it declares routes and the client asks. Reading,
  triaging and answering are separate calls, separately granted.
* **Config** — read-only, and micyte-honest: the automation register's posture (empty by
  design — the first routine reopens the 2026-07-31 "no scheduler" decision, which is its
  own operator gate) and the seams this app declares: the AI providers, and the email/SMS
  ports the Oveure refinement declared contract-only (available, deliberately unused).
  What this tab deliberately does
  NOT show is the email/newsletter/forwarding posture: that state lives in instance files
  a micyte tool cannot read (and must not — the boundary sweep is the wall), and it
  already has surfaces; a second rendering here would be the drift the one-fact-per-
  surface rule exists to prevent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.instance_baseline import LCL_DOCUMENT
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .inbox_viewer import inbox_payload
from .lcl_editor import LclEditorViewer
from .note_books import NOTE_ARCHETYPE, OVEURE_PROVIDERS

TOOL_ID = "oveure"
_SCHEMA = "mycite.v2.portal.workbench.tool.oveure.v1"
_TENANT_DEFAULT = "fnd"

#: The hub's own tab switch — its own token, so the three hubs cannot read each other's
#: active tab out of one URL (`erp_tab`, `brevat_tab`, this).
TAB_QUERY = "oveure_tab"
DEFAULT_TAB = "domain"



#: The widest a figure may be. The layout rule the config pane is drawn to — prose goes in
#: the label, the figure stays a glance — pinned by a test over EVERY row here.
_FIGURE_WIDTH = 24


def _routines_figure(registered: list[str] | tuple[str, ...]) -> str:
    """The routine ids while they fit in a figure, otherwise how many there are."""
    if not registered:
        return "none"
    joined = ", ".join(registered)
    if len(joined) <= _FIGURE_WIDTH:
        return joined
    return f"{len(registered)} routines"


def _count(n: int, noun: str) -> str:
    """``1 function`` / ``4 functions``. A figure that reads as broken English is one an
    operator stops reading, and this pane is nothing but figures."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _config() -> dict[str, Any]:
    """What runs on this instance's behalf, read from the registers that hold the fact.

    Everything here is a register micyte itself owns — the automation register, the
    contract's operation grain, this app's own declared providers. Binding and grant
    STATUS is deliberately absent: the Ports tab computes it through the real gates,
    and a second computation here would be a second answer.
    """
    from micyte.automation import routine_ids
    from micyte.ports.ai_provider import OPERATION_MESSAGES_CREATE
    from micyte.ports.port_catalog import port_type

    registered = routine_ids()
    # Short figures, prose in the label — the overview's screenshot-taught rule.
    items = [
        # Declared and scheduled are two facts and the pane keeps them apart. The
        # register held nothing until `email_triage`; what it holds now still runs on
        # nobody's timer, and collapsing the two rows into "1 routine" would read as
        # something being on.
        {"label": "Automation routines — declared here, and refused until granted",
         # NAMES while they fit, a COUNT once they do not. A figure is a glance, and the
         # 24-character rule is what keeps this column readable beside the others; two
         # routine ids joined already ran to 36. Still not "1 routine" at one — the name
         # is the useful answer while there is only one thing to name.
         "figure": _routines_figure(registered)},
        {"label": "Scheduling — none. The 2026-07-31 decision has not been reopened",
         "figure": "by hand"},
        *[{"label": f"AI · {provider} — bind and grant on Utilities → Ports",
           "figure": OPERATION_MESSAGES_CREATE}
          for provider in OVEURE_PROVIDERS],
        # The messaging seams, stated FROM the port catalog rather than from a vendor.
        # These rows named `aws_ses`/`aws_sns` until the port-type work, which read as a
        # claim about who carries the message — and that is the operator's choice of
        # EXTENSION on Ports, not something this app knows. What the app can honestly
        # say is which port it employs and at what grain.
        *[{"label": (f"{port_type(port).label} — declared; the extension that fills "
                     f"it and every grant are chosen on Utilities > Ports"),
           "figure": _count(len(port_type(port).operations), "function")}
          for port in ("email_provider", "sms_provider")],
    ]
    return {"schema": _SCHEMA, "container": "synopsis", "title": "Config",
            "items": items}


def _hub_pane(
    tab_id: str, *, authority_db_file: Path | None, sandbox: str,
) -> dict[str, Any]:
    """The panes the hub builds itself — the ones with no standalone tool behind them.

    A dispatch rather than a chain of ternaries: the third such pane was the one that
    would have made the expression unreadable, and a hub gaining a fourth should not have
    to touch the loop that renders them.
    """
    del authority_db_file
    if tab_id == "inbox":
        return inbox_payload(sandbox=sandbox, providers=OVEURE_PROVIDERS)
    return _config()


#: ``(tab id, label, a FACTORY or None)`` — ``None`` marks a pane the hub builds itself.
#: Order is the order of the work: write the tree, answer what arrived, see what runs.
TABS: tuple[tuple[str, str, Any], ...] = (
    ("domain", "Domain", LclEditorViewer),
    ("inbox", "Inbox", None),
    ("config", "Config", None),
)


class Oveure:
    """The surfaces an instance that keeps knowledge needs, in one place."""

    tool_id = TOOL_ID
    label = "Oveure"
    # UI copy: the rail hover. One sentence from the user's side — the each-tab-is-
    # the-standalone-tool rule lives in the class docstring, not in a tooltip.
    summary = "Write your own tree of topics, and answer the mail against it."
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    applies_to_archetype: tuple[str, ...] = (NOTE_ARCHETYPE,)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: empty follows the instance switcher.
    icon = "oveure"
    #: The substrate gate: the DOMAIN tab is the sandbox's own `lcl`, which every live
    #: instance already holds — so the hub lights everywhere, honestly, with the tree
    #: empty until the first writing. Per-note documents cannot gate a requirement
    #: (requirements read fixed names; a note's name is its own).
    requires = ToolRequirement(documents=(
        DocumentRequirement(
            name=LCL_DOCUMENT, archetype="local_domain_log",
            why="the domain sheet — Oveure's substrate; notes and the ask relay hang beside it"),
    ))
    # No `writes`: each pane owns its own, and `_write_owners` refuses a second
    # declaration of an action — the composite rule all three hubs share.

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = dict(extra_query or {})
        sandbox = as_text(sandbox_id)
        panes: list[dict[str, Any]] = []
        for tab_id, label, tool in TABS:
            try:
                if tool is None:
                    payload = _hub_pane(
                        tab_id, authority_db_file=authority_db_file, sandbox=sandbox)
                    pane_tool_id = f"oveure_{tab_id}"
                else:
                    instance = tool()
                    pane_tool_id = instance.tool_id
                    kwargs: dict[str, Any] = {
                        "authority_db_file": authority_db_file,
                        "sandbox_id": sandbox,
                        # Only the pane the operator is editing gets the row address —
                        # the composite rule the other two hubs carry.
                        "document_id": (
                            document_id if query.get(TAB_QUERY) == tab_id else ""),
                        "datum_address": (
                            datum_address if query.get(TAB_QUERY) == tab_id else ""),
                    }
                    if getattr(instance, "wants_surface_query", False):
                        kwargs["extra_query"] = query
                    payload = instance.build_panel_payload(**kwargs)
            except Exception as exc:  # pragma: no cover — defensive
                payload = {"schema": _SCHEMA, "error": f"{tab_id} pane failed: {exc}"}
                pane_tool_id = tab_id
            panes.append({
                "id": tab_id,
                "label": label,
                "tool_id": pane_tool_id,
                "panel_payload": payload,
            })

        ids = [pane["id"] for pane in panes]
        active = as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in ids:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Oveure",
            "sandbox_id": sandbox,
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": panes,
        }


register(Oveure())

__all__ = ["DEFAULT_TAB", "TABS", "TAB_QUERY", "Oveure"]
