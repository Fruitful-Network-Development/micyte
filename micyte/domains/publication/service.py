from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.core.identities import is_plain_domain, require_plain_domain
from micyte.ports.datum_store import (
    PublicationProfileBasicsWritePort,
    PublicationProfileBasicsWriteRequest,
    PublicationProfileBasicsWriteResult,
    PublicationTenantSummaryPort,
    PublicationTenantSummaryRequest,
    PublicationTenantSummaryResult,
    PublicationTenantSummarySource,
)

_WEBSITE_KEYS = ("public_website_url", "website_url", "website", "url")
_EMAIL_KEYS = ("contact_email", "email")
_PROFILE_BASICS_COMMAND_FIELDS = frozenset(
    {
        "tenant_id",
        "tenant_domain",
        "profile_title",
        "profile_summary",
        "contact_email",
        "public_website_url",
    }
)
_PROFILE_BASICS_WRITABLE_FIELDS = (
    "profile_title",
    "profile_summary",
    "contact_email",
    "public_website_url",
)
_PROFILE_BASICS_FOCUS_DATUM_ADDRESS = "4-1-1"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_lower(value: object) -> str:
    return _as_text(value).lower()


def _looks_like_email(value: object) -> bool:
    token = _as_lower(value)
    return bool(token and "@" in token and not token.startswith("@") and not token.endswith("@"))


def _looks_like_public_website(value: object) -> bool:
    token = _as_text(value)
    return token.startswith("https://") or token.startswith("http://")


def _looks_like_domain(value: object) -> bool:
    return is_plain_domain(value)


def _normalize_optional_email(value: object, *, field_name: str) -> str:
    token = _as_text(value).lower()
    if not token:
        return ""
    if not _looks_like_email(token):
        raise ValueError(f"{field_name} must be empty or an email-like value")
    return token


def _normalize_optional_public_website(value: object, *, field_name: str) -> str:
    token = _as_text(value)
    if not token:
        return ""
    if not _looks_like_public_website(token):
        raise ValueError(f"{field_name} must be empty or an http(s) URL")
    return token


def _pretty_label(value: object, *, fallback: str) -> str:
    token = _as_text(value)
    if not token:
        token = fallback
    normalized = token.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in normalized.split()) or fallback


