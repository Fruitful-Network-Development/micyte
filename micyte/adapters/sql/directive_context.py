from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from micyte.adapters.sql._sqlite import dumps_json, loads_json, open_sqlite
from micyte.ports.directive_context import (
    DirectiveContextEventPort,
    DirectiveContextEventQuery,
    DirectiveContextEventRecord,
    DirectiveContextPort,
    DirectiveContextRequest,
    DirectiveContextResult,
    DirectiveContextSource,
)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _candidate_score(
    source: DirectiveContextSource,
    *,
    request: DirectiveContextRequest,
) -> tuple[int, int, int, int]:
    hyphae_exact = 1 if request.subject_hyphae_hash and source.subject_hyphae_hash == request.subject_hyphae_hash else 0
    version_exact = 1 if request.subject_version_hash and source.subject_version_hash == request.subject_version_hash else 0
    hyphae_generic = 1 if not source.subject_hyphae_hash else 0
    version_generic = 1 if not source.subject_version_hash else 0
    return (hyphae_exact, version_exact, hyphae_generic, version_generic)


def _matches_request(source: DirectiveContextSource, *, request: DirectiveContextRequest) -> bool:
    if source.portal_instance_id != request.portal_instance_id:
        return False
    if source.tool_id != request.tool_id:
        return False
    if request.subject_hyphae_hash and source.subject_hyphae_hash not in {"", request.subject_hyphae_hash}:
        return False
    if request.subject_version_hash and source.subject_version_hash not in {"", request.subject_version_hash}:
        return False
    if request.subject_hyphae_hash and source.subject_hyphae_hash == request.subject_hyphae_hash:
        return True
    if request.subject_version_hash and source.subject_version_hash == request.subject_version_hash:
        return True
    return False


class SqliteDirectiveContextAdapter(DirectiveContextPort, DirectiveContextEventPort):
    def __init__(
        self,
        db_file: str | Path,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._db_file = Path(db_file)
        self._clock = clock or (lambda: int(time.time() * 1000))

    def _connect(self):
        return open_sqlite(self._db_file)

    def store_directive_context(self, source: DirectiveContextSource | dict[str, Any]) -> None:
        normalized = source if isinstance(source, DirectiveContextSource) else DirectiveContextSource.from_dict(source)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO directive_context_snapshots (
                    context_id,
                    portal_instance_id,
                    tool_id,
                    hyphae_hash,
                    version_hash,
                    payload_json,
                    updated_at_unix_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(context_id) DO UPDATE SET
                    portal_instance_id = excluded.portal_instance_id,
                    tool_id = excluded.tool_id,
                    hyphae_hash = excluded.hyphae_hash,
                    version_hash = excluded.version_hash,
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (
                    normalized.context_id,
                    normalized.portal_instance_id,
                    normalized.tool_id,
                    normalized.subject_hyphae_hash,
                    normalized.subject_version_hash,
                    dumps_json(normalized.to_dict()),
                    self._clock(),
                ),
            )
            connection.commit()

    def read_directive_context(self, request: DirectiveContextRequest) -> DirectiveContextResult:
        normalized_request = (
            request if isinstance(request, DirectiveContextRequest) else DirectiveContextRequest.from_dict(request)
        )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json, updated_at_unix_ms
                FROM directive_context_snapshots
                WHERE portal_instance_id = ? AND tool_id = ?
                ORDER BY updated_at_unix_ms DESC, context_id DESC
                """,
                (normalized_request.portal_instance_id, normalized_request.tool_id),
            ).fetchall()
        candidates: list[tuple[tuple[int, int, int, int], int, DirectiveContextSource]] = []
        for row in rows:
            source = DirectiveContextSource.from_dict(loads_json(row["payload_json"]))
            if not _matches_request(source, request=normalized_request):
                continue
            candidates.append((_candidate_score(source, request=normalized_request), int(row["updated_at_unix_ms"]), source))
        if not candidates:
            return DirectiveContextResult(
                source=None,
                resolution_status={"directive_context": "missing"},
                warnings=("sql_directive_context_missing",),
            )
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        source = candidates[0][2]
        match_kind = "exact_hyphae_version"
        if source.subject_hyphae_hash == normalized_request.subject_hyphae_hash and not source.subject_version_hash:
            match_kind = "hyphae_subject_fallback"
        elif source.subject_version_hash == normalized_request.subject_version_hash and not source.subject_hyphae_hash:
            match_kind = "version_subject_fallback"
        elif source.subject_hyphae_hash == normalized_request.subject_hyphae_hash and source.subject_version_hash != normalized_request.subject_version_hash:
            match_kind = "hyphae_subject_match"
        return DirectiveContextResult(
            source=source,
            resolution_status={
                "directive_context": "loaded",
                "match_kind": match_kind,
            },
        )

    def append_directive_context_event(self, event: DirectiveContextEventRecord | dict[str, Any]) -> None:
        normalized = event if isinstance(event, DirectiveContextEventRecord) else DirectiveContextEventRecord.from_dict(event)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO directive_context_events (
                    event_id,
                    context_id,
                    portal_instance_id,
                    tool_id,
                    event_kind,
                    hyphae_hash,
                    version_hash,
                    payload_json,
                    provenance_json,
                    recorded_at_unix_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.event_id,
                    normalized.context_id,
                    normalized.portal_instance_id,
                    normalized.tool_id,
                    normalized.event_kind,
                    normalized.subject_hyphae_hash,
                    normalized.subject_version_hash,
                    dumps_json(normalized.payload or {}),
                    dumps_json(normalized.provenance or {}),
                    normalized.recorded_at_unix_ms or self._clock(),
                ),
            )
            connection.commit()

    def read_directive_context_events(self, request: DirectiveContextEventQuery) -> tuple[DirectiveContextEventRecord, ...]:
        normalized_request = (
            request if isinstance(request, DirectiveContextEventQuery) else DirectiveContextEventQuery.from_dict(request)
        )
        query = """
            SELECT
                event_id,
                context_id,
                portal_instance_id,
                tool_id,
                event_kind,
                hyphae_hash AS subject_hyphae_hash,
                version_hash AS subject_version_hash,
                payload_json,
                provenance_json,
                recorded_at_unix_ms
            FROM directive_context_events
            WHERE portal_instance_id = ?
        """
        params: list[Any] = [normalized_request.portal_instance_id]
        if normalized_request.tool_id:
            query += " AND tool_id = ?"
            params.append(normalized_request.tool_id)
        if normalized_request.context_id:
            query += " AND context_id = ?"
            params.append(normalized_request.context_id)
        query += " ORDER BY recorded_at_unix_ms DESC, event_id DESC LIMIT ?"
        params.append(normalized_request.limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return tuple(
            DirectiveContextEventRecord(
                event_id=row["event_id"],
                context_id=row["context_id"],
                portal_instance_id=row["portal_instance_id"],
                tool_id=row["tool_id"],
                event_kind=row["event_kind"],
                subject_hyphae_hash=row["subject_hyphae_hash"],
                subject_version_hash=row["subject_version_hash"],
                payload=loads_json(row["payload_json"]),
                provenance=loads_json(row["provenance_json"]),
                recorded_at_unix_ms=int(row["recorded_at_unix_ms"]),
            )
            for row in rows
        )
