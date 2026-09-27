# MOS Database Schema Addendum

> **Companion contract:** schema only. The runtime-authority rule and
> its enforcement chain live at
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md).

## Purpose

This addendum extends the schema proposed in `mycelial_ontological_schema.md` with
the relational changes required to realize the canonical MOS document naming
taxonomy (see `datum_document_naming_taxonomy.md`). Per the 2026-05-05 user
clarification, *only one* new relational table is introduced (`documents`); SAMRAS,
HOPS, datum-editing, and document-naming concerns are handled by core libraries —
not by additional relational schemas.

## §1 — `documents` (the only new table; replaces / renames `files`)

Primary document entity with enforced canonical naming. The prefix
discriminates between the four datum-document file types — `lv.` sandbox sources,
`stl.` binary payloads, `cptr.` cached sources, and `art.` artifacts (added 2026-08-23;
the taxonomy's `art` row says what one is).

```sql
CREATE TABLE documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       TEXT    NOT NULL,
    document_id     TEXT    NOT NULL UNIQUE,        -- canonical lv./stl./cptr./art. id
    prefix          TEXT    NOT NULL CHECK (prefix IN ('lv','stl','cptr','art')),
    msn_id          TEXT    NOT NULL,
    sandbox         TEXT,                            -- NULL for stl./cptr./art.
    name            TEXT    NOT NULL,
    version_hash    TEXT    NOT NULL,                -- 64-char hex SHA-256 over MSS form
    is_anchor       INTEGER NOT NULL DEFAULT 0 CHECK (is_anchor IN (0, 1)),
    origin          TEXT    NOT NULL DEFAULT 'local' CHECK (origin IN ('local','foreign')),
    legacy_alias    TEXT,                            -- e.g. 'system:anthology' (one-cycle compat)
    created_at      INTEGER NOT NULL                 -- Unix epoch ms
);
CREATE UNIQUE INDEX idx_documents_document_id ON documents (document_id);
CREATE INDEX        idx_documents_tenant_legacy ON documents (tenant_id, legacy_alias);
CREATE UNIQUE INDEX idx_documents_tenant_legacy_unique ON documents (tenant_id, legacy_alias)
    WHERE legacy_alias IS NOT NULL AND legacy_alias != '';
CREATE INDEX        idx_documents_sandbox ON documents (tenant_id, sandbox) WHERE sandbox IS NOT NULL;
```

Naming validation regex (enforced at the SQL adapter boundary by
`micyte/adapters/sql/datum_store.py` via the
`micyte/core/document_naming` library):

```
^lv\.[^.]+\.[^.]+\.[^.]+\.[a-f0-9]{64}$
|
^(stl|cptr|art)\.[^.]+\.[^.]+\.[a-f0-9]{64}$
```

`legacy_alias` is retained for one cycle to keep readers compatible with the legacy
`system:<file>`/`sandbox:<tool>:<filename>.json` identifiers. New writes must
produce a canonical `document_id`.

After authority repair (TASK-MOS-AUTHORITY-SEMANTICS-AND-DEDUPE-2026-05-06), the partial
unique index **`idx_documents_tenant_legacy_unique`** enforces **at most one**
`documents` row per `(tenant_id, legacy_alias)` when `legacy_alias` is non-empty:
duplicate rows drift catalog projection versus row semantics.

`datum_document_semantics` and `datum_row_semantics` **`document_id` foreign keys**
are migrated to canonical `lv.`/`stl.`/`cptr.` ids; legacy identifiers remain readable
via `documents.legacy_alias` and SQL adapter alias-bridges until fixtures fully drop legacy keys.

When the runtime is operating in compatibility mode, the raw source filename may
still be carried alongside the canonical row as secondary metadata. That does not
change authority: sandbox anchors remain first-class `documents` rows with
`is_anchor = 1`, not an out-of-band support-file category.

See `datum_document_naming_taxonomy.md` for the full naming contract.

## §2 — `samras_namespaces` — **withdrawn**

The 2026-05-03 audit proposed a `samras_namespaces` table to track multiple
SAMRAS address spaces per anchor. This is **withdrawn**: SAMRAS is a structural
abstraction over a datum file's row content, not a relational entity. The
authoritative implementation lives in `micyte/core/samras/`
(magnitude decode, ordinal address derivation, structure validity, mutation /
canonical bitstream regeneration). Per-document SAMRAS state, when materialized,
remains as a row inside the document itself (e.g. the `1-1-2` `msn` SAMRAS
abstraction lives in the anthology's datum rows).

## §3 — `precinct_time_windows` — **withdrawn**

The proposed `precinct_time_windows` table is **withdrawn**. Per state-profile
precinct/time-window data lives inline in the relevant `lv.<msn_id>.<sandbox>.<state_profile>`
document, decoded by the core `samras` and `hops` libraries. Tracking is
deferred to `TASK-MOS-RUIGI-SAMRAS-2026-05-03`.

## §4 — `datum_hyphae_chains` — **withdrawn**

The proposed `datum_hyphae_chains` table is **withdrawn**. The chain remains
serialized as JSON in the existing `datum_row_semantics.hyphae_chain_json`
column. Derivation is performed by
`micyte/core/mss/datum_identity.py::derive_hyphae_chain`. Storing the
chain as JSON inside the row keeps a row's hyphae value co-located with its
identity hash and avoids a join-table that has no readers.

## §5 — `document_staging_map` — **withdrawn**

The proposed `document_staging_map` table is **withdrawn**. The migration
script `fnd_app/scripts/migrate_to_canonical_document_ids.py` is idempotent and
records the legacy → canonical mapping directly on the `documents` row via the
`legacy_alias` column. There is no longer a need for a separate staging map.

## Why the Collapse

The clarified data model treats *file category* as the primary discriminator (anchor /
binary payload / cached source / sandbox source) and absorbs every other concern
either:

- into the row itself (`hyphae_chain_json` on `datum_row_semantics`), or
- into a pure-stdlib core library (`micyte/core/samras`, `micyte/core/hops`,
  `micyte/core/mss`, `micyte/core/document_naming`).

This keeps the relational surface narrow (one canonical-name table plus the existing
row-semantics tables) while the algorithmic mass — bullet-proof datum editing,
SAMRAS/HOPS decode, MSS hashing, hyphae chain derivation — lives in clean,
independently-testable Python libraries.

## Relationships to Prior Schema

| Table | Relationship to `mycelial_ontological_schema.md` |
|---|---|
| `documents` | Supersedes `files`. All `file_id` foreign keys in row-semantics tables should follow the cycle to reference `documents.id`. `legacy_alias` retained for one cycle. |

The other prior-schema tables proposed in the 2026-05-03 audit are withdrawn for the
reasons in §2–§5. Follow `datum_document_naming_taxonomy.md` and the core libraries
listed above instead.


## 2026-09-21 — the record is the per-document row (TASK-2026-09-17-001, phase A)

`authoritative_catalog_snapshots` is no longer read for the catalog nor consulted for the
index. Measured on the live store that day: `documents` ⋈ `datum_document_semantics` held
every one of the blob's 116,497 rows (42 documents differing in row order only — the payload
is canonical order), the same `document_metadata` and `source_kind`, the 192 artifacts the
blob never carried, and the 2026-09-10 append to `registrar.address_nodes` whose base id the
blob's 09-18 rewrite no longer held — which `_apply_pending_appends` dropped by rule, so the
two readers disagreed about that document for eleven days.

* `datum_document_provenance` (new) carries what the hashed payload does not: `document_name`,
  `relative_path`, `source_authority`, `warnings`, and the anchor context
  (`anchor_document_name/path/metadata`, `anchor_rows`) the document was written with —
  preserved exactly, never refreshed, because anchor rows feed a document's row hyphae and a
  "current" anchor moves every row's hash (measured). Written by every door through
  `_upsert_documents_index`; healed once from the blob (`json_each`, no Python parse) for a
  store written before the table existed.
* `read_authoritative_datum_documents` assembles from the tables in index order (a re-key
  keeps its row id, so a replaced document keeps its place). `read_document_index` projects
  from the same assembly and is fresh while the tables' newest `updated_at_unix_ms` /
  `created_at` matches its stamp. The blob path survives as `_read_catalog_from_blob`, the
  fallback for a store whose semantics table holds no `lv.` document, and the reference
  `fnd_app/scripts/verify_catalog_parity.py` compares against.
* `store_authoritative_catalog` indexes what it stores. The delta tables
  (`document_creates`, `document_row_appends`) are still written and no longer read.
* Phase B (next): the four blob-writing doors stop writing it. Phase C: the bitstream
  beside the row, once the codec decodes an empty document and the closure carries a foreign
  reference (see the task's report). Phase D: the id flip, the operator's.