def _safe_profile(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def _document_names(source: PublicationTenantSummarySource) -> tuple[str, ...]:
    names: list[str] = []
    if source.public_profile:
        names.append("public_profile")
    if source.tenant_profile:
        names.append("tenant_profile")
    return tuple(names)


def _summary_text(source: PublicationTenantSummarySource) -> str:
    tenant_profile = _safe_profile(source.tenant_profile)
    public_profile = _safe_profile(source.public_profile)
    return _as_text(
        tenant_profile.get("summary")
        or tenant_profile.get("bio")
        or public_profile.get("summary")
        or public_profile.get("bio")
    )


def _entity_type(source: PublicationTenantSummarySource) -> str:
    public_profile = _safe_profile(source.public_profile)
    tenant_profile = _safe_profile(source.tenant_profile)
    return _as_text(public_profile.get("entity_type") or tenant_profile.get("entity_type"))


def _display_title(source: PublicationTenantSummarySource) -> str:
    tenant_profile = _safe_profile(source.tenant_profile)
    public_profile = _safe_profile(source.public_profile)
    return _pretty_label(
        tenant_profile.get("title") or public_profile.get("title"),
        fallback=source.tenant_id,
    )


def _find_contact_email(payload: dict[str, Any]) -> str:
    for key in _EMAIL_KEYS:
        candidate = payload.get(key)
        if _looks_like_email(candidate):
            return _as_lower(candidate)
    options_public = payload.get("options_public")
    if isinstance(options_public, dict):
        for key in _EMAIL_KEYS:
            candidate = options_public.get(key)
            if _looks_like_email(candidate):
                return _as_lower(candidate)
    links = payload.get("links")
    if isinstance(links, list):
        for entry in links:
            if not isinstance(entry, dict):
                continue
            href = _as_text(entry.get("href") or entry.get("url"))
            if href.startswith("mailto:"):
                email = href.split(":", 1)[1].strip().lower()
                if _looks_like_email(email):
                    return email
            for key in _EMAIL_KEYS:
                candidate = entry.get(key)
                if _looks_like_email(candidate):
                    return _as_lower(candidate)
    return ""


def _find_public_website(payload: dict[str, Any]) -> str:
    for key in _WEBSITE_KEYS:
        candidate = payload.get(key)
        if _looks_like_public_website(candidate):
            return _as_text(candidate)
    options_public = payload.get("options_public")
    if isinstance(options_public, dict):
        for key in _WEBSITE_KEYS:
            candidate = options_public.get(key)
            if _looks_like_public_website(candidate):
                return _as_text(candidate)
    links = payload.get("links")
    if isinstance(links, list):
        for entry in links:
            if not isinstance(entry, dict):
                continue
            href = _as_text(entry.get("href") or entry.get("url"))
            if _looks_like_public_website(href):
                return href
            for key in _WEBSITE_KEYS:
                candidate = entry.get(key)
                if _looks_like_public_website(candidate):
                    return _as_text(candidate)
    return ""


@dataclass(frozen=True)
class PublicationTenantSummary:
    tenant_id: str
    tenant_domain: str
    profile_title: str
    profile_summary: str
    entity_type: str
    contact_email: str
    public_website_url: str
    available_documents: tuple[str, ...]
    profile_resolution: str
    publication_mode: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tenant_id = _as_lower(self.tenant_id)
        profile_title = _as_text(self.profile_title)
        profile_resolution = _as_text(self.profile_resolution).lower()
        publication_mode = _as_text(self.publication_mode).lower()
        if not tenant_id:
            raise ValueError("publication_tenant_summary.tenant_id is required")
        if not profile_title:
            raise ValueError("publication_tenant_summary.profile_title is required")
        if profile_resolution not in {
            "publication_profiles_loaded",
            "publication_profiles_partial",
            "publication_identity_only",
            "publication_unresolved",
        }:
            raise ValueError("publication_tenant_summary.profile_resolution is invalid")
        if publication_mode != "publication-only":
            raise ValueError("publication_tenant_summary.publication_mode must be publication-only")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(
            self,
            "tenant_domain",
            require_plain_domain(
                self.tenant_domain,
                field_name="publication_tenant_summary.tenant_domain",
            ),
        )
        object.__setattr__(self, "profile_title", profile_title)
        object.__setattr__(self, "profile_summary", _as_text(self.profile_summary))
        object.__setattr__(self, "entity_type", _as_text(self.entity_type))
        object.__setattr__(
            self,
            "contact_email",
            _as_lower(self.contact_email) if _looks_like_email(self.contact_email) else "",
        )
        object.__setattr__(
            self,
            "public_website_url",
            _as_text(self.public_website_url) if _looks_like_public_website(self.public_website_url) else "",
        )
        object.__setattr__(
            self,
            "available_documents",
            tuple(_as_text(item) for item in self.available_documents if _as_text(item)),
        )
        object.__setattr__(self, "profile_resolution", profile_resolution)
        object.__setattr__(self, "publication_mode", publication_mode)
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_domain": self.tenant_domain,
            "profile_title": self.profile_title,
            "profile_summary": self.profile_summary,
            "entity_type": self.entity_type,
            "contact_email": self.contact_email,
            "public_website_url": self.public_website_url,
            "available_documents": list(self.available_documents),
            "profile_resolution": self.profile_resolution,
            "publication_mode": self.publication_mode,
            "warnings": list(self.warnings),
        }

    @classmethod
    def fallback(
        cls,
        *,
        tenant_id: str,
        tenant_domain: str,
        warnings: tuple[str, ...] = (),
    ) -> PublicationTenantSummary:
        fallback_title = _pretty_label(tenant_id, fallback=_as_text(tenant_id) or "Tenant")
        return cls(
            tenant_id=tenant_id,
            tenant_domain=tenant_domain,
            profile_title=fallback_title,
            profile_summary="",
            entity_type="",
            contact_email="",
            public_website_url="",
            available_documents=(),
            profile_resolution="publication_unresolved",
            publication_mode="publication-only",
            warnings=warnings,
        )


