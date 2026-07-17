# 70 · YAML Materialization Pipeline

> Status: design-spec
>
> [← Overview](00-overview-and-glossary.md)

This page specifies a single runtime working surface for the MiCyte datum
workbench: every sandbox is materialized as **standardized-convention-aligned
WORKBOOK-YAML at runtime**, a fixed catalog of **modular functions operates on
that YAML form**, and edits **pipeline back into the MOS database** through one
store-bound executor. The MOS database stays canonical; YAML is never persisted
as the authority.

The convention this page builds on already exists and is already documented in
code as "the standardized, interface-ready YAML form tools/lenses/UI consume"
(`MyCiteV2/packages/core/datum_ops/workbook.py:5`). What does not yet exist is a
*single* surface: the **write** path runs through WORKBOOK-YAML, while the
**read/render** path is a parallel SQL→JSON projection that bypasses it. This
page is a proposal to close that split.

---

## Problem

The workbench has two materialization conventions for the same underlying
datum documents, and they do not share a model:

1. **The read/render split.** When the UI renders a sandbox, the read service
   reads the authoritative catalog out of SQL and projects it straight to a
   render JSON model — it never passes through the WORKBOOK-YAML codec. When the
   UI saves an edit, the mutation runtime takes WORKBOOK-YAML text, decodes it
   through the codec, compiles ops, plans a migration, and applies. So a row the
   user is *looking at* and a row the user is *saving* are described by two
   different in-memory shapes produced by two unrelated code paths.

2. **Two conventions to keep in sync.** Every field the render projection
   computes (recognized family, resolved lens, hyphae/semantic identity,
   grouping, sort) is computed in projection logic that has no counterpart in
   the YAML round-trip. The YAML codec carries `{address, raw}` verbatim and
   nothing else (see *Data shapes* below); the projection re-derives a much
   richer per-row view every call. Two materializers means two places to evolve
   when the datum conventions change.

3. **Per-request reprojection cost.** The read service re-reads, re-filters,
   re-sorts, and re-groups the *entire* document set on every request, and for
   the selected document it re-runs per-row datum recognition plus per-row SQL
   semantic-identity reads. For pure view-only navigation (toggling a sort, a
   group mode, a lens; selecting a different row) the underlying catalog has not
   changed, so that recognition + SQL work is repeated waste. A projection cache
   was added to mitigate this (see *Current reality*), but it caches the
   *projection*, not a shared materialized working form — the read and write
   sides still don't meet.

The user's stated vision is a document-processor experience (like Excel): the
rules are clear and fixed, and the software simply enables interfacing and
manipulation *within* the rules, over one working surface. Two parallel
materializers is the opposite of one working surface.

---

## Current reality

> All paths below were read before citing. Line anchors are to the files as they
> exist at the time of writing.

### The WORKBOOK-YAML convention exists (transport only)

`MyCiteV2/packages/core/datum_io/codec.py` defines the codec. It is explicitly a
transport format — *"This is a TRANSPORT format only: the MOS database remains
the canonical authority … nothing here writes datum state to disk"*
(`codec.py:1`). The multi-sheet envelope is `mycite.v2.datum_io.workbook.v1`
(`codec.py:26`), produced by `workbook_to_yaml(sandbox, documents)`
(`codec.py:97`) and reconstructed by `workbook_from_yaml(text) -> (sandbox,
[documents])` (`codec.py:112`). Single documents round-trip through
`to_yaml`/`from_yaml` (`codec.py:55`, `codec.py:88`) with an MSS-version-identity
round-trip guarantee.

The `Workbook ⇄ WORKBOOK-YAML` bridge sits one layer up in
`MyCiteV2/packages/core/datum_ops/workbook.py`. Its module docstring names this
form *"the standardized, interface-ready YAML form tools/lenses/UI consume.
Transport only; never persisted (MOS-only storage rule)"* (`workbook.py:5`). It
exposes `to_yaml(workbook)` (`workbook.py:16`) and `from_yaml(text) -> Workbook`
(`workbook.py:28`), keying sheets by the canonical-name segment of the document
id.

