"""Request signature verification — the port, not an implementation.

Same split, and for the same reason, as :mod:`micyte.core.crypto.channel`: micyte's
dependency list is ``pyyaml`` + ``shapely``, so the platform declares the SHAPE of
verification and an FND-side peripheral supplies it with ``cryptography``. A lone-laptop
install that never engages a closed channel pays nothing for this.

What it is for: a contract identifies its counterparty by msn id, which is a *name*.
A name is not an identity — anyone can claim one. Binding the name to a key the
contract carries, and requiring a signature over the request, is what makes "this
request is from msn X" a checkable statement rather than a header.

What it deliberately is NOT: a key store, a handshake, or a transport. There is no key
generation, rotation or exchange here — the counterparty's public key arrives in the
contract, out of band, the same way the rest of the contract does.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SignatureVerifierUnavailable(RuntimeError):
    """No verifier is installed.

    Raised rather than returning False, and never falling back to "accept": a caller
    that cannot verify must fail closed and must be able to tell "the signature was
    wrong" apart from "nothing here can check a signature". The same discipline
    ``require_cipher`` applies to encryption.
    """


@runtime_checkable
class RequestVerifier(Protocol):
    """Verifies a detached signature over a canonical request string."""

    #: Names the algorithm, so a signature made under one scheme cannot be checked
    #: under another by accident.
    suite: str

    def verify(self, *, public_key_pem: str, message: bytes, signature: bytes) -> bool:
        """True when ``signature`` is a valid signature of ``message`` by the key.

        Must return False — never raise — for a malformed key, a malformed signature
        or a mismatch. An exception here would be indistinguishable from a server
        fault, and a route cannot tell those apart from the outside either.
        """
        ...


_VERIFIER: RequestVerifier | None = None


def install_verifier(verifier: RequestVerifier) -> None:
    """Register the process-wide verifier. Called by the host at wiring time."""
    global _VERIFIER
    _VERIFIER = verifier


def require_verifier() -> RequestVerifier:
    """The installed verifier, or raise. Never returns a permissive stand-in."""
    if _VERIFIER is None:
        raise SignatureVerifierUnavailable(
            "no request verifier is installed; a signed request cannot be checked, "
            "so it must not be accepted"
        )
    return _VERIFIER