def normalize_publication_tenant_summary(
    payload: PublicationTenantSummarySource | dict[str, Any],
    *,
    warnings: tuple[str, ...] = (),
) -> PublicationTenantSummary:
    if isinstance(payload, PublicationTenantSummarySource):
        source = payload
    elif isinstance(payload, dict):
        source = PublicationTenantSummarySource.from_dict(payload)
    else:
        raise ValueError("publication_tenant_summary_source must be a dict or PublicationTenantSummarySource")

    available_documents = _document_names(source)
    if len(available_documents) == 2:
        profile_resolution = "publication_profiles_loaded"
    elif available_documents:
        profile_resolution = "publication_profiles_partial"
    else:
        profile_resolution = "publication_identity_only"

    public_profile = _safe_profile(source.public_profile)
    tenant_profile = _safe_profile(source.tenant_profile)

    return PublicationTenantSummary(
        tenant_id=source.tenant_id,
        tenant_domain=source.tenant_domain,
        profile_title=_display_title(source),
        profile_summary=_summary_text(source),
        entity_type=_entity_type(source),
        contact_email=_find_contact_email(tenant_profile) or _find_contact_email(public_profile),
        public_website_url=_find_public_website(tenant_profile) or _find_public_website(public_profile),
        available_documents=available_documents,
        profile_resolution=profile_resolution,
        publication_mode="publication-only",
        warnings=warnings,
    )


class PublicationTenantSummaryService:
    def __init__(self, datum_store: PublicationTenantSummaryPort) -> None:
        self._datum_store = datum_store

    def read_projection(self, tenant_id: str, tenant_domain: str) -> PublicationTenantSummaryResult:
        return self._datum_store.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=tenant_id,
                tenant_domain=tenant_domain,
            )
        )

    def read_summary(self, tenant_id: str, tenant_domain: str) -> PublicationTenantSummary | None:
        projection = self.read_projection(tenant_id, tenant_domain)
        if projection.source is None:
            return None
        return normalize_publication_tenant_summary(
            projection.source,
            warnings=projection.warnings,
        )


