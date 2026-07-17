"""Datum templates: archetype-driven scaffolding and recognition.

A *datum template* is a declarative spec that pairs a target schema with
the value-group reference design used by every datum row in a document of
that archetype. Templates serve three purposes:

1. **Scaffold** — produce an empty ``AuthoritativeDatumDocument`` with the
   header rows materialized (schema row, ownership row, etc.) and no
   per-record rows yet. Header rows can interpolate ``{{name}}``
   placeholders from a context dict.
2. **Recognize** — given an existing document, decide whether every row
   in its repeating layer matches the template's reference design. If
   yes, the document carries the template's ``archetype`` AITAS token
   and is eligible for retroactive edits and CSV intake.
3. **Map columns** — declare the mapping from CSV column → datum
   magnitude name, used by ``csv_intake.py`` (Phase 4).

Templates live as YAML files in ``micyte/data_templates/`` — inside the
package, so they ship with the wheel.
The registry loads them on demand.

This package is **read-only** with respect to the AITAS state machine
and the SQL adapter. Mutation persistence happens through the existing
``portal_datum_workbench_mutation_runtime.run_datum_workbench_mutation_action``
seam; this package only produces ``AuthoritativeDatumDocument`` values
and ``DocumentArchetypeReport`` reports.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)

_DATUM_TEMPLATE_SCHEMA = "mycite.v2.core.datum_template.v1"
_ARCHETYPE_REPORT_SCHEMA = "mycite.v2.core.datum_template.archetype_report.v1"
# Package-relative on purpose. This was parents[3]/"data"/"datum_templates" —
# path arithmetic that walked out of the package to MyCiteV2/data/. It broke the
# moment the tree moved, and it could never have shipped: a wheel contains the
# package, so template data living outside it would simply be absent on any
# install. parents[2] is the micyte package root.
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "data_templates"

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_DATUM_ADDRESS_RE = re.compile(r"^(\d+)-(\d+)-(\d+)$")


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class HeaderRowSpec:
    """A header row materialized once per scaffolded document."""

    address: str
    field_name: str
    raw_template: Any  # str (with placeholders), or any JsonValue (passed through)

    def render(self, context: Mapping[str, Any]) -> Any:
        if isinstance(self.raw_template, str):
            return _interpolate_placeholders(self.raw_template, context)
        return self.raw_template


@dataclass(frozen=True)
class MagnitudeSpec:
    """One magnitude (named field) inside a repeating archetype row."""

    name: str
    magnitude_kind: str
    required: bool = True


@dataclass(frozen=True)
class RepeatingArchetypeSpec:
    layer: int
    magnitudes: tuple[MagnitudeSpec, ...]

    @property
    def magnitude_names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.magnitudes)


@dataclass(frozen=True)
class DatumTemplate:
    """Declarative spec for an archetype-shaped datum document."""

    template_id: str
    schema: str
    sandbox: str
    archetype: str
    header_rows: tuple[HeaderRowSpec, ...] = ()
    repeating_archetype: RepeatingArchetypeSpec | None = None
    csv_column_map: dict[str, str] = field(default_factory=dict)
    csv_intake_pipeline: tuple[dict[str, Any], ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _DATUM_TEMPLATE_SCHEMA,
            "template_id": self.template_id,
            "datum_schema": self.schema,
            "sandbox": self.sandbox,
            "archetype": self.archetype,
            "description": self.description,
            "header_rows": [
                {"address": h.address, "field_name": h.field_name}
                for h in self.header_rows
            ],
            "repeating_archetype": (
                {
                    "layer": self.repeating_archetype.layer,
                    "magnitudes": [
                        {
                            "name": m.name,
                            "magnitude_kind": m.magnitude_kind,
                            "required": m.required,
                        }
                        for m in self.repeating_archetype.magnitudes
                    ],
                }
                if self.repeating_archetype is not None
                else None
            ),
            "csv_column_map": dict(self.csv_column_map),
        }


@dataclass(frozen=True)
class DocumentArchetypeReport:
    """Result of running a recognizer over a document."""

    template_id: str
    archetype: str
    matched: bool
    repeating_layer: int
    matched_row_count: int
    total_row_count: int
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _ARCHETYPE_REPORT_SCHEMA,
            "template_id": self.template_id,
            "archetype": self.archetype,
            "matched": self.matched,
            "repeating_layer": self.repeating_layer,
            "matched_row_count": self.matched_row_count,
            "total_row_count": self.total_row_count,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

class TemplateRegistry:
    """Loads and indexes datum templates from a YAML directory.

    The registry is intentionally simple — load on construction, lookup
    by ``template_id``. Reload by re-instantiating.
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = Path(template_dir) if template_dir is not None else _DEFAULT_TEMPLATE_DIR
        self._templates: dict[str, DatumTemplate] = {}
        if self._template_dir.exists():
            for path in sorted(self._template_dir.glob("*.yaml")):
                template = _load_template_file(path)
                if template is not None:
                    self._templates[template.template_id] = template

    @property
    def template_dir(self) -> Path:
        return self._template_dir

    def get(self, template_id: str) -> DatumTemplate | None:
        return self._templates.get(_as_text(template_id))

    def by_archetype(self, archetype: str) -> list[DatumTemplate]:
        token = _as_text(archetype)
        return [t for t in self._templates.values() if t.archetype == token]

    def all(self) -> list[DatumTemplate]:
        return list(self._templates.values())


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------

