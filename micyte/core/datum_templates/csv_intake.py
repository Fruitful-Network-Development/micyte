"""CSV intake for datum templates.

Reads a CSV file, maps columns to template magnitude names via the
template's ``csv_column_map``, and produces a list of new row payloads
that can be inserted into a datum document at the template's repeating
layer.

Two modes:

* **Bulk insert** — every CSV row becomes a new datum row with all
  mapped magnitudes.
* **Single-column update** — a CSV with one mapped column is treated as
  a retroactive edit: each CSV row binds the named magnitude on the
  matching existing datum row (matched by a configurable join key,
  default: the first required magnitude). Rows without a match are
  skipped and reported as warnings.

Persistence is the caller's responsibility; this module produces row
payloads only and does not touch the SQL adapter.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)
from micyte.core.datum_templates import DatumTemplate
from micyte.core.datum_templates.bacillete import (
    encode_email_bacillete,
    encode_name_bacillete,
)

_PIPELINE_DROP = object()  # sentinel: directive removed the row


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class CsvIntakeResult:
    template_id: str
    archetype: str
    new_rows: tuple[AuthoritativeDatumDocumentRow, ...]
    updated_rows: tuple[AuthoritativeDatumDocumentRow, ...]
    skipped_csv_rows: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "mycite.v2.core.datum_template.csv_intake.v1",
            "template_id": self.template_id,
            "archetype": self.archetype,
            "new_row_count": len(self.new_rows),
            "updated_row_count": len(self.updated_rows),
            "skipped_csv_rows": list(self.skipped_csv_rows),
            "warnings": list(self.warnings),
        }


def import_csv_via_template(
    template: DatumTemplate,
    csv_path: Path | str,
    *,
    document: AuthoritativeDatumDocument | None = None,
    next_iteration_start: int | None = None,
    join_key: str | None = None,
) -> CsvIntakeResult:
    """Translate a CSV into datum row payloads.

    Args:
      template: source-of-truth for csv_column_map and the repeating layer.
      csv_path: path to a UTF-8 CSV file with a header row.
      document: optional existing document. When provided AND the CSV maps
        only one magnitude, intake runs in *single-column update* mode:
        each CSV row updates the matching existing row's magnitude in
        place (joined on ``join_key``, defaulting to the template's first
        required magnitude). Otherwise intake runs in *bulk insert* mode.
      next_iteration_start: starting iteration number for bulk insert.
        Defaults to ``max(existing_iter) + 1`` when ``document`` is
        provided, else ``1``.
      join_key: magnitude name used to match CSV rows against existing
        document rows in single-column update mode.

    Returns:
      CsvIntakeResult listing new rows, updated rows, skipped CSV rows,
      and warnings.
    """
    if template.repeating_archetype is None:
        return CsvIntakeResult(
            template_id=template.template_id,
            archetype=template.archetype,
            new_rows=(),
            updated_rows=(),
            skipped_csv_rows=(),
            warnings=("template_has_no_repeating_archetype",),
        )

    rows = _read_csv_rows(Path(csv_path))
    if not rows:
        return CsvIntakeResult(
            template_id=template.template_id,
            archetype=template.archetype,
            new_rows=(),
            updated_rows=(),
            skipped_csv_rows=(),
            warnings=("csv_empty",),
        )

    csv_to_magnitude = {
        col: mag for col, mag in template.csv_column_map.items() if col in rows[0]
    }
    if not csv_to_magnitude:
        return CsvIntakeResult(
            template_id=template.template_id,
            archetype=template.archetype,
            new_rows=(),
            updated_rows=(),
            skipped_csv_rows=tuple(rows),
            warnings=("no_csv_columns_match_template",),
        )

    single_column_mode = (
        document is not None and len(csv_to_magnitude) == 1
    )
    if single_column_mode:
        return _single_column_update(
            template=template,
            document=document,  # type: ignore[arg-type]
            csv_rows=rows,
            csv_to_magnitude=csv_to_magnitude,
            join_key=join_key,
        )
    return _bulk_insert(
        template=template,
        csv_rows=rows,
        csv_to_magnitude=csv_to_magnitude,
        existing_document=document,
        next_iteration_start=next_iteration_start,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [
            {(_as_text(k)): _as_text(v) for k, v in row.items() if k is not None}
            for row in reader
        ]


def _bulk_insert(
    *,
    template: DatumTemplate,
    csv_rows: list[dict[str, str]],
    csv_to_magnitude: dict[str, str],
    existing_document: AuthoritativeDatumDocument | None,
    next_iteration_start: int | None,
) -> CsvIntakeResult:
    layer = template.repeating_archetype.layer  # type: ignore[union-attr]
    iteration = (
        next_iteration_start
        if next_iteration_start is not None
        else _next_iteration_for_layer(existing_document, layer)
    )

    required_names = tuple(
        m.name for m in template.repeating_archetype.magnitudes if m.required  # type: ignore[union-attr]
    )

    pipeline = list(template.csv_intake_pipeline)
    new_rows: list[AuthoritativeDatumDocumentRow] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []
    accepted_dicts: list[dict[str, Any]] = []
    accepted_csv_rows: list[dict[str, str]] = []

    for csv_row in csv_rows:
        magnitudes: dict[str, Any] = {
            csv_to_magnitude[col]: csv_row[col]
            for col in csv_to_magnitude
            if col in csv_row
        }
        if pipeline:
            piped = _run_intake_pipeline(magnitudes, pipeline, warnings)
            if piped is _PIPELINE_DROP:
                skipped.append(csv_row)
                continue
            magnitudes = piped  # type: ignore[assignment]
        accepted_dicts.append(magnitudes)
        accepted_csv_rows.append(csv_row)

    # Cross-row pass: dedupe directives may live in the pipeline.
    if pipeline:
        deduped_dicts, deduped_csv, removed = _apply_cross_row_directives(
            accepted_dicts, accepted_csv_rows, pipeline, warnings
        )
        skipped.extend(removed)
        accepted_dicts = deduped_dicts
        accepted_csv_rows = deduped_csv

    for magnitudes, csv_row in zip(accepted_dicts, accepted_csv_rows, strict=False):
        missing = [name for name in required_names if name not in magnitudes]
        if missing:
            warnings.append(
                f"row_missing_required_magnitudes:{','.join(missing)}"
            )
            skipped.append(csv_row)
            continue
        address = f"{layer}-0-{iteration}"
        raw_payload = [[address, "~", "0-0-11"], magnitudes]
        new_rows.append(
            AuthoritativeDatumDocumentRow(datum_address=address, raw=raw_payload)
        )
        iteration += 1

    return CsvIntakeResult(
        template_id=template.template_id,
        archetype=template.archetype,
        new_rows=tuple(new_rows),
        updated_rows=(),
        skipped_csv_rows=tuple(skipped),
        warnings=tuple(warnings),
    )


def _single_column_update(
    *,
    template: DatumTemplate,
    document: AuthoritativeDatumDocument,
    csv_rows: list[dict[str, str]],
    csv_to_magnitude: dict[str, str],
    join_key: str | None,
) -> CsvIntakeResult:
    repeating = template.repeating_archetype
    assert repeating is not None
    layer = repeating.layer
    target_magnitude = next(iter(csv_to_magnitude.values()))
    join_magnitude = (
        join_key
        or next((m.name for m in repeating.magnitudes if m.required), "")
    )
    if not join_magnitude:
        return CsvIntakeResult(
            template_id=template.template_id,
            archetype=template.archetype,
            new_rows=(),
            updated_rows=(),
            skipped_csv_rows=tuple(csv_rows),
            warnings=("no_join_magnitude_available",),
        )

    # Find the CSV column that holds the join key
    join_csv_column = next(
        (col for col, mag in template.csv_column_map.items() if mag == join_magnitude and col in csv_rows[0]),
        None,
    )
    if join_csv_column is None:
        return CsvIntakeResult(
            template_id=template.template_id,
            archetype=template.archetype,
            new_rows=(),
            updated_rows=(),
            skipped_csv_rows=tuple(csv_rows),
            warnings=(f"join_csv_column_missing:{join_magnitude}",),
        )

    csv_by_join = {row[join_csv_column]: row for row in csv_rows if row.get(join_csv_column)}
    target_csv_column = next(col for col, mag in csv_to_magnitude.items() if mag == target_magnitude)

    updated: list[AuthoritativeDatumDocumentRow] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []

    for row in document.rows:
        if _row_layer(row.datum_address) != layer:
            continue
        magnitudes = _row_magnitudes(row)
        if magnitudes is None:
            continue
        join_value = magnitudes.get(join_magnitude)
        if join_value not in csv_by_join:
            continue
        csv_row = csv_by_join[join_value]
        new_magnitudes = dict(magnitudes)
        new_magnitudes[target_magnitude] = csv_row.get(target_csv_column, "")
        updated.append(
            AuthoritativeDatumDocumentRow(
                datum_address=row.datum_address,
                raw=[[row.datum_address, "~", "0-0-11"], new_magnitudes],
            )
        )

    matched_join_values = {
        magnitudes.get(join_magnitude)
        for row in document.rows
        if _row_layer(row.datum_address) == layer
        for magnitudes in [_row_magnitudes(row)]
        if magnitudes is not None
    }
    for join_value, csv_row in csv_by_join.items():
        if join_value not in matched_join_values:
            skipped.append(csv_row)
            warnings.append(f"unmatched_join_value:{join_value}")

    return CsvIntakeResult(
        template_id=template.template_id,
        archetype=template.archetype,
        new_rows=(),
        updated_rows=tuple(updated),
        skipped_csv_rows=tuple(skipped),
        warnings=tuple(warnings),
    )


_VALID_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _run_intake_pipeline(
    row: dict[str, Any],
    pipeline: list[dict[str, Any]],
    warnings: list[str],
):
    """Apply per-row directives in order. Returns the (possibly mutated)
    row dict, or the ``_PIPELINE_DROP`` sentinel if the row was dropped.

    Cross-row directives (currently only ``dedupe``) are no-ops here;
    they're applied in :func:`_apply_cross_row_directives` after the
    per-row pass.
    """
    work = dict(row)
    for step in pipeline:
        if not isinstance(step, dict) or len(step) != 1:
            continue
        directive = next(iter(step))
        spec = step[directive] if isinstance(step[directive], dict) else {}
        if directive == "join_name":
            sources = list(spec.get("from") or [])
            target = _as_text(spec.get("to"))
            sep = spec.get("separator", " ") or " "
            if target:
                parts = [_as_text(work.get(s)) for s in sources if _as_text(work.get(s))]
                work[target] = sep.join(parts)
        elif directive == "skip_if_email_in_name":
            name_field = _as_text(spec.get("name_field")) or "name_ascii"
            _as_text(spec.get("email_field")) or "email_ascii"
            name_val = _as_text(work.get(name_field))
            if name_val and "@" in name_val:
                work[name_field] = ""  # blank the bogus name; keep the row
        elif directive == "normalize_email":
            field_name = _as_text(spec.get("field")) or "email_ascii"
            value = _as_text(work.get(field_name))
            if spec.get("lowercase", True):
                value = value.lower()
            work[field_name] = value
        elif directive == "reject_invalid_email":
            field_name = _as_text(spec.get("field")) or "email_ascii"
            value = _as_text(work.get(field_name))
            if not value or not _VALID_EMAIL_RE.match(value):
                warnings.append(f"reject_invalid_email:{value!r}")
                return _PIPELINE_DROP
        elif directive == "bacillete_encode":
            ascii_field = _as_text(spec.get("ascii"))
            binary_field = _as_text(spec.get("binary"))
            confirmed_field = _as_text(spec.get("confirmed"))
            encoder = _as_text(spec.get("encoder")).lower()
            if not ascii_field or not binary_field or not confirmed_field:
                continue
            value = _as_text(work.get(ascii_field))
            if encoder == "name":
                binary, confirmed = encode_name_bacillete(value)
            elif encoder == "email":
                binary, confirmed = encode_email_bacillete(value)
            else:
                warnings.append(f"unknown_bacillete_encoder:{encoder!r}")
                continue
            work[binary_field] = binary
            work[confirmed_field] = confirmed
        elif directive == "drop_scratch_fields":
            prefix = _as_text(spec.get("prefix")) or "_"
            for key in [k for k in work if isinstance(k, str) and k.startswith(prefix)]:
                work.pop(key, None)
        elif directive == "default_field_values":
            for key, default in spec.items():
                if key not in work or work.get(key) in (None, ""):
                    work[key] = default
        elif directive == "dedupe":
            continue  # cross-row pass handles this
        else:
            warnings.append(f"unknown_pipeline_directive:{directive!r}")
    return work


def _apply_cross_row_directives(
    rows: list[dict[str, Any]],
    csv_rows: list[dict[str, str]],
    pipeline: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    removed: list[dict[str, str]] = []
    for step in pipeline:
        if not isinstance(step, dict) or len(step) != 1:
            continue
        directive = next(iter(step))
        if directive != "dedupe":
            continue
        spec = step[directive] if isinstance(step[directive], dict) else {}
        key = _as_text(spec.get("key"))
        keep = _as_text(spec.get("keep")) or "first"
        if not key:
            continue
        seen: dict[str, int] = {}
        kept_rows: list[dict[str, Any]] = []
        kept_csv: list[dict[str, str]] = []
        for _i, (row, csv_row) in enumerate(zip(rows, csv_rows, strict=False)):
            value = _as_text(row.get(key))
            if not value:
                kept_rows.append(row)
                kept_csv.append(csv_row)
                continue
            if value in seen:
                if keep == "last":
                    # Replace prior occurrence
                    prior_index = seen[value]
                    kept_rows[prior_index] = row
                    kept_csv[prior_index] = csv_row
                    removed.append(csv_rows[prior_index])
                else:
                    removed.append(csv_row)
                    warnings.append(f"dedupe_dropped:{value}")
                continue
            seen[value] = len(kept_rows)
            kept_rows.append(row)
            kept_csv.append(csv_row)
        rows = kept_rows
        csv_rows = kept_csv
    return rows, csv_rows, removed


def _next_iteration_for_layer(
    document: AuthoritativeDatumDocument | None,
    layer: int,
) -> int:
    if document is None:
        return 1
    iterations = []
    for row in document.rows:
        parts = row.datum_address.split("-")
        if len(parts) == 3 and parts[0].isdigit() and int(parts[0]) == layer and parts[2].isdigit():
            iterations.append(int(parts[2]))
    return (max(iterations) + 1) if iterations else 1


def _row_layer(address: str) -> int:
    parts = _as_text(address).split("-")
    if len(parts) == 3 and parts[0].isdigit():
        return int(parts[0])
    return -1


def _row_magnitudes(row: AuthoritativeDatumDocumentRow) -> dict[str, Any] | None:
    raw = row.raw
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], dict):
        return dict(raw[1])
    return None


__all__ = [
    "CsvIntakeResult",
    "import_csv_via_template",
]
