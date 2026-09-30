"""Phase 11 architecture postcondition: datum-document naming invariants.

Locks the vocabulary that the (future) Phase E4 catalog upgrade will
enforce universally. Tests in this file run against the **live code**
not against any datum-store contents; the document-id format and the
sandbox-token shape are pinned at the source-of-truth level.

Per datum_catalog_phase_e4_migration.md, three invariants matter for
the foundation:

  1. ALLOWED_PREFIXES in packages/core/document_naming = ("lv","stl","cptr").
  2. The format_canonical_document_id helper enforces the dotted shape
     and the 64-hex version_hash. Any change to ALLOWED_PREFIXES or the
     dotted shape needs to be deliberate.
  3. Sandbox tokens are lowercase + underscore-separated. URL slugs may
     use hyphens; sandbox segments in canonical document ids must not.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.document_naming import (
    ALLOWED_PREFIXES,
    CanonicalNameError,
    format_canonical_document_id,
    is_canonical_document_id,
    parse_canonical_document_id,
)
from micyte.state_machine.portal_shell.shell_schemas import (
    CORE_SANDBOX_TOKEN,
    REGISTRAR_SANDBOX_TOKEN,
    WORKBENCH_UI_SANDBOX_TOKEN,
)

# 64 'a' chars — a syntactically valid version_hash for shape tests.
HASH = "a" * 64


class CanonicalPrefixTests(unittest.TestCase):
    def test_allowed_prefixes_are_exactly_four(self) -> None:
        """`art.` joined 2026-08-23 for the artifact datum type (plan P5).

        Kept as an exact set rather than a membership check: a prefix is a shape the whole
        naming contract has to agree about — whether it carries a sandbox segment, whether
        the catalog snapshot may hold it — so adding one should stop somebody, which is
        what this did.
        """
        self.assertEqual(set(ALLOWED_PREFIXES), {"lv", "stl", "cptr", "art"})

    def test_art_carries_no_sandbox_segment(self) -> None:
        """The `stl.`/`cptr.` shape. An artifact is addressed by the node that DENOTES it,
        not by a sandbox it sits in."""
        good = format_canonical_document_id(
            prefix="art", msn_id="3-2-3", sandbox=None, name="photo", version_hash=HASH
        )
        self.assertEqual(good, f"art.3-2-3.photo.{HASH}")
        self.assertTrue(is_canonical_document_id(good))

    def test_lv_requires_sandbox_segment(self) -> None:
        good = format_canonical_document_id(
            prefix="lv", msn_id="3-2-3", sandbox="cts_gis", name="document", version_hash=HASH
        )
        self.assertTrue(good.startswith("lv.3-2-3.cts_gis.document."))
        with self.assertRaises(CanonicalNameError):
            format_canonical_document_id(
                prefix="lv", msn_id="3-2-3", sandbox="", name="document", version_hash=HASH
            )

    def test_stl_and_cptr_refuse_sandbox_segment(self) -> None:
        # Both prefixes must succeed without a sandbox segment...
        format_canonical_document_id(
            prefix="stl", msn_id="3-2-3", sandbox=None, name="payload", version_hash=HASH
        )
        format_canonical_document_id(
            prefix="cptr", msn_id="3-2-3", sandbox=None, name="cache", version_hash=HASH
        )
        # ...and fail when a sandbox segment is supplied.
        with self.assertRaises(CanonicalNameError):
            format_canonical_document_id(
                prefix="stl", msn_id="3-2-3", sandbox="cts_gis", name="payload", version_hash=HASH
            )

    def test_version_hash_must_be_64_hex_chars(self) -> None:
        with self.assertRaises(CanonicalNameError):
            format_canonical_document_id(
                prefix="lv", msn_id="3-2-3", sandbox="system", name="x", version_hash="short"
            )
        # Uppercase input is accepted but normalised to lowercase in the
        # output id — the formatter is lenient on input case.
        formatted = format_canonical_document_id(
            prefix="lv",
            msn_id="3-2-3",
            sandbox="system",
            name="x",
            version_hash="A" * 64,
        )
        self.assertEqual(formatted.split(".")[-1], "a" * 64)

    def test_round_trip_format_then_parse_is_stable(self) -> None:
        formatted = format_canonical_document_id(
            prefix="lv", msn_id="3-2-3", sandbox="cts_gis", name="document", version_hash=HASH
        )
        parsed = parse_canonical_document_id(formatted)
        self.assertEqual(parsed.prefix, "lv")
        self.assertEqual(parsed.msn_id, "3-2-3")
        self.assertEqual(parsed.sandbox, "cts_gis")
        self.assertEqual(parsed.name, "document")
        self.assertEqual(parsed.version_hash, HASH)
        # Round-trip equality.
        self.assertEqual(parsed.document_id, formatted)


class IsCanonicalDocumentIdTests(unittest.TestCase):
    def test_recognises_each_prefix(self) -> None:
        self.assertTrue(is_canonical_document_id(f"lv.3-2-3.system.anthology.{HASH}"))
        self.assertTrue(is_canonical_document_id(f"stl.3-2-3.payload.{HASH}"))
        self.assertTrue(is_canonical_document_id(f"cptr.3-2-3.cache.{HASH}"))

    def test_rejects_legacy_aliases(self) -> None:
        self.assertFalse(is_canonical_document_id("system:anthology"))
        self.assertFalse(is_canonical_document_id("sandbox:cts_gis:precincts.json"))
        self.assertFalse(is_canonical_document_id("payload:abc.bin"))
        self.assertFalse(is_canonical_document_id("cache:abc.json"))

    def test_rejects_wrong_hash_shape(self) -> None:
        # is_canonical_document_id is the matcher path (not the lenient
        # formatter path), so it requires lowercase hex of length 64.
        self.assertFalse(is_canonical_document_id(f"lv.3-2-3.system.x.{HASH[:-1]}"))
        self.assertFalse(is_canonical_document_id(f"lv.3-2-3.system.x.{HASH.upper()}"))


class SandboxTokenInvariantsTests(unittest.TestCase):
    """Sandbox tokens (the segment that goes between msn_id and name in
    canonical lv. ids) are lowercase with underscores. URL slugs may use
    hyphens elsewhere, but the canonical sandbox segment must not."""

    KNOWN_TOKENS = (
        CORE_SANDBOX_TOKEN,
        REGISTRAR_SANDBOX_TOKEN,
        WORKBENCH_UI_SANDBOX_TOKEN,
    )

    def test_no_token_contains_a_hyphen(self) -> None:
        for token in self.KNOWN_TOKENS:
            self.assertNotIn(
                "-",
                token,
                f"sandbox token {token!r} must not contain a hyphen — use underscores",
            )

    def test_all_tokens_are_lowercase(self) -> None:
        for token in self.KNOWN_TOKENS:
            self.assertEqual(token, token.lower(), f"sandbox token {token!r} must be lowercase")

    def test_tokens_are_format_compatible(self) -> None:
        # Each canonical sandbox token must be accepted by the formatter
        # (i.e. composes a valid lv. id when paired with valid msn/name/hash).
        for token in self.KNOWN_TOKENS:
            formatted = format_canonical_document_id(
                prefix="lv", msn_id="3-2-3", sandbox=token, name="probe", version_hash=HASH
            )
            self.assertTrue(is_canonical_document_id(formatted))


if __name__ == "__main__":
    unittest.main()
