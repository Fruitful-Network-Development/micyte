from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from micyte.adapters.sql import (
    SqliteDirectiveContextAdapter,
    SqliteSystemDatumStoreAdapter,
)
from micyte.core.datum_rules import family_column_template
from micyte.core.datum_semantics import (
    build_document_semantics,
    build_document_version_identity,
    datum_address_sort_key,
    parse_datum_address,
)
from micyte.core.mss import (
    build_catalog_index,
    datum_closure_to_mss,
    document_closure_to_mss,
    mss_document_hash,
)
from micyte.domains.datum_recognition import recognize_authoritative_document
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRequest,
)
from micyte.ports.directive_context import (
    DirectiveContextEventQuery,
    DirectiveContextRequest,
)
from micyte.state_machine.lens import resolve_datum_lens
from micyte.tools._shared.utilities import as_text as _as_text

WORKBENCH_UI_TOOL_ID = "workbench_ui"
# Canonical hash policy for the render. Default = the JSON+SHA256 stand-in
# (mos.mss_sha256_v1). Set MOS_CANONICAL_HASH=mss_binary_v2 to make the render
# compute the BINARY MSS document hash + per-datum binary hyphae, so it agrees
# with a store migrated by scripts/recompile_datum_semantics. Flag-gated → with
# the flag unset, behavior is byte-for-byte unchanged (the golden test holds).
_MSS_BINARY_POLICY = "mss_binary_v2"


def _canonical_hash_policy() -> str:
    return (os.environ.get("MOS_CANONICAL_HASH") or "").strip() or "mss_sha256_v1"


WORKBENCH_UI_DEFAULT_DOCUMENT_SORT = "version_hash"
WORKBENCH_UI_DEFAULT_ROW_SORT = "datum_address"
WORKBENCH_UI_DEFAULT_GROUP = "flat"
WORKBENCH_UI_DEFAULT_LENS = "interpreted"
WORKBENCH_UI_DEFAULT_SOURCE_VISIBILITY = "show"
WORKBENCH_UI_DEFAULT_OVERLAY_VISIBILITY = "show"

_DOCUMENT_SORT_KEYS = {
    "document_id",
    "document_name",
    "source_kind",
    "row_count",
    "version_hash",
}
_ROW_SORT_KEYS = {
    "datum_address",
    "layer",
    "value_group",
    "iteration",
    "labels",
    "relation",
    "object_ref",
    "hyphae_hash",
}
_GROUP_MODES = {"flat", "layer", "layer_value_group", "layer_value_group_iteration"}
_LENS_MODES = {"interpreted", "raw"}
_VISIBILITY_MODES = {"show", "hide"}


def _normalize_sort_key(value: object, *, allowed: set[str], default: str) -> str:
    sort_key = _as_text(value).lower() or default
    if sort_key not in allowed:
        return default
    return sort_key


def _normalize_sort_direction(value: object) -> str:
    return "desc" if _as_text(value).lower() == "desc" else "asc"


def _normalize_mode(value: object, *, allowed: set[str], default: str) -> str:
    token = _as_text(value).lower() or default
    if token not in allowed:
        return default
    return token


def _short_hash(value: object, *, length: int = 12) -> str:
    token = _as_text(value)
    return token[:length] if token else ""


# Real document file extensions we strip from a fallback document_name. NOT any
# short dotted token — a name like "report.v2" / "inventory.feb" must keep its tail.
_STRIPPABLE_EXTENSIONS = frozenset({"json", "yaml", "yml", "txt", "md", "csv"})


def _short_document_name(document_name: object) -> str:
    """Reduce a possibly path/dotted document_name to a clean short label.

    Strips any directory component (full filesystem paths) and a recognized file
    extension. Used only as a fallback when canonical_name is absent — the
    canonical_name projection is the authoritative clean name for every doc.
    """
    text = _as_text(document_name)
    if not text:
        return ""
    base = text.replace("\\", "/").rsplit("/", 1)[-1]
    stem, sep, ext = base.rpartition(".")
    if sep and stem and ext.lower() in _STRIPPABLE_EXTENSIONS:
        base = stem
    return base or text


def _document_display_name(document: AuthoritativeDatumDocument) -> str:
    """The clean short label shown in the workbench doc-list.

    Prefer the authoritative canonical_name; fall back to a cleaned
    document_name; last resort the document_id. Never a raw path/dotted blob.
    """
    canonical = _as_text(getattr(document, "canonical_name", ""))
    if canonical:
        return canonical
    return _short_document_name(getattr(document, "document_name", "")) or _as_text(document.document_id)


# Datum-KIND classification → the standardized displayer BODY a document should
# dispatch to. The workbench editor reads this signal to auto-select a kind-aware
# summary (contact card / record table / …) instead of always rendering the raw
# datum grid. Conservative by design: any identity that matches no known pattern
# resolves to "document" (the raw grid), so a new kind is added by EXTENDING the
# pattern table, never by loosening the default.
_DATUM_KIND_DOCUMENT = "document"

# Ordered (first match wins): stronger structural identities before weaker ones.
# Each (kind, tokens) selects `kind` when any token is a case-insensitive
# substring of the canonical/document name. Tokens are grounded in the live fnd
# corpus — registrar/registry cards, trapp invoices/contracts, taxonomy `txa`,
# `*_profiles` — with a few forward-looking geo tokens (no geo docs exist yet).
# Note the deliberate contact/contract split: the record token is "contract"
# (with the r), and the card tokens require the hyphen/underscore ("contact-card"
# / "contact_card"), so a plural "contacts" TABLE never misfires as a card.
_DATUM_KIND_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tree", ("txa", "taxonomy", "dendrogram")),
    ("record", ("invoice", "ledger", "contract", "receipt", "statement")),
    ("geo_map", ("geospatial", "coordinate", "parcel", "cts_gis", "ruigi", "geo_", "_geo", "land")),
    ("contact_card", ("contact-card", "contact_card", "registry", "registrar")),
    ("profile", ("profile",)),
)


