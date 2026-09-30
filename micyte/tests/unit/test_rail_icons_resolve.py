"""Every glyph the rail can ask for is one the sprite actually has.

An external ``<use>`` pointing at a missing symbol **instantiates an empty box, draws
nothing, and reports nothing**. No console error, no exception, no failed request — the rail
slot is simply blank, and it reads as a theme or CSS problem rather than as a missing glyph.
That is why this has to be a test: there is no runtime signal at all.

The renderer's own comment claimed "the sprite either has that symbol or the generic one is
used". Nothing implemented the second half. The ``if/else`` chain that HAD done it — drawing
a circle for anything it did not recognise — was deleted when the sprite replaced it, and
the fallback went with it.

Three blank slots were live when this was written, none visible to any test:

* ``workbench_ui`` and a tenant's own slug, both reachable from
  ``activity_icon_id_for_surface``;
* ``export`` — ``ExportManager.tool_id`` is ``export`` while the sprite carried
  ``export_manager``;
* every channel but ``agnet``, by construction rather than by oversight.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import micyte.channels as channels_mod
import micyte.tools as T
from micyte.state_machine.portal_shell.icon_sprite import (
    GENERIC_ICON_ID,
    SYMBOLS,
    icon_id_or_generic,
)
from micyte.state_machine.portal_shell.shell import activity_icon_id_for_surface
from micyte.state_machine.portal_shell.shell_registry import build_portal_surface_catalog


class ResolutionTests(unittest.TestCase):
    def test_a_known_id_survives(self) -> None:
        self.assertEqual(icon_id_or_generic("quiar"), "quiar")

    def test_an_unknown_id_becomes_the_generic_one(self) -> None:
        self.assertEqual(icon_id_or_generic("no_such_glyph"), GENERIC_ICON_ID)
        self.assertEqual(icon_id_or_generic(""), GENERIC_ICON_ID)
        self.assertEqual(icon_id_or_generic(None), GENERIC_ICON_ID)

    def test_the_fallback_itself_is_IN_the_sprite(self) -> None:
        """If the fallback is missing, every unknown id draws nothing and the fallback has
        achieved exactly nothing."""
        self.assertIn(GENERIC_ICON_ID, SYMBOLS)


class EveryEmittableIconResolvesTests(unittest.TestCase):
    """The sweep. Each source of an ``icon_id`` is asked what it can produce."""

    def test_every_rail_surface_icon_is_in_the_sprite(self) -> None:
        """The five fixed rail entries (2026-08-21) each name a symbol; a missing one
        draws nothing and reports nothing."""
        from micyte.state_machine.portal_shell import activity_icon_id_for_surface
        from micyte.state_machine.portal_shell.shell_schemas import ROOT_SURFACE_IDS

        checked = 0
        for surface_id in sorted(ROOT_SURFACE_IDS):
            icon = activity_icon_id_for_surface(surface_id)
            with self.subTest(surface=surface_id, icon=icon):
                self.assertIn(
                    icon, SYMBOLS,
                    f"{surface_id} would ask for {icon!r}, which the sprite does not "
                    "have — the rail slot draws nothing and reports nothing. Add it to "
                    "micyte/state_machine/portal_shell/icon_sprite.SYMBOLS and rebuild.")
            checked += 1
        self.assertTrue(checked, "no root surfaces — the sweep was vacuous")

    def test_every_instruments_icon_is_in_the_sprite(self) -> None:
        """The Gadgets gallery and the instrument face both draw these raw (no
        icon_id_or_generic pass), so a missing symbol is a silent empty box."""
        from micyte.tools._instruments import INSTRUMENTS

        for item in INSTRUMENTS:
            with self.subTest(instrument=item.instrument_id, icon=item.icon_id):
                self.assertIn(item.icon_id, SYMBOLS)

    def test_a_DECLARED_icon_is_the_one_used(self) -> None:
        """`_contract` documents `icon` as "the sprite symbol the rail draws" and four tools
        declare one. Nothing read it, so the declarations were dead."""
        declaring = [
            tool for tool in T.all_tools() if str(getattr(tool, "icon", "") or "")
        ]
        self.assertTrue(declaring, "no tool declares an icon — the attribute is dead again")
        for tool in declaring:
            with self.subTest(tool=tool.tool_id):
                self.assertEqual(
                    icon_id_or_generic(tool.icon), tool.icon)

    def test_every_channels_icon_is_in_the_sprite(self) -> None:
        found = list(channels_mod.all_channels())
        self.assertTrue(found, "no channels — the sweep was vacuous")
        for channel in found:
            declared = str(getattr(channel, "icon", "") or "") or channel.channel_id
            with self.subTest(channel=channel.channel_id, icon=declared):
                self.assertIn(declared, SYMBOLS)

    def test_every_surface_icon_the_rail_can_emit_resolves(self) -> None:
        """`activity_icon_id_for_surface` may legitimately answer something the sprite has
        no art for — a tenant's slug is a TENANT name, and per-tenant rail art is not a
        thing this can have. So the requirement is that it RESOLVES, not that every answer
        is a symbol: the fallback is what makes an unknowable id safe."""
        catalog = list(build_portal_surface_catalog(network_enabled=True))
        self.assertTrue(catalog, "empty surface catalog — the sweep was vacuous")
        for entry in catalog:
            raw = activity_icon_id_for_surface(entry.surface_id)
            with self.subTest(surface=entry.surface_id, icon=raw):
                self.assertIn(icon_id_or_generic(raw), SYMBOLS)

    def test_the_export_tools_id_is_what_the_sprite_CARRIES(self) -> None:
        """A named regression. The sprite held `export_manager` — the module name — while
        the rail sends `ExportManager.tool_id`, which is `export`."""
        export = T.get("export")
        self.assertIsNotNone(export, "the export tool is no longer registered as `export`")
        self.assertIn("export", SYMBOLS)


class EveryUseNamesTheSymbolPrefixTests(unittest.TestCase):
    """`<use href="…#id">` resolves only against `icon-<id>`, and fails SILENTLY.

    The Compendium's gallery shipped emitting `#generic` instead of
    `#icon-generic`, so every document tile drew a 40px hole where its glyph
    belongs. Nothing errored: a `<use>` pointing at a symbol that does not exist
    renders nothing and raises nothing, which is exactly the failure a source-level
    pin has to catch instead.
    """

    def test_every_sprite_use_in_the_client_names_the_prefix(self) -> None:
        import re
        from pathlib import Path

        static = (
            Path(__file__).resolve().parents[3]
            / "fnd_app" / "instances" / "_shared" / "portal_host" / "static"
        )
        offenders: list[str] = []
        for path in sorted(static.glob("*.js")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if 'href="' not in line or "#" not in line:
                    continue
                # The two markup builders both concatenate sprite + "#" + id.
                for match in re.finditer(r'\+\s*"#([^"]*)"', line):
                    if not match.group(1).startswith("icon-"):
                        offenders.append(f"{path.name}: {line.strip()}")
        self.assertEqual(offenders, [], "sprite href missing the `icon-` prefix")


class BuiltSpriteTests(unittest.TestCase):
    """The declared table and the built file must agree, or the server names symbols the
    browser cannot find. Skipped where the shared pool is absent — this is the only
    assertion here that needs the deploy tree."""

    def setUp(self) -> None:
        from scripts.build_portal_icon_sprite import sprite_path

        self.sprite = sprite_path()
        if not self.sprite.parent.is_dir():
            self.skipTest(f"shared leaflet pool not present at {self.sprite.parent}")

    def test_the_built_sprite_contains_every_declared_symbol(self) -> None:
        if not self.sprite.exists():
            self.skipTest("sprite not built here")
        body = self.sprite.read_text(encoding="utf-8")
        missing = sorted(name for name in SYMBOLS if f'id="icon-{name}"' not in body)
        self.assertEqual(
            missing, [],
            f"declared but not in the built sprite: {missing} — rebuild with "
            "scripts/build_portal_icon_sprite.py")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
