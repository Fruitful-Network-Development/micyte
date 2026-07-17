from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from micyte.ports.datum_store import (
    SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA,
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentCatalogResult,
    AuthoritativeDatumDocumentPort,
    AuthoritativeDatumDocumentRequest,
    AuthoritativeDatumDocumentRow,
)

_RF_TOKEN_RE = re.compile(r"^rf\.([0-9]+-[0-9]+-[0-9]+)$")
_DATUM_ADDRESS_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")
_NUMERIC_HYPHEN_RE = re.compile(r"^[0-9]+(?:-[0-9]+)+$")
_BINARY_RE = re.compile(r"^[01]+$")
_DIAGNOSTIC_STATES = frozenset(
    {
        "ok",
        "missing_reference",
        "unresolved_anchor",
        "family_magnitude_mismatch",
        "illegal_magnitude_literal",
        "address_irregularity",
        "unrecognized_family",
    }
)
_REFERENCE_RESOLUTION_STATES = frozenset({"resolved", "unresolved_anchor", "missing_reference"})
_VALUE_KINDS = frozenset({"binary_string", "numeric_hyphen", "literal_text", "tuple", "unknown"})
_OVERLAY_KINDS = frozenset(
    {
        "none",
        "title_babelette",
        "samras_babelette",
        "hops_babelette",
        "binary_overlay",
        "raw_only",
    }
)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_lower(value: object) -> str:
    return _as_text(value).lower()


def _normalize_json_value(value: Any, *, field_name: str) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item, field_name=f"{field_name}[]") for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            token = _as_text(key)
            if not token:
                raise ValueError(f"{field_name} keys must be non-empty strings")
            out[token] = _normalize_json_value(item, field_name=f"{field_name}.{token}")
        return out
    raise ValueError(f"{field_name} must be JSON-serializable data")


def _normalize_reference_token(value: object) -> str:
    token = _as_lower(value)
    match = _RF_TOKEN_RE.fullmatch(token)
    if not match:
        return ""
    return f"rf.{match.group(1)}"


def _is_numeric_hyphen(value: object) -> bool:
    return bool(_NUMERIC_HYPHEN_RE.fullmatch(_as_text(value)))


def _is_binary_string(value: object) -> bool:
    return bool(_BINARY_RE.fullmatch(_as_text(value)))


def _address_tuple(value: object) -> tuple[int, int, int] | None:
    token = _as_text(value)
    if not _DATUM_ADDRESS_RE.fullmatch(token):
        return None
    first, second, third = token.split("-", 2)
    return int(first), int(second), int(third)


def _extract_labels(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], (list, tuple)):
        return tuple(_as_text(item) for item in raw[1] if _as_text(item))
    if isinstance(raw, dict):
        labels = raw.get("labels") or raw.get("label") or raw.get("name") or ()
        if isinstance(labels, (list, tuple)):
            return tuple(_as_text(item) for item in labels if _as_text(item))
        token = _as_text(labels)
        return (token,) if token else ()
    return ()


def _extract_tokens(raw: Any, *, datum_address: str) -> tuple[str, ...]:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return tuple(_as_text(item) for item in raw[0] if _as_text(item))
    if isinstance(raw, dict):
        tokens = [
            _as_text(raw.get("subject_ref") or raw.get("subject") or datum_address),
            _as_text(raw.get("relation") or raw.get("predicate")),
            _as_text(raw.get("object_ref") or raw.get("object")),
        ]
        return tuple(token for token in tokens if token)
    return ()


def _primary_value_token(tokens: tuple[str, ...]) -> str:
    if not tokens:
        return ""
    return _as_text(tokens[-1])


def _family_contract(anchor_label: object) -> tuple[str, str, str]:
    label = _as_lower(anchor_label)
    if "title-babelette" in label or "title-babellette" in label:
        return "nominal_babelette", "binary_string", "title_babelette"
    if ("ipv4" in label or "ipv6" in label or "dns" in label) and (
        "babelette" in label or "babellette" in label
    ):
        return "network_babelette", "binary_string", "binary_overlay"
    if "samras" in label and ("babelette" in label or "babellette" in label):
        return "samras_babelette", "numeric_hyphen", "samras_babelette"
    if "hops" in label and ("babelette" in label or "babellette" in label):
        return "hops_babelette", "numeric_hyphen", "hops_babelette"
    if "samras" in label:
        return "samras", "numeric_hyphen", "samras_babelette"
    if "hops" in label:
        return "hops", "numeric_hyphen", "hops_babelette"
    return "", "unknown", "none"


