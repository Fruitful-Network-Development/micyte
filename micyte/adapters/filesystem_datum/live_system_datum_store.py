from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from micyte.core.document_naming import (
    CanonicalNameError,
    derive_canonical_id_from_legacy,
    parse_canonical_document_id,
)
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentCatalogResult,
    AuthoritativeDatumDocumentRequest,
    AuthoritativeDatumDocumentRow,
    PublicationProfileBasicsWriteRequest,
    PublicationProfileBasicsWriteResult,
    PublicationTenantSummaryRequest,
    PublicationTenantSummaryResult,
    PublicationTenantSummarySource,
    SystemDatumResourceRow,
    SystemDatumStorePort,
    SystemDatumStoreRequest,
    SystemDatumWorkbenchResult,
)

_PARALLEL_PREFETCH_MAX_WORKERS = 8
_PARALLEL_PREFETCH_WARM_THRESHOLD = 0.8

def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(_as_text(item) for item in value if _as_text(item))
    token = _as_text(value)
    return (token,) if token else ()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _split_document_payload(payload: dict[str, Any]) -> tuple[tuple[AuthoritativeDatumDocumentRow, ...], dict[str, Any]]:
    row_source: dict[str, Any] = payload
    metadata: dict[str, Any] = {}
    if isinstance(payload.get("datum_addressing_abstraction_space"), dict):
        row_source = payload.get("datum_addressing_abstraction_space") or {}
        metadata = {
            key: value for key, value in payload.items() if key != "datum_addressing_abstraction_space"
        }
    rows = tuple(
        AuthoritativeDatumDocumentRow(datum_address=datum_address, raw=raw)
        for datum_address, raw in row_source.items()
    )
    return rows, metadata


def _read_document_rows_and_metadata(path: Path) -> tuple[tuple[AuthoritativeDatumDocumentRow, ...], dict[str, Any]]:
    payload = _read_json_object(path)
    return _split_document_payload(payload)


def _load_anchor_document(path: Path | None) -> tuple[str, str, dict[str, Any], tuple[AuthoritativeDatumDocumentRow, ...], list[str]]:
    if path is None:
        return "", "", {}, (), []
    warnings: list[str] = []
    try:
        rows, metadata = _read_document_rows_and_metadata(path)
    except FileNotFoundError:
        warnings.append(f"Supporting sandbox anchor document is missing at {path}.")
        return path.name, str(path), {}, (), warnings
    except json.JSONDecodeError:
        warnings.append(f"Supporting sandbox anchor document is not valid JSON at {path}.")
        return path.name, str(path), {}, (), warnings
    except ValueError:
        warnings.append(f"Supporting sandbox anchor document must be a JSON object at {path}.")
        return path.name, str(path), {}, (), warnings
    return path.name, str(path), metadata, rows, warnings


def _canonical_tool_public_id(value: object) -> str:
    return _as_text(value).lower()


def _find_tool_anchor_file(tool_dir: Path) -> Path | None:
    candidates: list[Path] = []
    for pattern in ("tool*.json",):
        candidates.extend(sorted(tool_dir.glob(pattern)))
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    candidates = deduped
    return candidates[0] if candidates else None


def _iter_sandbox_source_files(source_dir: Path, *, tool_id: str) -> list[Path]:
    candidates = list(sorted(source_dir.glob("*.json")))
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _document_id_for_path(*, source_kind: str, tool_id: str, path: Path) -> str:
    if source_kind == "system_anthology":
        return "system:anthology"
    return f"sandbox:{tool_id}:{path.name}"


def _canonical_name_for_legacy_document_id(document_id: str) -> str:
    try:
        return parse_canonical_document_id(
            derive_canonical_id_from_legacy(
                document_id,
                msn_id="X",
                version_hash="0" * 64,
            )
        ).name
    except CanonicalNameError:
        return ""


