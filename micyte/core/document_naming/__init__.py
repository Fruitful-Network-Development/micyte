"""Canonical MOS datum-document naming.

Pure-stdlib helpers for parsing, formatting, and validating canonical
``lv./stl./cptr.`` document identifiers per
``docs/contracts/datum_document_naming_taxonomy.md``.

This module is the single point of validation for canonical document IDs.
SQL adapters call into ``parse_canonical_document_id`` (raises) or
``is_canonical_document_id`` (boolean) before persisting, and the migration
script uses ``derive_canonical_id_from_legacy`` to convert pre-canonical
``system:<file>`` / ``sandbox:<tool>:<filename>.json`` identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_PREFIXES = ("lv", "stl", "cptr")

_LV_RE = re.compile(r"^lv\.([^.]+)\.([^.]+)\.([^.]+)\.([a-f0-9]{64})$")
_STL_OR_CPTR_RE = re.compile(r"^(stl|cptr)\.([^.]+)\.([^.]+)\.([a-f0-9]{64})$")

_LEGACY_SYSTEM_RE = re.compile(r"^system:([A-Za-z0-9_\-]+)$")
_LEGACY_SANDBOX_RE = re.compile(
    r"^sandbox:([A-Za-z0-9_\-]+):([A-Za-z0-9_\-./]+)\.json$"
)
_LEGACY_PAYLOAD_RE = re.compile(r"^payload:([A-Za-z0-9_\-]+)\.bin$")
_LEGACY_CACHE_RE = re.compile(r"^cache:([A-Za-z0-9_\-]+)\.json$")

_HEX_RE = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class ParsedDocumentId:
    """Parsed components of a canonical document id."""

    prefix: str
    msn_id: str
    sandbox: str | None
    name: str
    version_hash: str

    @property
    def document_id(self) -> str:
        return format_canonical_document_id(
            prefix=self.prefix,
            msn_id=self.msn_id,
            sandbox=self.sandbox,
            name=self.name,
            version_hash=self.version_hash,
        )


class CanonicalNameError(ValueError):
    """Raised when a document id violates the canonical naming contract."""


def _strip_sha256_prefix(value: str) -> str:
    if value.startswith("sha256:"):
        return value[len("sha256:"):]
    return value


def format_canonical_document_id(
    *,
    prefix: str,
    msn_id: str,
    sandbox: str | None,
    name: str,
    version_hash: str,
) -> str:
    """Compose a canonical document id from its parts.

    ``sandbox`` must be supplied for ``lv.`` and absent (``None``/empty) for
    ``stl.`` and ``cptr.``. ``version_hash`` is the 64-char lowercase hex
    SHA-256 over the document MSS form (with or without ``sha256:`` prefix).
    """

    if prefix not in ALLOWED_PREFIXES:
        raise CanonicalNameError(f"prefix must be one of {ALLOWED_PREFIXES}: {prefix!r}")
    msn_clean = (msn_id or "").strip()
    if not msn_clean or "." in msn_clean:
        raise CanonicalNameError(f"invalid msn_id: {msn_id!r}")
    name_clean = (name or "").strip()
    if not name_clean or "." in name_clean:
        raise CanonicalNameError(f"invalid name: {name!r}")
    hash_clean = _strip_sha256_prefix((version_hash or "").strip().lower())
    if not _HEX_RE.fullmatch(hash_clean):
        raise CanonicalNameError(
            f"invalid version_hash (need 64 hex chars): {version_hash!r}"
        )

    if prefix == "lv":
        sandbox_clean = (sandbox or "").strip()
        if not sandbox_clean or "." in sandbox_clean:
            raise CanonicalNameError(
                f"lv documents require a sandbox segment: {sandbox!r}"
            )
        return f"lv.{msn_clean}.{sandbox_clean}.{name_clean}.{hash_clean}"

    if sandbox:
        raise CanonicalNameError(
            f"{prefix} documents must not carry a sandbox segment: {sandbox!r}"
        )
    return f"{prefix}.{msn_clean}.{name_clean}.{hash_clean}"


def parse_canonical_document_id(text: str) -> ParsedDocumentId:
    """Parse a canonical document id; raises ``CanonicalNameError`` on miss."""

    raw = (text or "").strip()
    if not raw:
        raise CanonicalNameError("empty document id")

    match_lv = _LV_RE.fullmatch(raw)
    if match_lv:
        return ParsedDocumentId(
            prefix="lv",
            msn_id=match_lv.group(1),
            sandbox=match_lv.group(2),
            name=match_lv.group(3),
            version_hash=match_lv.group(4),
        )
    match_other = _STL_OR_CPTR_RE.fullmatch(raw)
    if match_other:
        return ParsedDocumentId(
            prefix=match_other.group(1),
            msn_id=match_other.group(2),
            sandbox=None,
            name=match_other.group(3),
            version_hash=match_other.group(4),
        )
    raise CanonicalNameError(f"not a canonical document id: {raw!r}")


def is_canonical_document_id(text: str) -> bool:
    """Boolean form of ``parse_canonical_document_id``."""

    try:
        parse_canonical_document_id(text)
    except CanonicalNameError:
        return False
    return True


def _sanitize_segment(text: str) -> str:
    """Lowercase, preserve underscores, strip non-allowed chars (spaces → underscore)."""

    cleaned = text.strip().lower().replace(" ", "_")
    out = []
    for ch in cleaned:
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch)
    return "".join(out).strip("_-") or "anchor"


def _sanitize_sandbox_token(text: str) -> str:
    """Normalize a sandbox token to its canonical underscore form.

    Hyphens and spaces become underscores. Only alphanumeric and underscores
    are kept. This maps URL slugs (``cts-gis``) to programmatic tokens
    (``cts_gis``) while leaving already-canonical tokens unchanged.
    """

    cleaned = text.strip().lower().replace("-", "_").replace(" ", "_")
    out = []
    for ch in cleaned:
        if ch.isalnum() or ch == "_":
            out.append(ch)
    return "".join(out).strip("_") or "anchor"


_SC_MSN_RE = re.compile(r"^[0-9][0-9\-]*[0-9]$")
_SC_NAMESPACE_MARKERS = ("msn-", "msn_", "fnd.", "cts.", "registrar.")


def extract_semantic_name_from_sc_stem(stem: str) -> str | None:
    """Extract the canonical semantic name from a source-file stem.

    Source files follow the pattern ``sc.<msn_id>.<namespace><semantic>``.
    This function strips the ``sc.`` prefix, skips the MSN address segment,
    and strips any namespace marker (``msn-``, ``msn_``, ``fnd.``,
    ``registrar.``) to produce the bare semantic name.

    Returns ``None`` when the stem is malformed (empty semantic after stripping,
    or unrecognisable structure).

    Examples::

        "sc.1-2-3-4-5-6-7-8-9-0.msn-natural_entity"  → "natural_entity"
        "sc.1-2-3-4-5-6-7-8-9-0.msn_address_nodes"   → "address_nodes"
        "sc.1-2-3-4-5-6-7-8-9-0.fnd.1-2-3-4-5-6" → "1-2-3-4-5-6"
        "sc.1-2-3-4-5-6-7-8-9-0.sos_voterid"          → "sos_voterid"
        "sc.1-2-3-4-5-6-7-8-9-0.msn-"                 → None
        "sc.1-2-3-4-5-6-7-8-9-0."                     → None
    """

    if not stem.startswith("sc."):
        return None
    rest = stem[3:]  # strip "sc."
    if not rest:
        return None

    # Split off the first dot-segment; if it looks like an MSN address, skip it.
    if "." in rest:
        msn_candidate, remainder = rest.split(".", 1)
        if not _SC_MSN_RE.fullmatch(msn_candidate):
            # Not an MSN address — treat entire rest as the semantic suffix.
            remainder = rest
    else:
        # No dot: entire rest is the semantic suffix (no MSN segment).
        remainder = rest

    if not remainder:
        return None

    # Strip namespace prefix if present.
    for marker in _SC_NAMESPACE_MARKERS:
        if remainder.startswith(marker):
            semantic = remainder[len(marker):]
            if not semantic:
                return None  # malformed: marker with empty tail
            return _sanitize_segment(semantic) or None

    # No namespace prefix — remainder is the semantic name directly.
    return _sanitize_segment(remainder) or None


class MalformedSourceNameError(CanonicalNameError):
    """Raised when a source file stem cannot be reduced to a valid semantic name.

    The offending stem is included in the message. Callers should quarantine
    the source file rather than materialising a garbage document.
    """


def derive_canonical_id_from_legacy(
    legacy_id: str,
    *,
    msn_id: str,
    version_hash: str,
) -> str:
    """Derive the canonical id for a legacy ``system:`` / ``sandbox:`` /
    ``payload:`` / ``cache:`` document identifier.

    Rules:
    * ``system:anthology`` → ``lv.<msn>.system.anthology.<hash>``
    * ``system:<other>``   → ``lv.<msn>.system.<other>.<hash>``
    * ``sandbox:<tool>:<file>.json`` → ``lv.<msn>.<token>.<name>.<hash>``
      where ``<token>`` is the canonical underscore sandbox token derived
      via ``_sanitize_sandbox_token()`` (e.g. ``cts_gis``, never ``cts-gis``).
      The ``<name>`` is extracted from the source filename using
      ``extract_semantic_name_from_sc_stem()`` for ``sc.`` files; malformed
      stems raise ``MalformedSourceNameError``.
    * ``payload:<name>.bin`` → ``stl.<msn>.<name>.<hash>``
    * ``cache:<name>.json``  → ``cptr.<msn>.<name>.<hash>``
    """

    raw = (legacy_id or "").strip()
    if not raw:
        raise CanonicalNameError("empty legacy id")

    sys_match = _LEGACY_SYSTEM_RE.fullmatch(raw)
    if sys_match:
        name = _sanitize_segment(sys_match.group(1))
        return format_canonical_document_id(
            prefix="lv",
            msn_id=msn_id,
            sandbox="system",
            name=name,
            version_hash=version_hash,
        )

    sb_match = _LEGACY_SANDBOX_RE.fullmatch(raw)
    if sb_match:
        sandbox_raw, file_stem = sb_match.group(1), sb_match.group(2)
        sandbox = _sanitize_sandbox_token(sandbox_raw)
        stem = file_stem.rsplit("/", 1)[-1]
        anchor_pattern = re.compile(r"^tool\.[^.]+\.([A-Za-z0-9_\-]+)$")
        anchor_hit = anchor_pattern.fullmatch(stem)
        if anchor_hit and _sanitize_sandbox_token(anchor_hit.group(1)) == sandbox:
            name = "anchor"
        elif sandbox == "system" and stem == "anthology":
            name = "anthology"
        else:
            semantic = extract_semantic_name_from_sc_stem(stem)
            if semantic is None:
                if stem.startswith("sc."):
                    raise MalformedSourceNameError(
                        f"malformed source stem, quarantined: {stem!r}"
                    )
                # Non-sc. file without namespace prefix — use sanitized stem directly.
                name = _sanitize_segment(stem.split(".", 1)[0] if "." in stem else stem)
            else:
                name = semantic
        return format_canonical_document_id(
            prefix="lv",
            msn_id=msn_id,
            sandbox=sandbox,
            name=name,
            version_hash=version_hash,
        )

    payload_match = _LEGACY_PAYLOAD_RE.fullmatch(raw)
    if payload_match:
        return format_canonical_document_id(
            prefix="stl",
            msn_id=msn_id,
            sandbox=None,
            name=_sanitize_segment(payload_match.group(1)),
            version_hash=version_hash,
        )

    cache_match = _LEGACY_CACHE_RE.fullmatch(raw)
    if cache_match:
        return format_canonical_document_id(
            prefix="cptr",
            msn_id=msn_id,
            sandbox=None,
            name=_sanitize_segment(cache_match.group(1)),
            version_hash=version_hash,
        )

    raise CanonicalNameError(f"unsupported legacy id: {legacy_id!r}")


__all__ = [
    "ALLOWED_PREFIXES",
    "CanonicalNameError",
    "MalformedSourceNameError",
    "ParsedDocumentId",
    "derive_canonical_id_from_legacy",
    "extract_semantic_name_from_sc_stem",
    "format_canonical_document_id",
    "is_canonical_document_id",
    "parse_canonical_document_id",
]