### The write path runs through WORKBOOK-YAML

`MyCiteV2/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py`
implements the `apply_workbook` operation (`...:39`, dispatched at `...:576`).
Its core, `_run_workbook_mutation_action` (`...:480`), is the canonical
edited-YAML → MOS pipeline:

```
edited = workbook_codec.from_yaml(edited_yaml)   # ...:511
ops    = compile_workbook(baseline, edited)       # ...:515  (diff → op sequence)
plan   = plan_migration(baseline, ops)            # ...:516  (pure planner)
result = execute_migration(authority_db_file, plan, tenant_id=tenant_id)  # ...:533
```

`stage`/`validate`/`preview` run the pure planner only (no writes); `apply`
runs the store-bound executor. The executor,
`MyCiteV2/packages/adapters/sql/datum_workbook_apply.py`, loads a sandbox into a
`Workbook` (`load_workbook`, `datum_workbook_apply.py:36`) and applies the plan
as *backup → write → index → verify* (`execute_migration`,
`datum_workbook_apply.py:103`/`:111`), restoring from backup on a verify
failure. So the write side already treats WORKBOOK-YAML as its working surface.

### The read/render path does NOT run through WORKBOOK-YAML

`MyCiteV2/packages/tools/workbench_ui/service.py` (~990 LOC) is the render path.
`WorkbenchUiReadService` (`service.py:468`) reads the authoritative catalog
directly out of SQL — `read_authoritative_datum_documents(...)`
(`service.py:598`) — and `_compute_surface` (`service.py:630`) filters, sorts,
groups, and per-row recognizes it into a render JSON model whose surface payload
is tagged `"kind": "sql_authority_lens"` (`service.py:931`). The heavy per-row
work — `recognize_authoritative_document` plus a `read_datum_semantic_identity`
SQL read for each row — lives in `_row_items` (`service.py:497`). At no point
does the read path call `workbook_to_yaml` / `workbook_from_yaml`; it is a second
materializer of the same catalog, independent of the codec the write path uses.

### The projection cache (mitigation, not unification)

A process-local projection cache was added to blunt the reprojection cost:
`_GLOBAL_SURFACE_CACHE` (`service.py:412`), keyed by a content fingerprint of the
catalog (`_catalog_fingerprint`, `service.py:416`) plus the normalized view
parameters. `read_surface` (`service.py:586`) returns a deep copy on a hit and
only stores entries that resolved no live directive overlay. This is real and
useful, but it memoizes the *projection output*; it does not give the read and
write sides a *shared materialized working form*. The two conventions remain.

### The modular functions exist (pure ops)

The "modular functions for working with and on the runtime form" already exist as
pure, store-agnostic ops in `MyCiteV2/packages/core/datum_ops/`. The package
docstring describes the model exactly: *"A sandbox loads as a `Workbook` (named
sheets); operations transform it in memory and a single store-bound executor
persists the cascade"* (`datum_ops/__init__.py:6`). The public surface
(`datum_ops/__init__.py:53`) exports:

| Tier | Ops | Source |
|---|---|---|
| Row-level (intra-sheet) | `InsertRow`, `DeleteRow`, `MoveRow`, `ReorderRow` | `datum_ops/ops.py:105`–`:172` |
| Node-address (cross-sheet) | `MintNode`, `RelocateNode`, `RepointNode`, `RenameNode`, `DropNode`, `RewriteRefs`, `RecompileMagnitude`, `RebuildCollection` | `datum_ops/node_ops.py` |
| Threading | `apply_sequence(workbook, ops) -> (workbook, [delta])` | `datum_ops/ops.py:85` |
| Diff→ops | `compile_workbook(baseline, edited)` | `datum_ops/compiler.py:50` |
| Plan | `plan_migration(baseline, ops) -> MigrationPlan` | `datum_ops/migrate.py:82` |

