"""KEY PASS — what this instance holds on behalf of an alias, and what may be done with it.

The operator, 2026-08-24:

    "The utilities page should feature a key pass wallet tab. For the most part this will
    only be used for API keys, but also for the FND instance I will use this to see, and
    implement from, for AWS verification info for the FND service module and more
    important for the Grantor Application to charge clients with their provided payment
    information held under the respective docs."

THE RULE, stated without naming a screen:

    A HELD INSTRUMENT is something this instance possesses on behalf of an alias, which
    has a purpose, a state, and a declared reading of what may be done with it.

    ``held_instruments`` returns enough to RECOGNISE one -- which alias, what kind, when
    it arrived, whether it is usable -- and NEVER enough to USE one.

That last sentence is a property of THIS MODULE, not of a renderer. A surface that
receives a secret and chooses not to draw it has already put the secret in a payload, a
log, and a browser's memory. So the secret never leaves here.

## The one deliberate exception, named so it cannot be called by accident

``service_key_for_handover`` DOES return the key in full, because that is what a service
key is FOR: the operator copies it and gives it to the client, who pastes it where their
extension's binding asks. The grantor channel has always shown it
(``grantor.py:_service_key`` -- "the KEY IS SHOWN, exposing a copyable key is the
depiction's point").

Two readings of one file, and the names say which is which. See the memory note
"two denotations or none": the failure is one function serving both, where the caller
that wanted an inventory quietly gets a credential.

## Record vs instrument

The operator's phrase "held under the respective docs" reads like a collision with the
rule that credentials never enter MOS. It is not one:

    the RECORD     -- which services an alias opted into, and their state
                   -- MOS, ``grantor.grantee-<msn>`` documents
    the INSTRUMENT -- the PayPal client_secret, the SES config, the service key
                   -- instance FILES, 0600, never MOS

This module reads instruments only. Joining them to the record is the surface's job, and
joining is not moving: ``fnd_app/docs/contracts/instance_payment_storage.md`` stays true.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The three families an instance can hold. Keys are universal; the other two exist only
#: where the operator's own trees do, which is why a client instance shows keys and
#: nothing else without any permission rule being involved.
KEYPASS_FAMILIES: tuple[str, ...] = (
    "service_key",
    "aws_verification",
    "payment_instrument",
    # What FND charges an alias WITH — the processor's vault reference for the card the
    # client put on file at signup (TASK-2026-09-16-001). A fourth family rather than a
    # reading of the third: `payment_instrument` below is the client's own MERCHANT
    # credential, the account their site takes money INTO, and the two point opposite
    # ways. One family for both would let "this alias can be charged" mean "this alias
    # can take payment", which was in fact what the third family's purpose string said
    # until 2026-09-16.
    "charging_instrument",
)

STATE_PRESENT = "present"
STATE_ABSENT = "absent"
STATE_UNVERIFIED = "unverified"
STATE_ERROR = "error"

_KEY_DIRNAME = ("utilities", "tools", "fnd_service", "keys")
_AWS_DIRNAME = ("utilities", "tools", "aws-csm")
#: Where `fnd_app...grantor_instruments` keeps the vault reference FND charges an alias
#: with. Spelled here as well because this module reads it and imports nothing that
#: could tell it; `test_key_pass_wallet` holds the two spellings together.
_CHARGING_DIRNAME = ("utilities", "tools", "grantor", "instruments")


@dataclass(frozen=True)
class HeldInstrument:
    """One thing this instance holds for one alias.

    ``fingerprint`` is a RECOGNISER and never a value. Enough to tell two apart in a
    list; never enough to reconstruct one. What that means differs per family and each
    builder below says so at the point it decides.
    """

    family: str
    alias: str
    purpose: str
    state: str
    fingerprint: str = ""
    arrived_at: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "alias": self.alias,
            "purpose": self.purpose,
            "state": self.state,
            "fingerprint": self.fingerprint,
            "arrived_at": self.arrived_at,
            "note": self.note,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load(path: Path) -> tuple[dict[str, Any] | None, str]:
    """``(record, error)``. An unreadable file is a row in state=error, never a skip.

    A swallowed row reads as "this alias holds nothing", which is the same shape as an
    alias who genuinely holds nothing -- and the operator cannot tell them apart. Say
    which.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"{type(exc).__name__}"
    if not isinstance(loaded, dict):
        return None, "not a JSON object"
    return loaded, ""


