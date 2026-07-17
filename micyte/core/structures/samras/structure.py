from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_address_segments(address: str) -> tuple[int, ...]:
    token = as_text(address)
    if not token:
        raise ValueError("address is required")
    parts = token.split("-")
    segments: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"address segment is not numeric: {part}")
        value = int(part, 10)
        if value <= 0:
            raise ValueError(f"address segment must be positive: {part}")
        segments.append(value)
    return tuple(segments)


def format_address(segments: tuple[int, ...] | list[int]) -> str:
    if not segments:
        return ""
    return "-".join(str(int(item)) for item in segments)


def parent_address(address: str) -> str:
    segments = parse_address_segments(address)
    if len(segments) <= 1:
        return ""
    return format_address(list(segments[:-1]))


def address_depth(address: str) -> int:
    return len(parse_address_segments(address))


def address_sort_key(address: str) -> tuple[int, ...]:
    return parse_address_segments(address)


@dataclass(frozen=True)
class SamrasStructure:
    root_ref: str
    bitstream: str
    address_width_bits: int
    stop_count_width_bits: int
    stop_count: int
    stop_addresses: tuple[int, ...]
    value_tokens: tuple[str, ...]
    values: tuple[int, ...]
    addresses: tuple[str, ...]
    source_format: str
    canonical_state: str
    warnings: tuple[str, ...] = ()

    @property
    def decoded_value_count(self) -> int:
        return len(self.values)

    @property
    def root_count(self) -> int:
        return int(self.values[0]) if self.values else 0

    @property
    def node_count(self) -> int:
        return len(self.addresses)

    @property
    def node_values(self) -> list[int]:
        return [int(item) for item in self.values]

    @property
    def address_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        child_counts = list(self.values[1:])
        for index, address in enumerate(self.addresses):
            out[str(address)] = int(child_counts[index]) if index < len(child_counts) else 0
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_ref": self.root_ref,
            "bitstream": self.bitstream,
            "address_width_bits": int(self.address_width_bits),
            "stop_count_width_bits": int(self.stop_count_width_bits),
            "stop_count": int(self.stop_count),
            "decoded_value_count": int(self.decoded_value_count),
            "root_count": int(self.root_count),
            "node_count": int(self.node_count),
            "stop_addresses": [int(item) for item in self.stop_addresses],
            "value_tokens": [str(item) for item in self.value_tokens],
            "values": [int(item) for item in self.values],
            "node_values": [int(item) for item in self.values],
            "addresses": [str(item) for item in self.addresses],
            "address_map": {str(key): int(value) for key, value in self.address_map.items()},
            "source_format": self.source_format,
            "canonical_state": self.canonical_state,
            "warnings": [str(item) for item in self.warnings],
        }