Each op is a frozen dataclass with `apply(workbook) -> WorkbookDelta`
(`ops.py:3`); the `WorkbookDelta` it returns is defined at `ops.py:69`. They are
*pure*: they never touch a store. That is precisely the
"modular functions on the runtime YAML" the vision calls for — but today only the
write path consumes them; the render path has its own projection logic instead.

---

## Proposed model

> **Proposal.** Everything in this section is a design proposal, not current
> behavior.

Unify **both** read and write on the WORKBOOK-YAML convention as the single
runtime working surface. The `Workbook` (decoded from WORKBOOK-YAML) becomes the
one in-memory working form; render derives *from* it, and edits flow *through*
it. MOS stays canonical.

### Lifecycle

```
load sandbox                read_authoritative_datum_documents(tenant) → catalog
   │                        (SQL is canonical; this is the freshness signal)
   ▼
materialize WORKBOOK-YAML    catalog → Workbook → workbook_codec.to_yaml(...)
   │                        (the single runtime working form; transport only)
   ▼
modular functions operate    datum_ops ops over the Workbook in memory
   │                        (InsertRow/.../MintNode/RelocateNode/...)
   ▼
render derives from it       a render projection computed FROM the same Workbook,
   │                        not a parallel SQL→JSON path
   ▼
preview                      compile_workbook → plan_migration  (pure, no writes)
   │                        stage / validate / preview stop here
   ▼
pipeline to MOS-save         execute_migration(db, plan)  backup → write → verify
```

The key change versus today: the render projection (the work in
`service.py:_row_items` / `_compute_surface`) is re-expressed as a function **of
the materialized `Workbook`**, so read and write share one decode of one
convention. The projection becomes a *lens over the working form*, not a second
materializer of the catalog.

### Modular-function catalog (already implemented; this is the contract the UI binds to)

These are the fixed "rules" of the document processor. The UI never invents
shapes; it composes these:

- **Row edits within a sheet** — `InsertRow`, `DeleteRow`, `MoveRow`,
  `ReorderRow` (`ops.py:105`–`:172`). Thin wrappers over the trusted intra-doc
  reorder engine, inheriting its iteration-shift, intra-doc reference remap,
  contiguity guard, and delete-while-referenced block (`ops.py:10`).
- **Structural / node-address edits across sheets** — `MintNode`,
  `RelocateNode`, `RepointNode`, `RenameNode`, `DropNode`, plus the housekeeping
  ops `RewriteRefs`, `RecompileMagnitude`, `RebuildCollection`
  (`node_ops.py`). These change node-address *values* and therefore cascade to
  every sheet that references the moved node.
- **Diff inference** — `compile_workbook(baseline, edited)` (`compiler.py:50`)
  lets the UI hand back *edited YAML* without knowing the op grammar; it infers
  relocate/rename/mint/drop by node title and appends the SAMRAS housekeeping
  cascade in the order `plan_migration` expects.
- **Plan + verify expectations** — `plan_migration` (`migrate.py:82`) re-mints
  canonical ids from the new MSS hash, rule-checks (HARD issues abort), asserts
  SAMRAS magnitudes match their source node sets, and records row-count /
  closure-size expectations the executor re-verifies.

### Excel / document-processor UX contract

- **Fixed rules.** The op catalog above *is* the rule set. The UI exposes only
  these operations; malformed shapes are rejected at the edge (the write runtime
  already does this — `_reject_malformed_row`,
  `portal_datum_workbench_mutation_runtime.py:72`). The user manipulates within
  the rules; they cannot author an arbitrary shape.
- **Cell-level edit.** A "cell" is a datum row's `raw` (or a head token within
  it). A single-cell edit is an in-place `update_row_raw` on the materialized
  sheet; a structural edit (insert/move/relocate/mint) is the corresponding op.
  Every edit is staged into the working `Workbook`, never written until save.
