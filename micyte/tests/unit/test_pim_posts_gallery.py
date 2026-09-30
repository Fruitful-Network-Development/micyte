"""PIM's Authoring tab: three views of one article, not three kinds of thing.

Restructured 2026-08-29 on the operator's instruction to make the tab intuitive and to
give it "a gallery of created posts to edit or manage for hiding or uploading drafts".

What was there: one "Writing" tab holding a table of published pieces, a publish form, and
a retire form. To take something down you read its address out of the table and typed it
into the form below. To edit, you retyped the piece. There was no draft — the only way to
save something unfinished was to publish it and hide it afterwards, which put it on the
public site for as long as that took.

What was there next, same day: Posts (the gallery, and one piece opened from it), Write (a
blank page), Pages, Images.

Then: Posts (published) and Drafts (everything else, and where a new one starts).

What is there NOW, on the operator's instruction of 2026-09-14: **Articles, Newsletter,
Website**. The old split cut by whether a piece was FINISHED, so an author looking for
something they wrote had to remember which state they had left it in. These cut by
DESTINATION — which is what the author was choosing between in the first place — and each
view offers the one act that is about it: write, send, put up or take down.

A piece of writing is an ARTICLE ARTIFACT. "Sent" and "on the site" are two things that
can be true of one independently, which is why the status column says both.

These tests pin the parts a redesign is most likely to quietly lose.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.ports.site_hosting import PublishedArticle
from micyte.tools.pim_design import (
    DEFAULT_TAB,
    PIECE_QUERY,
    TAB_QUERY,
    PimDesign,
)

BODY = "# On Playing the Light\n\nSome roles you build. Others you agree to stand inside."


class _Site:
    def __init__(self, pieces=()):
        self._pieces = pieces

    def list_articles(self, *, site=""):
        return self._pieces

    def list_subtopics(self, *, site=""):
        return ("writing",)

    def list_pages(self, *, site=""):
        return ()

    def list_site_content(self, *, site=""):
        return {"enabled": True, "pages": [], "gallery": {}}


def _piece(slug="on_playing_the_light", *, hidden=False, body=BODY):
    return PublishedArticle(
        slug=slug, title="On Playing the Light", date="2026-07-02", subtopic="writing",
        hidden=hidden, url=f"https://masonlenehan.com/article/{slug}.html",
        extra={"body": body, "excerpt": "Some roles you build."})


def _panes(site, **query):
    payload = PimDesign().build_panel_payload(
        sandbox_id="pim", host_context={"private_dir": None, "port": lambda _p: site},
        extra_query=query or None)
    return payload, {t["id"]: t["panel_payload"] for t in payload["tabs"]}


def _by_title(pane):
    return {p["panel_payload"].get("title"): p["panel_payload"]
            for p in pane.get("panes", [])}


class TheThreeViews(unittest.TestCase):
    def test_articles_is_the_landing(self) -> None:
        self.assertEqual(DEFAULT_TAB, "articles")
        payload, _panes_by_id = _panes(_Site((_piece(),)))
        # CONTACTS IS THE FOURTH, since 2026-09-15 — last, because it is WHO the first
        # three are addressed to, and beside them so the send form's subscriber count and
        # the table that count comes from are on one screen.
        self.assertEqual([t["id"] for t in payload["tabs"]],
                         ["articles", "newsletter", "website", "contacts"])
        self.assertEqual(payload["active_tab"], "articles")

    def test_articles_hides_nothing(self) -> None:
        """The whole point of the 2026-09-14 split: one list, whatever became of each."""
        _payload, panes = _panes(_Site((_piece(), _piece(slug="d", hidden=True))))
        gallery = _by_title(panes["articles"])["Your writing"]
        self.assertEqual(gallery["row_count"], 2)

    def test_the_status_column_says_BOTH_facts(self) -> None:
        """On the site and sent are not points on a scale; showing one would hide the
        other, and "draft" is what is left when neither is true.

        All four combinations, because the one that matters is the piece that is BOTH —
        a column that picked a winner would silently drop half of what became of it.
        """
        payload = PimDesign().build_panel_payload(
            sandbox_id="pim",
            host_context={
                "private_dir": None,
                "port": lambda _p: _Site((
                    _piece(slug="both"), _piece(slug="up"),
                    _piece(slug="mailed", hidden=True),
                    _piece(slug="neither", hidden=True))),
                "sent_issues": {"both": {"sent_at": "2026-08-01T00:00:00Z"},
                                "mailed": {"sent_at": "2026-08-02T00:00:00Z"}}},
            extra_query={TAB_QUERY: "articles"})
        panes = {t["id"]: t["panel_payload"] for t in payload["tabs"]}
        statuses = sorted(r["status"]
                          for r in _by_title(panes["articles"])["Your writing"]["rows"])
        self.assertEqual(statuses,
                         ["draft", "on the site", "on the site · sent", "sent"])

    def test_website_is_what_is_ON_the_site(self) -> None:
        _payload, panes = _panes(_Site((_piece(), _piece(slug="d", hidden=True))))
        listing = _by_title(panes["website"])["On your website"]
        self.assertEqual(listing["row_count"], 1)
        self.assertEqual(listing["count_label"], "1 on the site")

    def test_website_offers_taking_off_and_putting_up(self) -> None:
        _payload, panes = _panes(_Site((_piece(), _piece(slug="d", hidden=True))))
        forms = _by_title(panes["website"])
        self.assertIn("Take one off the website", forms)
        self.assertIn("Put one on the website", forms)
        # THE WRITING IS KEPT either way — both post to `visibility`, never to `retire`.
        for title in ("Take one off the website", "Put one on the website"):
            self.assertTrue(forms[title]["submit_action"]["route"].endswith("/visibility"))

    def test_nothing_up_means_no_take_off_form(self) -> None:
        """A control that can only fail is worse than no control."""
        _payload, panes = _panes(_Site((_piece(slug="d", hidden=True),)))
        self.assertNotIn("Take one off the website", _by_title(panes["website"]))

    def test_a_new_piece_is_a_DRAFT_and_reaches_nobody(self) -> None:
        """The destination select went with the split. A first draft must not go on the
        web or to 39 people as a side effect of being written down."""
        _payload, panes = _panes(_Site(()))
        start = _by_title(panes["articles"])["Write a new piece"]
        self.assertEqual(start["submit_action"]["fixed"], {"visibility": "draft"})
        self.assertTrue(start["submit_action"]["route"].endswith("/publish"))
        self.assertNotIn("danger", start["submit_action"])


class TheNewsletterView(unittest.TestCase):
    SENT = {"on_playing_the_light": {"sent_at": "2026-08-01T09:00:00Z",
                                     "subject": "On Playing the Light",
                                     "target_count": 39}}

    def _panes(self, site, sent=None, count=39):
        payload = PimDesign().build_panel_payload(
            sandbox_id="pim",
            host_context={"private_dir": None, "port": lambda _p: site,
                          "sent_issues": self.SENT if sent is None else sent,
                          "subscribers": {"count": count,
                                          "list_address": "news@example.com",
                                          "signup_url": "https://example.com/"}})
        return {t["id"]: t["panel_payload"] for t in payload["tabs"]}

    def test_it_lists_what_has_gone_out_with_its_day(self) -> None:
        panes = self._panes(_Site((_piece(),)))
        history = _by_title(panes["newsletter"])["Sent to your list"]
        self.assertEqual(history["row_count"], 1)
        self.assertEqual(history["rows"][0]["sent"], "2026-08-01")
        self.assertEqual(history["rows"][0]["people"], "39")

    def test_an_issue_with_no_article_is_still_listed(self) -> None:
        """Sent by mailing news@<domain>, captured by a Lambda. A list built by filtering
        ARTICLES would leave the author's own newsletter off their newsletter page."""
        panes = self._panes(_Site(()), sent={"tour": {"sent_at": "2026-06-26T00:00:00Z",
                                                     "subject": "Tour Saturday",
                                                     "target_count": 12}})
        history = _by_title(panes["newsletter"])["Sent to your list"]
        self.assertEqual(history["rows"][0]["title"], "Tour Saturday")
        self.assertEqual(history["rows"][0]["on the site"], "not an article yet")
        # …and it can be brought across, which is the only way it ever gets a page.
        self.assertIn("Put a sent issue on your website", _by_title(panes["newsletter"]))

    def test_newest_first(self) -> None:
        panes = self._panes(
            _Site((_piece(slug="a"), _piece(slug="b"))),
            sent={"a": {"sent_at": "2026-01-01T00:00:00Z", "subject": "older"},
                  "b": {"sent_at": "2026-09-01T00:00:00Z", "subject": "newer"}})
        rows = _by_title(panes["newsletter"])["Sent to your list"]["rows"]
        self.assertEqual([r["title"] for r in rows], ["newer", "older"])

    def test_only_UNSENT_pieces_are_offered_to_send(self) -> None:
        """A sent issue is terminal and the adapter refuses a second send of one, so
        offering it here would be offering an act that can only refuse."""
        panes = self._panes(_Site((_piece(), _piece(slug="fresh", hidden=True))))
        form = _by_title(panes["newsletter"])["Send to your list"]
        chosen = next(f for f in form["fields"] if f["key"] == "slug")
        self.assertEqual([o["value"] for o in chosen["options"]], ["fresh"])

    def test_the_send_is_typed_and_names_the_count(self) -> None:
        panes = self._panes(_Site((_piece(slug="fresh"),)), sent={})
        form = _by_title(panes["newsletter"])["Send to your list"]
        self.assertEqual(form["submit_action"]["confirm"]["expect"], "send")
        self.assertIn("39 people", form["submit_action"]["confirm"]["text"])
        self.assertIn("news@example.com", form["submit_action"]["confirm"]["text"])
        self.assertIn("39 people", form["submit_label"])

    def test_an_empty_roster_offers_no_send_and_names_the_form(self) -> None:
        panes = self._panes(_Site((_piece(slug="fresh"),)), sent={}, count=0)
        form = _by_title(panes["newsletter"])["Send to your list"]
        self.assertNotIn("submit_action", form)
        self.assertIn("Nobody has subscribed yet", repr(form))
        self.assertIn("example.com", repr(form))

    def test_nothing_written_is_not_the_same_as_everything_sent(self) -> None:
        """Two opposite situations leave this list empty, and the first needs to be told
        to write something rather than that everything is done."""
        form = _by_title(self._panes(_Site(()), sent={})["newsletter"])["Send to your list"]
        self.assertIn("nothing written yet", repr(form))


