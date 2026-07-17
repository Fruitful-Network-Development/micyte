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
CREATE TABLE IF NOT EXISTS authoritative_catalog_snapshots (
    tenant_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
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

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       TEXT    NOT NULL,
    document_id     TEXT    NOT NULL UNIQUE,
    prefix          TEXT    NOT NULL CHECK (prefix IN ('lv','stl','cptr')),
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
"""