def _default_value_kind(value_token: object) -> str:
    token = _as_text(value_token)
    if not token:
        return "unknown"
    if _is_binary_string(token):
        return "binary_string"
    if _is_numeric_hyphen(token):
        return "numeric_hyphen"
    if token.upper() == "HERE":
        return "literal_text"
    return "literal_text"


def _first_label(labels: tuple[str, ...]) -> str:
    return labels[0] if labels else ""


def _anchor_label_map(document: AuthoritativeDatumDocument) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in document.anchor_rows:
        labels = _extract_labels(row.raw)
        label = _first_label(labels)
        if label:
            out[row.datum_address] = label
    return out


def _diagnostic_counts(rows: tuple[DatumRecognitionRow, ...]) -> dict[str, int]:
    counts = {state: 0 for state in sorted(_DIAGNOSTIC_STATES)}
    for row in rows:
        for state in row.diagnostic_states:
            counts[state] = counts.get(state, 0) + 1
    return counts


def _detect_address_irregularities(document: AuthoritativeDatumDocument) -> set[str]:
    groups: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for row in document.rows:
        parsed = _address_tuple(row.datum_address)
        if parsed is None:
            continue
        groups.setdefault((parsed[0], parsed[1]), []).append((parsed[2], row.datum_address))
    irregular: set[str] = set()
    for values in groups.values():
        values.sort()
        previous_last: int | None = None
        for current_last, datum_address in values:
            if previous_last is not None and current_last != previous_last + 1:
                irregular.add(datum_address)
            previous_last = current_last
    return irregular


@dataclass(frozen=True)
class DatumRecognitionReferenceBinding:
    reference_form: str
    normalized_reference_form: str
    value_token: str
    anchor_address: str
    anchor_label: str
    resolution_state: str
    expected_value_kind: str = "unknown"

    def __post_init__(self) -> None:
        reference_form = _as_text(self.reference_form)
        normalized_reference_form = _normalize_reference_token(self.normalized_reference_form or reference_form)
        anchor_address = _as_text(self.anchor_address)
        anchor_label = _as_text(self.anchor_label)
        resolution_state = _as_lower(self.resolution_state)
        expected_value_kind = _as_lower(self.expected_value_kind) or "unknown"
        if not reference_form:
            raise ValueError("datum_recognition_reference.reference_form is required")
        if not normalized_reference_form:
            raise ValueError("datum_recognition_reference.normalized_reference_form is required")
        if not anchor_address:
            raise ValueError("datum_recognition_reference.anchor_address is required")
        if resolution_state not in _REFERENCE_RESOLUTION_STATES:
            raise ValueError("datum_recognition_reference.resolution_state is invalid")
        if expected_value_kind not in _VALUE_KINDS:
            raise ValueError("datum_recognition_reference.expected_value_kind is invalid")
        object.__setattr__(self, "reference_form", reference_form)
        object.__setattr__(self, "normalized_reference_form", normalized_reference_form)
        object.__setattr__(self, "value_token", _as_text(self.value_token))
        object.__setattr__(self, "anchor_address", anchor_address)
        object.__setattr__(self, "anchor_label", anchor_label)
        object.__setattr__(self, "resolution_state", resolution_state)
        object.__setattr__(self, "expected_value_kind", expected_value_kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_form": self.reference_form,
            "normalized_reference_form": self.normalized_reference_form,
            "value_token": self.value_token,
            "anchor_address": self.anchor_address,
            "anchor_label": self.anchor_label,
            "resolution_state": self.resolution_state,
            "expected_value_kind": self.expected_value_kind,
        }