def _classify_datum_kind(
    document_name: object,
    source_kind: object,
    canonical_name: object,
) -> str:
    """Map a document's identity to its standardized displayer-body KIND.

    Pure, conservative helper returning one of
    ``contact_card | profile | record | geo_map | tree | document``. It is the
    single datum-KIND signal the workbench editor uses to auto-dispatch to a
    kind-aware summary body; it never reads or mutates the store.

    ``source_kind`` carries only ``sandbox_source`` | ``system_anthology`` in
    the corpus, so it is not a kind descriptor — identity comes from the
    canonical/document name. The tenant system-anthology INDEX is never a
    displayable artifact, so it short-circuits to ``document``. Any name that
    matches no known identity pattern also resolves to ``document`` (raw grid).
    """
    if _as_text(source_kind).lower() == "system_anthology":
        return _DATUM_KIND_DOCUMENT
    haystack = f"{_as_text(canonical_name).lower()} {_as_text(document_name).lower()}"
    if not haystack.strip():
        return _DATUM_KIND_DOCUMENT
    for kind, tokens in _DATUM_KIND_PATTERNS:
        if any(token in haystack for token in tokens):
            return kind
    return _DATUM_KIND_DOCUMENT


def _truncate_text(value: object, *, limit: int = 96) -> str:
    token = _as_text(value)
    if len(token) <= limit:
        return token
    return f"{token[:limit - 1]}…"


def _json_text(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return _as_text(value)


def _joined_labels(raw: Any) -> str:
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], (list, tuple)):
        return ", ".join(_as_text(item) for item in raw[1] if _as_text(item))
    if isinstance(raw, dict):
        labels = raw.get("labels") or raw.get("label") or raw.get("name") or ()
        if isinstance(labels, (list, tuple)):
            return ", ".join(_as_text(item) for item in labels if _as_text(item))
        return _as_text(labels)
    return ""


def _relation(raw: Any) -> str:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        triple = raw[0]
        return _as_text(triple[1] if len(triple) > 1 else "")
    if isinstance(raw, dict):
        return _as_text(raw.get("relation") or raw.get("predicate"))
    return ""


def _object_ref(raw: Any, *, datum_address: str) -> str:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        triple = raw[0]
        return _as_text(triple[2] if len(triple) > 2 else "")
    if isinstance(raw, dict):
        return _as_text(raw.get("object_ref") or raw.get("object") or datum_address)
    return ""


def _document_filter_haystack(document: dict[str, Any]) -> str:
    return " ".join(
        _as_text(document.get(key)).lower()
        for key in ("document_id", "document_name", "source_kind", "version_hash")
    )


def _document_sort_value(document: dict[str, Any], *, sort_key: str) -> Any:
    if sort_key == "row_count":
        return int(document.get(sort_key) or 0)
    return _as_text(document.get(sort_key)).lower()


def _row_filter_haystack(row: dict[str, Any]) -> str:
    return " ".join(
        _as_text(row.get(key)).lower()
        for key in (
            "datum_address",
            "labels",
            "relation",
            "object_ref",
            "hyphae_hash",
            "semantic_hash",
            "raw_json",
            "display_value",
            "recognized_family",
            "resolved_lens",
        )
    )


def _row_sort_value(row: dict[str, Any], *, sort_key: str) -> Any:
    if sort_key == "datum_address":
        return datum_address_sort_key(row["datum_address"])
    if sort_key in {"layer", "value_group", "iteration"}:
        return int(row.get(sort_key) or 0)
    return _as_text(row.get(sort_key)).lower()


