# Release and versioning

> Status: as-built — written 2026-09-17 (TASK-2026-09-16-002 P4, operator decision D5).
> Enforced by `fnd_app/tests/unit/test_version_is_coherent.py`, `scripts/lock_packages.py`
> and the `release_gate` job in `.github/workflows/tests.yml`.

## One version

`micyte/__init__.py` holds `__version__`. `pyproject.toml` reads it (`dynamic =
["version"]`); nothing else may spell it. Before 2026-07-22 the two disagreed and the
wheel would have shipped under a number the notes contradicted.

The version is coherent when three things say it: `__version__`, the newest released
section of `CHANGELOG.md`, and `micyte.com/get` (the page that offers the wheel).
`test_version_is_coherent` fails a build in which any one moved alone.

## Where a release lives (D5)

The public repository `Fruitful-Network-Development/micyte` is the release source of
truth: it is what `micyte.com/get` links, and its tag `v<version>` with the wheel on the
release page is the artifact. This tree (`mycite-core`) is where the work happens; its
own `micyte-v0.1.0` release is retired. The public tree is CUT from this one — `micyte/`,
`docs/wiki`, `docs/standards`, `LICENSE`, `README.md`, `pyproject.toml` and the public
scripts — never edited in place, so the two cannot drift.

## The cut

`scripts/publish_micyte.py`:

1. refuses when `__version__` equals the newest public tag (bump first);
2. exports the public tree to a scratch directory on disk (not the tmpfs
   scratchpad);
3. runs `scripts/release_gate_scan.py` against the export — private documents must be
   absent, and no public file may carry a live msn, an absolute `/srv` path, a hosted-zone
   id or an AWS account id; a red scan is a refused cut;
4. builds the wheel there (`python -m build --wheel`);
5. with `--apply`: commits the export onto a clone of the public repository as
   `MiCyte <version>`, tags `v<version>`, pushes, and creates the GitHub release with the
   changelog section as its notes and the wheel attached.

Dry run is the default and prints every step; `--apply` is the operator's act.

## Wire ids and schema tokens

`mycite.v2.*` schema ids, `mos.*` policy tokens and the MSS format version are stored in
payloads, in published stills and in micyte.com's JS. They are bumped by suffix
(`.v2` → `.v3`, `mos.mss_binary_v2` → `_v3`), never renamed: a renamed id is a document
somebody else holds that no longer verifies.

## Gadgets

A package (app, instrument, tool) carries its own version in `micyte/tools/_packages.py`.
**A package whose declarations change — tools, requirements, writes, port declarations
or fills, app sandbox, features — bumps its version.** `scripts/lock_packages.py` refuses
to record a changed digest under an unchanged version, and
`test_a_changed_package_bumps_its_version` pins the lock to the build. Requirements name
archetypes by the hash in `micyte/tools/_archetypes.lock.json`; re-run
`scripts/lock_archetypes.py` when the library is re-minted, in the same commit as the
packages that move with it.

## Documentation

Every `docs/wiki` page declares a status (`as-built`, `design-spec`, `how-to`, `index`,
`stale`) and links the index; every path a wiki or contract page cites exists or is named
as debt with why (`test_wiki_is_combed`, `test_contract_pages_are_pinned`). A contract
that names its tests names tests that exist.

## What a release note says

In the voice of `documentation_style_guide.md`: what changed for the person reading, in
plain verbs — what the engine now refuses, what a gadget can now do — never the commit
list. The section is written when the version is bumped; the cut copies it.
