"""What a PAYMENT INSTRUMENT is, on this side of the processor — the rule, with no I/O.

The operator's ask (2026-09-16): the grantor sandbox keeps the grantee's card "in the
grantee datum docs … handled via hash datum entries as I want to make sure that I am being
responsible in how it is stored." The responsible half of that sentence is kept here and
the mechanism is changed, for a reason that is arithmetic rather than caution.

## Why no hash of a card number is stored, anywhere, by anything that imports this

A primary account number is 13–19 digits. Its first six to eight are the BIN — a public,
enumerable table — and its last is a Luhn check digit. For a known BIN the search space
is at most 10^9 candidates and Luhn removes nine in ten. SHA-256 over 10^8 candidates is
seconds on one GPU. A per-record salt has to be stored beside the hash, so it changes
nothing about the exponent; it only stops one table from cracking every row at once. A
hashed PAN in a datum document is therefore a PAN in a datum document, readable by anyone
who can read the document — and MOS copies every ``lv.`` write into a 139.9 MB catalog
blob, and into every backup of it, on every unrelated write forever.

What makes recurring billing possible is not the number. It is a **processor vault
reference**: the card goes into fields the processor hosts, the processor hands back an
opaque token, and FND charges the token. FND never sees, transmits or stores a PAN, which
is also what keeps FND on PCI SAQ-A rather than SAQ-D.

## Record vs instrument — the split ``keypass`` already codifies

    the RECORD     -- brand, last four, expiry, STATE, when it arrived: the recogniser
                   -- MOS, ``grantor.grantee-<msn>``, the row a client and the operator read
    the INSTRUMENT -- the vault reference, the processor, the environment
                   -- an instance FILE, 0600, never MOS (``grantor_instruments``)

This module is the RULE both halves obey. It knows no store, no file, no processor and no
surface. What it does know is what a recogniser is, which states an instrument can be in,
what each state means to the person whose card it is, and — the one rule that has to be
mechanical rather than remembered — what a card number LOOKS like, so that every writer
on either side can refuse one at the door.

## Why the PAN guard is here and not in a writer

Three writers exist on day one (the instrument file, the datum row, the port's vaulted
result) and a fourth will. A guard written in each is a guard the fourth forgets. Written
once, imported by all, it is a property of the module rather than a promise of a caller —
the same reason ``keypass`` keeps the secret from leaving rather than trusting a renderer
not to draw it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

#: A card is on file and may be charged.
STATE_PRESENT = "present"
#: No card is on file. The seven grantees onboarded before 2026-09-16 are here, and it is
#: a STATED state — a row that says so — not a missing row. An instrument row nobody wrote
#: and an instrument nobody holds look identical, and the pre-existing population is
#: exactly what would make "no row" the normal case and hide a real gap on a new account.
STATE_ABSENT = "absent"
#: The card on file has passed its expiry month. Derived from the record, never written by
#: a person: see :func:`effective_state`.
STATE_EXPIRED = "expired"
#: The card on file was refused the last time it was charged.
STATE_FAILING = "failing"

STATES: tuple[str, ...] = (STATE_PRESENT, STATE_ABSENT, STATE_EXPIRED, STATE_FAILING)

#: What each state means to the PERSON WHOSE CARD IT IS — the client's sentence, which
#: PIM draws. The operator's reading of the same state is the channel's to word.
STATE_SENTENCES: dict[str, str] = {
    STATE_PRESENT: "A card is on file.",
    STATE_ABSENT: "No card is on file.",
    STATE_EXPIRED: "The card on file has expired — add a current one.",
    STATE_FAILING: "The card on file was declined the last time it was charged — check it "
                   "or add another.",
}

#: The trial every new base account starts with (operator, 2026-09-16: "maybe perhaps a
#: free 30 day trial"). A DEFAULT the sequencer passes, not a rule the ledger knows: a
#: trial is a positive credit row whose note names its end, and this is only how long.
DEFAULT_TRIAL_DAYS = 30

#: The recogniser's one shape. ASCII, because the title babelette that carries it in the
#: datum row is fixed-width ASCII and `encode_label_bits` RAISES on anything else — an
#: em-dash or a middle dot here would make the record unwritable, not merely ugly.
_RECOGNISER = re.compile(
    r"^(?P<brand>[A-Za-z][A-Za-z ]{0,23}) ending (?P<last4>[0-9]{4}), "
    r"expires (?P<month>[0-9]{2})/(?P<year>[0-9]{2})$"
)

_SEPARATORS = re.compile(r"[\s-]+")


class CardholderDataRefused(ValueError):
    """A value that looks like a card number was offered to something that stores.

    Raised, never logged: the refusal must not itself write the number anywhere. The
    message names the FIELD and never echoes the value.
    """


class InstrumentRecordError(ValueError):
    """A record that cannot be what it claims — an unknown state, a last-four that is not
    four digits, an expiry month that is not a month."""


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = ord(char) - 48
        if index % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def looks_like_a_pan(text: object) -> bool:
    """Whether ``text`` is shaped like a primary account number.

    13 to 19 digits once spaces and hyphens are removed, in at most FOUR groups, and
    Luhn-valid. The group limit is what keeps every msn address out: a card is written
    ``4242 4242 4242 4242`` or ``4242-4242-4242-4242``, four groups at most, and an msn
    address is ten (``3-2-3-17-77-1-6-51-2-1`` is thirteen digits and would otherwise be
    a candidate). A version hash is hex and a date has slashes; neither reaches Luhn.

    A recogniser is not a PAN and must not read as one, which is why the last four are
    four digits and never more.
    """
    token = str(text or "").strip()
    if not token:
        return False
    groups = [group for group in _SEPARATORS.split(token) if group]
    if not groups or len(groups) > 4:
        return False
    digits = "".join(groups)
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    return _luhn(digits)


def refuse_pan(value: object, *, field: str) -> str:
    """``value`` as text, or :class:`CardholderDataRefused` naming ``field``.

    Every writer on either side of the record/instrument split calls this on every cell it
    is about to store. The exception's message carries the field name and NOT the value —
    a refusal that echoed the number into a log would be a third place it was stored.
    """
    text = "" if value is None else str(value).strip()
    if looks_like_a_pan(text):
        raise CardholderDataRefused(
            f"{field} looks like a card number; a card number is never stored here, "
            "hashed or otherwise — store the processor's vault reference instead")
    return text


def _two_digit_year(year: int) -> int:
    return year if year >= 100 else 2000 + year


@dataclass(frozen=True)
class InstrumentRecord:
    """The RECORD half: what a person may be shown about the card on file.

    Never the number, never a hash of it, never the vault reference. ``arrived_at`` is the
    day the instrument was recorded (a HOPS day in the datum row, ISO here), which is what
    tells two records for one alias apart — the LATEST wins, since the grantee document is
    an append-path document and a replaced card is a new row.
    """

    alias: str
    state: str
    brand: str = ""
    last4: str = ""
    exp_month: int = 0
    exp_year: int = 0
    arrived_at: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise InstrumentRecordError(
                f"unknown instrument state {self.state!r}; expected one of {STATES}")
        refuse_pan(self.alias, field="alias")
        refuse_pan(self.brand, field="brand")
        if self.last4 and not (len(self.last4) == 4 and self.last4.isdigit()):
            raise InstrumentRecordError("last4 must be exactly four digits")
        if self.exp_month and not 1 <= self.exp_month <= 12:
            raise InstrumentRecordError("exp_month must be 1..12")
        if self.exp_year:
            object.__setattr__(self, "exp_year", _two_digit_year(self.exp_year))
        if self.state != STATE_ABSENT and not (self.brand and self.last4):
            raise InstrumentRecordError(
                f"a {self.state} instrument needs a brand and a last four to be recognised by")

    @property
    def recogniser(self) -> str:
        if self.state == STATE_ABSENT:
            return ""
        return recogniser(self.brand, self.last4, self.exp_month, self.exp_year)

    @property
    def sentence(self) -> str:
        return STATE_SENTENCES[self.state]

    def as_dict(self) -> dict[str, object]:
        return {
            "alias": self.alias,
            "state": self.state,
            "brand": self.brand,
            "last4": self.last4,
            "exp_month": self.exp_month,
            "exp_year": self.exp_year,
            "arrived_at": self.arrived_at,
            "recogniser": self.recogniser,
            "sentence": self.sentence,
        }


def recogniser(brand: str, last4: str, exp_month: int, exp_year: int) -> str:
    """``"Visa ending 4242, expires 04/29"`` — the one sentence a card is known by.

    ASCII by construction (see :data:`_RECOGNISER`), at most 64 characters so it fits the
    title babelette, and refused if the pieces are not what they claim to be. It is the
    INVERSE of :func:`parse_recogniser`; the two are held together by a round-trip test
    because the datum row carries only this string.
    """
    brand_text = refuse_pan(brand, field="brand")
    if not brand_text or not brand_text.replace(" ", "").isalpha():
        raise InstrumentRecordError("a recogniser needs a brand made of letters")
    if not (len(str(last4)) == 4 and str(last4).isdigit()):
        raise InstrumentRecordError("a recogniser needs exactly four last digits")
    if not 1 <= int(exp_month) <= 12:
        raise InstrumentRecordError("a recogniser needs an expiry month 1..12")
    year = _two_digit_year(int(exp_year))
    words = " ".join(f"{w[:1].upper()}{w[1:].lower()}" for w in brand_text.split())
    text = f"{words} ending {last4}, expires {int(exp_month):02d}/{year % 100:02d}"
    if not _RECOGNISER.match(text):
        raise InstrumentRecordError("a recogniser could not be formed from these parts")
    return text


def parse_recogniser(text: object) -> tuple[str, str, int, int]:
    """``(brand, last4, exp_month, exp_year)`` from a recogniser, or a refusal."""
    match = _RECOGNISER.match(str(text or "").strip())
    if match is None:
        raise InstrumentRecordError("not a recogniser")
    return (match.group("brand"), match.group("last4"),
            int(match.group("month")), _two_digit_year(int(match.group("year"))))


def is_expired(exp_month: int, exp_year: int, *, today: date) -> bool:
    """A card is good through the LAST day of its expiry month."""
    if not exp_month or not exp_year:
        return False
    return (_two_digit_year(int(exp_year)), int(exp_month)) < (today.year, today.month)


def effective_state(record: InstrumentRecord, *, today: date) -> str:
    """The state a reader should show TODAY.

    ``expired`` is derived, not written: a row that said "present" in April is still the
    same row in May, and the date is what changed. Deriving it here means no routine has to
    sweep the documents on the first of the month, and the stored row stays a fact about
    the day it was written.
    """
    if record.state == STATE_PRESENT and is_expired(
            record.exp_month, record.exp_year, today=today):
        return STATE_EXPIRED
    return record.state


@dataclass(frozen=True)
class TrialWindow:
    started: date
    ends: date
    days_left: int
    active: bool

    def as_dict(self) -> dict[str, object]:
        return {"started": self.started.isoformat(), "ends": self.ends.isoformat(),
                "days_left": self.days_left, "active": self.active}


def trial_window(started: date, *, today: date, days: int = DEFAULT_TRIAL_DAYS) -> TrialWindow:
    """When a trial that began on ``started`` ends, and where ``today`` stands in it.

    ``ends`` is the first day that is NOT in the trial: a 30-day trial started on the 1st
    ends on the 31st, and the 31st is the first day a charge stands. ``days_left`` is
    never negative — a trial that ended is over, not owed.
    """
    if days <= 0:
        raise ValueError("a trial needs a positive number of days")
    ends = started + timedelta(days=days)
    left = (ends - today).days
    return TrialWindow(started=started, ends=ends, days_left=max(left, 0), active=left > 0)


__all__ = [
    "DEFAULT_TRIAL_DAYS",
    "STATES",
    "STATE_ABSENT",
    "STATE_EXPIRED",
    "STATE_FAILING",
    "STATE_PRESENT",
    "STATE_SENTENCES",
    "CardholderDataRefused",
    "InstrumentRecord",
    "InstrumentRecordError",
    "TrialWindow",
    "effective_state",
    "is_expired",
    "looks_like_a_pan",
    "parse_recogniser",
    "recogniser",
    "refuse_pan",
    "trial_window",
]
