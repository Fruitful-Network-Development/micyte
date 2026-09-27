"""HOPS-chronological tokens <-> calendar dates, in ANY sandbox's namespace.

The write path encodes a calendar day into a HOPS-UTC token against the sandbox's own
chronology radix; this is the inverse, used by read tools (the Inventory Manager, the
calendar) to show a readable date. Kept in the tools layer so a read tool need not import
the heavier write runtime.

## The chronology row is found by LABEL, not by address

This module used to read the anchor's ``1-1-6`` row, because that is where the agro anchor
keeps its chronology. Measured across the live store, that address means different things:

======================================  =======  ==============================
sandbox                                 1-1-5    1-1-6
======================================  =======  ==============================
a farm sandbox (FARM)                  lcl      **HOPS-chronological**
``registrar`` / a client sandbox        **HOPS-chronological**   lcl-SAMRAS
======================================  =======  ==============================

So a fixed address does not read a handyman instance's chronology — it reads its **lcl
radix**, and builds a chronology authority out of a classification numbering. That is the
same namespace blindness the decoder ring exists to end, one layer down: the field registry
already knows ``rf.3-1-3`` is ``title`` in the registrar and ``coordinate`` in a farm, and
the anchor's own rows need the same treatment.

**And the two spellings differ.** The registrar block says ``HOPS-chornological`` and the
farm says ``HOPS-chronological`` — a transposition, copied verbatim into every sandbox that
inherited each anchor. Matching an exact string would have worked in a farm and silently
failed everywhere else, which is the failure this module is being fixed for. The two known
spellings are listed, and anything else is refused loudly rather than decoded against the
wrong radix.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from micyte.agro.doc_lib import (
    ANCHOR_TIME_PRIMITIVE,
    _as_rows,
    build_chronology_authority,
    schema_from_anchor_payload,
)
from micyte.core.structures.hops.chronology import (
    decode_hops_as_utc_datetime,
    encode_utc_datetime_as_hops,
)

#: The chronology row's label, as the live anchors actually spell it. `chornological` is a
#: transposition in the registrar block; it is carried rather than corrected for the reason
#: the archetype mint carries the registrar's `2-1-1` inconsistency — every document alive
#: today is anchored on it, and correcting a label is a migration, not a rider.
CHRONOLOGY_LABELS = frozenset({"hops-chronological", "hops-chornological"})

#: The family the chronology row lives in. Which MEMBER of it varies by namespace, which is
#: the whole point of searching rather than indexing.
CHRONOLOGY_FAMILY = "1-1-"


def chronology_row(anchor_doc: Any) -> tuple[str, list] | None:
    """``(address, head)`` of the anchor's chronology row, or ``None``.

    Searched by label across the ``1-1`` family, because the address is not stable across
    namespaces. Returns the address too, so a caller that needs to say *where* it found the
    chronology can — an unresolvable anchor is worth naming rather than silently dating
    nothing.
    """
    if anchor_doc is None:
        return None
    for row in _as_rows(anchor_doc):
        address = str(getattr(row, "datum_address", "") or "")
        if not address.startswith(CHRONOLOGY_FAMILY):
            continue
        raw = getattr(row, "raw", None)
        if not (isinstance(raw, list) and raw and isinstance(raw[0], list) and len(raw[0]) > 2):
            continue
        label = ""
        if len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
            label = str(raw[1][0])
        if label.strip().lower() in CHRONOLOGY_LABELS:
            return address, raw[0]
    return None


def chrono_authority(anchor_doc: Any) -> Any | None:
    """Build the chronology authority from an anchor doc's chronology row (or ``None``)."""
    found = chronology_row(anchor_doc)
    if found is None:
        return None
    _address, head = found
    schema = schema_from_anchor_payload(
        {"1-1-1": [["1-1-1", ANCHOR_TIME_PRIMITIVE, str(head[2])], ["HOPS-chronological"]]})
    return build_chronology_authority(
        schema_payload=schema,
        quadrennium_payload={"3-1-1": [["3-1-1", "~", "0"], ["quadrennium"]]},
        cosmological_prefix=(0, 0))


