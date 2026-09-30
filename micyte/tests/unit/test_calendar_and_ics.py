"""The generalized calendar and the .ics it exports.

`agro_calendar` read a module CONSTANT naming the registrar, so a handyman instance opening
the calendar saw nothing — its jobs are not in the registrar and nothing else was looked at.
The general one resolves its sources from the sandbox through the CLASS tree, which is the
thing Phase 1 was for.

The .ics half is tested against RFC 5545 rather than eyeballed, because every one of these
is a real interoperability failure that looks like bad data: a bare LF file is rejected
outright, an unescaped comma truncates a summary mid-word in some clients, and an overlong
unfolded line can be dropped.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from micyte.core.datum_ops import viewscope as vs
from micyte.tools import _ics
from micyte.tools.calendar_viewer import LOG_CLASS, TIME_FIELD, CalendarViewer

WHEN = datetime(2026, 3, 16, 9, 0, tzinfo=UTC)

# --- a stub store, so the CLASS filter can be exercised without a 545 MB catalog ----------
#
# It answers only the three things `log_documents` asks: the archetype library, the rows of
# one sandbox, and nothing else. Built from the mint scripts' own declarations so the
# archetypes and classes under test are the REAL ones — a hand-written pair would agree with
# whatever this test expected and prove nothing.

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops.labels import encode_label_bits as _t_raw

_NS = _fr.REGISTRAR
MSN = "rf." + _fr.address(_NS, "msn_id")
SITE = "rf." + _fr.RESERVED_NEW_FIELDS[_NS]["site_msn"]
LCL = "rf." + _fr.address(_NS, "lcl_id")
UTC = "rf." + _fr.address(_NS, "utc")
TITLE = "rf." + _fr.address(_NS, "title")
COORD = "rf." + _fr.address(_NS, "coordinate")
MSSB = "rf." + _fr.address(_NS, "mss_source_binary")
RKIND = "rf." + _fr.address(_NS, "resource_kind")


def _t(text: str) -> str:
    return _t_raw(text)


def _mint_modules():
    import importlib.util
    import pathlib as _p
    import sys as _s

    root = _p.Path(__file__).resolve().parents[3] / "scripts"
    out = []
    for name in ("mint_archetype_sandbox", "mint_class_library"):
        spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        _s.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            _s.modules.pop(name, None)
        out.append(module)
    return out


class _StubDoc:
    def __init__(self, name, rows, metadata):
        self.document_id = f"lv.3-2-3.archetype.{name}." + "0" * 64
        self.canonical_name = name
        self.document_metadata = metadata
        self.rows = rows
        self.is_anchor = False


class _StubRow:
    def __init__(self, address, raw):
        self.datum_address = address
        self.raw = raw


class _StubStore:
    """Answers the archetype library from the mint declarations, and one sandbox's rows."""

    def __init__(self, documents):
        self._documents = documents
        archetypes_mod, classes_mod = _mint_modules()
        library = []
        for archetype in archetypes_mod.ARCHETYPES:
            head = [f"{archetype.layer}-1-1"]
            for slot in archetype.slots:
                marker = (slot.literal if slot.kind == archetypes_mod.POSITION
                          else archetypes_mod.slot_marker(slot.name))
                filler = "0" if slot.required else ""
                for cell in range(2 if slot.run else 1):
                    head += [marker, "" if (cell and slot.run_optional) else filler]
            library.append(_StubDoc(
                archetype.name,
                [_StubRow(f"{archetype.layer}-1-1", [head, [archetype.name]])],
                {"role": "archetype"}))
        from micyte.core.datum_ops import archetype_class as _ac

        for klass in classes_mod.CLASSES:
            model = _ac.ArchetypeClass(
                name=klass.name, organizer=klass.organizer, container=klass.container,
                parent=klass.parent, members=klass.members,
                slots=tuple(_ac.SlotSpec(group=g, primitive=p, field=f) for g, p, f in klass.slots))
            library.append(_StubDoc(
                _ac.class_name(klass.name),
                [_StubRow(r["datum_address"], r["raw"]) for r in _ac.build_class_rows(model)],
                {"role": "class"}))
        self._library = library

    def read_documents_by_sandbox(self, *, tenant_id, sandbox):
        return self._library if sandbox == "archetype" else []

    def iter_document_rows_by_sandbox(self, *, tenant_id, sandbox):
        for name, rows in self._documents.items():
            for head in rows:
                yield (f"lv.3-2-3.{sandbox}.{name}.0", name, [head])