def _extract_row(resource_id: str, raw: Any) -> SystemDatumResourceRow:
    subject_ref = resource_id
    relation = ""
    object_ref = ""
    labels: tuple[str, ...] = ()

    if isinstance(raw, list) and raw:
        triple = raw[0]
        if isinstance(triple, list):
            subject_ref = _as_text(triple[0] if len(triple) > 0 else resource_id) or resource_id
            relation = _as_text(triple[1] if len(triple) > 1 else "")
            object_ref = _as_text(triple[2] if len(triple) > 2 else "")
        if len(raw) > 1:
            labels = _as_text_tuple(raw[1])
    elif isinstance(raw, dict):
        subject_ref = _as_text(raw.get("subject_ref") or raw.get("subject") or resource_id) or resource_id
        relation = _as_text(raw.get("relation") or raw.get("predicate"))
        object_ref = _as_text(raw.get("object_ref") or raw.get("object"))
        labels = _as_text_tuple(raw.get("labels") or raw.get("label") or raw.get("name"))

    return SystemDatumResourceRow(
        resource_id=resource_id,
        subject_ref=subject_ref,
        relation=relation,
        object_ref=object_ref,
        labels=labels,
        raw=raw,
    )


class FilesystemSystemDatumStoreAdapter(SystemDatumStorePort):
    def __init__(self, data_dir: str | Path, *, public_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._public_dir = None if public_dir is None else Path(public_dir)
        self._path_capabilities: dict[str, Path] = {}
        self._rows_metadata_cache: dict[
            str,
            tuple[
                tuple[bool, int, int],
                tuple[AuthoritativeDatumDocumentRow, ...] | None,
                dict[str, Any] | None,
                Exception | None,
            ],
        ] = {}
        self._anchor_document_cache: dict[
            str,
            tuple[
                tuple[bool, int, int],
                tuple[str, str, dict[str, Any], tuple[AuthoritativeDatumDocumentRow, ...], list[str]],
            ],
        ] = {}

    def with_path_capabilities(
        self,
        *,
        system_anthology_file: str | Path | None = None,
        system_sources_dir: str | Path | None = None,
        payload_cache_dir: str | Path | None = None,
        sandbox_root_dir: str | Path | None = None,
    ) -> FilesystemSystemDatumStoreAdapter:
        if system_anthology_file is not None:
            self._path_capabilities["system_anthology_file"] = Path(system_anthology_file)
        if system_sources_dir is not None:
            self._path_capabilities["system_sources_dir"] = Path(system_sources_dir)
        if payload_cache_dir is not None:
            self._path_capabilities["payload_cache_dir"] = Path(payload_cache_dir)
        if sandbox_root_dir is not None:
            self._path_capabilities["sandbox_root_dir"] = Path(sandbox_root_dir)
        return self

    def _resolve_path(self, key: str, fallback: Path) -> Path:
        return self._path_capabilities.get(key, fallback)

    def _relative_or_absolute(self, path: Path) -> str:
        # Keep catalog metadata portable across hosts by preferring DATA_DIR-relative
        # source paths whenever the source lives beneath the configured data root.
        try:
            return str(path.relative_to(self._data_dir))
        except Exception:
            return str(path)

    @staticmethod
    def _path_signature(path: Path) -> tuple[bool, int, int]:
        try:
            stat = path.stat()
        except OSError:
            return (False, 0, 0)
        return (path.is_file(), int(stat.st_mtime_ns), int(stat.st_size))

    def _cached_read_document_rows_and_metadata(
        self,
        path: Path,
    ) -> tuple[tuple[AuthoritativeDatumDocumentRow, ...], dict[str, Any]]:
        cache_key = str(path)
        signature = self._path_signature(path)
        cached = self._rows_metadata_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            if cached[3] is not None:
                raise cached[3]
            return tuple(cached[1] or ()), dict(cached[2] or {})

        try:
            rows, metadata = _read_document_rows_and_metadata(path)
        except Exception as exc:
            self._rows_metadata_cache[cache_key] = (signature, None, None, exc)
            raise

        self._rows_metadata_cache[cache_key] = (signature, rows, metadata, None)
        return rows, metadata

    def _prefetch_document_rows_and_metadata(self, paths: list[Path]) -> None:
        cold_paths = [path for path in paths if str(path) not in self._rows_metadata_cache]
        if len(paths) == 0 or len(cold_paths) <= max(1, len(paths) // 5):
            return
        from concurrent.futures import ThreadPoolExecutor

        max_workers = min(8, len(cold_paths))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for _ in pool.map(self._safe_prefetch_one, cold_paths):
                pass

    def _safe_prefetch_one(self, path: Path) -> None:
        try:
            self._cached_read_document_rows_and_metadata(path)
        except Exception:
            pass

    def _cached_load_anchor_document(
        self,
        path: Path | None,
    ) -> tuple[str, str, dict[str, Any], tuple[AuthoritativeDatumDocumentRow, ...], list[str]]:
        if path is None:
            return "", "", {}, (), []
        cache_key = str(path)
        signature = self._path_signature(path)
        cached = self._anchor_document_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            name, anchor_path, metadata, rows, warnings = cached[1]
            return name, anchor_path, dict(metadata), tuple(rows), list(warnings)

        warnings: list[str] = []
        anchor_display_path = self._relative_or_absolute(path)
        try:
            rows, metadata = self._cached_read_document_rows_and_metadata(path)
        except FileNotFoundError:
            warnings.append(f"Supporting sandbox anchor document is missing at {anchor_display_path}.")
            result = (path.name, anchor_display_path, {}, (), warnings)
            self._anchor_document_cache[cache_key] = (signature, result)
            return result
        except json.JSONDecodeError:
            warnings.append(f"Supporting sandbox anchor document is not valid JSON at {anchor_display_path}.")
            result = (path.name, anchor_display_path, {}, (), warnings)
            self._anchor_document_cache[cache_key] = (signature, result)
            return result
        except ValueError:
            warnings.append(f"Supporting sandbox anchor document must be a JSON object at {anchor_display_path}.")
            result = (path.name, anchor_display_path, {}, (), warnings)
            self._anchor_document_cache[cache_key] = (signature, result)
            return result

        result = (path.name, anchor_display_path, dict(metadata), tuple(rows), warnings)
        self._anchor_document_cache[cache_key] = (signature, result)
        return result

    def _prefetch_sandbox_source_documents(self, tool_dirs: list[Path]) -> None:
        paths: list[Path] = []
        for tool_dir in tool_dirs:
            source_dir = tool_dir / "sources"
            if not source_dir.exists() or not source_dir.is_dir():
                continue
            public_tool_id = _canonical_tool_public_id(tool_dir.name)
            paths.extend(_iter_sandbox_source_files(source_dir, tool_id=public_tool_id))
        if not paths:
            return
        cold_paths = [path for path in paths if str(path) not in self._rows_metadata_cache]
        warm_ratio = (len(paths) - len(cold_paths)) / len(paths)
        if warm_ratio >= _PARALLEL_PREFETCH_WARM_THRESHOLD:
            return
        worker_count = min(_PARALLEL_PREFETCH_MAX_WORKERS, len(cold_paths))

        def _prime(path: Path) -> None:
            try:
                self._cached_read_document_rows_and_metadata(path)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            list(pool.map(_prime, cold_paths))

    def read_authoritative_datum_documents(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        normalized_request = (
            request
            if isinstance(request, AuthoritativeDatumDocumentRequest)
            else AuthoritativeDatumDocumentRequest.from_dict(request)
        )
        anthology_file = self._resolve_path("system_anthology_file", self._data_dir / "system" / "anthology.json")
        system_source_files = sorted(
            self._resolve_path("system_sources_dir", self._data_dir / "system" / "sources").glob("*.json")
        )
        payload_cache_files = sorted(
            self._resolve_path("payload_cache_dir", self._data_dir / "payloads" / "cache").glob("*.json")
        )

        documents: list[AuthoritativeDatumDocument] = []
        warnings: list[str] = []
        anthology_status = "missing"

        if not anthology_file.exists() or not anthology_file.is_file():
            warnings.append("Canonical system anthology is missing at data/system/anthology.json.")
        else:
            try:
                rows, metadata = self._cached_read_document_rows_and_metadata(anthology_file)
                documents.append(
                    AuthoritativeDatumDocument(
                        document_id=_document_id_for_path(
                            source_kind="system_anthology",
                            tool_id="",
                            path=anthology_file,
                        ),
                        source_kind="system_anthology",
                        document_name=anthology_file.name,
                        canonical_name="anthology",
                        relative_path=self._relative_or_absolute(anthology_file),
                        document_metadata={
                            **dict(metadata),
                            "legacy_alias": "system:anthology",
                        },
                        is_anchor=True,
                        rows=rows,
                    )
                )
                anthology_status = "loaded"
            except json.JSONDecodeError:
                anthology_status = "invalid"
                warnings.append("Canonical system anthology is not valid JSON.")
            except ValueError:
                anthology_status = "invalid"
                warnings.append("Canonical system anthology must be a JSON object.")

        sandbox_source_files: list[Path] = []
        sandbox_anchor_files: list[Path] = []
        seen_sandbox_document_ids: set[str] = set()
        sandbox_root = self._resolve_path("sandbox_root_dir", self._data_dir / "sandbox")
        if sandbox_root.exists() and sandbox_root.is_dir():
            sorted_tool_dirs = sorted(path for path in sandbox_root.iterdir() if path.is_dir())
            self._prefetch_sandbox_source_documents(sorted_tool_dirs)
            for tool_dir in sorted_tool_dirs:
                source_dir = tool_dir / "sources"
                anchor_file = _find_tool_anchor_file(tool_dir)
                if (not source_dir.exists() or not source_dir.is_dir()) and anchor_file is None:
                    continue
                public_tool_id = _canonical_tool_public_id(tool_dir.name)
                if anchor_file is not None:
                    anchor_document_id = _document_id_for_path(
                        source_kind="sandbox_source",
                        tool_id=public_tool_id,
                        path=anchor_file,
                    )
                    if anchor_document_id not in seen_sandbox_document_ids:
                        seen_sandbox_document_ids.add(anchor_document_id)
                        sandbox_anchor_files.append(anchor_file)
                        anchor_signature = self._path_signature(anchor_file)
                        anchor_warnings: list[str] = []
                        try:
                            anchor_rows, anchor_metadata = self._cached_read_document_rows_and_metadata(anchor_file)
                        except json.JSONDecodeError:
                            anchor_rows = ()
                            anchor_metadata = {}
                            anchor_warnings.append(
                                f"Sandbox anchor document is not valid JSON at {self._relative_or_absolute(anchor_file)}."
                            )
                        except ValueError:
                            anchor_rows = ()
                            anchor_metadata = {}
                            anchor_warnings.append(
                                f"Sandbox anchor document must be a JSON object at {self._relative_or_absolute(anchor_file)}."
                            )
                        anchor_metadata_with_cache = {
                            **dict(anchor_metadata),
                            "legacy_alias": anchor_document_id,
                            "__filesystem_cache__": {
                                "source_signature": {
                                    "exists": bool(anchor_signature[0]),
                                    "mtime_ns": int(anchor_signature[1]),
                                    "size": int(anchor_signature[2]),
                                },
                                "anchor_signature": {
                                    "exists": bool(anchor_signature[0]),
                                    "mtime_ns": int(anchor_signature[1]),
                                    "size": int(anchor_signature[2]),
                                },
                            },
                        }
                        documents.append(
                            AuthoritativeDatumDocument(
                                document_id=anchor_document_id,
                                source_kind="sandbox_source",
                                document_name=anchor_file.name,
                                canonical_name=_canonical_name_for_legacy_document_id(anchor_document_id) or "anchor",
                                relative_path=self._relative_or_absolute(anchor_file),
                                tool_id=public_tool_id,
                                document_metadata=anchor_metadata_with_cache,
                                is_anchor=True,
                                anchor_document_name=anchor_file.name,
                                anchor_document_path=self._relative_or_absolute(anchor_file),
                                anchor_document_metadata=dict(anchor_metadata_with_cache),
                                anchor_rows=anchor_rows,
                                rows=anchor_rows,
                                warnings=tuple(anchor_warnings),
                            )
                        )
                if not source_dir.exists() or not source_dir.is_dir():
                    continue
                _sandbox_paths = list(_iter_sandbox_source_files(source_dir, tool_id=public_tool_id))
                self._prefetch_document_rows_and_metadata(_sandbox_paths)
                for source_path in _sandbox_paths:
                    source_signature = self._path_signature(source_path)
                    anchor_signature = self._path_signature(anchor_file) if anchor_file is not None else (False, 0, 0)
                    document_id = _document_id_for_path(
                        source_kind="sandbox_source",
                        tool_id=public_tool_id,
                        path=source_path,
                    )
                    if document_id in seen_sandbox_document_ids:
                        continue
                    seen_sandbox_document_ids.add(document_id)
                    sandbox_source_files.append(source_path)
                    source_warnings: list[str] = []
                    try:
                        rows, metadata = self._cached_read_document_rows_and_metadata(source_path)
                    except json.JSONDecodeError:
                        rows = ()
                        metadata = {}
                        source_warnings.append(
                            f"Sandbox source document is not valid JSON at {self._relative_or_absolute(source_path)}."
                        )
                    except ValueError:
                        rows = ()
                        metadata = {}
                        source_warnings.append(
                            f"Sandbox source document must be a JSON object at {self._relative_or_absolute(source_path)}."
                        )
                    metadata_with_cache = {
                        **dict(metadata),
                        "legacy_alias": document_id,
                        "__filesystem_cache__": {
                            "source_signature": {
                                "exists": bool(source_signature[0]),
                                "mtime_ns": int(source_signature[1]),
                                "size": int(source_signature[2]),
                            },
                            "anchor_signature": {
                                "exists": bool(anchor_signature[0]),
                                "mtime_ns": int(anchor_signature[1]),
                                "size": int(anchor_signature[2]),
                            },
                        },
                    }

                    (
                        anchor_document_name,
                        anchor_document_path,
                        anchor_document_metadata,
                        anchor_rows,
                        anchor_warnings,
                    ) = self._cached_load_anchor_document(anchor_file)
                    source_warnings.extend(anchor_warnings)

                    documents.append(
                        AuthoritativeDatumDocument(
                            document_id=document_id,
                            source_kind="sandbox_source",
                            document_name=source_path.name,
                            canonical_name=_canonical_name_for_legacy_document_id(document_id),
                            relative_path=self._relative_or_absolute(source_path),
                            tool_id=public_tool_id,
                            document_metadata=metadata_with_cache,
                            is_anchor=False,
                            anchor_document_name=anchor_document_name,
                            anchor_document_path=anchor_document_path,
                            anchor_document_metadata=anchor_document_metadata,
                            anchor_rows=anchor_rows,
                            rows=rows,
                            warnings=tuple(source_warnings),
                        )
                    )

        if not system_source_files:
            warnings.append("No canonical system source JSON files were found under data/system/sources.")
        if not payload_cache_files:
            warnings.append("No derived payload cache JSON files were found under data/payloads/cache.")

        derived_materialization = "present"
        if not system_source_files and not payload_cache_files:
            derived_materialization = "missing"
        elif not system_source_files or not payload_cache_files:
            derived_materialization = "partial"

        authoritative_catalog = "loaded" if documents else "missing"

        return AuthoritativeDatumDocumentCatalogResult(
            tenant_id=normalized_request.tenant_id,
            documents=tuple(documents),
            source_files={
                "anthology": self._relative_or_absolute(anthology_file),
                "sandbox_anchor_documents": [self._relative_or_absolute(path) for path in sandbox_anchor_files],
                "sandbox_source_documents": [self._relative_or_absolute(path) for path in sandbox_source_files],
                "system_sources": [self._relative_or_absolute(path) for path in system_source_files],
                "payload_cache": [self._relative_or_absolute(path) for path in payload_cache_files],
            },
            readiness_status={
                "authoritative_catalog": authoritative_catalog,
                "anthology_status": anthology_status,
                "sandbox_anchor_document_count": len(sandbox_anchor_files),
                "sandbox_source_document_count": len(sandbox_source_files),
                "system_source_count": len(system_source_files),
                "payload_cache_count": len(payload_cache_files),
                "derived_materialization": derived_materialization,
            },
            warnings=tuple(warnings),
        )

    def read_system_resource_workbench(self, request: SystemDatumStoreRequest) -> SystemDatumWorkbenchResult:
        normalized_request = (
            request if isinstance(request, SystemDatumStoreRequest) else SystemDatumStoreRequest.from_dict(request)
        )
        catalog = self.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=normalized_request.tenant_id)
        )
        system_document = next(
            (document for document in catalog.documents if document.source_kind == "system_anthology"),
            None,
        )
        rows: list[SystemDatumResourceRow] = []
        if system_document is not None:
            rows = [
                _extract_row(row.datum_address, row.raw)
                for row in sorted(system_document.rows, key=lambda item: item.datum_address)
            ]

        return SystemDatumWorkbenchResult(
            tenant_id=normalized_request.tenant_id,
            rows=tuple(rows),
            source_files=catalog.source_files,
            materialization_status={
                "canonical_source": catalog.readiness_status.get("anthology_status"),
                "authoritative_catalog": catalog.readiness_status.get("authoritative_catalog"),
                "sandbox_anchor_document_count": catalog.readiness_status.get("sandbox_anchor_document_count"),
                "sandbox_source_document_count": catalog.readiness_status.get("sandbox_source_document_count"),
                "derived_materialization": catalog.readiness_status.get("derived_materialization"),
                "system_source_count": catalog.readiness_status.get("system_source_count"),
                "payload_cache_count": catalog.readiness_status.get("payload_cache_count"),
            },
            warnings=tuple(catalog.warnings),
        )

    def read_publication_tenant_summary(
        self,
        request: PublicationTenantSummaryRequest,
    ) -> PublicationTenantSummaryResult:
        normalized_request = (
            request
            if isinstance(request, PublicationTenantSummaryRequest)
            else PublicationTenantSummaryRequest.from_dict(request)
        )
        (
            profile_id,
            public_profile,
            _public_status,
            tenant_profile,
            _tenant_status,
            resolution_status,
            warnings,
        ) = self._resolve_publication_profiles(
            tenant_domain=normalized_request.tenant_domain,
        )
        if not profile_id:
            return PublicationTenantSummaryResult(
                source=None,
                resolution_status=resolution_status,
                warnings=tuple(warnings),
            )
        return PublicationTenantSummaryResult(
            source=PublicationTenantSummarySource(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
                profile_id=profile_id,
                public_profile=public_profile,
                tenant_profile=tenant_profile,
            ),
            resolution_status=resolution_status,
            warnings=tuple(warnings),
        )

    def write_publication_profile_basics(
        self,
        request: PublicationProfileBasicsWriteRequest,
    ) -> PublicationProfileBasicsWriteResult:
        normalized_request = (
            request
            if isinstance(request, PublicationProfileBasicsWriteRequest)
            else PublicationProfileBasicsWriteRequest.from_dict(request)
        )
        (
            profile_id,
            _public_profile,
            _public_status,
            tenant_profile,
            tenant_status,
            _resolution_status,
            _warnings,
        ) = self._resolve_publication_profiles(
            tenant_domain=normalized_request.tenant_domain,
        )
        if not profile_id:
            raise ValueError(
                "No canonical publication profile mapping was found for the requested tenant domain."
            )
        if self._public_dir is None:
            raise ValueError("Publication profile basics write requires public_dir.")
        if tenant_status == "invalid":
            raise ValueError("The resolved tenant publication profile document is invalid JSON.")

        next_payload = dict(tenant_profile or {})
        next_payload["title"] = normalized_request.profile_title
        next_payload["summary"] = normalized_request.profile_summary
        next_payload["contact_email"] = normalized_request.contact_email
        next_payload["public_website_url"] = normalized_request.public_website_url

        target_path = _tenant_profile_path(public_dir=self._public_dir, profile_id=profile_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(next_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        confirmed = self.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
            )
        )
        if confirmed.source is None:
            raise ValueError("Publication profile basics read-after-write confirmation failed.")
        return PublicationProfileBasicsWriteResult(
            source=confirmed.source,
            resolution_status=confirmed.resolution_status,
            warnings=confirmed.warnings,
        )

    def _resolve_publication_profiles(
        self,
        *,
        tenant_domain: str,
    ) -> tuple[
        str,
        dict[str, Any] | None,
        str,
        dict[str, Any] | None,
        str,
        dict[str, Any],
        list[str],
    ]:
        anthology_file = self._data_dir / "system" / "anthology.json"
        warnings: list[str] = []
        resolution_status: dict[str, Any] = {
            "anthology": "missing",
            "domain_match": "missing",
            "public_profile": "missing",
            "tenant_profile": "missing",
        }

        if not anthology_file.exists() or not anthology_file.is_file():
            warnings.append("Canonical system anthology is missing at data/system/anthology.json.")
            return "", None, "missing", None, "missing", resolution_status, warnings

        try:
            anthology_payload = _read_json_object(anthology_file)
        except (json.JSONDecodeError, ValueError):
            warnings.append("Canonical system anthology is not a valid JSON object.")
            resolution_status["anthology"] = "invalid"
            return "", None, "missing", None, "missing", resolution_status, warnings

        resolution_status["anthology"] = "loaded"
        profile_id = _resolve_profile_id_from_domain(
            anthology_payload=anthology_payload,
            tenant_domain=tenant_domain,
        )
        if not profile_id:
            warnings.append(
                "No canonical publication profile mapping was found for the requested tenant domain."
            )
            return "", None, "missing", None, "missing", resolution_status, warnings

        resolution_status["domain_match"] = "matched"
        public_profile, public_status = _load_publication_profile(
            public_dir=self._public_dir,
            profile_id=profile_id,
            include_fnd=False,
        )
        tenant_profile, tenant_status = _load_publication_profile(
            public_dir=self._public_dir,
            profile_id=profile_id,
            include_fnd=True,
        )
        resolution_status["public_profile"] = public_status
        resolution_status["tenant_profile"] = tenant_status

        if public_status == "missing":
            warnings.append("No public publication profile document was found for the resolved tenant profile.")
        elif public_status == "invalid":
            warnings.append("The resolved public publication profile document is invalid JSON.")
        if tenant_status == "missing":
            warnings.append("No tenant publication profile document was found for the resolved tenant profile.")
        elif tenant_status == "invalid":
            warnings.append("The resolved tenant publication profile document is invalid JSON.")
        return (
            profile_id,
            public_profile,
            public_status,
            tenant_profile,
            tenant_status,
            resolution_status,
            warnings,
        )


def _resolve_profile_id_from_domain(
    *,
    anthology_payload: dict[str, Any],
    tenant_domain: str,
) -> str:
    normalized_domain = _as_text(tenant_domain).lower()
    if not normalized_domain:
        return ""
    for resource_id in sorted(anthology_payload.keys()):
        raw = anthology_payload[resource_id]
        labels = tuple(label.lower() for label in _extract_labels(raw))
        if normalized_domain not in labels:
            continue
        profile_id = _extract_profile_id(raw)
        if profile_id:
            return profile_id
    return ""


def _extract_labels(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, list) and len(raw) > 1:
        return _as_text_tuple(raw[1])
    if isinstance(raw, dict):
        return _as_text_tuple(raw.get("labels") or raw.get("label") or raw.get("name"))
    return ()


def _extract_profile_id(raw: Any) -> str:
    if isinstance(raw, list) and raw:
        triple = raw[0]
        if isinstance(triple, list) and len(triple) > 4:
            return _as_text(triple[4])
    if isinstance(raw, dict):
        return _as_text(raw.get("profile_id") or raw.get("msn_id"))
    return ""


def _candidate_profile_paths(*, public_dir: Path, profile_id: str, include_fnd: bool) -> tuple[Path, ...]:
    candidates = [
        public_dir / f"{profile_id}.json",
        public_dir / f"msn-{profile_id}.json",
        public_dir / f"mss-{profile_id}.json",
    ]
    if include_fnd:
        candidates = [_tenant_profile_path(public_dir=public_dir, profile_id=profile_id)]
    return tuple(candidates)


def _tenant_profile_path(*, public_dir: Path, profile_id: str) -> Path:
    return public_dir / f"fnd-{profile_id}.json"


def _load_publication_profile(
    *,
    public_dir: Path | None,
    profile_id: str,
    include_fnd: bool,
) -> tuple[dict[str, Any] | None, str]:
    if public_dir is None:
        return None, "missing"
    saw_invalid = False
    for path in _candidate_profile_paths(public_dir=public_dir, profile_id=profile_id, include_fnd=include_fnd):
        if not path.exists() or not path.is_file():
            continue
        try:
            return _read_json_object(path), "loaded"
        except (json.JSONDecodeError, ValueError):
            saw_invalid = True
    return None, "invalid" if saw_invalid else "missing"