def _service_keys(private_dir: Path) -> list[HeldInstrument]:
    folder = private_dir.joinpath(*_KEY_DIRNAME)
    if not folder.is_dir():
        # NOT an error. On the live host this directory does not exist, because no
        # service key has ever been minted -- so "no keys" is the honest answer and the
        # surface must say "none minted" rather than look broken.
        return []
    out: list[HeldInstrument] = []
    for path in sorted(folder.glob("*.json")):
        alias = path.stem
        record, error = _load(path)
        if record is None:
            out.append(HeldInstrument(
                family="service_key", alias=alias,
                purpose="Enables an FND port on this alias's own instance.",
                state=STATE_ERROR,
                note=f"The key file could not be read ({error}).",
            ))
            continue
        key = _text(record.get("key"))
        out.append(HeldInstrument(
            family="service_key",
            alias=_text(record.get("grantee_msn_id")) or alias,
            purpose="Enables an FND port on this alias's own instance.",
            state=STATE_PRESENT if key else STATE_ABSENT,
            # Last four plus the mint date. The operator has to tell two apart when
            # handing one over; four characters of a 48-hex token does that and
            # reconstructs nothing. The full key is service_key_for_handover's job.
            fingerprint=f"…{key[-4:]}" if len(key) >= 4 else "",
            arrived_at=_text(record.get("minted_at")),
            note="" if key else "The record carries no key.",
        ))
    return out


def _aws_verifications(private_dir: Path) -> list[HeldInstrument]:
    folder = private_dir.joinpath(*_AWS_DIRNAME)
    if not folder.is_dir():
        return []
    out: list[HeldInstrument] = []
    for path in sorted(folder.glob("aws-csm.*.json")):
        record, error = _load(path)
        if record is None:
            out.append(HeldInstrument(
                family="aws_verification", alias=path.stem,
                purpose="AWS SES identity backing the FND service module.",
                state=STATE_ERROR, note=f"Unreadable ({error}).",
            ))
            continue
        identity = record.get("identity")
        identity = identity if isinstance(identity, dict) else {}
        workflow = record.get("workflow")
        workflow = workflow if isinstance(workflow, dict) else {}
        lifecycle = _text(workflow.get("lifecycle_state"))
        out.append(HeldInstrument(
            family="aws_verification",
            alias=_text(identity.get("tenant_id")) or path.stem,
            purpose="AWS SES identity backing the FND service module.",
            # "operational" is the only state that means the identity is usable. Every
            # other value is a stage on the way there, and calling it present would let
            # a half-onboarded identity read as ready.
            state=STATE_PRESENT if lifecycle == "operational" else STATE_UNVERIFIED,
            # The identity itself, which is a public fact -- it is the address mail
            # arrives at. Not a secret, and the operator needs to see WHICH one.
            fingerprint=_text(identity.get("send_as_email"))
            or _text(identity.get("domain")),
            arrived_at=_text(workflow.get("onboarded_at")),
            note=lifecycle or "no lifecycle state recorded",
        ))
    return out


def _payment_instruments(grantee_root: Path | None) -> list[HeldInstrument]:
    """Vendor, environment, and WHETHER a secret is present. Never a fingerprint of one.

    A service key gets last-four because the operator hands it over and has to tell two
    apart by eye. A payment secret is never told apart by eye, so there is nothing four
    characters of it would buy that "a secret is on file" does not.
    """
    if grantee_root is None:
        return []
    folder = Path(grantee_root) / "secrets"
    if not folder.is_dir():
        return []
    out: list[HeldInstrument] = []
    for path in sorted(folder.glob("grantee.*.secrets.yaml")):
        alias = path.name.split(".")[1] if path.name.count(".") >= 2 else path.stem
        try:
            import yaml

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            out.append(HeldInstrument(
                family="payment_instrument", alias=alias,
                purpose="The PayPal merchant account this alias's own site takes payment through.",
                state=STATE_ERROR, note=f"Unreadable ({type(exc).__name__}).",
            ))
            continue
        loaded = loaded if isinstance(loaded, dict) else {}
        paypal = loaded.get("paypal")
        paypal = paypal if isinstance(paypal, dict) else {}
        if not paypal:
            continue
        has_secret = bool(_text(paypal.get("client_secret")))
        environment = _text(paypal.get("environment")) or _text(paypal.get("mode"))
        out.append(HeldInstrument(
            family="payment_instrument",
            alias=alias,
            # CORRECTED 2026-09-16. This read "What the Grantor Application charges
            # against" from the day the wallet was built, and the file it reads is the
            # client's PayPal MERCHANT secret -- the account their own site takes
            # donations into. Grantor charges nobody through it. The instrument grantor
            # charges WITH is the `charging_instrument` family below.
            purpose="The PayPal merchant account this alias's own site takes payment through.",
            state=STATE_PRESENT if has_secret else STATE_ABSENT,
            fingerprint=f"PayPal · {environment}" if environment else "PayPal",
            # STATE, never a diagnosis. `cvcc` carries an environment and a webhook
            # URL with no credentials, and that is DELIBERATE -- its donate page was
            # built as the on-site REST experience and left un-wired at the operator's
            # instruction. A wallet that called this a fault would be reporting a
            # working configuration as broken.
            note="Credentials on file; this alias can be charged." if has_secret
            else "No credentials on file; this alias cannot be charged yet.",
        ))
    return out