class IcsFormatTests(unittest.TestCase):
    def test_every_line_ends_CRLF(self) -> None:
        """A bare-LF calendar file is refused outright by several importers."""
        out = _ics.event_ics(uid="u", starts=WHEN, summary="a job")
        self.assertEqual(out.count("\r\n"), out.count("\n"))
        self.assertTrue(out.endswith("\r\n"))

    def test_text_values_are_escaped(self) -> None:
        """An unescaped comma silently truncates the summary in some clients, which reads
        as the data being wrong rather than the file."""
        out = _ics.event_ics(
            uid="u", starts=WHEN, summary="front walk, driveway; steps",
            description="one\ntwo", location="a\\b")
        self.assertIn("front walk\\, driveway\\; steps", out)
        self.assertIn("one\\ntwo", out)
        self.assertIn("a\\\\b", out)

    def test_the_backslash_is_escaped_FIRST(self) -> None:
        """Escaping the backslash after the comma would double the escape it just wrote."""
        out = _ics.event_ics(uid="u", starts=WHEN, summary="a\\,b")
        self.assertIn("a\\\\\\,b", out)

    def test_lines_fold_at_75_OCTETS_not_characters(self) -> None:
        """The limit is octets, so accented text folds earlier than its length suggests."""
        folded = _ics.fold("SUMMARY:" + "é" * 90)
        for line in folded.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), _ics.FOLD_OCTETS)
        # and it never splits a character in half
        self.assertEqual(folded.replace("\r\n ", ""), "SUMMARY:" + "é" * 90)

    def test_a_continuation_line_starts_with_a_space(self) -> None:
        rest = _ics.fold("DESCRIPTION:" + "x" * 200).split("\r\n")[1:]
        self.assertTrue(rest)
        for line in rest:
            self.assertTrue(line.startswith(" "), line[:20])

    def test_the_uid_is_stable_so_a_re_import_UPDATES(self) -> None:
        """Two exports of one job must carry one UID, or a client makes two events."""
        first = _ics.event_ics(uid="bpw/job_log/4-1-2", starts=WHEN, now=WHEN)
        second = _ics.event_ics(uid="bpw/job_log/4-1-2", starts=WHEN, now=WHEN)
        self.assertEqual(first, second)
        self.assertIn("UID:bpw/job_log/4-1-2", first)

    def test_an_event_always_has_an_end(self) -> None:
        """A zero-length event renders as a pin rather than an appointment."""
        out = _ics.event_ics(uid="u", starts=WHEN, ends=WHEN)
        self.assertIn("DTSTART:20260316T090000Z", out)
        self.assertIn("DTEND:20260316T110000Z", out)

    def test_the_filename_is_safe_and_findable(self) -> None:
        name = _ics.filename_for("pressure washing, front walk", WHEN)
        self.assertTrue(name.startswith("2026-03-16-"))
        self.assertTrue(name.endswith(".ics"))
        self.assertNotIn("/", name)
        self.assertNotIn(",", name)


