"""INSTRUMENTS — what an instance interfaces with ACROSS its sandboxes.

The operator's own definition (2026-08-20): "artifacts that allow an instance to interface
with specific *types* of datum information from different sandboxes". That is a different
kind of thing from a sandbox, and the Compendium's shelf shows it as one.

## Why this is a category and not two tools

Both members already existed and both were deleted on 2026-08-16 with the calendar-only
rail — and the primitive they read did not go with them. :mod:`micyte.tools._sandboxes`
says so in its own first paragraph: it is "held here as a primitive because two surfaces
declare against it — the rolodex reads every sandbox's contacts, the unpinned calendar
reads every sandbox's logs". A primitive with a stated pair of callers and no callers is a
category waiting to be named.

## An instrument is not a sandbox, and must not look like one

A sandbox is a place: it holds documents, it has a local domain, and opening it opens that
domain. An instrument holds nothing. It is a lens over a datum KIND wherever that kind is
kept, so it cannot be browsed into, cannot be written to as a place, and has no anchor.
Mixing the two on one shelf would make "how many sandboxes do I have" unanswerable at a
glance, which is the shelf's whole job — so they render as their own band, and the card
draws the sandboxes it spans along its foot. An instrument that reads three sandboxes and
one that reads one must not look alike.

## Read-only, both of them

Each spans documents that other surfaces OWN. The calendar's moments are written where
they are logged; a contact is edited in its own sandbox's contacts document. An instrument
that also wrote would be a second writer of a document a tool already owns, which is the
rule ``_write_owners`` enforces by raising.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calendar_viewer import TOOL_ID as CALENDAR_TOOL
from .contacts_manager import CONTACTS
from .rolodex import TOOL_ID as ROLODEX_TOOL


@dataclass(frozen=True)
class Instrument:
    """One lens over one datum kind, across every sandbox of an instance."""

    instrument_id: str
    label: str
    #: What an operator gains by opening it — the shelf card's second line.
    why: str
    #: The datum KIND it spans, in the operator's words. Not an archetype id: the calendar
    #: reads every ``class_log`` shape there is, and naming one would be narrower than the
    #: instrument.
    reads: str
    #: The workbench tool that draws it. An instrument is a PLACE on the shelf; the drawing
    #: is a tool that already exists, so there is no second renderer to keep in step.
    tool_id: str
    #: The sprite SYMBOL name, bare. The client stamps the ``icon-`` prefix
    #: (``compendiumIconMarkup``), so carrying it here would produce ``#icon-icon-calendar``
    #: and an empty glyph — the external-``use`` lesson from 2026-08-16.
    icon_id: str


INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument(
        instrument_id="calendar",
        label="Calendar",
        why="every dated thing this instance keeps, wherever it is logged",
        reads="dated rows",
        # The REGISTERED id, imported. The literal "calendar_viewer" (the module's
        # name, not the tool's) sat here from 2026-08-20 to 2026-08-21 and the
        # instrument face answered "Calendar has no reader installed" the whole time.
        tool_id=CALENDAR_TOOL,
        icon_id="calendar",
    ),
    Instrument(
        instrument_id="rolodex",
        label="Rolodex",
        why="everyone this instance deals with, and which sandbox keeps them",
        reads=CONTACTS,
        tool_id=ROLODEX_TOOL,
        icon_id="contacts_manager",
    ),
    # The DEFAULT instrument (operator depiction 2026-08-21). Its face is NOT a
    # registered micyte tool: it reads facts only the host holds (the contact-card
    # file, the oauth posture, the instance catalog) and micyte must not import
    # fnd_app — so `tool_id` here names the host-side builder
    # (fnd_app.…profile_interface_runtime), which the instrument face resolver
    # special-cases by this id. The deviation is stated in that module's docstring.
    Instrument(
        instrument_id="profile_interface",
        label="Profile",
        why="who this instance is, its channel accounts, and your session",
        reads="the msn_profile, the contact card, and the channel aliases",
        tool_id="profile_interface",
        icon_id="profile_interface",
    ),
)

INSTRUMENTS_BY_ID: dict[str, Instrument] = {i.instrument_id: i for i in INSTRUMENTS}


def instrument(instrument_id: str) -> Instrument | None:
    """The instrument named, or ``None`` — an unknown id is a request for nothing, not
    an error: a stale bookmark should land on the shelf, not on a stack trace."""
    return INSTRUMENTS_BY_ID.get(str(instrument_id or "").strip())


__all__ = ["INSTRUMENTS", "INSTRUMENTS_BY_ID", "Instrument", "instrument"]