def _charging_instruments(private_dir: Path) -> list[HeldInstrument]:
    """The vault reference FND charges an alias with: WHICH processor, WHICH environment,
    and whether a reference is on file. Never the reference.

    A vault reference is opaque and the client never sees it, so — like the merchant
    secret above and unlike a service key — nothing four characters of it would buy. The
    recogniser a person knows the card BY (brand, last four, expiry) is not held here
    at all: it is the RECORD, in the grantee's datum document, read by the surfaces that
    draw it. This file holds only what a charge needs, and this reader reports only that
    it is there.
    """
    folder = private_dir.joinpath(*_CHARGING_DIRNAME)
    if not folder.is_dir():
        # NOT an error: no client has put a card on file yet, and on the live host that
        # is every client. "none on file" must not look like a broken page.
        return []
    out: list[HeldInstrument] = []
    for path in sorted(folder.glob("*.json")):
        alias = path.stem
        record, error = _load(path)
        if record is None:
            out.append(HeldInstrument(
                family="charging_instrument", alias=alias,
                purpose="What FND charges this alias with.",
                state=STATE_ERROR, note=f"The instrument file could not be read ({error}).",
            ))
            continue
        reference = _text(record.get("vault_ref"))
        processor = _text(record.get("processor"))
        environment = _text(record.get("environment"))
        out.append(HeldInstrument(
            family="charging_instrument",
            alias=_text(record.get("grantee_msn_id")) or alias,
            purpose="What FND charges this alias with.",
            state=STATE_PRESENT if reference else STATE_ABSENT,
            # The processor and the environment, which are the two facts an operator
            # needs to tell a sandbox instrument from a live one. Not a character of
            # the reference.
            fingerprint=" \u00b7 ".join(part for part in (processor, environment) if part),
            arrived_at=_text(record.get("added_at")),
            note="A vault reference is on file; this alias can be charged." if reference
            else "No vault reference on file; this alias cannot be charged.",
        ))
    return out


def held_instruments(
    private_dir: Path | str | None,
    *,
    grantee_root: Path | str | None = None,
) -> tuple[HeldInstrument, ...]:
    """Everything this instance holds, as recognisers.

    ``grantee_root`` is optional and separate because it is an ENV-configured tree
    (``MYCITE_GRANTEE_ROOT``) that only the operator's instance has. Passing it is the
    caller's decision; this module does not read the environment, so it cannot quietly
    reach a tree its caller did not name.

    Returns ``()`` for an unreadable tree. An instance whose private directory cannot be
    resolved holds an UNKNOWN number of instruments, not zero -- but the surface's job
    then is to say the tree is unreadable, which it can tell from the config it already
    has. Returning a fabricated empty inventory here would be the worse lie.
    """
    if private_dir is None:
        return ()
    root = Path(private_dir)
    if not root.is_dir():
        return ()
    found: list[HeldInstrument] = []
    found.extend(_service_keys(root))
    found.extend(_aws_verifications(root))
    found.extend(_payment_instruments(
        Path(grantee_root) if grantee_root is not None else None))
    found.extend(_charging_instruments(root))
    return tuple(found)


def instruments_by_family(
    instruments: tuple[HeldInstrument, ...],
) -> dict[str, list[HeldInstrument]]:
    """Grouped, with EVERY family present even when empty.

    An absent family and an empty one look identical to a renderer that only iterates
    what it was given, and they mean different things: "this instance holds no keys" is
    a fact worth drawing, and it is currently the true one on the live host.
    """
    grouped: dict[str, list[HeldInstrument]] = {name: [] for name in KEYPASS_FAMILIES}
    for held in instruments:
        grouped.setdefault(held.family, []).append(held)
    return grouped


def service_key_for_handover(
    private_dir: Path | str | None, *, alias_msn: str
) -> dict[str, Any]:
    """THE FULL KEY. The one function here that returns a secret, named so that calling
    it is a decision rather than an accident.

    This is what a service key is for: the operator copies it and gives it to the client,
    who pastes it where their extension's binding asks. ``grantor.py`` has always done
    this and continues to; the wallet does NOT call this.

    Returns the same shape grantor's ``_service_key`` has always returned, so the channel
    payload is unchanged by moving the read here.
    """
    if private_dir is None:
        return {"present": False, "note": "No private directory configured."}
    path = Path(private_dir).joinpath(*_KEY_DIRNAME) / f"{alias_msn}.json"
    if not path.is_file():
        return {"present": False, "note": "No service key minted for this alias yet."}
    record, _error = _load(path)
    if record is None:
        return {"present": False, "note": "The key file could not be read."}
    return {
        "present": True,
        "key": _text(record.get("key")),
        "minted_at": _text(record.get("minted_at")),
        "note": "Copy this key into the FND email extension's binding to enable the "
                "port. Every port works this way: add the extension, enable it with "
                "a key.",
    }
