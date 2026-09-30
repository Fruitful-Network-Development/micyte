# Development process

> Status: as-built — written 2026-09-29 (TASK-2026-09-27-001 P1). Enforced where a test
> can enforce it: `fnd_app/tests/architecture/test_tests_do_not_name_live_paths.py` (the
> suite stays hermetic), `test_wiki_is_combed.py` (this page is indexed and its counts hold),
> the `tests` workflow (`.github/workflows/tests.yml`), `scripts/health_gate.sh` (the
> host's run), and `srv-infra/scripts/deploy_portal.sh` (the deploy refuses a red suite).

## Why this page exists

On 2026-09-27 three programs closed on the same morning, each verified by the batches it
named and deployed through a gate that ran the architecture tests. None of those steps read
the `tests` workflow, so a suite that had gone red on a clean runner on 2026-09-11 stayed red
for sixteen days behind eleven deploys reporting `ok:true`. Seventy-two of the failures were
tests that passed only on the production host — reading its grant store, its scratch
directory, a sibling checkout. The repository had one machine it agreed with itself on.

This page is the flow that lands a change so that three focuses can work at once without
breaking one another or the live instance. It is short on purpose; the rules it cites are
held by tests, not by this prose.

## The flow

1. **Cut a worktree, never a branch in the live checkout.** The checkout the portal unit
   runs from (its `WorkingDirectory` and `PYTHONPATH`) stays on `main`. Work happens in a
   worktree beside it — `git worktree add ../<repo>-<slug> -b <branch> main` (measured
   2026-08-23: an uncommitted edit to a loaded core module in the live checkout invalidated
   a gate run and turned `/healthz` stale).
2. **Name the focus in the branch:** `feat/<focus>-<slug>` — see the registry below. A
   change that touches two rows is two PRs, with one exception (the archetype re-pin lands
   with the package bumps the lock demands).
3. **Verify locally with the gate, never the whole suite in one process:**
   `scripts/health_gate.sh` (batched and memory-capped; on a 3.8 GB host `pytest
   fnd_app/tests` in one process is OOM-killed). Run it with `PRIVATE_DIR` pointed at an
   empty directory to see what a clean runner sees. Its verdict names the commit and whether
   the tree was clean.
4. **Push and open a PR against `main`.** The `tests` workflow is the hermetic verdict: ruff,
   the release gate (public export + wheel), the datum-on-disk guard, pytest with
   `PRIVATE_DIR` pointed at nowhere. The browser smoke job is advisory until it has been
   green ten runs running.
5. **Merge when green.** `main` takes direct pushes (the private repository has no branch
   protection), so the PR is the discipline, not a lock: nothing lands on `main` that the
   workflow has not passed.
6. **Deploy from `main` with `srv-infra/scripts/deploy_portal.sh`.** It pulls `main`,
   refuses a commit whose `tests` run is not green (`DEPLOY_GATE_LOG=<health_gate log>` for
   a host that must deploy while GitHub is unreachable; `SKIP_DEPLOY_GATE=1` is loud), runs
   ruff + the architecture batch, restarts the unit and waits for `/healthz` to answer with
   the new build id. `code_coherence: current` and `source_freshness: fresh` are the
   post-deploy claims.
7. **Remove the worktree** when the branch is merged (`git worktree remove`); delete the
   branch. A worktree with uncommitted work is a branch nobody can see.

## The focus registry

| Focus | Owns | Its gate | Bumps |
|---|---|---|---|
| **engine** — core MiCyte mechanics | `micyte/core/**`, `micyte/adapters/**`, `micyte/ports/**`, `micyte/domains/**`, `micyte/state_machine/**` | the engine suites + architecture batch | `__version__` + a CHANGELOG section |
| **datum standard** — an archetype, a naming/prefix rule, an invariant, a wire schema | `micyte/core/archetypes/**`, `micyte/core/mss/invariants.py`, `docs/contracts/**`, `micyte/tools/_archetypes.lock.json` | `test_contract_pages_are_pinned`, `lock_archetypes.py`, `audit_mss_invariants.py`; a wire id bumps by suffix | archetype lock re-cut + every package that pins it (`lock_packages.py` refuses otherwise) = a release |
| **gadget** — an app, instrument, tool, extension | `micyte/tools/<package>*.py`, its entry in `micyte/tools/_packages.py`, `_packages.lock.json` | `test_a_changed_package_bumps_its_version`, the package's tests, `install_package` on the e2e-provisioned instance | the package version |
| **surface** — a portal view, a PIM tab, a shell asset | `fnd_app/instances/_shared/portal_host/**`, `fnd_app/instances/_shared/runtime/**`, `micyte/state_machine/portal_shell/**`, the shell JS/CSS | unit batch + asset budget + browser smoke | none (deployed from `main`) |
| **network standard** — contract formation, alias, port binding, the published doors | `micyte/channels/**`, `micyte/domains/contracts/**`, `fnd_app/instances/_shared/runtime/contract_*.py`, `instance_client.py`, `package_update_transport.py`, the three network contract pages | e2e over the wire (provisioned instance) + contract pins | schema id by suffix; `micyte.packages.manifest.vN` |
| **infra** — unit, vhost, timers, deploy | `srv-infra/**`, `fnd_app/deploy/**` | `deploy_portal.sh` + `/healthz` | none |

## What the live host is for

Deploy and verify — never develop. Three rules a test holds:

* **No test names a live or host-only path.** The live store is reached through
  `fnd_app/tests/_live_instances` and skipped where it is absent; scratch is `TMPDIR` or
  `tempfile` (never `/tmp`, which is RAM on the host); a sibling checkout is a variable the
  harness sets. The guard ratchets: a file that stops needing its exemption loses it.
* **No runtime module edits `sys.path`.** What the software needs, it carries
  (`fnd_app/packages/site_core` is the article grammar for that reason).
* **A test that needs a grant writes it** (`fnd_app/tests/_egress_grants_fixture.py`). The
  operator's grant store is the nightly ledger's, not a fixture.

The e2e harness provisions its own instance (`fnd_app/tests/_provisioned_instance`); a
measurement against the live store opens it read-only or takes a `consistent_copy` under
`TMPDIR`.

## Backups and private state

Any file under `private/` is backed up through `stamped_backup_path` before it is written;
retention is by count (`prune_mos_backups.py`), never by age. A store copy for a rehearsal
is `VACUUM INTO`, never `copy2` of a WAL store.

## See also

`release_and_versioning.md` (the cut), `05-engineering-standards.md` (layering and the
test strategy), `docs/contracts/mss_engine_invariants.md` (what the doors refuse).
