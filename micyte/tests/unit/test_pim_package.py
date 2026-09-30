"""PIM — the CLIENT's application, and the three things that must not drift.

WHOSE APP IT IS. The operator's depiction: the CHANNEL is where an alias manages the
services they pay for and collects API keys; the Use button binds a key to one of THEIR
ports; and "thereafter the relationship a client has with their provider services is
entirely facilitated through a new sandbox and application called PIM". So PIM runs on the
CLIENT's instance, over the client's own records — not the operator looking at a client.
The first draft of this package had that backwards.

1. THE NAMESPACE INHERITS. Oveure shipped a static `"system"` here, which is the
   namespace of exactly ONE instance's core anchor (FND's) and one with no lcl-node
   vocabulary — so its Domain tab could never have minted on a farm or a client instance.
   A PIM sandbox is copied from the instance's own core anchor the same way, so the same
   token would be wrong in the same way. This is the one thing about PIM that was decided
   before it was designed, and the test exists so it cannot quietly regress.

2. IT DECLARES ONLY WHAT IT CAN SERVE. PIM ships exactly ONE tool, `pim_overview`. A
   package listing Newsletter, Analytics or Design would offer a tab that cannot open —
   the glyph library's rule ("every title here is what the grammar can HONESTLY draw")
   applied to a hub, with the rejected gear as precedent.

   (This paragraph said "the plan names six tabs; three have tools" until 2026-08-24.
   Two of those six were never PIM's — `artifacts` shipped as a base-core INSTRUMENT,
   and Domain was not on the operator's list — and the count of tools was one, not
   three. Three depictions of the same package disagreed at once, which is what
   `TheDepictionMatchesTheDeclaration` below now makes impossible to do quietly.)

3. ITS PROSE AGREES WITH ITS TUPLE. Added 2026-08-24. The package's docstring claimed
   it served Contacts and a files tab; its user-visible `summary` said Contacts was
   planned with no tool; `tools` shipped neither. Nothing checked, so the three drifted
   for as long as nobody read them side by side.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools import all_tools
from micyte.tools._packages import catalogue

#: Named tabs with no tool behind them. Shrinks as each is built; a tool arriving for one
#: of these should move it into `tools`, and this list is where somebody notices.
TABS_WITHOUT_TOOLS = ("newsletter", "analytics", "email", "contacts")


def _pim():
    return next(p for p in catalogue() if p.package_id == "pim")


class TheNamespaceInherits(unittest.TestCase):
    def test_it_is_not_a_static_token(self) -> None:
        """`""` means "whatever the instance's own core anchor speaks", resolved at
        install. A token cannot state that rule — it can only state one answer."""
        self.assertEqual(_pim().app_sandbox.namespace, "")
        self.assertTrue(_pim().app_sandbox.inherits_namespace)

    def test_it_does_not_claim_system_the_way_oveure_did(self) -> None:
        """The specific regression. `system` is FND's core anchor's namespace and has no
        lcl-node vocabulary, so a Domain tab could never mint there."""
        self.assertNotEqual(_pim().app_sandbox.namespace, "system")

    def test_every_app_lineage_now_inherits_or_says_why(self) -> None:
        """quiar and brevat state a namespace deliberately — they are tied to an instance
        KIND. A new app that states one should be a decision, not a copied line."""
        # `enchir` (2026-09-10) has NO app sandbox at all — its subject is the instance's
        # own documents, in whichever sandbox it is opened over — so it neither states
        # nor inherits, and is not in this dict.
        stated = {p.package_id: p.app_sandbox.namespace
                  for p in catalogue()
                  if getattr(p, "is_app", False) and p.app_sandbox is not None
                  and not p.app_sandbox.inherits_namespace}
        # `grantor` joined 2026-08-24, and its reason is the sharpest of the three:
        # INHERIT resolves from the anchor's `copied_from`, and the grantor anchor records
        # none — so it would fall back to FND's core `system` anchor, the one namespace of
        # six with NO lcl vocabulary. FND is the only instance this app runs on, so it is
        # guaranteed to hit that. Stated, and checked against `field_registry`'s own
        # `grantor: farm` when the claim is registered at install.
        self.assertEqual(
            stated, {"quiar": "registrar", "brevat": "farm", "grantor": "farm"})


class ItDeclaresOnlyWhatItCanServe(unittest.TestCase):
    def test_every_declared_tool_is_registered(self) -> None:
        """A tab that cannot open is worse than a tab that is not offered."""
        registered = {t.tool_id for t in all_tools()}
        for tool_id in _pim().tools:
            with self.subTest(tool=tool_id):
                self.assertIn(tool_id, registered)

    def test_the_three_tabs_without_tools_are_NOT_declared(self) -> None:
        for tab in TABS_WITHOUT_TOOLS:
            with self.subTest(tab=tab):
                self.assertNotIn(tab, _pim().tools)

    def test_the_absent_tabs_are_NAMED_rather_than_silently_omitted(self) -> None:
        """A gap somebody can read beats a gap they have to notice."""
        summary = _pim().summary.lower()
        for tab in TABS_WITHOUT_TOOLS:
            with self.subTest(tab=tab):
                self.assertIn(tab, summary)

    def test_the_list_of_absent_tabs_does_not_go_STALE(self) -> None:
        """If a tool is built for one of these, it belongs in `tools` and out of here —
        otherwise this file keeps excusing an absence that has ended."""
        registered = {t.tool_id for t in all_tools()}
        for tab in TABS_WITHOUT_TOOLS:
            with self.subTest(tab=tab):
                self.assertNotIn(
                    tab, registered,
                    f"{tab!r} is a registered tool now — declare it in PIM's tools and "
                    "drop it from TABS_WITHOUT_TOOLS")

    def test_its_hub_is_one_of_its_own_tools(self) -> None:
        self.assertIn(_pim().hub_tool, _pim().tools)


class ItDoesNotDeclareARetiredTool(unittest.TestCase):
    def test_it_declares_only_its_OWN_tools(self) -> None:
        """A tool belongs to exactly one lineage — `packages_by_tool` raises on a shared
        claim — and an app's hub must be one of the things it installs.

        The first draft borrowed quiar's `contacts_manager` and the Compendium's
        `artifacts`. Wrong structurally, and wrong semantically: quiar's contacts are a
        CRM's, PIM's are people who signed up on a website. Same word, different record.
        """
        from micyte.tools._packages import packages_by_tool

        owners = packages_by_tool()
        for tool_id in _pim().tools:
            with self.subTest(tool=tool_id):
                self.assertEqual(owners[tool_id].package_id, "pim")

    def test_it_does_not_borrow_another_apps_tool(self) -> None:
        self.assertNotIn("contacts_manager", _pim().tools)

    def test_it_does_not_declare_local_domain(self) -> None:
        """`local_domain` is not a tool and has not been since 2026-08-06 — retired for
        "merely rendering a document's own values". An earlier draft declared it, and
        `test_every_declared_tool_is_registered` is what said so.
        """
        self.assertNotIn("local_domain", _pim().tools)


class ItIsAnAppLineage(unittest.TestCase):
    def test_it_is_the_fourth(self) -> None:
        """PIM is the fourth lineage BY ARRIVAL; `grantor` is the fifth (2026-08-24).

        The name stays because it is about PIM's place in the sequence — brevat, quiar,
        oveure, then PIM — not about how many exist now.
        """
        apps = sorted(p.package_id for p in catalogue() if getattr(p, "is_app", False))
        # `enchir` is the sixth (2026-09-10): the projects a client keeps and how their
        # site offers them up, employing `site_hosting` for the profile editor.
        self.assertEqual(apps, ["brevat", "enchir", "grantor", "oveure", "pim", "quiar"])

    def test_it_declares_the_FND_seam(self) -> None:
        """The port is the point. Without one PIM is a sandbox with nothing to fill it —
        the operator's "enabled and permitted to use the ports"."""
        self.assertEqual(
            [d.port_id for d in _pim().port_declarations],
            ["email_provider", "site_hosting"])

    def test_it_employs_OPERATIONS_and_never_a_vendor(self) -> None:
        """Which extension carries the mail — FND relaying it, or a direct SES adapter —
        is the operator's choice on Ports, made after this manifest was written. A vendor
        named here would pin PIM to one extension and stop matching when somebody chose
        another."""
        for declaration in _pim().port_declarations:
            with self.subTest(port=declaration.port_id):
                self.assertTrue(declaration.operations)
                self.assertEqual(getattr(declaration, "calls", ()), ())

    def test_it_can_never_SEND_anything(self) -> None:
        """The operator's constraint, made structural: "I don't yet want to mess up
        anyone's emails or websites."

        `message.send` and `message.forward` are the two operations that put words
        outside the box. PIM employs neither, so there is no grant an operator could
        write — however generous — that would let this app send. A read-only app is not
        a promise here; it is the absence of a declared verb.
        """
        from micyte.ports.email_provider import (
            OPERATION_MESSAGE_FORWARD,
            OPERATION_MESSAGE_SEND,
        )

        employed = {op for d in _pim().port_declarations for op in d.operations}
        self.assertNotIn(OPERATION_MESSAGE_SEND, employed)
        self.assertNotIn(OPERATION_MESSAGE_FORWARD, employed)

    def test_it_declares_every_site_operation_as_its_OWN_permission(self) -> None:
        """The constraint moved from the PORT to the GRANT, by the operator's decision.

        Until 2026-08-29 this asserted `content.replace` and `asset.upload` were absent,
        on the operator's "I don't yet want to mess up anyone's emails or websites". The
        same person then asked for exactly those: the design page should "allow for image
        changes and icons and text edits that change the hosted site". So the line did not
        erode — it was redrawn, and this test follows it rather than defending where it
        used to be.

        Where it sits now is the GRAIN. Six operations, each its own permission, so an
        operator may let a client fix a typo without letting them upload a file to a
        public URL, and either without letting them publish a piece. A single `site.write`
        would have made all three one decision, and there would be nowhere for a line to
        be drawn at all.

        DECLARING IS NOT GRANTING, and that is the remaining tooth: the package ships able
        to do none of this until somebody binds the port and writes a grant naming the
        operation.
        """
        declared = {d.port_id: set(d.operations) for d in _pim().port_declarations}
        self.assertEqual(
            declared.get("site_hosting"),
            {"page.list", "article.publish", "article.retire", "analytics.read",
             "content.replace", "asset.upload"})

    def test_each_site_operation_is_distinct(self) -> None:
        # Six names, six permissions. If two ever collapse to one string, an operator
        # granting the safer one silently grants the other.
        declared = {d.port_id: list(d.operations) for d in _pim().port_declarations}
        operations = declared.get("site_hosting") or []
        self.assertEqual(len(operations), len(set(operations)))

    def test_the_package_carries_no_grant(self) -> None:
        """The whole of what keeps a declaration safe. A manifest that shipped its own
        grant would make the permissive outcome the default one."""
        blob = repr([d for d in _pim().port_declarations]).lower()
        for forbidden in ("external_call_grant", "granted", "permitted"):
            self.assertNotIn(forbidden, blob)

    def test_it_declares_the_clients_three_writes_and_no_send(self) -> None:
        """The line moved on 2026-09-10, by the operator's decision, and exactly this far:
        PIM employs `forwarding.set`, `identity.verify_request` and `identity.remind` —
        the client's own address, and the setup email re-sent to its owner — and still
        none of `message.send`, `message.forward`, `alias.create` or `alias.remove`."""
        declared = {d.port_id: set(d.operations) for d in _pim().port_declarations}
        mail = declared.get("email_provider") or set()
        for employed in ("forwarding.set", "identity.verify_request", "identity.remind"):
            with self.subTest(operation=employed):
                self.assertIn(employed, mail)
        for withheld in ("message.send", "message.forward", "alias.create", "alias.remove"):
            with self.subTest(operation=withheld):
                self.assertNotIn(withheld, mail)