def recognize_archetype(
    document: AuthoritativeDatumDocument,
    *,
    template: DatumTemplate,
) -> DocumentArchetypeReport:
    """Decide whether ``document``'s repeating layer matches ``template``.

    A match means: every row in the layer carries each required magnitude
    name as part of its raw payload. The check is intentionally lenient —
    raw shapes vary across legacy and migrated docs — but the magnitude
    set must be present.

    Rows whose raw value is a dict and contains every required magnitude
    name as a key count as matches. Rows whose raw value is a list whose
    second element is a dict (the SAMRAS row shape ``[[address-triple],
    {magnitudes}]``) also count when that dict has the required keys.
    """
    if template.repeating_archetype is None:
        return DocumentArchetypeReport(
            template_id=template.template_id,
            archetype=template.archetype,
            matched=False,
            repeating_layer=-1,
            matched_row_count=0,
            total_row_count=len(document.rows),
            notes=("template has no repeating_archetype",),
        )

    layer = template.repeating_archetype.layer
    required = tuple(m.name for m in template.repeating_archetype.magnitudes if m.required)
    layer_rows = [row for row in document.rows if _row_layer(row.datum_address) == layer]
    matched = sum(1 for row in layer_rows if _row_carries_magnitudes(row, required))
    return DocumentArchetypeReport(
        template_id=template.template_id,
        archetype=template.archetype,
        matched=bool(layer_rows) and matched == len(layer_rows),
        repeating_layer=layer,
        matched_row_count=matched,
        total_row_count=len(layer_rows),
    )


def recognize_archetype_in_registry(
    document: AuthoritativeDatumDocument,
    registry: TemplateRegistry,
) -> DocumentArchetypeReport | None:
    """Iterate every template in ``registry`` and return the first match.

    Returns ``None`` when no template's repeating archetype matches.
    """
    for template in registry.all():
        report = recognize_archetype(document, template=template)
        if report.matched:
            return report
    return None


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------