@dataclass(frozen=True)
class DatumRecognitionRow:
    datum_address: str
    raw: Any
    labels: tuple[str, ...]
    reference_bindings: tuple[DatumRecognitionReferenceBinding | dict[str, Any], ...]
    recognized_family: str = ""
    recognized_anchor: str = ""
    primary_value_token: str = ""
    diagnostic_states: tuple[str, ...] = ("ok",)
    render_hints: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        datum_address = _as_text(self.datum_address)
        if not datum_address:
            raise ValueError("datum_recognition_row.datum_address is required")
        labels = tuple(_as_text(item) for item in self.labels if _as_text(item))
        bindings: list[DatumRecognitionReferenceBinding] = []
        for item in self.reference_bindings:
            bindings.append(
                item if isinstance(item, DatumRecognitionReferenceBinding) else DatumRecognitionReferenceBinding(**item)
            )
        diagnostic_states = tuple(_as_lower(item) for item in self.diagnostic_states if _as_text(item))
        if not diagnostic_states:
            raise ValueError("datum_recognition_row.diagnostic_states is required")
        invalid = [item for item in diagnostic_states if item not in _DIAGNOSTIC_STATES]
        if invalid:
            raise ValueError(f"datum_recognition_row.diagnostic_states is invalid: {invalid}")
        if "ok" in diagnostic_states and len(diagnostic_states) > 1:
            diagnostic_states = tuple(item for item in diagnostic_states if item != "ok")
        render_hints = _normalize_json_value(self.render_hints or {}, field_name="datum_recognition_row.render_hints")
        if not isinstance(render_hints, dict):
            raise ValueError("datum_recognition_row.render_hints must be a dict")
        object.__setattr__(self, "datum_address", datum_address)
        object.__setattr__(self, "raw", _normalize_json_value(self.raw, field_name="datum_recognition_row.raw"))
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "reference_bindings", tuple(bindings))
        object.__setattr__(self, "recognized_family", _as_text(self.recognized_family))
        object.__setattr__(self, "recognized_anchor", _as_text(self.recognized_anchor))
        object.__setattr__(self, "primary_value_token", _as_text(self.primary_value_token))
        object.__setattr__(self, "diagnostic_states", diagnostic_states)
        object.__setattr__(self, "render_hints", render_hints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "datum_address": self.datum_address,
            "raw": self.raw,
            "labels": list(self.labels),
            "reference_bindings": [item.to_dict() for item in self.reference_bindings],
            "recognized_family": self.recognized_family,
            "recognized_anchor": self.recognized_anchor,
            "primary_value_token": self.primary_value_token,
            "diagnostic_states": list(self.diagnostic_states),
            "render_hints": dict(self.render_hints or {}),
        }


