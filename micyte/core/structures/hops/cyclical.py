"""Cyclical (interval) chronological HOPS structures — the ic-hops family.

The universal chronology (``uc hops``, anchor datum ``1-1-1`` lineage,
``4-1000-1000-1000-1462-24-60-60``) positions an *instance* of a thing on the
absolute time axis. The structures here instead position a *recurring* event
within one cycle of a fixed period; which structure a stamp is in reference to
carries the cadence (weekly vs monthly vs dated), so cadence is derivable from
the address itself rather than from side-band labels:

* ``qc hops`` — quadrennium chronological: ``1462-24-60`` (day-in-quadrennium,
  1-based 1..1461 with slot 0 reserved; hour; minute). Quadrenniums, not years,
  because HOPS siblings must share division — 365- and 366-day year siblings
  would be two unit types, while 1461 absorbs the leap day into one fixed
  container.
* ``hc hops`` — hebdomad chronological: ``8-24-60`` (day-of-week 1..7, hour,
  minute). Day 1 = Monday.
* ``lc hops`` — lunation chronological: ``32-24-60`` (day-in-lunation 1..31 of
  a fixed civil 30-day cycle). Defined and reserved; no producer uses it yet.

Phase anchoring is EPOCH-CONTINUOUS from 2024-01-01 (quadrennium 507 day 1,
a Monday — so hebdomad day 1 = Monday needs no offset). ``1461 % 7 == 5`` and
``1461 % 30 == 21``: positions reset at each cycle boundary would drift, so
hebdomad/lunation ordinals are counted continuously across quadrenniums.

Span/duration is NOT an ordinal address: event rows pair a stamp here with a
(time-unit ref, magnitude) span in the time-*incremental*-unit lineage.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

EPOCH = date(2024, 1, 1)  # quadrennium 507 day 1 — a Monday
DAYS_PER_QUADRENNIUM = 1461

# lcl 1-5 chronology_structure leaves (mycelium_network sandbox taxonomy)
LCL_UC = "1-5-1"
LCL_QC = "1-5-2"
LCL_HC = "1-5-3"
LCL_LC = "1-5-4"

# lcl 1-6 time_unit leaves (tiu lineage) for span magnitudes
LCL_DAY_UNIT = "1-6-1"
LCL_HOUR_UNIT = "1-6-2"
LCL_MINUTE_UNIT = "1-6-3"

QC_DENOTATIONS = (1462, 24, 60)
HC_DENOTATIONS = (8, 24, 60)
LC_DENOTATIONS = (32, 24, 60)
_DENOTATIONS_BY_STRUCTURE = {LCL_QC: QC_DENOTATIONS, LCL_HC: HC_DENOTATIONS, LCL_LC: LC_DENOTATIONS}

LUNATION_DAYS = 30  # fixed civil lunation; slot 31 is denotational headroom


def encode_mixed_radix_magnitude(denotations: tuple[int, ...] | list[int]) -> str:
    """Inverse of ``time_address_schema.decode_mixed_radix_magnitude`` with the
    minimal-width header convention used by the anthology-base magnitudes."""
    values = [int(v) for v in denotations]
    if not values or any(v <= 0 for v in values):
        raise ValueError("denotations must be positive integers")
    segments = [format(v, "b") for v in values]
    stops: list[int] = []
    total = 0
    for seg in segments[:-1]:
        total += len(seg)
        stops.append(total)
    count = len(values)
    count_width = max(1, count.bit_length())
    stop_width = max(1, max(stops).bit_length()) if stops else 1
    bits = "0" * stop_width + "1"
    bits += "0" * count_width + "1"
    bits += format(count, f"0{count_width}b")
    for stop in stops:
        bits += format(stop, f"0{stop_width}b")
    bits += "".join(segments)
    return bits


QC_MAGNITUDE_BITS = encode_mixed_radix_magnitude(QC_DENOTATIONS)
HC_MAGNITUDE_BITS = encode_mixed_radix_magnitude(HC_DENOTATIONS)
LC_MAGNITUDE_BITS = encode_mixed_radix_magnitude(LC_DENOTATIONS)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def cycle_start_year_of(value: date | datetime) -> int:
    d = _as_date(value)
    return d.year - (d.year % 4)


def qc_day_of(value: date | datetime) -> int:
    """1-based day-in-quadrennium of a date (cycle-relative position)."""
    d = _as_date(value)
    return (d - date(cycle_start_year_of(d), 1, 1)).days + 1


def date_of_qc_day(day: int, *, cycle_start_year: int) -> date:
    if not 1 <= int(day) <= DAYS_PER_QUADRENNIUM:
        raise ValueError(f"qc day must be 1..{DAYS_PER_QUADRENNIUM}: {day}")
    return date(int(cycle_start_year), 1, 1) + timedelta(days=int(day) - 1)


def hc_day_of(value: date | datetime) -> int:
    """1-based hebdomad day (1=Monday), epoch-continuous across quadrenniums."""
    return (_as_date(value) - EPOCH).days % 7 + 1


def lc_day_of(value: date | datetime) -> int:
    """1-based day in the fixed civil 30-day lunation, epoch-continuous."""
    return (_as_date(value) - EPOCH).days % LUNATION_DAYS + 1


def parse_ic_stamp(stamp: str, *, structure: str) -> tuple[int, int, int]:
    """Parse a cyclical stamp ``<day>[-<hh>[-<mm>]]`` against its structure's
    denotations. Returns (day, hour, minute); missing segments decode as 0.
    Day is 1-based; hour/minute are 0-based, per the structure radices."""
    denotations = _DENOTATIONS_BY_STRUCTURE.get(str(structure))
    if denotations is None:
        raise ValueError(f"unknown cyclical structure: {structure!r}")
    token = str(stamp or "").strip()
    parts = token.split("-") if token else []
    if not parts or len(parts) > len(denotations) or any(not p.isdigit() for p in parts):
        raise ValueError(f"malformed cyclical stamp: {stamp!r}")
    values = [int(p) for p in parts] + [0] * (len(denotations) - len(parts))
    day, hour, minute = values[0], values[1], values[2]
    if not 1 <= day < denotations[0]:
        raise ValueError(f"stamp day {day} out of range for structure {structure}")
    if not 0 <= hour < denotations[1] or not 0 <= minute < denotations[2]:
        raise ValueError(f"stamp time out of range: {stamp!r}")
    return day, hour, minute


def format_ic_stamp(day: int, hour: int | None = None, minute: int | None = None) -> str:
    parts = [int(day)]
    if hour is not None:
        parts.append(int(hour))
        if minute is not None:
            parts.append(int(minute))
    return "-".join(str(p) for p in parts)


def qc_day_in_closures(qc_day: int, closures: list[tuple[int, int]]) -> bool:
    """closures = [(start_day, span_days)] — cycle-relative closed runs that
    repeat every quadrennium. A run may extend past day 1461 conceptually; the
    caller derives runs within one cycle, so we test plain containment."""
    for start, span in closures:
        if int(start) <= int(qc_day) < int(start) + int(span):
            return True
    return False


def open_runs_from_closures(closures: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Complement of the closed runs within [1, 1461] as (start_day, end_day)
    inclusive runs. No closures → the whole cycle is one open run."""
    closed: list[tuple[int, int]] = []
    for start, span in sorted((int(s), int(n)) for s, n in closures):
        lo, hi = max(1, start), min(DAYS_PER_QUADRENNIUM, start + span - 1)
        if hi < lo:
            continue
        if closed and lo <= closed[-1][1] + 1:
            closed[-1] = (closed[-1][0], max(closed[-1][1], hi))
        else:
            closed.append((lo, hi))
    runs: list[tuple[int, int]] = []
    cursor = 1
    for lo, hi in closed:
        if lo > cursor:
            runs.append((cursor, lo - 1))
        cursor = hi + 1
    if cursor <= DAYS_PER_QUADRENNIUM:
        runs.append((cursor, DAYS_PER_QUADRENNIUM))
    return runs