def scaffold_from_template(
    template: DatumTemplate,
    *,
    msn_id: str,
    document_id: str,
    document_name: str,
    relative_path: str,
    canonical_name: str = "",
    context: Mapping[str, Any] | None = None,
) -> AuthoritativeDatumDocument:
    """Produce an empty datum document with the template's header rows.

    The returned document has zero per-record rows. Callers fill in
    repeating-layer rows via the workbench mutation runtime
    (``insert_datum`` operation) or the CSV intake (Phase 4).

    Note: the caller must compute the canonical version_hash and rewrite
    ``document_id`` after rows are added — see
    ``MyCiteV2.scripts.bootstrap_taxonomy_anchor`` for the placeholder →
    real-hash idiom.
    """
    ctx = dict(context or {})
    rows = tuple(
        AuthoritativeDatumDocumentRow(
            datum_address=spec.address,
            raw=spec.render(ctx),
        )
        for spec in template.header_rows
    )
    metadata = {
        "datum_template_id": template.template_id,
        "datum_template_schema": template.schema,
        "datum_template_archetype": template.archetype,
    }
    return AuthoritativeDatumDocument(
        document_id=document_id,
        source_kind="sandbox_source",
        document_name=document_name,
        relative_path=relative_path,
        canonical_name=canonical_name or template.template_id,
        tool_id=template.sandbox,
        is_anchor=False,
        rows=rows,
        document_metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _interpolate_placeholders(text: str, context: Mapping[str, Any]) -> str:
    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return _as_text(context.get(key)) if key in context else match.group(0)

    return _PLACEHOLDER_RE.sub(_sub, text)


def _row_layer(address: str) -> int:
    match = _DATUM_ADDRESS_RE.fullmatch(_as_text(address))
    if not match:
        return -1
    return int(match.group(1))


def _row_carries_magnitudes(
    row: AuthoritativeDatumDocumentRow,
    required: Iterable[str],
) -> bool:
    needed = tuple(required)
    if not needed:
        return True
    raw = row.raw
    candidate: dict[str, Any] | None = None
    if isinstance(raw, dict):
        candidate = raw
    elif isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], dict):
        candidate = raw[1]
    if candidate is None:
        return False
    return all(name in candidate for name in needed)


def _load_template_file(path: Path) -> DatumTemplate | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    template_id = _as_text(payload.get("template_id")) or path.stem
    schema = _as_text(payload.get("schema"))
    sandbox = _as_text(payload.get("sandbox"))
    archetype = _as_text(payload.get("archetype"))
    if not schema or not sandbox or not archetype:
        return None
    header_rows = tuple(
        HeaderRowSpec(
            address=_as_text(item.get("address")),
            field_name=_as_text(item.get("field")),
            raw_template=item.get("raw"),
        )
        for item in (payload.get("header_rows") or [])
        if isinstance(item, dict) and _as_text(item.get("address"))
    )
    repeating_payload = payload.get("repeating_archetype")
    repeating: RepeatingArchetypeSpec | None = None
    if isinstance(repeating_payload, dict):
        magnitudes_payload = repeating_payload.get("value_group_reference_design") or {}
        if isinstance(magnitudes_payload, dict) and magnitudes_payload:
            magnitudes = tuple(
                MagnitudeSpec(
                    name=_as_text(name),
                    magnitude_kind=_as_text((spec or {}).get("magnitude_kind")),
                    required=bool((spec or {}).get("required", True)),
                )
                for name, spec in magnitudes_payload.items()
                if _as_text(name)
            )
            repeating = RepeatingArchetypeSpec(
                layer=int(repeating_payload.get("layer", 1)),
                magnitudes=magnitudes,
            )
    csv_map_payload = payload.get("csv_column_map") or {}
    csv_map = {
        _as_text(k): _as_text(v)
        for k, v in csv_map_payload.items()
        if _as_text(k) and _as_text(v)
    } if isinstance(csv_map_payload, dict) else {}
    pipeline_payload = payload.get("csv_intake_pipeline") or []
    csv_pipeline = tuple(
        dict(step) for step in pipeline_payload if isinstance(step, dict)
    )
    return DatumTemplate(
        template_id=template_id,
        schema=schema,
        sandbox=sandbox,
        archetype=archetype,
        header_rows=header_rows,
        repeating_archetype=repeating,
        csv_column_map=csv_map,
        csv_intake_pipeline=csv_pipeline,
        description=_as_text(payload.get("description")),
    )


__all__ = [
    "DatumTemplate",
    "DocumentArchetypeReport",
    "HeaderRowSpec",
    "MagnitudeSpec",
    "RepeatingArchetypeSpec",
    "TemplateRegistry",
    "recognize_archetype",
    "recognize_archetype_in_registry",
    "scaffold_from_template",
]