def _joined_tokens(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return _as_text(values)
    return ", ".join(_as_text(item) for item in values if _as_text(item))


def _first_non_empty(*values: object) -> str:
    for value in values:
        token = _as_text(value)
        if token:
            return token
    return ""


def _display_summary(*, relation: str, object_ref: str, recognized_family: str, resolved_lens: str, diagnostics: tuple[str, ...]) -> str:
    bits = [
        recognized_family,
        f"lens:{resolved_lens}" if resolved_lens else "",
        f"{relation} -> {object_ref}" if relation or object_ref else "",
        _joined_tokens(diagnostics),
    ]
    return " · ".join(bit for bit in bits if bit)


def _layer_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layers: dict[int, dict[str, Any]] = {}
    value_groups: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        layer = int(row.get("layer") or 0)
        value_group = int(row.get("value_group") or 0)
        layer_entry = layers.setdefault(
            layer,
            {
                "layer": layer,
                "title": f"Layer {layer}",
                "summary": f"Iteration cells grouped under layer {layer}.",
                "value_groups": [],
                "row_count": 0,
                "selected": False,
            },
        )
        value_group_entry = value_groups.setdefault(
            (layer, value_group),
            {
                "value_group": value_group,
                "title": f"Value Group {value_group}",
                "summary": f"Iteration cells for value group {value_group}.",
                "cells": [],
                "row_count": 0,
                "selected": False,
            },
        )
        if value_group_entry not in layer_entry["value_groups"]:
            layer_entry["value_groups"].append(value_group_entry)
        value_group_entry["cells"].append(row)
        value_group_entry["row_count"] += 1
        value_group_entry["selected"] = value_group_entry["selected"] or bool(row.get("selected"))
        layer_entry["row_count"] += 1
        layer_entry["selected"] = layer_entry["selected"] or bool(row.get("selected"))
    ordered_layers = [layers[key] for key in sorted(layers)]
    for layer_entry in ordered_layers:
        groups = sorted(
            list(layer_entry["value_groups"]),
            key=lambda item: int(item.get("value_group") or 0),
        )
        for group in groups:
            group["cells"] = sorted(
                list(group["cells"]),
                key=lambda item: datum_address_sort_key(item["datum_address"]),
            )
            group["column_template"] = [
                {"role": col.role, "index": col.index, "key": col.key, "variadic": col.variadic}
                for col in family_column_template(
                    [(cell.get("datum_address"), cell.get("raw")) for cell in group["cells"]]
                )
            ]
        layer_entry["value_groups"] = groups
    return ordered_layers


def _overlay_summary_rows(overlay: dict[str, Any] | None, *, event_rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    rows = [
        {"label": "overlay", "value": "loaded" if overlay is not None else "missing"},
        {"label": "context id", "value": _as_text((overlay or {}).get("context_id")) or "—"},
        {"label": "subject version hash", "value": _as_text((overlay or {}).get("subject_version_hash")) or "—"},
        {"label": "subject hyphae hash", "value": _as_text((overlay or {}).get("subject_hyphae_hash")) or "—"},
    ]
    if overlay is not None:
        rows.append(
            {
                "label": "NIMM",
                "value": json.dumps(dict(overlay.get("nimm_state") or {}), sort_keys=True),
            }
        )
        rows.append(
            {
                "label": "AITAS",
                "value": json.dumps(dict(overlay.get("aitas_state") or {}), sort_keys=True),
            }
        )
    event_rows = list(event_rows)
    if event_rows:
        rows.append({"label": "recent events", "value": str(len(event_rows))})
    return rows


def _document_table_columns(*, source_visibility: str) -> list[dict[str, str]]:
    columns = [
        {"key": "label", "label": "document"},
        {"key": "document_id", "label": "document_id"},
    ]
    if source_visibility == "show":
        columns.append({"key": "source_kind", "label": "source_kind"})
    columns.extend(
        [
            {"key": "version_hash_short", "label": "version_hash_badge"},
            {"key": "version_hash", "label": "version_hash"},
            {"key": "row_count", "label": "row_count"},
        ]
    )
    return columns


def _datum_grid_columns(*, workbench_lens: str) -> list[dict[str, str]]:
    columns = [
        {"key": "datum_address", "label": "datum_address"},
        {"key": "layer", "label": "layer"},
        {"key": "value_group", "label": "value_group"},
        {"key": "iteration", "label": "iteration"},
    ]
    if workbench_lens == "raw":
        columns.extend(
            [
                {"key": "raw_preview", "label": "raw"},
                {"key": "hyphae_hash_short", "label": "hyphae_hash_badge"},
            ]
        )
    else:
        columns.extend(
            [
                {"key": "labels", "label": "labels"},
                {"key": "relation", "label": "relation"},
                {"key": "object_ref", "label": "object_ref"},
                {"key": "hyphae_hash_short", "label": "hyphae_hash_badge"},
            ]
        )
    return columns


def _group_rows(rows: list[dict[str, Any]], *, group_mode: str, workbench_lens: str) -> list[dict[str, Any]]:
    if group_mode == "flat":
        return [
            {
                "key": "flat",
                "title": "All Rows",
                "summary": "Flat row list for the selected authoritative document.",
                "columns": _datum_grid_columns(workbench_lens=workbench_lens),
                "items": rows,
                "row_count": len(rows),
            }
        ]

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if group_mode == "layer":
            key = f"layer:{row['layer']}"
            title = f"Layer {row['layer']}"
            summary = f"Canonical datum order within layer {row['layer']}."
        else:
            key = f"layer:{row['layer']}:value_group:{row['value_group']}"
            title = f"Layer {row['layer']} / Value Group {row['value_group']}"
            summary = (
                f"Canonical datum order within layer {row['layer']} "
                f"and value group {row['value_group']}."
            )
        grouped.setdefault(
            key,
            {
                "key": key,
                "title": title,
                "summary": summary,
                "columns": _datum_grid_columns(workbench_lens=workbench_lens),
                "items": [],
            },
        )["items"].append(row)

    groups = list(grouped.values())
    for group in groups:
        items = list(group["items"])
        items.sort(key=lambda item: datum_address_sort_key(item["datum_address"]))
        group["items"] = items
        group["row_count"] = len(items)
    groups.sort(key=lambda group: datum_address_sort_key(group["items"][0]["datum_address"]) if group["items"] else ())
    return groups


def _section_rows_for_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for group in groups:
        sections.append(
            {
                "title": group["title"],
                "summary": group["summary"],
                "columns": list(group["columns"]),
                "items": list(group["items"]),
            }
        )
    return sections


def _navigation_item(items: list[dict[str, Any]], *, index: int, label_key: str, id_key: str) -> dict[str, str] | None:
    if index < 0 or index >= len(items):
        return None
    item = items[index]
    return {
        "id": _as_text(item.get(id_key)),
        "label": _as_text(item.get(label_key)) or _as_text(item.get(id_key)) or "—",
    }


def _preferred_document_id(document_rows: list[dict[str, Any]]) -> str:
    for document in document_rows:
        if document.get("is_anchor"):
            return _as_text(document.get("document_id"))
    return _as_text((document_rows[0] if document_rows else {}).get("document_id"))


# Projection cache. ``read_surface`` re-reads/filters/sorts/groups the entire
# document set on every request; for view-only navigation (sort/group/lens
# toggles, row/document selection) the catalog has not changed, so the heavy
# per-row recognition + SQL semantic reads in ``_row_items`` are pure waste.
# We memoize the assembled projection keyed by a content fingerprint of the
# catalog content. The fingerprint hashes document identity + row content
# (NOT just document ids — legacy ``system:`` / ``sandbox:`` ids are stable
# regardless of content, so an in-place row edit must still be detected), plus
# the normalized view parameters. The catalog rows are already in memory from
# the store read, so this is an I/O-free CPU hash and is cheaper than the
# recognition + SQL semantic reads a cache hit avoids. It does not rely on
# filesystem mtime granularity. Entries that resolved a live directive overlay
# are never stored (see ``read_surface``). The cache is process-local and
# bounded; it holds no on-disk state (MOS-only datum rule).
_GLOBAL_SURFACE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_SURFACE_CACHE_MAX_ENTRIES = 256

# The catalog fingerprint is a SHA-256 over every row of every document, so it is
# wasteful to recompute on every request (it runs before the surface-cache lookup,
# so even cache HITs pay it). The catalog content is fully determined by the db
# file's mtime — the same freshness signal the datum store keys its own catalog
# cache on — so memoize the fingerprint per (db_file, mtime_ns). A write bumps the
# mtime (the store guarantees this), yielding a new key and a fresh fingerprint.
_FINGERPRINT_MEMO: dict[tuple[str, int], str] = {}
_FINGERPRINT_MEMO_MAX_ENTRIES = 64


def _catalog_fingerprint(catalog: Any) -> str:
    digest = hashlib.sha256()
    for document in catalog.documents:
        digest.update(_as_text(document.document_id).encode("utf-8"))
        digest.update(b"\x00")
        digest.update(_as_text(document.document_name).encode("utf-8"))
        digest.update(b"\x00")
        # ``raw`` rows fully determine a document's content/version.
        digest.update(
            json.dumps(
                [[row.datum_address, row.raw] for row in document.rows],
                separators=(",", ":"),
                sort_keys=False,
                default=str,
            ).encode("utf-8")
        )
        digest.update(b"\x1e")
    return digest.hexdigest()


def _surface_cache_key(
    *,
    db_file: str,
    portal_instance_id: str,
    catalog: Any,
    query: dict[str, Any],
    enabled_lens_ids: frozenset[str] | None = None,
    hash_policy: str = "mss_sha256_v1",
    catalog_fingerprint: str | None = None,
) -> tuple[Any, ...]:
    fingerprint = catalog_fingerprint if catalog_fingerprint is not None else _catalog_fingerprint(catalog)
    # The enabled-lens policy changes the rendered display values, so it MUST be
    # part of the key (None = all-enabled is its own distinct bucket).
    lens_key = "*" if enabled_lens_ids is None else ",".join(sorted(enabled_lens_ids))
    return (
        db_file,
        portal_instance_id,
        fingerprint,
        lens_key,
        hash_policy,
        _as_text(query.get("document")),
        _as_text(query.get("row")),
        _as_text(query.get("sandbox_filter")),
        _as_text(query.get("document_filter")).lower(),
        _normalize_sort_key(
            query.get("document_sort"),
            allowed=_DOCUMENT_SORT_KEYS,
            default=WORKBENCH_UI_DEFAULT_DOCUMENT_SORT,
        ),
        _normalize_sort_direction(query.get("document_dir")),
        _as_text(query.get("filter")).lower(),
        _normalize_sort_key(query.get("sort"), allowed=_ROW_SORT_KEYS, default=WORKBENCH_UI_DEFAULT_ROW_SORT),
        _normalize_sort_direction(query.get("dir")),
        _normalize_mode(query.get("group"), allowed=_GROUP_MODES, default=WORKBENCH_UI_DEFAULT_GROUP),
        _normalize_mode(query.get("workbench_lens"), allowed=_LENS_MODES, default=WORKBENCH_UI_DEFAULT_LENS),
        _normalize_mode(query.get("source"), allowed=_VISIBILITY_MODES, default=WORKBENCH_UI_DEFAULT_SOURCE_VISIBILITY),
        _normalize_mode(query.get("overlay"), allowed=_VISIBILITY_MODES, default=WORKBENCH_UI_DEFAULT_OVERLAY_VISIBILITY),
    )


class WorkbenchUiReadService:
    def __init__(self, db_file: str | Path) -> None:
        self._db_file = Path(db_file)
        self._datum_store = SqliteSystemDatumStoreAdapter(self._db_file)
        self._directive_context = SqliteDirectiveContextAdapter(self._db_file)

    def _build_document_entry(
        self,
        *,
        tenant_id: str,
        document: AuthoritativeDatumDocument,
        mss_index: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del tenant_id  # identity is derived from the document, not a SQL lookup
        # Phase 3 cut-over: derive the version identity from the document via the
        # core engine — the SAME engine the store uses at write time
        # (store_authoritative_catalog → build_document_semantics) — instead of
        # reading the persisted SQL projection. One materialized source of truth.
        # When MOS_CANONICAL_HASH=mss_binary_v2 (mss_index provided), the canonical
        # identity is the BINARY MSS hash of the document's tenant-wide downward
        # closure — matching a store migrated by recompile_datum_semantics.
        if mss_index is not None:
            version_hash = mss_document_hash(document_closure_to_mss(document, index=mss_index))
        else:
            version_hash = _as_text(build_document_version_identity(document).get("version_hash"))
        display_name = _document_display_name(document)
        return {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "canonical_name": _as_text(document.canonical_name),
            "label": display_name,
            "source_kind": document.source_kind,
            "row_count": int(document.row_count),
            "version_hash": version_hash,
            "version_hash_short": _short_hash(version_hash),
            "is_anchor": bool(document.is_anchor),
            "selected": False,
        }

    def _row_items(
        self,
        *,
        tenant_id: str,
        document: AuthoritativeDatumDocument,
        enabled_lens_ids: frozenset[str] | None = None,
        mss_index: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del tenant_id  # semantics are derived from the document, not a SQL lookup
        # Phase 3 cut-over: derive every row's semantics in ONE core-engine pass
        # (build_document_semantics) — the SAME engine the store runs at write
        # time — instead of one read_datum_semantic_identity SQL read per row.
        # This retires the per-row SQL hotspot and unifies read + write on the
        # core engine. Derive from the catalog document directly: the single-doc
        # WORKBOOK-YAML codec is intentionally lossy for anchor context
        # (anchor_rows / anchor_document_metadata), which the engine folds into
        # the anchor-context hash, so a round-trip here would corrupt the hashes
        # of anchored documents.
        row_semantics = build_document_semantics(document)["rows"]
        recognized_document = recognize_authoritative_document(document)
        recognized_rows = {
            row.datum_address: row
            for row in recognized_document.rows
        }
        items: list[dict[str, Any]] = []
        for row in sorted(document.rows, key=lambda item: datum_address_sort_key(item.datum_address)):
            layer, value_group, iteration = parse_datum_address(row.datum_address)
            semantics = row_semantics.get(row.datum_address)
            recognized = recognized_rows.get(row.datum_address)
            # Binary mode: the per-datum hyphae is the MSS hash of its downward
            # closure (matching recompile_datum_semantics); semantic_hash + the
            # other derived fields stay on the engine fold (as the migration left
            # them). Default mode keeps the engine hyphae_hash.
            _binary_closure = (
                datum_closure_to_mss(row.datum_address, index=mss_index)
                if mss_index is not None else None
            )
            if _binary_closure is not None:
                hyphae_hash = mss_document_hash(_binary_closure)
            else:
                hyphae_hash = _as_text((semantics or {}).get("hyphae_hash"))
            semantic_hash = _as_text((semantics or {}).get("semantic_hash"))
            recognized_family = _as_text(getattr(recognized, "recognized_family", ""))
            recognized_anchor = _as_text(getattr(recognized, "recognized_anchor", ""))
            primary_value_token = _as_text(getattr(recognized, "primary_value_token", ""))
            render_hints = dict(getattr(recognized, "render_hints", {}) or {})
            diagnostics = tuple(getattr(recognized, "diagnostic_states", ()) or ())
            reference_bindings = [
                binding.to_dict() if hasattr(binding, "to_dict") else dict(binding)
                for binding in (getattr(recognized, "reference_bindings", ()) or ())
            ]
            lens_resolution = resolve_datum_lens(
                recognized_family=recognized_family,
                primary_value_kind=render_hints.get("primary_value_kind"),
                overlay_kind=render_hints.get("overlay_kind"),
                enabled_lens_ids=enabled_lens_ids,
            )
            display_value = _first_non_empty(
                lens_resolution.lens.decode(primary_value_token) if primary_value_token else "",
                _joined_labels(row.raw),
                _object_ref(row.raw, datum_address=row.datum_address),
            )
            raw_json = _json_text(row.raw)
            if _binary_closure is not None:
                hyphae_chain_addresses = [d.address for d in _binary_closure]
                hyphae_policy = "mos.mss_binary_v2"
            else:
                hyphae_chain = dict((semantics or {}).get("hyphae_chain") or {})
                hyphae_chain_addresses = list(hyphae_chain.get("addresses") or [])
                hyphae_policy = _as_text((semantics or {}).get("policy"))
            local_references = list((semantics or {}).get("local_references") or [])
            items.append(
                {
                    "datum_address": row.datum_address,
                    "layer": layer,
                    "value_group": value_group,
                    "iteration": iteration,
                    "labels": _joined_labels(row.raw),
                    "relation": _relation(row.raw),
                    "object_ref": _object_ref(row.raw, datum_address=row.datum_address),
                    "recognized_family": recognized_family,
                    "recognized_anchor": recognized_anchor,
                    "primary_value_token": primary_value_token,
                    "primary_value_kind": _as_text(render_hints.get("primary_value_kind")),
                    "overlay_kind": _as_text(render_hints.get("overlay_kind")),
                    "diagnostic_states": list(diagnostics),
                    "reference_bindings": reference_bindings,
                    "resolved_lens": lens_resolution.lens_id,
                    "resolved_lens_match": lens_resolution.matched_on,
                    "display_value": display_value,
                    "display_summary": _display_summary(
                        relation=_relation(row.raw),
                        object_ref=_object_ref(row.raw, datum_address=row.datum_address),
                        recognized_family=recognized_family,
                        resolved_lens=lens_resolution.lens_id,
                        diagnostics=diagnostics,
                    ),
                    "hyphae_hash": hyphae_hash,
                    "hyphae_hash_short": _short_hash(hyphae_hash),
                    "semantic_hash": semantic_hash,
                    "semantic_hash_short": _short_hash(semantic_hash),
                    "hyphae_policy": hyphae_policy,
                    "hyphae_chain_addresses": hyphae_chain_addresses,
                    "hyphae_chain_length": len(hyphae_chain_addresses),
                    "local_references": local_references,
                    "local_reference_count": len(local_references),
                    "warnings": list((semantics or {}).get("warnings") or []),
                    "raw": row.raw,
                    "raw_json": raw_json,
                    "raw_preview": _truncate_text(raw_json),
                    "selected": False,
                }
            )
        return items

    def read_surface(
        self,
        *,
        portal_instance_id: str,
        portal_domain: str,
        surface_query: dict[str, Any] | None = None,
        enabled_lens_ids: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        del portal_domain
        query = dict(surface_query or {})
        # The catalog read is already cached + correctly invalidated by the
        # datum store (mtime + explicit pop on every write), so it is the
        # cheap, authoritative freshness signal we fingerprint the cache on.
        catalog = self._datum_store.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=portal_instance_id)
        )
        hash_policy = _canonical_hash_policy()
        # Build the closure index ONLY in binary mode (default mode never needs
        # it, so there's zero added cost when the flag is unset).
        mss_index = build_catalog_index(catalog) if hash_policy == _MSS_BINARY_POLICY else None
        # Memoize the (expensive) catalog fingerprint by db mtime — see
        # _FINGERPRINT_MEMO. Falls back to a direct compute if the file can't
        # be stat'd (then the catalog itself would be empty/unavailable anyway).
        try:
            _mtime_ns = os.stat(self._db_file).st_mtime_ns
        except OSError:
            _mtime_ns = -1
        if _mtime_ns < 0:
            fingerprint = _catalog_fingerprint(catalog)
        else:
            fp_key = (str(self._db_file), _mtime_ns)
            fingerprint = _FINGERPRINT_MEMO.get(fp_key)
            if fingerprint is None:
                fingerprint = _catalog_fingerprint(catalog)
                if len(_FINGERPRINT_MEMO) >= _FINGERPRINT_MEMO_MAX_ENTRIES:
                    _FINGERPRINT_MEMO.clear()
                _FINGERPRINT_MEMO[fp_key] = fingerprint
        cache_key = _surface_cache_key(
            db_file=str(self._db_file),
            portal_instance_id=portal_instance_id,
            catalog=catalog,
            query=query,
            enabled_lens_ids=enabled_lens_ids,
            hash_policy=hash_policy,
            catalog_fingerprint=fingerprint,
        )
        cached = _GLOBAL_SURFACE_CACHE.get(cache_key)
        if cached is not None:
            # The runtime bundle builder mutates the returned model in place
            # (schema / request_contract stamping, navigation decoration), so
            # a hit must return an independent copy or the cache corrupts.
            return copy.deepcopy(cached)

        result = self._compute_surface(
            portal_instance_id=portal_instance_id,
            query=query,
            catalog=catalog,
            enabled_lens_ids=enabled_lens_ids,
            mss_index=mss_index,
        )

        # Directive overlays are live, advisory annotations served from a
        # separate subsystem. Only memoize projections that resolved no
        # overlay, so an overlay can never be served stale; everything else in
        # the projection is fully determined by the catalog fingerprint.
        if result.get("overlay") is None:
            if len(_GLOBAL_SURFACE_CACHE) >= _SURFACE_CACHE_MAX_ENTRIES:
                _GLOBAL_SURFACE_CACHE.clear()
            _GLOBAL_SURFACE_CACHE[cache_key] = copy.deepcopy(result)
        return result

    def _compute_surface(
        self,
        *,
        portal_instance_id: str,
        query: dict[str, Any],
        catalog: Any,
        enabled_lens_ids: frozenset[str] | None = None,
        mss_index: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_document_id = _as_text(query.get("document"))
        selected_row_id = _as_text(query.get("row"))
        document_filter = _as_text(query.get("document_filter")).lower()
        document_sort_key = _normalize_sort_key(
            query.get("document_sort"),
            allowed=_DOCUMENT_SORT_KEYS,
            default=WORKBENCH_UI_DEFAULT_DOCUMENT_SORT,
        )
        document_sort_direction = _normalize_sort_direction(query.get("document_dir"))
        text_filter = _as_text(query.get("filter")).lower()
        row_sort_key = _normalize_sort_key(query.get("sort"), allowed=_ROW_SORT_KEYS, default=WORKBENCH_UI_DEFAULT_ROW_SORT)
        row_sort_direction = _normalize_sort_direction(query.get("dir"))
        group_mode = _normalize_mode(query.get("group"), allowed=_GROUP_MODES, default=WORKBENCH_UI_DEFAULT_GROUP)
        workbench_lens = _normalize_mode(query.get("workbench_lens"), allowed=_LENS_MODES, default=WORKBENCH_UI_DEFAULT_LENS)
        source_visibility = _normalize_mode(
            query.get("source"),
            allowed=_VISIBILITY_MODES,
            default=WORKBENCH_UI_DEFAULT_SOURCE_VISIBILITY,
        )
        overlay_visibility = _normalize_mode(
            query.get("overlay"),
            allowed=_VISIBILITY_MODES,
            default=WORKBENCH_UI_DEFAULT_OVERLAY_VISIBILITY,
        )

        sandbox_filter = _as_text(query.get("sandbox_filter"))
        documents = list(catalog.documents)
        if sandbox_filter:
            # Per-tool sandbox scoping (added 2026-05-17 for the Trapp Family Farm
            # workbench surface). Documents are kept when the canonical
            # document_id segment ``.{sandbox}.`` matches the requested
            # sandbox token. Tools that need to show the entire tenant
            # corpus (Workbench-UI) leave sandbox_filter unset.
            marker = f".{sandbox_filter}."
            documents = [
                document
                for document in documents
                if marker in _as_text(document.document_id)
            ]
        document_rows = [
            self._build_document_entry(
                tenant_id=portal_instance_id, document=document, mss_index=mss_index
            )
            for document in documents
        ]
        if document_filter:
            document_rows = [document for document in document_rows if document_filter in _document_filter_haystack(document)]
        document_rows.sort(
            key=lambda document: (
                _document_sort_value(document, sort_key=document_sort_key),
                _as_text(document.get("document_id")).lower(),
            ),
            reverse=document_sort_direction == "desc",
        )
        # Pin the sandbox anchor document first regardless of sort direction
        # (stable sort preserves the prior ordering within each group).
        document_rows.sort(key=lambda document: 0 if document.get("is_anchor") else 1)
        if selected_document_id not in {document["document_id"] for document in document_rows}:
            selected_document_id = ""
        if not selected_document_id and document_rows:
            selected_document_id = _preferred_document_id(document_rows)

        active_document = next((document for document in documents if document.document_id == selected_document_id), None)
        active_document_row = next((document for document in document_rows if document["document_id"] == selected_document_id), None)
        for document in document_rows:
            document["selected"] = document["document_id"] == selected_document_id

        document_version_hash = _as_text((active_document_row or {}).get("version_hash"))
        document_version_hash_short = _as_text((active_document_row or {}).get("version_hash_short"))
        rows: list[dict[str, Any]] = []
        if active_document is not None:
            rows = self._row_items(
                tenant_id=portal_instance_id,
                document=active_document,
                enabled_lens_ids=enabled_lens_ids,
                mss_index=mss_index,
            )
        if text_filter:
            rows = [row for row in rows if text_filter in _row_filter_haystack(row)]

        flat_rows = list(rows)
        flat_rows.sort(
            key=lambda row: (_row_sort_value(row, sort_key=row_sort_key), row["datum_address"]),
            reverse=row_sort_direction == "desc",
        )
        grouped_rows = list(rows)
        grouped_rows.sort(key=lambda row: datum_address_sort_key(row["datum_address"]))
        active_rows = flat_rows if group_mode == "flat" else grouped_rows

        selected_row = next((row for row in active_rows if row["datum_address"] == selected_row_id), None)
        if selected_row is None and active_rows:
            selected_row = active_rows[0]
        selected_row_id = _as_text((selected_row or {}).get("datum_address"))
        for row in rows:
            row["selected"] = row["datum_address"] == selected_row_id
        selected_row = next((row for row in rows if row["datum_address"] == selected_row_id), selected_row)

        row_groups = _group_rows(grouped_rows, group_mode=group_mode, workbench_lens=workbench_lens)
        layer_matrix = _layer_matrix(grouped_rows)
        row_sections = _section_rows_for_groups(row_groups)
        visible_row_items = flat_rows if group_mode == "flat" else []

        overlay = None
        overlay_events: list[dict[str, Any]] = []
        if overlay_visibility == "show" and document_version_hash:
            request = DirectiveContextRequest(
                portal_instance_id=portal_instance_id,
                tool_id=WORKBENCH_UI_TOOL_ID,
                subject_hyphae_hash=_as_text((selected_row or {}).get("hyphae_hash")),
                subject_version_hash=document_version_hash,
            )
            directive_result = self._directive_context.read_directive_context(request)
            if directive_result.source is not None:
                overlay = directive_result.source.to_dict()
                overlay_events = [
                    record.to_dict()
                    for record in self._directive_context.read_directive_context_events(
                        DirectiveContextEventQuery(
                            portal_instance_id=portal_instance_id,
                            tool_id=WORKBENCH_UI_TOOL_ID,
                            context_id=directive_result.source.context_id,
                            limit=5,
                        )
                    )
                ]

        document_index = next(
            (index for index, document in enumerate(document_rows) if document["document_id"] == selected_document_id),
            -1,
        )
        row_index = next(
            (index for index, row in enumerate(active_rows) if row["datum_address"] == selected_row_id),
            -1,
        )
        navigation = {
            "previous_document": _navigation_item(document_rows, index=document_index - 1, label_key="document_name", id_key="document_id"),
            "next_document": _navigation_item(document_rows, index=document_index + 1, label_key="document_name", id_key="document_id"),
            "previous_row": _navigation_item(active_rows, index=row_index - 1, label_key="datum_address", id_key="datum_address"),
            "next_row": _navigation_item(active_rows, index=row_index + 1, label_key="datum_address", id_key="datum_address"),
        }

        selected_document_summary = {
            "document_id": selected_document_id,
            "document_name": _as_text((active_document_row or {}).get("document_name")),
            "source_kind": _as_text((active_document_row or {}).get("source_kind")),
            # Datum-KIND dispatch signal (additive): lets the editor auto-select a
            # standardized displayer body instead of always showing the raw grid.
            "datum_kind": _classify_datum_kind(
                _as_text((active_document_row or {}).get("document_name")),
                _as_text((active_document_row or {}).get("source_kind")),
                _as_text((active_document_row or {}).get("canonical_name")),
            ),
            "version_hash": document_version_hash,
            "version_hash_short": document_version_hash_short,
            "row_count": int((active_document_row or {}).get("row_count") or 0),
        }
        selected_row_summary = {
            "datum_address": _as_text((selected_row or {}).get("datum_address")),
            "layer": int((selected_row or {}).get("layer") or 0),
            "value_group": int((selected_row or {}).get("value_group") or 0),
            "iteration": int((selected_row or {}).get("iteration") or 0),
            "labels": _as_text((selected_row or {}).get("labels")),
            "relation": _as_text((selected_row or {}).get("relation")),
            "object_ref": _as_text((selected_row or {}).get("object_ref")),
            "recognized_family": _as_text((selected_row or {}).get("recognized_family")),
            "recognized_anchor": _as_text((selected_row or {}).get("recognized_anchor")),
            "primary_value_token": _as_text((selected_row or {}).get("primary_value_token")),
            "primary_value_kind": _as_text((selected_row or {}).get("primary_value_kind")),
            "overlay_kind": _as_text((selected_row or {}).get("overlay_kind")),
            "resolved_lens": _as_text((selected_row or {}).get("resolved_lens")),
            "resolved_lens_match": _as_text((selected_row or {}).get("resolved_lens_match")),
            "display_value": _as_text((selected_row or {}).get("display_value")),
            "display_summary": _as_text((selected_row or {}).get("display_summary")),
            "diagnostic_states": list((selected_row or {}).get("diagnostic_states") or []),
            "hyphae_hash": _as_text((selected_row or {}).get("hyphae_hash")),
            "hyphae_hash_short": _as_text((selected_row or {}).get("hyphae_hash_short")),
            "semantic_hash": _as_text((selected_row or {}).get("semantic_hash")),
            "semantic_hash_short": _as_text((selected_row or {}).get("semantic_hash_short")),
            "hyphae_policy": _as_text((selected_row or {}).get("hyphae_policy")),
            "hyphae_chain_addresses": list((selected_row or {}).get("hyphae_chain_addresses") or []),
            "hyphae_chain_length": int((selected_row or {}).get("hyphae_chain_length") or 0),
            "local_references": list((selected_row or {}).get("local_references") or []),
            "local_reference_count": int((selected_row or {}).get("local_reference_count") or 0),
            "raw": (selected_row or {}).get("raw"),
            "raw_json": _as_text((selected_row or {}).get("raw_json")),
        }

        query_summary_rows = [
            {"label": "document filter", "value": document_filter or "—"},
            {"label": "document sort", "value": document_sort_key},
            {"label": "document direction", "value": document_sort_direction},
            {"label": "row filter", "value": text_filter or "—"},
            {"label": "row sort", "value": row_sort_key},
            {"label": "row direction", "value": row_sort_direction},
            {"label": "group", "value": group_mode},
            {"label": "workbench lens", "value": workbench_lens},
            {"label": "source visibility", "value": source_visibility},
            {"label": "overlay visibility", "value": overlay_visibility},
        ]

        notes = [
            "Directive overlays are additive summaries only.",
            "Document filtering indexes version_hash and document identity fields.",
            "Row filtering indexes hyphae_hash, semantic identity, resolved lens, and row semantic fields.",
            "Hyphae identity comes from SQL semantic persistence; family and lens resolution remain presentation-only.",
            "Grouped datum views preserve canonical structural ordering within each section.",
            "Mutation slots (new-document / new-datum forms) are emitted by the workbench runtime when the resolved sandbox is writable; this read service itself stays read-only.",
        ]

        selection_summary_sections = [
            {
                "title": "Selection",
                "rows": [
                    {"label": "document name", "value": selected_document_summary["document_name"] or "—"},
                    {"label": "document id", "value": selected_document_summary["document_id"] or "—"},
                    {"label": "document version hash", "value": selected_document_summary["version_hash"] or "—"},
                    {"label": "datum address", "value": selected_row_summary["datum_address"] or "—"},
                    {"label": "semantic hash", "value": selected_row_summary["semantic_hash"] or "—"},
                    {"label": "hyphae hash", "value": selected_row_summary["hyphae_hash"] or "—"},
                    {"label": "raw", "value": selected_row_summary["raw_json"] or "—"},
                ],
            }
        ]
        selection_summary_sections.append(
            {
                "title": "Lens Resolution",
                "rows": [
                    {"label": "display value", "value": selected_row_summary["display_value"] or "—"},
                    {"label": "display summary", "value": selected_row_summary["display_summary"] or "—"},
                    {"label": "recognized family", "value": selected_row_summary["recognized_family"] or "—"},
                    {"label": "recognized anchor", "value": selected_row_summary["recognized_anchor"] or "—"},
                    {"label": "primary value kind", "value": selected_row_summary["primary_value_kind"] or "—"},
                    {"label": "resolved lens", "value": selected_row_summary["resolved_lens"] or "—"},
                ],
            }
        )
        selection_summary_sections.append(
            {
                "title": "Hyphae Identity",
                "rows": [
                    {"label": "policy", "value": selected_row_summary["hyphae_policy"] or "—"},
                    {"label": "chain length", "value": str(selected_row_summary["hyphae_chain_length"])},
                    {"label": "local references", "value": _joined_tokens(selected_row_summary["local_references"]) or "—"},
                    {"label": "chain addresses", "value": _joined_tokens(selected_row_summary["hyphae_chain_addresses"]) or "—"},
                ],
            }
        )
        if source_visibility == "show":
            selection_summary_sections.append(
                {
                    "title": "Source Metadata",
                    "rows": [
                        {"label": "source kind", "value": selected_document_summary["source_kind"] or "—"},
                        {"label": "row count", "value": str(selected_document_summary["row_count"])},
                    ],
                }
            )
        selection_summary_sections.append(
            {
                "title": "Directive Overlay",
                "rows": _overlay_summary_rows(overlay, event_rows=overlay_events),
            }
        )

        document_section = {
            "title": "Document Table",
            "summary": "Read-only authoritative documents keyed by SQL version identity.",
            "sticky_header": True,
            "columns": _document_table_columns(source_visibility=source_visibility),
            "items": document_rows,
        }
        datum_section: dict[str, Any] = {
            "title": "Datum Grid",
            "summary": "Spreadsheet-like read-only rows keyed by row semantic identity.",
            "sticky_header": True,
            "columns": _datum_grid_columns(workbench_lens=workbench_lens),
            "items": visible_row_items,
        }
        if group_mode != "flat":
            datum_section["subsections"] = row_sections

        return {
            "tool_id": WORKBENCH_UI_TOOL_ID,
            "document_id": selected_document_id,
            "document_name": selected_document_summary["document_name"],
            "document_rows": document_rows,
            "document_filter": document_filter,
            "document_sort_key": document_sort_key,
            "document_sort_direction": document_sort_direction,
            "document_version_hash": document_version_hash,
            "document_version_hash_short": document_version_hash_short,
            "row_count": len(active_rows),
            "sort_key": row_sort_key,
            "sort_direction": row_sort_direction,
            "text_filter": text_filter,
            "group_mode": group_mode,
            "workbench_lens": workbench_lens,
            "source_visibility": source_visibility,
            "overlay_visibility": overlay_visibility,
            "rows": active_rows,
            "row_groups": row_groups,
            "selected_row": selected_row_summary,
            "selected_row_hyphae_hash_short": selected_row_summary["hyphae_hash_short"],
            "overlay": overlay,
            "overlay_events": overlay_events,
            "warnings": list(catalog.warnings),
            "navigation": navigation,
            "surface_payload": {
                "kind": "sql_authority_lens",
                "tool_id": WORKBENCH_UI_TOOL_ID,
                "title": "Workbench UI",
                "subtitle": "Read-only two-pane SQL-backed spreadsheet with additive directive overlays.",
                "cards": [
                    {"label": "documents", "value": str(len(document_rows))},
                    {"label": "document", "value": selected_document_id or "—"},
                    {"label": "version", "value": document_version_hash_short or "—", "meta": document_version_hash or "—"},
                    {"label": "rows", "value": str(len(active_rows))},
                    {"label": "overlay", "value": overlay_visibility},
                ],
                "sections": [
                    document_section,
                    datum_section,
                    {
                        "title": "Query Controls",
                        "rows": query_summary_rows,
                    },
                ],
                "workspace": {
                    "query": {
                        "document": selected_document_id,
                        "document_filter": document_filter,
                        "document_sort": document_sort_key,
                        "document_dir": document_sort_direction,
                        "filter": text_filter,
                        "sort": row_sort_key,
                        "dir": row_sort_direction,
                        "group": group_mode,
                        "workbench_lens": workbench_lens,
                        "source": source_visibility,
                        "overlay": overlay_visibility,
                        "row": selected_row_summary["datum_address"],
                    },
                    "document_table": {
                        "sticky_header": True,
                        "columns": _document_table_columns(source_visibility=source_visibility),
                        "rows": document_rows,
                        "selected_document_id": selected_document_id,
                        "selected_marker": "selected",
                    },
                    "datum_grid": {
                        "sticky_header": True,
                        "columns": _datum_grid_columns(workbench_lens=workbench_lens),
                        "rows": visible_row_items,
                        "groups": row_groups,
                        "layers": layer_matrix,
                        "group_mode": group_mode,
                        "lens": workbench_lens,
                        "selected_row_id": selected_row_summary["datum_address"],
                        "selected_marker": "selected",
                    },
                    "selected_document": selected_document_summary,
                    "selected_row": selected_row_summary,
                    "navigation": navigation,
                    "source_visibility": source_visibility,
                    "overlay_visibility": overlay_visibility,
                },
                "notes": notes,
            },
            "selection_summary_sections": selection_summary_sections,
        }
