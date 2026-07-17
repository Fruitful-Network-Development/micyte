from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from micyte.core.datum_documents import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)


def dumps_json(value: Any) -> str:
    # Canonical JSON serialization (sorted keys, no whitespace). Inlined from
    # adapters.sql._sqlite so this core engine carries no adapter dependency.
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"
HYPHAE_CHAIN_POLICY = "mos.hyphae_chain_v1"
EDIT_REMAP_POLICY = "mos.edit_remap_v1"

_DATUM_ADDRESS_RE = re.compile(r"^[0-9]+-[0-9]+-[0-9]+$")
_RF_TOKEN_RE = re.compile(r"^rf\.([0-9]+-[0-9]+-[0-9]+)$", re.IGNORECASE)
_NUMERIC_HYPHEN_RE = re.compile(r"^[0-9]+(?:-[0-9]+)+$")


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_numeric_hyphen_token(value: object) -> bool:
    return bool(_NUMERIC_HYPHEN_RE.fullmatch(_as_text(value)))


def is_datum_address(value: object) -> bool:
    return bool(_DATUM_ADDRESS_RE.fullmatch(_as_text(value)))


def parse_datum_address(value: object) -> tuple[int, int, int]:
    token = _as_text(value)
    if not is_datum_address(token):
        raise ValueError("datum address must be <layer>-<value_group>-<iteration>")
    layer, value_group, iteration = token.split("-", 2)
    return int(layer, 10), int(value_group, 10), int(iteration, 10)


def format_datum_address(layer: int, value_group: int, iteration: int) -> str:
    return f"{int(layer)}-{int(value_group)}-{int(iteration)}"


def datum_address_sort_key(value: object) -> tuple[int, int, int]:
    return parse_datum_address(value)


def _sha256_token(*, prefix: str, payload: Any) -> str:
    digest = hashlib.sha256(f"{prefix}:{dumps_json(payload)}".encode()).hexdigest()
    return f"sha256:{digest}"


def _copy_row_with_address(row: AuthoritativeDatumDocumentRow, *, datum_address: str, raw: Any) -> AuthoritativeDatumDocumentRow:
    return AuthoritativeDatumDocumentRow(datum_address=datum_address, raw=raw)


def _copy_document(
    document: AuthoritativeDatumDocument,
    *,
    rows: tuple[AuthoritativeDatumDocumentRow, ...],
    warnings: tuple[str, ...] | None = None,
) -> AuthoritativeDatumDocument:
    return AuthoritativeDatumDocument(
        document_id=document.document_id,
        source_kind=document.source_kind,
        document_name=document.document_name,
        relative_path=document.relative_path,
        canonical_name=document.canonical_name,
        tool_id=document.tool_id,
        source_authority=document.source_authority,
        document_metadata=document.document_metadata,
        is_anchor=document.is_anchor,
        anchor_document_name=document.anchor_document_name,
        anchor_document_path=document.anchor_document_path,
        anchor_document_metadata=document.anchor_document_metadata,
        anchor_rows=document.anchor_rows,
        rows=rows,
        warnings=tuple(document.warnings) if warnings is None else tuple(warnings),
    )


def _row_tokens(raw: Any, *, datum_address: str) -> tuple[str, ...]:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return tuple(_as_text(item) for item in raw[0] if _as_text(item))
    if isinstance(raw, dict):
        values = (
            raw.get("datum_address"),
            raw.get("subject_ref") or raw.get("subject") or datum_address,
            raw.get("relation") or raw.get("predicate"),
            raw.get("object_ref") or raw.get("object"),
        )
        return tuple(_as_text(item) for item in values if _as_text(item))
    return ()


def _row_local_refs(
    row: AuthoritativeDatumDocumentRow,
    *,
    known_addresses: set[str],
) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    tokens = _row_tokens(row.raw, datum_address=row.datum_address)
    for index, token in enumerate(tokens):
        if not token:
            continue
        if index == 0 and token == row.datum_address:
            continue
        if _RF_TOKEN_RE.fullmatch(token):
            continue
        if is_datum_address(token) and token in known_addresses and token != row.datum_address and token not in seen:
            seen.add(token)
            out.append(token)
            continue
        if "." in token:
            prefix, suffix = token.split(".", 1)
            if _is_numeric_hyphen_token(prefix) and is_datum_address(suffix) and suffix in known_addresses:
                if suffix != row.datum_address and suffix not in seen:
                    seen.add(suffix)
                    out.append(suffix)
    return tuple(out)


