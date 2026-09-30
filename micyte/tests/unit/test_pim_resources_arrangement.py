"""PIM's Resources tab shows the arrangement, not just the contents.

The operator's ask: the tab should be "a partial LCL domain graph surface esque ui" where a
client can "create groupings like inserting nodes or changing parent nodes … to control
semantic organization of information", with the default being nodes like `icons`, `images`,
`memos`, `logos`, and under them entries carrying a node address, a title, an icon
reference and the resource artifact being denoted.

Read against the live host on 2026-08-31, FND's `pim` domain is:

    1     documents        (meta root)      rows at layer-4: 4-2-1 .. 4-2-9
    1-1   icons            1-2  documents   (1-3 artifacts does not exist on any tree)
    2     domain
    2-1   resource_type -> 2-1-1 images, 2-1-2 logos

so the branch a client arranges is `resource_type`, and the type nodes already there ARE
the default groupings the ask describes.

RE-AIMED 2026-09-01, WHEN THE DOOR LANDED. This file used to say "it draws the tree; it
does not yet write it … drawing buttons before that exists would put controls in front of
a client that answer 404", and every assertion below was written against a pane whose
`panel_payload` WAS the table. The door now exists — and answers on `/__fnd/pim/
resources/<action>`, the path a client vhost proxies, NOT on the `/portal/api/` spelling
it was first registered under: verified 2026-09-03, that one answers 404 from a client
domain. Both routes reach the same handler; only one reaches a client. So the
pane is a composite — the table, then the three forms that post to it — and the reading
tests are re-pointed at the table INSIDE that composite rather than deleted. The premise
that changed is which container the pane is; what each of those tests measures did not
change at all.

The door's own scoping is pinned by `fnd_app/tests/integration/test_pim_resources_writes_
are_scoped.py`. What is pinned HERE is the half a payload owns: that the forms name the
actions the gate can measure, that they never offer an instance field, and that the two
actions the door would let default to the branch root are drawn with no default.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools.pim_overview import PimOverview


def _pane(graph, types=None):
    facts = {"types": types if types is not None else [
        {"label": "images", "full_type": "image", "rows": [], "why_not": ""}],
        "why_not": "", "graph": graph}
    return PimOverview()._resource_graph_pane(facts)


def _panes(pane):
    """The composite's panes, in the order a client reads them down the column."""
    return [p["panel_payload"] for p in pane["panel_payload"]["panes"]]


def _table(pane):
    """The arrangement TABLE, found by container rather than by position.

    By container, because the forms below it are conditional — an unwritable branch draws
    none and an empty one draws only the add form — and an index that happened to be right
    for one of those three shapes would silently read a form as a table in the others.
    """
    tables = [p for p in _panes(pane) if p["container"] == "record_table"]
    assert len(tables) == 1, f"expected exactly one table pane, got {len(tables)}"
    return tables[0]


def _forms(pane):
    """The write forms, keyed by the ACTION their route ends in."""
    return {p["submit_action"]["route"].rsplit("/", 1)[-1]: p
            for p in _panes(pane) if p["container"] == "record_form"}


def _fields(form):
    return {f["key"]: f for f in form["fields"]}


#: FND's own branch, as read from the live store.
LIVE_GRAPH = {
    "root": "2-1", "branch": "resource_type", "why_not": "",
    "nodes": [
        {"node": "2-1-1", "label": "images", "parent": "2-1", "icon": "", "slot": "",
         "artifact": "", "grouping": True, "address": "4-2-8"},
        {"node": "2-1-2", "label": "logos", "parent": "2-1", "icon": "", "slot": "",
         "artifact": "", "grouping": True, "address": "4-2-9"},
    ],
}


