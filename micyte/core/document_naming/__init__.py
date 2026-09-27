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

#: `art.` joins them 2026-08-23 for the `artifact` datum type (plan P5). It takes the
#: `stl.`/`cptr.` shape — NO sandbox segment — because an artifact is addressed by the node
#: that denotes it, not by a sandbox it sits in, and because a binary payload must not enter
#: the catalog snapshot (see `NonCatalogPrefixError`): the catalog is read whole on every
#: authoritative read, and `lv.` is what it carries.
ALLOWED_PREFIXES = ("lv", "stl", "cptr", "art")

_LV_RE = re.compile(r"^lv\.([^.]+)\.([^.]+)\.([^.]+)\.([a-f0-9]{64})$")
_NO_SANDBOX_RE = re.compile(r"^(stl|cptr|art)\.([^.]+)\.([^.]+)\.([a-f0-9]{64})$")

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
    ``stl.``, ``cptr.`` and ``art.``. ``version_hash`` is the 64-char lowercase hex
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
    match_other = _NO_SANDBOX_RE.fullmatch(raw)
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


#: The names reserved for a SANDBOX ANCHOR, and for nothing else.
#:
#: `datum_document_naming_taxonomy.md`: "for `lv.` documents the name is `anchor` for every
#: sandbox anchor EXCEPT the system sandbox, where it is `anthology`", and both names "are
#: reserved for sandbox anchors — non-anchor documents must not use them".
#:
#: Named here, beside the contract they come from, because that exception stopped being a
#: special case: every instance keeps its own core sandbox called `system`, so `anthology`
#: is now the ORDINARY name for an instance's anchor and `anchor` is what the network-wide
#: sandboxes (registrar, taxonomy, agnet, archetype) use. Code that asks "does this sandbox
#: have an anchor" must ask about the pair, never about one literal.
ANCHOR_DOCUMENT_NAMES: frozenset[str] = frozenset({"anchor", "anthology"})

#: The canonical name of a sandbox's LOCAL DOMAIN — its lcl id-space, and (from
#: 2026-08-20) the log of which document each id names.
#:
#: Beside the anchor because it is the anchor's peer: the two documents every sandbox
#: holds, both found BY NAME by every reader, both reserved. The operator's direction —
#: "establish lcl_domain datum docs as a canonical default document for each sandbox,
#: similar to that of the anchor file" — is a statement about this pair.
LOCAL_DOMAIN_DOCUMENT = "lcl_domain"

#: What it was called before 2026-08-20. All eight live local domains still carried it
#: when the rename began; the promise to rename them was made on 2026-08-14 and not kept,
#: which is how the document meant to be canonical had two names for six days.
LEGACY_LOCAL_DOMAIN_DOCUMENT = "lcl"

#: Every spelling a local domain may be stored under, CANONICAL FIRST.
#:
#: Read through this, never against one literal — the same rule
#: :data:`ANCHOR_DOCUMENT_NAMES` states, learned the same way. It loses its second entry
#: when the store holds none, and ``test_instance_baseline`` fails if a legacy name
#: outlives its migration.
LOCAL_DOMAIN_DOCUMENT_NAMES: tuple[str, ...] = (
    LOCAL_DOMAIN_DOCUMENT, LEGACY_LOCAL_DOMAIN_DOCUMENT,
)


def document_in_sandbox(document_id: str, sandbox: str, *, msn_id: str = "") -> bool:
    """Does ``document_id`` belong to ``sandbox`` — and, when given, to ``msn_id``?

    The one place this question is answered. Seven call sites asked it as a substring
    test, ``f".{sandbox}." in document_id``, and one of them documented the reasoning:
    "documents follow the canonical id pattern ``lv.<MSN>.<sandbox>.<name>.<hash>``, so a
    token match against the dot-bounded substring is DECISIVE."

    It was decisive only while a sandbox name identified exactly one sandbox. Every
    instance now keeps its own core sandbox named ``system``, so that substring matches
    every instance's copy at once — a 2026-07 tripwire in ``test_instances.py`` predicted
    precisely this and named the consequence: ``load_workbook`` "would silently mix two
    instances' documents into one workbook".

    Passing ``msn_id`` is what makes the answer decisive again. Omitting it keeps the old,
    name-only question, which is still correct for a sandbox no other instance can hold
    (``registrar``, ``archetype``, ``taxonomy``, ``agnet``) — but a caller that HAS the msn
    should always pass it, because the failure mode of not passing it is silent and
    cross-tenant.

    Structural, NOT validating. It reads the segments and does not care whether the
    version hash is well-formed, because the hash has nothing to do with the question.
    Parsing it properly instead was tried and immediately dropped 31 tests' worth of
    documents whose ids end in a short stand-in hash: a filter that silently drops rows
    is a worse failure than one that answers a slightly wider question, and the substring
    it replaces did not validate anything either.

    Only ``lv.`` documents live in a sandbox at all — ``stl.``, ``cptr.`` and ``art.``
    carry no sandbox segment, so they are in none.
    """
    parts = str(document_id or "").split(".")
    # lv . <msn_id> . <sandbox> . <name> . <version_hash>  — and no segment may contain
    # a dot, so a canonical id is exactly five parts.
    if len(parts) != 5 or parts[0] != "lv":
        return False
    if parts[2] != sandbox:
        return False
    return not msn_id or parts[1] == msn_id


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
    "document_in_sandbox",
    "extract_semantic_name_from_sc_stem",
    "format_canonical_document_id",
    "is_canonical_document_id",
    "parse_canonical_document_id",
]
