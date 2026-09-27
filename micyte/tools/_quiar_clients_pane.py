"""Quiar's CLIENTS tab — the client form above the contacts table, one act.

Operator, 2026-09-17: the contact form should *"in addition to fields being used to add a
contact via an added msn_id etc. … also start a job, giving them a more intuitive and
coherent [form-field] selection of jobs needed … informed by the jobs and job types
defined and configured in the local domain."*

`contacts_manager` stays what it declares — an `editable_table`, which every sweep over
the editable tables checks it as, and which its own *Schedule* composite already stands
a booking row in front of. The form that also starts a job is stood in front of it HERE,
at the hub's tab, the way `JobsPane` stands the open job document above the job log: a
tab is a declaration of a pane, and this is that declaration. Standalone, the tool is
still the table.

Two states pass straight through: a contact being SCHEDULED (the tool already returned
its booking composite) and a client OPENED (their card and their work), because a second
form above either would be two things asking for attention on one screen.

No new renderer: `renderComposite` paints each pane through `paintPanelInto`, and the
form is the `record_form` every other pane of its kind already renders with — the jobs
pick is the ONE field `_services.pick_field` draws for the job form too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text

from .contacts_manager import ContactsManager, client_form

_SCHEMA = "mycite.v2.portal.workbench.tool.quiar_clients.v1"

#: No client renderer under this id, on purpose — `paintPanelInto` falls through to the
#: CONTAINER renderer, so the tab paints as the composite it declares itself to be.
TOOL_ID = "quiar_clients"


class ClientsPane:
    """The contacts table, with the client-and-work form above it."""

    tool_id = TOOL_ID
    label = "Clients"

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        table = ContactsManager().build_panel_payload(
            authority_db_file=authority_db_file, sandbox_id=sandbox_id,
            document_id=document_id, datum_address=datum_address, extra_query=extra_query)
        # Scheduling (already a composite), opened client (a card), or a refusal: the tool
        # said what it had to say, and a form above it would be a second voice.
        if table.get("container") != "editable_table" or table.get("error"):
            return table
        sandbox = as_text(sandbox_id)
        pick: list[dict[str, Any]] = []
        if authority_db_file is not None and sandbox:
            from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

            from ._services import offered_services

            try:
                pick, _log = offered_services(
                    SqliteSystemDatumStoreAdapter(Path(authority_db_file)),
                    tenant_id=ContactsManager.tenant_id, sandbox=sandbox,
                    msn_id=as_text((extra_query or {}).get("msn_id")))
            except Exception:
                pick = []
        return {
            "schema": _SCHEMA,
            "container": "composite",
            "direction": "column",
            "title": "Clients",
            "sandbox_id": sandbox,
            "panes": [
                {"label": "", "panel_payload": client_form(
                    sandbox=sandbox, pick=pick,
                    states=table.get("state_options") or [],
                    cities=table.get("city_options") or [])},
                {"label": "", "tool_id": ContactsManager.tool_id, "panel_payload": table},
            ],
        }


__all__ = ["TOOL_ID", "ClientsPane"]