class CalendarPostureTests(unittest.TestCase):
    def test_it_reads_by_CLASS_not_by_document_name(self) -> None:
        """The whole decoupling. A sandbox names its own documents — `job_log` here is
        `work_log` in the next instance — so a list of names would be a per-instance
        configuration nobody maintains."""
        source = (
            __import__("pathlib").Path(__file__).resolve().parents[3]
            / "micyte/tools/calendar_viewer.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(LOG_CLASS, "log")
        self.assertNotIn('"job_log"', source, "a document name is hardcoded")
        self.assertIn("lineage_of", source)

    def test_a_source_must_declare_a_TIME_field(self) -> None:
        """A `sources` manifest classes under `network_log` and carries no `utc` at all.
        Without this the calendar reported 471 UNDATED rows for a document that could never
        have produced an event — a fault note where there is no fault.

        Exercised through `log_documents` rather than asserted as a constant. The first cut
        of this test only checked `TIME_FIELD == "utc"`, which passes whether the filter
        exists or not — a guard that cannot fail, caught by mutating the filter away and
        watching it stay green.
        """
        from micyte.tools.calendar_viewer import log_documents

        self.assertEqual(TIME_FIELD, "utc")
        store = _StubStore({
            # a job log: `job_event` declares utc -> a source
            "job_log": [["4-1-1", MSN, "3-2-3", SITE, "3-2-3", LCL, "1-1", UTC, "0-0-0-1-1-0-0-0"]],
            # a sources manifest: `source_entry` declares NO utc -> not a source
            "sources": [["4-1-1", TITLE, _t("x"), COORD, "3-1", MSSB, "ab", RKIND, _t("k")]],
        })
        found = log_documents(store, tenant_id="fnd", sandbox="registrar")
        self.assertIn("job_log", found)
        self.assertNotIn(
            "sources", found,
            "a document whose archetype declares no time field must not be a calendar source",
        )

    def test_a_cadence_is_NOT_flattened_into_a_moment(self) -> None:
        """`ic_stamp` is a weekday and an hour that RECUR. Rendering that as a single
        appointment would misstate a farm's opening hours."""
        source = (
            __import__("pathlib").Path(__file__).resolve().parents[3]
            / "micyte/tools/calendar_viewer.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('values.get("ic_stamp"', source)

    def test_it_is_the_calendar_instrument_and_follows_the_instance(self) -> None:
        """The `core` rail flag left with the launcher rail (2026-08-21); the calendar's
        instance-wide posture is now its INSTRUMENT declaration, which must name the
        registered tool id — the literal "calendar_viewer" sat there for a day and the
        instrument face answered "no reader installed"."""
        from micyte.tools._instruments import INSTRUMENTS_BY_ID

        entry = INSTRUMENTS_BY_ID["calendar"]
        self.assertEqual(entry.tool_id, CalendarViewer.tool_id)

    def test_it_says_what_it_does_not_hold(self) -> None:
        """A calendar that silently omits a source reads as broken rather than scoped."""
        from micyte.tools.calendar_viewer import EXCLUDED_SOURCES

        self.assertTrue(EXCLUDED_SOURCES)
        for entry in EXCLUDED_SOURCES:
            self.assertTrue(entry["source"] and entry["surface"])


class SymbolPrimitiveTests(unittest.TestCase):
    def test_icon_ref_draws_rather_than_printing_its_filename(self) -> None:
        self.assertIn("symbol", vs.PRIMITIVES)
        self.assertEqual(vs.default_primitive("icon_ref"), "symbol")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class QuiarCompositeTests(unittest.TestCase):
    """The composite's tab keys must be the ones the RENDERER reads.

    `renderTabbed` reads `tab.panel_payload` and `tab.tool_id`. The first cut emitted
    `payload`, and the result was a hub with the right title, the right three tabs, and
    "Jobs — no sub-tools yet" in the body — a payload correct by its own lights that the
    client could not read. No amount of checking the payload would have found it; only
    opening it in a browser did, which is why this asserts against the JS.
    """

    def test_the_tab_keys_are_the_ones_the_renderer_reads(self) -> None:
        import pathlib

        from micyte.tools.quiar import TABS, Quiar

        js = (
            pathlib.Path(__file__).resolve().parents[3]
            / "fnd_app/instances/_shared/portal_host/static/v2_portal_workbench_renderers.js"
        ).read_text(encoding="utf-8")
        self.assertIn("tab.panel_payload == null", js, "renderTabbed changed shape")
        self.assertIn("paintPanelInto(tab.panel_payload, bodyNode, tab.tool_id)", js)

        payload = Quiar().build_panel_payload(
            authority_db_file=None, sandbox_id="", document_id="", datum_address="")
        self.assertEqual(payload["container"], "tabbed")
        self.assertEqual([t["id"] for t in payload["tabs"]], [t[0] for t in TABS])
        for tab in payload["tabs"]:
            with self.subTest(tab=tab["id"]):
                # the key the renderer reads, and never null — a null one is the scaffold
                self.assertIn("panel_payload", tab)
                self.assertIsNotNone(tab["panel_payload"])
                self.assertTrue(tab["tool_id"])
                self.assertNotIn("payload", tab, "the key the renderer does NOT read")

    def test_a_pane_that_fails_does_not_blank_the_hub(self) -> None:
        """One empty tab is legible; a blank hub is not."""
        from micyte.tools.quiar import TABS, Quiar

        payload = Quiar().build_panel_payload(
            authority_db_file=None, sandbox_id="nope", document_id="", datum_address="")
        # Against TABS, not against a literal count. This said `3` and the fourth tab broke
        # it — a test that has to be edited to add a tab is a test that reports the ADDITION
        # as the defect. What is actually being asserted is "every declared tab is here and
        # carries a payload", and that is what it now says.
        self.assertEqual(len(payload["tabs"]), len(TABS))
        for tab in payload["tabs"]:
            self.assertIsNotNone(tab["panel_payload"])


class SharedCalendarGridTests(unittest.TestCase):
    """One grid, two calendars.

    The month cells, the leading blanks, the seven days of a week and what to call them are
    pure geometry, and they were written out twice — once in `renderAgroCalendar` and once
    nowhere at all, because the general calendar rendered a flat list of days instead. The
    moment it became a calendar the geometry would have been copied, and a copy is what
    starts drifting.

    What is deliberately NOT shared is the event model. A registrar `event_log_entry` carries
    an `ic_stamp` — a CADENCE that recurs — and a `job_event` carries a `utc`, ONE MOMENT.
    `calendar_viewer`'s docstring is explicit that flattening one into the other lies about
    when somebody's driveway gets washed. These tests pin the split, not just the sharing.
    """

    def _js(self) -> str:
        import pathlib

        return (
            pathlib.Path(__file__).resolve().parents[3]
            / "fnd_app/instances/_shared/portal_host/static"
            / "v2_portal_workbench_renderers.js"
        ).read_text(encoding="utf-8")

    def test_the_grid_is_a_module_the_calendar_reaches(self) -> None:
        """The grid stayed a global module when the network calendar retired
        (2026-08-16): this file holds THREE separate IIFEs with different helper
        sets, so a plain function in one is invisible in the others — the same
        reason __MYCITE_V2_CONTAINER_RENDERERS is a global rather than a variable.
        renderGeneralCalendar lives in a later IIFE than the grid."""
        js = self._js()
        self.assertIn("window.__MYCITE_V2_CALENDAR_GRID = CalendarGrid", js)
        self.assertIn("window.__MYCITE_V2_CALENDAR_GRID;", js)
        self.assertIn("Grid.monthGrid({", js)
        self.assertIn("Grid.weekGrid({", js)

    def test_neither_calendar_builds_its_own_month_cells(self) -> None:
        """The leading-blanks loop is the tell. It appeared once in the agro calendar and
        would have been the first thing copied into the second."""
        js = self._js()
        self.assertEqual(
            js.count('v2-cal__cell is-blank'), 1,
            "a second month-cell builder exists; the grid was copied rather than shared")

    def test_the_general_calendar_draws_a_grid_and_not_only_a_list(self) -> None:
        """The operator's finding, asserted: the Calendar tab was a list of days, and a list
        answers 'what is booked' where a calendar answers 'when am I free'."""
        js = self._js()
        general = js[js.index("function renderGeneralCalendar"):]
        for marker in ('data-cal2-view="month"', 'data-cal2-view="week"',
                       "data-cal2-day", "data-cal2-back"):
            with self.subTest(marker=marker):
                self.assertIn(marker, general)

    def test_the_two_event_models_are_still_apart(self) -> None:
        """The general calendar reads `starts`/`day` (moments). It must not acquire the
        cadence vocabulary — `weekdays`, `start_min` — which would mean it had started
        flattening a recurrence into an appointment."""
        js = self._js()
        general = js[js.index("function renderGeneralCalendar"):]
        for cadence in ("ev.weekdays", "start_min", "ic_stamp"):
            with self.subTest(field=cadence):
                self.assertNotIn(cadence, general)


class CalendarRendererTests(unittest.TestCase):
    """Every container a tool emits must have a renderer registered for it.

    The general calendar shipped without one and painted "No renderer for calendar." — a
    correct payload, a registered tool, a rail entry, and nothing on screen. The container
    name is the join between the two halves and nothing checked it.
    """

    #: EVERY static file, not just the workbench renderers. `export_preview` is registered
    #: in v2_portal_viewscope.js, so a sweep reading one file reported it as missing — a
    #: guard that cries wolf gets muted, which is worse than no guard.
    def _renderers_js(self) -> str:
        import pathlib

        static = (
            pathlib.Path(__file__).resolve().parents[3]
            / "fnd_app/instances/_shared/portal_host/static"
        )
        return "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(static.glob("*.js"))
        )

    def test_the_calendar_container_has_a_renderer(self) -> None:
        from micyte.tools.calendar_viewer import CONTAINER

        self.assertIn(
            f'__MYCITE_V2_CONTAINER_RENDERERS["{CONTAINER}"]', self._renderers_js(),
            f"nothing renders container {CONTAINER!r} — the panel paints 'No renderer for'",
        )

    def test_it_is_the_one_calendar_renderer_left(self) -> None:
        """The network cadence renderer retired WITH its tool (2026-08-16); nothing
        may quietly re-register its container and resurrect the moment-vs-cadence
        flattening the two renderers existed to prevent."""
        js = self._renderers_js()
        self.assertIn("function renderGeneralCalendar", js)
        self.assertNotIn("function renderAgroCalendar", js)
        self.assertNotIn('__MYCITE_V2_CONTAINER_RENDERERS["agro_calendar"]', js)

    def test_every_registered_tool_container_has_a_renderer(self) -> None:
        """The sweep, so the next tool cannot ship the same way."""
        import re

        import micyte.tools as T

        js = self._renderers_js()
        # BOTH spellings: the registry is written `[...]` in one file and `.name` in
        # another, and reading only the first reported a registered renderer as missing.
        registered = set(re.findall(r'__MYCITE_V2_CONTAINER_RENDERERS\["([^"]+)"\]', js))
        registered |= set(re.findall(r"__MYCITE_V2_CONTAINER_RENDERERS\.([A-Za-z_][\w]*)", js))
        # Containers the SHELL owns rather than the workbench renderer file.
        elsewhere = {"composite"}
        missing = []
        for tool in T.all_tools():
            container = str(getattr(tool, "container", "") or "")
            if not container or container in elsewhere or container in registered:
                continue
            missing.append(f"{tool.tool_id} -> {container}")
        self.assertEqual(missing, [], f"no renderer registered for: {missing}")