class TheArrangementIsDrawn(unittest.TestCase):
    def test_every_node_becomes_a_row(self) -> None:
        rows = _table(_pane(LIVE_GRAPH))["rows"]
        self.assertEqual([r["address"] for r in rows], ["2-1-1", "2-1-2"])
        self.assertEqual([r["name"].strip() for r in rows], ["images", "logos"])

    def test_a_grouping_says_it_is_one(self) -> None:
        """The 'empty parent node with title' from the ask. A grouping denoting nothing must
        not read as a resource that failed to load."""
        rows = _table(_pane(LIVE_GRAPH))["rows"]
        self.assertTrue(all(r["holds"] == "grouping" for r in rows))

    def test_an_entry_shows_what_it_denotes_and_the_icon_it_wears(self) -> None:
        """The three lcl ids of a resource entry: its own address, its icon, and the thing
        it stands for."""
        graph = {**LIVE_GRAPH, "nodes": LIVE_GRAPH["nodes"] + [
            {"node": "2-1-1-1", "label": "porch.jpg", "parent": "2-1-1",
             "icon": "1-1-4", "slot": "", "artifact": "1-3-2",
             "grouping": False, "address": "4-4-1"},
        ]}
        row = next(r for r in _table(_pane(graph))["rows"] if r["address"] == "2-1-1-1")
        self.assertEqual(row["holds"], "1-3-2")
        self.assertEqual(row["icon"], "1-1-4")

    def test_a_document_denotation_reads_the_same_way(self) -> None:
        """`slot` and `artifact` are two readings of ONE denotation, told apart by branch.
        The pane shows whichever the node carries."""
        graph = {**LIVE_GRAPH, "nodes": [
            {"node": "2-1-1-1", "label": "memo", "parent": "2-1-1", "icon": "",
             "slot": "1-2-7", "artifact": "", "grouping": False, "address": "4-3-1"}]}
        self.assertEqual(_table(_pane(graph))["rows"][0]["holds"], "1-2-7")

    def test_depth_is_drawn_from_parent(self) -> None:
        """The indent IS the arrangement. A child must read as under its parent, and the
        depth comes from `parent` rather than from a nested payload — nesting would let the
        order and the structure disagree."""
        graph = {**LIVE_GRAPH, "nodes": LIVE_GRAPH["nodes"] + [
            {"node": "2-1-1-1", "label": "porch.jpg", "parent": "2-1-1", "icon": "",
             "slot": "", "artifact": "1-3-2", "grouping": False, "address": "4-3-1"},
        ]}
        rows = {r["address"]: r["name"] for r in _table(_pane(graph))["rows"]}
        self.assertTrue(rows["2-1-1"].startswith("images"))
        self.assertTrue(rows["2-1-1-1"].startswith("  "),
                        f"child not indented under its parent: {rows['2-1-1-1']!r}")


class ItSaysWhyWhenItCanShowNothing(unittest.TestCase):
    def test_an_empty_branch_invites_rather_than_faults(self) -> None:
        empty = {"root": "2-1", "branch": "resource_type", "why_not": "", "nodes": []}
        text = _table(_pane(empty))["empty_text"]
        self.assertIn("Groupings are folders you name", text)

    def test_a_stated_reason_wins_over_the_invitation(self) -> None:
        """ABSENT is not UNREADABLE. A domain that could not be read must not be reported
        with the same sentence as one that is simply empty."""
        broken = {"root": "", "branch": "resource_type", "nodes": [],
                  "why_not": "this instance's domain could not be read: boom"}
        self.assertIn("could not be read", _table(_pane(broken))["empty_text"])

    def test_a_client_is_never_told_to_run_a_script(self) -> None:
        """The rule the sibling pane learned on Mason Lenehan's instance: a tab a CLIENT
        opens must not name an operator script or an operator-only page."""
        for graph in (LIVE_GRAPH, {"root": "", "nodes": [], "why_not": ""}):
            text = _table(_pane(graph))["empty_text"].lower()
            for forbidden in (".py", "ports", "operator", "script"):
                self.assertNotIn(forbidden, text)


