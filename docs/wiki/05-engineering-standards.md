> Status: as-built

[← Overview](00-overview-and-glossary.md)

# Engineering Standards

How we keep MiCyte Portal lean and correct. This is the operating contract for
contributors: where code belongs, how dependencies are allowed to point, what
"too much code" means, how we cache, how we test, and what the front-end is
allowed to ship to the browser.

The stack is hexagonal with three layers (see the
[Overview](00-overview-and-glossary.md) for the full picture):

- **L1 CORE** — `MyCiteV2/packages/core/` — the lean MOS datum-database
  library. Pure domain logic, no I/O, no framework.
- **L2 SURFACE** — `MyCiteV2/packages/ports/` (pure contracts) +
  `MyCiteV2/packages/adapters/` (implementations: SQL, filesystem, AWS).
- **L3 UI** — `MyCiteV2/packages/tools/`, `MyCiteV2/packages/state_machine/`,
  and the Flask host + JS shell under
  `MyCiteV2/instances/_shared/portal_host/`.

---

## Purpose

This page exists so that a reviewer can answer one question quickly: *does this
change keep the stack lean and the layering honest?* Everything below is
enforced (or should be enforced) by tests in
`MyCiteV2/tests/architecture/`, so the standards are mechanical, not matters of
taste.

---

## Dependency direction (the rule)

Imports point **inward**. The dependency graph has no upward or sideways edges:

```
instances / tools / state_machine   (L3 UI)
            │  may import
            ▼
        adapters                     (L2 — implement ports)
            │  may import
            ▼
          ports                      (L2 — pure contracts)
            │  may import
            ▼
          core                       (L1 — pure domain)
```

The hard rules:

1. **`core` must never import from `adapters`, `ports`, `instances`,
   `state_machine`, `tools`, `modules`, or `sandboxes`.** Core depends only on
   the standard library and other `core` modules.
2. **`adapters` depend on `ports`** (the contracts they implement) and on
   `core`, never on `instances` or `tools`.
3. **`ports` are pure contracts** — dataclasses / Protocols describing what a
   store or service must provide. A port file imports only the stdlib and
   `core`; it never reaches into an adapter or the UI.
4. **L3 (UI/tools/host) is the only layer allowed to wire concrete adapters to
   ports.**

### Enforcement: architecture boundary tests

These rules are not honor-system — they are pinned by ~33 AST-walking tests in
`MyCiteV2/tests/architecture/`. Each one parses every `.py` file in a package
and fails the build on a forbidden import or a leaked runtime/instance token.
Representative examples (read these to learn the convention):

- `MyCiteV2/tests/architecture/test_core_datum_refs_boundaries.py:42` — asserts
  `packages/core/datum_refs` imports only stdlib + `MyCiteV2.packages.core`,
  and that the source contains no instance/runtime path tokens.
- `MyCiteV2/tests/architecture/test_state_machine_boundaries.py:47` — confines
  `packages/state_machine` to `core` + `state_machine` imports and bans
  dynamic-import / glob tokens.
- `MyCiteV2/tests/architecture/test_core_datum_rules_boundaries.py` — same
  pattern for `packages/core/datum_rules`.
- `MyCiteV2/tests/architecture/test_datum_store_port_boundaries.py` and
  `MyCiteV2/tests/architecture/test_filesystem_adapter_boundaries.py` — pin the
  port/adapter seam.
- `MyCiteV2/tests/architecture/test_no_disk_datum_authorities.py` and
  `MyCiteV2/tests/architecture/test_no_filesystem_datum_authority_in_runtime.py`
  — keep the MOS-is-canonical rule honest (no on-disk datum authorities).
- `MyCiteV2/tests/architecture/test_palette_eligibility_purity.py` — purity of
  palette-eligibility logic.