- **Equation-vs-value lenses.** Like a spreadsheet showing the formula vs. the
  computed value, the workbench keeps a `raw` lens (the stored value/equation,
  i.e. `workbench_lens=raw`) and an `interpreted` lens (the resolved, recognized,
  display value). Both lenses are *views over the same materialized working
  form* — the render projection's lens resolution becomes a pure function of the
  `Workbook`, removing the second materializer. The lens vocabulary already
  exists in the read service (`WORKBENCH_UI_DEFAULT_LENS`, `_LENS_MODES` in
  `service.py`); the proposal is to drive it from the shared form. See
  `30-l3-shell-runtime-ui.md` for the grid/shell that renders these lenses.

---

## Data shapes / interfaces

### WORKBOOK-YAML schema (already in `codec.py`)

The on-the-wire / in-memory form is `mycite.v2.datum_io.workbook.v1`
(`codec.py:26`). It is deliberately minimal — identity + verbatim rows — so the
round-trip preserves MSS version identity:

```yaml
schema: mycite.v2.datum_io.workbook.v1
sandbox: <sandbox-id>
sheets:
  - schema: mycite.v2.datum_io.document.v1
    document_id: <canonical id>
    document_name: <name>
    canonical_name: <name>
    relative_path: <path>
    source_kind: system_anthology | sandbox_source
    source_authority: <authority>
    tool_id: <tool>
    is_anchor: <bool>
    document_metadata: { ... }
    rows:
      - { address: <datum_address>, raw: <verbatim raw> }
```

Per-sheet payload is built by `_document_payload` (`codec.py:39`); each row is
`{address, raw}` (`codec.py:31`). Everything richer the UI shows (recognized
family, lens, hyphae/semantic identity, grouping) is *derived* from `{address,
raw}` — it is not carried in the YAML, which is exactly why a single
materialization (decode once, derive once) is feasible.

### The op → migrate → apply pipeline interface

```
workbook_codec.from_yaml(text)            -> Workbook              # datum_ops/workbook.py:28
compile_workbook(baseline, edited)        -> list[op]              # compiler.py:50
plan_migration(baseline, ops)             -> MigrationPlan         # migrate.py:82
execute_migration(db, plan, tenant_id=…)  -> dict (apply summary)  # datum_workbook_apply.py:103
```

`MigrationPlan` (`migrate.py:70`) carries `touched: {name: TouchedSheet}`,
`write_order`, `expectations` (row counts + SAMRAS closure sizes), and
`advisories`. `TouchedSheet` (`migrate.py:62`) carries `prior_id`,
`new_document`, and `new_hash`. The executor writes touched sheets in
`write_order`, upserts the documents index, and verifies the recorded
expectations, restoring from backup on failure
(`datum_workbook_apply.py:103`–`:164`).

For authoring guidance on binding a tool to this pipeline, see
`80-tool-authoring-guide.md`. For repo-wide conventions (purity boundaries,
adapter-only SQL), see `05-engineering-standards.md`.

---

## Migration path

Incremental, behavior-preserving, MOS-canonical throughout. No step requires
persisting YAML.

1. **Route the read projection through the codec.** In `WorkbenchUiReadService`,
   after reading the catalog (`service.py:598`), materialize the working form via
   `workbook_codec.to_yaml` / `from_yaml` (or build the `Workbook` directly and
   serialize once), and re-express `_compute_surface` / `_row_items`
   (`service.py:630` / `service.py:497`) as functions over that shared form. The
   render output is unchanged; the *source* of the render becomes the same
   convention the write path decodes.

