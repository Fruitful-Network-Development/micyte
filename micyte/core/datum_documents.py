"""Canonical datum-document value types (the MOS data model).

Relocated here from ``packages/ports/datum_store/contracts.py`` so that ``core``
depends only inward: the datum-document dataclasses are core domain values, and
``core`` modules (``datum_io``, ``datum_ops``, ``datum_semantics``, ``mss``,
``datum_templates``) now import them from here instead of reaching *up* into
``ports`` (which ``core/forbidden_dependencies.md`` forbids). The ``ports`` layer
re-exports these names, so existing ``ports.datum_store`` importers are
unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.core.identities import require_plain_domain

SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA = "mycite.v2.data.system_resource_workbench.surface.v1"
AUTHORITATIVE_DATUM_DOCUMENT_ROW_SCHEMA = "mycite.v2.data.authoritative_document_row.v1"
AUTHORITATIVE_DATUM_DOCUMENT_SCHEMA = "mycite.v2.data.authoritative_document.v1"
AUTHORITATIVE_DATUM_DOCUMENT_CATALOG_SCHEMA = "mycite.v2.data.authoritative_document_catalog.v1"
PUBLICATION_TENANT_SUMMARY_SOURCE_SCHEMA = "mycite.v2.data.publication_tenant_summary.source.v1"
PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA = "mycite.v2.data.publication_profile_basics.write_result.v1"

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_json_value(value: Any, *, field_name: str) -> JsonValue:
    # Hot path: this runs on every row's `raw` for every document on every catalog
    # deserialization (millions of calls for a large tenant). Two behaviour-preserving
    # optimisations vs the naive recursion: (1) don't build a per-element ``field_name``
    # string on every call (it was only ever used in the rare error message); (2) return
    # the input object unchanged when nothing needed coercing, so already-clean JSON
    # (e.g. straight from ``json.loads`` of our own persisted blob) is validated without
    # re-allocating the whole structure. Output is value-identical to the naive form.
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        changed = False
        out: list[JsonValue] = []
        for item in value:
            normalized = _normalize_json_value(item, field_name=field_name)
            out.append(normalized)
            if normalized is not item:
                changed = True
        return out if changed else value
    if isinstance(value, dict):
        changed = False
        out_map: dict[str, JsonValue] = {}
        for key, item in value.items():
            token = key if (type(key) is str and key and key == key.strip()) else _as_text(key)
            if not token:
                raise ValueError(f"{field_name} keys must be non-empty strings")
            normalized = _normalize_json_value(item, field_name=field_name)
            out_map[token] = normalized
            if token is not key or normalized is not item:
                changed = True
        return out_map if changed else value
    raise ValueError(f"{field_name} must be JSON-serializable data")


def _normalize_object_payload(value: Any, *, field_name: str) -> dict[str, JsonValue]:
    normalized = _normalize_json_value(value, field_name=field_name)
    if not isinstance(normalized, dict):
        raise ValueError(f"{field_name} must be a dict")
    return normalized


@dataclass(frozen=True)
class SystemDatumStoreRequest:
    tenant_id: str

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        if not tenant_id:
            raise ValueError("system_datum_store_request.tenant_id is required")
        object.__setattr__(self, "tenant_id", tenant_id)

    def to_dict(self) -> dict[str, str]:
        return {"tenant_id": self.tenant_id}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SystemDatumStoreRequest:
        if not isinstance(payload, dict):
            raise ValueError("system_datum_store_request must be a dict")
        return cls(tenant_id=payload.get("tenant_id"))


@dataclass(frozen=True)
class AuthoritativeDatumDocumentRequest:
    tenant_id: str

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        if not tenant_id:
            raise ValueError("authoritative_datum_document_request.tenant_id is required")
        object.__setattr__(self, "tenant_id", tenant_id)

    def to_dict(self) -> dict[str, str]:
        return {"tenant_id": self.tenant_id}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthoritativeDatumDocumentRequest:
        if not isinstance(payload, dict):
            raise ValueError("authoritative_datum_document_request must be a dict")
        return cls(tenant_id=payload.get("tenant_id"))


@dataclass(frozen=True)
class AuthoritativeDatumDocumentRow:
    datum_address: str
    raw: JsonValue
    schema: str = AUTHORITATIVE_DATUM_DOCUMENT_ROW_SCHEMA

    def __post_init__(self) -> None:
        datum_address = _as_text(self.datum_address)
        if not datum_address:
            raise ValueError("authoritative_datum_document_row.datum_address is required")
        object.__setattr__(self, "datum_address", datum_address)
        object.__setattr__(
            self,
            "raw",
            _normalize_json_value(self.raw, field_name="authoritative_datum_document_row.raw"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "datum_address": self.datum_address,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthoritativeDatumDocumentRow:
        if not isinstance(payload, dict):
            raise ValueError("authoritative_datum_document_row must be a dict")
        return cls(
            datum_address=payload.get("datum_address"),
            raw=payload.get("raw"),
        )


@dataclass(frozen=True)
class AuthoritativeDatumDocument:
    document_id: str
    source_kind: str
    document_name: str
    relative_path: str
    canonical_name: str = ""
    tool_id: str = ""
    source_authority: str = "authoritative"
    document_metadata: dict[str, JsonValue] | None = None
    is_anchor: bool = False
    anchor_document_name: str = ""
    anchor_document_path: str = ""
    anchor_document_metadata: dict[str, JsonValue] | None = None
    anchor_rows: tuple[AuthoritativeDatumDocumentRow | dict[str, Any], ...] = ()
    rows: tuple[AuthoritativeDatumDocumentRow | dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    schema: str = AUTHORITATIVE_DATUM_DOCUMENT_SCHEMA

    def __post_init__(self) -> None:
        document_id = _as_text(self.document_id)
        source_kind = _as_text(self.source_kind).lower()
        document_name = _as_text(self.document_name)
        canonical_name = _as_text(self.canonical_name)
        relative_path = _as_text(self.relative_path)
        tool_id = _as_text(self.tool_id)
        source_authority = _as_text(self.source_authority).lower() or "authoritative"
        if not document_id:
            raise ValueError("authoritative_datum_document.document_id is required")
        if source_kind not in {"system_anthology", "sandbox_source"}:
            raise ValueError("authoritative_datum_document.source_kind is invalid")
        if not document_name:
            raise ValueError("authoritative_datum_document.document_name is required")
        if not relative_path:
            raise ValueError("authoritative_datum_document.relative_path is required")
        if source_authority != "authoritative":
            raise ValueError("authoritative_datum_document.source_authority must be authoritative")

        normalized_anchor_rows: list[AuthoritativeDatumDocumentRow] = []
        for row in self.anchor_rows:
            normalized_anchor_rows.append(
                row if isinstance(row, AuthoritativeDatumDocumentRow) else AuthoritativeDatumDocumentRow.from_dict(row)
            )

        normalized_rows: list[AuthoritativeDatumDocumentRow] = []
        for row in self.rows:
            normalized_rows.append(
                row if isinstance(row, AuthoritativeDatumDocumentRow) else AuthoritativeDatumDocumentRow.from_dict(row)
            )

        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(self, "document_name", document_name)
        object.__setattr__(self, "canonical_name", canonical_name)
        object.__setattr__(self, "relative_path", relative_path)
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "source_authority", source_authority)
        object.__setattr__(
            self,
            "document_metadata",
            _normalize_object_payload(
                self.document_metadata or {},
                field_name="authoritative_datum_document.document_metadata",
            ),
        )
        object.__setattr__(self, "is_anchor", bool(self.is_anchor))
        object.__setattr__(self, "anchor_document_name", _as_text(self.anchor_document_name))
        object.__setattr__(self, "anchor_document_path", _as_text(self.anchor_document_path))
        object.__setattr__(
            self,
            "anchor_document_metadata",
            _normalize_object_payload(
                self.anchor_document_metadata or {},
                field_name="authoritative_datum_document.anchor_document_metadata",
            ),
        )
        object.__setattr__(self, "anchor_rows", tuple(normalized_anchor_rows))
        object.__setattr__(self, "rows", tuple(normalized_rows))
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def anchor_row_count(self) -> int:
        return len(self.anchor_rows)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "document_id": self.document_id,
            "source_kind": self.source_kind,
            "document_name": self.document_name,
            "canonical_name": self.canonical_name,
            "relative_path": self.relative_path,
            "tool_id": self.tool_id,
            "source_authority": self.source_authority,
            "document_metadata": self.document_metadata or {},
            "is_anchor": self.is_anchor,
            "anchor_document_name": self.anchor_document_name,
            "anchor_document_path": self.anchor_document_path,
            "anchor_document_metadata": self.anchor_document_metadata or {},
            "anchor_rows": [row.to_dict() for row in self.anchor_rows],
            "anchor_row_count": self.anchor_row_count,
            "rows": [row.to_dict() for row in self.rows],
            "row_count": self.row_count,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthoritativeDatumDocument:
        if not isinstance(payload, dict):
            raise ValueError("authoritative_datum_document must be a dict")
        anchor_rows = payload.get("anchor_rows") or ()
        if not isinstance(anchor_rows, (list, tuple)):
            raise ValueError("authoritative_datum_document.anchor_rows must be a list")
        rows = payload.get("rows") or ()
        if not isinstance(rows, (list, tuple)):
            raise ValueError("authoritative_datum_document.rows must be a list")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("authoritative_datum_document.warnings must be a list")
        return cls(
            document_id=payload.get("document_id"),
            source_kind=payload.get("source_kind"),
            document_name=payload.get("document_name"),
            canonical_name=payload.get("canonical_name") or "",
            relative_path=payload.get("relative_path"),
            tool_id=payload.get("tool_id") or "",
            source_authority=payload.get("source_authority") or "authoritative",
            document_metadata=payload.get("document_metadata") or {},
            is_anchor=bool(payload.get("is_anchor")),
            anchor_document_name=payload.get("anchor_document_name") or "",
            anchor_document_path=payload.get("anchor_document_path") or "",
            anchor_document_metadata=payload.get("anchor_document_metadata") or {},
            anchor_rows=tuple(anchor_rows),
            rows=tuple(rows),
            warnings=tuple(str(item) for item in warnings),
        )


@dataclass(frozen=True)
class AuthoritativeDatumDocumentCatalogResult:
    tenant_id: str
    documents: tuple[AuthoritativeDatumDocument | dict[str, Any], ...]
    source_files: dict[str, JsonValue]
    readiness_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()
    schema: str = AUTHORITATIVE_DATUM_DOCUMENT_CATALOG_SCHEMA

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        if not tenant_id:
            raise ValueError("authoritative_datum_document_catalog.tenant_id is required")
        normalized_documents: list[AuthoritativeDatumDocument] = []
        for document in self.documents:
            normalized_documents.append(
                document if isinstance(document, AuthoritativeDatumDocument) else AuthoritativeDatumDocument.from_dict(document)
            )
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "documents", tuple(normalized_documents))
        object.__setattr__(
            self,
            "source_files",
            _normalize_json_value(
                self.source_files,
                field_name="authoritative_datum_document_catalog.source_files",
            ),
        )
        object.__setattr__(
            self,
            "readiness_status",
            _normalize_json_value(
                self.readiness_status,
                field_name="authoritative_datum_document_catalog.readiness_status",
            ),
        )
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def ok(self) -> bool:
        return bool(self.document_count) and self.readiness_status.get("authoritative_catalog") == "loaded"

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "tenant_id": self.tenant_id,
            "document_count": self.document_count,
            "documents": [document.to_dict() for document in self.documents],
            "source_files": self.source_files,
            "readiness_status": self.readiness_status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthoritativeDatumDocumentCatalogResult:
        if not isinstance(payload, dict):
            raise ValueError("authoritative_datum_document_catalog must be a dict")
        documents = payload.get("documents") or ()
        if not isinstance(documents, (list, tuple)):
            raise ValueError("authoritative_datum_document_catalog.documents must be a list")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("authoritative_datum_document_catalog.warnings must be a list")
        return cls(
            tenant_id=payload.get("tenant_id"),
            documents=tuple(documents),
            source_files=payload.get("source_files") or {},
            readiness_status=payload.get("readiness_status") or {},
            warnings=tuple(str(item) for item in warnings),
        )


@dataclass(frozen=True)
class SystemDatumResourceRow:
    resource_id: str
    subject_ref: str
    relation: str
    object_ref: str
    labels: tuple[str, ...]
    raw: JsonValue

    def __post_init__(self) -> None:
        resource_id = _as_text(self.resource_id)
        if not resource_id:
            raise ValueError("system_datum_resource_row.resource_id is required")
        labels = tuple(_as_text(label) for label in self.labels if _as_text(label))
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "subject_ref", _as_text(self.subject_ref))
        object.__setattr__(self, "relation", _as_text(self.relation))
        object.__setattr__(self, "object_ref", _as_text(self.object_ref))
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "raw", _normalize_json_value(self.raw, field_name="system_datum_resource_row.raw"))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "resource_id": self.resource_id,
            "subject_ref": self.subject_ref,
            "relation": self.relation,
            "object_ref": self.object_ref,
            "labels": list(self.labels),
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SystemDatumResourceRow:
        if not isinstance(payload, dict):
            raise ValueError("system_datum_resource_row must be a dict")
        labels = payload.get("labels") or ()
        if not isinstance(labels, (list, tuple)):
            raise ValueError("system_datum_resource_row.labels must be a list")
        return cls(
            resource_id=payload.get("resource_id"),
            subject_ref=payload.get("subject_ref"),
            relation=payload.get("relation"),
            object_ref=payload.get("object_ref"),
            labels=tuple(str(label) for label in labels),
            raw=payload.get("raw"),
        )


@dataclass(frozen=True)
class SystemDatumWorkbenchResult:
    tenant_id: str
    rows: tuple[SystemDatumResourceRow, ...]
    source_files: dict[str, JsonValue]
    materialization_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()
    schema: str = SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        if not tenant_id:
            raise ValueError("system_datum_workbench_result.tenant_id is required")
        normalized_rows: list[SystemDatumResourceRow] = []
        for row in self.rows:
            normalized_rows.append(row if isinstance(row, SystemDatumResourceRow) else SystemDatumResourceRow.from_dict(row))
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "rows", tuple(normalized_rows))
        object.__setattr__(
            self,
            "source_files",
            _normalize_json_value(self.source_files, field_name="system_datum_workbench_result.source_files"),
        )
        object.__setattr__(
            self,
            "materialization_status",
            _normalize_json_value(
                self.materialization_status,
                field_name="system_datum_workbench_result.materialization_status",
            ),
        )
        object.__setattr__(self, "warnings", tuple(_as_text(warning) for warning in self.warnings if _as_text(warning)))

    @property
    def ok(self) -> bool:
        return self.row_count > 0 and self.materialization_status.get("canonical_source") == "loaded"

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "tenant_id": self.tenant_id,
            "row_count": self.row_count,
            "rows": [row.to_dict() for row in self.rows],
            "source_files": self.source_files,
            "materialization_status": self.materialization_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PublicationTenantSummaryRequest:
    tenant_id: str
    tenant_domain: str

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        if not tenant_id:
            raise ValueError("publication_tenant_summary_request.tenant_id is required")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(
            self,
            "tenant_domain",
            require_plain_domain(
                self.tenant_domain,
                field_name="publication_tenant_summary_request.tenant_domain",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_domain": self.tenant_domain,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationTenantSummaryRequest:
        if not isinstance(payload, dict):
            raise ValueError("publication_tenant_summary_request must be a dict")
        return cls(
            tenant_id=payload.get("tenant_id"),
            tenant_domain=payload.get("tenant_domain"),
        )


def _normalize_optional_object_payload(value: Any, *, field_name: str) -> dict[str, JsonValue] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict or null")
    normalized = _normalize_json_value(value, field_name=field_name)
    if not isinstance(normalized, dict):
        raise ValueError(f"{field_name} must be a dict or null")
    return normalized


@dataclass(frozen=True)
class PublicationTenantSummarySource:
    tenant_id: str
    tenant_domain: str
    profile_id: str
    public_profile: dict[str, JsonValue] | None
    tenant_profile: dict[str, JsonValue] | None
    schema: str = PUBLICATION_TENANT_SUMMARY_SOURCE_SCHEMA

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        profile_id = _as_text(self.profile_id)
        if not tenant_id:
            raise ValueError("publication_tenant_summary_source.tenant_id is required")
        if not profile_id:
            raise ValueError("publication_tenant_summary_source.profile_id is required")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(
            self,
            "tenant_domain",
            require_plain_domain(
                self.tenant_domain,
                field_name="publication_tenant_summary_source.tenant_domain",
            ),
        )
        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(
            self,
            "public_profile",
            _normalize_optional_object_payload(
                self.public_profile,
                field_name="publication_tenant_summary_source.public_profile",
            ),
        )
        object.__setattr__(
            self,
            "tenant_profile",
            _normalize_optional_object_payload(
                self.tenant_profile,
                field_name="publication_tenant_summary_source.tenant_profile",
            ),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "tenant_id": self.tenant_id,
            "tenant_domain": self.tenant_domain,
            "profile_id": self.profile_id,
            "public_profile": self.public_profile,
            "tenant_profile": self.tenant_profile,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationTenantSummarySource:
        if not isinstance(payload, dict):
            raise ValueError("publication_tenant_summary_source must be a dict")
        return cls(
            tenant_id=payload.get("tenant_id"),
            tenant_domain=payload.get("tenant_domain"),
            profile_id=payload.get("profile_id"),
            public_profile=payload.get("public_profile"),
            tenant_profile=payload.get("tenant_profile"),
        )


@dataclass(frozen=True)
class PublicationTenantSummaryResult:
    source: PublicationTenantSummarySource | dict[str, Any] | None
    resolution_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source is None:
            normalized_source = None
        elif isinstance(self.source, PublicationTenantSummarySource):
            normalized_source = self.source
        elif isinstance(self.source, dict):
            normalized_source = PublicationTenantSummarySource.from_dict(self.source)
        else:
            raise ValueError(
                "publication_tenant_summary_result.source must be PublicationTenantSummarySource, dict, or None"
            )
        object.__setattr__(self, "source", normalized_source)
        object.__setattr__(
            self,
            "resolution_status",
            _normalize_json_value(
                self.resolution_status,
                field_name="publication_tenant_summary_result.resolution_status",
            ),
        )
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def found(self) -> bool:
        return self.source is not None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "found": self.found,
            "source": None if self.source is None else self.source.to_dict(),
            "resolution_status": self.resolution_status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationTenantSummaryResult:
        if not isinstance(payload, dict):
            raise ValueError("publication_tenant_summary_result must be a dict")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("publication_tenant_summary_result.warnings must be a list")
        return cls(
            source=payload.get("source"),
            resolution_status=payload.get("resolution_status") or {},
            warnings=tuple(str(item) for item in warnings),
        )


@dataclass(frozen=True)
class PublicationProfileBasicsWriteRequest:
    tenant_id: str
    tenant_domain: str
    profile_title: str
    profile_summary: str = ""
    contact_email: str = ""
    public_website_url: str = ""

    def __post_init__(self) -> None:
        tenant_id = _as_text(self.tenant_id).lower()
        profile_title = _as_text(self.profile_title)
        if not tenant_id:
            raise ValueError("publication_profile_basics_write_request.tenant_id is required")
        if not profile_title:
            raise ValueError("publication_profile_basics_write_request.profile_title is required")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(
            self,
            "tenant_domain",
            require_plain_domain(
                self.tenant_domain,
                field_name="publication_profile_basics_write_request.tenant_domain",
            ),
        )
        object.__setattr__(self, "profile_title", profile_title)
        object.__setattr__(self, "profile_summary", _as_text(self.profile_summary))
        object.__setattr__(self, "contact_email", _as_text(self.contact_email).lower())
        object.__setattr__(self, "public_website_url", _as_text(self.public_website_url))

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_domain": self.tenant_domain,
            "profile_title": self.profile_title,
            "profile_summary": self.profile_summary,
            "contact_email": self.contact_email,
            "public_website_url": self.public_website_url,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationProfileBasicsWriteRequest:
        if not isinstance(payload, dict):
            raise ValueError("publication_profile_basics_write_request must be a dict")
        return cls(
            tenant_id=payload.get("tenant_id"),
            tenant_domain=payload.get("tenant_domain"),
            profile_title=payload.get("profile_title"),
            profile_summary=payload.get("profile_summary") or "",
            contact_email=payload.get("contact_email") or "",
            public_website_url=payload.get("public_website_url") or "",
        )


@dataclass(frozen=True)
class PublicationProfileBasicsWriteResult:
    source: PublicationTenantSummarySource | dict[str, Any]
    resolution_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()
    schema: str = PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA

    def __post_init__(self) -> None:
        normalized_source = (
            self.source
            if isinstance(self.source, PublicationTenantSummarySource)
            else PublicationTenantSummarySource.from_dict(self.source)
        )
        object.__setattr__(self, "source", normalized_source)
        schema = _as_text(self.schema) or PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA
        if schema != PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA:
            raise ValueError(
                "publication_profile_basics_write_result.schema must be "
                + PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA
            )
        object.__setattr__(self, "schema", schema)
        object.__setattr__(
            self,
            "resolution_status",
            _normalize_json_value(
                self.resolution_status,
                field_name="publication_profile_basics_write_result.resolution_status",
            ),
        )
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema": self.schema,
            "source": self.source.to_dict(),
            "resolution_status": self.resolution_status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationProfileBasicsWriteResult:
        if not isinstance(payload, dict):
            raise ValueError("publication_profile_basics_write_result must be a dict")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("publication_profile_basics_write_result.warnings must be a list")
        return cls(
            source=payload.get("source"),
            resolution_status=payload.get("resolution_status") or {},
            warnings=tuple(str(item) for item in warnings),
            schema=payload.get("schema") or PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA,
        )
