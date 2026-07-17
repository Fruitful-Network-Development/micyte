from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .codec import decode_structure, encode_canonical_structure_from_addresses
from .structure import (
    SamrasStructure,
    address_depth,
    address_sort_key,
    as_text,
    parent_address,
    parse_address_segments,
)
from .validation import InvalidSamrasStructure


def _split_row_source(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("datum_addressing_abstraction_space"), dict):
        return dict(payload.get("datum_addressing_abstraction_space") or {})
    return dict(payload)


def _looks_like_binary(token: str) -> bool:
    return bool(token) and all(ch in {"0", "1"} for ch in token)


def _looks_like_address(token: str) -> bool:
    raw = as_text(token)
    if not raw:
        return False
    if "-" not in raw:
        return raw.isdigit() and raw != "0" and len(raw) <= 6
    parts = raw.split("-")
    return bool(parts) and all(part.isdigit() and part != "0" for part in parts)


def _raw_base(raw_value: object) -> list[str]:
    row_values = raw_value if isinstance(raw_value, list) else []
    base = row_values[0] if len(row_values) > 0 and isinstance(row_values[0], list) else []
    return [str(item).strip() for item in base]


def _raw_labels(raw_value: object) -> list[str]:
    row_values = raw_value if isinstance(raw_value, list) else []
    labels = row_values[1] if len(row_values) > 1 and isinstance(row_values[1], list) else []
    return [str(item).strip() for item in labels if str(item).strip()]


def _decode_ascii_title_babelette(value: object) -> str:
    token = as_text(value)
    if not token:
        return ""
    if any(ch not in {"0", "1"} for ch in token) or (len(token) % 8) != 0:
        return ""
    data = bytearray(int(token[index : index + 8], 2) for index in range(0, len(token), 8))
    while data and data[-1] == 0:
        data.pop()
    if not data:
        return ""
    try:
        decoded = bytes(data).decode("ascii")
    except UnicodeDecodeError:
        return ""
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in decoded):
        return ""
    return decoded.strip()


@dataclass(frozen=True)
class SamrasStructureAuthority:
    source_kind: str
    source_path: str
    datum_address: str
    label: str
    magnitude: str
    score: int
    structure: SamrasStructure | None = None
    error: str = ""

    @property
    def decodable(self) -> bool:
        return self.structure is not None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_kind": self.source_kind,
            "source_path": self.source_path,
            "datum_address": self.datum_address,
            "label": self.label,
            "magnitude": self.magnitude,
            "score": self.score,
            "decodable": self.decodable,
            "error": self.error,
        }
        if self.structure is not None:
            payload["structure"] = self.structure.to_dict()
        return payload


@dataclass(frozen=True)
class SamrasWorkspaceNode:
    address_id: str
    title: str
    titles: tuple[str, ...]
    parent_address: str
    depth: int
    child_count: int
    child_addresses: tuple[str, ...]
    row_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "address_id": self.address_id,
            "title": self.title,
            "titles": [str(item) for item in self.titles],
            "parent_address": self.parent_address,
            "depth": int(self.depth),
            "child_count": int(self.child_count),
            "child_addresses": [str(item) for item in self.child_addresses],
            "row_ids": [str(item) for item in self.row_ids],
        }


@dataclass(frozen=True)
class SamrasWorkspaceResource:
    structure_row_id: str
    structure_label: str
    structure: SamrasStructure
    nodes: tuple[SamrasWorkspaceNode, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure_row_id": self.structure_row_id,
            "structure_label": self.structure_label,
            "structure": self.structure.to_dict(),
            "nodes": [item.to_dict() for item in self.nodes],
            "warnings": [str(item) for item in self.warnings],
        }