@dataclass(frozen=True)
class PublicationProfileBasicsCommand:
    tenant_id: str
    tenant_domain: str
    profile_title: str
    profile_summary: str = ""
    contact_email: str = ""
    public_website_url: str = ""
    writable_field_set: tuple[str, ...] = _PROFILE_BASICS_WRITABLE_FIELDS

    def __post_init__(self) -> None:
        tenant_id = _as_lower(self.tenant_id)
        profile_title = _as_text(self.profile_title)
        if not tenant_id:
            raise ValueError("publication_profile_basics.tenant_id is required")
        if not profile_title:
            raise ValueError("publication_profile_basics.profile_title is required")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(
            self,
            "tenant_domain",
            require_plain_domain(
                self.tenant_domain,
                field_name="publication_profile_basics.tenant_domain",
            ),
        )
        object.__setattr__(self, "profile_title", profile_title)
        object.__setattr__(self, "profile_summary", _as_text(self.profile_summary))
        object.__setattr__(
            self,
            "contact_email",
            _normalize_optional_email(
                self.contact_email,
                field_name="publication_profile_basics.contact_email",
            ),
        )
        object.__setattr__(
            self,
            "public_website_url",
            _normalize_optional_public_website(
                self.public_website_url,
                field_name="publication_profile_basics.public_website_url",
            ),
        )
        object.__setattr__(self, "writable_field_set", tuple(_PROFILE_BASICS_WRITABLE_FIELDS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_domain": self.tenant_domain,
            "profile_title": self.profile_title,
            "profile_summary": self.profile_summary,
            "contact_email": self.contact_email,
            "public_website_url": self.public_website_url,
            "writable_field_set": list(self.writable_field_set),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PublicationProfileBasicsCommand:
        if not isinstance(payload, dict):
            raise ValueError("publication_profile_basics must be a dict")
        extra_fields = sorted(set(payload.keys()) - _PROFILE_BASICS_COMMAND_FIELDS)
        if extra_fields:
            raise ValueError(f"publication_profile_basics has unsupported fields: {extra_fields}")
        return cls(
            tenant_id=payload.get("tenant_id"),
            tenant_domain=payload.get("tenant_domain"),
            profile_title=payload.get("profile_title"),
            profile_summary=payload.get("profile_summary") or "",
            contact_email=payload.get("contact_email") or "",
            public_website_url=payload.get("public_website_url") or "",
        )


@dataclass(frozen=True)
class PublicationProfileBasicsOutcome:
    command: PublicationProfileBasicsCommand
    profile_id: str
    confirmed_summary: PublicationTenantSummary

    def __post_init__(self) -> None:
        profile_id = _as_text(self.profile_id)
        if not profile_id:
            raise ValueError("publication_profile_basics_outcome.profile_id is required")
        object.__setattr__(self, "profile_id", profile_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "updated_fields": list(self.command.writable_field_set),
            "confirmed_summary": self.confirmed_summary.to_dict(),
        }

    def to_local_audit_payload(self) -> dict[str, Any]:
        return {
            "event_type": "publication.profile_basics.write.accepted",
            "focus_subject": f"{self.profile_id}.{_PROFILE_BASICS_FOCUS_DATUM_ADDRESS}",
            "shell_verb": "portal.profile_basics_write",
            "details": {
                "tenant_scope_id": self.command.tenant_id,
                "profile_id": self.profile_id,
                "updated_fields": list(self.command.writable_field_set),
                "profile_title": self.command.profile_title,
                "profile_summary": self.command.profile_summary,
                "contact_email": self.command.contact_email,
                "public_website_url": self.command.public_website_url,
            },
        }


def normalize_publication_profile_basics_command(
    payload: PublicationProfileBasicsCommand | dict[str, Any],
) -> PublicationProfileBasicsCommand:
    if isinstance(payload, PublicationProfileBasicsCommand):
        return payload
    return PublicationProfileBasicsCommand.from_dict(payload)


class PublicationProfileBasicsService:
    def __init__(self, datum_store: PublicationProfileBasicsWritePort) -> None:
        self._datum_store = datum_store

    def apply_write(
        self,
        payload: PublicationProfileBasicsCommand | dict[str, Any],
    ) -> PublicationProfileBasicsOutcome:
        command = normalize_publication_profile_basics_command(payload)
        result = self._datum_store.write_publication_profile_basics(
            PublicationProfileBasicsWriteRequest(
                tenant_id=command.tenant_id,
                tenant_domain=command.tenant_domain,
                profile_title=command.profile_title,
                profile_summary=command.profile_summary,
                contact_email=command.contact_email,
                public_website_url=command.public_website_url,
            )
        )
        normalized_result = (
            result
            if isinstance(result, PublicationProfileBasicsWriteResult)
            else PublicationProfileBasicsWriteResult.from_dict(result)
        )
        confirmed_summary = normalize_publication_tenant_summary(
            normalized_result.source,
            warnings=normalized_result.warnings,
        )
        if confirmed_summary.tenant_id != command.tenant_id:
            raise ValueError("publication_profile_basics confirmation tenant_id does not match request")
        if confirmed_summary.tenant_domain != command.tenant_domain:
            raise ValueError("publication_profile_basics confirmation tenant_domain does not match request")
        if confirmed_summary.profile_title != command.profile_title:
            raise ValueError("publication_profile_basics confirmation profile_title does not match request")
        if confirmed_summary.profile_summary != command.profile_summary:
            raise ValueError("publication_profile_basics confirmation profile_summary does not match request")
        if confirmed_summary.contact_email != command.contact_email:
            raise ValueError("publication_profile_basics confirmation contact_email does not match request")
        if confirmed_summary.public_website_url != command.public_website_url:
            raise ValueError(
                "publication_profile_basics confirmation public_website_url does not match request"
            )
        return PublicationProfileBasicsOutcome(
            command=command,
            profile_id=normalized_result.source.profile_id,
            confirmed_summary=confirmed_summary,
        )
