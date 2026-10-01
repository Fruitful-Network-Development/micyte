"""A document a positional reader owns is named by the one rule the readdress and the
audit both ask (`micyte.core.datum_ops.positional_grammars`)."""

from __future__ import annotations

import unittest

from micyte.core.datum_ops import archetype_class, viewscope
from micyte.core.datum_ops.positional_grammars import POSITIONAL_GRAMMARS, positional_grammar


class TheRuleNamesTheReadersThatOwnTheirFamilies(unittest.TestCase):
    def test_a_class_and_a_viewscope_are_positional(self) -> None:
        self.assertTrue(positional_grammar(archetype_class.class_name("log")).startswith("class library"))
        self.assertTrue(positional_grammar(viewscope.viewscope_name("farm_identity")).startswith("viewscope"))

    def test_an_archetype_is_held_to_the_arity_convention(self) -> None:
        # `class_record` is a live ARCHETYPE, not the class library's document: the
        # library's prefix is `kind_` precisely so the two cannot collide.
        for name in ("farm_identity", "class_record", "job", "", "kind", "viewscope"):
            with self.subTest(name=name):
                self.assertEqual(positional_grammar(name), "")

    def test_the_prefixes_are_the_readers_own(self) -> None:
        # The rule restates nothing: it imports the prefix each reader finds its documents by.
        self.assertEqual([p for p, _g in POSITIONAL_GRAMMARS], [archetype_class.CLASS_PREFIX, viewscope.VIEWSCOPE_PREFIX])
        for prefix, grammar in POSITIONAL_GRAMMARS:
            with self.subTest(prefix=prefix):
                self.assertIn("4-1", grammar)


if __name__ == "__main__":
    unittest.main()