class ItRidesTheTabbedContainer(unittest.TestCase):
    def test_the_pane_is_shaped_like_its_siblings(self) -> None:
        """A COMPOSITE now, not a bare table — the table first, then what acts on it.

        Until the door landed this asserted `container == "record_table"` on the pane
        itself. The sibling shape it is checked against moved with it: `_payment_pane`
        stacks a form over its table in exactly this container.
        """
        pane = _pane(LIVE_GRAPH)
        self.assertEqual(pane["id"], "arrangement")
        self.assertIn("tool_id", pane)
        self.assertEqual(pane["panel_payload"]["container"], "composite")
        self.assertEqual(pane["panel_payload"]["direction"], "column")
        self.assertEqual(_panes(pane)[0]["container"], "record_table")

    def test_the_label_carries_the_count(self) -> None:
        """A row of subtabs with no numbers makes somebody open each to find out which has
        anything in it — the sibling panes' stated rule."""
        self.assertEqual(_pane(LIVE_GRAPH)["label"], "Arrangement (2)")
        self.assertEqual(_pane({"root": "", "nodes": [], "why_not": ""})["label"],
                         "Arrangement")


class TheFormsAreTheDoorsOwnThreeActions(unittest.TestCase):
    """A client arranges the branch, and every control here is one the door will take."""

    def test_the_three_actions_are_offered_under_the_operations_own_names(self) -> None:
        """`add_grouping` would have been DENIED at the gate on every request:
        `authorize_datum_write` judges the tool that DECLARES an action, and an undeclared
        one has no document kind to be measured against. So the form words and the route
        words are the writer's own."""
        forms = _forms(_pane(LIVE_GRAPH))
        self.assertEqual(set(forms), {"define_type", "rename_node", "move_node"})
        for action, form in forms.items():
            self.assertEqual(form["submit_action"]["route"],
                             f"/__fnd/pim/resources/{action}")

    def test_no_form_offers_an_instance_field(self) -> None:
        """THE INSTANCE IS NOT A FIELD. It is resolved from the sign-in header
        server-side; a client who could name it could name somebody else's. Checked by
        FIELD KEY rather than by searching the payload for a substring, because a matcher
        that cannot tell a control from a caption is not checking what it claims to."""
        for form in _forms(_pane(LIVE_GRAPH)).values():
            for key in _fields(form):
                self.assertNotIn(key, ("msn", "msn_id", "instance", "instance_msn",
                                       "sandbox_id", "tenant_id"),
                                 f"{form['title']!r} grew an instance field: {key!r}")

    def test_add_opens_on_the_root_because_the_door_lets_that_default(self) -> None:
        """`define_type` names its PARENT and may omit it — a grouping at the top of the
        branch is the common case, so the select opens there."""
        add = _forms(_pane(LIVE_GRAPH))["define_type"]
        self.assertEqual(_fields(add)["node"]["value"], LIVE_GRAPH["root"])

    def test_rename_and_move_name_their_subject_and_never_default_it(self) -> None:
        """The door reads `node or root` for `define_type` only. If a rename arrived with
        no node it would rename the branch ROOT — which is found by its label, so the
        branch would be orphaned from this very tab, permanently and with a 200. The
        payload's half of that guard is a select that opens on nothing."""
        forms = _forms(_pane(LIVE_GRAPH))
        for action in ("rename_node", "move_node"):
            self.assertEqual(_fields(forms[action])["node"]["value"], "",
                             f"{action} preselected a node to act on")

    def test_move_offers_the_top_level_as_a_value_not_as_the_blank_option(self) -> None:
        """The renderer prepends a blank `—` to every select, and an empty `new_parent` is
        refused as out of scope. So "top level" has to be the root's own id, or the one
        destination a client most wants is the one they cannot choose."""
        move = _forms(_pane(LIVE_GRAPH))["move_node"]
        options = _fields(move)["new_parent"]["options"]
        self.assertEqual(options[0]["value"], LIVE_GRAPH["root"])
        self.assertIn("Top level", options[0]["label"])
        self.assertEqual(_fields(move)["new_parent"]["value"], LIVE_GRAPH["root"])

    def test_move_asks_what_happens_to_the_branch_beneath(self) -> None:
        """`move_node` refuses an unknown `descendants` and says why: 'follow' takes the
        branch, 'promote' lifts the children into the slot it vacated, and the two produce
        different trees. The form draws the choice — in the client's words, and opened on
        the ordinary meaning of 'move' — rather than sending a value they never saw."""
        move = _forms(_pane(LIVE_GRAPH))["move_node"]
        field = _fields(move)["descendants"]
        self.assertEqual(field["value"], "follow")
        self.assertEqual({o["value"] for o in field["options"]}, {"follow", "promote"})

    def test_only_a_node_that_can_take_a_child_is_offered_as_a_parent(self) -> None:
        """`move_node` refuses a parent that holds a writing, and `define_type` the same.
        A filed resource in the destination list would be a refusal offered as a control."""
        graph = {**LIVE_GRAPH, "nodes": LIVE_GRAPH["nodes"] + [
            {"node": "2-1-1-1", "label": "porch.jpg", "parent": "2-1-1", "icon": "",
             "slot": "", "artifact": "1-3-2", "grouping": False, "address": "4-3-1"},
        ]}
        forms = _forms(_pane(graph))
        parents = {o["value"] for o in _fields(forms["define_type"])["node"]["options"]}
        self.assertEqual(parents, {"2-1", "2-1-1", "2-1-2"})
        # The SUBJECT list is wider on purpose: renaming a filed resource is as much this
        # tab's business as renaming a folder, and the door permits it.
        subjects = {o["value"] for o in _fields(forms["rename_node"])["node"]["options"]}
        self.assertIn("2-1-1-1", subjects)

    def test_an_option_says_its_path_so_two_same_named_rows_can_be_told_apart(self) -> None:
        """A browser collapses leading spaces inside an <option>, so the table's indent
        cannot be borrowed. Two groupings each holding a `logo.svg` would otherwise offer
        the client the same word twice and ask them to guess."""
        graph = {**LIVE_GRAPH, "nodes": LIVE_GRAPH["nodes"] + [
            {"node": "2-1-1-1", "label": "logo.svg", "parent": "2-1-1", "icon": "",
             "slot": "", "artifact": "1-3-2", "grouping": False, "address": "4-3-1"},
            {"node": "2-1-2-1", "label": "logo.svg", "parent": "2-1-2", "icon": "",
             "slot": "", "artifact": "1-3-3", "grouping": False, "address": "4-3-2"},
        ]}
        labels = {o["value"]: o["label"] for o in
                  _fields(_forms(_pane(graph))["rename_node"])["node"]["options"]}
        self.assertEqual(labels["2-1-1-1"], "images / logo.svg")
        self.assertEqual(labels["2-1-2-1"], "logos / logo.svg")


