"""The site-hosting contract, and the distinctions it exists to keep.

The Design tab has always written straight to disk — `site_content_extension` replaces a
string in a manifest JSON or a `.html` file — and it is the one write path in this stack
with no port in front of it. So nothing about it was declared, nothing could be granted
separately, and the Ports surface could not show it.

What the tests below are really pinning is the GRAIN. An operation is what an operator
would refuse separately, and the temptation with a site editor is one `write` permission
covering everything. These keep six apart.

Two of them arrived 2026-08-26 with client authoring: publishing a written piece is
neither a replacement (it changes nothing already on a page) nor an upload (which leaves a
file the site may not link) — it ADDS A PAGE. And because the retitle path retires the
prior slug, retiring is performed and therefore declared.

The sixth arrived 2026-08-28 and is the first that WRITES NOTHING: `analytics.read`
reports the monthly traffic totals. It is separate for the reason the others are —
`site_analytics_refresh` runs unattended and needs exactly this, and an operator granting
a counter must not thereby have granted a publisher.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.ports.port_catalog import port_type
from micyte.ports.site_hosting import (
    OPERATION_ANALYTICS_READ,
    OPERATION_ARTICLE_PUBLISH,
    OPERATION_ARTICLE_RETIRE,
    OPERATION_ARTICLE_SEND,
    OPERATION_ASSET_SWAP,
    OPERATION_ASSET_UPLOAD,
    OPERATION_CONTENT_REPLACE,
    OPERATION_PAGE_LIST,
    OPERATION_PROFILE_EDIT,
    OPERATION_PROJECT_EXPORT,
    AmbiguousEdit,
    ArticleDraft,
    ContentEdit,
    EditablePage,
    ProfileEdit,
    PublishedArticle,
    SiteHostingError,
    SiteHostingPort,
    SiteHostingUnavailable,
    SiteProfile,
)

#: `asset.swap` joined 2026-08-31, and the grain below is why it is its own permission
#: rather than a use of `content.replace`: the swap path refuses a target that is not in
#: the site's own gallery, where a content replacement could point an `<img>` anywhere.
#: "May change which of your photos this page shows" and "may rewrite any text on the page"
#: are different things to grant, and until this they had one word.
#: `profile.edit` joined 2026-09-10 for Enchir's project editor. It edits the LEAFLET a
#: site's pages are generated from — feature image, photograph order and hiding, the two
#: descriptions — and rebuilds them, so one save reaches a hero, a card, a project row and
#: an overlay at once and can withhold a photograph. Neither one string on one page nor one
#: <img> pointed at another file; an operator may let a client arrange their own projects
#: without letting them rewrite any text on the page.
#: `article.send` is the tenth (2026-09-13) and argues for itself on the sharpest version
#: of the same ground: a publish puts words on a page the author can take back down in a
#: minute, and a send puts them in other people's mail where nothing can be taken back. An
#: operator may well want a client writing for the web and not mailing a list of 38 people.
ALL_OPERATIONS = (
    OPERATION_PAGE_LIST, OPERATION_CONTENT_REPLACE, OPERATION_ASSET_SWAP,
    OPERATION_ASSET_UPLOAD, OPERATION_ARTICLE_PUBLISH, OPERATION_ARTICLE_RETIRE,
    OPERATION_ARTICLE_SEND,
    OPERATION_ANALYTICS_READ, OPERATION_PROFILE_EDIT, OPERATION_PROJECT_EXPORT,
)


class TheGrainIsOnePermissionPerRefusableAct(unittest.TestCase):
    def test_every_operation_is_its_own_permission(self) -> None:
        """A single `site.write` would make "fix a typo" and "put a file on the
        internet" the same permission — since 2026-08-26 it would fold "add a page to
        this person's website" into it too, and since 2026-08-28 it would hand a nightly
        counter the right to publish.

        The number is asserted so that ADDING one is a deliberate edit here. What matters
        is not that there are seven; it is that no two of them are things an operator would
        want to grant together without saying so. `asset.swap` was the seventh (2026-08-31)
        and had to argue for itself on exactly that ground: it is fenced to the site's own
        gallery, and `content.replace` is not.
        """
        # Eight since 2026-09-10: `profile.edit`, which argued for itself the same way —
        # it rewrites a source of record several pages draw on and can hide a photograph.
        self.assertEqual(len(set(ALL_OPERATIONS)), 10)

    def test_the_register_carries_exactly_these(self) -> None:
        self.assertEqual(set(port_type("site_hosting").operations), set(ALL_OPERATIONS))

    def test_publishing_is_not_uploading(self) -> None:
        """The distinction the two exist to keep, asserted rather than described.

        Both put bytes at a public URL. An upload leaves a file the site may or may not
        link; a publish gives somebody a NEW ADDRESS and puts a tile on a gallery pointing
        at it. An operator granting the first has not granted the second.
        """
        self.assertNotEqual(OPERATION_ARTICLE_PUBLISH, OPERATION_ASSET_UPLOAD)

    def test_the_only_take_down_is_scoped_to_a_written_piece(self) -> None:
        """The port still has no page-delete and no asset-delete.

        Until 2026-08-26 this test asserted no take-down existed at all, on the true
        ground that the Design surface performs none. Authoring performs one:
        `delete_article` is wired to a live route, and the retitle path retires the prior
        slug on every title edit, so a publish that could not retire would strand the old
        page and its sitemap entry. What the rule protects is that the take-down is
        NARROW — it names an article, not a page and not an asset.
        """
        take_downs = [
            op for op in port_type("site_hosting").operations
            if any(word in op for word in ("delete", "remove", "retire"))
        ]
        self.assertEqual(take_downs, [OPERATION_ARTICLE_RETIRE])
        self.assertTrue(OPERATION_ARTICLE_RETIRE.startswith("article."))

    def test_it_names_its_own_operations(self) -> None:
        """Unlike `commerce_offering`, whose egress grain is its vendor's."""
        self.assertTrue(port_type("site_hosting").names_its_operations)


