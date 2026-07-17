"""Contacts viewer — the agro_erp supply-source directory (Phase 3).

A :class:`DatumDocTool` subclass over the ``contacts`` doc (``4-5-N`` rows: an lcl
supplier node + four ``rf.3-1-2`` title fields = name / email / phone / website).
Emits a declarative ``record_list`` payload (searchable list) the shared JS container
renderer paints. This is the "supply-source profiles" surface of the agronomics group.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    Markers,
    decode_label,
    iter_marker_pairs,
)

from ._contract import DatumDocTool
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head


class ContactsViewer(DatumDocTool):
    tool_id = "contacts"
    label = "Contacts"
    summary = "Supply-source directory — supplier name, email, phone and website."
    schema = "mycite.v2.portal.workbench.tool.contacts.v1"
    canonical_name = "contacts"
    container = "record_list"
    applies_to_archetype: tuple[str, ...] = ("mycite.v2.datum.agro_erp.contacts.v1",)

    def empty_body(self) -> dict[str, Any]:
        return {"container": self.container, "items": [], "item_count": 0}

    def shape_payload(self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for row in getattr(doc, "rows", ()) or ():
            if not _as_text(row.datum_address).startswith("4-5-"):
                continue
            head = _row_head(row)
            node = ""
            titles: list[str] = []
            for marker, value in iter_marker_pairs(head):
                if marker == Markers.LCL_ID and not node:
                    node = _as_text(value)
                elif marker == Markers.TITLE:
                    titles.append(decode_label(value))
            # head order (ledger): name, email, phone, website.
            name, email, phone, website = [*titles, "", "", "", ""][:4]
            items.append({
                "title": name or node,
                "subtitle": node,
                "fields": [
                    {"label": "email", "value": email},
                    {"label": "phone", "value": phone},
                    {"label": "website", "value": website},
                ],
            })
        return {
            "container": self.container,
            "title": "Contacts",
            "count_label": f"{len(items)} supplier{'' if len(items) == 1 else 's'}",
            "items": items,
            "item_count": len(items),
            "search_placeholder": "Search suppliers…",
            "empty_text": "No contacts.",
        }


register(ContactsViewer())
