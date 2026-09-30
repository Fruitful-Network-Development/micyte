# The public suite

Every test here exercises `micyte.*` alone — no `fnd_app` import, no live fixture, no
literal the release gate refuses (a live msn, a `/srv` path, a zone or account id) — so
it ships with the cut (`scripts/publish_micyte.py` exports `micyte/`, tests included) and
runs in the public repository's own CI. `fnd_app/tests/architecture/
test_the_public_suite_holds_every_micyte_only_test.py` is the ratchet: a test that
qualifies and sits under `fnd_app/tests` fails it, and a test here that reaches for
`fnd_app` or a private literal fails it too.

The directories mirror `fnd_app/tests` (`unit`, `contracts`, `adapters`, `architecture`)
so a file's depth — and its `REPO_ROOT = Path(__file__).resolve().parents[3]` — does not
change when it moves. No `__init__.py`: these are collected as top-level test modules,
the way `fnd_app/tests` is, and the wheel excludes this directory.

Sixty-one micyte-only tests still sit under `fnd_app/tests` because they name a live
registrar address, and one because its fixtures name real parties; each moves the day
its literal becomes a fixture constant.
