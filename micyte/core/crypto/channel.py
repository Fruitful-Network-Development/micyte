"""The channel cipher **port** — a contract, deliberately without an implementation.

Why there is no cipher in this file
-----------------------------------
Two rules meet here and both hold.

**Do not invent a cipher.** An authenticated encrypted channel between instances
is security-critical, and the way to get one is to use a vetted construction
(X25519 key agreement, HKDF, an AEAD such as ChaCha20-Poly1305), not to assemble
primitives by hand. Nothing in this module tries.

**MiCyte's dependency list is a boundary check.** ``pyproject.toml`` names two
third-party dependencies — pyyaml and shapely — and says so on purpose: the
thinness is how the FND-application boundary stays observable. Vendoring
``cryptography`` into the platform to serve an *opt-in* network module would
quietly make every lone-laptop install carry it.

So the platform declares the shape of the thing, and whoever runs the network
module supplies it. FND does, from a package it already depends on. That is not
a compromise: a cipher belongs at the deployment that holds the keys, and a port
is how a domain-agnostic platform says "this is required, and it is not mine to
choose."

What an implementation must provide
-----------------------------------
- **Authenticated encryption.** Confidentiality alone is not enough; a receiver
  must be able to tell that a message came from the counterparty and was not
  altered. Ciphertext that decrypts to *something* under a wrong key must be
  rejected, not returned.
- **Nonce discipline.** A nonce must never repeat under one key. Generate them,
  do not let callers pass them in — this port has no nonce parameter for exactly
  that reason.
- **Forward-ish secrecy at the session level.** Derive a per-channel key from an
  ephemeral agreement rather than encrypting with a long-lived contract secret.

What it must NOT do
-------------------
**Never alter the plaintext.** The plaintext here is a `.mss` envelope, and a
`.mss` is content-addressed — its recorded hashes describe exactly those bytes.
A transport that re-compressed, re-framed or re-ordered anything would break the
correspondence between what was hashed and what arrived, and the receiver's
integrity check would fail for a reason that has nothing to do with the sender.
Encrypt the bytes; return the same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ChannelCipherUnavailable(RuntimeError):
    """No cipher is installed, so the channel cannot carry anything.

    Raised rather than falling back to plaintext. A "degraded" unencrypted mode
    is the failure this exception exists to prevent: it would look like the
    channel working.
    """


@dataclass(frozen=True)
class SealedMessage:
    """Ciphertext plus what a receiver needs to open it.

    ``associated_data`` is authenticated but not encrypted — the channel header
    (who, which contract, which message kind) travels in the clear so a receiver
    can route before it can decrypt, while still being covered by the tag, so
    none of it can be tampered with in transit.
    """

    ciphertext: bytes
    nonce: bytes
    associated_data: bytes = b""
    #: Names the construction actually used (e.g. ``"x25519-hkdf-chacha20poly1305"``).
    #: Recorded so a receiver can refuse a suite it does not implement rather
    #: than guessing, and so a future migration is legible on the wire.
    suite: str = ""


@runtime_checkable
class ChannelCipher(Protocol):
    """Authenticated encryption for one established channel."""

    @property
    def suite(self) -> str:
        """The construction identifier written into every :class:`SealedMessage`."""
        ...

    def seal(self, plaintext: bytes, *, associated_data: bytes = b"") -> SealedMessage:
        """Encrypt and authenticate. Generates its own nonce — see the module docstring."""
        ...

    def open(self, message: SealedMessage) -> bytes:
        """Verify and decrypt, or raise.

        Must raise on any authentication failure. Returning plaintext that failed
        its tag check, or returning ``None``, turns a detected forgery into an
        undetected one.
        """
        ...


@runtime_checkable
class KeyAgreement(Protocol):
    """Establishes the shared secret a :class:`ChannelCipher` is built from."""

    def public_key(self) -> bytes:
        """This instance's public key, as published in the channel handshake."""
        ...

    def cipher_for(self, peer_public_key: bytes, *, context: bytes = b"") -> ChannelCipher:
        """Agree with ``peer_public_key`` and derive a channel cipher.

        ``context`` binds the derived key to the relationship it is for — the
        contract id and both msn ids. Without that binding, a key agreed for one
        contract could be replayed against another.
        """
        ...


def require_cipher(cipher: ChannelCipher | None) -> ChannelCipher:
    """Return ``cipher``, or refuse.

    The single place the "no plaintext fallback" rule is enforced, so a call site
    cannot implement its own more lenient version of it.
    """
    if cipher is None:
        raise ChannelCipherUnavailable(
            "no ChannelCipher is installed — the P2P channel refuses to send in "
            "plaintext. Install an implementation (FND supplies one from the "
            "`cryptography` package) or leave the network module disabled."
        )
    return cipher


__all__ = [
    "ChannelCipher",
    "ChannelCipherUnavailable",
    "KeyAgreement",
    "SealedMessage",
    "require_cipher",
]