@dataclass(frozen=True)
class DatumRecognitionDocument:
    document_id: str
    source_kind: str
    document_name: str
    canonical_name: str
    relative_path: str
    tool_id: str
    source_authority: str
    document_metadata: dict[str, Any] | None
    is_anchor: bool
    legacy_alias: str
    anchor_document_name: str
    anchor_document_path: str
    anchor_document_metadata: dict[str, Any] | None
    anchor_resolution: str
    anchor_rows: tuple[AuthoritativeDatumDocumentRow | dict[str, Any], ...]
    rows: tuple[DatumRecognitionRow | dict[str, Any], ...]
    diagnostic_totals: dict[str, int]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        document_id = _as_text(self.document_id)
        source_kind = _as_lower(self.source_kind)
        if not document_id:
            raise ValueError("datum_recognition_document.document_id is required")
        if source_kind not in {"system_anthology", "sandbox_source"}:
            raise ValueError("datum_recognition_document.source_kind is invalid")
        anchor_rows: list[AuthoritativeDatumDocumentRow] = []
        for row in self.anchor_rows:
            anchor_rows.append(
                row if isinstance(row, AuthoritativeDatumDocumentRow) else AuthoritativeDatumDocumentRow.from_dict(row)
            )
        rows: list[DatumRecognitionRow] = []
        for row in self.rows:
            rows.append(row if isinstance(row, DatumRecognitionRow) else DatumRecognitionRow(**row))
        diagnostic_totals = _normalize_json_value(
            self.diagnostic_totals,
            field_name="datum_recognition_document.diagnostic_totals",
        )
        if not isinstance(diagnostic_totals, dict):
            raise ValueError("datum_recognition_document.diagnostic_totals must be a dict")
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(self, "document_name", _as_text(self.document_name))
        object.__setattr__(self, "canonical_name", _as_text(self.canonical_name))
        object.__setattr__(self, "relative_path", _as_text(self.relative_path))
        object.__setattr__(self, "tool_id", _as_text(self.tool_id))
        object.__setattr__(self, "source_authority", _as_lower(self.source_authority) or "authoritative")
        object.__setattr__(
            self,
            "document_metadata",
            _normalize_json_value(self.document_metadata or {}, field_name="datum_recognition_document.document_metadata"),
        )
        object.__setattr__(self, "is_anchor", bool(self.is_anchor))
        object.__setattr__(self, "legacy_alias", _as_text(self.legacy_alias))
        object.__setattr__(self, "anchor_document_name", _as_text(self.anchor_document_name))
        object.__setattr__(self, "anchor_document_path", _as_text(self.anchor_document_path))
        object.__setattr__(
            self,
            "anchor_document_metadata",
            _normalize_json_value(
                self.anchor_document_metadata or {},
                field_name="datum_recognition_document.anchor_document_metadata",
            ),
        )
        object.__setattr__(self, "anchor_resolution", _as_lower(self.anchor_resolution))
        object.__setattr__(self, "anchor_rows", tuple(anchor_rows))
        object.__setattr__(self, "rows", tuple(rows))
        object.__setattr__(self, "diagnostic_totals", diagnostic_totals)
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def diagnostic_row_count(self) -> int:
        return sum(1 for row in self.rows if "ok" not in row.diagnostic_states)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_kind": self.source_kind,
            "document_name": self.document_name,
            "canonical_name": self.canonical_name,
            "relative_path": self.relative_path,
            "tool_id": self.tool_id,
            "source_authority": self.source_authority,
            "document_metadata": dict(self.document_metadata or {}),
            "is_anchor": self.is_anchor,
            "legacy_alias": self.legacy_alias,
            "anchor_document_name": self.anchor_document_name,
            "anchor_document_path": self.anchor_document_path,
            "anchor_document_metadata": dict(self.anchor_document_metadata or {}),
            "anchor_resolution": self.anchor_resolution,
            "anchor_row_count": len(self.anchor_rows),
            "row_count": self.row_count,
            "diagnostic_row_count": self.diagnostic_row_count,
            "diagnostic_totals": dict(self.diagnostic_totals),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class DatumWorkbenchProjection:
    tenant_id: str
    documents: tuple[DatumRecognitionDocument | dict[str, Any], ...]
    selected_document_id: str
    source_files: dict[str, Any]
    readiness_status: dict[str, Any]
    warnings: tuple[str, ...] = ()
    schema: str = SYSTEM_DATUM_RESOURCE_WORKBENCH_SCHEMA

    def __post_init__(self) -> None:
        tenant_id = _as_lower(self.tenant_id)
        if not tenant_id:
            raise ValueError("datum_workbench_projection.tenant_id is required")
        documents: list[DatumRecognitionDocument] = []
        for document in self.documents:
            documents.append(document if isinstance(document, DatumRecognitionDocument) else DatumRecognitionDocument(**document))
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "documents", tuple(documents))
        object.__setattr__(self, "selected_document_id", _as_text(self.selected_document_id))
        object.__setattr__(self, "source_files", _normalize_json_value(self.source_files, field_name="datum_workbench_projection.source_files"))
        object.__setattr__(
            self,
            "readiness_status",
            _normalize_json_value(self.readiness_status, field_name="datum_workbench_projection.readiness_status"),
        )
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def selected_document(self) -> DatumRecognitionDocument | None:
        for document in self.documents:
            if document.document_id == self.selected_document_id:
                return document
        return self.documents[0] if self.documents else None

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def row_count(self) -> int:
        document = self.selected_document
        return document.row_count if document is not None else 0

    @property
    def ok(self) -> bool:
        return self.selected_document is not None and self.readiness_status.get("authoritative_catalog") == "loaded"

    def to_dict(self) -> dict[str, Any]:
        selected_document = self.selected_document
        rows = selected_document.rows if selected_document is not None else ()
        rows_preview = rows[:120]
        return {
            "schema": self.schema,
            "ok": self.ok,
            "tenant_id": self.tenant_id,
            "document_count": self.document_count,
            "selected_document_id": self.selected_document_id,
            "row_count": self.row_count,
            "documents": [document.to_summary_dict() for document in self.documents],
            "selected_document": None if selected_document is None else selected_document.to_summary_dict(),
            "rows": [row.to_dict() for row in rows],
            "rows_preview": [row.to_dict() for row in rows_preview],
            "source_files": self.source_files,
            "readiness_status": self.readiness_status,
            "diagnostic_totals": {} if selected_document is None else dict(selected_document.diagnostic_totals),
            "warnings": list(self.warnings),
        }


