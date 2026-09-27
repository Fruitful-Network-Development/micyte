"""One event as an ``.ics`` file — the "add to calendar" the operator asked for.

A single artifact answers "IOS or Google etc.": both import ``text/calendar``, so there is
one thing to build and nothing leaves the box on the way. A prefilled
``calendar.google.com`` template URL was the alternative and is deliberately NOT offered —
clicking it sends the customer's name, the time and the street address to Google, which is
not a thing a handyman's job log should do because a button was convenient.

RFC 5545 is fussier than it looks, and each of these is a real interoperability failure
rather than tidiness:

* **CRLF**, every line. A bare LF file is rejected outright by several importers.
* **Folding at 75 octets**, continued with a leading space — and octets, not characters, so
  the fold has to count the UTF-8 encoding rather than ``len()``.
* **Escaping** of ``\\``, ``;``, ``,`` and newlines in every TEXT value. An unescaped comma
  in "front walk, driveway and steps" silently truncates the summary at the comma in some
  clients, which looks like the data is wrong rather than the file.
* **A stable UID.** Re-importing the same job must update the event rather than duplicate
  it, so the UID is derived from the datum address, not generated.
"""

from __future__ import annotations

from datetime import datetime, timedelta

#: Line-length limit from RFC 5545 §3.1, in OCTETS.
FOLD_OCTETS = 75

PRODID = "-//Fruitful Network Development//MiCyte//EN"

#: Default length of a job with no recorded span. An .ics event needs an end, and a
#: zero-length one renders as a pin rather than an appointment in most clients.
DEFAULT_DURATION = timedelta(hours=2)


def escape_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11. Backslash FIRST, or it doubles the rest."""
    out = str(value or "")
    out = out.replace("\\", "\\\\")
    out = out.replace("\n", "\\n").replace("\r", "")
    out = out.replace(";", "\\;").replace(",", "\\,")
    return out


def fold(line: str) -> str:
    """Fold one content line to 75 octets, continuing with a leading space.

    Counted in octets because the limit is octets: a line of accented characters folds
    earlier than its character count suggests, and a client reading the un-folded overlong
    line may drop it.
    """
    raw = line.encode("utf-8")
    if len(raw) <= FOLD_OCTETS:
        return line
    chunks: list[bytes] = []
    start = 0
    limit = FOLD_OCTETS
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Never split a multi-byte character: back off to a lead byte.
        while end > start and end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end])
        start = end
        limit = FOLD_OCTETS - 1          # continuation lines carry a leading space
    head, *rest = (chunk.decode("utf-8") for chunk in chunks)
    return "\r\n ".join([head, *rest])


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def event_ics(
    *,
    uid: str,
    starts: datetime,
    ends: datetime | None = None,
    summary: str = "",
    location: str = "",
    description: str = "",
    now: datetime | None = None,
) -> str:
    """One VEVENT in a complete VCALENDAR, ready to serve as ``text/calendar``.

    ``now`` is injectable so a test can assert the whole file byte for byte; DTSTAMP is
    otherwise the only line that changes between two identical exports.
    """
    finish = ends or (starts + DEFAULT_DURATION)
    if finish <= starts:
        finish = starts + DEFAULT_DURATION
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{escape_text(uid)}",
        f"DTSTAMP:{_stamp(now or starts)}",
        f"DTSTART:{_stamp(starts)}",
        f"DTEND:{_stamp(finish)}",
    ]
    if summary:
        lines.append(f"SUMMARY:{escape_text(summary)}")
    if location:
        lines.append(f"LOCATION:{escape_text(location)}")
    if description:
        lines.append(f"DESCRIPTION:{escape_text(description)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def filename_for(summary: str, starts: datetime) -> str:
    """A download name a human can find again, with nothing a filesystem will refuse."""
    stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(summary or "event"))
    stem = "-".join(part for part in stem.split("-") if part)[:48] or "event"
    return f"{starts.date().isoformat()}-{stem}.ics"


__all__ = ["DEFAULT_DURATION", "FOLD_OCTETS", "PRODID", "escape_text", "event_ics",
           "filename_for", "fold"]
