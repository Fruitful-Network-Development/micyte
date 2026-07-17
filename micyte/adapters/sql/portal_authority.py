from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from micyte.adapters.sql._sqlite import dumps_json, loads_json, open_sqlite
from micyte.ports.portal_authority import (
    PortalAuthorityPort,
    PortalAuthorityRequest,
    PortalAuthorityResult,
    PortalAuthoritySource,
)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


class SqlitePortalAuthorityAdapter(PortalAuthorityPort):
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

    def has_scope(self, scope_id: str) -> bool:
        token = _as_text(scope_id)
        if not token:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM portal_authority_snapshots WHERE scope_id = ?",
                (token,),
            ).fetchone()
        return row is not None

    def store_portal_authority(self, source: PortalAuthoritySource | dict[str, Any]) -> None:
        normalized = source if isinstance(source, PortalAuthoritySource) else PortalAuthoritySource.from_dict(source)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portal_authority_snapshots (scope_id, payload_json, updated_at_unix_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (normalized.scope_id, dumps_json(normalized.to_dict()), self._clock()),
            )
            connection.commit()

    def bootstrap_from_defaults(
        self,
        *,
        scope_id: str,
        capabilities: tuple[str, ...] | list[str],
        tool_exposure_policy: dict[str, Any],
        ownership_posture: str = "portal_instance",
    ) -> None:
        if self.has_scope(scope_id):
            return
        self.store_portal_authority(
            PortalAuthoritySource(
                scope_id=scope_id,
                capabilities=tuple(capabilities),
                tool_exposure_policy=tool_exposure_policy,
                ownership_posture=ownership_posture,
            )
        )

    def read_portal_authority(self, request: PortalAuthorityRequest) -> PortalAuthorityResult:
        normalized_request = (
            request if isinstance(request, PortalAuthorityRequest) else PortalAuthorityRequest.from_dict(request)
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM portal_authority_snapshots WHERE scope_id = ?",
                (normalized_request.scope_id,),
            ).fetchone()
        if row is None:
            return PortalAuthorityResult(
                source=None,
                resolution_status={"portal_authority": "missing"},
                warnings=("sql_portal_authority_missing",),
            )
        source = PortalAuthoritySource.from_dict(loads_json(row["payload_json"]))
        return PortalAuthorityResult(
            source=source,
            resolution_status={
                "portal_authority": "loaded",
                "known_tool_count": len(normalized_request.known_tool_ids),
            },
        )