def _canonical_storage_row(row: AuthoritativeDatumDocumentRow) -> dict[str, Any]:
    return {
        "datum_address": row.datum_address,
        "raw": row.raw,
    }


def build_document_version_identity(document: AuthoritativeDatumDocument) -> dict[str, Any]:
    payload = {
        "policy": MSS_VERSION_HASH_POLICY,
        "source_kind": document.source_kind,
        "document_metadata": document.document_metadata or {},
        "rows": [_canonical_storage_row(row) for row in sorted(document.rows, key=lambda item: datum_address_sort_key(item.datum_address))],
    }
    return {
        "policy": MSS_VERSION_HASH_POLICY,
        "version_hash": _sha256_token(prefix=MSS_VERSION_HASH_POLICY, payload=payload),
        "canonical_payload": payload,
    }


def _anchor_context_payload(document: AuthoritativeDatumDocument) -> dict[str, Any]:
    return {
        "anchor_document_metadata": document.anchor_document_metadata or {},
        "anchor_rows": [
            _canonical_storage_row(row)
            for row in sorted(document.anchor_rows, key=lambda item: datum_address_sort_key(item.datum_address))
        ],
    }


def _remap_semantic_raw(
    raw: Any,
    *,
    current_address: str,
    semantic_refs: dict[str, str],
) -> Any:
    if isinstance(raw, list):
        out: list[Any] = []
        for index, item in enumerate(raw):
            if index == 0 and isinstance(item, list):
                tokens: list[Any] = []
                for token_index, token in enumerate(item):
                    value = _as_text(token)
                    if token_index == 0 and value == current_address:
                        tokens.append("__self__")
                        continue
                    if is_datum_address(value) and value in semantic_refs:
                        tokens.append({"local_ref": semantic_refs[value]})
                        continue
                    if "." in value:
                        prefix, suffix = value.split(".", 1)
                        if _is_numeric_hyphen_token(prefix) and is_datum_address(suffix) and suffix in semantic_refs:
                            tokens.append({"qualified_local_ref": {"msn_id": prefix, "semantic_hash": semantic_refs[suffix]}})
                            continue
                    tokens.append(token)
                out.append(tokens)
                continue
            out.append(item)
        return out
    if isinstance(raw, dict):
        out = dict(raw)
        for key in ("datum_address", "subject_ref", "subject", "object_ref", "object"):
            value = _as_text(out.get(key))
            if not value:
                continue
            if value == current_address and key in {"datum_address", "subject_ref", "subject"}:
                out[key] = "__self__"
                continue
            if is_datum_address(value) and value in semantic_refs:
                out[key] = {"local_ref": semantic_refs[value]}
                continue
            if "." in value:
                prefix, suffix = value.split(".", 1)
                if _is_numeric_hyphen_token(prefix) and is_datum_address(suffix) and suffix in semantic_refs:
                    out[key] = {"qualified_local_ref": {"msn_id": prefix, "semantic_hash": semantic_refs[suffix]}}
        return out
    return raw