class AProfileEditMustChangeSomething(unittest.TestCase):
    """`ProfileEdit` refuses at construction, so a malformed edit never reaches a leaflet."""

    def test_it_needs_the_profiles_slug(self) -> None:
        with self.assertRaises(SiteHostingError):
            ProfileEdit(slug="", summary="x")

    def test_an_edit_that_changes_nothing_is_refused(self) -> None:
        """Every field is optional and at least one must be given — the rule `ContentEdit`
        states about `old == new`: it would report a save over a leaflet that did not
        change."""
        with self.assertRaises(SiteHostingError):
            ProfileEdit(slug="77_parmelee_dr")

    def test_a_title_alone_is_an_edit(self) -> None:
        """The project's name as the site shows it (2026-09-10: "editing the title")."""
        self.assertEqual(ProfileEdit(slug="s", title="The Elm").changes, ("title",))

    def test_None_means_leave_it_alone_and_names_are_trimmed(self) -> None:
        edit = ProfileEdit(slug="s", gallery_order=(" a.avif ", "", "b.avif"), hidden=("b.avif",))
        self.assertEqual(edit.changes, ("gallery_order", "hidden"))
        self.assertEqual(edit.gallery_order, ("a.avif", "b.avif"))
        self.assertIsNone(edit.feature_ref)
        self.assertIsNone(edit.summary)

    def test_an_empty_bio_paragraph_is_nothing(self) -> None:
        self.assertEqual(ProfileEdit(slug="s", bio=("one", " ", "two")).bio, ("one", "two"))

    def test_a_profile_names_its_photographs_for_a_person(self) -> None:
        """`gallery_names` is what a form shows and sends back; `name_of` falls back to
        the ref so an unnamed photograph is still addressable."""
        profile = SiteProfile(slug="s", gallery_refs=("/a/x.avif", "/a/y.avif"),
                              gallery_names={"/a/x.avif": "x.avif"})
        self.assertEqual(profile.name_of("/a/x.avif"), "x.avif")
        self.assertEqual(profile.name_of("/a/y.avif"), "/a/y.avif")
        with self.assertRaises(SiteHostingError):
            SiteProfile(slug="")


class AnEditMustBeAnEdit(unittest.TestCase):
    def test_a_replacement_with_no_OLD_value_is_refused(self) -> None:
        """It is an append wearing an edit's name: with nothing to match, the
        implementation's exactly-one-occurrence guard has nothing to check."""
        with self.assertRaises(SiteHostingError):
            ContentEdit(page="index.html", old="", new="hello")

    def test_an_edit_that_changes_nothing_is_refused(self) -> None:
        """It would consume the one occurrence it was allowed and report success."""
        with self.assertRaises(SiteHostingError):
            ContentEdit(page="index.html", old="same", new="same")

    def test_an_edit_needs_a_page(self) -> None:
        with self.assertRaises(SiteHostingError):
            ContentEdit(page="", old="a", new="b")

    def test_a_real_edit_is_accepted(self) -> None:
        edit = ContentEdit(page="index.html", old="Welcom", new="Welcome")
        self.assertEqual((edit.page, edit.old, edit.new),
                         ("index.html", "Welcom", "Welcome"))