class AFormIsDrawnOnlyWhereItCanLand(unittest.TestCase):
    """Built-and-unreachable is the shape this repo keeps paying for. The door refuses
    what it cannot scope, so the pane does not draw what the door would refuse."""

    def test_a_branchless_domain_draws_the_table_and_no_forms(self) -> None:
        """No root means `_resource_branch_scope` returns `no_branch` and every action is
        answered 409. The table still says why, which is the whole content of the tab."""
        for graph in ({"root": "", "nodes": [], "why_not": ""},
                      {"root": "", "nodes": [], "why_not": "domain could not be read"}):
            pane = _pane(graph)
            self.assertEqual(_forms(pane), {})
            self.assertEqual(len(_panes(pane)), 1)

    def test_an_empty_branch_offers_the_one_action_that_works_on_it(self) -> None:
        """There is nothing to rename or to move yet — a picker with no options is a
        control that teaches nothing — but a grouping can be added to the root."""
        forms = _forms(_pane({"root": "2-1", "branch": "resource_type",
                              "why_not": "", "nodes": []}))
        self.assertEqual(set(forms), {"define_type"})

    def test_no_form_names_an_operator_surface_or_a_script(self) -> None:
        """The rule the sibling pane learned on Mason Lenehan's instance, applied to the
        controls as well as to the empty state: a client cannot run a script, and
        `/portal/utilities` is a 404 on every client vhost."""
        for form in _forms(_pane(LIVE_GRAPH)).values():
            words = " ".join(
                [form["title"], form["submit_label"]]
                + [f.get("label", "") for f in form["fields"]]
                + [o["label"] for f in form["fields"] for o in f.get("options", [])]
            ).lower()
            for forbidden in (".py", "operator", "script", "utilities", "sandbox", "lcl"):
                self.assertNotIn(forbidden, words,
                                 f"{form['title']!r} says {forbidden!r} to a client")


if __name__ == "__main__":
    unittest.main()
