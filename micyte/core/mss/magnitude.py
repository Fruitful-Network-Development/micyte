"""Injective token ↔ magnitude codec — the piece that makes MSS a *transport*.

Background
----------
MSS was written as a **hash** representation: a document's identity is the sha256
of its bitstream, and for comparing digests it never mattered that the projection
``token → int`` threw information away. The moment MSS becomes the form a datum
document is *carried* in — to a website, to another instance, over a P2P channel —
losing information stops being tolerable, because the far side has to reconstruct
the token, not just compare a digest.

The old projection (``document_adapter._coerce_magnitude``) was not injective, and
measurably so. An 8-bit-aligned ``0``/``1`` string — the corpus's encoding for
display text — satisfies ``str.isdigit()``, so it took the *decimal* branch and its
**leading zero was destroyed**, shifting every subsequent bit. Measured over the
live ``fnd`` registrar documents: **2,297 of 8,003 head values (28.7%)
unrecoverable**, 327 more ambiguous, and every one of the 2,276 losses in
``registrar.administrative`` a region label. Three further collisions were latent
in the same function:

- ``True`` and ``1`` both became ``1`` — a bool could not be told from an int;
- ``"7"`` and ``7`` both became ``7`` — a numeric string could not be told from an
  int, so ``"007"`` came back as ``7``;
- ``"-5"`` reached ``_g_encode``, which **raises** on negatives — a latent crash,
  not a loss, but reachable from ordinary data.

The fix
-------
Emit a **(kind, magnitude)** pair instead of a bare magnitude. Both halves are
non-negative integers, so both are gamma-codable and the wire cost is one extra
gamma int per tuple. The kind is the discriminator that makes the inverse exact:

===============  =====================================================
kind             magnitude
===============  =====================================================
``MAG_INT``      zigzag(value) — signed-safe, so ``-5`` is representable
``MAG_TEXT``     ``int.from_bytes(b"\\x01" + utf8, "big")``
``MAG_BOOL``     ``0`` / ``1``
===============  =====================================================

The ``\\x01`` sentinel on the text branch is load-bearing: without it a token
whose UTF-8 begins with a zero byte would lose that byte to big-endian
normalization, and the empty string would be indistinguishable from absent. With
it, ``""`` encodes as ``1`` and every text token has an exact inverse. (This is
the same sentinel trick the micyte.com offering exporter already uses for its
text magnitudes — generalized here and made the rule.)

The property this module exists to guarantee, asserted over the whole live corpus
in ``fnd_app/tests/unit/test_mss_envelope.py`` (``MagnitudeInjectivityTest``)::

    decode_magnitude(*encode_magnitude(token)) == token

Note that the shape a token *looks* like is no longer consulted. A bit-string is
just text; a numeric string is just text. Nothing in the codec has to guess what a
token meant, which is exactly why the guessing can no longer be wrong.
"""

from __future__ import annotations

from typing import Any

#: Discriminator values. These are wire constants — appending is safe, renumbering
#: is a format break.
MAG_INT = 0
MAG_TEXT = 1
MAG_BOOL = 2

#: Prepended to a text token's UTF-8 before the big-endian integer conversion, so
#: that leading zero bytes survive and ``""`` is distinguishable from absent.
_TEXT_SENTINEL = 0x01


class MagnitudeError(ValueError):
    """A token cannot be encoded, or a (kind, magnitude) pair cannot be decoded."""


def _zigzag_encode(value: int) -> int:
    """Map the integers onto the naturals so negatives survive a gamma code.

    ``_g_encode`` refuses a negative value, and the old projection handed it one
    for any token like ``"-5"`` — a latent crash reachable from ordinary data.
    """
    return value * 2 if value >= 0 else -value * 2 - 1


def _zigzag_decode(value: int) -> int:
    if value < 0:
        raise MagnitudeError("zigzag magnitude cannot be negative")
    return value // 2 if value % 2 == 0 else -((value + 1) // 2)


def encode_magnitude(token: Any) -> tuple[int, int] | None:
    """``token`` → ``(kind, magnitude)``, or ``None`` if it is not encodable.

    ``None`` means *this token has no magnitude form* (e.g. a nested list) — the
    caller counts it as malformed. It never means "encoded lossily".
    """
    if isinstance(token, bool):
        # Must precede the int branch: bool IS an int in Python, and collapsing
        # the two is one of the losses this module exists to remove.
        return MAG_BOOL, 1 if token else 0
    if isinstance(token, int):
        return MAG_INT, _zigzag_encode(token)
    if isinstance(token, str):
        return MAG_TEXT, int.from_bytes(bytes([_TEXT_SENTINEL]) + token.encode("utf-8"), "big")
    return None


def decode_magnitude(kind: int, magnitude: int) -> Any:
    """``(kind, magnitude)`` → the original token. Inverse of :func:`encode_magnitude`."""
    if magnitude < 0:
        raise MagnitudeError("magnitude cannot be negative")
    if kind == MAG_BOOL:
        if magnitude not in (0, 1):
            raise MagnitudeError(f"bool magnitude must be 0 or 1, got {magnitude}")
        return magnitude == 1
    if kind == MAG_INT:
        return _zigzag_decode(magnitude)
    if kind == MAG_TEXT:
        if magnitude == 0:
            raise MagnitudeError("text magnitude is missing its sentinel byte")
        width = (magnitude.bit_length() + 7) // 8
        body = magnitude.to_bytes(width, "big")
        if body[0] != _TEXT_SENTINEL:
            raise MagnitudeError("text magnitude has a corrupt sentinel byte")
        try:
            return body[1:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MagnitudeError(f"text magnitude is not utf-8: {exc}") from exc
    raise MagnitudeError(f"unknown magnitude kind: {kind}")


def encode_text(token: str) -> int:
    """A standalone text token as a single non-negative integer.

    Used for fields that are always text and therefore need no discriminator —
    the datum ``title`` slot, where ``0`` is reserved to mean *absent* and any
    value ``≥ 1`` decodes to a (possibly empty) string.
    """
    return int.from_bytes(bytes([_TEXT_SENTINEL]) + token.encode("utf-8"), "big")


def decode_text(code: int) -> str:
    """Inverse of :func:`encode_text`. ``0`` is not a valid code (it means absent)."""
    return str(decode_magnitude(MAG_TEXT, code))


__all__ = [
    "MAG_BOOL",
    "MAG_INT",
    "MAG_TEXT",
    "MagnitudeError",
    "decode_magnitude",
    "decode_text",
    "encode_magnitude",
    "encode_text",
]
