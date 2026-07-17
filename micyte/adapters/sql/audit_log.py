from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from micyte.adapters.sql._sqlite import dumps_json, loads_json, open_sqlite
from micyte.ports.audit_log import (
    AuditLogAppendReceipt,
    AuditLogAppendRequest,
    AuditLogPort,
    AuditLogReadRequest,
    AuditLogReadResult,
    AuditLogRecentWindowRequest,
    AuditLogRecentWindowResult,
    AuditLogRecord,
)


class SqliteAuditLogAdapter(AuditLogPort):
    def __init__(
        self,
        db_file: str | Path,
        *,
        clock: Callable[[], int] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._db_file = Path(db_file)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)

    def _connect(self):
        return open_sqlite(self._db_file)

    def append_audit_record(self, request: AuditLogAppendRequest) -> AuditLogAppendReceipt:
        normalized_request = request if isinstance(request, AuditLogAppendRequest) else AuditLogAppendRequest.from_dict(request)
        record = AuditLogRecord(
            record_id=self._id_factory(),
            recorded_at_unix_ms=self._clock(),
            record=normalized_request.record,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_records (record_id, recorded_at_unix_ms, record_json)
                VALUES (?, ?, ?)
                """,
                (record.record_id, record.recorded_at_unix_ms, dumps_json(record.record)),
            )
            connection.commit()
        return AuditLogAppendReceipt(
            record_id=record.record_id,
            recorded_at_unix_ms=record.recorded_at_unix_ms,
        )

    def read_audit_record(self, request: AuditLogReadRequest) -> AuditLogReadResult:
        normalized_request = request if isinstance(request, AuditLogReadRequest) else AuditLogReadRequest.from_dict(request)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_id, recorded_at_unix_ms, record_json FROM audit_records WHERE record_id = ?",
                (normalized_request.record_id,),
            ).fetchone()
        if row is None:
            return AuditLogReadResult(record=None)
        return AuditLogReadResult(
            record=AuditLogRecord(
                record_id=row["record_id"],
                recorded_at_unix_ms=row["recorded_at_unix_ms"],
                record=loads_json(row["record_json"]),
            )
        )

    def read_recent_audit_records(
        self,
        request: AuditLogRecentWindowRequest,
    ) -> AuditLogRecentWindowResult:
        normalized_request = (
            request
            if isinstance(request, AuditLogRecentWindowRequest)
            else AuditLogRecentWindowRequest.from_dict(request)
        )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, recorded_at_unix_ms, record_json
                FROM audit_records
                ORDER BY recorded_at_unix_ms DESC, record_id DESC
                LIMIT ?
                """,
                (normalized_request.limit,),
            ).fetchall()
        return AuditLogRecentWindowResult(
            records=tuple(
                AuditLogRecord(
                    record_id=row["record_id"],
                    recorded_at_unix_ms=row["recorded_at_unix_ms"],
                    record=loads_json(row["record_json"]),
                )
                for row in rows
            )
        )

    def bootstrap_from_filesystem(self, storage_file: str | Path | None) -> None:
        path = None if storage_file is None else Path(storage_file)
        if path is None or not path.exists() or not path.is_file():
            return
        with self._connect() as connection:
            existing = connection.execute("SELECT COUNT(*) AS count FROM audit_records").fetchone()
            if existing is not None and int(existing["count"]) > 0:
                return
            for line in path.read_text(encoding="utf-8").splitlines():
                token = line.strip()
                if not token:
                    continue
                try:
                    payload = json.loads(token)
                    record = AuditLogRecord.from_dict(payload)
                except Exception:
                    continue
                connection.execute(
                    """
                    INSERT OR IGNORE INTO audit_records (record_id, recorded_at_unix_ms, record_json)
                    VALUES (?, ?, ?)
                    """,
                    (record.record_id, record.recorded_at_unix_ms, dumps_json(record.record)),
                )
            connection.commit()