2. **Add a render-side cache keyed on snapshot + query.** The existing
   `_catalog_fingerprint` + view-parameter key (`service.py:416`,
   `service.py:_surface_cache_key`) is the right shape; extend the cache to hold
   the *materialized working form* (or its derived projection) so view-only
   toggles never re-materialize. Keep the existing invalidation discipline (the
   catalog read is the freshness signal; overlay-resolving projections are not
   cached) — see *Open questions* on caching the working form vs. the projection.

3. **Share one decode for read and write.** Once read materializes a `Workbook`,
   a stage/preview can hand the *same* working form to `compile_workbook` /
   `plan_migration` without a second decode, so a user's in-flight edits and the
   preview operate on one object.

4. **Keep MOS canonical.** No step persists YAML to disk; the codec stays
   transport-only (`codec.py:1`, `workbook.py:5`). SQL remains the freshness
   signal and the only durable store. The MOS-only datum storage rule is
   unchanged.

---

## Open design questions

- **Materialize-on-read cost vs. caching.** Materializing the full WORKBOOK-YAML
  for a large sandbox on every read may cost more than today's
  selected-document-only projection (the read service only deeply processes the
  *selected* document in `_row_items`). Should materialization be lazy
  per-sheet, and should the cache hold the decoded `Workbook`, the serialized
  YAML text, or the derived render projection? Caching the `Workbook` shares the
  most work with the write path; caching the projection matches today's behavior.
- **Client-side vs. server-side working form.** Does the UI hold the materialized
  YAML/working form client-side (edit locally, post the whole edited YAML on
  save — matching today's `apply_workbook` which takes `edited_workbook_yaml`)
  or server-side (a session-scoped working form the UI mutates via op calls)?
  Client-side keeps the server stateless and reuses the existing apply contract;
  server-side enables finer op-level preview but needs session lifecycle and
  concurrency handling.
- **Per-row derived fields in the shared form.** The render needs recognized
  family / lens / hyphae identity that the YAML does not carry. Should these be
  computed into a *derived overlay* keyed by the `Workbook` snapshot (cacheable,
  re-derivable) rather than threaded into the working form (which would break the
  MSS round-trip guarantee)? The proposal assumes a derived overlay.
- **Concurrency / staleness on apply.** `apply_workbook` recomputes `baseline`
  from the live store at apply time (`portal_datum_workbench_mutation_runtime.py:510`).
  If read materialized an earlier snapshot, the diff is computed against a fresher
  baseline. Is that acceptable (last-writer-wins on a re-diff) or does the UI need
  an optimistic-concurrency check against the snapshot version hash?

---

## Acceptance

A future implementation satisfies this spec when:

1. The read/render path materializes the sandbox through the WORKBOOK-YAML codec
   (`codec.py` / `datum_ops/workbook.py`) and derives its render model from that
   shared `Workbook`, rather than from an independent SQL→JSON projection in
   `service.py`.
2. Read and write share a single materialization convention — there is one decode
   of `mycite.v2.datum_io.workbook.v1`, not two parallel materializers.
3. The modular-function catalog (`datum_ops` row + node ops, `compile_workbook`,
   `plan_migration`, `execute_migration`) is the only way the UI mutates a
   sandbox, and the document-processor UX contract (fixed rules, cell-level edit,
   equation-vs-value lenses) is expressed as views/ops over the shared form.
4. A render-side cache keyed on catalog snapshot + normalized query eliminates
   re-materialization for view-only navigation, with invalidation tied to the
   catalog freshness signal (no stale overlays).
5. MOS remains canonical: no YAML is persisted as authority; the codec stays
   transport-only.
6. Render output for existing sandboxes is unchanged (the migration is
   behavior-preserving), verified against the current `sql_authority_lens`
   surface payload.

---

*Forward references (sibling wiki pages, may not yet exist):*
[`05-engineering-standards.md`](05-engineering-standards.md) ·
[`30-l3-shell-runtime-ui.md`](30-l3-shell-runtime-ui.md) ·
[`80-tool-authoring-guide.md`](80-tool-authoring-guide.md)
