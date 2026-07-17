from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from micyte.adapters.filesystem_datum import FilesystemSystemDatumStoreAdapter
from micyte.adapters.sql._sqlite import dumps_json, loads_json, open_sqlite
from micyte.adapters.sql.datum_semantics import (
    build_document_semantics,
)
from micyte.adapters.sql.datum_semantics import (
    preview_document_delete as preview_document_delete_mutation,
)
from micyte.adapters.sql.datum_semantics import (
    preview_document_insert as preview_document_insert_mutation,
)
from micyte.adapters.sql.datum_semantics import (
    preview_document_move as preview_document_move_mutation,
)
from micyte.core.document_naming import (
    derive_canonical_id_from_legacy,
    is_canonical_document_id,
)
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentCatalogResult,
    AuthoritativeDatumDocumentMutationPort,
    AuthoritativeDatumDocumentRequest,
    PublicationProfileBasicsWritePort,
    PublicationProfileBasicsWriteRequest,
    PublicationProfileBasicsWriteResult,
    PublicationTenantSummaryPort,
    PublicationTenantSummaryRequest,
    PublicationTenantSummaryResult,
    SystemDatumResourceRow,
    SystemDatumStorePort,
    SystemDatumStoreRequest,
    SystemDatumWorkbenchResult,
)


class NonCanonicalDocumentIdError(ValueError):
    """Raised when a write attempts to persist a non-canonical document id.

    Phase E3: new writes must produce canonical ``lv./stl./cptr.`` ids; legacy
    ``system:`` / ``sandbox:`` ids are still accepted on reads via the
    ``documents.legacy_alias`` index for one cycle.
    """


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _sqlite_journal_mode_token(value: object) -> str:
    token = _as_text(value).upper()
    if token in {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}:
        return token
    return "WAL"


def _normalize_version_hash_token(value: object) -> str:
    token = _as_text(value).lower()
    if token.startswith("sha256:"):
        token = token.split(":", 1)[1]
    return token


def _sql_norm_version_hash(column: str) -> str:
    """SQLite expression lowering version_hash tokens like ``sha256:<hex>`` for joins."""

    col = column.strip()
    return (
        f"CASE WHEN substr(lower(trim({col})), 1, 7) = 'sha256:' "
        f"THEN substr(lower(trim({col})), 8) ELSE lower(trim({col})) END"
    )


def _workbench_from_payload(payload: dict[str, object]) -> SystemDatumWorkbenchResult:
    rows = payload.get("rows") or ()
    warnings = payload.get("warnings") or ()
    return SystemDatumWorkbenchResult(
        tenant_id=payload.get("tenant_id"),
        rows=tuple(
            row if isinstance(row, SystemDatumResourceRow) else SystemDatumResourceRow.from_dict(row)
            for row in rows
        ),
        source_files=payload.get("source_files") or {},
        materialization_status=payload.get("materialization_status") or {},
        warnings=tuple(str(item) for item in warnings),
    )


# Phase 14c: module-level catalog cache shared across SqliteSystemDatumStoreAdapter
# instances. The MOS extension adapters (PayPal, Newsletter, Email) each
# instantiate a fresh adapter per request → per-instance cache (still present
# below) couldn't help cross-extension. With the production authority DB at
# 244 MB and the ext_paypal `_find_doc` doing a full catalog scan to find one
# canonical_name, parallelized rendering still serialized on this load. The
# module-level cache lets 4 extensions share one fetch per (db_path, tenant_id)
# until the file's mtime changes; any write through `_invalidate_catalog`
# clears both layers.
_GLOBAL_CATALOG_CACHE: dict[tuple[str, str], tuple[int, Any]] = {}