class ThePageDescription(unittest.TestCase):
    def test_a_page_needs_a_path(self) -> None:
        with self.assertRaises(SiteHostingError):
            EditablePage(path="")

    def test_editable_defaults_to_FALSE(self) -> None:
        """A page is not editable until something says it is. The other default would
        make a page nobody classified look like one anybody may rewrite."""
        self.assertFalse(EditablePage(path="index.html").editable)


class TheErrorsStayApart(unittest.TestCase):
    def test_unavailable_is_a_site_hosting_error(self) -> None:
        self.assertTrue(issubclass(SiteHostingUnavailable, SiteHostingError))

    def test_an_ambiguous_edit_is_NOT_an_outage(self) -> None:
        """"The tree is unreachable" and "that matched twice" send an operator to fix
        entirely different things."""
        self.assertTrue(issubclass(AmbiguousEdit, SiteHostingError))
        self.assertFalse(issubclass(AmbiguousEdit, SiteHostingUnavailable))
        self.assertFalse(issubclass(SiteHostingUnavailable, AmbiguousEdit))


class ADraftIsAPieceOfWriting(unittest.TestCase):
    def test_a_draft_with_no_body_is_refused(self) -> None:
        """Publishing nothing would still add a page."""
        with self.assertRaises(SiteHostingError):
            ArticleDraft(body="   ")

    def test_a_loose_date_is_refused_because_it_becomes_a_filename(self) -> None:
        with self.assertRaises(SiteHostingError):
            ArticleDraft(body="# T\n\nx", date="Aug 26 2026")

    def test_an_empty_date_is_allowed_and_means_today(self) -> None:
        self.assertEqual(ArticleDraft(body="# T\n\nx").date, "")

    def test_a_draft_carries_no_title_field(self) -> None:
        """The title is the first `# ` line of the body. A separate field could
        disagree with the heading, and then the piece has two titles."""
        self.assertNotIn("title", ArticleDraft(body="# T\n\nx").__dataclass_fields__)

    def test_the_body_is_NOT_capped_at_a_writings_budget(self) -> None:
        """The 4096-character limit belongs to a MOS writing and must not be read
        across. Measured 2026-08-26: 27 of the 33 live articles exceed it, and 12 use
        characters `note_books.unstorable` refuses. A leaflet holds all of them."""
        from micyte.tools.note_books import NOTE_CHAR_BUDGET

        long_body = "# Long\n\n" + ("word " * 3000)
        self.assertGreater(len(long_body), NOTE_CHAR_BUDGET)
        self.assertEqual(ArticleDraft(body=long_body).body, long_body)

    def test_a_published_piece_needs_a_slug(self) -> None:
        """It is the piece's address."""
        with self.assertRaises(SiteHostingError):
            PublishedArticle(slug="")


class TheProtocolIsRuntimeCheckable(unittest.TestCase):
    def test_an_object_with_every_method_satisfies_it(self) -> None:
        class Adapter:
            def list_pages(self, *, site): return ()
            def replace_content(self, *, site, edit): return {}
            def upload_asset(self, *, site, name, payload): return {}
            def export_project(self, *, site="", export=None): return {}
            def list_articles(self, *, site): return ()
            def publish_article(self, *, site, draft): return PublishedArticle(slug="s")
            def retire_article(self, *, site, slug): return {}
            def read_analytics(self, *, site): return ()

        self.assertIsInstance(Adapter(), SiteHostingPort)

    def test_one_missing_method_does_not(self) -> None:
        class Partial:
            def list_pages(self, *, site): return ()

        self.assertNotIsInstance(Partial(), SiteHostingPort)


class ThePortHoldsNoImplementation(unittest.TestCase):
    def test_it_opens_no_tree_and_imports_no_client(self) -> None:
        """`micyte` may hold no network client and no filesystem write. A contract that
        quietly grew one would put the thing being governed inside the governor."""
        source = (REPO_ROOT / "micyte" / "ports" / "site_hosting"
                  / "contracts.py").read_text()
        for forbidden in ("import requests", "import httpx", "urllib.request",
                          "open(", "write_text", "write_bytes", "shutil", "subprocess"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