def _parse_moment(text: str) -> datetime:
    """``YYYY-MM-DD``, ``MM-DD-YYYY`` or either of those with ``THH:MM[:SS]`` after it.

    ## THE CLOCK IS TAKEN AS TYPED. Nothing here converts a timezone.

    A ``datetime-local`` input hands back a WALL CLOCK with no offset on it — the operator's
    2pm, said the way they said it — and the tzinfo attached below is ``UTC`` because that
    is the frame the whole chronology is compiled in
    (:func:`~micyte.core.structures.hops.chronology.encode_utc_datetime_as_hops`), not
    because anybody claimed the operator is in Greenwich. Read the token back through
    :func:`hops_token_to_datetime` and the same 2pm comes out, which is the property every
    surface in this portal depends on.

    **Converting would be worse, and measurably so.** No instance carries a timezone
    anywhere in this codebase — there is no correct offset to convert BY — and every job in
    the live log was written at midnight-UTC by the day-only encoder this replaces. Shifting
    those by a UTC-05:00 would redate all of them to 7pm the evening BEFORE, silently, on
    every screen that reads the log. A stored wall clock keeps every row saying the day it
    was booked.

    **What this costs, named:** the ``.ics`` export stamps ``DTSTART`` with a trailing ``Z``
    (:mod:`micyte.tools._ics`), so a phone importing a 2pm job draws it at 2pm *UTC* — 10am
    in Ohio. That was already true of the midnight tokens; a time of day makes it visible.
    Fixing it means giving an instance a timezone, which is a fact about the instance and
    belongs with its profile, not smuggled into a date parser.
    """
    text = str(text or "").strip()
    # `T` is what a `datetime-local` input posts; a space is what a person pastes.
    stamp = text.replace(" ", "T")
    day_part, _, time_part = stamp.partition("T")
    parts = day_part.split("-")
    if len(parts) < 3:
        raise ValueError(f"{text!r} is not a date")
    if len(parts[0]) == 4:                           # YYYY-MM-DD
        year, month, dom = (int(x) for x in parts[:3])
    else:                                            # MM-DD-YYYY
        month, dom, year = (int(x) for x in parts[:3])
    hour = minute = second = 0
    if time_part:
        clock = time_part.split(":")
        if len(clock) < 2:
            raise ValueError(f"{time_part!r} is not a time of day")
        hour, minute = int(clock[0]), int(clock[1])
        # Seconds ride through when a caller sends them; the form never does. Truncated at
        # the decimal because a fractional second is not something anyone books.
        second = int(float(clock[2])) if len(clock) > 2 and clock[2] else 0
    return datetime(year, month, dom, hour, minute, second, tzinfo=UTC)


def moment_to_hops_token(anchor_doc: Any, moment: str) -> str:
    """Encode a day — and a TIME OF DAY, when one was given — for THIS sandbox.

    The hour-aware half of :func:`day_to_hops_token`, which could only ever say midnight, so
    a 2pm appointment was not expressible by any writer in the product. The token format was
    never the obstacle: ``encode_utc_datetime_as_hops`` takes a full datetime and
    :func:`hops_token_to_datetime` already kept the hour on the way back. Only the write
    side could not set one.

    Accepts ``YYYY-MM-DD`` unchanged, so every existing caller keeps its exact behaviour —
    a day with no clock on it is midnight, which is also how a job with no time booked reads
    back. See :func:`_parse_moment` for what a typed 2pm MEANS and where it is not converted.

    Raises ``ValueError`` rather than returning a fallback. A moment that cannot be encoded
    must not be written as something else; the caller refuses the save and says so.
    """
    authority = chrono_authority(anchor_doc)
    if authority is None:
        raise ValueError(
            "this sandbox's anchor has no HOPS-chronological row "
            f"(looked for {sorted(CHRONOLOGY_LABELS)} across {CHRONOLOGY_FAMILY}*)"
        )
    text = str(moment or "").strip()
    try:
        return encode_utc_datetime_as_hops(_parse_moment(text), authority=authority)
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a date: {exc}") from None


def day_to_hops_token(anchor_doc: Any, day: str) -> str:
    """Encode ``YYYY-MM-DD`` (or ``MM-DD-YYYY``) into a HOPS-UTC token for THIS sandbox.

    The counterpart to :func:`hops_token_to_date`, here so the two cannot drift and so every
    caller resolves the chronology the same way. A write that stored the form's string
    unencoded is what this exists to stop: the archetype declares ``utc``, which is a
    HOPS-chronological babelette, and a cell holding ``2026-03-16`` is not a magnitude under
    that babelette at all — it just looks like a date to a human reading the row.

    Kept as the name the date-only writers say — the .xlsx importers, the re-encode script —
    and DELEGATING, so there is one parser and one encoder rather than two that agree until
    a time of day is added to one of them.
    """
    return moment_to_hops_token(anchor_doc, day)


def hops_token_to_date(authority: Any, token: str) -> date | None:
    """Decode a HOPS-UTC token to a ``date`` using a prebuilt ``authority`` (None on failure)."""
    token = (token or "").strip()
    if not token or authority is None:
        return None
    try:
        return decode_hops_as_utc_datetime(token, authority=authority).date()
    except Exception:
        return None


def hops_token_to_datetime(authority: Any, token: str) -> datetime | None:
    """As :func:`hops_token_to_date`, keeping the time of day.

    A calendar needs the hour; a shelf-life calculation does not. Both read the same token,
    so they read it through the same decoder rather than two.
    """
    token = (token or "").strip()
    if not token or authority is None:
        return None
    try:
        return decode_hops_as_utc_datetime(token, authority=authority)
    except Exception:
        return None


__all__ = [
    "CHRONOLOGY_FAMILY",
    "CHRONOLOGY_LABELS",
    "chrono_authority",
    "chronology_row",
    "day_to_hops_token",
    "hops_token_to_date",
    "hops_token_to_datetime",
    "moment_to_hops_token",
]
