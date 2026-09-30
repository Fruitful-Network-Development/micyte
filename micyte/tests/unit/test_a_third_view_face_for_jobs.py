"""A THIRD face for the jobs table — cards beside the table and the map.

The operator, 2026-09-02: *"a subtab of preview cards that TOGGLES to a map view. Opening a
job in either setting shows the SAME job profile view. One view, two indexes."*

Half of that already shipped. ``_record_view.views`` has always taken any number of
``(id, label)`` pairs and ``viewSwitchHtml`` has always drawn all of them — but the switch
that ACTED on the choice named its two faces by hand::

    viewState = asText(id) || "table";
    if (mapWrap) mapWrap.hidden = viewState !== "map";
    if (tableWrap) tableWrap.hidden = viewState === "map";

so a third id drew a PRESSED BUTTON and hid nothing: the table stayed on screen under the
gallery's label. The server was correct throughout, and a segmented control cannot show you
that the face did not change — which is why the switch is pinned in the browser, in
``fnd_app/tests/e2e/test_three_faces_of_the_jobs_table.py``, and not only here.

This file pins the three things that are decidable without a browser:

* what a card SAYS — one per row, in the rows' own order, blanks dropped;
* that a card names only columns a job row actually carries, the rule the facets already
  follow (a facet on a column nobody builds is a dropdown that offers nothing forever;
  a card line on one is a line that never draws, and more quietly, because a blank line
  is dropped by design);
* that every face the switch OFFERS is a face the renderer can build — read off the JS
  source, because the two declarations live in two files and nothing else compares them.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools._record_view import view_param, views
from micyte.tools._row_gallery import card_gallery, card_line
from micyte.tools.job_manager import JOB_ROW_KEYS, JobManager

RENDERERS_JS = (
    REPO_ROOT / "fnd_app" / "instances" / "_shared" / "portal_host" / "static"
    / "v2_portal_workbench_renderers.js"
)
PORTAL_CSS = (
    REPO_ROOT / "fnd_app" / "instances" / "_shared" / "portal_host" / "static" / "portal.css"
)

#: Two jobs and a third with nothing on it but a date — the shape that decides whether a
#: card drops a blank line or draws an empty one.
ROWS = [
    {"datum_address": "4-1-1", "customer": "Jane Doe", "address": "77 Parmalee Dr, Hudson",
     "pay": "$240.00", "date": "18 Aug 2026", "trade": "Pressure washing",
     "stage": "Booked", "belongs": "", "arrived": "Referral", "note": "front walk"},
    {"datum_address": "4-1-2", "customer": "", "address": "12 Main St, Kent",
     "pay": "", "date": "20 Aug 2026", "trade": "Gutters",
     "stage": "", "belongs": "Spring contract", "arrived": "", "note": ""},
]


def _gallery(rows=None):
    return card_gallery(
        rows if rows is not None else ROWS,
        title_column="customer", subtitle_column="address", badge_column="pay",
        lines=(card_line("date"), card_line("trade"), card_line("stage"),
               card_line("belongs", label="project"),
               card_line("arrived", label="lead"), card_line("note")),
        untitled_text="(no customer named)",
        empty_text="No jobs match — clear a filter, or book one from the table.")


class WhatACardSays(unittest.TestCase):
    def test_one_card_per_row_in_the_rows_own_order(self) -> None:
        """The gallery is an INDEX of the same rows, not a selection from them.

        Order included: the jobs table is organized by date (`by_date`), and a gallery in
        a different order would be a second answer to "what happened most recently".
        """
        gallery = _gallery()
        self.assertEqual(gallery["card_count"], len(ROWS))
        self.assertEqual([c["datum_address"] for c in gallery["cards"]],
                         [r["datum_address"] for r in ROWS])

    def test_a_card_opens_the_row_it_was_built_from(self) -> None:
        """ONE view, two indexes: the card carries the row's own address.

        The renderer's `data-inv-open` reads this and lands on `openRecord`, which is the
        same function the table's pencil calls — so there is no second seeding rule that
        could drift into showing a different record from the two indexes.
        """
        for card, row in zip(_gallery()["cards"], ROWS, strict=True):
            self.assertEqual(card["datum_address"], row["datum_address"])

    def test_a_blank_line_is_DROPPED_not_drawn_empty(self) -> None:
        """A card is a preview; the table is the complete index.

        Row two has no stage, no lead and no note. Drawing three em-dashes on a card is
        noise, while the same blanks in a TABLE cell are how the operator sees the gap —
        which is the reason both faces exist rather than one replacing the other.
        """
        second = _gallery()["cards"][1]
        drawn = {line["label"] for line in second["lines"]}
        self.assertEqual(drawn, {"date", "trade", "project"})
        self.assertNotIn("", {line["value"] for line in second["lines"]})

    def test_a_line_label_may_differ_from_its_column(self) -> None:
        """`belongs` is a row key and *project* is what a person reads.

        The same value/label split `facet` states, and the jobs table has four columns
        whose heading is not their key.
        """
        second = _gallery()["cards"][1]
        self.assertEqual([line for line in second["lines"] if line["label"] == "project"],
                         [{"label": "project", "value": "Spring contract"}])

    def test_an_unnamed_customer_gets_a_SENTENCE_not_a_blank_heading(self) -> None:
        """A job at a house the registrar has nobody on yet is a real row.

        Left blank, its card heads with nothing and reads as a rendering fault — so the
        caller supplies what the heading says instead.
        """
        cards = _gallery()["cards"]
        self.assertEqual(cards[0]["title"], "Jane Doe")
        self.assertEqual(cards[1]["title"], "(no customer named)")

    def test_the_subtitle_and_badge_are_the_cells_the_caller_named(self) -> None:
        first = _gallery()["cards"][0]
        self.assertEqual(first["subtitle"], "77 Parmalee Dr, Hudson")
        self.assertEqual(first["badge"], "$240.00")
        # Row two has no pay: an empty badge, not a "$" with nothing after it.
        self.assertEqual(_gallery()["cards"][1]["badge"], "")

    def test_a_row_with_no_address_gets_a_card_with_no_address(self) -> None:
        """A button that opens nothing is worse than an absent one.

        The renderer draws that card as a plain box rather than a dead control; what makes
        that decidable is the empty `datum_address` here.
        """
        gallery = _gallery([{"customer": "Nobody", "date": "1 Jan 2026"}])
        self.assertEqual(gallery["cards"][0]["datum_address"], "")

    def test_an_empty_gallery_says_something_for_whoever_reached_it(self) -> None:
        """A gallery narrowed to nothing and a book with no work in it look identical.

        Only one of them is the operator's own filter, so the sentence names the way out.
        """
        gallery = _gallery([])
        self.assertEqual(gallery["card_count"], 0)
        self.assertIn("clear a filter", gallery["empty_text"])

    def test_it_offers_no_image_slot_at_all(self) -> None:
        """PHOTOGRAPHS ARE NOT AVAILABLE, and an empty frame would say they nearly are.

        `job_event` is `msn_id, site_msn, lcl_id, utc+, price?, title?, project_ref?,
        status_ref?, lead_ref?` — no image field, no attachment field — and `save_job` has
        no path that would write one. So a card carries no image key rather than one that
        is always empty, which would claim the field exists and is unset. Adding
        photographs is a change to the archetype and to the write route; this test is here
        to be DELETED by that change rather than to forbid it.
        """
        card = _gallery()["cards"][0]
        for absent in ("image", "image_url", "photo", "thumbnail", "media"):
            self.assertNotIn(absent, card)


class TheJobsTableDeclaresThreeFaces(unittest.TestCase):
    def test_the_switch_offers_table_cards_and_map(self) -> None:
        ids = [i for i, _label in JobManager.view_options]
        self.assertEqual(ids, ["table", "gallery", "map"])

    def test_the_default_face_is_still_the_table(self) -> None:
        """A tab that opened on a face nobody asked for would be a changed default.

        `views` falls back to the FIRST offered pair, so the order of `view_options` is
        the default; asserted through `views` rather than by reading index 0, because it
        is `views` that decides.
        """
        control = views("jobs", query={}, options=JobManager.view_options)
        self.assertEqual(control["value"], "table")

    def test_the_THIRD_id_survives_the_query_it_is_asked_with(self) -> None:
        """The regression this task exists for, on the server side.

        `views` always accepted N pairs; it was the renderer that acted on two. Pinned
        anyway, because the fix is worthless if the id stops round-tripping.
        """
        control = views("jobs", query={view_param("jobs"): "gallery"},
                        options=JobManager.view_options)
        self.assertEqual(control["value"], "gallery")
        self.assertEqual([o["id"] for o in control["options"] if o["active"]], ["gallery"])
        self.assertNotIn("unknown", control)

    def test_an_id_nobody_offers_falls_back_and_SAYS_so(self) -> None:
        control = views("jobs", query={view_param("jobs"): "calendar"},
                        options=JobManager.view_options)
        self.assertEqual(control["value"], "table")
        self.assertEqual(control["unknown"], "calendar")

    def test_a_card_only_names_columns_a_job_row_carries(self) -> None:
        """A card line on a column nobody BUILDS is a line that never draws.

        Quietly, too: a blank line is dropped by design, so a renamed column costs a line
        and reports nothing. The same rule the facets follow — see
        `test_a_facet_column_is_a_key_the_row_actually_carries`.
        """
        named = ([JobManager.card_title_column, JobManager.card_subtitle_column,
                  JobManager.card_badge_column]
                 + [column for column, _label in JobManager.card_lines])
        for column in named:
            self.assertIn(
                column, JOB_ROW_KEYS,
                f"the card reads row key {column!r} and `_job_rows` builds no such key, so "
                f"the line is silently dropped from every card (row keys: {JOB_ROW_KEYS})")


def _code_only(source: str) -> str:
    """The JS with its whole-line ``//`` comments removed.

    Because the comment that RECORDS a defect quotes the defect. This file's first cut
    asserted ``"mapWrap.hidden" not in js`` and went red against the renderer's own
    explanation of why ``mapWrap`` is gone — matching prose for a directive, the same trap
    that once sent real mail. Whole-line only: an inline ``//`` cannot be stripped without
    parsing, and a URL inside a string would go with it.
    """
    return "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("//"))


class EveryDeclaredFaceHasARenderer(unittest.TestCase):
    """The switch is declared in Python and ACTED ON in JavaScript, in two files.

    Nothing but this compares them, which is exactly how the two-face switch survived a
    payload that could already describe three.

    Every assertion here goes through ``_present`` / ``_absent`` rather than
    ``assertIn``/``assertNotIn``: the haystack is a 220 KB source file, and unittest prints
    the haystack on failure — 220 KB of JavaScript in place of the one line that is wrong.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.js = RENDERERS_JS.read_text(encoding="utf-8")
        cls.code = _code_only(cls.js)
        cls.css = PORTAL_CSS.read_text(encoding="utf-8")

    def _present(self, needle: str, why: str) -> None:
        self.assertTrue(needle in self.code, f"{needle!r} is not in the renderer — {why}")

    def _absent(self, needle: str, why: str) -> None:
        self.assertFalse(needle in self.code, f"{needle!r} is back in the renderer — {why}")

    def test_each_offered_id_has_a_container_the_renderer_emits(self) -> None:
        for face, _label in JobManager.view_options:
            self._present(
                f'data-inv-face="{face}"',
                f"the jobs switch offers {face!r} and no container carries it, so the "
                f"button presses and nothing changes")

    def test_the_switch_no_longer_names_its_faces_BY_HAND(self) -> None:
        """The defect itself, spelled out so a revert cannot pass.

        ``mapWrap.hidden = viewState !== "map"`` beside ``tableWrap.hidden = viewState ===
        "map"`` was the two-face switch. Its replacement hides every registered face that is
        not the chosen one, so a fourth face is a container and a payload key and no change
        to `setView` at all.
        """
        # `.hidden`, not the bare names: `v2-tableWrap` is a CLASS half this file's other
        # renderers use, and a substring match on `tableWrap` would report those.
        self._absent("mapWrap.hidden", "the switch is naming one face by hand again")
        self._absent("tableWrap.hidden", "the switch is naming one face by hand again")
        self._present(
            "faces[key].hidden = key !== viewState",
            "setView no longer hides every face but the chosen one")

    def test_a_card_and_a_table_row_open_through_ONE_function(self) -> None:
        """"Opening a job in either setting shows the SAME job profile view."

        Two bindings, one target. A second seeding path is what would let the two indexes
        open different-looking records from the same row.
        """
        self._present("function openRecord(addr)", "there is no one place a record opens")
        self._present('openRecord(b.getAttribute("data-inv-edit"))',
                      "the table's pencil stopped going through it")
        self._present('openRecord(b.getAttribute("data-inv-open"))',
                      "a card stopped going through it")

    def test_opening_from_another_face_brings_the_TABLE_forward(self) -> None:
        """The edit row is drawn inside the table BODY.

        Opening a card without switching faces first would put the form behind a hidden
        container — the operator clicks a card and watches nothing happen.
        """
        self._present('if (viewState !== "table") setView("table");',
                      "a form can now open behind a hidden face")
        self._absent('if (viewState === "map") setView("table");',
                     "the check covers one of the two non-table faces again")

    def test_the_card_face_has_its_stylesheet(self) -> None:
        """A face whose classes are unstyled lays out as a column of unstyled spans."""
        for rule in (".v2-cardGal", ".v2-cardGal__grid", ".v2-cardGal__card",
                     ".v2-cardGal__title", ".v2-cardGal__badge", ".v2-cardGal__line",
                     ".v2-cardGal__empty", ".v2-invTable__facegap"):
            self.assertIn(rule, self.css, f"{rule} missing from portal.css")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
