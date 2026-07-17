"""Bacillete (binary-form) encoders for the FND newsletter contact log.

The system anthology defines two SAMRAS structural slots used by every
operator-mailbox contact list:

* ``name-babelette`` (anthology row ``3-1-4``) — references
  ``niu-baciloid-256-32`` (``2-1-3``), i.e. **32 base-256 digits = 32
  bytes** of pure ASCII. Reserved for human names.
* ``email-babellette`` (anthology row ``3-1-9``) — references
  ``niu-baciloid-8-320`` (``2-1-8``), i.e. **320 base-8 digits**. Each
  ASCII byte fits in 3 octal digits, so the slot holds emails up to
  ⌊320 / 3⌋ = 106 ASCII bytes.

This module provides lossless, deterministic encoders:

* ``encode_name_bacillete(value) -> (hex, confirmed)`` — joins each
  ASCII byte as two hex digits. ``confirmed`` is ``True`` iff the
  value is pure ASCII and ≤ 32 bytes (no truncation).
* ``encode_email_bacillete(value) -> (octal, confirmed)`` — joins each
  ASCII byte as three octal digits. ``confirmed`` is ``True`` iff the
  value is pure ASCII and total octal digits ≤ 320 (i.e., ≤ 106 ASCII
  bytes).

Both encoders are total functions: when ``confirmed`` is False they
still return a best-effort representation so the row remains storable;
the caller decides whether to persist a non-confirmed entry.
"""

from __future__ import annotations

NAME_BABELETTE_BYTE_LIMIT = 32          # niu-baciloid-256-32 (anthology 2-1-3)
EMAIL_BABELLETTE_OCTAL_LIMIT = 320      # niu-baciloid-8-320  (anthology 2-1-8)
EMAIL_BABELLETTE_ASCII_BYTE_LIMIT = EMAIL_BABELLETTE_OCTAL_LIMIT // 3  # 106


def _is_pure_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def encode_name_bacillete(value: str) -> tuple[str, bool]:
    """Encode a human name into the ``name-babelette`` binary form.

    Returns ``(hex_form, confirmed)``. ``confirmed`` is ``True`` iff
    the original value is non-empty, pure ASCII, and fits in 32 bytes.
    Non-ASCII bytes are stripped to maintain a usable hex form, but
    ``confirmed`` is then ``False`` so the caller can flag the row.
    """
    if not value:
        return "", False
    confirmed = _is_pure_ascii(value)
    encoded = value.encode("ascii", errors="ignore")
    if len(encoded) > NAME_BABELETTE_BYTE_LIMIT:
        encoded = encoded[:NAME_BABELETTE_BYTE_LIMIT]
        confirmed = False
    return encoded.hex(), confirmed


def decode_name_bacillete(hex_form: str) -> str:
    """Inverse of :func:`encode_name_bacillete`."""
    if not hex_form:
        return ""
    try:
        return bytes.fromhex(hex_form).decode("ascii", errors="replace")
    except ValueError:
        return ""


def encode_email_bacillete(value: str) -> tuple[str, bool]:
    """Encode an email address into the ``email-babellette`` binary form.

    Returns ``(octal_form, confirmed)``. Each ASCII byte is rendered as
    three zero-padded octal digits (``000`` to ``377``). ``confirmed`` is
    ``True`` iff the original value is non-empty, pure ASCII, and the
    resulting octal string fits in 320 digits (<= 106 ASCII bytes).
    """
    if not value:
        return "", False
    confirmed = _is_pure_ascii(value)
    encoded = value.encode("ascii", errors="ignore")
    if len(encoded) > EMAIL_BABELLETTE_ASCII_BYTE_LIMIT:
        encoded = encoded[:EMAIL_BABELLETTE_ASCII_BYTE_LIMIT]
        confirmed = False
    octal = "".join(f"{b:03o}" for b in encoded)
    return octal, confirmed


def decode_email_bacillete(octal_form: str) -> str:
    """Inverse of :func:`encode_email_bacillete`."""
    if not octal_form:
        return ""
    chunks = [octal_form[i : i + 3] for i in range(0, len(octal_form), 3)]
    bytes_out: list[int] = []
    for chunk in chunks:
        if len(chunk) != 3 or any(ch not in "01234567" for ch in chunk):
            continue
        bytes_out.append(int(chunk, 8))
    return bytes(bytes_out).decode("ascii", errors="replace")


__all__ = [
    "EMAIL_BABELLETTE_ASCII_BYTE_LIMIT",
    "EMAIL_BABELLETTE_OCTAL_LIMIT",
    "NAME_BABELETTE_BYTE_LIMIT",
    "decode_email_bacillete",
    "decode_name_bacillete",
    "encode_email_bacillete",
    "encode_name_bacillete",
]
