"""Artifacts — the files an instance keeps, listed from the index rather than the blob.

The surface that completes the artifact datum type. The bytes of a file are its rows
(`micyte.core.datum_ops.artifact`), the rows are stored past the catalog snapshot
(`store_artifact_document`), and this is where a person sees that any of it happened.

## Why it lists by INSTANCE and not by sandbox

An `art.` id carries an msn and NO sandbox segment — the same shape `stl.` and `cptr.`
take — so "this sandbox's artifacts" is not a question the id can answer. An artifact
belongs to an instance; what ties one to a sandbox is the lcl node that DENOTES it, in
the artifacts branch (`ARTIFACT_BRANCH_ORDINAL`). Until nodes denote artifacts there is
nothing to group by, and inventing a grouping here would be inventing a fact.

So the tool is launched by ADDRESS, against the instance the switcher is on, rather than
offered for a document in focus. It declares no `applies_to_*`, which is how the contract
says exactly that.

## Sizes are DERIVED, not stored

An artifact's row count times :data:`CHUNK_BYTES` bounds its size without reading a byte
of it — the last chunk is short, so the count gives a ceiling and never a total. Shown as
a ceiling and labelled one. Reading the rows to get an exact figure would parse the whole
pool to draw a list of names, which is the cost this whole storage path exists to avoid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.artifact import CHUNK_BYTES, HEADER_ROWS
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.artifacts.v1"
_TENANT = "fnd"


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _instance_msn(private_dir: Any) -> str:
    """Which instance this portal IS, from its own config — never from the row.

    The switcher's sandbox cannot answer it: `system` is four instances' core sandbox, so
    a listing keyed on the browsing sandbox would show one client's files under another's
    name.
    """
    import json

    if not private_dir:
        return ""
    config = Path(private_dir) / "config.json"
    if not config.is_file():
        return ""
    try:
        return _as_text(json.loads(config.read_text(encoding="utf-8")).get("msn_id"))
    except (OSError, ValueError):
        return ""


def _ceiling_bytes(row_count: int) -> int:
    # The three header rows declare the file; only the rows beneath them carry it.
    return max(0, int(row_count) - HEADER_ROWS) * CHUNK_BYTES


class ArtifactsViewer:
    """The instance's artifact files, newest name first."""

    tool_id = "artifacts"
    label = "Artifacts"
    summary = (
        "Files this instance keeps as datum documents — name, size ceiling and version. "
        "Listed from the document index, because an artifact is deliberately absent from "
        "the catalog every other read goes through."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Launched by ADDRESS against the instance, not offered for a document in focus —
    #: an artifact has no sandbox, so there is no document it "applies to".
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        private_dir: Any = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del sandbox_id, document_id, datum_address
        if not authority_db_file:
            return self._table([], notice="no authority store configured")

        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(authority_db_file, allow_legacy_writes=False)
        msn = _instance_msn(private_dir)
        listed = store.list_artifact_documents(tenant_id=_TENANT, msn_id=msn)

        rows: list[dict[str, Any]] = []
        for entry in listed:
            document = store.read_artifact_document(
                tenant_id=_TENANT, document_id=entry["document_id"])
            count = len(document.rows) if document is not None else 0
            rows.append({
                "name": entry["name"],
                # Payload rows: the three header rows declare the file, they do not carry it.
                "rows": max(0, int(count) - HEADER_ROWS),
                # A CEILING: the final chunk is short, so this is never the exact size and
                # is not labelled as one.
                "size_ceiling": _ceiling_bytes(count),
                "version": _as_text(entry["version_hash"])[:19],
                "msn_id": entry["msn_id"],
            })

        notice = ""
        if not msn:
            notice = (
                "this instance's config names no msn_id, so every artifact in the store "
                "is listed rather than this instance's")
        return self._table(rows, notice=notice)

    def _table(self, rows: list[dict[str, Any]], *, notice: str = "") -> dict[str, Any]:
        payload = {
            "schema": _SCHEMA,
            "container": "record_table",
            "title": "Artifacts",
            "count_label": f"{len(rows)} artifact{'' if len(rows) == 1 else 's'}",
            "columns": ["name", "rows", "size_ceiling", "version", "msn_id"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": "No artifacts. Nothing has been stored under the `art.` prefix.",
        }
        if notice:
            payload["notice"] = notice
        return payload


register(ArtifactsViewer())
