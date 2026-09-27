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
    AuthoritativeDatumDocumentIndexResult,
    AuthoritativeDatumDocumentRequest,
    AuthoritativeDatumDocumentRow,
    AuthoritativeDatumDocumentSummary,
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
    "AuthoritativeDatumDocumentIndexResult",
    "AuthoritativeDatumDocumentMutationPort",
    "AuthoritativeDatumDocumentPort",
    "AuthoritativeDatumDocumentRequest",
    "AuthoritativeDatumDocumentRow",
    "AuthoritativeDatumDocumentSummary",
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
    """What a caller needs to read documents, in the three shapes callers ask for.

    The whole catalog, the rows-free index, and one document — three questions with
    three costs, and a caller picks by what it is going to do with the answer. All
    three belong to the port because callers already require all three: the portal
    shell and the workbench read the index, the datum grid reads one document, and
    only a full export reads the catalog.

    They were added to the SQL adapter alone, so the port stopped describing what
    callers require and a store built to the port raised ``AttributeError`` on a
    method the type said nothing about. An adapter with no blob problem implements
    the two cheaply over its own catalog read — the projection is what the SQL
    adapter's index table caches, not a different answer.
    """

    def read_authoritative_datum_documents(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Read authoritative datum documents from canonical system and sandbox sources."""

    def read_document_index(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentIndexResult:
        """Every document's metadata, without its rows."""

    def read_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        allow_catalog_fallback: bool = True,
    ) -> AuthoritativeDatumDocument | None:
        """One document with its rows, or ``None`` when the store does not hold it."""


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
