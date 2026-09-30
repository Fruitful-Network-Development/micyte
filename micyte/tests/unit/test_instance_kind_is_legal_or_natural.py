"""An instance says it is a legal entity or a natural one. Those are the only two.

The registrar's `entity_class` branch carries four, and it should: `administrative` is
cited 57 times on this host by the counties and municipalities the registrar tracks, and
`informal` 3 times. Those classify PLACES and PARTIES in the registry.

An INSTANCE is a party doing business with FND, and the whole of the registrar's concern
about one is which of the two it is. The finer classification of a legal entity —
producer, orchard, food hub — belongs to the AGNET channel, which builds those profiles
over msn_ids it already assumes carry the registrar's legal type indicator. That is the
first place the distinction is relevant, and it is not the instance profile.

`seed_instance_kind_vocabulary` mirrored the registrar's branch wholesale, so every
client's own profile offered "administrative" as something it could declare itself to be.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools._viewscope import INSTANCE_KIND_BRANCH, INSTANCE_KINDS, lcl_options


class _Log:
    def __init__(self, entries):
        self.entries = entries


class _Entry:
    def __init__(self, label):
        self.label = label


class _Doc:
    canonical_name = "lcl_domain"


class TheVocabularyIsTwo(unittest.TestCase):
    def test_exactly_legal_and_natural(self) -> None:
        self.assertEqual(INSTANCE_KINDS, ("legal", "natural"))

    def test_the_branch_it_applies_to_is_named_kind(self) -> None:
        # The narrowing is keyed on the branch, so a slot drawing from any OTHER branch
        # keeps its full vocabulary — `job_manager`'s job types are the same mechanism and
        # must not be cut down to two.
        self.assertEqual(INSTANCE_KIND_BRANCH, "kind")


class OnlyTheKindBranchIsNarrowed(unittest.TestCase):
    """A filter that applied to every branch would silently gut unrelated pickers."""

    ENTRIES = {
        "2": _Entry("kind"),
        "2-1": _Entry("legal"),
        "2-2": _Entry("informal"),
        "2-3": _Entry("administrative"),
        "2-4": _Entry("natural"),
        "3": _Entry("job_type"),
        "3-1": _Entry("gutter cleaning"),
        "3-2": _Entry("administrative"),
    }

    def _options(self, branch: str):
        import micyte.tools._viewscope as vsmod

        class _Store:
            def read_documents_by_sandbox(self, **_kw):
                return [_Doc()]

        real_read = vsmod.__dict__.get("_ld_read_log")
        del real_read
        from micyte.core.datum_ops import local_domain as ld

        original = ld.read_log
        ld.read_log = lambda _doc: _Log(self.ENTRIES)
        try:
            return [o["label"] for o in lcl_options(
                _Store(), tenant_id="fnd", sandbox="system", namespace="registrar",
                msn_id="3-2-3", branch=branch)]
        finally:
            ld.read_log = original

    def test_the_kind_branch_offers_only_the_two(self) -> None:
        self.assertEqual(self._options("kind"), ["legal", "natural"])

    def test_another_branch_keeps_everything_it_defines(self) -> None:
        self.assertEqual(self._options("job_type"),
                         ["gutter cleaning", "administrative"])


if __name__ == "__main__":
    unittest.main()