def find_structure_authorities(
    payload: dict[str, Any],
    *,
    source_kind: str = "",
    source_path: str = "",
    root_ref: str = "0-0-5",
) -> tuple[SamrasStructureAuthority, ...]:
    row_source = _split_row_source(payload)
    authorities: list[SamrasStructureAuthority] = []
    for row_key, raw_value in row_source.items():
        base = _raw_base(raw_value)
        labels = tuple(_raw_labels(raw_value))
        label_text = " ".join(labels).lower()
        row_id = as_text(row_key)
        if not row_id:
            continue
        score = -1
        magnitude = ""
        if len(base) >= 3 and as_text(base[1]) == root_ref and (_looks_like_binary(as_text(base[2])) or "-" in as_text(base[2])):
            magnitude = as_text(base[2])
            score = 100
        elif len(base) == 2 and (_looks_like_binary(as_text(base[1])) or "-" in as_text(base[1])):
            magnitude = as_text(base[1])
            score = 50
        if score < 0:
            continue
        if "samras" in label_text or "txa" in label_text or "msn" in label_text:
            score += 10
        if row_id.startswith("1-"):
            score += 5
        structure = None
        error = ""
        try:
            structure = decode_structure(magnitude, root_ref=root_ref)
        except InvalidSamrasStructure as exc:
            error = str(exc)
        authorities.append(
            SamrasStructureAuthority(
                source_kind=as_text(source_kind),
                source_path=as_text(source_path),
                datum_address=row_id,
                label=labels[0] if labels else "",
                magnitude=magnitude,
                score=score,
                structure=structure,
                error=error,
            )
        )
    authorities.sort(
        key=lambda item: (
            1 if item.decodable else 0,
            int(item.score),
            1 if item.datum_address.startswith("1-") else 0,
        ),
        reverse=True,
    )
    return tuple(authorities)


def select_preferred_structure_authority(
    authorities: list[SamrasStructureAuthority] | tuple[SamrasStructureAuthority, ...],
    *,
    require_decodable: bool = True,
) -> SamrasStructureAuthority:
    if not authorities:
        raise InvalidSamrasStructure("unable to locate a SAMRAS structure row in the payload")
    if not require_decodable:
        return next(iter(authorities))
    for authority in authorities:
        if authority.decodable:
            return authority
    raise InvalidSamrasStructure(next(iter(authorities)).error or "unable to decode SAMRAS structure from available authorities")


def reconstruct_addresses_from_rows(payload: dict[str, Any]) -> list[str]:
    row_source = _split_row_source(payload)
    raw_addresses: set[str] = set()
    for raw_value in row_source.values():
        base = _raw_base(raw_value)
        for index, token in enumerate(base):
            if as_text(token) != "rf.3-1-2" or index + 1 >= len(base):
                continue
            candidate = as_text(base[index + 1])
            if _looks_like_address(candidate):
                raw_addresses.add(candidate)
    expanded: set[str] = set(raw_addresses)
    changed = True
    while changed:
        changed = False
        snapshot = sorted(expanded, key=address_sort_key)
        for address in snapshot:
            parent = parent_address(address)
            while parent:
                if parent not in expanded:
                    expanded.add(parent)
                    changed = True
                parent = parent_address(parent)
        parent_to_ordinals: dict[str, set[int]] = {}
        for address in list(expanded):
            segments = parse_address_segments(address)
            parent = "-".join(str(item) for item in segments[:-1]) if len(segments) > 1 else ""
            parent_to_ordinals.setdefault(parent, set()).add(int(segments[-1]))
        for parent_id, ordinals in parent_to_ordinals.items():
            maximum = max(ordinals) if ordinals else 0
            for ordinal in range(1, maximum + 1):
                candidate = str(ordinal) if not parent_id else f"{parent_id}-{ordinal}"
                if candidate not in expanded:
                    expanded.add(candidate)
                    changed = True
    return sorted(expanded, key=address_sort_key)


def reconstruct_structure_from_rows(
    payload: dict[str, Any],
    *,
    root_ref: str = "0-0-5",
    warnings: list[str] | tuple[str, ...] = (),
) -> SamrasStructure:
    addresses = reconstruct_addresses_from_rows(payload)
    if not addresses:
        raise InvalidSamrasStructure("payload does not carry SAMRAS address rows that can reconstruct a structure")
    return encode_canonical_structure_from_addresses(
        addresses,
        root_ref=root_ref,
        warnings=warnings,
    )


