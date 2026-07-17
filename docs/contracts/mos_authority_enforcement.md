# MOS Authority Enforcement

## Status

Canonical — single binding contract for MOS-as-authority enforcement.
Supersedes the scattered statements catalogued in
`the internal authority-drift audit evidence`.

## The rule

The MOS authority database (`mos_authority.sqlite3`) is the **single
runtime source of truth** for datum document materialization and naming
(verbatim from `datum_document_naming_taxonomy.md:182-184`).

- The `documents` table is the canonical index.
- The `datum_document_semantics` and `datum_row_semantics` tables hold the
  authoritative content.
- All readers consult MOS. No reader, at runtime, may treat the filesystem
  as authoritative for datum content.

`the legacy `hippo` tree` is historical evidence only — not imported at runtime,
not a materialization authority, and not allowed to influence document
naming, sandbox-token resolution, or workbench rendering.

## Allowed filesystem usage

The filesystem is allowed only for these specific roles:

1. **Compiled UI surface payloads** under `data/payloads/compiled/`.
   These are renderable artifacts, not datum documents. They must not
   contain the `raw[0]` / `raw[1]` row shape characteristic of datum
   documents.
2. **Evidence and audit trails** under `<evidence>/`. Read-only
   historical records — never the source of runtime decisions.
3. **One-shot bootstrap staging** in `<evidence>/<task>/legacy_staging/`.
   JSON staging files prepared as input to a per-sandbox `bootstrap_*.py`
   ingestion script. Once ingested into MOS, the staging file ceases to
   carry authority.
4. **Append-only observation logs.** Per-extension event NDJSON files
   under `<private>/utilities/tools/<extension>/`. Each row is a
   factual observation produced by a public collector or a server-side
   probe; the file is **monotone-append** (no row is ever rewritten in
   place). Derived insights are computed on demand by pure functions
   in the corresponding `packages.core.<extension>.derivations`
   module; insights themselves are never persisted as authoritative.
   Current canonical instance:
   `<private>/utilities/tools/analytics/analytics.<domain>.events.<YYYY-MM>.ndjson`
   (contract: `analytics_event_schema.md`). Retention: 365 days online
   + cold archive at `<private>/utilities/tools/<extension>/archive/`.

   Observation logs are **not** datum documents and **must not** be
   mirrored into `mos_authority.sqlite3` as a fast-path cache. The
   `MosDatumAnalyticsSummaryAdapter` was retired in 2026-05; future
   summary-mirror adapters are explicitly forbidden — derivations
   recompute on demand from the canonical NDJSON or not at all.

## Forbidden filesystem usage

No datum-document JSON, bin, or sqlite file may live under
`<mycite-state-root>/`:

| Path | Forbidden patterns |
|---|---|
| `data/system/**` | `lv.*.json`, `sc.*.json`, `cptr.*.json`, `stl.*.json`, `rf.*.json`, `tool.*.json`, `anthology.json`, `system_log.json` |
| `data/sandbox/**` | the same patterns + `.pre-repair`, `.pre-compile-*` backups |
| `data/payloads/cache/**` | `sc.*.json` (these duplicate canonical content; recompile from MOS) |
| `data/payloads/*.bin` | zero-byte placeholders are abandoned stubs |
| `fnd/` (top level) | `*.sqlite3` (only `private/mos_authority.sqlite3` is allowed) |

`data/payloads/compiled/*.json` is the only allowed JSON content under
`data/`.

## Enforcement chain

The rule is enforced by a chain of automated checks. Each check is the
**only** required path through its specific stage; if a check is skipped,
the rule fails.

| Stage | Check | Location |
|---|---|---|
| Test (architecture) | No on-disk datum docs | `MyCiteV2/tests/architecture/test_no_disk_datum_authorities.py` |
| Test (architecture) | No filesystem adapter in runtime | `MyCiteV2/tests/architecture/test_no_filesystem_datum_authority_in_runtime.py` |
| Test (unit) | MOS-internal consistency, FS↔MOS parity, ref integrity, no compat keys, required contracts present | `MyCiteV2/tests/unit/test_mos_program_closure.py` (5 tests) |
| CI | Commit-gate on forbidden additions | `.github/workflows/tests.yml` → `no_disk_datum_docs` job |
| Tool | One-shot parity audit | `MyCiteV2/scripts/audit_mos_filesystem_parity.py` |
| Bootstrap | Per-sandbox ingestion scripts | `MyCiteV2/scripts/bootstrap_<sandbox>_anchor.py` |