def _dependency_closure(start: str, dependency_map: dict[str, Any]) -> list[str]:
    """The minimum-but-complete dependency path of ``start`` (focus-excluded):
    a DFS over local-reference edges, dependencies emitted before dependents,
    with NO rudi-range fill. ``start`` is the last element.
    """
    out: list[str] = []
    seen: set[str] = set()

    def visit(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        for dependency in sorted(dependency_map.get(current, ()), key=datum_address_sort_key):
            visit(dependency)
        out.append(current)

    visit(start)
    return out


def _semantic_context(document: AuthoritativeDatumDocument) -> dict[str, Any]:
    """Shared semantic substrate consumed by ``build_document_semantics``,
    ``build_minimum_complete_path``, and ``compile_hyphae_value``.

    Returns the address map, the local-reference dependency map, the
    anchor-context hash, the per-row **content-canonical** semantic hashes
    (address-independent — each local ref folds to its dependency's semantic
    hash and the row's own address to ``__self__``), and the detected cycle set.
    """
    address_map = {
        row.datum_address: row
        for row in sorted(document.rows, key=lambda item: datum_address_sort_key(item.datum_address))
    }
    known_addresses = set(address_map.keys())
    dependency_map = {
        address: _row_local_refs(row, known_addresses=known_addresses)
        for address, row in address_map.items()
    }
    anchor_context_payload = _anchor_context_payload(document)
    anchor_context_hash = _sha256_token(prefix=f"{HYPHAE_CHAIN_POLICY}:anchor", payload=anchor_context_payload)

    semantic_hashes: dict[str, str] = {}
    visiting: set[str] = set()
    cycle_rows: set[str] = set()

    def semantic_hash_for(address: str) -> str:
        cached = semantic_hashes.get(address)
        if cached:
            return cached
        if address in visiting:
            cycle_rows.add(address)
            fallback_payload = {
                "policy": HYPHAE_CHAIN_POLICY,
                "anchor_context_hash": anchor_context_hash,
                "row": {
                    "datum_address": "__cycle__",
                    "raw": address_map[address].raw,
                },
            }
            fallback = _sha256_token(prefix=f"{HYPHAE_CHAIN_POLICY}:row_cycle", payload=fallback_payload)
            semantic_hashes[address] = fallback
            return fallback
        visiting.add(address)
        refs = {ref: semantic_hash_for(ref) for ref in dependency_map.get(address, ())}
        normalized_raw = _remap_semantic_raw(
            address_map[address].raw,
            current_address=address,
            semantic_refs=refs,
        )
        payload = {
            "policy": HYPHAE_CHAIN_POLICY,
            "anchor_context_hash": anchor_context_hash,
            "raw": normalized_raw,
        }
        hashed = _sha256_token(prefix=f"{HYPHAE_CHAIN_POLICY}:row", payload=payload)
        semantic_hashes[address] = hashed
        visiting.remove(address)
        return hashed

    for address in address_map:
        semantic_hash_for(address)

    return {
        "address_map": address_map,
        "dependency_map": dependency_map,
        "anchor_context_hash": anchor_context_hash,
        "semantic_hashes": semantic_hashes,
        "cycle_rows": cycle_rows,
    }


def build_minimum_complete_path(
    document: AuthoritativeDatumDocument, datum_address: str
) -> list[str]:
    """The minimum-but-complete abstraction path for ``datum_address``: the
    focus-excluded local-reference closure (dependencies first, target last),
    with NO inclusive rudi-range fill. Raises ``ValueError`` if absent.
    """
    context = _semantic_context(document)
    if datum_address not in context["address_map"]:
        raise ValueError(f"datum_address not found in document: {datum_address!r}")
    return _dependency_closure(datum_address, context["dependency_map"])


def compile_hyphae_value(
    document: AuthoritativeDatumDocument, datum_address: str
) -> str:
    """Compile the **canonical hyphae value** of ``datum_address`` — a single
    ``sha256:`` token over the datum's focus closure.

    Per the MOS spec (``docs/personal_notes/MOS/mycelial_ontological_schema.md``
    + ``docs/contracts/mss_binary_sequence/``), the canonical hyphae value MUST
    carry the **ordinal rudi context** — *"include all preceding rudi datums even
    if not used directly; if the abstraction uses ``0-0-5``, include ``0-0-1``
    through ``0-0-5``"*. The rudis are the ordinal/incremental/nominal frames, so
    a value is only canonical if it is anchored to the universal rudi starting
    position. (An earlier version of this function folded the reference closure
    *without* the rudi scaffold — that was wrong and is corrected here by
    delegating to the rudi-inclusive per-row computation.)

    Today this is the JSON+SHA fold ``build_document_semantics`` produces; the
    forthcoming binary-MSS codec will replace the *representation* (a hash of the
    MSS sequence of the focus closure) while keeping the rudi-inclusion rule.
    """
    rows = build_document_semantics(document)["rows"]
    if datum_address not in rows:
        raise ValueError(f"datum_address not found in document: {datum_address!r}")
    return str(rows[datum_address]["hyphae_hash"])


def build_document_semantics(document: AuthoritativeDatumDocument) -> dict[str, Any]:
    context = _semantic_context(document)
    address_map = context["address_map"]
    dependency_map = context["dependency_map"]
    anchor_context_hash = context["anchor_context_hash"]
    semantic_hashes = context["semantic_hashes"]
    cycle_rows = context["cycle_rows"]

    rudi_rows = {
        address: row
        for address, row in address_map.items()
        if parse_datum_address(address)[:2] == (0, 0)
    }
    row_results: dict[str, dict[str, Any]] = {}
    for address in address_map:
        closure = _dependency_closure(address, dependency_map)
        reachable_rudi_iterations = [
            parse_datum_address(item)[2]
            for item in closure
            if parse_datum_address(item)[:2] == (0, 0)
        ]
        rudi_prefix: list[str] = []
        if reachable_rudi_iterations:
            max_rudi = max(reachable_rudi_iterations)
            for iteration in range(1, max_rudi + 1):
                rudi_address = format_datum_address(0, 0, iteration)
                if rudi_address in rudi_rows:
                    rudi_prefix.append(rudi_address)
        chain_order: list[str] = []
        for item in rudi_prefix + closure:
            if item not in chain_order:
                chain_order.append(item)
        chain = [
            {
                "datum_address": item,
                "semantic_hash": semantic_hashes[item],
                "local_dependencies": [semantic_hashes[dependency] for dependency in dependency_map.get(item, ())],
            }
            for item in chain_order
        ]
        hyphae_payload = {
            "policy": HYPHAE_CHAIN_POLICY,
            "anchor_context_hash": anchor_context_hash,
            "target_semantic_hash": semantic_hashes[address],
            "chain_semantic_hashes": [semantic_hashes[item] for item in chain_order],
        }
        row_results[address] = {
            "policy": HYPHAE_CHAIN_POLICY,
            "datum_address": address,
            "semantic_hash": semantic_hashes[address],
            "hyphae_hash": _sha256_token(prefix=f"{HYPHAE_CHAIN_POLICY}:chain", payload=hyphae_payload),
            "hyphae_chain": {
                "policy": HYPHAE_CHAIN_POLICY,
                "target_datum_address": address,
                "anchor_context_hash": anchor_context_hash,
                "addresses": chain_order,
                "chain": chain,
            },
            "local_references": list(dependency_map.get(address, ())),
            "warnings": ["semantic_cycle_detected"] if address in cycle_rows else [],
        }
    return {
        "document": build_document_version_identity(document),
        "anchor_context_hash": anchor_context_hash,
        "rows": row_results,
    }


def _normalize_mutation_token(
    token: Any,
    *,
    address_map: dict[str, str],
) -> Any:
    value = _as_text(token)
    if not value:
        return token
    if _RF_TOKEN_RE.fullmatch(value):
        return token
    if is_datum_address(value) and value in address_map:
        return address_map[value]
    if "." in value:
        prefix, suffix = value.split(".", 1)
        if _is_numeric_hyphen_token(prefix) and is_datum_address(suffix) and suffix in address_map:
            return f"{prefix}.{address_map[suffix]}"
    if _is_numeric_hyphen_token(value):
        parts = value.split("-")
        if len(parts) > 3:
            suffix = "-".join(parts[-3:])
            prefix = "-".join(parts[:-3])
            if prefix and suffix in address_map:
                return f"{prefix}-{address_map[suffix]}"
    return token


def _remap_row_raw(
    row: AuthoritativeDatumDocumentRow,
    *,
    next_address: str,
    address_map: dict[str, str],
) -> Any:
    raw = row.raw
    if isinstance(raw, list):
        out: list[Any] = []
        for index, item in enumerate(raw):
            if index == 0 and isinstance(item, list):
                tokens: list[Any] = []
                for token_index, token in enumerate(item):
                    if token_index == 0:
                        tokens.append(next_address)
                        continue
                    tokens.append(_normalize_mutation_token(token, address_map=address_map))
                out.append(tokens)
                continue
            out.append(item)
        return out
    if isinstance(raw, dict):
        out = dict(raw)
        if _as_text(out.get("datum_address")):
            out["datum_address"] = next_address
        for key in ("subject_ref", "subject", "object_ref", "object"):
            if key in out:
                out[key] = _normalize_mutation_token(out.get(key), address_map=address_map)
        return out
    return raw


def _family_stats(rows: tuple[AuthoritativeDatumDocumentRow, ...]) -> dict[tuple[int, int], tuple[int, int, bool]]:
    stats: dict[tuple[int, int], tuple[int, int, bool]] = {}
    grouped: dict[tuple[int, int], list[int]] = {}
    for row in rows:
        layer, value_group, iteration = parse_datum_address(row.datum_address)
        grouped.setdefault((layer, value_group), []).append(iteration)
    for family, iterations in grouped.items():
        ordered = sorted(iterations)
        lower = ordered[0]
        upper = ordered[-1]
        expected = lower
        canonical = True
        for value in ordered:
            if value != expected:
                canonical = False
                break
            expected += 1
        stats[family] = (lower, upper, canonical)
    return stats


def _family_bounds(rows: tuple[AuthoritativeDatumDocumentRow, ...]) -> dict[tuple[int, int], tuple[int, int]]:
    bounds: dict[tuple[int, int], tuple[int, int]] = {}
    for family, (lower, upper, canonical) in _family_stats(rows).items():
        if not canonical:
            raise ValueError("document_rows_not_canonical")
        bounds[family] = (lower, upper)
    return bounds


def _document_row_map(document: AuthoritativeDatumDocument) -> dict[str, AuthoritativeDatumDocumentRow]:
    return {
        row.datum_address: row
        for row in sorted(document.rows, key=lambda item: datum_address_sort_key(item.datum_address))
    }


def _validate_insert_target(
    rows: tuple[AuthoritativeDatumDocumentRow, ...],
    *,
    target_address: str,
) -> None:
    family = parse_datum_address(target_address)[:2]
    target_iteration = parse_datum_address(target_address)[2]
    current = _family_stats(rows).get(family)
    if current is None:
        if target_iteration != 1:
            raise ValueError("empty_family_insert_must_start_at_iteration_1")
        return
    lower, upper, canonical = current
    if target_iteration < lower or target_iteration > upper + 1:
        raise ValueError("insert_target_iteration_out_of_range")
    if not canonical and target_iteration <= upper:
        raise ValueError("document_rows_not_canonical")


def _validate_move_target(
    rows_without_source: tuple[AuthoritativeDatumDocumentRow, ...],
    *,
    destination_address: str,
) -> None:
    family = parse_datum_address(destination_address)[:2]
    destination_iteration = parse_datum_address(destination_address)[2]
    bounds = _family_bounds(rows_without_source)
    current = bounds.get(family)
    if current is None:
        if destination_iteration != 1:
            raise ValueError("empty_family_insert_must_start_at_iteration_1")
        return
    lower, upper = current
    if destination_iteration < lower or destination_iteration > upper + 1:
        raise ValueError("move_destination_iteration_out_of_range")


def preview_document_insert(
    document: AuthoritativeDatumDocument,
    *,
    target_address: str,
    raw: Any,
) -> dict[str, Any]:
    target_address = _as_text(target_address)
    _validate_insert_target(document.rows, target_address=target_address)
    row_map = _document_row_map(document)
    target_layer, target_value_group, target_iteration = parse_datum_address(target_address)
    address_map: dict[str, str] = {}
    updated_rows: list[AuthoritativeDatumDocumentRow] = []
    for row in row_map.values():
        layer, value_group, iteration = parse_datum_address(row.datum_address)
        next_address = row.datum_address
        if (layer, value_group) == (target_layer, target_value_group) and iteration >= target_iteration:
            next_address = format_datum_address(layer, value_group, iteration + 1)
        address_map[row.datum_address] = next_address
    for row in row_map.values():
        next_address = address_map[row.datum_address]
        updated_rows.append(
            _copy_row_with_address(
                row,
                datum_address=next_address,
                raw=_remap_row_raw(row, next_address=next_address, address_map=address_map),
            )
        )
    inserted_row = AuthoritativeDatumDocumentRow(datum_address=target_address, raw=raw)
    updated_rows.append(
        _copy_row_with_address(
            inserted_row,
            datum_address=target_address,
            raw=_remap_row_raw(inserted_row, next_address=target_address, address_map=address_map),
        )
    )
    updated_document = _copy_document(
        document,
        rows=tuple(sorted(updated_rows, key=lambda item: datum_address_sort_key(item.datum_address))),
    )
    before_identity = build_document_version_identity(document)
    after_identity = build_document_version_identity(updated_document)
    return {
        "policy": EDIT_REMAP_POLICY,
        "action": "insert",
        "target_address": target_address,
        "address_map": address_map,
        "updated_document": updated_document,
        "version_hash_before": before_identity["version_hash"],
        "version_hash_after": after_identity["version_hash"],
    }


def preview_document_delete(
    document: AuthoritativeDatumDocument,
    *,
    target_address: str,
) -> dict[str, Any]:
    target_address = _as_text(target_address)
    row_map = _document_row_map(document)
    if target_address not in row_map:
        raise ValueError("delete_target_row_missing")
    _family_bounds(document.rows)
    dependency_map = {
        address: _row_local_refs(row, known_addresses=set(row_map.keys()))
        for address, row in row_map.items()
    }
    referencing_rows = [
        address
        for address, refs in dependency_map.items()
        if target_address in refs and address != target_address
    ]
    if referencing_rows:
        raise ValueError("delete_target_row_still_referenced")
    target_layer, target_value_group, target_iteration = parse_datum_address(target_address)
    address_map: dict[str, str] = {}
    for row in row_map.values():
        if row.datum_address == target_address:
            continue
        layer, value_group, iteration = parse_datum_address(row.datum_address)
        next_address = row.datum_address
        if (layer, value_group) == (target_layer, target_value_group) and iteration > target_iteration:
            next_address = format_datum_address(layer, value_group, iteration - 1)
        address_map[row.datum_address] = next_address
    updated_rows: list[AuthoritativeDatumDocumentRow] = []
    for row in row_map.values():
        if row.datum_address == target_address:
            continue
        next_address = address_map[row.datum_address]
        updated_rows.append(
            _copy_row_with_address(
                row,
                datum_address=next_address,
                raw=_remap_row_raw(row, next_address=next_address, address_map=address_map),
            )
        )
    updated_document = _copy_document(
        document,
        rows=tuple(sorted(updated_rows, key=lambda item: datum_address_sort_key(item.datum_address))),
    )
    before_identity = build_document_version_identity(document)
    after_identity = build_document_version_identity(updated_document)
    return {
        "policy": EDIT_REMAP_POLICY,
        "action": "delete",
        "target_address": target_address,
        "address_map": address_map,
        "removed_address": target_address,
        "updated_document": updated_document,
        "version_hash_before": before_identity["version_hash"],
        "version_hash_after": after_identity["version_hash"],
    }


def preview_document_move(
    document: AuthoritativeDatumDocument,
    *,
    source_address: str,
    destination_address: str,
) -> dict[str, Any]:
    source_address = _as_text(source_address)
    destination_address = _as_text(destination_address)
    if source_address == destination_address:
        raise ValueError("move_source_and_destination_must_differ")
    row_map = _document_row_map(document)
    if source_address not in row_map:
        raise ValueError("move_source_row_missing")
    _family_bounds(document.rows)
    moving_row = row_map[source_address]
    remaining_rows = tuple(row for row in row_map.values() if row.datum_address != source_address)
    _validate_move_target(remaining_rows, destination_address=destination_address)

    source_layer, source_value_group, source_iteration = parse_datum_address(source_address)
    removal_map: dict[str, str] = {}
    temp_rows: list[AuthoritativeDatumDocumentRow] = []
    for row in remaining_rows:
        layer, value_group, iteration = parse_datum_address(row.datum_address)
        next_address = row.datum_address
        if (layer, value_group) == (source_layer, source_value_group) and iteration > source_iteration:
            next_address = format_datum_address(layer, value_group, iteration - 1)
        removal_map[row.datum_address] = next_address
        temp_rows.append(_copy_row_with_address(row, datum_address=next_address, raw=row.raw))

    destination_layer, destination_value_group, destination_iteration = parse_datum_address(destination_address)
    insertion_map: dict[str, str] = {}
    final_map: dict[str, str] = {source_address: destination_address}
    updated_rows: list[AuthoritativeDatumDocumentRow] = []
    for row in temp_rows:
        layer, value_group, iteration = parse_datum_address(row.datum_address)
        next_address = row.datum_address
        if (layer, value_group) == (destination_layer, destination_value_group) and iteration >= destination_iteration:
            next_address = format_datum_address(layer, value_group, iteration + 1)
        insertion_map[row.datum_address] = next_address
    for original_address, temp_address in removal_map.items():
        final_map[original_address] = insertion_map.get(temp_address, temp_address)

    for original_address, row in row_map.items():
        if original_address == source_address:
            continue
        next_address = final_map[original_address]
        updated_rows.append(
            _copy_row_with_address(
                row,
                datum_address=next_address,
                raw=_remap_row_raw(row, next_address=next_address, address_map=final_map),
            )
        )

    updated_rows.append(
        _copy_row_with_address(
            moving_row,
            datum_address=destination_address,
            raw=_remap_row_raw(moving_row, next_address=destination_address, address_map=final_map),
        )
    )
    updated_document = _copy_document(
        document,
        rows=tuple(sorted(updated_rows, key=lambda item: datum_address_sort_key(item.datum_address))),
    )
    before_identity = build_document_version_identity(document)
    after_identity = build_document_version_identity(updated_document)
    return {
        "policy": EDIT_REMAP_POLICY,
        "action": "move",
        "source_address": source_address,
        "destination_address": destination_address,
        "address_map": final_map,
        "updated_document": updated_document,
        "version_hash_before": before_identity["version_hash"],
        "version_hash_after": after_identity["version_hash"],
    }
