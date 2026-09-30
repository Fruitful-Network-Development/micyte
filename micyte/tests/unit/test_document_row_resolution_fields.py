"""What a document row must carry for the keyboard contract to resolve.

F2 and the row context menu act on a document that is *not* necessarily the one
open in the editor, so they cannot read anything off the selected-document
summary. Every field they need has to be on the row itself:

    document_id     the write target
    canonical_name  what the rename input is seeded with — the FULL name, never
                    the elided label the row displays
    sandbox         the mutation's sandbox_id
    is_anchor       so the client refuses what the server refuses

Losing any one of them makes F2 a no-op on some rows and silently correct on
others, which is the failure mode hardest to notice.
"""

from __future__ import annotations

import unittest

from micyte.core.datum_documents import AuthoritativeDatumDocument
from micyte.tools.workbench_ui.service import WorkbenchUiReadService

_HASH = "a" * 64


def _document(
    *, sandbox: str = "trapp", name: str = "invoices", anchor: bool = False, canonical: str | None = None
) -> AuthoritativeDatumDocument:
    return AuthoritativeDatumDocument(
        document_id=f"lv.3-2-3.{sandbox}.{name}.{_HASH}",
        source_kind="sandbox_source",
        document_name=f"{name}.json",
        relative_path=f"{sandbox}/{name}.json",
        canonical_name=name if canonical is None else canonical,
        tool_id=sandbox,
        is_anchor=anchor,
        rows=({"datum_address": "0-0-1", "raw": [["0-0-1", "~", "0-0-0"], ["ordinal"]]},),
    )


def _entry(document: AuthoritativeDatumDocument) -> dict:
    # The builder reads nothing off `self`; identity is derived from the document.
    service = object.__new__(WorkbenchUiReadService)
    return WorkbenchUiReadService._build_document_entry(service, tenant_id="fnd", document=document)


class DocumentRowResolutionTests(unittest.TestCase):
    def test_a_row_carries_every_field_the_rename_resolves_against(self) -> None:
        entry = _entry(_document())
        for field in ("document_id", "canonical_name", "sandbox", "is_anchor"):
            self.assertIn(field, entry, f"row is missing {field}")
        self.assertEqual(entry["sandbox"], "trapp")
        self.assertEqual(entry["canonical_name"], "invoices")

    def test_the_sandbox_comes_from_the_id_not_from_the_view(self) -> None:
        """A row must name ITS OWN sandbox: the rename posts sandbox_id, and the
        list shows the whole tenant corpus, not one sandbox."""
        self.assertEqual(_entry(_document(sandbox="wolf"))["sandbox"], "wolf")
        self.assertEqual(_entry(_document(sandbox="agnet"))["sandbox"], "agnet")

    def test_an_anchor_is_marked_so_the_client_can_refuse_what_the_server_refuses(self) -> None:
        self.assertTrue(_entry(_document(name="anchor", anchor=True))["is_anchor"])
        self.assertFalse(_entry(_document())["is_anchor"])

    def test_the_full_name_survives_beside_the_display_label(self) -> None:
        """`label` may be shortened for the list; `canonical_name` may not, because
        it is what a rename is seeded with and therefore what would be written."""
        entry = _entry(_document(name="county_line_produce_auction_lots"))
        self.assertEqual(entry["canonical_name"], "county_line_produce_auction_lots")
        self.assertIn("label", entry)

    def test_a_row_with_no_canonical_name_still_offers_a_full_fallback(self) -> None:
        """The rename falls back to document_name, which must be the whole name."""
        entry = _entry(_document(name="msn-1234", canonical=""))
        self.assertEqual(entry["canonical_name"], "")
        self.assertEqual(entry["document_name"], "msn-1234.json")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