class OpeningOnePiece(unittest.TestCase):
    def _open(self, site, slug="on_playing_the_light", sent=None):
        payload = PimDesign().build_panel_payload(
            sandbox_id="pim",
            host_context={"private_dir": None, "port": lambda _p: site,
                          "sent_issues": sent or {}},
            extra_query={TAB_QUERY: "articles", PIECE_QUERY: slug})
        return _by_title({t["id"]: t["panel_payload"]
                          for t in payload["tabs"]}["articles"])

    def test_the_edit_form_is_PREFILLED_with_the_writing(self) -> None:
        forms = self._open(_Site((_piece(),)))
        body = next(f for f in forms["Edit this post"]["fields"] if f["key"] == "body")
        self.assertEqual(body["value"], BODY)

    def test_the_edit_names_the_piece_it_replaces(self) -> None:
        forms = self._open(_Site((_piece(),)))
        self.assertEqual(forms["Edit this post"]["submit_action"]["fixed"]["prior_slug"],
                         "on_playing_the_light")

    def test_a_draft_stays_a_draft_when_it_is_edited(self) -> None:
        forms = self._open(_Site((_piece(hidden=True),)))
        self.assertIs(forms["Edit this post"]["submit_action"]["fixed"]["hidden"], True)

    def test_EDITING_A_SENT_PIECE_FORKS_IT(self) -> None:
        """What went out is in other people's mail and cannot be changed, so the save
        makes a new piece and the sent one stays as the record of what was sent."""
        forms = self._open(
            _Site((_piece(),)),
            sent={"on_playing_the_light": {"sent_at": "2026-08-01T09:00:00Z"}})
        action = forms["Edit this post"]["submit_action"]
        self.assertEqual(action["fixed"]["fork_of"], "on_playing_the_light")
        self.assertNotIn("prior_slug", action["fixed"],
                         "a fork must not retire the piece it came from")
        self.assertIs(action["fixed"]["hidden"], True)
        self.assertEqual(forms["Edit this post"]["submit_label"], "Save as a new piece")

    def test_the_fork_says_so_BEFORE_the_author_types(self) -> None:
        forms = self._open(
            _Site((_piece(),)),
            sent={"on_playing_the_light": {"sent_at": "2026-08-01T09:00:00Z"}})
        body = next(f for f in forms["Edit this post"]["fields"] if f["key"] == "body")
        self.assertIn("2026-08-01", body["label"])
        self.assertIn("NEW piece", body["label"])

    def test_delete_carries_the_address_and_a_typed_confirmation(self) -> None:
        forms = self._open(_Site((_piece(),)))
        action = forms["Delete this post"]["submit_action"]
        self.assertEqual(action["fixed"]["slug"], "on_playing_the_light")
        self.assertEqual(action["confirm"]["expect"], "retire")

    def test_the_piece_carries_NO_send_and_NO_visibility_control(self) -> None:
        """Both moved to the tab that is ABOUT them, where the choice is made against a
        list of what has already gone out or is already up. This pane offered "send to
        subscribers" with no sight of what had been sent."""
        forms = self._open(_Site((_piece(),)))
        self.assertEqual(set(forms) - {None},
                         {"On Playing the Light", "Edit this post", "Delete this post"})

    def test_a_stale_address_falls_back_to_the_gallery(self) -> None:
        forms = self._open(_Site((_piece(),)), slug="gone")
        self.assertIn("Your writing", forms)


class OldLinksStillLand(unittest.TestCase):
    def test_the_retired_tab_names_open_the_nearest_thing(self) -> None:
        """`posts` was "what is published", which is now Website; `drafts` was "everything
        else, and where a new one starts", which is Articles."""
        for old, now in (("posts", "website"), ("drafts", "articles"),
                         ("writing", "articles"), ("pages", "website")):
            with self.subTest(old=old):
                payload, _panes_by_id = _panes(_Site(()), **{TAB_QUERY: old})
                self.assertEqual(payload["active_tab"], now)

    def test_an_unknown_tab_falls_to_the_default(self) -> None:
        payload, _ = _panes(_Site(()), **{TAB_QUERY: "nonsense"})
        self.assertEqual(payload["active_tab"], DEFAULT_TAB)


if __name__ == "__main__":
    unittest.main()