Tests marked `@unittest.expectedFailure` indicate invariants that depend
on outstanding corrective work (Phases 6/7/9 of plan
`quiet-booping-stream.md`). When the corresponding correction lands, the
decorator must be removed in the same PR. An invariant whose
`expectedFailure` is upgraded to `unexpected success` should fail the
build until reconciled — that is the intended signal.

## Sandbox-add procedure

Adding a new sandbox to MOS is exclusively via a one-shot bootstrap script:

1. Stage the sandbox's source content as JSON files under
   `<evidence>/<sandbox>_bootstrap/legacy_staging/`.
2. Create `MyCiteV2/scripts/bootstrap_<sandbox>_anchor.py` modeled on
   `bootstrap_fnd_csm_anchor.py` and `bootstrap_agro_erp_anchor.py`:
   - Reads from the staging dir
   - Builds AuthoritativeDatumDocument instances
   - Computes MSS hashes via `compute_mss_hash`
   - UPSERTs into MOS via `replace_single_document_efficient` and a direct
     `documents`-table UPSERT
3. Run the script with `--dry-run` first, then for real.
4. Confirm with `audit_mos_filesystem_parity.py --strict`.
5. Move the staging files from `legacy_staging/` to a sibling
   `archived_after_ingestion/` directory; never leave them in
   `webapps/mycite/fnd/data/`.

## Legacy alias retirement schedule

The `documents.legacy_alias` column was added 2026-05-05 as one-cycle
compatibility for the `lv./stl./cptr.` migration. Two phases:

- **Phase 1 (2026-05-05 → 2026-06-05): dual-lookup active.**
  Readers accept either canonical or legacy IDs. New writes must produce
  canonical IDs. Filesystem callers' legacy filenames remain resolvable
  through the alias.
- **Phase 2 (2026-06-05 onward): column dropped.**
  Pre-cutover datum_document_semantics / datum_row_semantics rows that
  still use legacy IDs must be re-keyed to canonical form before this
  date. After the cutover:
  - The `legacy_alias` column is dropped from the `documents` table
  - Dual-lookup paths (`WHERE document_id = ? OR legacy_alias = ?`) are
    removed from `MyCiteV2/packages/adapters/sql/datum_store.py`
  - Test `test_no_legacy_compatibility_document_keys_remain_as_primary_ids`
    (currently `@unittest.expectedFailure`) becomes required.

The migration script `MyCiteV2/scripts/drop_legacy_alias_column.py`
performs the schema change. It refuses to run if any row in
`datum_*_semantics` still uses a legacy `sandbox:` or `system:` form
document_id as primary key. As of 2026-05-17 the preconditions are
already satisfied — see `evidence/mos_authority_drift_audit_2026-05-17/`.
On 2026-06-05 the operator runs::

    python -m MyCiteV2.scripts.drop_legacy_alias_column \
        --authority-db <authority-db>.sqlite3

The script is idempotent (subsequent runs return
`status=already_retired`).

## Cross-references

This document supersedes the rule-statement portions of the following
documents. They retain their narrower contracts and should link here
rather than restating the rule:

- `datum_document_naming_taxonomy.md` (§182-209)
- `cts_gis_legacy_alias_retirement_timeline.md` (request-side aliases;
  augment with the documents-column section per this doc)
- `mos_database_schema_addendum.md` (schema only)
- `samras_structural_model.md` (SAMRAS encoding only)
- `service_tool_peripheral_package_contract.md` (peripheral data only)
- `the internal MOS consolidation notes`
  (point-in-time guidance — the rule moved here)

## Drift audit history

- **2026-05-17** — Comprehensive drift audit landed at
  `the internal authority-drift audit evidence`.
  Found 141 on-disk datum artifacts + 2 stale sqlite databases + 287
  phantom cts_gis index rows + 25 orphan fnd_csm semantic payloads +
  5 skipped anti-drift tests. Phases 1-5, 8, 10 corrected. Phases 6, 7, 9
  + MOS internal reconciliation deferred to follow-up (the corresponding
  tests are `@unittest.expectedFailure` until those land).
