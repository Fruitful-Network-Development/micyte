"""The record spec AS DATA — the format a tenant declares its own record types in.

Read and write live in one module, so the round-trip is the central assertion: what
``build_spec_rows`` writes, ``load_specs`` must read back into the identical spec. A format
whose two halves drift produces a document that looks written and reads back subtly wrong.

The refusals carry the rest. A declaration that names a built-in token would leave the bespoke
viewer that reads those rows POSITIONALLY reading the right document with the wrong columns —
which presents as corrupt data rather than as a rejected write, so it is refused on the way in
AND ignored on the way out.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops.record_spec import (
    RECORD_SPEC,
    Field,
    build_spec_rows,
    load_specs,
    parse_field_lines,
    reserved_token,
    spec_for,
    spec_from_declaration,
    specs_for,
)


class _Row:
    def __init__(self, address: str, raw: list) -> None:
        self.datum_address = address
        self.raw = raw


class _Doc:
    def __init__(self, rows: list) -> None:
        self.rows = tuple(rows)


def _doc_for(token: str, lines: str) -> _Doc:
    fields, problems = parse_field_lines(lines)
    assert not problems, problems
    spec = spec_from_declaration(token, fields)
    return _Doc([_Row(a, r) for a, r in build_spec_rows(spec, token)])


class ParseTests(unittest.TestCase):
    def test_a_line_becomes_a_field_with_a_slugged_name_and_a_display_label(self) -> None:
        fields, problems = parse_field_lines("Lead time days | Lead time (days)")
        self.assertEqual(problems, [])
        self.assertEqual(fields[0].name, "lead_time_days")
        self.assertEqual(fields[0].display, "Lead time (days)")

    def test_a_trailing_star_marks_the_field_required(self) -> None:
        fields, _ = parse_field_lines("name* | Supplier\nemail | Email")
        self.assertEqual([f.required for f in fields], [True, False])

    def test_a_field_with_no_label_humanizes_its_name(self) -> None:
        fields, _ = parse_field_lines("lead_time_days")
        self.assertEqual(fields[0].display, "Lead Time Days")

    def test_blank_lines_are_skipped_not_reported(self) -> None:
        fields, problems = parse_field_lines("name\n\n   \nemail\n")
        self.assertEqual([f.name for f in fields], ["name", "email"])
        self.assertEqual(problems, [])

    def test_a_duplicate_and_a_nameless_line_are_reported_by_line_number(self) -> None:
        # Returned, never raised and never dropped: a mistyped line has to be named, or the
        # tenant gets a record type quietly missing a column.
        fields, problems = parse_field_lines("name\nname\n| just a label")
        self.assertEqual([f.name for f in fields], ["name"])
        self.assertEqual(problems, ["line 2: duplicate field 'name'", "line 3: no field name"])


class RoundTripTests(unittest.TestCase):
    def test_what_is_written_reads_back_identical(self) -> None:
        fields, _ = parse_field_lines("name* | Supplier name\nemail | Email\nlead_time_days")
        spec = spec_from_declaration("supplier", fields)
        rows = [_Row(a, r) for a, r in build_spec_rows(spec, "supplier")]
        got, problems = load_specs(_Doc(rows))
        self.assertEqual(problems, [])
        self.assertEqual(got["supplier"], spec)

    def test_a_declared_type_gets_its_own_document_and_the_first_field_titles_it(self) -> None:
        spec = spec_from_declaration("supplier", parse_field_lines("name\nemail")[0])
        self.assertEqual(spec.document, "supplier")
        self.assertEqual(spec.row_family, "4-1")
        self.assertEqual(spec.title_field, "name")

    def test_fields_ride_the_namespaces_title_marker_not_a_literal(self) -> None:
        spec = spec_from_declaration("supplier", parse_field_lines("name")[0])
        self.assertEqual(spec.fields[0].marker, _fr.marker(_fr.FARM, "title"))

    def test_a_second_declaration_appends_beside_the_first(self) -> None:
        first = build_spec_rows(spec_from_declaration("a", parse_field_lines("x\ny")[0]), "a")
        second = build_spec_rows(
            spec_from_declaration("b", parse_field_lines("z")[0]), "b",
            type_start=1, field_start=2)
        addresses = [a for a, _ in first] + [a for a, _ in second]
        self.assertEqual(addresses, ["4-1-1", "4-2-1", "4-2-2", "4-1-2", "4-2-3"])
        specs, problems = load_specs(_Doc([_Row(a, r) for a, r in first + second]))
        self.assertEqual(problems, [])
        self.assertEqual(sorted(specs), ["a", "b"])
        self.assertEqual([f.name for f in specs["a"].fields], ["x", "y"])
        self.assertEqual([f.name for f in specs["b"].fields], ["z"])


class RefusalTests(unittest.TestCase):
    def test_a_builtin_token_is_reserved_and_says_which_reader_owns_it(self) -> None:
        self.assertIn("built-in", reserved_token("contacts"))
        # The refusal SURVIVES the old writer's retirement — the token now names the
        # modern ledger as its owner, so the reason a caller reads is a live one.
        self.assertIn("add_supply", reserved_token("invoice"))
        self.assertEqual(reserved_token("supplier"), "")

    def test_a_document_declaring_a_reserved_token_is_ignored_with_a_reason(self) -> None:
        # The hazard is silent: the declared-table reader reads 4-5 rows positionally, so a redefined
        # `contacts` shape would render the right document with the wrong columns.
        specs, problems = load_specs(_doc_for("contacts", "a\nb"))
        self.assertEqual(specs, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("built-in", problems[0])

    def test_a_type_row_with_no_fields_is_reported_not_returned(self) -> None:
        rows = [r for r in _doc_for("supplier", "name").rows if r.datum_address.startswith("4-1-")]
        specs, problems = load_specs(_Doc(rows))
        self.assertEqual(specs, {})
        self.assertEqual(problems, ["supplier: declared with no fields"])

    def test_field_rows_with_no_type_row_are_reported(self) -> None:
        rows = [r for r in _doc_for("supplier", "name").rows if r.datum_address.startswith("4-2-")]
        specs, problems = load_specs(_Doc(rows))
        self.assertEqual(specs, {})
        self.assertEqual(problems, ["supplier: fields declared with no record type row"])

    def test_a_field_riding_an_unsupported_marker_is_refused_not_written_blind(self) -> None:
        doc = _doc_for("supplier", "name\nemail")
        broken = list(doc.rows)
        head = list(broken[2].raw[0])
        head[8] = "geometry"  # the marker_field slot, decoded as plain text
        broken[2] = _Row(broken[2].datum_address, [head, broken[2].raw[1]])
        specs, problems = load_specs(_Doc(broken))
        self.assertEqual([f.name for f in specs["supplier"].fields], ["name"])
        self.assertEqual(len(problems), 1)
        self.assertIn("unsupported marker", problems[0])


class MergeTests(unittest.TestCase):
    def test_declared_types_join_the_builtins(self) -> None:
        specs = specs_for({"record_spec": _doc_for("supplier", "name\nemail")})
        self.assertEqual(sorted(specs), ["contacts", "supplier"])
        self.assertEqual(specs["contacts"], RECORD_SPEC["contacts"])

    def test_a_sandbox_with_no_spec_document_still_has_the_builtins(self) -> None:
        self.assertEqual(specs_for({}), RECORD_SPEC)
        self.assertEqual(specs_for({"record_spec": None}), RECORD_SPEC)

    def test_the_builtin_lookup_is_unchanged_for_existing_callers(self) -> None:
        self.assertIs(spec_for("contacts"), RECORD_SPEC["contacts"])
        self.assertIsNone(spec_for("supplier"))

    def test_a_field_list_survives_the_document_it_was_written_into(self) -> None:
        # The point of the phase: the shape is data, so reading it needs no Python about it.
        specs = specs_for({"record_spec": _doc_for("equipment", "asset* | Asset\nserial | Serial")})
        spec = specs["equipment"]
        self.assertEqual([f.name for f in spec.fields], ["asset", "serial"])
        self.assertEqual([f.required for f in spec.fields], [True, False])
        self.assertEqual(spec.fields[0], Field("asset", spec.fields[0].marker,
                                               required=True, label="Asset"))


if __name__ == "__main__":
    unittest.main()
