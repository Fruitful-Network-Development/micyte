from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .time_address import normalize_time_address_for_schema, parse_time_address

_SECONDS_PER_DAY = 24 * 60 * 60


@dataclass(frozen=True)
class ChronologyAuthority:
    schema_payload: dict[str, Any]
    quadrennium_payload: dict[str, Any]
    cosmological_prefix: tuple[int, int] = (0, 0)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _require_quadrennium_authority(payload: dict[str, Any]) -> None:
    row = payload.get("3-1-1")
    if not isinstance(row, list) or not row:
        raise ValueError("quadrennium authority is missing HOPS-babelette-quadrennium_cycle")


def build_chronology_authority(
    *,
    schema_payload: dict[str, Any],
    quadrennium_payload: dict[str, Any],
    cosmological_prefix: tuple[int, int] = (0, 0),
) -> ChronologyAuthority:
    if not bool(schema_payload.get("ok")):
        raise ValueError(str(schema_payload.get("error") or "chronology schema is unavailable"))
    _require_quadrennium_authority(quadrennium_payload)
    return ChronologyAuthority(
        schema_payload=dict(schema_payload),
        quadrennium_payload=dict(quadrennium_payload),
        cosmological_prefix=(int(cosmological_prefix[0]), int(cosmological_prefix[1])),
    )


def _as_utc_datetime(value: datetime | int | float) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    number = float(value)
    if number > 10_000_000_000:
        number = number / 1000.0
    return datetime.fromtimestamp(number, tz=UTC)


def _day_in_quadrennium(current: datetime, cycle_start_year: int) -> int:
    cycle_start = datetime(cycle_start_year, 1, 1, tzinfo=UTC)
    delta = current - cycle_start
    day_index = int(delta.total_seconds() // _SECONDS_PER_DAY) + 1
    if day_index < 1:
        raise ValueError("computed day-in-cycle fell below 1")
    return day_index


def encode_utc_datetime_as_hops(
    value: datetime | int | float,
    *,
    authority: ChronologyAuthority,
) -> str:
    current = _as_utc_datetime(value)
    cycle_start_year = current.year - (current.year % 4)
    cycle_group = cycle_start_year // 4000
    cycle = (cycle_start_year // 4) + 1 - (cycle_group * 1000)
    day_in_cycle = _day_in_quadrennium(current, cycle_start_year)
    address = "-".join(
        str(part)
        for part in (
            authority.cosmological_prefix[0],
            authority.cosmological_prefix[1],
            cycle_group,
            cycle,
            day_in_cycle,
            current.hour,
            current.minute,
            current.second,
        )
    )
    return normalize_time_address_for_schema(address, authority.schema_payload)


def encode_unix_ms_as_hops(unix_ms: int | float, *, authority: ChronologyAuthority) -> str:
    return encode_utc_datetime_as_hops(unix_ms, authority=authority)


def decode_hops_as_utc_datetime(address: str, *, authority: ChronologyAuthority) -> datetime:
    """Inverse of :func:`encode_utc_datetime_as_hops`.

    Requires at least day specificity (``p0-p1-cycle_group-cycle-day``); missing
    hour/minute/second segments decode as 0. The cosmological prefix must match
    the authority's.
    """
    normalized = normalize_time_address_for_schema(address, authority.schema_payload)
    parsed = parse_time_address(normalized)
    if parsed.prefix != authority.cosmological_prefix:
        raise ValueError(
            f"cosmological prefix {parsed.prefix} does not match authority {authority.cosmological_prefix}"
        )
    if parsed.depth < 3:
        raise ValueError("time address must reach day specificity to decode to a datetime")
    cycle_group, cycle, day_in_cycle = parsed.temporal[0], parsed.temporal[1], parsed.temporal[2]
    if cycle < 1 or day_in_cycle < 1:
        raise ValueError("cycle and day-in-cycle segments must be >= 1")
    hour = parsed.temporal[3] if parsed.depth > 3 else 0
    minute = parsed.temporal[4] if parsed.depth > 4 else 0
    second = parsed.temporal[5] if parsed.depth > 5 else 0
    cycle_start_year = (cycle_group * 1000 + cycle - 1) * 4
    return datetime(cycle_start_year, 1, 1, tzinfo=UTC) + timedelta(
        days=day_in_cycle - 1, hours=hour, minutes=minute, seconds=second
    )


__all__ = [
    "ChronologyAuthority",
    "build_chronology_authority",
    "decode_hops_as_utc_datetime",
    "encode_unix_ms_as_hops",
    "encode_utc_datetime_as_hops",
]