class SqliteSystemDatumStoreAdapter(
    SystemDatumStorePort,
    AuthoritativeDatumDocumentMutationPort,
    PublicationTenantSummaryPort,
    PublicationProfileBasicsWritePort,
):
    def __init__(
        self,
        db_file: str | Path,
        *,
        clock: Callable[[], int] | None = None,
        allow_legacy_writes: bool = False,
    ) -> None:
        self._db_file = Path(db_file)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._allow_legacy_writes_flag = bool(allow_legacy_writes)
        # Per-instance catalog cache: dict[tenant_id, (db_mtime_ns, catalog_result)]
        # Kept for tests that introspect per-instance state; the module-level
        # _GLOBAL_CATALOG_CACHE is consulted first to share fetches across
        # ephemeral adapter instances.
        self._catalog_cache: dict[str, tuple[int, Any]] = {}

    @property
    def db_file(self) -> Path:
        """The authority db this adapter is bound to.

        Public because sibling state is addressed relative to it — the contract
        store lives at `<private>/contracts/`, beside the db — and callers should
        not have to be told a path they could derive.
        """
        return self._db_file

    def _connect(self):
        return open_sqlite(self._db_file)

    def _allow_legacy_writes(self) -> bool:
        """Phase E3 one-cycle compatibility flag for legacy bootstrapping.

        New writes must produce canonical ``lv./stl./cptr.`` ids. This adapter
        keeps a per-instance ``allow_legacy_writes`` escape hatch that the
        bootstrapping pipeline (and tests that materialise legacy fixtures)
        opt into explicitly. The flag will be removed once the catalog
        upgrade in Phase E4 lands.
        """

        return self._allow_legacy_writes_flag

    def has_authoritative_catalog(self, tenant_id: str) -> bool:
        token = _as_text(tenant_id).lower()
        if not token:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
                (token,),
            ).fetchone()
        return row is not None

    def has_system_workbench(self, tenant_id: str) -> bool:
        token = _as_text(tenant_id).lower()
        if not token:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM system_workbench_snapshots WHERE tenant_id = ?",
                (token,),
            ).fetchone()
        return row is not None

    def has_publication_summary(self, tenant_id: str, tenant_domain: str) -> bool:
        normalized_request = PublicationTenantSummaryRequest(
            tenant_id=tenant_id,
            tenant_domain=tenant_domain,
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM publication_summary_snapshots WHERE tenant_id = ? AND tenant_domain = ?",
                (normalized_request.tenant_id, normalized_request.tenant_domain),
            ).fetchone()
        return row is not None

    def store_authoritative_catalog(
        self,
        result: AuthoritativeDatumDocumentCatalogResult,
        *,
        allow_non_canonical_catalog_ids: bool | None = None,
    ) -> None:
        normalized = (
            result
            if isinstance(result, AuthoritativeDatumDocumentCatalogResult)
            else AuthoritativeDatumDocumentCatalogResult.from_dict(result)
        )
        non_canonical_ids: list[str] = []
        for document in normalized.documents:
            doc_id = _as_text(document.document_id)
            if doc_id and not is_canonical_document_id(doc_id):
                non_canonical_ids.append(doc_id)
        allow_legacy_effective = (
            self._allow_legacy_writes()
            if allow_non_canonical_catalog_ids is None
            else bool(allow_non_canonical_catalog_ids)
        )
        if non_canonical_ids and not allow_legacy_effective:
            raise NonCanonicalDocumentIdError(
                "Refusing to persist non-canonical document ids: "
                + ", ".join(sorted(set(non_canonical_ids))[:3])
                + (" …" if len(non_canonical_ids) > 3 else "")
            )
        updated_at = self._clock()
        with self._connect() as connection:
            prior_journal_mode = _sqlite_journal_mode_token(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            )
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA journal_mode = MEMORY")
            try:
                connection.execute(
                    """
                    INSERT INTO authoritative_catalog_snapshots (tenant_id, payload_json, updated_at_unix_ms)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at_unix_ms = excluded.updated_at_unix_ms
                    """,
                    (normalized.tenant_id, dumps_json(normalized.to_dict()), updated_at),
                )
                connection.execute("DELETE FROM datum_row_semantics WHERE tenant_id = ?", (normalized.tenant_id,))
                connection.execute("DELETE FROM datum_document_semantics WHERE tenant_id = ?", (normalized.tenant_id,))
                for document in normalized.documents:
                    semantics = build_document_semantics(document)
                    connection.execute(
                        """
                        INSERT INTO datum_document_semantics (
                            tenant_id,
                            document_id,
                            policy,
                            version_hash,
                            canonical_payload_json,
                            updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            normalized.tenant_id,
                            document.document_id,
                            semantics["document"]["policy"],
                            semantics["document"]["version_hash"],
                            dumps_json(semantics["document"]["canonical_payload"]),
                            updated_at,
                        ),
                    )
                    for datum_address, row_semantics in semantics["rows"].items():
                        connection.execute(
                            """
                            INSERT INTO datum_row_semantics (
                                tenant_id,
                                document_id,
                                datum_address,
                                policy,
                                semantic_hash,
                                hyphae_hash,
                                hyphae_chain_json,
                                local_references_json,
                                warnings_json,
                                updated_at_unix_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                normalized.tenant_id,
                                document.document_id,
                                datum_address,
                                row_semantics["policy"],
                                row_semantics["semantic_hash"],
                                row_semantics["hyphae_hash"],
                                dumps_json(row_semantics["hyphae_chain"]),
                                dumps_json(row_semantics["local_references"]),
                                dumps_json(row_semantics["warnings"]),
                                updated_at,
                            ),
                        )
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
                connection.execute(f"PRAGMA journal_mode = {prior_journal_mode}")
        # Phase 14c: invalidate the in-memory catalog caches on EVERY
        # catalog write path — the per-instance + module-level dicts both
        # rely on this since mtime granularity on some filesystems is
        # coarser than the test save→load sequence.
        self._catalog_cache.pop(normalized.tenant_id, None)
        _GLOBAL_CATALOG_CACHE.pop((str(self._db_file.resolve()), normalized.tenant_id), None)

    def replace_single_document_efficient(
        self,
        *,
        tenant_id: str,
        prior_document_id: str | None,
        updated_document: AuthoritativeDatumDocument,
    ) -> None:
        """Replace exactly one document in the catalog without re-encoding
        every other document's semantics.

        Background: :meth:`store_authoritative_catalog` does a full
        ``DELETE FROM datum_row_semantics WHERE tenant_id=?`` followed by
        re-INSERTing every row of every document. For a single
        contact-log update with 1168 rows on top of 124 CTS-GIS docs,
        that's ~100 MB of pointless work and a worker memory spike
        (observed: ~800 MB transient allocation, OOM-throttled by
        MemoryHigh=1500M in the systemd override).

        This method instead:

        1. Reads the current catalog (single SELECT, served from cache
           after first call).
        2. Builds the new catalog tuple in memory by swapping
           ``prior_document_id`` for ``updated_document`` (or appending
           if ``prior_document_id`` is ``None``).
        3. UPSERTs the snapshot row.
        4. DELETEs + INSERTs semantics rows ONLY for the changed doc
           (and the prior one if its id was different).

        Cost: O(rows_in_changed_doc) instead of O(all_rows_in_catalog).
        """
        prior_id = _as_text(prior_document_id) if prior_document_id else ""
        new_id = _as_text(updated_document.document_id)
        if not new_id:
            raise ValueError("updated_document.document_id is required")
        if not is_canonical_document_id(new_id) and not self._allow_legacy_writes():
            raise NonCanonicalDocumentIdError(
                f"Refusing to persist non-canonical document id: {new_id!r}"
            )

        # Build the new catalog tuple in memory (swap or append).
        catalog = self.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        )
        documents: list[AuthoritativeDatumDocument] = []
        swapped = False
        for document in catalog.documents:
            if prior_id and document.document_id == prior_id:
                documents.append(updated_document)
                swapped = True
            else:
                documents.append(document)
        if not swapped:
            documents.append(updated_document)
        next_catalog = AuthoritativeDatumDocumentCatalogResult(
            tenant_id=catalog.tenant_id,
            documents=tuple(documents),
            source_files=dict(catalog.source_files),
            readiness_status=dict(catalog.readiness_status),
            warnings=tuple(catalog.warnings),
        )

        # Compute semantics ONLY for the changed doc.
        semantics = build_document_semantics(updated_document)
        updated_at = self._clock()
        with self._connect() as connection:
            prior_journal_mode = _sqlite_journal_mode_token(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            )
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA journal_mode = MEMORY")
            try:
                connection.execute(
                    """
                    INSERT INTO authoritative_catalog_snapshots (tenant_id, payload_json, updated_at_unix_ms)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at_unix_ms = excluded.updated_at_unix_ms
                    """,
                    (next_catalog.tenant_id, dumps_json(next_catalog.to_dict()), updated_at),
                )
                # Remove the prior doc's semantics (under its OLD id) and
                # the new doc's semantics (under its NEW id, in case of
                # idempotent reapply). Both DELETEs are scoped by
                # document_id so cost is O(rows_in_those_docs), not the
                # full tenant.
                if prior_id and prior_id != new_id:
                    connection.execute(
                        "DELETE FROM datum_row_semantics WHERE tenant_id = ? AND document_id = ?",
                        (next_catalog.tenant_id, prior_id),
                    )
                    connection.execute(
                        "DELETE FROM datum_document_semantics WHERE tenant_id = ? AND document_id = ?",
                        (next_catalog.tenant_id, prior_id),
                    )
                connection.execute(
                    "DELETE FROM datum_row_semantics WHERE tenant_id = ? AND document_id = ?",
                    (next_catalog.tenant_id, new_id),
                )
                connection.execute(
                    "DELETE FROM datum_document_semantics WHERE tenant_id = ? AND document_id = ?",
                    (next_catalog.tenant_id, new_id),
                )
                connection.execute(
                    """
                    INSERT INTO datum_document_semantics (
                        tenant_id, document_id, policy, version_hash,
                        canonical_payload_json, updated_at_unix_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        next_catalog.tenant_id,
                        new_id,
                        semantics["document"]["policy"],
                        semantics["document"]["version_hash"],
                        dumps_json(semantics["document"]["canonical_payload"]),
                        updated_at,
                    ),
                )
                for datum_address, row_semantics in semantics["rows"].items():
                    connection.execute(
                        """
                        INSERT INTO datum_row_semantics (
                            tenant_id, document_id, datum_address, policy,
                            semantic_hash, hyphae_hash, hyphae_chain_json,
                            local_references_json, warnings_json, updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            next_catalog.tenant_id,
                            new_id,
                            datum_address,
                            row_semantics["policy"],
                            row_semantics["semantic_hash"],
                            row_semantics["hyphae_hash"],
                            dumps_json(row_semantics["hyphae_chain"]),
                            dumps_json(row_semantics["local_references"]),
                            dumps_json(row_semantics["warnings"]),
                            updated_at,
                        ),
                    )
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
                connection.execute(f"PRAGMA journal_mode = {prior_journal_mode}")
        # Invalidate both the in-memory catalog caches (per-instance + module-
        # level) so the next read picks up the swap. The mtime check alone is
        # not enough — within a single test the file write may not bump
        # st_mtime to a different second on some filesystems.
        self._catalog_cache.pop(tenant_id, None)
        _GLOBAL_CATALOG_CACHE.pop((str(self._db_file.resolve()), tenant_id), None)

    def store_system_workbench(self, result: SystemDatumWorkbenchResult) -> None:
        normalized = (
            result
            if isinstance(result, SystemDatumWorkbenchResult)
            else SystemDatumWorkbenchResult.from_dict(result)
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_workbench_snapshots (tenant_id, payload_json, updated_at_unix_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (normalized.tenant_id, dumps_json(normalized.to_dict()), self._clock()),
            )
            connection.commit()

    def store_publication_summary(self, result: PublicationTenantSummaryResult, *, tenant_id: str, tenant_domain: str) -> None:
        normalized_request = PublicationTenantSummaryRequest(tenant_id=tenant_id, tenant_domain=tenant_domain)
        normalized_result = (
            result
            if isinstance(result, PublicationTenantSummaryResult)
            else PublicationTenantSummaryResult.from_dict(result)
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO publication_summary_snapshots (tenant_id, tenant_domain, payload_json, updated_at_unix_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, tenant_domain) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (
                    normalized_request.tenant_id,
                    normalized_request.tenant_domain,
                    dumps_json(normalized_result.to_dict()),
                    self._clock(),
                ),
            )
            connection.commit()

    def bootstrap_from_filesystem(
        self,
        *,
        data_dir: str | Path,
        public_dir: str | Path | None,
        tenant_id: str,
        tenant_domain: str | None = None,
        canonical_ids: bool = False,
        canonical_ids_msn: str = "3-2-3",
    ) -> None:
        filesystem = FilesystemSystemDatumStoreAdapter(Path(data_dir), public_dir=public_dir)
        normalized_tenant_id = _as_text(tenant_id).lower()
        catalog = filesystem.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=normalized_tenant_id)
        )
        # ``canonical_ids`` rewrites each filesystem-derived legacy id
        # (``system:`` / ``sandbox:`` …) to its canonical ``lv.`` form before
        # persisting. This is the only knob that lets bootstrap-based fixtures
        # exercise the canonical-only write path (apply re-persists the full
        # catalog and refuses non-canonical ids). Default False preserves the
        # legacy-keyed seed shape that read-only fixtures still assert against.
        if canonical_ids:
            catalog = self._canonicalize_catalog_document_ids(
                catalog, msn_id=canonical_ids_msn
            )
        self.store_authoritative_catalog(
            catalog,
            allow_non_canonical_catalog_ids=not canonical_ids,
        )
        self.store_system_workbench(
            filesystem.read_system_resource_workbench(
                SystemDatumStoreRequest(tenant_id=normalized_tenant_id)
            )
        )
        if tenant_domain:
            self.store_publication_summary(
                filesystem.read_publication_tenant_summary(
                    PublicationTenantSummaryRequest(
                        tenant_id=normalized_tenant_id,
                        tenant_domain=tenant_domain,
                    )
                ),
                tenant_id=normalized_tenant_id,
                tenant_domain=tenant_domain,
            )

    def _canonicalize_catalog_document_ids(
        self,
        catalog: AuthoritativeDatumDocumentCatalogResult,
        *,
        msn_id: str,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Return ``catalog`` with every legacy document id rewritten to its
        canonical ``lv.`` form, keyed by the document's own content hash.

        Mirrors the production migration convention (one ``msn_id`` per tenant,
        ``version_hash`` taken from the document semantics). Documents that are
        already canonical pass through unchanged. ``source_files`` keys are
        relative paths, not ids, so they are left intact.
        """

        canonical_documents = []
        for document in catalog.documents:
            doc_id = _as_text(document.document_id)
            if not doc_id or is_canonical_document_id(doc_id):
                canonical_documents.append(document)
                continue
            version_hash = build_document_semantics(document)["document"]["version_hash"]
            canonical_id = derive_canonical_id_from_legacy(
                doc_id, msn_id=msn_id, version_hash=version_hash
            )
            canonical_documents.append(
                dataclasses.replace(document, document_id=canonical_id)
            )
        return dataclasses.replace(catalog, documents=tuple(canonical_documents))

    def _db_mtime_ns(self) -> int:
        try:
            return int(self._db_file.stat().st_mtime_ns)
        except OSError:
            return 0

    def read_authoritative_datum_documents(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        normalized_request = (
            request
            if isinstance(request, AuthoritativeDatumDocumentRequest)
            else AuthoritativeDatumDocumentRequest.from_dict(request)
        )
        tenant_id = normalized_request.tenant_id
        db_mtime = self._db_mtime_ns()
        # Per-instance cache first (preserved for tests that introspect state).
        cached = self._catalog_cache.get(tenant_id)
        if cached is not None and cached[0] == db_mtime:
            return cached[1]
        # Phase 14c: module-level cache shared across instances. Auto-
        # invalidates on db_mtime change (any write bumps it).
        global_key = (str(self._db_file.resolve()), tenant_id)
        global_cached = _GLOBAL_CATALOG_CACHE.get(global_key)
        if global_cached is not None and global_cached[0] == db_mtime:
            self._catalog_cache[tenant_id] = global_cached
            return global_cached[1]

        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if row is None:
                result = AuthoritativeDatumDocumentCatalogResult(
                    tenant_id=tenant_id,
                    documents=(),
                    source_files={},
                    readiness_status={"authoritative_catalog": "missing"},
                    warnings=("sql_authoritative_catalog_missing",),
                )
                self._catalog_cache[tenant_id] = (db_mtime, result)
                _GLOBAL_CATALOG_CACHE[global_key] = (db_mtime, result)
                return result
            payload = loads_json(row["payload_json"])
            self._project_canonical_document_ids(connection, tenant_id, payload)
        result = AuthoritativeDatumDocumentCatalogResult.from_dict(payload)
        self._catalog_cache[tenant_id] = (db_mtime, result)
        _GLOBAL_CATALOG_CACHE[global_key] = (db_mtime, result)
        return result

    def _project_canonical_document_ids(
        self,
        connection: Any,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Phase E4: project canonical document ids over a catalog payload.

        Looks up each ``document_id`` in the ``documents`` table; if the row was
        seeded by the migration script (``legacy_alias`` matching the legacy
        identifier or ``document_id`` itself canonical), the catalog payload is
        rewritten in-place to:

        * carry the canonical identifier on ``documents[].document_id``
        * retain the original legacy identifier under
          ``documents[].document_metadata.legacy_alias`` for one-cycle
          compatibility
        """

        documents = payload.get("documents")
        if not isinstance(documents, list) or not documents:
            return
        cursor = connection.execute(
            "SELECT id, document_id, name, is_anchor, version_hash, created_at "
            "FROM documents WHERE tenant_id = ? ORDER BY created_at DESC, id DESC",
            (tenant_id,),
        )
        semantics_version_by_id = {
            str(row["document_id"]).strip(): _normalize_version_hash_token(row["version_hash"])
            for row in connection.execute(
                "SELECT document_id, version_hash FROM datum_document_semantics WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()
        }
        canonical_by_id: dict[str, dict[str, Any]] = {}
        canonical_by_id_version: dict[tuple[str, str], dict[str, Any]] = {}
        for row in cursor.fetchall():
            doc_id = str(row["document_id"]).strip()
            if not doc_id:
                continue
            normalized_version = _normalize_version_hash_token(row["version_hash"])
            details = {
                "document_id": doc_id,
                "canonical_name": str(row["name"] or "").strip(),
                "is_anchor": bool(row["is_anchor"]),
                "version_hash": normalized_version,
            }
            canonical_by_id_version[(doc_id, normalized_version)] = details
            canonical_by_id.setdefault(doc_id, details)
        if not canonical_by_id:
            return
        for entry in documents:
            if not isinstance(entry, dict):
                continue
            stored_id = str(entry.get("document_id") or "").strip()
            if not stored_id:
                continue
            stored_version = (
                _normalize_version_hash_token(entry.get("version_hash"))
                or semantics_version_by_id.get(stored_id, "")
            )
            metadata = entry.get("document_metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            details = (
                canonical_by_id_version.get((stored_id, stored_version))
                or canonical_by_id.get(stored_id)
            )
            if details is None:
                continue
            projected_id = str(details.get("document_id") or "").strip()
            if projected_id:
                entry["document_id"] = projected_id
            if str(details.get("canonical_name") or "").strip():
                entry["canonical_name"] = str(details.get("canonical_name") or "").strip()
            entry["is_anchor"] = bool(details.get("is_anchor")) or bool(entry.get("is_anchor"))
            entry["document_metadata"] = metadata

    def read_system_resource_workbench(self, request: SystemDatumStoreRequest) -> SystemDatumWorkbenchResult:
        normalized_request = (
            request if isinstance(request, SystemDatumStoreRequest) else SystemDatumStoreRequest.from_dict(request)
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM system_workbench_snapshots WHERE tenant_id = ?",
                (normalized_request.tenant_id,),
            ).fetchone()
            if row is None:
                return SystemDatumWorkbenchResult(
                    tenant_id=normalized_request.tenant_id,
                    rows=(),
                    source_files={},
                    materialization_status={"canonical_source": "missing", "authoritative_catalog": "missing"},
                    warnings=("sql_system_workbench_missing",),
                )
            payload = loads_json(row["payload_json"])
            self._project_canonical_source_documents(connection, normalized_request.tenant_id, payload)
        return _workbench_from_payload(payload)

    def _project_canonical_source_documents(
        self,
        connection: Any,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Retired no-op (2026-05-27 legacy_alias retirement).

        This previously extended ``source_files`` with canonical-keyed entries
        derived from ``documents.legacy_alias``. With the legacy-alias column
        retired and every payload keyed by canonical document_id, there is no
        legacy id to project; ``source_files`` is already canonical. Kept as a
        no-op so callers need not change.
        """
        return

    def read_publication_tenant_summary(
        self,
        request: PublicationTenantSummaryRequest,
    ) -> PublicationTenantSummaryResult:
        normalized_request = (
            request
            if isinstance(request, PublicationTenantSummaryRequest)
            else PublicationTenantSummaryRequest.from_dict(request)
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM publication_summary_snapshots
                WHERE tenant_id = ? AND tenant_domain = ?
                """,
                (normalized_request.tenant_id, normalized_request.tenant_domain),
            ).fetchone()
        if row is None:
            return PublicationTenantSummaryResult(
                source=None,
                resolution_status={"publication_summary": "missing"},
                warnings=("sql_publication_summary_missing",),
            )
        return PublicationTenantSummaryResult.from_dict(loads_json(row["payload_json"]))

    def read_document_version_identity(self, *, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        normalized_request = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        document_token = _as_text(document_id)
        if not document_token:
            raise ValueError("document_id is required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT policy, version_hash, canonical_payload_json
                FROM datum_document_semantics
                WHERE tenant_id = ? AND document_id = ?
                """,
                (normalized_request.tenant_id, document_token),
            ).fetchone()
            if row is None:
                # Post-2026-05-17 reconciliation: every payload is keyed by
                # canonical document_id. The legacy_alias dual-lookup was
                # retired (see docs/contracts/mos_authority_enforcement.md).
                return None
        return {
            "policy": row["policy"],
            "version_hash": row["version_hash"],
            "canonical_payload": loads_json(row["canonical_payload_json"]),
        }

    def read_datum_semantic_identity(
        self,
        *,
        tenant_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any] | None:
        normalized_request = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        document_token = _as_text(document_id)
        datum_token = _as_text(datum_address)
        if not document_token:
            raise ValueError("document_id is required")
        if not datum_token:
            raise ValueError("datum_address is required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT policy, semantic_hash, hyphae_hash, hyphae_chain_json, local_references_json, warnings_json
                FROM datum_row_semantics
                WHERE tenant_id = ? AND document_id = ? AND datum_address = ?
                """,
                (normalized_request.tenant_id, document_token, datum_token),
            ).fetchone()
            # Post-2026-05-17 reconciliation: legacy_alias dual-lookup retired.
        if row is None:
            return None
        return {
            "policy": row["policy"],
            "semantic_hash": row["semantic_hash"],
            "hyphae_hash": row["hyphae_hash"],
            "hyphae_chain": loads_json(row["hyphae_chain_json"]),
            "local_references": loads_json(row["local_references_json"]),
            "warnings": loads_json(row["warnings_json"]),
        }

    def _catalog_with_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> tuple[AuthoritativeDatumDocumentCatalogResult, AuthoritativeDatumDocument]:
        catalog = self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
        for document in catalog.documents:
            if document.document_id == _as_text(document_id):
                return catalog, document
        raise ValueError("authoritative_document_missing")

    def _persist_updated_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        updated_document: AuthoritativeDatumDocument,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        catalog = self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
        documents: list[AuthoritativeDatumDocument] = []
        found = False
        for document in catalog.documents:
            if document.document_id == _as_text(document_id):
                documents.append(updated_document)
                found = True
            else:
                documents.append(document)
        if not found:
            raise ValueError("authoritative_document_missing")
        next_catalog = AuthoritativeDatumDocumentCatalogResult(
            tenant_id=catalog.tenant_id,
            documents=tuple(documents),
            source_files=dict(catalog.source_files),
            readiness_status=dict(catalog.readiness_status),
            warnings=tuple(catalog.warnings),
        )
        self.store_authoritative_catalog(next_catalog)
        return self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))

    def replace_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        updated_document: AuthoritativeDatumDocument,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        normalized_document = (
            updated_document
            if isinstance(updated_document, AuthoritativeDatumDocument)
            else AuthoritativeDatumDocument.from_dict(updated_document)
        )
        if normalized_document.document_id != _as_text(document_id):
            raise ValueError("updated_document.document_id must match document_id")
        return self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=normalized_document,
        )

    def delete_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        catalog = self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
        remaining = [d for d in catalog.documents if d.document_id != _as_text(document_id)]
        if len(remaining) == len(catalog.documents):
            raise ValueError("authoritative_document_missing")
        next_catalog = AuthoritativeDatumDocumentCatalogResult(
            tenant_id=catalog.tenant_id,
            documents=tuple(remaining),
            source_files=dict(catalog.source_files),
            readiness_status=dict(catalog.readiness_status),
            warnings=tuple(catalog.warnings),
        )
        self.store_authoritative_catalog(next_catalog)
        return self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))

    def preview_document_insert(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
        raw: Any,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_insert_mutation(document, target_address=target_address, raw=raw)
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_insert(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
        raw: Any,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_insert_mutation(document, target_address=target_address, raw=raw)
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def preview_document_delete(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_delete_mutation(document, target_address=target_address)
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_delete(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_delete_mutation(document, target_address=target_address)
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def preview_document_move(
        self,
        *,
        tenant_id: str,
        document_id: str,
        source_address: str,
        destination_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_move_mutation(
            document,
            source_address=source_address,
            destination_address=destination_address,
        )
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_move(
        self,
        *,
        tenant_id: str,
        document_id: str,
        source_address: str,
        destination_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_move_mutation(
            document,
            source_address=source_address,
            destination_address=destination_address,
        )
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def write_publication_profile_basics(
        self,
        request: PublicationProfileBasicsWriteRequest,
    ) -> PublicationProfileBasicsWriteResult:
        normalized_request = (
            request
            if isinstance(request, PublicationProfileBasicsWriteRequest)
            else PublicationProfileBasicsWriteRequest.from_dict(request)
        )
        current = self.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
            )
        )
        if current.source is None:
            raise ValueError("No SQL-backed publication summary exists for the requested tenant domain.")

        next_source = current.source.to_dict()
        tenant_profile = dict(next_source.get("tenant_profile") or {})
        tenant_profile["title"] = normalized_request.profile_title
        tenant_profile["summary"] = normalized_request.profile_summary
        tenant_profile["contact_email"] = normalized_request.contact_email
        tenant_profile["public_website_url"] = normalized_request.public_website_url
        next_source["tenant_profile"] = tenant_profile

        result = PublicationTenantSummaryResult(
            source=next_source,
            resolution_status=dict(current.resolution_status),
            warnings=tuple(current.warnings),
        )
        self.store_publication_summary(
            result,
            tenant_id=normalized_request.tenant_id,
            tenant_domain=normalized_request.tenant_domain,
        )
        confirmed = self.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
            )
        )
        if confirmed.source is None:
            raise ValueError("SQL publication profile basics read-after-write confirmation failed.")
        return PublicationProfileBasicsWriteResult(
            source=confirmed.source,
            resolution_status=confirmed.resolution_status,
            warnings=confirmed.warnings,
        )
