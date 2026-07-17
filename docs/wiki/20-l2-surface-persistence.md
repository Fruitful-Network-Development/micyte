# L2 Surface — Datum Persistence

> Status: as-built
[← Overview](00-overview-and-glossary.md)

## Purpose

This page documents the **L2 SURFACE** persistence seam for datum documents: the
ports/adapters layer that sits between L1 CORE (the datum address/MSS algebra)
and L3 UI (the portal shell and workbench). It covers how a datum document is
defined as a contract, how it is read from and written to the **MOS authority
database** (SQLite today), how the read-only filesystem adapter seeds and mirrors
that store, how the canonical MSS-per-document title is composed, and where
"sandboxes" actually live in the model.

The governing rule for this layer: **the MOS DB is the canonical datum store;
filesystem JSON is dev/test/bootstrap only.** L2 adapters operate strictly within
MOS rules — canonical-only writes, one document per row, MSS form.

## File map

### Port (the contract — adapter-neutral)

| `path:line` | Role | LOC |
|---|---|---|
| `MyCiteV2/packages/ports/datum_store/contracts.py:123` | `AuthoritativeDatumDocument` — the canonical datum-document value object: `document_id`, `source_kind` (`system_anthology`/`sandbox_source`), `rows`, `anchor_rows`, `tool_id`, `document_metadata`. | 775 |
| `MyCiteV2/packages/ports/datum_store/contracts.py:89` | `AuthoritativeDatumDocumentRow` (`datum_address` + `raw`) — one datum address-line ("Row" in the unit brief) inside a document. | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:264` | `AuthoritativeDatumDocumentCatalogResult` — the whole-tenant catalog (tuple of documents + `source_files` + `readiness_status`). | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:717` | `SystemDatumStorePort` — read the system resource workbench surface. | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:723` | `AuthoritativeDatumDocumentPort` — read authoritative documents. | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:732` | `AuthoritativeDatumDocumentMutationPort` — adds `read_document_version_identity`, `replace_authoritative_document`, `delete_authoritative_document`. | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:760` | `PublicationTenantSummaryPort` — read one tenant profile projection. | — |
| `MyCiteV2/packages/ports/datum_store/contracts.py:770` | `PublicationProfileBasicsWritePort` — one bounded profile-basics write with read-after-write confirmation. | — |
| `MyCiteV2/packages/ports/datum_store/__init__.py:1` | Public re-export surface for the port. | 53 |
| `MyCiteV2/packages/ports/datum_store/README.md:1` | Port README (currently a one-line placeholder). | — |

### SQL authority adapter (the writer)

| `path:line` | Role | LOC |
|---|---|---|
| `MyCiteV2/packages/adapters/sql/datum_store.py:111` | `SqliteSystemDatumStoreAdapter` — implements all four ports against SQLite. The canonical authority. | 1066 |
| `MyCiteV2/packages/adapters/sql/datum_store.py:182` | `store_authoritative_catalog` — full-catalog UPSERT: rewrites every doc's + row's semantics for the tenant. | — |
| `MyCiteV2/packages/adapters/sql/datum_store.py:296` | `replace_single_document_efficient` — O(rows-in-one-doc) swap; the hot path for single-document edits (avoids the full re-encode). | — |
| `MyCiteV2/packages/adapters/sql/datum_store.py:498` | `bootstrap_from_filesystem` — one-way seed: filesystem catalog → SQL (optionally canonicalizing legacy ids). | — |
| `MyCiteV2/packages/adapters/sql/datum_store.py:580` | `read_authoritative_datum_documents` — cached catalog read + canonical-id projection. | — |
| `MyCiteV2/packages/adapters/sql/datum_store.py:108` | `_GLOBAL_CATALOG_CACHE` — module-level `(db_path, tenant_id) → (mtime_ns, catalog)` cache shared across ephemeral adapter instances; mtime-invalidated, also popped on every write. | — |
| `MyCiteV2/packages/adapters/sql/datum_store.py:45` | `NonCanonicalDocumentIdError` — raised when a write would persist a non-canonical id (unless `allow_legacy_writes`). | — |
| `MyCiteV2/packages/adapters/sql/datum_semantics.py:209` | `build_document_semantics` — the address/hyphae/MSS engine: per-row hyphae chains, semantic hashes, version identity. **Misplaced here** (see Vision-fit). | 663 |
| `MyCiteV2/packages/adapters/sql/datum_semantics.py:136` | `build_document_version_identity` — MSS SHA-256 over the canonicalized row set (`mos.mss_sha256_v1`). | — |
| `MyCiteV2/packages/adapters/sql/datum_semantics.py:474` | `preview_document_insert` / `_delete` (526) / `_move` (587) — pure address-remap mutations consumed by the adapter's apply/preview methods. | — |
| `MyCiteV2/packages/adapters/sql/datum_workbook_apply.py:103` | `execute_migration` — store-bound workbook executor: backup → write-in-order → index → verify → restore-on-failure. | 164 |
| `MyCiteV2/packages/adapters/sql/_sqlite.py:9` | `SCHEMA_SQL` — the full DB schema (snapshot tables + `documents` index + semantics tables + directive-context). | 155 |
| `MyCiteV2/packages/adapters/sql/_sqlite.py:138` | `connect_sqlite` / `open_sqlite` — WAL, `foreign_keys=ON`, idempotent schema bootstrap. | — |
| `MyCiteV2/packages/adapters/sql/directive_context.py:54` | `SqliteDirectiveContextAdapter` — sibling adapter; shared-shell directive overlays keyed by `(portal_instance_id, tool_id, hyphae_hash, version_hash)`. | 223 |
| `MyCiteV2/packages/adapters/sql/portal_authority.py:23` | `SqlitePortalAuthorityAdapter` — sibling adapter; portal-scope grants / tool-exposure read seam. | 103 |

### Filesystem adapter (read-only seed/mirror) + core naming + accessor

| `path:line` | Role | LOC |
|---|---|---|
| `MyCiteV2/packages/adapters/filesystem_datum/live_system_datum_store.py:188` | `FilesystemSystemDatumStoreAdapter` — **read-only** discovery of `data/system/sources/*.json` + `data/sandbox/<tool>/sources/*.json` + tool anchors. | 856 |
| `MyCiteV2/packages/adapters/filesystem_datum/live_system_datum_store.py:347` | `read_authoritative_datum_documents` — the directory walk that produces the legacy-keyed catalog. | — |
| `MyCiteV2/packages/adapters/filesystem_datum/live_system_datum_store.py:139` | `_document_id_for_path` — emits legacy ids (`system:anthology`, `sandbox:<tool>:<file>`). | — |
| `MyCiteV2/packages/core/document_naming/__init__.py:65` | `format_canonical_document_id` — composes `lv./stl./cptr.` ids. | 338 |
| `MyCiteV2/packages/core/document_naming/__init__.py:109` | `parse_canonical_document_id` — single validation point for canonical ids. | — |
| `MyCiteV2/packages/core/document_naming/__init__.py:238` | `derive_canonical_id_from_legacy` — migrates `system:`/`sandbox:`/`payload:`/`cache:` → canonical. | — |
| `MyCiteV2/instances/_shared/datum_store_accessor.py:26` | `_datum_store_for_authority_db` — neutral accessor; caches one canonical-only adapter per resolved DB path. | 45 |
| `MyCiteV2/packages/sandboxes/system/__init__.py:1` | Empty stub (`"""Inert package scaffold."""`). | 1 |
| `MyCiteV2/packages/sandboxes/orchestration/__init__.py:1` | Empty stub (`"""Inert package scaffold."""`). | 1 |

## How it works

### Port ↔ adapter wiring

The port (`ports/datum_store/contracts.py`) defines four runtime-checkable
`Protocol`s and a set of frozen, self-validating dataclasses (`__post_init__`
normalizes/validates and rejects bad shapes early). It imports nothing but
`core.identities`, so it is adapter-neutral.

Two adapters implement the read protocols:

- `SqliteSystemDatumStoreAdapter` (`adapters/sql/datum_store.py:111`) implements
  **all four** ports — read, mutate, publication-summary read, and
  publication-basics write. It is the only writer.
- `FilesystemSystemDatumStoreAdapter` (`adapters/filesystem_datum/live_system_datum_store.py:188`)
  implements only `SystemDatumStorePort` and the read methods. It is **read-only**
  and exists for bootstrap/dev.

Runtime modules reach the SQL adapter through the neutral accessor
(`instances/_shared/datum_store_accessor.py:26`), which caches one
`allow_legacy_writes=False` adapter per resolved authority-DB path. The portal
host resolves that DB path from env (`MYCITE_V2_PORTAL_AUTHORITY_DB`,
`portal_host/app.py:630`).

### Save-to-MOS path

A single-document edit (the common case — e.g. a contact-log row insert) flows:

1. UI calls an apply method on the adapter, e.g. `apply_document_insert`
   (`datum_store.py:920`).
2. The adapter loads the current document from the cached catalog
   (`_catalog_with_document`, `datum_store.py:827`) and runs the **pure** mutation
   planner `preview_document_insert` from `datum_semantics.py:474`, which produces
   an `updated_document` with re-numbered datum addresses and remapped local refs.
3. `_persist_updated_document` (`datum_store.py:839`) swaps the doc into the catalog
   tuple and calls `store_authoritative_catalog` (`datum_store.py:182`).
4. `store_authoritative_catalog` UPSERTs the catalog snapshot, then **re-derives
   and re-writes** `datum_document_semantics` + `datum_row_semantics` for every
   doc of the tenant (computing version hash + per-row hyphae chains via
   `build_document_semantics`).
5. Both cache layers (`_catalog_cache` per-instance and `_GLOBAL_CATALOG_CACHE`
   module-level) are invalidated.

Because step 4 is O(all rows in the tenant), the perf-sensitive path uses
`replace_single_document_efficient` (`datum_store.py:296`) instead: it swaps a
single doc in the catalog tuple and DELETE/INSERTs semantics rows **only for the
changed doc** (and the prior id if it differs) — O(rows-in-one-doc). The workbook
executor (`datum_workbook_apply.py:135`) uses this path per touched sheet.

Writes pass through canonical-id enforcement: `store_authoritative_catalog`
(`datum_store.py:203`) and `replace_single_document_efficient` (`datum_store.py:331`)
raise `NonCanonicalDocumentIdError` unless every `document_id` parses as canonical
(or `allow_legacy_writes`/`allow_non_canonical_catalog_ids` is explicitly set —
the one-cycle bootstrap escape hatch).

`store_authoritative_catalog` runs its semantics rewrite under `PRAGMA
journal_mode=MEMORY` + `temp_store=MEMORY`, restoring the prior pragmas in a
`finally` (`datum_store.py:284`). The whole rewrite is a single transaction
committed at the end (`datum_store.py:283`).

### MSS-per-doc title

Canonical document ids are the MSS-per-document title. They are composed and
validated only in `core/document_naming/__init__.py`:

- `lv.<msn_id>.<sandbox>.<name>.<hash>` — a datum document inside a sandbox
  (`format_canonical_document_id`, `__init__.py:65`; `_LV_RE`, `__init__.py:21`).
- `stl.<msn_id>.<name>.<hash>` — payload/stored-blob style (no sandbox segment).
- `cptr.<msn_id>.<name>.<hash>` — cache-pointer style (no sandbox segment).

`<hash>` is the 64-char lowercase SHA-256 over the document's MSS form, produced
by `build_document_version_identity` (`datum_semantics.py:136`, policy
`mos.mss_sha256_v1`). The `documents` table CHECK-constrains `prefix IN
('lv','stl','cptr')` (`_sqlite.py:56`) and stores the parsed `msn_id`, `sandbox`,
`name`, `version_hash` columns alongside the full `document_id`.

The vision speaks of `<document_type>.<msn_id>.<sandbox>.<name>.<hash>`. Today the
`<document_type>` slot is exactly these three prefixes (`lv`/`stl`/`cptr`). That
reconciliation is captured in `61-mss-and-hyphae-form-spec.md` (forward ref).

### Sandbox modeling

`MyCiteV2/packages/sandboxes/system/` and `sandboxes/orchestration/` are
**empty stubs** — confirmed: each `__init__.py` is the single line
`"""Inert package scaffold."""` and the READMEs say "Placeholder". There is no
sandbox-orchestration engine.

Sandbox identity is instead carried entirely by:

1. The canonical document id's `<sandbox>` segment (`lv.<msn>.<sandbox>.<name>.<hash>`),
   parsed into the `documents.sandbox` column (`_sqlite.py:58`, indexed at
   `_sqlite.py:66`).
2. The `tool_id` field on `AuthoritativeDatumDocument` (`contracts.py:129`).
3. On the dev/seed side, the filesystem adapter's directory walk: each
   `data/sandbox/<tool>/` directory is one sandbox; `sources/*.json` are its
   documents and `tool*.json` is its anchor (`live_system_datum_store.py:347`,
   `_find_tool_anchor_file`, `:101`). The legacy id `sandbox:<tool>:<file>` is
   minted there (`:139`) and later canonicalized to the `<sandbox>` token via
   `derive_canonical_id_from_legacy` (`document_naming/__init__.py:238`, using
   `_sanitize_sandbox_token` so `cts-gis` → `cts_gis`).

The workbook loader keys sheets by sandbox segment by string-splitting the
document id (`datum_workbook_apply.py:39`: `f".{sandbox}." in d.document_id`).

### Instance / tenant layout

One tenant = one on-disk bubble plus one MOS DB. For FND the live root is
`<mycite-state-root>/`:

- `private/mos_authority.sqlite3` — the **canonical** MOS authority DB (244 MB
  live as of this audit). The portal host points at it via
  `MYCITE_V2_PORTAL_AUTHORITY_DB` (`app.py:630`). It is the single SQLite file;
  the architecture test `test_no_extra_sqlite_databases_under_fnd`
  (`tests/architecture/test_no_disk_datum_authorities.py:74`) forbids any other
  `*.sqlite3` under the tenant.
- `private/` also holds `config.json`, `local_audit/`, `network/`, etc.
- `public/` — published profiles.
- `data/` — `payloads/` (compiled UI surfaces, exempt) and, in dev, the
  `system/`/`sandbox/` JSON trees the filesystem adapter walks.

The host config resolves `PUBLIC_DIR`, `PRIVATE_DIR`, `DATA_DIR`, and the
authority DB from env (`app.py:618-633`), so the tenant root is not hardcoded —
which is what keeps the design form-factor-agnostic for the desktop end state.

### SQL vs. filesystem (split-brain risk)

The two stores are **not** kept in sync:

- SQL is the **only writer** and the canonical authority.
- `bootstrap_from_filesystem` (`datum_store.py:498`) is **one-way**
  (filesystem → SQL). There is no back-sync from SQL to disk.
- Filesystem JSON is dev/test/bootstrap only. Two architecture tests enforce
  this in production:
  - `test_no_filesystem_datum_authority_in_runtime.py` — no runtime module under
    `MyCiteV2/instances/` may import `FilesystemSystemDatumStoreAdapter` or glob
    `data/sandbox`/`data/system` paths (`:28-35`, `:68`).
  - `test_no_disk_datum_authorities.py` — no datum-doc-shaped JSON/.bin files may
    exist under the live `data/{system,sandbox,payloads/cache}/` (`:42`).

So the only safe direction is disk → DB at bootstrap time; once live, the DB is
authoritative and the disk tree is expected to be empty of datum content.

## Vision-fit

### Implemented

- **Ports/adapters discipline.** A clean adapter-neutral port with frozen,
  self-validating contracts; the SQL adapter is the sole authority and implements
  every port. L2 operates strictly within MOS rules.
- **MSS form, one document per doc.** Each `AuthoritativeDatumDocument` persists as
  one catalog entry + one `datum_document_semantics` row keyed by canonical
  `document_id`; the title is the canonical MSS id.
- **Canonical-only writes.** `NonCanonicalDocumentIdError` + the
  `allow_legacy_writes=False` default in the accessor enforce that new writes
  produce `lv./stl./cptr.` ids.
- **MOS DB canonical; disk is dev/test.** Enforced both in code (one-way bootstrap,
  no back-sync) and by two architecture tests.
- **Form-factor-agnostic persistence (partial→ready).** Tenant root and DB path are
  env-resolved, not hardcoded; the adapter only needs a writable SQLite file path.
  This is the cleanest foothold for the desktop / local-DB end state — a desktop
  build can point `MYCITE_V2_PORTAL_AUTHORITY_DB` at a local file with no code
  change.

### Partial

- **Per-document efficient writes.** `replace_single_document_efficient` exists and
  is used by the workbook executor and edit apply paths, but
  `store_authoritative_catalog` (full re-encode) is still on the
  `_persist_updated_document` path used by `replace_authoritative_document` /
  `delete_authoritative_document` / the `apply_document_*` methods — so a single
  edit through those still triggers a whole-tenant semantics rewrite.
- **Transactional cascades.** A multi-document workbook migration is **not** a single
  transaction (`replace_single_document_efficient` opens its own connection per
  call). The mitigation is backup → verify → restore-on-failure in
  `execute_migration` (`datum_workbook_apply.py:103`), not real atomicity — noted in
  that module's docstring.

### Absent

- **Sandbox orchestration package.** `sandboxes/system/` and
  `sandboxes/orchestration/` are inert stubs. All sandbox semantics are emergent
  from the document id, `tool_id`, and (on the seed side) the filesystem directory
  walk — there is no first-class sandbox object or lifecycle.
- **Non-SQLite authority backend.** Only a SQLite adapter exists. The port is
  backend-neutral, but a server-DB or embedded-DB adapter for other form factors is
  not yet present.

### Misplaced (forward ref)

- `adapters/sql/datum_semantics.py` is the address/hyphae/MSS engine, but it imports
  **only** `ports/datum_store` + the pure `dumps_json` helper from `._sqlite`
  (verified: no SQL/connection use). It is logically L1 CORE, not an SQL adapter. A
  separate unit relocates it to core — see `60-canonical-datum-and-hyphae-flags.md`
  (forward ref).

## Open questions

1. Should `replace_authoritative_document` / `delete_authoritative_document` /
   the `apply_document_*` methods route through `replace_single_document_efficient`
   so that *every* single-doc edit is O(one doc), retiring the full-catalog rewrite
   from the hot path entirely?
2. Multi-document workbook cascades rely on backup/verify/restore rather than a real
   transaction. For the desktop / local-DB end state, should the executor hold one
   connection across the whole `write_order` so a cascade is atomic?
3. `bootstrap_from_filesystem` is one-way. Is there any supported workflow for
   exporting the canonical DB back to a reviewable JSON tree (e.g. for git-tracked
   fixtures), or is the disk tree permanently a seed-only artifact?
4. Sandbox identity is split across the id `<sandbox>` segment, `tool_id`, and the
   directory name. Should a single source of truth (the `documents.sandbox` column)
   be made authoritative, given the `sandboxes/` packages are inert?
5. The `_GLOBAL_CATALOG_CACHE` is process-global and mtime-keyed. In a desktop
   single-writer process this is fine, but does it need an explicit invalidation
   hook for any out-of-process writer (e.g. a bootstrap script run against a live DB
   while the portal is up)?