def _build_reference_bindings(
    *,
    raw_tokens: tuple[str, ...],
    anchor_labels: dict[str, str],
) -> tuple[
    tuple[DatumRecognitionReferenceBinding, ...],
    tuple[str, ...],
    str,
    str,
    dict[str, Any],
]:
    bindings: list[DatumRecognitionReferenceBinding] = []
    diagnostics: list[str] = []
    recognized_family = ""
    recognized_anchor = ""
    overlay_kind = "none"
    expected_value_kind = "unknown"
    for index, token in enumerate(raw_tokens):
        normalized_reference = _normalize_reference_token(token)
        if not normalized_reference:
            continue
        anchor_address = normalized_reference.split(".", 1)[1]
        next_token = _as_text(raw_tokens[index + 1]) if index + 1 < len(raw_tokens) else ""
        if _normalize_reference_token(next_token):
            next_token = ""
        anchor_label = _as_text(anchor_labels.get(anchor_address))
        if not next_token:
            resolution_state = "missing_reference"
            diagnostics.append("missing_reference")
            binding = DatumRecognitionReferenceBinding(
                reference_form=_as_text(token),
                normalized_reference_form=normalized_reference,
                value_token="",
                anchor_address=anchor_address,
                anchor_label=anchor_label,
                resolution_state=resolution_state,
                expected_value_kind="unknown",
            )
            bindings.append(binding)
            continue
        if not anchor_label:
            resolution_state = "unresolved_anchor"
            diagnostics.append("unresolved_anchor")
            binding = DatumRecognitionReferenceBinding(
                reference_form=_as_text(token),
                normalized_reference_form=normalized_reference,
                value_token=next_token,
                anchor_address=anchor_address,
                anchor_label="",
                resolution_state=resolution_state,
                expected_value_kind="unknown",
            )
            bindings.append(binding)
            continue

        family, binding_expected_value_kind, binding_overlay_kind = _family_contract(anchor_label)
        if not family:
            diagnostics.append("unrecognized_family")
        elif not recognized_family:
            recognized_family = family
            recognized_anchor = anchor_label
            overlay_kind = binding_overlay_kind
            expected_value_kind = binding_expected_value_kind

        if _as_lower(next_token) == "here":
            diagnostics.append("illegal_magnitude_literal")
        if binding_expected_value_kind == "binary_string" and next_token and not _is_binary_string(next_token):
            diagnostics.append("family_magnitude_mismatch")
        if binding_expected_value_kind == "numeric_hyphen" and next_token and not _is_numeric_hyphen(next_token):
            diagnostics.append("family_magnitude_mismatch")

        bindings.append(
            DatumRecognitionReferenceBinding(
                reference_form=_as_text(token),
                normalized_reference_form=normalized_reference,
                value_token=next_token,
                anchor_address=anchor_address,
                anchor_label=anchor_label,
                resolution_state="resolved",
                expected_value_kind=binding_expected_value_kind,
            )
        )
    if not bindings:
        overlay_kind = "raw_only"
        expected_value_kind = "tuple"
    return (
        tuple(bindings),
        tuple(dict.fromkeys(diagnostics)),
        recognized_family,
        recognized_anchor,
        {
            "value_kind": expected_value_kind if expected_value_kind in _VALUE_KINDS else "unknown",
            "overlay_kind": overlay_kind if overlay_kind in _OVERLAY_KINDS else "none",
        },
    )