class TheDepictionMatchesTheDeclaration(unittest.TestCase):
    """A package describes itself in three places — docstring, `summary`, `tools` — and
    until 2026-08-24 nothing required them to agree.

    They disagreed, in the direction that costs most: the DOCSTRING (read first, by
    whoever is deciding what still needs building) claimed two tabs were served, while
    the summary and the tuple both said none were. A maintainer reading only the
    docstring concludes half the remaining work is done.

    These run over EVERY package, not just PIM. The drift was not special to PIM; only
    the noticing was.
    """

    # `ToolPackage.__doc__` is the DATACLASS's docstring, identical for every package.
    # The prose that drifted lives on the BUILDER FUNCTION (`_pim_package`), so that is
    # what has to be read. The first version of these tests read `package.__doc__`,
    # passed against the injected regression, and proved nothing — the same shape as the
    # three tests this file's own history records as having proved nothing.
    @staticmethod
    def _builder_prose(package_id: str) -> str:
        import inspect

        from micyte.tools import _packages

        builder = getattr(_packages, f"_{package_id}_package", None)
        if builder is None:
            return ""
        return inspect.getdoc(builder) or ""

    @staticmethod
    def _builders() -> list[str]:
        import inspect

        from micyte.tools import _packages

        return [name[1:-8] for name, _ in inspect.getmembers(_packages, inspect.isfunction)
                if name.startswith("_") and name.endswith("_package")]

    def test_the_helper_actually_finds_the_prose(self) -> None:
        """Guard on the guard. If `_builder_prose` silently returned "" the two tests
        below would pass forever — which is exactly what happened when they read
        `package.__doc__` instead."""
        prose = self._builder_prose("pim")
        self.assertTrue(prose, "found no builder prose for pim — the tests below are inert")
        self.assertIn("pim_overview", prose)

    def test_no_package_claims_in_prose_a_tab_its_summary_calls_PLANNED(self) -> None:
        """The exact contradiction that shipped: prose said "Contacts ... ha[s] tools
        today", summary said Contacts is "planned ... with no tool behind them yet"."""
        for package in catalogue():
            prose = self._builder_prose(package.package_id).lower()
            summary = package.summary.lower()
            if not prose:
                continue
            if "no tool behind them yet" not in summary and "planned tab" not in summary:
                continue
            for tab in TABS_WITHOUT_TOOLS:
                if tab not in summary:
                    continue
                # Only the CLAIM matters, not the word: this file and the builder both
                # discuss the old contradiction in order to record it.
                claim = f"{tab} and the files tab have tools"
                with self.subTest(package=package.package_id, tab=tab):
                    self.assertNotIn(
                        claim, prose,
                        f"{package.package_id}'s builder prose presents {tab!r} as "
                        "served while its summary calls it planned")

    def test_no_package_names_a_tool_in_prose_that_it_does_not_declare(self) -> None:
        """Catches the borrow that `packages_by_tool` already forbids structurally, at
        the layer where it is only WRITTEN — which is where it survived."""
        registered = {t.tool_id for t in all_tools()}
        for package in catalogue():
            prose = self._builder_prose(package.package_id)
            if not prose:
                continue
            for tool_id in registered:
                if tool_id in package.tools or len(tool_id) < 8:
                    continue
                # A backticked tool id reads as "this package uses it". Prose that is
                # explicitly ABOUT not borrowing says so — but the disclaimer must sit
                # in the SAME SENTENCE as the mention.
                #
                # The first version scanned the whole docstring for "borrow", which the
                # historical note happens to contain, so ONE disclaiming sentence
                # switched the check off for every tool in the package. It passed
                # against the injected regression. A document-wide escape hatch is not
                # an exception; it is an off switch.
                for sentence in prose.replace("\n", " ").split("."):
                    if f"`{tool_id}`" not in sentence:
                        continue
                    disclaims = any(w in sentence.lower() for w in
                                    ("borrow", "cannot", "not declare", "never",
                                     "does not", "wrong", "retired"))
                    with self.subTest(package=package.package_id, tool=tool_id):
                        self.assertTrue(
                            disclaims,
                            f"{package.package_id}'s builder prose names {tool_id!r} "
                            f"but does not declare it, and the sentence does not say "
                            f"it is not used: {sentence.strip()!r}")

    def test_every_absent_port_has_a_recorded_REASON(self) -> None:
        """An absence with a reason is a decision; an absence without one cannot be told
        apart from an oversight.

        `site_hosting` was justified in three places and `commerce_offering` — the
        payment hub the operator named by name — was simply missing, while the plan's
        blueprint still listed it. Two absences, one explained.

        `site_hosting` was then DECLARED (2026-08-26), which is why this asserts over
        whatever is absent NOW rather than over a written-down pair. A test naming the
        absentees has to be edited every time one arrives, and the edit is exactly the
        moment somebody deletes the check instead.
        """
        import inspect

        from micyte.ports.port_catalog import port_types
        from micyte.tools import _packages

        source = inspect.getsource(_packages._pim_package)
        declared = {d.port_id for d in _pim().port_declarations}
        absent = [p.port_id for p in port_types() if p.port_id not in declared]
        self.assertTrue(absent, "every port declared — this check has nothing to guard")
        for port_id in absent:
            with self.subTest(port=port_id):
                self.assertIn(
                    port_id, source,
                    f"{port_id} is absent from PIM's declarations and its absence is "
                    "not explained anywhere in the builder — record WHY, so the next "
                    "reader can tell a decision from an oversight")


if __name__ == "__main__":
    unittest.main()
