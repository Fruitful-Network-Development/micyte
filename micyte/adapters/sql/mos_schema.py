"""Bounded schema for the MOS (Mycite Object Store) datum-store submodule.

MOS owns exactly these tables — they are the sole authority for canonical datum
documents (see ``docs/contracts/mos_authority_enforcement.md``). They are kept as
one importable constant so the MOS store can, in future, be pointed at its own
physical database file without disturbing the co-resident *non-MOS* ports
(``audit_log``, ``portal_authority``, ``directive_context``) that today share the
authority SQLite file for operational convenience.

``_sqlite.py`` composes this fragment with the non-MOS fragments into the full
``SCHEMA_SQL`` that ``connect_sqlite`` materializes; because every statement is
``CREATE ... IF NOT EXISTS``, composing is idempotent and requires no migration.
Splitting the string does not move any data — it only draws the module boundary
in code so the MOS submodule declares its own storage shape.
"""

from __future__ import annotations

# Ordering note: ``datum_document_semantics`` is declared before
# ``datum_row_semantics`` because the latter carries a FOREIGN KEY into it.
MOS_SCHEMA_SQL = """
-- THE ROLLBACK COPY, not the store (TASK-2026-09-17-001, 2026-09-21/22). Until
-- 2026-09-21 this blob — the whole tenant catalog as one JSON, 137 MB live — was
-- what every catalog read parsed and what every document write REWROTE. Since
-- phase A the catalog is assembled from the per-document tables and since phase B
-- nothing writes here: the row keeps its last snapshot (2026-09-18 live) so the
-- previous build's reader would find exactly what it left. Read only when the
-- tables hold nothing for the tenant (a store written by an older build).
CREATE TABLE IF NOT EXISTS authoritative_catalog_snapshots (
    tenant_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);

-- The metadata projection of the catalog, carrying every document MINUS its
-- rows. It exists because the catalog is 137 MB of JSON for one tenant while the
-- questions the portal shell asks of it — how many documents, what are they
-- called, which sandbox, what version — are answered by ~200 KB. Parsing the blob
-- to list documents cost 460 MB and 5.3 s per shell render (see
-- plans/TASK-2026-08-13-001-catalog-payload-debt.plan.md).
--
-- It is a SEPARATE TABLE rather than a column so the schema stays composable
-- `CREATE ... IF NOT EXISTS` with no migration step. Since 2026-09-22 it is
-- projected from the TABLES and stamped with their version (`updated_at_unix_ms`
-- = the newest write; the envelope carries the whole version, counts included,
-- because a delete moves no clock); every door edits its own entry in its own
-- transaction, and a reader that finds the stamp stale rebuilds it once.
CREATE TABLE IF NOT EXISTS authoritative_catalog_index (
    tenant_id TEXT PRIMARY KEY,
    index_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);

-- The catalog's OWN facts — the import's `source_files` and `readiness_status`,
-- which the blob carried at its top level. Since 2026-09-22 the bulk import writes
-- no blob, so it records them here; the reader takes this row first and the blob's
-- top level for a store written before it.
CREATE TABLE IF NOT EXISTS authoritative_catalog_facts (
    tenant_id TEXT PRIMARY KEY,
    source_files_json TEXT NOT NULL,
    readiness_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);

-- A document's IDENTITY facts the hashed payload does not carry and the `documents`
-- index cannot hold for every id: `canonical_name`, `tool_id`, `is_anchor`. For an
-- `lv.` id the index row and the id itself say the same; for a LEGACY id (a store
-- opened with `allow_legacy_writes`) this row is the only place they live, and until
-- 2026-09-22 the blob carried them. Written beside the provenance row, in the same
-- transaction, by the one writer of both.
CREATE TABLE IF NOT EXISTS datum_document_identity (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    is_anchor INTEGER NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE TABLE IF NOT EXISTS system_workbench_snapshots (
    tenant_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS publication_summary_snapshots (
    tenant_id TEXT NOT NULL,
    tenant_domain TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, tenant_domain)
);

CREATE TABLE IF NOT EXISTS datum_document_semantics (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    policy TEXT NOT NULL,
    version_hash TEXT NOT NULL,
    canonical_payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

-- The binary MSS identity, DUAL-WRITTEN beside the JSON stand-in from 2026-09-17
-- (TASK-2026-09-16-002 P1, operator decision D2: dual-write now, no re-key). `mss_hash`
-- is `mos.mss_binary_v3` over the document's reindexed downward closure resolved from
-- its OWN rows and anchor rows; `dropped_json` counts the references that closure could
-- not resolve (dangling / upward / malformed) — 0/0/0 is a lossless encoding, and the
-- id flip to this hash (TASK-2026-09-17-001) waits until the corpus reads 0/0/0.
-- `policy` is 'deferred' for a document over the full-semantics cap, whose closure is
-- not computed on the write path for the same reason its hyphae are not.
CREATE TABLE IF NOT EXISTS datum_document_binary (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    policy TEXT NOT NULL,
    mss_hash TEXT NOT NULL,
    datums INTEGER NOT NULL,
    dropped_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

-- The document's rows as ONE MSS bitstream (TASK-2026-09-17-001 phase C, 2026-09-23):
-- `mos.mss_binary_v4`, the transport grammar of `micyte/core/mss/transport.py`, packed
-- big-endian behind a 1-bit sentinel (`bit_count` is the unpacked length). Written by
-- every door beside the semantics row; decodes to rows identical to the payload's
-- (rehearsed over the whole corpus: 1,356 of 1,356). A reader takes it only behind
-- MOS_READ_FROM_BITSTREAM; the payload stays the store of record until phase D. Three
-- facts besides a stream: a document over the full-semantics cap carries policy
-- `deferred`; one the transport REFUSES (two rows at one address — I1, which the write
-- door does not yet enforce) carries `refused` with the sentence in `note`; a document
-- with no row was written before this table existed.
CREATE TABLE IF NOT EXISTS datum_document_bitstream (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    policy TEXT NOT NULL,
    mss_hash TEXT NOT NULL,
    bit_count INTEGER NOT NULL,
    bitstream BLOB NOT NULL,
    datums INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

-- The part of a document the hashed payload does not carry (2026-09-21, TASK-2026-09-17-001
-- phase A): how it was named and filed when it was written, and the ANCHOR CONTEXT it was
-- given — the sandbox anchor's rows as they were at that moment. Kept per document so the
-- catalog can be assembled from the tables alone, byte-for-byte what the blob served: anchor
-- rows feed a document's row hyphae (measured: attaching a current anchor to a document that
-- had none moves every row's hyphae and semantic hash), so they are preserved exactly, never
-- refreshed. Written by every door beside the `documents` row; healed from the blob once for
-- a store written before this table existed.
CREATE TABLE IF NOT EXISTS datum_document_provenance (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    anchor_document_name TEXT NOT NULL,
    anchor_document_path TEXT NOT NULL,
    anchor_document_metadata_json TEXT NOT NULL,
    anchor_rows_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       TEXT    NOT NULL,
    document_id     TEXT    NOT NULL UNIQUE,
    -- `art` joined 2026-08-23 for the artifact datum type (plan P5). The CHECK is why
    -- adding a prefix to ALLOWED_PREFIXES is not enough on its own: the database refuses
    -- the row with `IntegrityError: CHECK constraint failed`, and SQLite cannot ALTER a
    -- CHECK, so an EXISTING store needs the table rebuilt —
    -- `fnd_app/scripts/migrate_documents_prefix_check.py`.
    prefix          TEXT    NOT NULL CHECK (prefix IN ('lv','stl','cptr','art')),
    msn_id          TEXT    NOT NULL,
    sandbox         TEXT,
    name            TEXT    NOT NULL,
    version_hash    TEXT    NOT NULL,
    is_anchor       INTEGER NOT NULL DEFAULT 0,
    origin          TEXT    NOT NULL DEFAULT 'local' CHECK (origin IN ('local','foreign')),
    created_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_prefix_sandbox
ON documents (tenant_id, prefix, sandbox);
CREATE INDEX IF NOT EXISTS documents_created_idx
ON documents(tenant_id, created_at);

-- The index's freshness key is the newest write the tables hold (2026-09-21); MAX over an
-- unindexed column scans the whole 187 MB table — measured at ~10 s on a cold disk, paid
-- on every catalog-cache miss. Indexed, it is a lookup.
CREATE INDEX IF NOT EXISTS datum_document_semantics_updated_idx
ON datum_document_semantics(tenant_id, updated_at_unix_ms);
CREATE TABLE IF NOT EXISTS datum_row_semantics (
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    datum_address TEXT NOT NULL,
    policy TEXT NOT NULL,
    semantic_hash TEXT NOT NULL,
    hyphae_hash TEXT NOT NULL,
    hyphae_chain_json TEXT NOT NULL,
    local_references_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id, datum_address),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES datum_document_semantics(tenant_id, document_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS datum_row_semantics_document_idx
ON datum_row_semantics(tenant_id, document_id);

-- Rows appended to a document SINCE the catalog snapshot was taken.
--
-- The catalog is one 138 MB JSON blob holding all 549 documents, and the cost of a
-- document write is the blob, not the document. Measured on a VACUUM INTO copy:
--
--     catalog READ alone .......................  479 MB
--     write to a TWO-ROW document ..............  776 MB
--     write to `address_nodes` (41,999 rows) ...  890 MB
--     the blob rewritten with no JSON parsing ..  421 MB
--     semantics + row semantics only ...........  164 MB
--
-- against `MemoryHigh=900M` on a service that boots at ~800 MB. So an append that
-- rewrites the blob cannot run in the portal at ANY document size, and the 421 MB floor
-- says no cleverer patch of the blob helps either.
--
-- This table is the write-ahead: an append writes the semantics tables and records its
-- delta here, and `read_authoritative_datum_documents` applies the deltas on the way out.
-- The catalog stays a SNAPSHOT and this is what has happened since — which is a stated
-- relationship, not the silent disagreement that put the catalog at 531 and the index at
-- 510 on 2026-08-06. `store_authoritative_catalog` writes a fresh snapshot and clears it.
--
-- Keyed on `base_document_id` — the id the SNAPSHOT holds — so a second append to the
-- same document extends one row rather than starting a chain the reader would have to
-- walk. `document_id` is where the document is now.
CREATE TABLE IF NOT EXISTS document_row_appends (
    tenant_id           TEXT    NOT NULL,
    base_document_id    TEXT    NOT NULL,
    document_id         TEXT    NOT NULL,
    rows_json           TEXT    NOT NULL,
    appended_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, base_document_id)
);

CREATE INDEX IF NOT EXISTS document_row_appends_head_idx
ON document_row_appends(tenant_id, document_id);

-- Documents created SINCE the catalog snapshot was taken.
--
-- The sibling of `document_row_appends`, and needed for the same reason: creating a
-- document through `replace_single_document_efficient` costs ~776 MB whatever its size,
-- because the cost is the 138 MB blob. Onboarding a new instance creates four documents,
-- so on the old path standing up one handyman business was ~3 GB of transient allocation.
--
-- A row here means "this document is not in the snapshot; assemble it from its semantics
-- on the way out". That read is per-document and a new document is small, so the
-- reconciliation is cheap in exactly the case it applies to.
--
-- An APPEND to a pending create updates this row's `document_id` rather than writing an
-- append delta: the reader assembles the whole document from its semantics either way, and
-- two records describing one document is a second thing to keep in step.
CREATE TABLE IF NOT EXISTS document_creates (
    tenant_id          TEXT    NOT NULL,
    document_id        TEXT    NOT NULL,
    created_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);
"""