def next_hc_occurrences(
    hc_days: set[int] | list[int],
    closures: list[tuple[int, int]],
    *,
    now: date | datetime,
    limit: int = 3,
    horizon_days: int = 800,
) -> list[date]:
    """Upcoming dates whose hebdomad day is in ``hc_days`` and whose
    cycle-relative day is not inside a closed run."""
    wanted = {int(d) for d in hc_days if 1 <= int(d) <= 7}
    if not wanted:
        return []
    day = _as_date(now)
    out: list[date] = []
    for _ in range(max(1, int(horizon_days))):
        if hc_day_of(day) in wanted and not qc_day_in_closures(qc_day_of(day), closures):
            out.append(day)
            if len(out) >= limit:
                break
        day += timedelta(days=1)
    return out


def current_open_window(
    closures: list[tuple[int, int]],
    *,
    now: date | datetime,
) -> tuple[date, date]:
    """The open run containing ``now`` (cycle-relative), else the next open run
    (wrapping into the next quadrennium when the cycle tail is closed)."""
    today = _as_date(now)
    runs = open_runs_from_closures(closures)
    cycle_year = cycle_start_year_of(today)
    today_day = qc_day_of(today)
    for lo, hi in runs:
        if lo <= today_day <= hi:
            return (date_of_qc_day(lo, cycle_start_year=cycle_year),
                    date_of_qc_day(hi, cycle_start_year=cycle_year))
    for lo, hi in runs:
        if lo > today_day:
            return (date_of_qc_day(lo, cycle_start_year=cycle_year),
                    date_of_qc_day(hi, cycle_start_year=cycle_year))
    lo, hi = runs[0]
    return (date_of_qc_day(lo, cycle_start_year=cycle_year + 4),
            date_of_qc_day(hi, cycle_start_year=cycle_year + 4))


__all__ = [
    "DAYS_PER_QUADRENNIUM",
    "EPOCH",
    "HC_DENOTATIONS",
    "HC_MAGNITUDE_BITS",
    "LCL_DAY_UNIT",
    "LCL_HC",
    "LCL_HOUR_UNIT",
    "LCL_LC",
    "LCL_MINUTE_UNIT",
    "LCL_QC",
    "LCL_UC",
    "LC_DENOTATIONS",
    "LC_MAGNITUDE_BITS",
    "LUNATION_DAYS",
    "QC_DENOTATIONS",
    "QC_MAGNITUDE_BITS",
    "current_open_window",
    "cycle_start_year_of",
    "date_of_qc_day",
    "encode_mixed_radix_magnitude",
    "format_ic_stamp",
    "hc_day_of",
    "lc_day_of",
    "next_hc_occurrences",
    "open_runs_from_closures",
    "parse_ic_stamp",
    "qc_day_in_closures",
    "qc_day_of",
]
