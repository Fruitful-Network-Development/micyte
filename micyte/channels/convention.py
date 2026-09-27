"""CONVENTION — an open channel that offers up the local domain convention.

TASK-2026-09-11-001 P4: "the offer up source file, and handling payload pings for
updates". A peer instance that pins the archetype library's tree as the convention its
own tree follows needs one thing from FND to know whether it is behind: the library
tree's CURRENT id and hash. This channel serves that, and the convention the tree states,
read-only by construction (the open channel routes are GET-only and header-less).

Deliberately NOT the per-tree standing: which instances hold which sandboxes and whether
each is behind is the operator's view (the `convention` surface), not the network's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc

from . import register

CHANNEL_ID = "convention"
SESSION_SCHEMA = "mycite.v2.channel.convention.session.v1"
TABS = ("convention",)


class ConventionChannel:
    """The library tree's current version and the convention it states."""

    channel_id = CHANNEL_ID
    label = "Convention"
    summary = ("The local domain convention every tree is seeded from: the library tree's "
               "current version, and what it says. Compare your pin to it.")
    access = "open"
    sandbox = arc.ARCHETYPE_SANDBOX
    tabs = TABS

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        del sandbox_id, document_id, datum_address
        payload: dict[str, Any] = {
            "schema": SESSION_SCHEMA, "container": "record_table", "channel_id": CHANNEL_ID,
            "title": "The convention", "tabs": list(TABS), "active_tab": TABS[0],
            "columns": ["role", "label", "wears"], "rows": [], "row_count": 0,
        }
        if authority_db_file is None:
            payload["empty_text"] = "no authority store configured"
            return payload
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
        from micyte.core.datum_ops import local_domain as ld
        from micyte.core.datum_ops import local_domain_convention as ldc
        from micyte.core.document_naming import parse_canonical_document_id
        from micyte.core.instance_baseline import LOCAL_DOMAIN_NAMES

        store = SqliteSystemDatumStoreAdapter(Path(authority_db_file), allow_legacy_writes=False)
        documents = list(store.read_documents_by_sandbox(tenant_id="fnd", sandbox=arc.ARCHETYPE_SANDBOX))
        tree = next((d for d in documents if d.canonical_name in LOCAL_DOMAIN_NAMES), None)
        if tree is None:
            payload["empty_text"] = "this instance holds no archetype library tree"
            return payload
        parsed = parse_canonical_document_id(str(tree.document_id))
        convention = ldc.from_log(ld.read_log(tree), source=str(tree.document_id))
        rows = [{"role": role, "label": convention.label(role),
                 "wears": convention.structural_glyphs.get(role, "")}
                for role in ldc.STRUCTURAL_ROLES]
        payload.update({
            "document_id": str(tree.document_id), "version_hash": parsed.version_hash,
            "pin_title": f"{parsed.msn_id}.{arc.ARCHETYPE_SANDBOX}_{parsed.name}",
            "convention": convention.to_dict(), "rows": rows, "row_count": len(rows),
            "count_label": f"version {parsed.version_hash[:12]}",
        })
        return payload


register(ConventionChannel())

__all__ = ["CHANNEL_ID", "ConventionChannel"]