def _title_rows_by_address(payload: dict[str, Any], valid_addresses: set[str]) -> tuple[dict[str, list[dict[str, Any]]], tuple[str, ...]]:
    row_source = _split_row_source(payload)
    grouped: dict[str, list[dict[str, Any]]] = {}
    blank_title_nodes: list[str] = []
    for row_key, raw_value in row_source.items():
        base = _raw_base(raw_value)
        labels = _raw_labels(raw_value)
        node_id = ""
        title_bits = ""
        for index, token in enumerate(base):
            marker = as_text(token)
            if marker == "rf.3-1-2" and index + 1 < len(base):
                node_id = as_text(base[index + 1])
            if marker == "rf.3-1-3" and index + 1 < len(base):
                title_bits = as_text(base[index + 1])
        if node_id not in valid_addresses:
            continue
        decoded_title = _decode_ascii_title_babelette(title_bits)
        if title_bits and not decoded_title:
            blank_title_nodes.append(node_id)
        grouped.setdefault(node_id, []).append(
            {
                "row_id": as_text(row_key),
                "label": decoded_title or (labels[0] if labels else ""),
            }
        )
    counter = Counter(blank_title_nodes)
    return grouped, tuple(sorted(counter.keys(), key=address_sort_key))


def _build_nodes(structure: SamrasStructure, title_rows: dict[str, list[dict[str, Any]]]) -> tuple[SamrasWorkspaceNode, ...]:
    nodes: list[SamrasWorkspaceNode] = []
    child_count_map = structure.address_map
    by_parent: dict[str, list[str]] = {}
    for address in structure.addresses:
        by_parent.setdefault(parent_address(address), []).append(address)
    for children in by_parent.values():
        children.sort(key=address_sort_key)
    for address in structure.addresses:
        rows = list(title_rows.get(address, ()))
        titles = tuple(as_text(item.get("label")) for item in rows if as_text(item.get("label")))
        row_ids = tuple(as_text(item.get("row_id")) for item in rows if as_text(item.get("row_id")))
        nodes.append(
            SamrasWorkspaceNode(
                address_id=address,
                title=titles[0] if titles else "",
                titles=titles,
                parent_address=parent_address(address),
                depth=address_depth(address),
                child_count=int(child_count_map.get(address) or 0),
                child_addresses=tuple(by_parent.get(address, ())),
                row_ids=row_ids,
            )
        )
    return tuple(nodes)


def load_workspace_from_compact_payload(
    payload: dict[str, Any],
    *,
    source_kind: str = "",
    source_path: str = "",
    root_ref: str = "0-0-5",
) -> SamrasWorkspaceResource:
    authorities = find_structure_authorities(
        payload,
        source_kind=source_kind,
        source_path=source_path,
        root_ref=root_ref,
    )
    warnings: list[str] = []
    structure_row_id = ""
    structure_label = ""
    try:
        authority = select_preferred_structure_authority(authorities, require_decodable=True)
        structure = authority.structure
        structure_row_id = authority.datum_address
        structure_label = authority.label
    except InvalidSamrasStructure:
        authority = select_preferred_structure_authority(authorities, require_decodable=False) if authorities else None
        structure = reconstruct_structure_from_rows(
            payload,
            root_ref=root_ref,
            warnings=("canonical SAMRAS structure was reconstructed from staged address rows",),
        )
        warnings.append("structure row could not be decoded; canonical SAMRAS structure was reconstructed from staged address rows")
        if authority is not None and authority.error:
            warnings.append(authority.error)
        structure_row_id = authority.datum_address if authority is not None else "reconstructed"
        structure_label = authority.label if authority is not None else "reconstructed"
    if structure is None:
        raise InvalidSamrasStructure("unable to build SAMRAS workspace structure")
    title_rows, blank_title_nodes = _title_rows_by_address(payload, set(structure.addresses))
    if blank_title_nodes:
        warnings.append(
            "some staged node rows carried undecodable ASCII title overlays and were left blank: "
            + ", ".join(blank_title_nodes[:25])
        )
    nodes = _build_nodes(structure, title_rows)
    return SamrasWorkspaceResource(
        structure_row_id=structure_row_id,
        structure_label=structure_label,
        structure=structure,
        nodes=nodes,
        warnings=tuple(list(structure.warnings) + warnings),
    )
