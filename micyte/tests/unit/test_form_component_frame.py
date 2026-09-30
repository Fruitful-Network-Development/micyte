"""Unit tests for build_form_component_frame() — Phase 7 of
TASK-PORTAL-SIMPLIFICATION-2026-05-14.

Covers:
  - field normalization for every supported type
  - boolean coercion (truthy → True, falsy → False)
  - select requires non-empty options
  - string_list value defaults to an empty list and accepts iterables
  - unknown field types raise ValueError
  - duplicate field keys raise ValueError
  - empty fields list raises ValueError
  - submit_action.route is required
  - render_key includes attention_node_id + frame_id
  - tab_id attaches when provided
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.state_machine.nimm.mediate_handlers import (
    FORM_FIELD_TYPES,
    build_form_component_frame,
)


def _submit_action(**overrides) -> dict:
    base = {
        "route": "/__fnd/grantee/save",
        "schema": "mycite.v2.grantee.save.request.v1",
        "payload": {"msn_id": "test-grantee"},
    }
    base.update(overrides)
    return base


class FormFieldTypesTests(unittest.TestCase):
    def test_canonical_field_types_set_is_stable(self) -> None:
        self.assertEqual(
            FORM_FIELD_TYPES,
            frozenset({"text", "email", "url", "password", "boolean", "select", "string_list", "multiline"}),
        )


class BuildFormComponentFrameTests(unittest.TestCase):
    def test_text_field_normalizes(self) -> None:
        frame = build_form_component_frame(
            frame_id="g1",
            label="Profile",
            fields=[{"key": "label", "type": "text", "value": "CVCC", "required": True}],
            submit_action=_submit_action(),
        )
        self.assertEqual(frame["component_type"], "form")
        field = frame["payload"]["fields"][0]
        self.assertEqual(field["key"], "label")
        self.assertEqual(field["type"], "text")
        self.assertEqual(field["value"], "CVCC")
        self.assertTrue(field["required"])

    def test_boolean_field_coerces_truthy_and_falsy(self) -> None:
        frame = build_form_component_frame(
            frame_id="b1",
            label="Toggle",
            fields=[
                {"key": "active", "type": "boolean", "value": 1},
                {"key": "deleted", "type": "boolean", "value": ""},
            ],
            submit_action=_submit_action(),
        )
        self.assertTrue(frame["payload"]["fields"][0]["value"])
        self.assertFalse(frame["payload"]["fields"][1]["value"])

    def test_select_field_accepts_dict_options_and_string_options(self) -> None:
        frame = build_form_component_frame(
            frame_id="s1",
            label="Environment",
            fields=[
                {"key": "env", "type": "select", "options": ["sandbox", "live"]},
                {
                    "key": "tier",
                    "type": "select",
                    "options": [{"value": "free", "label": "Free Tier"}, {"value": "pro"}],
                },
            ],
            submit_action=_submit_action(),
        )
        env_options = frame["payload"]["fields"][0]["options"]
        self.assertEqual(env_options[0], {"value": "sandbox", "label": "sandbox"})
        tier_options = frame["payload"]["fields"][1]["options"]
        self.assertEqual(tier_options[0]["label"], "Free Tier")
        self.assertEqual(tier_options[1]["label"], "pro")

    def test_string_list_field_defaults_to_empty_and_coerces(self) -> None:
        frame = build_form_component_frame(
            frame_id="ls1",
            label="Domains",
            fields=[
                {"key": "domains", "type": "string_list"},
                {"key": "tags", "type": "string_list", "value": ("a", "b")},
            ],
            submit_action=_submit_action(),
        )
        self.assertEqual(frame["payload"]["fields"][0]["value"], [])
        self.assertEqual(frame["payload"]["fields"][1]["value"], ["a", "b"])

    def test_multiline_and_password_normalize_to_strings(self) -> None:
        frame = build_form_component_frame(
            frame_id="mp1",
            label="Notes",
            fields=[
                {"key": "notes", "type": "multiline", "value": "hello\nworld"},
                {"key": "secret", "type": "password", "value": "shh"},
            ],
            submit_action=_submit_action(),
        )
        self.assertEqual(frame["payload"]["fields"][0]["value"], "hello\nworld")
        self.assertEqual(frame["payload"]["fields"][1]["value"], "shh")

    def test_unknown_field_type_raises(self) -> None:
        with self.assertRaises(ValueError) as cm:
            build_form_component_frame(
                frame_id="x",
                label="x",
                fields=[{"key": "k", "type": "color_picker"}],
                submit_action=_submit_action(),
            )
        self.assertIn("color_picker", str(cm.exception))

    def test_missing_field_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_form_component_frame(
                frame_id="x",
                label="x",
                fields=[{"type": "text"}],
                submit_action=_submit_action(),
            )

    def test_duplicate_field_keys_raise(self) -> None:
        with self.assertRaises(ValueError) as cm:
            build_form_component_frame(
                frame_id="dup",
                label="x",
                fields=[
                    {"key": "k", "type": "text"},
                    {"key": "k", "type": "email"},
                ],
                submit_action=_submit_action(),
            )
        self.assertIn("duplicate", str(cm.exception).lower())

    def test_empty_fields_list_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_form_component_frame(
                frame_id="empty",
                label="x",
                fields=[],
                submit_action=_submit_action(),
            )

    def test_select_without_options_raises(self) -> None:
        with self.assertRaises(ValueError) as cm:
            build_form_component_frame(
                frame_id="bad_sel",
                label="x",
                fields=[{"key": "k", "type": "select"}],
                submit_action=_submit_action(),
            )
        self.assertIn("options", str(cm.exception))

    def test_missing_submit_route_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_form_component_frame(
                frame_id="x",
                label="x",
                fields=[{"key": "k", "type": "text"}],
                submit_action={"schema": "x"},
            )

    def test_render_key_includes_attention_and_frame_id(self) -> None:
        frame = build_form_component_frame(
            frame_id="profile",
            label="Profile",
            fields=[{"key": "k", "type": "text"}],
            submit_action=_submit_action(),
            attention_node_id="3-2-3",
            lens_key="active",
        )
        self.assertIn("profile", frame["render_key"])
        self.assertIn("3-2-3", frame["render_key"])
        self.assertIn("active", frame["render_key"])

    def test_tab_id_attaches_when_provided(self) -> None:
        frame = build_form_component_frame(
            frame_id="x",
            label="x",
            fields=[{"key": "k", "type": "text"}],
            submit_action=_submit_action(),
            tab_id="settings",
        )
        self.assertEqual(frame["tab_id"], "settings")

    def test_submit_action_payload_passes_through(self) -> None:
        frame = build_form_component_frame(
            frame_id="x",
            label="x",
            fields=[{"key": "k", "type": "text"}],
            submit_action=_submit_action(payload={"msn_id": "abc", "extra": "y"}),
        )
        self.assertEqual(
            frame["payload"]["submit_action"]["payload"],
            {"msn_id": "abc", "extra": "y"},
        )

    def test_frame_marker_fields(self) -> None:
        frame = build_form_component_frame(
            frame_id="g",
            label="Grantee",
            fields=[{"key": "k", "type": "text"}],
            submit_action=_submit_action(),
        )
        self.assertEqual(frame["initializer"]["verb"], "mediate")
        self.assertEqual(frame["initializer"]["intent"], "resolve_form")
        self.assertEqual(frame["initializer"]["form_id"], "g")
        self.assertFalse(frame["frozen"])  # forms are not frozen — they're editable


if __name__ == "__main__":
    unittest.main()
