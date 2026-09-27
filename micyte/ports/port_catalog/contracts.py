"""Which port TYPES exist, so that naming one can be wrong.

``micyte/ports/`` has held the port contracts since the beginning, but nothing held the
LIST of them. ``PortDeclaration.port_id`` and ``PortBinding.port_id`` were free strings:
a typo bound a port that does not exist, refused nothing, and rendered on the Ports
surface as a row an operator could not act on. There was also nothing to render "the
ports this instance could have" from — only the ones somebody had already filled.

The operator's model, which this completes:

    a port TYPE is a contract           -- this module's register
    an EXTENSION fills one, if eligible -- micyte.ports.tool_package.PortFill
    a BINDING is this instance's choice -- micyte.ports.port_binding.PortBinding
    a GRANT says whether it may         -- micyte.ports.external_call_policy

Declared, not derived
---------------------
:data:`PORT_TYPES` is written down, the way ``micyte.tools._packages.catalogue()`` is
written down and for the same reason. Deriving it by walking ``micyte/ports/*`` would put
``datum_write_policy`` and ``port_binding`` in a list of things an operator can bind an
adapter to, which is not what they are: those are the policies the binding is judged BY.

The two kinds are told apart here rather than by a filter, so the split is a fact in the
source. :data:`NOT_BINDABLE` names every port module that is deliberately absent, and
``test_port_catalog`` asserts the two sets together cover ``micyte/ports/`` exactly. A new
port module therefore cannot be quietly missing from both — the egress sweep's rule
(*never exclude silently*), applied to a register instead of to a call site.

The operations come FROM the contracts
--------------------------------------
Every ``operations`` tuple below is imported, never spelled. An operation grain restated
here would be a second statement of what the port already says, free to drift from it —
the ``JOB_LOG`` rule. The test pins that: it compares each entry against the module's own
``OPERATION_*`` exports.

Some ports name no operation of their own, and that is a real distinction rather than an
omission. ``commerce_offering``'s egress grain belongs to whatever payment vendor fills it
(``paypal:order.capture``), which is why ``brevat`` declares vendor ``calls`` while
``oveure`` declares port ``operations``. Such a port carries ``operations=()`` and a fill
for it may name the vendor's operations; :class:`PortType.names_its_operations` is the
question a validator asks instead of guessing from emptiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: A port whose operations move something OUT of this instance, to someone else's service.
DIRECTION_OUTBOUND = "outbound"
#: A port that brings something IN — a provider's events, a stranger's order.
DIRECTION_INBOUND = "inbound"
#: A port used in both directions. Email is the worked example: reading a mailbox and
#: answering from it are one seam, and splitting them into two ports would make an
#: operator bind twice to hold one conversation.
DIRECTION_BOTH = "both"

DIRECTIONS: tuple[str, ...] = (DIRECTION_OUTBOUND, DIRECTION_INBOUND, DIRECTION_BOTH)


class UnknownPortType(ValueError):
    """A port id nothing in this register answers to.

    Raised rather than tolerated: a declaration or binding naming a port that does not
    exist would sit on the Ports surface looking configured, and the operator's only
    signal would be that nothing ever happens.
    """


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class PortType:
    """One seam an instance can have an extension fill.

    ``operations`` is the withholdable grain — what a grant is written against — and it
    is the port's own vocabulary, imported from the contract module. ``why`` is required
    for the same reason ``SourceRequirement.why`` is: this register is rendered to an
    operator choosing what to connect, and a row nobody can explain is a row nobody can
    decide about.
    """

    port_id: str
    label: str
    why: str
    direction: str
    operations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("port_id", "label", "why", "direction"):
            token = _as_text(getattr(self, name))
            if not token:
                raise ValueError(f"port_type.{name} is required")
            object.__setattr__(self, name, token)
        if self.direction not in DIRECTIONS:
            raise ValueError(
                f"unknown port direction {self.direction!r}; expected one of {DIRECTIONS}"
            )
        operations = tuple(
            token for token in (_as_text(op) for op in (self.operations or ())) if token
        )
        if len(set(operations)) != len(operations):
            raise ValueError(f"port_type {self.port_id!r} names an operation twice")
        object.__setattr__(self, "operations", operations)

    @property
    def names_its_operations(self) -> bool:
        """True when a grant over this port is written in the PORT's vocabulary.

        False means the grain belongs to whichever vendor fills it, so a fill may name
        operations this register has never heard of. Asked explicitly so a validator
        never has to read an empty tuple as "anything goes" — the reading that makes a
        misconfigured port and a permissive one the same value.
        """
        return bool(self.operations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "label": self.label,
            "why": self.why,
            "direction": self.direction,
            "operations": list(self.operations),
        }


def _bindable() -> tuple[PortType, ...]:
    """Built at call time so the imports below stay local to the register."""
    from micyte.ports.ai_provider import OPERATION_MESSAGES_CREATE
    from micyte.ports.email_provider import (
        OPERATION_ALIAS_CREATE,
        OPERATION_ALIAS_LIST,
        OPERATION_ALIAS_REMOVE,
        OPERATION_FORWARDING_SET,
        OPERATION_IDENTITY_REMIND,
        OPERATION_IDENTITY_VERIFY_REQUEST,
        OPERATION_MAILBOX_LIST,
        OPERATION_MESSAGE_FETCH,
        OPERATION_MESSAGE_FORWARD,
    )
    from micyte.ports.email_provider import (
        OPERATION_MESSAGE_SEND as EMAIL_MESSAGE_SEND,
    )
    from micyte.ports.payment_instrument import (
        OPERATION_INSTRUMENT_CHARGE,
        OPERATION_INSTRUMENT_DESCRIBE,
        OPERATION_INSTRUMENT_DETACH,
        OPERATION_INSTRUMENT_VAULT,
    )
    from micyte.ports.site_hosting import (
        OPERATION_ANALYTICS_READ,
        OPERATION_ARTICLE_PUBLISH,
        OPERATION_ARTICLE_RETIRE,
        OPERATION_ARTICLE_SEND,
        OPERATION_ASSET_SWAP,
        OPERATION_ASSET_UPLOAD,
        OPERATION_CONTENT_REPLACE,
        OPERATION_PAGE_LIST,
        OPERATION_PROFILE_EDIT,
        OPERATION_PROJECT_EXPORT,
    )
    from micyte.ports.sms_provider import (
        OPERATION_MESSAGE_SEND as SMS_MESSAGE_SEND,
    )

    return (
        PortType(
            port_id="email_provider",
            label="Email",
            why=(
                "Read the mail an instance receives, answer it from the same address, "
                "and administer the addresses themselves — which exist, where each "
                "forwards, and whether its owner has confirmed they may send as it. "
                "One seam: reading and replying are one conversation, and the mailbox "
                "that conversation happens in is the same relationship."
            ),
            direction=DIRECTION_BOTH,
            operations=(
                # the MAIL
                OPERATION_MAILBOX_LIST,
                OPERATION_MESSAGE_FETCH,
                EMAIL_MESSAGE_SEND,
                OPERATION_MESSAGE_FORWARD,
                # the MAILBOXES — administration. Declared 2026-08-28: the capability was
                # live behind a session guard with no port in front, so none of it could
                # be granted or withheld and PIM had nothing to call.
                OPERATION_ALIAS_LIST,
                OPERATION_ALIAS_CREATE,
                OPERATION_ALIAS_REMOVE,
                OPERATION_FORWARDING_SET,
                OPERATION_IDENTITY_VERIFY_REQUEST,
                OPERATION_IDENTITY_REMIND,
            ),
        ),
        PortType(
            port_id="sms_provider",
            label="Text messaging",
            why=(
                "Send a text message on the instance's behalf. Declared before "
                "anything fills it, so the seam is visible rather than arriving with "
                "its first use."
            ),
            direction=DIRECTION_OUTBOUND,
            operations=(SMS_MESSAGE_SEND,),
        ),
        PortType(
            port_id="ai_provider",
            label="AI provider",
            why=(
                "Send text to a hosted model and read the reply. What it discloses is "
                "the text itself, which is why it is governed like a vendor."
            ),
            direction=DIRECTION_OUTBOUND,
            operations=(OPERATION_MESSAGES_CREATE,),
        ),
        PortType(
            port_id="site_hosting",
            label="Site hosting",
            why=(
                "Edit a grantee's public site, and read what it was visited by: which "
                "pages exist, one {old, new} replacement in the source, a picture "
                "pointed at another the site already has, a new asset at "
                "a public URL, a written piece published, sent to the people who subscribed, "
                "or retired, and the monthly "
                "traffic totals. The one write path in this stack that had "
                "no port in front of it, so nothing about it could be granted separately "
                "or shown on this surface."
            ),
            direction=DIRECTION_BOTH,
            operations=(
                OPERATION_PAGE_LIST,
                OPERATION_CONTENT_REPLACE,
                # Pointing a picture at a different file the site already has. Its own
                # operation because its fence is its own — the target must be in the
                # site's gallery, where a content replacement could point an <img>
                # anywhere — so an operator can grant the fenced act and withhold the
                # unfenced one.
                OPERATION_ASSET_SWAP,
                OPERATION_ASSET_UPLOAD,
                OPERATION_ARTICLE_PUBLISH,
                OPERATION_ARTICLE_RETIRE,
                # Mailing the list is not publishing the page. A publish can be taken
                # back down; a send cannot be taken back, so it is granted apart from
                # everything else this port does (2026-09-13).
                OPERATION_ARTICLE_SEND,
                # The only READ here that discloses nothing a visitor did not already do
                # on the site, and the only one an unattended routine performs. Separate
                # so it can be granted to a nightly refresh while the four writes above
                # stay withheld.
                OPERATION_ANALYTICS_READ,
                # Rewriting a PROFILE the pages are generated from — feature image,
                # photograph order and hiding, short and long description — and rebuilding
                # them. Its own operation because it edits a source of record several
                # pages draw on and can withhold a photograph, which is neither one string
                # on one page nor one <img> pointed at another file.
                OPERATION_PROFILE_EDIT,
                # A project DOCUMENT's view written beside the site and the profile
                # derived from it (2026-09-11): the books are the source, the leaflet
                # a copy; lands files and rewrites a profile in one act.
                OPERATION_PROJECT_EXPORT,
            ),
        ),
        PortType(
            port_id="commerce_offering",
            label="Commerce offering",
            why=(
                "Publish what is for sale and quote what may actually be sold. Its "
                "outbound grain belongs to the payment vendor that fills it, so this "
                "port names none of its own."
            ),
            direction=DIRECTION_BOTH,
        ),
        PortType(
            port_id="payment_instrument",
            label="Payment instrument",
            why=(
                "Charge a client's card on file for what they pay FND — the hosting "
                "relationship's other side from commerce_offering. The card is entered "
                "into fields the processor hosts and only an opaque vault reference "
                "comes back, so no operation here takes or returns a card number. "
                "Declared with no fill bound (2026-09-16): nothing on this build can "
                "move money until an operator binds one."
            ),
            direction=DIRECTION_OUTBOUND,
            operations=(
                # A signup's one act: the hosted fields' setup token becomes an
                # instrument on file.
                OPERATION_INSTRUMENT_VAULT,
                # Brand, last four, expiry for a reference already held — the read a
                # surface needs to DRAW the card, and nothing more.
                OPERATION_INSTRUMENT_DESCRIBE,
                # The one that moves money. Withheld from everything but the billing
                # routine; a grant here is a grant to spend somebody's money.
                OPERATION_INSTRUMENT_CHARGE,
                # The client's right to take the card back, and the act that makes
                # CHARGE impossible afterwards — its own grant for both reasons.
                OPERATION_INSTRUMENT_DETACH,
            ),
        ),
    )


#: Every port module in ``micyte/ports/`` that is NOT a bindable port type, and why.
#:
#: Named rather than filtered. These are the policies, stores and read models a binding is
#: judged BY or built FROM; offering an operator an adapter to fill ``datum_write_policy``
#: with would be offering to replace the gate. ``test_port_catalog`` asserts this set plus
#: :data:`PORT_TYPES` covers the directory exactly, so a NEW port module fails the suite
#: until somebody decides which it is.
NOT_BINDABLE: dict[str, str] = {
    "audit_log": "a record this instance keeps of itself, not a service it reaches",
    "aws_narrow_write": "an admin band, bound by the operator console rather than selected per instance",
    "aws_read_only_status": "an admin band, as above",
    "datum_store": "where this instance's own documents live; the store is composed at boot",
    "datum_write_policy": "the gate a binding is judged BY",
    "directive_context": "an inward read model of the instance's own state",
    "external_call_policy": "the gate a binding is judged BY",
    "network_root_read_model": "an inward read model of the instance's own state",
    "port_binding": "what a filled port IS; it cannot itself be filled",
    "port_catalog": "this register",
    "portal_authority": "the shell's own authority, composed at boot",
    "tool_package": "what an installable package IS; the marketplace's own contract",
}


def port_types() -> tuple[PortType, ...]:
    """Every port type an instance can have an extension fill, in display order."""
    return _bindable()


def port_type(port_id: object) -> PortType:
    """The port type ``port_id`` names. Raises :class:`UnknownPortType` otherwise."""
    token = _as_text(port_id)
    if not token:
        raise UnknownPortType("a port id is required")
    for entry in port_types():
        if entry.port_id == token:
            return entry
    known = ", ".join(sorted(entry.port_id for entry in port_types()))
    raise UnknownPortType(
        f"{token!r} is not a port type on this build. Known ports: {known}"
    )


def is_port_type(port_id: object) -> bool:
    """Whether ``port_id`` names a bindable port. For surfaces, never for validation."""
    try:
        port_type(port_id)
    except UnknownPortType:
        return False
    return True


__all__ = [
    "DIRECTIONS",
    "DIRECTION_BOTH",
    "DIRECTION_INBOUND",
    "DIRECTION_OUTBOUND",
    "NOT_BINDABLE",
    "PortType",
    "UnknownPortType",
    "is_port_type",
    "port_type",
    "port_types",
]