def _recognize_document(document: AuthoritativeDatumDocument) -> DatumRecognitionDocument:
    anchor_labels = _anchor_label_map(document)
    irregular_addresses = _detect_address_irregularities(document)
    rows: list[DatumRecognitionRow] = []
    for row in document.rows:
        raw_tokens = _extract_tokens(row.raw, datum_address=row.datum_address)
        reference_bindings, reference_diagnostics, recognized_family, recognized_anchor, base_render_hints = _build_reference_bindings(
            raw_tokens=raw_tokens,
            anchor_labels=anchor_labels,
        )
        diagnostics = list(reference_diagnostics)
        if row.datum_address in irregular_addresses:
            diagnostics.append("address_irregularity")
        if not diagnostics:
            diagnostics = ["ok"]
        primary_value_token = _primary_value_token(raw_tokens)
        render_hints = dict(base_render_hints)
        render_hints["show_raw_by_default"] = "ok" not in diagnostics
        render_hints["lens_presentation_only"] = True
        render_hints["primary_value_kind"] = (
            base_render_hints.get("value_kind")
            if base_render_hints.get("value_kind") not in {"unknown", "tuple"}
            else _default_value_kind(primary_value_token)
        )
        rows.append(
            DatumRecognitionRow(
                datum_address=row.datum_address,
                raw=row.raw,
                labels=_extract_labels(row.raw),
                reference_bindings=reference_bindings,
                recognized_family=recognized_family,
                recognized_anchor=recognized_anchor,
                primary_value_token=primary_value_token,
                diagnostic_states=tuple(dict.fromkeys(diagnostics)),
                render_hints=render_hints,
            )
        )

    anchor_resolution = "not_required" if document.source_kind == "system_anthology" or bool(document.is_anchor) else "resolved"
    if document.source_kind == "sandbox_source" and not document.is_anchor and not document.anchor_rows:
        anchor_resolution = "missing"
    return DatumRecognitionDocument(
        document_id=document.document_id,
        source_kind=document.source_kind,
        document_name=document.document_name,
        canonical_name=document.canonical_name,
        relative_path=document.relative_path,
        tool_id=document.tool_id,
        source_authority=document.source_authority,
        document_metadata=document.document_metadata,
        is_anchor=document.is_anchor,
        legacy_alias=_as_text((document.document_metadata or {}).get("legacy_alias")),
        anchor_document_name=document.anchor_document_name,
        anchor_document_path=document.anchor_document_path,
        anchor_document_metadata=document.anchor_document_metadata,
        anchor_resolution=anchor_resolution,
        anchor_rows=document.anchor_rows,
        rows=tuple(rows),
        diagnostic_totals=_diagnostic_counts(tuple(rows)),
        warnings=document.warnings,
    )


def recognize_authoritative_document(document: AuthoritativeDatumDocument) -> DatumRecognitionDocument:
    """Public seam for presentation/runtime layers that need bounded datum recognition."""

    return _recognize_document(document)


def _select_document_id(documents: tuple[DatumRecognitionDocument, ...]) -> str:
    sandbox_with_diagnostics = [
        document
        for document in documents
        if document.source_kind == "sandbox_source" and document.diagnostic_row_count > 0
    ]
    if sandbox_with_diagnostics:
        return sandbox_with_diagnostics[0].document_id
    sandbox_documents = [document for document in documents if document.source_kind == "sandbox_source"]
    if sandbox_documents:
        for document in sandbox_documents:
            if document.is_anchor:
                return document.document_id
        return sandbox_documents[0].document_id
    return documents[0].document_id if documents else ""


class DatumWorkbenchService:
    def __init__(self, datum_store: AuthoritativeDatumDocumentPort | None) -> None:
        self._datum_store = datum_store

    def _require_store(self) -> AuthoritativeDatumDocumentPort:
        if self._datum_store is None:
            raise ValueError("datum_workbench.datum_store is not configured")
        return self._datum_store

    def read_workbench(self, tenant_id: str) -> DatumWorkbenchProjection:
        result = self._require_store().read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        )
        normalized_result = (
            result
            if isinstance(result, AuthoritativeDatumDocumentCatalogResult)
            else AuthoritativeDatumDocumentCatalogResult.from_dict(result)
        )
        documents = tuple(_recognize_document(document) for document in normalized_result.documents)
        selected_document_id = _select_document_id(documents)
        warnings = list(normalized_result.warnings)
        if not documents:
            warnings.append("No authoritative datum documents were available for the current tenant.")
        return DatumWorkbenchProjection(
            tenant_id=normalized_result.tenant_id,
            documents=documents,
            selected_document_id=selected_document_id,
            source_files=normalized_result.source_files,
            readiness_status=normalized_result.readiness_status,
            warnings=tuple(warnings),
        )
