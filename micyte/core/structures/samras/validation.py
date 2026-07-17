from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .structure import (
    SamrasStructure,
    address_sort_key,
    as_text,
    format_address,
    parent_address,
    parse_address_segments,
)


class InvalidSamrasStructure(ValueError):
    """Raised when a SAMRAS structure or address set is invalid."""


def validate_stop_addresses(stops: list[int] | tuple[int, ...], value_stream_length: int) -> None:
    previous: int | None = None
    for stop in [int(item) for item in stops]:
        if stop < 0:
            raise InvalidSamrasStructure("negative stop address")
        if previous is not None and stop <= previous:
            raise InvalidSamrasStructure("stop addresses must be strictly increasing")
        if stop > int(value_stream_length):
            raise InvalidSamrasStructure("stop address exceeds value stream length")
        previous = stop


def derive_addresses_from_child_counts(values: list[int] | tuple[int, ...]) -> tuple[str, ...]:
    if not values:
        raise InvalidSamrasStructure("at least one value token is required")
    parsed = [int(item) for item in values]
    root_count = parsed[0]
    if root_count < 0:
        raise InvalidSamrasStructure("root count may not be negative")
    queue: deque[str] = deque()
    addresses: list[str] = []
    next_value_index = 1
    for ordinal in range(1, root_count + 1):
        address = str(ordinal)
        queue.append(address)
        addresses.append(address)
    while queue:
        parent = queue.popleft()
        if next_value_index >= len(parsed):
            raise InvalidSamrasStructure("not enough child-count values")
        child_count = int(parsed[next_value_index])
        next_value_index += 1
        if child_count < 0:
            raise InvalidSamrasStructure(f"negative child count for address {parent}")
        for child_ordinal in range(1, child_count + 1):
            child = f"{parent}-{child_ordinal}"
            queue.append(child)
            addresses.append(child)
    if next_value_index != len(parsed):
        raise InvalidSamrasStructure("unused values remain after queue is exhausted")
    return tuple(addresses)


def validate_address_set(addresses: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = [as_text(item) for item in addresses if as_text(item)]
    if len(set(normalized)) != len(normalized):
        raise InvalidSamrasStructure("addresses must be unique")
    sorted_addresses = sorted(normalized, key=address_sort_key)
    roots: list[int] = []
    parent_to_children: dict[str, list[int]] = {}
    known = set(sorted_addresses)
    for address in sorted_addresses:
        segments = parse_address_segments(address)
        if len(segments) == 1:
            roots.append(segments[0])
            continue
        parent = format_address(list(segments[:-1]))
        if parent not in known:
            raise InvalidSamrasStructure(f"missing parent for address {address}")
        parent_to_children.setdefault(parent, []).append(segments[-1])
    expected_roots = list(range(1, len(roots) + 1))
    if roots != expected_roots:
        raise InvalidSamrasStructure("roots must be contiguous from 1")
    for parent, ordinals in parent_to_children.items():
        sorted_ordinals = sorted(ordinals)
        expected = list(range(1, len(sorted_ordinals) + 1))
        if sorted_ordinals != expected:
            raise InvalidSamrasStructure(f"child ordinals must be contiguous for {parent}")
    return tuple(sorted_addresses)


def child_counts_from_addresses(addresses: list[str] | tuple[str, ...]) -> tuple[int, ...]:
    normalized = validate_address_set(addresses)
    parent_to_children: dict[str, list[str]] = {}
    roots: list[str] = []
    for address in normalized:
        parent = parent_address(address)
        if not parent:
            roots.append(address)
            continue
        parent_to_children.setdefault(parent, []).append(address)
    for parent in list(parent_to_children.keys()):
        parent_to_children[parent].sort(key=address_sort_key)
    roots.sort(key=address_sort_key)
    values: list[int] = [len(roots)]
    queue: deque[str] = deque(roots)
    while queue:
        address = queue.popleft()
        children = list(parent_to_children.get(address, ()))
        values.append(len(children))
        queue.extend(children)
    return tuple(values)


@dataclass(frozen=True)
class SamrasValidationReport:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [str(item) for item in self.errors],
            "warnings": [str(item) for item in self.warnings],
        }


def validate_structure(structure: SamrasStructure, *, require_canonical_roundtrip: bool = False) -> SamrasValidationReport:
    errors: list[str] = []
    warnings: list[str] = [str(item) for item in structure.warnings]
    if as_text(structure.root_ref) != "0-0-5":
        errors.append("root_ref must be 0-0-5")
    if int(structure.address_width_bits) <= 0:
        errors.append("address_width_bits must be positive")
    if int(structure.stop_count_width_bits) <= 0:
        errors.append("stop_count_width_bits must be positive")
    stops = [int(item) for item in structure.stop_addresses]
    if int(structure.stop_count) != len(stops):
        errors.append("stop_count must equal the number of stop addresses")
    if not structure.value_tokens:
        errors.append("at least one value token is required")
    if any(token == "" for token in structure.value_tokens):
        errors.append("empty value token")
    if any(any(ch not in {"0", "1"} for ch in token) for token in structure.value_tokens):
        errors.append("value tokens must be binary")
    if len(structure.values) != len(structure.value_tokens):
        errors.append("values must align with value tokens")
    if int(structure.stop_count) != max(0, len(structure.value_tokens) - 1):
        errors.append("stop_count must equal len(value_tokens) - 1")
    value_stream = "".join(structure.value_tokens)
    try:
        validate_stop_addresses(stops, len(value_stream))
    except InvalidSamrasStructure as exc:
        errors.append(str(exc))
    starts = [0, *stops]
    ends = [*stops, len(value_stream)]
    if len(starts) != len(structure.value_tokens) or len(ends) != len(structure.value_tokens):
        errors.append("stop addresses do not yield the expected number of tokens")
    else:
        for index, (left, right) in enumerate(zip(starts, ends, strict=False)):
            token = value_stream[left:right]
            if token != structure.value_tokens[index]:
                errors.append("stop addresses do not match the provided value tokens")
                break
    try:
        derived = derive_addresses_from_child_counts(structure.values)
        if tuple(structure.addresses) != derived:
            errors.append("addresses do not match breadth-first child-count derivation")
    except InvalidSamrasStructure as exc:
        errors.append(str(exc))
    if not errors:
        try:
            rebuilt_values = child_counts_from_addresses(structure.addresses)
            if rebuilt_values != tuple(int(item) for item in structure.values):
                errors.append("address set does not round-trip to the decoded child counts")
        except InvalidSamrasStructure as exc:
            errors.append(str(exc))
    if require_canonical_roundtrip and errors:
        warnings.append("canonical round-trip not satisfied")
    return SamrasValidationReport(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))
