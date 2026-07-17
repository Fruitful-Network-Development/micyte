"""System datum store PORT PROTOCOLS.

The datum-document value types (``AuthoritativeDatumDocument`` and friends) now
live in ``packages/core/datum_documents.py`` so that ``core`` no longer imports
``ports`` (see ``core/forbidden_dependencies.md``). This module defines only the
port *protocols* over those core value types, and re-exports the value types for
backward compatibility with existing ``ports.datum_store`` importers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from micyte.core.datum_documents import (
    AUTHORITATIVE_DATUM_DOCUMENT_CATALOG_SCHEMA,
    AUTHORITATIVE_DATUM_DOCUMENT_ROW_SCHEMA,
    AUTHORITATIVE_DATUM_DOCUMENT_SCHEMA,
    PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA,
    PUBLICATION_TENANT_SUMMARY_SOURCE_SCHEMA,
    SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA,
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentCatalogResult,
    AuthoritativeDatumDocumentRequest,
    AuthoritativeDatumDocumentRow,
    JsonScalar,
    JsonValue,
    PublicationProfileBasicsWriteRequest,
    PublicationProfileBasicsWriteResult,
    PublicationTenantSummaryRequest,
    PublicationTenantSummaryResult,
    PublicationTenantSummarySource,
    SystemDatumResourceRow,
    SystemDatumStoreRequest,
    SystemDatumWorkbenchResult,
)

__all__ = [
    "AUTHORITATIVE_DATUM_DOCUMENT_CATALOG_SCHEMA",
    "AUTHORITATIVE_DATUM_DOCUMENT_ROW_SCHEMA",
    "AUTHORITATIVE_DATUM_DOCUMENT_SCHEMA",
    "PUBLICATION_PROFILE_BASICS_WRITE_RESULT_SCHEMA",
    "PUBLICATION_TENANT_SUMMARY_SOURCE_SCHEMA",
    "SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA",
    "AuthoritativeDatumDocument",
    "AuthoritativeDatumDocumentCatalogResult",
    "AuthoritativeDatumDocumentMutationPort",
    "AuthoritativeDatumDocumentPort",
    "AuthoritativeDatumDocumentRequest",
    "AuthoritativeDatumDocumentRow",
    "JsonScalar",
    "JsonValue",
    "PublicationProfileBasicsWritePort",
    "PublicationProfileBasicsWriteRequest",
    "PublicationProfileBasicsWriteResult",
    "PublicationTenantSummaryPort",
    "PublicationTenantSummaryRequest",
    "PublicationTenantSummaryResult",
    "PublicationTenantSummarySource",
    "SystemDatumResourceRow",
    "SystemDatumStorePort",
    "SystemDatumStoreRequest",
    "SystemDatumWorkbenchResult",
]


@runtime_checkable
class SystemDatumStorePort(Protocol):
    def read_system_resource_workbench(self, request: SystemDatumStoreRequest) -> SystemDatumWorkbenchResult:
        """Read the canonical system datum workbench surface."""


@runtime_checkable
class AuthoritativeDatumDocumentPort(Protocol):
    def read_authoritative_datum_documents(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Read authoritative datum documents from canonical system and sandbox sources."""


@runtime_checkable
class AuthoritativeDatumDocumentMutationPort(AuthoritativeDatumDocumentPort, Protocol):
    def read_document_version_identity(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> dict[str, JsonValue] | None:
        """Read one authoritative document version identity without mutating the catalog."""

    def replace_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        updated_document: AuthoritativeDatumDocument,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Persist one fully materialized authoritative document replacement transactionally."""

    def delete_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Remove one authoritative document from the catalog transactionally."""


@runtime_checkable
class PublicationTenantSummaryPort(Protocol):
    def read_publication_tenant_summary(
        self,
        request: PublicationTenantSummaryRequest,
    ) -> PublicationTenantSummaryResult:
        """Read one publication-backed tenant profile projection without writes."""


@runtime_checkable
class PublicationProfileBasicsWritePort(Protocol):
    def write_publication_profile_basics(
        self,
        request: PublicationProfileBasicsWriteRequest,
    ) -> PublicationProfileBasicsWriteResult:
        """Apply one bounded publication-backed profile basics write with read-after-write confirmation."""