The shape every one of these tests shares: a `PACKAGE_DIR`, a
`FORBIDDEN_IMPORT_PREFIXES` tuple, an `_is_allowed_absolute_import` allowlist,
and an `ast.walk` over `ast.Import` / `ast.ImportFrom` nodes that collects
violations into a list asserted empty. When you introduce a new layering rule,
add a test in this exact shape (see [Test strategy](#test-strategy) below).

### Canonical anti-example: the `core → adapters` inversion

There is one **known, live violation** of rule (1), and it is the headline
standards problem in the repo today:

- `MyCiteV2/packages/core/datum_ops/ops.py:24` imports `parse_datum_address`,
  `preview_document_delete`, `preview_document_insert`, and
  `preview_document_move` **from**
  `MyCiteV2/packages/adapters/sql/datum_semantics.py`.
- `MyCiteV2/packages/core/datum_ops/node_ops.py:17` imports
  `parse_datum_address` from the same adapter module.

That is core reaching *up* into an adapter — exactly what rule (1) forbids. The
twist: `datum_semantics.py` (663 LOC,
`MyCiteV2/packages/adapters/sql/datum_semantics.py`) is the *real*
address / hyphae / MSS engine and is not actually SQL-coupled — it imports only
`MyCiteV2.packages.ports.datum_store` and a local JSON helper
(`datum_semantics.py:7-12`). It is **misplaced**, living in the SQL adapter when
it is pure domain logic that belongs in `core`.

This violation persists for one reason: **there is no
`MyCiteV2/tests/architecture/test_core_datum_ops_boundaries.py`.** Every other
core/adapter seam has a guard test; this one does not, so nothing fails when
core imports upward. A separate work unit will (a) add that boundary test in the
shape described above and (b) relocate the engine from the SQL adapter into
`core`. Until then, treat `datum_ops` as a cautionary tale, not a pattern to
copy.

---

## Bloat budget

The stack's whole reason for being is *lean and fast, Excel-like clarity*. New
code is a liability until proven otherwise. Principles:

1. **Reuse before adding.** Before writing a new module, find the existing one.
   A new file should be the exception, justified in the PR.
2. **No duplicate engines.** One canonical implementation per concept. There is
   currently a live duplication to fix, not extend:
   `MyCiteV2/packages/core/mss/datum_identity.py` carries near-duplicate
   address parsing and `compute_mss_hash` / `derive_hyphae_chain`
   (`datum_identity.py:101` and `:126`) that overlap the real engine in
   `MyCiteV2/packages/adapters/sql/datum_semantics.py`. Both define the same
   `_DATUM_ADDRESS_RE`, `_RF_TOKEN_RE`, `_NUMERIC_HYPHEN_RE`, `_as_text`, and an
   address parser (`datum_identity.py:15-39` vs `datum_semantics.py:18-42`).
   When the engine is relocated into core, this duplication collapses into one
   home — do not paper over it by adding a third copy.
3. **Delete dead stubs, or document why they survive.** A stub that nothing
   calls is bloat. Either remove it or leave a one-line comment naming the
   future caller.
4. **Prefer subtraction.** The repo has a documented history of large
   net-negative cleanups; that is the expected direction of travel.

### Prior bloat-reduction work (precedent)

The bar for "this is worth deleting" is already set by a multi-phase
bloat-reduction program: an audit framing, concrete findings turned into work,
and a remediation execution pass. Weigh large additions against that precedent —
duplicate-definition pressure especially, which is itself test-guarded:
`MyCiteV2/tests/architecture/test_no_duplicate_definitions.py` and
`MyCiteV2/tests/architecture/test_canonical_document_naming.py` exist to catch
copy-paste drift.

---

## Caching & performance posture

Rule zero: **measure before optimizing.** The common case is a *small* datum
document. Do not add a cache, an index, or a worker pool to shave microseconds
off a path that is already fast on the real payload.

What already exists (reuse it; do not reinvent it):

- **Module-level catalog cache.**
  `MyCiteV2/packages/adapters/sql/datum_store.py:108` declares
  `_GLOBAL_CATALOG_CACHE`, keyed by `(db_path, tenant_id)` and validated against
  the SQLite file's mtime, so the four portal extensions share one fetch per
  request instead of four. Any write invalidates it
  (`datum_store.py:294`, `:452`); reads consult it first
  (`datum_store.py:598`, `:617`, `:623`). See the explanatory comment at
  `datum_store.py:105-108`.
- **Efficient single-document update path.**
  `SqliteSystemDatumStoreAdapter.replace_single_document_efficient`
  (`MyCiteV2/packages/adapters/sql/datum_store.py:296`) replaces exactly one
  document in the catalog **without re-encoding every other document's
  semantics** — use it instead of a full catalog rewrite when you touch one doc.
- **Parallel JSON prefetch** in the filesystem adapter for cold reads.

### Known hotspot (future caching candidate — not yet optimized)

`MyCiteV2/packages/tools/workbench_ui/service.py` (~992 LOC) re-derives its
view **per request**: it re-sorts, re-filters, and re-groups the catalog on
every call via helpers like `_document_sort_value` (`service.py:139`),
`_row_sort_value` (`service.py:163`), `_document_filter_haystack`
(`service.py:132`), `_row_filter_haystack` (`service.py:145`), and the
layer / value-group grouping near `service.py:197`. This reprojection is the
read hotspot. It is a *candidate* for memoization keyed on
`(catalog_mtime, query_params)` — but only after a measurement shows it matters
on a representative document. Profile first; the catalog cache underneath it may
already make this cheap enough.

---

## Test strategy

`MyCiteV2/tests/` is organized by *kind of guarantee*, not by feature:

| Directory | Guarantees |
|---|---|
| `tests/unit/` | Pure logic, one module at a time (77 files). |
| `tests/integration/` | Multiple components wired together (34 files). |
| `tests/architecture/` | **Layering / boundary / no-duplication / asset-manifest invariants** (~33 files). |
| `tests/contracts/` | Port-contract conformance (8 files). |
| `tests/adapters/` | Adapter behavior against fakes/real stores (8 files). |
| `tests/smoke/` | End-to-end "the page actually renders / serves" checks (5 files). |
| `tests/sandboxes/`, `tests/tools/` | Sandbox-load and tool-surface coverage. |

Run the full suite (~1187 tests) with the portal venv:

```bash
python -m pytest MyCiteV2/tests -q
```

Run just the architecture guards while iterating on a layering change:

```bash
python -m pytest MyCiteV2/tests/architecture -q
```

**The architecture tests are the load-bearing part of this strategy.** They are
what make "dependencies point inward" a fact rather than a hope. The standing
rule: *whenever you introduce a new layer rule, add an architecture boundary
test for it in the same session* — using the `PACKAGE_DIR` +
`FORBIDDEN_IMPORT_PREFIXES` + `ast.walk` shape shown in
`test_core_datum_refs_boundaries.py:42`. A rule with no test will rot; the
`core/datum_ops` inversion above is the proof.

---

## Front-end asset budgets

The portal shell ships a small, versioned set of JS modules and is held to a
**gzip byte budget** so the initial paint stays fast. The budgets are declared
in the shell host:

- `MyCiteV2/instances/_shared/portal_host/app.py:244` —
  `PORTAL_SHELL_INITIAL_LOAD_BUDGET_GZIP_BYTES = 41000` (~41 KB gzip for the
  startup-critical shell).
- `MyCiteV2/instances/_shared/portal_host/app.py:245` —
  `PORTAL_SHELL_TOTAL_BUDGET_GZIP_BYTES = 65000` (~65 KB gzip total).
- `MyCiteV2/instances/_shared/portal_host/app.py:246` —
  `PORTAL_SHELL_DEFERRED_BUDGET_GZIP_BYTES = 30000` (~30 KB gzip for
  deferred tool renderers; advisory).

These feed the `budget_policy` block emitted by `build_shell_asset_manifest`
(`MyCiteV2/instances/_shared/portal_host/app.py:426`, policy block at
`app.py:453-462`), where the initial-load and total budgets are tagged
`"enforcement": "hard"` and the deferred budget `"advisory"`. Each shell module
declares its `budget_group` (`initial_shell` vs `deferred_tool_renderers`) in
the `PORTAL_SHELL_MODULE_CONTRACTS` tuple (`app.py:247` onward).

What is *test-enforced today* is the **manifest ↔ static-directory integrity**,
not the byte count:
`MyCiteV2/tests/architecture/test_asset_manifest_module_presence.py` asserts
every manifest entry points at a real file in
`instances/_shared/portal_host/static/` (`:41`), that `module_id`s are unique
(`:56`), and — critically for bloat — that there are **no orphan
`v2_portal_*.js` files** shipped to the browser but unregistered (`:64`). The
shared-layout invariants live in
`MyCiteV2/tests/architecture/test_shared_site_core_layout.py`.

Contributor implication: when you add or grow a shell module, keep it in the
right `budget_group`, register it in `PORTAL_SHELL_MODULE_CONTRACTS`, and check
its gzip size against the relevant budget by hand (the byte budget is policy,
declared and `"hard"` in intent, but there is not yet a test that gzips the
files and compares — do not assume CI will catch an over-budget bundle). Defer
anything that isn't needed for first paint into the deferred group. Delete dead
modules so the orphan check stays green.

---

## Checklist for contributors (pre-PR)

- [ ] **Right layer?** New code lives in the layer that owns the concern (pure
      domain → `core`; contract → `ports`; I/O → `adapters`; wiring/UI → L3).
- [ ] **No upward import?** Nothing in `core` imports `adapters` / `ports` /
      `instances` / `tools` / `state_machine`. (Don't replicate the
      `datum_ops → datum_semantics` inversion.)
- [ ] **No duplicate engine?** You reused the canonical implementation instead
      of copying it (no third `parse_datum_address` / `compute_mss_hash`).
- [ ] **Dead code removed?** No orphan stubs or unregistered
      `v2_portal_*.js` files.
- [ ] **MOS is canonical?** No new on-disk datum authority; YAML stays
      transport-only.
- [ ] **Tests pass?** `python -m pytest MyCiteV2/tests -q`
      is green.
- [ ] **Boundary test added if you introduced a new layer rule?** A new rule
      ships with its `tests/architecture/` guard in the same PR.
- [ ] **Asset budget respected?** New/grown shell modules are in the right
      `budget_group` and within their gzip budget; manifest stays in sync.
- [ ] **Docs updated?** If the change alters a standard, this page (and any
      affected wiki page) is updated alongside the code.

---

[← Overview](00-overview-and-glossary.md)
