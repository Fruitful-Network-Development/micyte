from __future__ import annotations

import dataclasses
import logging
import os
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from micyte.adapters.filesystem_datum import FilesystemSystemDatumStoreAdapter
from micyte.adapters.sql._sqlite import dumps_json, loads_json, open_sqlite
from micyte.core.datum_semantics import (
    build_document_semantics,
)
from micyte.core.datum_semantics import (
    preview_document_delete as preview_document_delete_mutation,
)
from micyte.core.datum_semantics import (
    preview_document_insert as preview_document_insert_mutation,
)
from micyte.core.datum_semantics import (
    preview_document_move as preview_document_move_mutation,
)
from micyte.core.datum_semantics.engine import (
    MSS_VERSION_HASH_POLICY,
    build_document_version_identity,
)
from micyte.core.document_naming import (
    derive_canonical_id_from_legacy,
    is_canonical_document_id,
    parse_canonical_document_id,
)
from micyte.core.mss.document_adapter import binary_identity
from micyte.core.mss.document_codec import MssFormatError
from micyte.core.mss.invariants import (
    InvariantRefused,
    Refusal,
    check_new_rows,
    check_replaced_rows,
    check_rows,
)
from micyte.core.mss.transport import (
    MSS_TRANSPORT_POLICY,
    canonical_json,
    decode_rows,
    encode_rows,
    pack_bits,
    rows_of,
    unpack_bits,
)
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentCatalogResult,
    AuthoritativeDatumDocumentIndexResult,
    AuthoritativeDatumDocumentMutationPort,
    AuthoritativeDatumDocumentRequest,
    AuthoritativeDatumDocumentRow,
    AuthoritativeDatumDocumentSummary,
    PublicationProfileBasicsWritePort,
    PublicationProfileBasicsWriteRequest,
    PublicationProfileBasicsWriteResult,
    PublicationTenantSummaryPort,
    PublicationTenantSummaryRequest,
    PublicationTenantSummaryResult,
    SystemDatumResourceRow,
    SystemDatumStorePort,
    SystemDatumStoreRequest,
    SystemDatumWorkbenchResult,
)


class NonCatalogPrefixError(ValueError):
    """Raised when a write attempts to put a non-``lv.`` document in the CATALOG.

    The catalog snapshot is one row per tenant holding every document as JSON — 138 MB on
    the live store, ~290 MiB parsed — and it is read WHOLE on every authoritative read. So
    what may enter it is a memory decision, not a naming one.

    ``lv.`` is a live document in a sandbox. ``stl.`` is a compiled binary payload and
    ``cptr.`` is a cache; neither carries a sandbox segment, neither has a production
    reader that goes through the catalog, and the live store has never held one — 749 of
    749 documents are ``lv.``. Nothing was keeping them out, though: measured 2026-08-23, a
    ``stl.`` document handed to ``store_authoritative_catalog`` was persisted and read
    straight back.

    That mattered before anyone noticed because of what comes next. The ``artifact`` datum
    type (plan P5) puts a 956-file, 127 MB pool into datum documents, and gamma coding
    roughly doubles a payload on the way in — so an artifact prefix that entered the
    catalog would take every authoritative read from 138 MB to something near 390 MB. The
    portal has already been OOM-killed by this exact blob once.

    The one path that could produce a non-``lv.`` id in production is
    ``derive_canonical_id_from_legacy``: ``payload:<name>.bin`` becomes ``stl.`` and
    ``cache:<name>.json`` becomes ``cptr.``, and ``_canonicalize_catalog_document_ids``
    would then hand the result here. It cannot fire against live data — the
    ``documents.legacy_alias`` column is GONE, so the legacy index it read no longer
    exists, and CI additionally gates on there being no on-disk datum documents. And if it
    ever did fire, refusing is the right answer: ``payload:`` is a binary payload, which is
    precisely what must not be in the catalog.

    REFUSED rather than skipped, deliberately. A filter that silently dropped these would
    lose a caller's document and report success, and "never exclude silently" is the rule
    the egress sweep and the port register already keep. A caller that means to store a
    binary payload needs a path that is not the catalog; this says so at the moment of the
    write instead of at the moment somebody looks for it.
    """


def _refuse_non_catalog_prefixes(documents: Any) -> None:
    """The catalog carries `lv.` and nothing else — see :class:`NonCatalogPrefixError`.

    Called from every door that ADDS whole documents to the catalog's tables — the bulk
    import and `replace_documents_efficient` (the single replace delegates); the create
    door takes canonical ids only. Until 2026-09-22 these were the four writers of the
    catalog blob. Guarding only `store_authoritative_catalog` — which is what the first
    version of this did — proves the rule on one path and leaves the rest open, which is
    worse than not guarding it: a test would report the property as held. The reader
    applies the same rule as a prefix filter (`_assemble_catalog`).

    Checked after canonicality so a malformed id is reported as malformed rather than as a
    prefix it does not really have.
    """
    foreign = sorted({
        doc_id.split(".", 1)[0]
        for doc_id in (_as_text(getattr(d, "document_id", "")) for d in (documents or ()))
        if doc_id and is_canonical_document_id(doc_id) and not doc_id.startswith("lv.")
    })
    if foreign:
        raise NonCatalogPrefixError(
            "The catalog snapshot carries `lv.` documents only; refusing "
            + ", ".join(f"`{prefix}.`" for prefix in foreign)
            + ". It is read whole on every authoritative read, so a binary payload here is "
            "paid for by every reader. Store it outside the catalog."
        )


class NonCanonicalDocumentIdError(ValueError):
    """Raised when a write attempts to persist a non-canonical document id.

    Phase E3: new writes must produce canonical ``lv./stl./cptr.`` ids; legacy
    ``system:`` / ``sandbox:`` ids are still accepted on reads via the
    ``documents.legacy_alias`` index for one cycle.
    """


class UnknownPriorDocumentIdError(ValueError):
    """Raised when a replace names a prior document id the catalog does not hold.

    A caller that passes a prior id is asserting "this document exists and I am superseding
    it". Falling back to an APPEND when the assertion is false is the worst available answer:
    the catalog ends up holding both the stale document and its replacement under the same
    name, and the mint reports success. Every caller computes its prior ids from a catalog
    read, so an id that misses means the read is stale — the write must not proceed on it.

    ``None`` still means "append", which is a different and explicit statement.
    """


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


# Why the write paths below no longer switch the journal mode.
#
# Each of them used to read the current journal mode, set ``PRAGMA journal_mode
# = MEMORY`` for the duration of the transaction, and restore it in a finally.
# Two things were wrong with that, and they are the same thing seen from two
# sides:
#
# 1. journal_mode is a property of the DATABASE, not of the connection. SQLite
#    cannot leave WAL while any other connection has the file open, so the
#    pragma raises ``database is locked`` — and it sat OUTSIDE the ``try``, with
#    its result discarded, so the failure surfaced as an exception from a line
#    that looked like a hint. One portal page being rendered was enough. That
#    never showed while a human was the only writer; a background writer makes
#    concurrent access the ordinary case.
# 2. When it DID take effect it removed the file's crash protection: the
#    rollback journal for a multi-hundred-MB transaction lived in RAM, so an OOM
#    kill mid-transaction left nothing on disk to roll back and the database
#    file malformed. ``replace_documents_efficient``'s own docstring records
#    that happening.
#
# WAL is both faster than a rollback journal for these writes and the mode that
# lets readers proceed during them, so there is nothing left to trade away.
# ``temp_store = MEMORY`` is genuinely per-connection and stays. Lock waiting is
# handled once, for every connection, by ``busy_timeout`` in _sqlite.py.


def _normalize_version_hash_token(value: object) -> str:
    token = _as_text(value).lower()
    if token.startswith("sha256:"):
        token = token.split(":", 1)[1]
    return token


def _sql_norm_version_hash(column: str) -> str:
    """SQLite expression lowering version_hash tokens like ``sha256:<hex>`` for joins."""

    col = column.strip()
    return (
        f"CASE WHEN substr(lower(trim({col})), 1, 7) = 'sha256:' "
        f"THEN substr(lower(trim({col})), 8) ELSE lower(trim({col})) END"
    )


def _workbench_from_payload(payload: dict[str, object]) -> SystemDatumWorkbenchResult:
    rows = payload.get("rows") or ()
    warnings = payload.get("warnings") or ()
    return SystemDatumWorkbenchResult(
        tenant_id=payload.get("tenant_id"),
        rows=tuple(
            row if isinstance(row, SystemDatumResourceRow) else SystemDatumResourceRow.from_dict(row)
            for row in rows
        ),
        source_files=payload.get("source_files") or {},
        materialization_status=payload.get("materialization_status") or {},
        warnings=tuple(str(item) for item in warnings),
    )


# Phase 14c: module-level catalog cache shared across SqliteSystemDatumStoreAdapter
# instances. The MOS extension adapters (PayPal, Newsletter, Email) each
# instantiate a fresh adapter per request → per-instance cache (still present
# below) couldn't help cross-extension. With the production authority DB at
# 244 MB and the ext_paypal `_find_doc` doing a full catalog scan to find one
# canonical_name, parallelized rendering still serialized on this load. The
# module-level cache lets 4 extensions share one fetch per (db_path, tenant_id)
# until the file's mtime changes; any write through `_invalidate_catalog`
# clears both layers.
_GLOBAL_CATALOG_CACHE: dict[tuple[str, str], tuple[int, Any]] = {}

# An entry is a whole catalog: the live store's single tenant carries 138 MB of JSON,
# which is ~290 MiB of objects once parsed. So the bound has to be small, and the cache
# has to have one at all — it had none, and the key is a *path*, which means any process
# that opens more than one authority store grew by a catalog per store and never gave
# one back. That is invisible in production (one store, one tenant, one entry) and fatal
# in a test process, which mints a temp store per test and deletes it in teardown: every
# test left a permanent entry under a key that could never be hit again.
#
# Two, not "a comfortable few": production only ever needs ONE (one store, one tenant),
# and the only legitimate reason a second appears is a test class that holds a shared
# read-only copy while one test works on its own — which is exactly two. A miss costs a
# re-read of the catalog, never a wrong answer, so the bound is cheap to be wrong about
# in the tight direction and expensive to be wrong about in the loose one.
_GLOBAL_CATALOG_CACHE_MAX = 2


def _remember_catalog(key: tuple[str, str], db_mtime: int, result: Any) -> None:
    """Cache `result` under `key`, evicting what can no longer be useful.

    Two rules, in order:

    1. **A key whose db file is gone is dead.** The key *is* the resolved path, so once
       that path stops existing nothing can ever produce this key again — the entry is
       pure retention. This is the rule that fits the key, and it is the one that
       matters: it evicts exactly the entries a test run creates and never fires
       against a live store.
    2. **A cap underneath it**, for a process that legitimately holds several stores
       that all still exist. Oldest insertion goes first.

    Both are memory rules only. Nothing here changes which catalog a caller gets: the
    mtime check at the read site is still what decides whether a cached entry is valid.
    """
    for dead in [k for k in _GLOBAL_CATALOG_CACHE if not Path(k[0]).exists()]:
        _GLOBAL_CATALOG_CACHE.pop(dead, None)
    _GLOBAL_CATALOG_CACHE[key] = (db_mtime, result)
    while len(_GLOBAL_CATALOG_CACHE) > _GLOBAL_CATALOG_CACHE_MAX:
        oldest = next(iter(_GLOBAL_CATALOG_CACHE))
        if oldest == key:  # never evict what we were just asked to remember
            break
        _GLOBAL_CATALOG_CACHE.pop(oldest, None)


_log = logging.getLogger("micyte.adapters.sql.datum_store")

#: The rows-free projection of the catalog, cached under the same (path, tenant)
#: key and the same mtime rule as `_GLOBAL_CATALOG_CACHE`. An entry here is ~200 KB
#: rather than ~290 MiB, so the bound is about hygiene, not headroom — but it is the
#: same bound for the same reason: the key is a PATH, and a process that opens many
#: stores would otherwise retain one projection per store forever.
#: Bump when the projection's SHAPE or the rules that fill it change. It is the
#: half of the freshness check that `updated_at_unix_ms` cannot express: the data
#: is unchanged but the code that reads it is not the code that wrote it.
# v2 added `archetype` (2026-08-16, the Compendium gallery): a persisted v1
# projection rebuilds on first read — the self-heal the format field exists for.
# v3 (2026-09-21): built from the TABLES. A persisted v2 projection was built from the blob
# and can carry what the blob carried — the pre-append id of a document the tables have
# since moved on from — so it is rebuilt once on first read, whatever its stamp says.
_CATALOG_INDEX_FORMAT = "mos.catalog_index.v4"
# Shape-matching a document costs one fold per row. The rebuild already parsed
# every row, so matching is nearly free — except for the address-space giants
# (the live `address_nodes` carries ~100k rows), which get the browsable-tree
# treatment elsewhere and never needed a per-document icon. Over the budget the
# entry keeps its declared metadata archetype or "".
_INDEX_ARCHETYPE_ROW_BUDGET = 4000

_GLOBAL_INDEX_CACHE: dict[tuple[str, str], tuple[int, Any]] = {}
_GLOBAL_INDEX_CACHE_MAX = 2


def _remember_index(key: tuple[str, str], db_mtime: int, result: Any) -> None:
    """`_remember_catalog`'s rules, for the index projection."""
    for dead in [k for k in _GLOBAL_INDEX_CACHE if not Path(k[0]).exists()]:
        _GLOBAL_INDEX_CACHE.pop(dead, None)
    _GLOBAL_INDEX_CACHE[key] = (db_mtime, result)
    while len(_GLOBAL_INDEX_CACHE) > _GLOBAL_INDEX_CACHE_MAX:
        oldest = next(iter(_GLOBAL_INDEX_CACHE))
        if oldest == key:
            break
        _GLOBAL_INDEX_CACHE.pop(oldest, None)


#: ONE sandbox's documents, under (path, tenant, sandbox, msn, budget) and the same mtime
#: rule as the catalog. The whole-catalog read was remembered per store version and the
#: one-sandbox door was not, so when the request-path readers moved from the one to the
#: other (2026-09-25) every one of them paid its read per call — the live `registrar`
#: (566 documents, 49,099 rows, 48 MB of payload) is ~2 s each time — where the catalog
#: had cost 4 s once. An entry is bounded by its sandbox, and every entry together by
#: the catalog they are a partition of; a process that opens many stores is the cap's
#: business, and a dead path's the first rule's.
_GLOBAL_SANDBOX_CACHE: dict[tuple[str, str, str, str, int], tuple[int, tuple[Any, ...]]] = {}
_GLOBAL_SANDBOX_CACHE_MAX = 32


def _remember_sandbox(
    key: tuple[str, str, str, str, int], db_mtime: int, result: tuple[Any, ...]
) -> None:
    """`_remember_catalog`'s rules, for one sandbox's documents."""
    for dead in [k for k in _GLOBAL_SANDBOX_CACHE if not Path(k[0]).exists()]:
        _GLOBAL_SANDBOX_CACHE.pop(dead, None)
    _GLOBAL_SANDBOX_CACHE[key] = (db_mtime, result)
    while len(_GLOBAL_SANDBOX_CACHE) > _GLOBAL_SANDBOX_CACHE_MAX:
        oldest = next(iter(_GLOBAL_SANDBOX_CACHE))
        if oldest == key:
            break
        _GLOBAL_SANDBOX_CACHE.pop(oldest, None)


def _forget_sandboxes(db_path: str, tenant_id: str) -> None:
    """Every remembered sandbox of one store's tenant — a write's business, since the file's
    mtime is blind to a commit that only reached the WAL."""
    for key in [k for k in _GLOBAL_SANDBOX_CACHE if k[0] == db_path and k[1] == tenant_id]:
        _GLOBAL_SANDBOX_CACHE.pop(key, None)



#: Below this many rows, an append just recomputes the whole document's semantics. The
#: incremental path costs two ``_semantic_context`` builds to check its own precondition,
#: which is more than the full computation is worth on a small document — and the simplest
#: correct thing should be what runs unless size says otherwise. Measured: the full
#: computation is 17.6 s at 41,999 rows and milliseconds at 66.
_FULL_SEMANTICS_ROWS = 5_000


class IdentityPolicyMismatch(ValueError):
    """A write keyed under a policy the store's documents are not keyed under."""


def _tenant_identity_policy(connection: Any, tenant_id: str) -> str | None:
    """The policy the tenant's `lv.` documents are keyed under, or ``None`` for none yet."""
    row = connection.execute(
        "SELECT policy FROM datum_document_semantics WHERE tenant_id = ? AND document_id LIKE 'lv.%' LIMIT 1",
        (tenant_id,),
    ).fetchone()
    return _as_text(row["policy"]) if row is not None else None


def _refuse_identity_policy_mismatch(connection: Any, *, tenant_id: str, policy: str) -> None:
    """A store keyed under one identity policy takes no write keyed under another
    (2026-09-25, the flip): with the token set for a v1 store, or unset for a v4 store,
    the write is refused with the sentence — never mis-keyed into a mixed store."""
    held = _tenant_identity_policy(connection, tenant_id)
    if held and policy and held != policy:
        raise IdentityPolicyMismatch(
            f"the store's documents are keyed under {held} and this write is keyed under {policy}; "
            f"set MOS_CANONICAL_HASH=mss_binary_v4 for a mos.mss_binary_v4 store, unset it for a "
            f"mos.mss_sha256_v1 store")


def _reidentified(document_id: str, version_hash: str) -> str:
    """The same canonical id carrying a new version hash.

    Content decides identity here, so an append re-keys the document. Rebuilt by
    replacing the last segment rather than by reassembling from parts: the parts are
    already in the id, and a reassembly is a second place for the naming rule to live.
    """
    head, _, _ = _as_text(document_id).rpartition(".")
    token = _as_text(version_hash)
    return f"{head}.{token.removeprefix('sha256:')}" if head else document_id


def _document_semantics_for(
    document: AuthoritativeDatumDocument, context: dict[str, Any], addresses: Sequence[str]
) -> dict[str, Any]:
    """:func:`build_document_semantics`, restricted to ``addresses``.

    The per-row loop is what makes the full build 17.6 s on 41,999 rows; the shared
    context is 1.76 s of it. Restricting the loop is safe only while the context is
    unchanged, which :meth:`append_document_rows` checks rather than assumes.
    """
    from micyte.core.datum_semantics import engine

    return engine.build_document_semantics_subset(document, context, addresses)


def _canonical_key(document_id: str) -> tuple[str, str, str] | None:
    """``(msn, sandbox, name)`` for a canonical id, ``None`` for a legacy one."""
    try:
        parsed = parse_canonical_document_id(document_id)
    except Exception:
        return None
    return (_as_text(parsed.msn_id), _as_text(parsed.sandbox), _as_text(parsed.name))


def _apply_pending_appends(connection: Any, tenant_id: str, payload: dict[str, Any]) -> int:
    """Fold ``document_row_appends`` into a catalog payload on the way out.

    The catalog blob is a SNAPSHOT and this is what has happened since. Applying the delta
    here — in the one function every one of the 94 catalog readers goes through — is what
    lets :meth:`append_document_rows` skip the blob without any of them seeing a stale
    document. The alternative, marking the catalog stale, would have made 94 call sites
    each responsible for noticing.

    Cost is O(appended rows), not O(document): the delta carries the rows themselves, so a
    document with 41,999 rows and one append costs one list append and one re-key. Reading
    the document back from its semantics payload instead would cost 203 MB, which is the
    whole thing this avoids.

    A delta whose base is not in the payload is DROPPED rather than guessed at. That
    happens when a full snapshot was written without clearing the table, and applying it
    to whatever else is there would corrupt a document to avoid admitting a gap.
    """
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        return 0
    pending = connection.execute(
        "SELECT base_document_id, document_id, rows_json FROM document_row_appends "
        "WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchall()
    if not pending:
        return 0
    by_id = {
        _as_text(entry.get("document_id")): entry
        for entry in documents
        if isinstance(entry, dict)
    }
    applied = 0
    for record in pending:
        entry = by_id.get(_as_text(record["base_document_id"]))
        if entry is None:
            continue
        rows = entry.get("rows")
        if not isinstance(rows, list):
            continue
        rows.extend(loads_json(record["rows_json"]))
        entry["document_id"] = _as_text(record["document_id"])
        applied += 1
    return applied


def _record_row_append(
    connection: Any, *, tenant_id: str, prior_document_id: str, document_id: str,
    rows: Sequence[AuthoritativeDatumDocumentRow], now: int,
) -> None:
    """Record the delta the catalog snapshot does not yet carry.

    Keyed on the id the SNAPSHOT holds, so a second append to the same document EXTENDS
    one row instead of starting a chain the reader would have to walk — a chain is a
    second traversal order to get wrong, and the reader already has one job.
    """
    # A document the snapshot has never seen is described by ONE record, not two. The
    # reader assembles a pending create from its semantics in full, so an append to it
    # only has to move the id forward.
    pending_create = connection.execute(
        "SELECT 1 FROM document_creates WHERE tenant_id = ? AND document_id = ?",
        (tenant_id, prior_document_id),
    ).fetchone()
    if pending_create is not None:
        connection.execute(
            "UPDATE document_creates SET document_id = ?, created_at_unix_ms = ? "
            "WHERE tenant_id = ? AND document_id = ?",
            (document_id, now, tenant_id, prior_document_id),
        )
        return

    payload = [{"datum_address": row.datum_address, "raw": row.raw} for row in rows]
    existing = connection.execute(
        "SELECT base_document_id, rows_json FROM document_row_appends "
        "WHERE tenant_id = ? AND document_id = ?",
        (tenant_id, prior_document_id),
    ).fetchone()
    if existing is not None:
        merged = loads_json(existing["rows_json"]) + payload
        connection.execute(
            "UPDATE document_row_appends SET document_id = ?, rows_json = ?, "
            "appended_at_unix_ms = ? WHERE tenant_id = ? AND base_document_id = ?",
            (document_id, dumps_json(merged), now, tenant_id, existing["base_document_id"]),
        )
        return
    connection.execute(
        """
        INSERT INTO document_row_appends (
            tenant_id, base_document_id, document_id, rows_json, appended_at_unix_ms
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, base_document_id) DO UPDATE SET
            document_id = excluded.document_id,
            rows_json = excluded.rows_json,
            appended_at_unix_ms = excluded.appended_at_unix_ms
        """,
        (tenant_id, prior_document_id, document_id, dumps_json(payload), now),
    )


def _chain_first(first: Any, cursor: Any) -> Iterator[Any]:
    yield first
    yield from cursor


def _record_provenance(
    connection: Any, *, tenant_id: str, document: AuthoritativeDatumDocument,
    prior_document_id: str = "", now: int = 0,
) -> None:
    """The part of ``document`` the hashed payload does not carry, beside its index row.

    Naming (``document_name``, ``relative_path``, ``source_authority``, ``warnings``) and the
    ANCHOR CONTEXT the document was written with. Preserved exactly: anchor rows feed a
    document's row hyphae, so a "refreshed" anchor would move every row's hash on the next
    write (measured 2026-09-21). A re-key deletes the prior id's row.
    """
    new_id = _as_text(document.document_id)
    if not new_id:
        return
    for stale in {_as_text(prior_document_id), new_id}:
        if stale:
            for table in ("datum_document_provenance", "datum_document_identity"):
                connection.execute(
                    f"DELETE FROM {table} WHERE tenant_id=? AND document_id=?",
                    (tenant_id, stale))
    connection.execute(
        "INSERT INTO datum_document_identity (tenant_id, document_id, canonical_name, tool_id, "
        "is_anchor, updated_at_unix_ms) VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, new_id, _as_text(document.canonical_name), _as_text(document.tool_id),
         1 if document.is_anchor else 0, int(now)),
    )
    connection.execute(
        """
        INSERT INTO datum_document_provenance (
            tenant_id, document_id, document_name, relative_path, source_authority, warnings_json,
            anchor_document_name, anchor_document_path, anchor_document_metadata_json,
            anchor_rows_json, updated_at_unix_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id, new_id, _as_text(document.document_name), _as_text(document.relative_path),
            _as_text(document.source_authority) or "authoritative",
            dumps_json(list(document.warnings)),
            _as_text(document.anchor_document_name), _as_text(document.anchor_document_path),
            dumps_json(document.anchor_document_metadata or {}),
            dumps_json([row.to_dict() if hasattr(row, "to_dict") else row for row in document.anchor_rows]),
            int(now),
        ),
    )


def _read_provenance(connection: Any, tenant_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT p.document_id, p.document_name, p.relative_path, p.source_authority, "
        "p.warnings_json, p.anchor_document_name, p.anchor_document_path, "
        "p.anchor_document_metadata_json, p.anchor_rows_json, "
        "i.canonical_name, i.tool_id, i.is_anchor "
        "FROM datum_document_provenance AS p "
        "LEFT JOIN datum_document_identity AS i "
        "ON i.tenant_id = p.tenant_id AND i.document_id = p.document_id "
        "WHERE p.tenant_id = ?",
        (tenant_id,),
    ):
        try:
            out[_as_text(row["document_id"])] = {
                # None when the identity row is absent (a store healed before 2026-09-22):
                # the reader then derives what an `lv.` id says about itself.
                "canonical_name": (None if row["canonical_name"] is None
                                   else _as_text(row["canonical_name"])),
                "tool_id": None if row["tool_id"] is None else _as_text(row["tool_id"]),
                "is_anchor": None if row["is_anchor"] is None else bool(row["is_anchor"]),
                "document_name": _as_text(row["document_name"]),
                "relative_path": _as_text(row["relative_path"]),
                "source_authority": _as_text(row["source_authority"]) or "authoritative",
                "warnings": tuple(loads_json(row["warnings_json"]) or ()),
                "anchor_document_name": _as_text(row["anchor_document_name"]),
                "anchor_document_path": _as_text(row["anchor_document_path"]),
                "anchor_document_metadata": loads_json(row["anchor_document_metadata_json"]) or {},
                "anchor_rows": tuple(loads_json(row["anchor_rows_json"]) or ()),
            }
        except Exception:  # one unreadable row must not blank the catalog's provenance
            continue
    return out


def _heal_provenance_from_blob(connection: Any, tenant_id: str, now: int) -> int:
    """Fill ``datum_document_provenance`` from the catalog blob, ONCE, for a store written
    before the table existed. SQLite's ``json_each`` walks the blob in C — no Python parse
    of 138 MB. Returns the rows written; 0 when there is no blob. Persisting from a read
    is the store's established self-heal (the index does the same)."""
    rows = connection.execute(
        """
        SELECT json_extract(value, '$.document_id') AS document_id,
               json_extract(value, '$.document_name') AS document_name,
               json_extract(value, '$.relative_path') AS relative_path,
               json_extract(value, '$.source_authority') AS source_authority,
               json_extract(value, '$.warnings') AS warnings,
               json_extract(value, '$.anchor_document_name') AS anchor_document_name,
               json_extract(value, '$.anchor_document_path') AS anchor_document_path,
               json_extract(value, '$.anchor_document_metadata') AS anchor_document_metadata,
               json_extract(value, '$.anchor_rows') AS anchor_rows,
               json_extract(value, '$.canonical_name') AS canonical_name,
               json_extract(value, '$.tool_id') AS tool_id,
               json_extract(value, '$.is_anchor') AS is_anchor
        FROM authoritative_catalog_snapshots, json_each(payload_json, '$.documents')
        WHERE tenant_id = ?
        """,
        (tenant_id,),
    ).fetchall()
    written = 0
    for row in rows:
        document_id = _as_text(row["document_id"])
        if not document_id:
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO datum_document_provenance (
                tenant_id, document_id, document_name, relative_path, source_authority,
                warnings_json, anchor_document_name, anchor_document_path,
                anchor_document_metadata_json, anchor_rows_json, updated_at_unix_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id, document_id, _as_text(row["document_name"]), _as_text(row["relative_path"]),
                _as_text(row["source_authority"]) or "authoritative", row["warnings"] or "[]",
                _as_text(row["anchor_document_name"]), _as_text(row["anchor_document_path"]),
                row["anchor_document_metadata"] or "{}", row["anchor_rows"] or "[]", int(now),
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO datum_document_identity (tenant_id, document_id, "
            "canonical_name, tool_id, is_anchor, updated_at_unix_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, document_id, _as_text(row["canonical_name"]), _as_text(row["tool_id"]),
             1 if row["is_anchor"] else 0, int(now)),
        )
        written += 1
    if written:
        connection.commit()
    return written


def _upsert_documents_index(
    connection: Any, *, tenant_id: str, document: AuthoritativeDatumDocument,
    prior_document_id: str = "", now: int = 0,
) -> int:
    """Put ``document`` in the ``documents`` index, in the CALLER'S transaction.

    The index is a separate table from the catalog snapshot, and until now nothing but the
    workbook-apply path and a handful of bootstrap scripts maintained it — each with its own
    copy of this SQL. So a DELETE was index-correct (``delete_single_document_efficient``
    does this) and a CREATE was not: the catalog grew and the index did not, which is
    exactly what the archetype mint hit on its first rehearsal (catalog 531, index 510).

    It must run in the caller's transaction, not after it. A second transaction bumps the
    db mtime again and silently invalidates the catalog cache the write just seeded — the
    same failure the delete task recorded, where atomicity and cache validity turned out to
    be one property.

    Keyed on ``(msn_id, sandbox, name)``, which is what every other writer uses and what
    ``delete_single_document_efficient`` matches on. A re-key (content edit -> new hash ->
    new id) is a DELETE of the prior row plus an INSERT, so the stale id cannot outlive its
    document. Returns rows removed, so a caller can assert the write did something rather
    than agree with itself.
    """
    new_id = _as_text(document.document_id)
    try:
        parsed = parse_canonical_document_id(new_id)
    except Exception:
        # A legacy id has no name key, so the index cannot hold it — but its provenance
        # and identity can, and since 2026-09-22 they are where the catalog reader finds
        # the facts the blob used to carry for it.
        if new_id:
            _record_provenance(
                connection, tenant_id=tenant_id, document=document,
                prior_document_id=prior_document_id, now=now)
        return 0
    removed = 0
    stale_ids = sorted({_as_text(prior_document_id), new_id} - {""})
    # The place the document first appeared in: a re-key (new hash, new id) keeps the
    # row id of the row it replaces, so the catalog — ordered by this id since 2026-09-21
    # — keeps a replaced document where it was rather than moving it to the end.
    kept = connection.execute(
        f"SELECT MIN(id) FROM documents WHERE tenant_id=? AND (document_id IN ({','.join('?' * len(stale_ids))}) "
        "OR (prefix=? AND msn_id=? AND sandbox IS ? AND name=?))",
        (tenant_id, *stale_ids, parsed.prefix, parsed.msn_id, parsed.sandbox, parsed.name),
    ).fetchone()[0]
    for stale in stale_ids:
        removed += connection.execute(
            "DELETE FROM documents WHERE tenant_id=? AND document_id=?", (tenant_id, stale)
        ).rowcount
    # `sandbox IS ?`, not `sandbox = ?`. `art.`, `stl.` and `cptr.` carry NO sandbox
    # segment, so `parsed.sandbox` is None and `= NULL` is never TRUE in SQL — this DELETE
    # has therefore never matched a no-sandbox row, and the "replace the document of this
    # name" rule has silently never applied to one. It did not show because the store has
    # held only `lv.` documents, every one of which has a sandbox.
    #
    # The consequence for P5 is not academic: re-migrating an artifact would leave the old
    # index row beside the new one instead of replacing it, so a corrected file would be
    # one of two rows and a reader would get whichever it found.
    #
    # The PREFIX is in the key for the same reason, and only becomes load-bearing once the
    # comparison above works: with `IS` and without the prefix, an artifact and a binary
    # payload sharing an msn and a name would start evicting each other.
    #
    # Both are no-ops for the 749 live rows: all are `lv.`, all have a sandbox, so `IS`
    # and `=` agree and the prefix partition already held exactly one prefix.
    removed += connection.execute(
        "DELETE FROM documents WHERE tenant_id=? AND prefix=? AND msn_id=? AND sandbox IS ? "
        "AND name=?",
        (tenant_id, parsed.prefix, parsed.msn_id, parsed.sandbox, parsed.name),
    ).rowcount
    connection.execute(
        "INSERT INTO documents (id, tenant_id, document_id, prefix, msn_id, sandbox, name, "
        "version_hash, is_anchor, origin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'local', ?)",
        (kept, tenant_id, new_id, parsed.prefix, parsed.msn_id, parsed.sandbox, parsed.name,
         f"sha256:{parsed.version_hash}", 1 if document.is_anchor else 0, int(now)),
    )
    # Its provenance rides in the same transaction: identity and the context it was
    # written with are one fact about the document (TASK-2026-09-17-001 A).
    _record_provenance(
        connection, tenant_id=tenant_id, document=document,
        prior_document_id=prior_document_id, now=now)
    return removed


def _scoped_msn_for(connection, *, tenant_id: str, sandbox: str, msn_id: str) -> str:
    """Which msn to read this sandbox as: explicit, else the scope, else none.

    The request scope DISAMBIGUATES; it never narrows. That distinction is the whole rule
    and it was learned the expensive way: applying the scope to every read filtered the
    SHARED sandboxes too, so `job_manager` scoped to the client instance read `registrar` —
    which is FND's msn — as empty, and its 43 jobs rendered as none.

    A sandbox only one instance holds needs no msn and gets none, whatever the scope says.
    A sandbox several hold uses the scoped msn, and with no scope it raises rather than
    merging.
    """
    explicit = _as_text(msn_id)
    if explicit:
        return explicit
    found = {
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT msn_id FROM documents WHERE tenant_id = ? AND sandbox = ?",
            (tenant_id, sandbox),
        ).fetchall()
        if row[0]
    }
    if len(found) <= 1:
        return ""
    from micyte.core.instance_scope import active_instance_msn

    scoped = active_instance_msn()
    if scoped:
        return scoped
    raise AmbiguousSandboxError(
        f"{sandbox!r} is held by {len(found)} instances ({', '.join(sorted(found))}); "
        "pass msn_id or enter an instance scope to say which. A sandbox is addressed by "
        "(msn_id, sandbox), and a read that merged them would look like it worked."
    )


class AmbiguousSandboxError(RuntimeError):
    """A sandbox NAME that more than one instance holds, read without saying which."""


def _refuse_ambiguous_sandbox(connection, *, tenant_id: str, sandbox: str, msn_id: str) -> None:
    """Refuse a whole-sandbox read that spans two instances.

    A sandbox's address is ``(msn_id, sandbox)``. These reads were keyed on the NAME alone,
    which was decisive while a name identified exactly one sandbox — and stops being so the
    moment every instance keeps its own core sandbox called ``system``. A name-only read
    would then return four instances' documents as one sandbox, and every caller would work
    perfectly on the merged result: the workbench would list them together, a write runtime
    would pick whichever ``contacts`` sorted first, and nothing anywhere would error.

    So this RAISES rather than picking, logging, or returning the union. A read that quietly
    merges two tenants' books is the one failure mode that must never be recoverable-looking,
    and the caller that forgot its msn is the only thing that can fix it.

    Costs one indexed COUNT over ``documents`` and only when no msn was given.
    """
    if msn_id:
        return
    found = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT msn_id FROM documents WHERE tenant_id = ? AND sandbox = ?",
            (tenant_id, sandbox),
        ).fetchall()
        if row[0]
    ]
    if len(found) > 1:
        raise AmbiguousSandboxError(
            f"{sandbox!r} is held by {len(found)} instances ({', '.join(sorted(found))}); "
            "pass msn_id to say which. A sandbox is addressed by (msn_id, sandbox), and a "
            "read that merged them would look like it worked."
        )


def _record_binary_identity(connection: Any, *, tenant_id: str, document_id: str,
                            document: AuthoritativeDatumDocument, prior_document_id: str = "",
                            now: int) -> None:
    """Dual-write the binary MSS identity beside the JSON one (D2, 2026-09-17).

    Computed from the document's own rows and anchor rows — never the catalog — and
    only under the full-semantics cap: a 41,999-row document's closure is not encoded
    on the append path for the same reason its hyphae are not recomputed there. Over the
    cap the row says ``deferred`` so absence and "too big" are different facts.
    """
    if len(document.rows) <= _FULL_SEMANTICS_ROWS:
        identity = binary_identity(document)
    else:
        identity = {"policy": "deferred", "mss_hash": "", "datums": len(document.rows),
                    "dropped": {"dangling": 0, "upward": 0, "malformed": 0}}
    if prior_document_id and prior_document_id != document_id:
        connection.execute(
            "DELETE FROM datum_document_binary WHERE tenant_id = ? AND document_id = ?",
            (tenant_id, prior_document_id))
    connection.execute(
        """
        INSERT OR REPLACE INTO datum_document_binary (
            tenant_id, document_id, policy, mss_hash, datums, dropped_json, updated_at_unix_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, document_id, identity["policy"], identity["mss_hash"], identity["datums"],
         dumps_json(identity["dropped"]), now),
    )


def _record_bitstream(connection: Any, *, tenant_id: str, document_id: str,
                      document: AuthoritativeDatumDocument, prior_document_id: str = "",
                      now: int) -> None:
    """The document's rows as one MSS-DOC.v4 bitstream, beside the semantics row
    (TASK-2026-09-17-001 phase C). Total over the corpus — 1,356 of 1,356 documents
    decode row-identical — and written by every door in the caller's transaction. Over
    the full-semantics cap the row says ``deferred``, as the binary identity does, so
    absence and "too big" stay different facts."""
    if prior_document_id and prior_document_id != document_id:
        connection.execute(
            "DELETE FROM datum_document_bitstream WHERE tenant_id = ? AND document_id = ?",
            (tenant_id, prior_document_id))
    if len(document.rows) <= _FULL_SEMANTICS_ROWS:
        try:
            encoded = encode_rows(rows_of(document))
        except MssFormatError as exc:
            # The transport refuses what nothing could derive an address from (two rows
            # at one address). The DOOR accepted the document, so the write lands and the
            # row says so — a refusal the next reader can see, not a failed write.
            values = ("refused", "", 0, b"", len(document.rows), str(exc))
        else:
            values = (MSS_TRANSPORT_POLICY, encoded.hash, len(encoded.bitstream),
                      pack_bits(encoded.bitstream), encoded.datum_count, "")
    else:
        values = ("deferred", "", 0, b"", len(document.rows), "")
    connection.execute(
        """
        INSERT OR REPLACE INTO datum_document_bitstream (
            tenant_id, document_id, policy, mss_hash, bit_count, bitstream, datums, note, updated_at_unix_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, document_id, *values, now),
    )


def _bitstream_read_mode() -> str:
    """``MOS_READ_FROM_BITSTREAM``: ``""`` (off, the default), ``"1"`` (serve rows decoded
    from the bitstream when a document has one), or ``"verify"`` (decode, compare with the
    payload's rows, log a mismatch, serve the payload) — the dual read the rehearsal uses."""
    return os.environ.get("MOS_READ_FROM_BITSTREAM", "").strip().lower()


class SqliteSystemDatumStoreAdapter(
    SystemDatumStorePort,
    AuthoritativeDatumDocumentMutationPort,
    PublicationTenantSummaryPort,
    PublicationProfileBasicsWritePort,
):
    def __init__(
        self,
        db_file: str | Path,
        *,
        clock: Callable[[], int] | None = None,
        allow_legacy_writes: bool = False,
        read_only: bool = False,
    ) -> None:
        self._db_file = Path(db_file)
        #: A read-only adapter applies no schema on connect — the only safe way to point
        #: this class at a store you do not own (a measurement of the live store).
        self._read_only = bool(read_only)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._allow_legacy_writes_flag = bool(allow_legacy_writes)
        # Per-instance catalog cache: dict[tenant_id, (db_mtime_ns, catalog_result)]
        # Kept for tests that introspect per-instance state; the module-level
        # _GLOBAL_CATALOG_CACHE is consulted first to share fetches across
        # ephemeral adapter instances.
        self._catalog_cache: dict[str, tuple[int, Any]] = {}

    @property
    def db_file(self) -> Path:
        """The authority db this adapter is bound to.

        Public because sibling state is addressed relative to it — the contract
        store lives at `<private>/contracts/`, beside the db — and callers should
        not have to be told a path they could derive.
        """
        return self._db_file

    def _connect(self):
        return open_sqlite(self._db_file, read_only=self._read_only)

    def _allow_legacy_writes(self) -> bool:
        """Phase E3 one-cycle compatibility flag for legacy bootstrapping.

        New writes must produce canonical ``lv./stl./cptr.`` ids. This adapter
        keeps a per-instance ``allow_legacy_writes`` escape hatch that the
        bootstrapping pipeline (and tests that materialise legacy fixtures)
        opt into explicitly. The flag will be removed once the catalog
        upgrade in Phase E4 lands.
        """

        return self._allow_legacy_writes_flag

    def has_authoritative_catalog(self, tenant_id: str) -> bool:
        token = _as_text(tenant_id).lower()
        if not token:
            return False
        with self._connect() as connection:
            # The tables are the record (2026-09-22); the blob answers for a store
            # written by an older build whose tables hold nothing.
            row = connection.execute(
                "SELECT 1 FROM datum_document_semantics WHERE tenant_id = ? LIMIT 1",
                (token,),
            ).fetchone() or connection.execute(
                "SELECT 1 FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
                (token,),
            ).fetchone()
        return row is not None

    def has_system_workbench(self, tenant_id: str) -> bool:
        token = _as_text(tenant_id).lower()
        if not token:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM system_workbench_snapshots WHERE tenant_id = ?",
                (token,),
            ).fetchone()
        return row is not None

    def has_publication_summary(self, tenant_id: str, tenant_domain: str) -> bool:
        normalized_request = PublicationTenantSummaryRequest(
            tenant_id=tenant_id,
            tenant_domain=tenant_domain,
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM publication_summary_snapshots WHERE tenant_id = ? AND tenant_domain = ?",
                (normalized_request.tenant_id, normalized_request.tenant_domain),
            ).fetchone()
        return row is not None

    def store_authoritative_catalog(
        self,
        result: AuthoritativeDatumDocumentCatalogResult,
        *,
        allow_non_canonical_catalog_ids: bool | None = None,
    ) -> None:
        normalized = (
            result
            if isinstance(result, AuthoritativeDatumDocumentCatalogResult)
            else AuthoritativeDatumDocumentCatalogResult.from_dict(result)
        )
        non_canonical_ids: list[str] = []
        for document in normalized.documents:
            doc_id = _as_text(document.document_id)
            if doc_id and not is_canonical_document_id(doc_id):
                non_canonical_ids.append(doc_id)
        allow_legacy_effective = (
            self._allow_legacy_writes()
            if allow_non_canonical_catalog_ids is None
            else bool(allow_non_canonical_catalog_ids)
        )
        if non_canonical_ids and not allow_legacy_effective:
            raise NonCanonicalDocumentIdError(
                "Refusing to persist non-canonical document ids: "
                + ", ".join(sorted(set(non_canonical_ids))[:3])
                + (" …" if len(non_canonical_ids) > 3 else "")
            )
        _refuse_non_catalog_prefixes(normalized.documents)
        updated_at = self._clock()
        # Bound ONCE: serialized into the snapshot below and projected into the
        # index before this transaction commits. Two `.to_dict()` calls would build
        # the whole catalog twice.
        with self._connect() as connection:
            # temp_store only — the journal mode is left alone; see the note at
            # the top of this module.
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                connection.execute("DELETE FROM datum_row_semantics WHERE tenant_id = ?", (normalized.tenant_id,))
                connection.execute("DELETE FROM datum_document_semantics WHERE tenant_id = ?", (normalized.tenant_id,))
                # The snapshot now INCLUDES everything, so there is nothing outstanding
                # against it. Leaving the deltas would replay appends already in the blob.
                connection.execute(
                    "DELETE FROM document_row_appends WHERE tenant_id = ?", (normalized.tenant_id,)
                )
                connection.execute(
                    "DELETE FROM document_creates WHERE tenant_id = ?", (normalized.tenant_id,)
                )
                # The index and the provenance beside every document (2026-09-21): a bulk
                # import used to leave `documents` untouched, so a store it loaded had
                # semantics rows and no index rows — unreadable by any path that starts
                # from the index.
                connection.execute(
                    "DELETE FROM documents WHERE tenant_id = ? AND prefix = 'lv'", (normalized.tenant_id,)
                )
                connection.execute(
                    "DELETE FROM datum_document_provenance WHERE tenant_id = ?", (normalized.tenant_id,)
                )
                connection.execute(
                    "DELETE FROM datum_document_identity WHERE tenant_id = ?", (normalized.tenant_id,)
                )
                connection.execute(
                    """
                    INSERT INTO authoritative_catalog_facts
                        (tenant_id, source_files_json, readiness_json, updated_at_unix_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                        source_files_json = excluded.source_files_json,
                        readiness_json = excluded.readiness_json,
                        updated_at_unix_ms = excluded.updated_at_unix_ms
                    """,
                    (
                        normalized.tenant_id,
                        dumps_json(dict(normalized.source_files or {})),
                        dumps_json(dict(normalized.readiness_status or {})),
                        updated_at,
                    ),
                )
                for document in normalized.documents:
                    semantics = build_document_semantics(document)
                    _upsert_documents_index(
                        connection, tenant_id=normalized.tenant_id, document=document, now=updated_at)
                    connection.execute(
                        """
                        INSERT INTO datum_document_semantics (
                            tenant_id,
                            document_id,
                            policy,
                            version_hash,
                            canonical_payload_json,
                            updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            normalized.tenant_id,
                            document.document_id,
                            semantics["document"]["policy"],
                            semantics["document"]["version_hash"],
                            dumps_json(semantics["document"]["canonical_payload"]),
                            updated_at,
                        ),
                    )
                    _record_bitstream(
                        connection, tenant_id=normalized.tenant_id, document_id=document.document_id,
                        document=document, now=updated_at)
                    for datum_address, row_semantics in semantics["rows"].items():
                        connection.execute(
                            """
                            INSERT INTO datum_row_semantics (
                                tenant_id,
                                document_id,
                                datum_address,
                                policy,
                                semantic_hash,
                                hyphae_hash,
                                hyphae_chain_json,
                                local_references_json,
                                warnings_json,
                                updated_at_unix_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                normalized.tenant_id,
                                document.document_id,
                                datum_address,
                                row_semantics["policy"],
                                row_semantics["semantic_hash"],
                                row_semantics["hyphae_hash"],
                                dumps_json(row_semantics["hyphae_chain"]),
                                dumps_json(row_semantics["local_references"]),
                                dumps_json(row_semantics["warnings"]),
                                updated_at,
                            ),
                        )
                # Refresh the index in THIS transaction, from the payload already in
                # hand. Before 2026-08-24 all four of these paths invalidated the index
                # and none refreshed it, so the rebuild fell on the next reader at
                # 543.9 MB peak instead of 25.5 MB — and under MemoryMax=1200M that
                # reader was killed mid-rebuild, so it never persisted and every retry
                # repeated. Non-fatal by design: on failure the read path still heals it.
                # The projection, from the documents just stored (2026-09-22: no blob is
                # written, so no payload is in hand — the documents are).
                try:
                    entries = self._project_catalog_index(
                        connection, normalized.tenant_id,
                        [d.to_dict() for d in normalized.documents])
                    self._persist_catalog_index(
                        connection, normalized.tenant_id, entries,
                        self._tables_version(connection, normalized.tenant_id), commit=False)
                except Exception:
                    _log.warning("could not project the catalog index for tenant %s; "
                                 "the next read rebuilds", normalized.tenant_id, exc_info=True)
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
        # Phase 14c: invalidate the in-memory catalog caches on EVERY
        # catalog write path — the per-instance + module-level dicts both
        # rely on this since mtime granularity on some filesystems is
        # coarser than the test save→load sequence.
        self._catalog_cache.pop(normalized.tenant_id, None)
        _GLOBAL_CATALOG_CACHE.pop((str(self._db_file.resolve()), normalized.tenant_id), None)
        _GLOBAL_INDEX_CACHE.pop((str(self._db_file.resolve()), normalized.tenant_id), None)
        _forget_sandboxes(str(self._db_file.resolve()), normalized.tenant_id)

    def replace_single_document_efficient(
        self,
        *,
        tenant_id: str,
        prior_document_id: str | None,
        updated_document: AuthoritativeDatumDocument,
    ) -> None:
        """Replace exactly one document in the catalog without re-encoding
        every other document's semantics.

        Background: :meth:`store_authoritative_catalog` does a full
        ``DELETE FROM datum_row_semantics WHERE tenant_id=?`` followed by
        re-INSERTing every row of every document. For a single
        contact-log update with 1168 rows on top of 124 CTS-GIS docs,
        that's ~100 MB of pointless work and a worker memory spike
        (observed: ~800 MB transient allocation, OOM-throttled by
        MemoryHigh=1500M in the systemd override).

        Since 2026-09-22 it is the one-document case of :meth:`replace_documents_efficient`:
        no catalog read, no blob write, the document's own rows.
        """
        self.replace_documents_efficient(
            tenant_id=tenant_id,
            replacements=[(prior_document_id or None, updated_document)],
        )

    def delete_single_document_efficient(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """Remove exactly one document without re-encoding every other one's semantics.

        The deleting sibling of :meth:`replace_single_document_efficient`, and it
        exists for the same reason, only more so:
        :meth:`delete_authoritative_document` routes through
        :meth:`store_authoritative_catalog`, which DELETEs and re-INSERTs the
        semantics of every document in the tenant. Measured on the live FND store
        (2026-08-06): 105,811 ``datum_row_semantics`` rows behind a 138 MB catalog
        snapshot — the shape whose transient allocation was observed at ~800 MB and
        OOM-throttled under ``MemoryHigh=1500M``. Spending that to remove one
        document is how an interactive delete takes the portal worker down with it.

        Cost here is O(rows_in_deleted_doc); since 2026-09-22 no snapshot is rewritten
        and no catalog is read.

        The ``documents`` INDEX row goes in the SAME transaction, and that is not
        tidiness. The index is a separate table no catalog write maintains (see
        ``_upsert_documents_index``), so a delete that skips it leaves the document
        listed under an id that resolves to nothing — but doing it in a second
        transaction afterwards, as the first cut of this did, bumps the db mtime again
        and silently invalidates the catalog cache this method has just seeded. The
        reload then re-parses 138 MB anyway, which is the whole failure this is written
        against. Atomicity and cache validity turn out to be the same property here.

        Returns the number of index rows removed.
        """
        target = _as_text(document_id)
        if not target:
            raise ValueError("document_id is required")
        tenant = _as_text(tenant_id).lower()
        index_rows_removed = 0
        with self._connect() as connection:
            if not self._document_exists(connection, tenant_id=tenant, document_id=target):
                raise ValueError("authoritative_document_missing")
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                related = {target}
                for base_id, post_id in connection.execute(
                    "SELECT base_document_id, document_id FROM document_row_appends "
                    "WHERE tenant_id = ? AND (document_id = ? OR base_document_id = ?)",
                    (tenant, target, target),
                ).fetchall():
                    related.add(_as_text(base_id))
                    related.add(_as_text(post_id))
                related.discard("")
                for member in related:
                    for table in ("datum_row_semantics", "datum_document_semantics",
                                  "document_creates", "datum_document_binary",
                                  "datum_document_bitstream",
                                  "datum_document_provenance", "datum_document_identity"):
                        connection.execute(
                            f"DELETE FROM {table} WHERE tenant_id = ? AND document_id = ?",
                            (tenant, member),
                        )
                    connection.execute(
                        "DELETE FROM document_row_appends WHERE tenant_id = ? "
                        "AND (document_id = ? OR base_document_id = ?)",
                        (tenant, member, member),
                    )
                try:
                    parsed = parse_canonical_document_id(target)
                except Exception:  # a legacy id has no name key to match on
                    parsed = None
                # A namesake that survives (two versions under one name) keeps the
                # name-keyed index row; the row goes only when nothing else answers to it.
                placeholders = ",".join("?" * len(related))
                survives = parsed is not None and connection.execute(
                    "SELECT 1 FROM datum_document_semantics AS s JOIN documents AS d "
                    "ON d.tenant_id = s.tenant_id AND d.document_id = s.document_id "
                    "WHERE s.tenant_id = ? AND d.msn_id = ? AND d.sandbox IS ? AND d.name = ? "
                    f"AND s.document_id NOT IN ({placeholders}) LIMIT 1",
                    (tenant, parsed.msn_id, parsed.sandbox, parsed.name, *sorted(related)),
                ).fetchone() is not None
                if parsed is not None and not survives:
                    index_rows_removed += connection.execute(
                        "DELETE FROM documents WHERE tenant_id=? AND msn_id=? AND sandbox IS ? AND name=?",
                        (tenant, parsed.msn_id, parsed.sandbox, parsed.name),
                    ).rowcount
                for member in related:
                    index_rows_removed += connection.execute(
                        "DELETE FROM documents WHERE tenant_id=? AND document_id=?",
                        (tenant, member),
                    ).rowcount
                self._refresh_index_entry(
                    connection, tenant_id=tenant, document=None,
                    remove_ids=related)
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
        self._catalog_cache.pop(tenant, None)
        _GLOBAL_CATALOG_CACHE.pop((str(self._db_file.resolve()), tenant), None)
        _GLOBAL_INDEX_CACHE.pop((str(self._db_file.resolve()), tenant), None)
        _forget_sandboxes(str(self._db_file.resolve()), tenant)
        return index_rows_removed

    def store_artifact_document(
        self, *, tenant_id: str, document: AuthoritativeDatumDocument,
    ) -> None:
        """Write an `art.` document PAST the catalog snapshot.

        The same three writes every other path makes — the `documents` index, the
        document's semantics, its rows' semantics — and deliberately not the fourth.

        WHY THERE IS A SEPARATE METHOD AT ALL. Every existing write maintains the catalog
        snapshot, which is one row per tenant holding every document as JSON: 138 MB live,
        ~290 MiB parsed, and read WHOLE on every authoritative read. The artifact pool is
        956 files and 127 MB, ~306 MB once decimal, so putting it there would take every
        reader from 138 MB toward 390 MB whether or not that reader wants a single byte of
        it. `store_authoritative_catalog` and its siblings REFUSE an `art.` document for
        exactly this reason (:class:`NonCatalogPrefixError`), so this is not a shortcut
        around a check — it is the path that check exists to point at.

        The read half already exists and needs nothing new:
        ``read_authoritative_document(..., allow_catalog_fallback=False)`` serves one
        document from its own semantics row without touching the blob. The fallback must
        be OFF for an artifact — falling back would search 138 MB for something that is
        deliberately not in it, and find nothing slowly.

        Cost is linear in the artifact's rows: ~0.16 ms/row measured over artifact-shaped
        documents, whose rows reference nothing and so cost the floor rate rather than the
        17.6 s/42k-row figure a dependency-heavy document reaches.
        """
        document_id = _as_text(document.document_id)
        if not document_id.startswith("art."):
            raise NonCatalogPrefixError(
                f"store_artifact_document is for `art.` documents; got {document_id!r}. "
                "Everything else belongs in the catalog, through the ordinary write path.")
        if not is_canonical_document_id(document_id):
            raise NonCanonicalDocumentIdError(
                f"Refusing to persist non-canonical document id: {document_id!r}")

        semantics = build_document_semantics(document)
        updated_at = self._clock()
        with self._connect() as connection:
            _refuse_identity_policy_mismatch(
                connection, tenant_id=_as_text(tenant_id).lower(), policy=semantics["document"]["policy"])
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                # Scoped by document_id, so a rewrite costs its own rows and not the
                # tenant's. Both tables, because a stale row-semantics entry under a
                # document that has fewer rows now is a row nothing will ever delete.
                for table in ("datum_row_semantics", "datum_document_semantics"):
                    connection.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ? AND document_id = ?",
                        (tenant_id, document_id))
                connection.execute(
                    """
                    INSERT INTO datum_document_semantics (
                        tenant_id, document_id, policy, version_hash,
                        canonical_payload_json, updated_at_unix_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tenant_id, document_id, semantics["document"]["policy"],
                     semantics["document"]["version_hash"],
                     dumps_json(semantics["document"]["canonical_payload"]), updated_at),
                )
                for datum_address, row_semantics in semantics["rows"].items():
                    connection.execute(
                        """
                        INSERT INTO datum_row_semantics (
                            tenant_id, document_id, datum_address, policy, semantic_hash,
                            hyphae_hash, hyphae_chain_json, local_references_json,
                            warnings_json, updated_at_unix_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (tenant_id, document_id, datum_address, row_semantics["policy"],
                         row_semantics["semantic_hash"], row_semantics["hyphae_hash"],
                         dumps_json(row_semantics["hyphae_chain"]),
                         dumps_json(row_semantics["local_references"]),
                         dumps_json(row_semantics.get("warnings") or []), updated_at),
                    )
                _upsert_documents_index(
                    connection, tenant_id=tenant_id, prior_document_id=None,
                    document=document, now=updated_at)
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")

    def list_artifact_documents(
        self, *, tenant_id: str, msn_id: str = "",
    ) -> tuple[dict[str, Any], ...]:
        """Every `art.` document's metadata, FROM THE INDEX — never from the blob.

        This inverts the direction :meth:`read_document_index` insists on, and does so
        because the rule there is right about `lv.` and inapplicable here.

        That method is DERIVED FROM THE BLOB precisely so it cannot miss a document the
        normalized tables lack: measured on the live store, 584 in the catalog against 583
        in each table, and an index built from the tables would silently drop the
        difference — the failure shape that once hid 469 of 471 documents.

        An artifact is DEFINED by being outside the blob (:class:`NonCatalogPrefixError`),
        so that read cannot see one and never will. Asking the blob for artifacts would
        return nothing, forever, and look exactly like an instance with no artifacts.
        Hence the `documents` index, which `store_artifact_document` writes in the same
        transaction as the semantics.

        The safety the blob rule buys is bought differently here: nothing else writes an
        `art.` row, so the index is not one of two sources that can disagree — it is the
        only one.

        Metadata only. An artifact's ROWS are its bytes, and a listing that materialised
        them would parse the whole pool to draw a list of names.
        """
        rows = []
        with self._connect() as connection:
            if msn_id:
                cursor = connection.execute(
                    "SELECT document_id, msn_id, name, version_hash, created_at "
                    "FROM documents WHERE tenant_id = ? AND prefix = 'art' AND msn_id = ? "
                    "ORDER BY name",
                    (tenant_id, msn_id))
            else:
                cursor = connection.execute(
                    "SELECT document_id, msn_id, name, version_hash, created_at "
                    "FROM documents WHERE tenant_id = ? AND prefix = 'art' ORDER BY name",
                    (tenant_id,))
            for row in cursor:
                rows.append({
                    "document_id": row["document_id"],
                    "msn_id": row["msn_id"],
                    "name": row["name"],
                    "version_hash": row["version_hash"],
                    "created_at": row["created_at"],
                })
        return tuple(rows)

    def read_artifact_document(
        self, *, tenant_id: str, document_id: str,
    ) -> AuthoritativeDatumDocument | None:
        """One artifact, from its own semantics row. NEVER the catalog.

        `allow_catalog_fallback=False` is the whole point: an artifact is deliberately
        absent from the blob, so a fallback would search 138 MB to find nothing. A miss
        here means the artifact is not stored, which is a fact worth returning quickly.
        """
        return self.read_authoritative_document(
            tenant_id=tenant_id, document_id=document_id, allow_catalog_fallback=False)

    def replace_documents_efficient(
        self,
        *,
        tenant_id: str,
        replacements: Sequence[tuple[str | None, AuthoritativeDatumDocument]],
    ) -> None:
        """Replace or append MANY documents in one pass, touching only their semantics.

        Since 2026-09-22 (TASK-2026-09-17-001 B) this touches NO catalog blob and reads no
        catalog: a prior is checked against the semantics table, the changed documents'
        semantics, index rows, provenance, binary identity and index entries are written,
        and nothing else in the tenant is read or rewritten. A two-row replace costs two
        rows; it used to cost 776 MB.

        The bulk sibling of :meth:`replace_single_document_efficient`, and the reason it
        exists separately: that method re-reads the catalog and rewrites the whole
        snapshot blob on every call, so looping it over a few hundred mints costs a few
        hundred re-parses of a ~50 MB payload. This does the read once, the snapshot once,
        and the semantics per changed document.

        Why not :meth:`store_authoritative_catalog`: its whole-tenant
        ``DELETE FROM datum_row_semantics`` touches every page of the largest table in the
        file. On a 300 MB authority that is a ~250 MB spike — observed as an OOM kill
        mid-transaction which, because both write paths then ran under ``PRAGMA
        journal_mode = MEMORY``, had nothing on disk to roll back and left the database
        file malformed. The journal-mode switch is gone (see the note at the top of this
        module), so the crash is now recoverable — but the spike is still real work
        nobody asked for, and a bulk mint must not be able to cause it.

        ``replacements`` is ``(prior_document_id | None, updated_document)`` pairs; a
        ``None`` prior appends, and a prior the catalog does not hold raises
        :class:`UnknownPriorDocumentIdError` rather than appending. Applied in order, in a
        single transaction.
        """
        _refuse_non_catalog_prefixes(
            [doc for _prior, doc in (replacements or ())])
        pairs = [
            (_as_text(prior) if prior else "", document) for prior, document in replacements
        ]
        for _, document in pairs:
            new_id = _as_text(document.document_id)
            if not new_id:
                raise ValueError("updated_document.document_id is required")
            if not is_canonical_document_id(new_id) and not self._allow_legacy_writes():
                raise NonCanonicalDocumentIdError(
                    f"Refusing to persist non-canonical document id: {new_id!r}"
                )
        if not pairs:
            return
        # The engine's document-level invariants over what CHANGED, judged BEFORE the
        # transaction opens and against the prior as the store holds it
        # (`core/mss/invariants.check_replaced_rows`). Until 2026-09-29 this door — the one
        # every in-place writer and every repair script replaces through — judged nothing,
        # so a four-pair row at `4-1-1` landed in a document that keeps its rows at `4-4`
        # while the append door next to it would have refused the same row. A replacement
        # with no prior is a create, and is held to the create door's rule: I7 is not
        # judged, because the document's first rows set which convention it keeps.
        for prior_id, document in pairs:
            new_id = _as_text(document.document_id)
            artifact = new_id.split(".", 1)[0] == "art"
            if prior_id:
                prior = self.read_authoritative_document(
                    tenant_id=tenant_id, document_id=prior_id, allow_catalog_fallback=False)
                refusals = (check_replaced_rows(prior.rows, document.rows, artifact=artifact)
                            if prior is not None else ())
            else:
                refusals = check_rows(document.rows, artifact=artifact, arity=False)
            if refusals:
                raise InvariantRefused(refusals)
        tenant = _as_text(tenant_id).lower()
        updated_at = self._clock()
        with self._connect() as connection:
            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                # Every prior is checked BEFORE anything is written, so a bad batch is
                # refused whole rather than half-applied. A prior may also be an id this
                # same batch is about to write (a chain of swaps), which the catalog-based
                # check honoured by construction.
                written: set[str] = set()
                for prior_id, document in pairs:
                    if prior_id and prior_id not in written and not self._document_exists(
                            connection, tenant_id=tenant, document_id=prior_id):
                        raise UnknownPriorDocumentIdError(
                            f"prior_document_id not in the {tenant_id!r} catalog: {prior_id!r}"
                        )
                    written.add(_as_text(document.document_id))
                for prior_id, document in pairs:
                    new_id = _as_text(document.document_id)
                    stale = {new_id} | ({prior_id} if prior_id else set())
                    for document_id in stale:
                        connection.execute(
                            "DELETE FROM datum_row_semantics WHERE tenant_id = ? AND document_id = ?",
                            (tenant, document_id),
                        )
                        connection.execute(
                            "DELETE FROM datum_document_semantics WHERE tenant_id = ? AND document_id = ?",
                            (tenant, document_id),
                        )
                    semantics = build_document_semantics(document)
                    _refuse_identity_policy_mismatch(
                        connection, tenant_id=tenant, policy=semantics["document"]["policy"])
                    connection.execute(
                        """
                        INSERT INTO datum_document_semantics (
                            tenant_id, document_id, policy, version_hash,
                            canonical_payload_json, updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tenant,
                            new_id,
                            semantics["document"]["policy"],
                            semantics["document"]["version_hash"],
                            dumps_json(semantics["document"]["canonical_payload"]),
                            updated_at,
                        ),
                    )
                    for datum_address, row_semantics in semantics["rows"].items():
                        connection.execute(
                            """
                            INSERT INTO datum_row_semantics (
                                tenant_id, document_id, datum_address, policy,
                                semantic_hash, hyphae_hash, hyphae_chain_json,
                                local_references_json, warnings_json, updated_at_unix_ms
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                tenant,
                                new_id,
                                datum_address,
                                row_semantics["policy"],
                                row_semantics["semantic_hash"],
                                row_semantics["hyphae_hash"],
                                dumps_json(row_semantics["hyphae_chain"]),
                                dumps_json(row_semantics["local_references"]),
                                dumps_json(row_semantics["warnings"]),
                                updated_at,
                            ),
                        )
                    _upsert_documents_index(
                        connection, tenant_id=tenant, document=document,
                        prior_document_id=prior_id, now=updated_at,
                    )
                    _record_binary_identity(
                        connection, tenant_id=tenant, document_id=new_id, document=document,
                        prior_document_id=prior_id, now=updated_at)
                    _record_bitstream(
                        connection, tenant_id=tenant, document_id=new_id, document=document,
                        prior_document_id=prior_id, now=updated_at)
                    self._refresh_index_entry(
                        connection, tenant_id=tenant, document=document,
                        prior_document_id=prior_id)
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
        self._catalog_cache.pop(tenant, None)
        _GLOBAL_CATALOG_CACHE.pop((str(self._db_file.resolve()), tenant), None)
        _GLOBAL_INDEX_CACHE.pop((str(self._db_file.resolve()), tenant), None)
        _forget_sandboxes(str(self._db_file.resolve()), tenant)

    def _document_exists(self, connection: Any, *, tenant_id: str, document_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM datum_document_semantics WHERE tenant_id = ? AND document_id = ? LIMIT 1",
            (tenant_id, document_id),
        ).fetchone() is not None

    def store_system_workbench(self, result: SystemDatumWorkbenchResult) -> None:
        normalized = (
            result
            if isinstance(result, SystemDatumWorkbenchResult)
            else SystemDatumWorkbenchResult.from_dict(result)
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_workbench_snapshots (tenant_id, payload_json, updated_at_unix_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (normalized.tenant_id, dumps_json(normalized.to_dict()), self._clock()),
            )
            connection.commit()

    def store_publication_summary(self, result: PublicationTenantSummaryResult, *, tenant_id: str, tenant_domain: str) -> None:
        normalized_request = PublicationTenantSummaryRequest(tenant_id=tenant_id, tenant_domain=tenant_domain)
        normalized_result = (
            result
            if isinstance(result, PublicationTenantSummaryResult)
            else PublicationTenantSummaryResult.from_dict(result)
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO publication_summary_snapshots (tenant_id, tenant_domain, payload_json, updated_at_unix_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, tenant_domain) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (
                    normalized_request.tenant_id,
                    normalized_request.tenant_domain,
                    dumps_json(normalized_result.to_dict()),
                    self._clock(),
                ),
            )
            connection.commit()

    def bootstrap_from_filesystem(
        self,
        *,
        data_dir: str | Path,
        public_dir: str | Path | None,
        tenant_id: str,
        tenant_domain: str | None = None,
        canonical_ids: bool = False,
        canonical_ids_msn: str = "3-2-3",
    ) -> None:
        filesystem = FilesystemSystemDatumStoreAdapter(Path(data_dir), public_dir=public_dir)
        normalized_tenant_id = _as_text(tenant_id).lower()
        catalog = filesystem.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=normalized_tenant_id)
        )
        # ``canonical_ids`` rewrites each filesystem-derived legacy id
        # (``system:`` / ``sandbox:`` …) to its canonical ``lv.`` form before
        # persisting. This is the only knob that lets bootstrap-based fixtures
        # exercise the canonical-only write path (apply re-persists the full
        # catalog and refuses non-canonical ids). Default False preserves the
        # legacy-keyed seed shape that read-only fixtures still assert against.
        if canonical_ids:
            catalog = self._canonicalize_catalog_document_ids(
                catalog, msn_id=canonical_ids_msn
            )
        self.store_authoritative_catalog(
            catalog,
            allow_non_canonical_catalog_ids=not canonical_ids,
        )
        self.store_system_workbench(
            filesystem.read_system_resource_workbench(
                SystemDatumStoreRequest(tenant_id=normalized_tenant_id)
            )
        )
        if tenant_domain:
            self.store_publication_summary(
                filesystem.read_publication_tenant_summary(
                    PublicationTenantSummaryRequest(
                        tenant_id=normalized_tenant_id,
                        tenant_domain=tenant_domain,
                    )
                ),
                tenant_id=normalized_tenant_id,
                tenant_domain=tenant_domain,
            )

    def _canonicalize_catalog_document_ids(
        self,
        catalog: AuthoritativeDatumDocumentCatalogResult,
        *,
        msn_id: str,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """Return ``catalog`` with every legacy document id rewritten to its
        canonical ``lv.`` form, keyed by the document's own content hash.

        Mirrors the production migration convention (one ``msn_id`` per tenant,
        ``version_hash`` taken from the document semantics). Documents that are
        already canonical pass through unchanged. ``source_files`` keys are
        relative paths, not ids, so they are left intact.
        """

        canonical_documents = []
        for document in catalog.documents:
            doc_id = _as_text(document.document_id)
            if not doc_id or is_canonical_document_id(doc_id):
                canonical_documents.append(document)
                continue
            version_hash = build_document_semantics(document)["document"]["version_hash"]
            canonical_id = derive_canonical_id_from_legacy(
                doc_id, msn_id=msn_id, version_hash=version_hash
            )
            canonical_documents.append(
                dataclasses.replace(document, document_id=canonical_id)
            )
        return dataclasses.replace(catalog, documents=tuple(canonical_documents))

    def _db_mtime_ns(self) -> int:
        try:
            return int(self._db_file.stat().st_mtime_ns)
        except OSError:
            return 0

    def read_authoritative_datum_documents(
        self,
        request: AuthoritativeDatumDocumentRequest,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """The whole catalog, assembled from the per-document tables.

        Until 2026-09-21 this parsed the 138 MB ``authoritative_catalog_snapshots`` blob
        (~290 MiB of objects, kept resident) and folded the create/append deltas onto it —
        and a delta whose base the blob no longer held was DROPPED, so the whole-catalog
        readers served `registrar.address_nodes` without its 2026-09-10 append while the
        per-document readers served it with. Measured that day: ``documents`` ⋈
        ``datum_document_semantics`` holds every row the blob holds (42 documents differ in
        row ORDER only — the payload is canonical order), the same metadata, and the
        documents the blob never did. So the tables are the record; the blob is the
        2026-09-18 snapshot kept for rollback, read here only for a store the tables
        cannot describe (none written by this code).
        """
        normalized_request = (
            request
            if isinstance(request, AuthoritativeDatumDocumentRequest)
            else AuthoritativeDatumDocumentRequest.from_dict(request)
        )
        tenant_id = normalized_request.tenant_id
        db_mtime = self._db_mtime_ns()
        cached = self._catalog_cache.get(tenant_id)
        if cached is not None and cached[0] == db_mtime:
            return cached[1]
        global_key = (str(self._db_file.resolve()), tenant_id)
        global_cached = _GLOBAL_CATALOG_CACHE.get(global_key)
        if global_cached is not None and global_cached[0] == db_mtime:
            self._catalog_cache[tenant_id] = global_cached
            return global_cached[1]
        with self._connect() as connection:
            result = self._assemble_catalog(connection, tenant_id)
            if result is None:
                result = self._read_catalog_from_blob(connection, tenant_id)
        self._catalog_cache[tenant_id] = (db_mtime, result)
        _remember_catalog(global_key, db_mtime, result)
        return result

    def _assemble_catalog(
        self, connection: Any, tenant_id: str
    ) -> AuthoritativeDatumDocumentCatalogResult | None:
        """``documents`` ⋈ ``datum_document_semantics`` (+ provenance), in index order.
        ``None`` when the tables hold no catalog document for the tenant."""
        # Driven by the SEMANTICS table, which every door writes; `documents` is a LEFT
        # JOIN for `is_anchor` and for the order a document first appeared in (a re-key
        # keeps its row id, so a replaced document keeps its place). A store loaded by
        # `store_authoritative_catalog` before 2026-09-21 has semantics rows and no index
        # rows at all, which is why the index cannot be the driver.
        rows = connection.execute(
            """
            SELECT s.document_id AS document_id, d.name AS name, d.sandbox AS sandbox,
                   d.is_anchor AS is_anchor, s.canonical_payload_json AS payload
            FROM datum_document_semantics AS s
            LEFT JOIN documents AS d
                   ON d.tenant_id = s.tenant_id AND d.document_id = s.document_id
            WHERE s.tenant_id = ? AND s.document_id NOT LIKE 'art.%'
                  AND s.document_id NOT LIKE 'stl.%' AND s.document_id NOT LIKE 'cptr.%'
            ORDER BY COALESCE(d.id, 9223372036854775807), s.rowid
            """,
            (tenant_id,),
        )
        # The three exclusions are `ALLOWED_PREFIXES` minus `lv` — the same rule as
        # `_refuse_non_catalog_prefixes`, pinned to it by the lv-only suite. A LEGACY id
        # (no recognised prefix; `allow_legacy_writes`) passes, as it did through the blob.
        # Streamed, not fetched whole: the payload strings of the live catalog total 187 MB
        # and holding them all beside their parsed rows doubled the read's peak.
        first = rows.fetchone()
        if first is None:
            return None
        provenance = _read_provenance(connection, tenant_id)
        if not provenance:
            healed = _heal_provenance_from_blob(connection, tenant_id, self._clock())
            if healed:
                _log.info("datum_document_provenance healed from the blob: %d documents", healed)
                provenance = _read_provenance(connection, tenant_id)
        documents: list[AuthoritativeDatumDocument] = []
        without_payload = 0
        unnamed = 0
        for row in _chain_first(first, rows):
            if row["payload"] is None:
                without_payload += 1
                continue
            document_id = _as_text(row["document_id"])
            given = provenance.get(document_id) or {}
            try:
                parsed = parse_canonical_document_id(document_id)
            except Exception:
                parsed = None
            if parsed is None and given.get("canonical_name") is None:
                # A legacy id with no identity row: nothing in the tables can name it.
                unnamed += 1
                continue
            name = (given["canonical_name"] if given.get("canonical_name") is not None
                    else _as_text(row["name"]) or _as_text(parsed.name))
            sandbox = (given["tool_id"] if given.get("tool_id") is not None
                       else _as_text(row["sandbox"]) or _as_text(parsed.sandbox))
            is_anchor = (bool(row["is_anchor"]) if row["is_anchor"] is not None
                         else bool(given.get("is_anchor")))
            payload = loads_json(row["payload"])
            documents.append(
                AuthoritativeDatumDocument(
                    document_id=document_id,
                    source_kind=_as_text(payload.get("source_kind")) or "sandbox_source",
                    document_name=given.get("document_name") or f"{name}.json",
                    relative_path=given.get("relative_path")
                    or (f"{sandbox}/{name}.json" if sandbox else f"{name}.json"),
                    canonical_name=name,
                    tool_id=sandbox,
                    source_authority=given.get("source_authority") or "authoritative",
                    is_anchor=is_anchor,
                    anchor_document_name=given.get("anchor_document_name") or "",
                    anchor_document_path=given.get("anchor_document_path") or "",
                    anchor_document_metadata=given.get("anchor_document_metadata") or None,
                    anchor_rows=tuple(given.get("anchor_rows") or ()),
                    rows=tuple(
                        AuthoritativeDatumDocumentRow(
                            datum_address=_as_text(item.get("datum_address")), raw=item.get("raw")
                        )
                        for item in payload.get("rows", ())
                    ),
                    document_metadata=payload.get("document_metadata") or {},
                    warnings=tuple(given.get("warnings") or ()),
                )
            )
        if not documents:
            return None
        source_files, readiness = self._catalog_provenance(connection, tenant_id)
        readiness = dict(readiness)
        readiness["authoritative_catalog"] = "loaded"
        readiness["store_of_record"] = "datum_document_semantics"
        if without_payload:
            _log.warning(
                "%d indexed documents have no semantics payload and are not in the catalog",
                without_payload)
            readiness["documents_without_semantics"] = without_payload
        if unnamed:
            _log.warning("%d legacy documents have no identity row and are not in the catalog", unnamed)
            readiness["documents_without_identity"] = unnamed
        return AuthoritativeDatumDocumentCatalogResult(
            tenant_id=tenant_id,
            documents=tuple(documents),
            source_files=source_files,
            readiness_status=readiness,
            warnings=(),
        )

    def _catalog_provenance(self, connection: Any, tenant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """The catalog's own ``source_files`` / ``readiness_status`` — historical facts about
        the import that built it: from ``authoritative_catalog_facts`` when the bulk door
        recorded them (2026-09-22), else from the blob's top level (two ``json_extract``
        calls, no parse) for a store written before that; empty for one that had neither."""
        row = connection.execute(
            "SELECT source_files_json AS source_files, readiness_json AS readiness_status "
            "FROM authoritative_catalog_facts WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone() or connection.execute(
            "SELECT json_extract(payload_json, '$.source_files') AS source_files, "
            "json_extract(payload_json, '$.readiness_status') AS readiness_status "
            "FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return {}, {}
        try:
            source_files = loads_json(row["source_files"]) if row["source_files"] else {}
            readiness = loads_json(row["readiness_status"]) if row["readiness_status"] else {}
        except Exception:
            return {}, {}
        return (source_files if isinstance(source_files, dict) else {},
                readiness if isinstance(readiness, dict) else {})

    def _read_catalog_from_blob(
        self, connection: Any, tenant_id: str
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """The pre-2026-09-21 read: the snapshot blob plus the deltas folded onto it. The
        FALLBACK for a store whose tables hold no catalog document, and the reference the
        parity script (`fnd_app/scripts/verify_catalog_parity.py`) compares against."""
        row = connection.execute(
            "SELECT payload_json FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return AuthoritativeDatumDocumentCatalogResult(
                tenant_id=tenant_id,
                documents=(),
                source_files={},
                readiness_status={"authoritative_catalog": "missing"},
                warnings=("sql_authoritative_catalog_missing",),
            )
        payload = loads_json(row["payload_json"])
        self._project_canonical_document_ids(connection, tenant_id, payload)
        self._apply_pending_creates(connection, tenant_id, payload)
        _apply_pending_appends(connection, tenant_id, payload)
        return AuthoritativeDatumDocumentCatalogResult.from_dict(payload)

    def read_document_index(
        self, request: AuthoritativeDatumDocumentRequest | dict[str, Any]
    ) -> AuthoritativeDatumDocumentIndexResult:
        """Every document's METADATA, without materializing a single row.

        This is the read the portal shell actually needs. Four of its five catalog
        reads want names, sandboxes, counts and version hashes; only the datum grid
        wants rows, and only for the ONE document in view.

        Since 2026-09-21 the projection is built from the TABLES (the assembled catalog),
        keyed for freshness on the newest write the tables hold — the latest semantics
        ``updated_at_unix_ms`` or index ``created_at`` — so a create or append, which
        writes the tables and no blob, makes the persisted projection stale and rebuilt on
        the next read rather than patched by deltas. The blob-derived rebuild remains the
        fallback for a store whose tables hold no catalog document.
        """
        normalized_request = (
            request
            if isinstance(request, AuthoritativeDatumDocumentRequest)
            else AuthoritativeDatumDocumentRequest.from_dict(request)
        )
        tenant_id = normalized_request.tenant_id
        db_mtime = self._db_mtime_ns()
        global_key = (str(self._db_file.resolve()), tenant_id)
        cached = _GLOBAL_INDEX_CACHE.get(global_key)
        if cached is not None and cached[0] == db_mtime:
            return cached[1]
        with self._connect() as connection:
            fresh_at = self._tables_version(connection, tenant_id)
            snapshot = connection.execute(
                "SELECT updated_at_unix_ms FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if fresh_at is None and snapshot is None:
                result = AuthoritativeDatumDocumentIndexResult(
                    tenant_id=tenant_id,
                    documents=(),
                    readiness_status={"authoritative_catalog": "missing"},
                    warnings=("sql_authoritative_catalog_missing",),
                )
                _remember_index(global_key, db_mtime, result)
                return result
            from_tables = fresh_at is not None
            key: tuple[int, ...] = (
                fresh_at if from_tables else (int(snapshot["updated_at_unix_ms"] or 0),)
            )
            stored = connection.execute(
                "SELECT index_json, updated_at_unix_ms FROM authoritative_catalog_index "
                "WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            entries: list[dict[str, Any]] | None = None
            if stored is not None and int(stored["updated_at_unix_ms"] or 0) == key[0]:
                try:
                    parsed = loads_json(stored["index_json"])
                    if (
                        isinstance(parsed, dict)
                        and parsed.get("format") == _CATALOG_INDEX_FORMAT
                        and isinstance(parsed.get("documents"), list)
                        and tuple(parsed.get("tables_version") or ()) == key
                    ):
                        entries = parsed["documents"]
                except Exception:  # a corrupt projection must not break the read
                    entries = None
            if entries is None:
                if from_tables:
                    catalog = self._assemble_catalog(connection, tenant_id)
                    documents = [d.to_dict() for d in catalog.documents] if catalog else []
                    entries = self._project_catalog_index(connection, tenant_id, documents)
                    self._persist_catalog_index(connection, tenant_id, entries, key, commit=True)
                else:
                    entries = self._rebuild_catalog_index(connection, tenant_id, key)
            entries = [dict(entry) for entry in entries if isinstance(entry, dict)]
            if not from_tables:
                self._apply_index_deltas(connection, tenant_id, entries)
        result = AuthoritativeDatumDocumentIndexResult(
            tenant_id=tenant_id,
            documents=tuple(
                AuthoritativeDatumDocumentSummary.from_dict(entry) for entry in entries
            ),
            readiness_status={"authoritative_catalog": "loaded"},
        )
        _remember_index(global_key, db_mtime, result)
        return result

    def _tables_version(self, connection: Any, tenant_id: str) -> tuple[int, int, int] | None:
        """A version of the tenant's document tables — ``(newest write, semantics rows,
        index rows)`` — or ``None`` when the semantics table holds nothing for the tenant.

        The index's freshness key (2026-09-21/22). A create, append or replace moves the
        newest write; a delete moves no clock, so the counts are part of the key — the
        first cut keyed on the clock alone and a delete left an index the reader could
        not tell from fresh. Four indexed aggregates (see the schema's freshness
        indexes); an artifact's write moves the key too — one spare rebuild, never a
        stale one. Every door stamps the index with the version the tables hold AFTER
        its own writes, read inside its transaction, so no door has to reproduce the
        reader's arithmetic.
        """
        newest, semantics_rows = connection.execute(
            "SELECT MAX(updated_at_unix_ms), COUNT(*) FROM datum_document_semantics "
            "WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if newest is None:
            return None
        created, index_rows = connection.execute(
            "SELECT MAX(created_at), COUNT(*) FROM documents WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        return (int(max(int(newest), int(created or 0))), int(semantics_rows), int(index_rows))

    def read_authoritative_document(
        self, *, tenant_id: str, document_id: str, allow_catalog_fallback: bool = True
    ) -> AuthoritativeDatumDocument | None:
        """ONE document, with its rows, without touching the catalog blob.

        The companion to :meth:`read_document_index`: the index answers "what is
        there", this answers "and what is in this one". Cost is that document's
        own ``canonical_payload_json`` — the median document in the live corpus is
        6,306 bytes — instead of the 138 MB every document costs together.

        Falls back to the catalog for a document the semantics table does not
        carry. That is not hypothetical: the live blob holds
        a client instance's ``lcl``, which has no ``datum_document_semantics``
        row, and returning ``None`` for it would make a document that the index
        lists unopenable.
        """
        token = _as_text(tenant_id).lower()
        document_token = _as_text(document_id)
        if not token or not document_token:
            return None
        with self._connect() as connection:
            # An append RE-KEYS the document, and the store carries the result in one
            # of two shapes: `datum_document_semantics` keyed on the BASE id with the
            # delta holding the extra rows, or keyed on the POST-append id with the
            # rows already folded in. Both exist; resolving through the delta FIRST
            # is correct only for the first, and on the live store five of the six
            # appended documents are the second — so the base lookup missed and every
            # read of them fell through to the 138 MB catalog. That is
            # a client instance's `contacts` and `.job_log` (the ERP's own two
            # documents), `agnet.lcl` (which decides what the instance switcher
            # shows), and `registrar.administrative`.
            #
            # Try the requested id DIRECTLY first. This is correct under both shapes,
            # with no heuristic: under the base-keyed shape the post-append id has no
            # semantics row of its own, so the direct lookup necessarily misses and
            # falls through to the delta below. Under the post-keyed shape it hits a
            # row that is already complete — measured: rows in semantics equals the
            # index's row_count for all four — so the delta must NOT be applied again.
            document = self._read_document(
                connection, tenant_id=token, document_id=document_token
            )
            if document is not None:
                return document
            delta = connection.execute(
                "SELECT base_document_id, rows_json FROM document_row_appends "
                "WHERE tenant_id = ? AND document_id = ?",
                (token, document_token),
            ).fetchone()
            if delta is not None:
                base_id = _as_text(delta["base_document_id"])
                document = self._read_document(
                    connection, tenant_id=token, document_id=base_id
                )
                if document is not None:
                    try:
                        extra = loads_json(delta["rows_json"])
                    except Exception:
                        extra = []
                    return dataclasses.replace(
                        document,
                        document_id=document_token,
                        rows=tuple(document.rows)
                        + tuple(extra if isinstance(extra, list) else ()),
                    )
        if not allow_catalog_fallback:
            # The caller is on a path where materializing the catalog would cost
            # more than the answer is worth (the document table's per-entry
            # recompute). A miss there is a missing field, not a 138 MB read.
            return None
        # Say so. This branch costs ~460 MB of Python objects and seconds of wall
        # clock, and it ran on four hot documents for months without a word — the
        # cost was only ever visible as "the portal is slow". A store where this
        # fires is a store with a document the normalized tables do not carry.
        _log.warning(
            "read_authoritative_document(%s) missed the semantics table; "
            "falling back to a full catalog parse",
            document_token,
        )
        catalog = self.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=token)
        )
        for candidate in catalog.documents:
            if candidate.document_id == document_token:
                return candidate
        return None

    def _rebuild_catalog_index(
        self, connection: Any, tenant_id: str, snapshot_at: tuple[int, ...]
    ) -> list[dict[str, Any]]:
        """Project the blob's metadata and persist it. Costs one full parse, once.

        Persisting from a READ is deliberate AND KEPT: a store written by an older
        build carries no index at all, so this is what lets any store self-heal on
        first read, and the ``updated_at_unix_ms`` equality check is what makes a
        stale projection impossible to serve.

        What changed 2026-08-24: it is no longer the ONLY writer. The four catalog
        write paths now refresh the index too, in their own transaction, from the
        document they already hold — see ``_refresh_index_entry``. The
        original note here argued against that on the grounds that it "has to get
        transaction ordering right four times." True, and the cost of not doing it
        was measured: every write invalidated this projection and none refreshed
        it, so the rebuild landed on whichever READER arrived first, at 543.9 MB
        peak against a 25.5 MB fresh read. Under the health gate's MemoryMax=1200M
        that reader was SIGKILLed mid-rebuild, so nothing persisted and the next
        run rebuilt and died identically — a wedge that reproduced 3/3 and
        presented as `GATE: FAIL` with zero test failures.

        This path is now the FALLBACK, not the steady state.
        """
        row = connection.execute(
            "SELECT payload_json FROM authoritative_catalog_snapshots WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return []
        payload = loads_json(row["payload_json"])
        documents = payload.get("documents") if isinstance(payload, dict) else None
        if not isinstance(documents, list):
            return []
        entries = self._project_catalog_index(connection, tenant_id, documents)
        self._persist_catalog_index(connection, tenant_id, entries, snapshot_at, commit=True)
        return entries

    def _project_catalog_index(
        self, connection: Any, tenant_id: str, documents: list[Any]
    ) -> list[dict[str, Any]]:
        """The projection itself: blob documents -> index entries.

        Split out of ``_rebuild_catalog_index`` so the four WRITE paths can reach it
        with the payload already in hand, and never re-parse the blob they just
        serialized.
        """
        hashes = {
            _as_text(record["document_id"]): (
                _as_text(record["version_hash"]),
                _as_text(record["policy"]),
            )
            for record in connection.execute(
                "SELECT document_id, version_hash, policy FROM datum_document_semantics "
                "WHERE tenant_id = ?",
                (tenant_id,),
            )
        }
        # The archetype registry, from the blob's OWN archetype library (role ==
        # "archetype" in document_metadata — the library rides the same catalog).
        # Built here because this is the one place every document's rows are
        # already in hand: the projection can carry each document's primary
        # archetype without any reader ever paying a full catalog parse for an
        # icon. Measured on the live corpus only 77 of 607 documents DECLARE an
        # archetype in metadata; the other 530 are known only by their shape.
        registry = None
        try:
            from micyte.core.archetypes import registry_for

            library = [
                AuthoritativeDatumDocument.from_dict(entry)
                for entry in documents
                if isinstance(entry, dict)
                and isinstance(entry.get("document_metadata"), dict)
                and _as_text(entry["document_metadata"].get("role")) == "archetype"
            ]
            registry = registry_for(library) if library else None
        except Exception:  # no library, no shape pass — declared metadata still lands
            registry = None
        entries: list[dict[str, Any]] = []
        for entry in documents:
            if not isinstance(entry, dict):
                continue
            document_id = _as_text(entry.get("document_id"))
            if not document_id:
                continue
            rows = entry.get("rows")
            metadata = entry.get("document_metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            archetype = _as_text(metadata.get("archetype")) or _as_text(
                metadata.get("datum_template_archetype"))
            if (
                not archetype
                and registry is not None
                and isinstance(rows, list)
                and 0 < len(rows) <= _INDEX_ARCHETYPE_ROW_BUDGET
            ):
                try:
                    archetype = _as_text(
                        registry.primary_archetype(
                            SimpleNamespace(document_id=document_id, rows=rows)
                        )
                    )
                except Exception:
                    archetype = ""
            version_hash, policy = hashes.get(document_id, ("", ""))
            if not version_hash:
                # No semantics row for this document. That is not hypothetical: the
                # live blob holds a client instance's `lcl`, and a document the
                # snapshot re-keyed no longer matches its semantics row by id.
                #
                # Compute it HERE, where the blob is already parsed, rather than
                # leaving the entry hash-less — a reader that finds no hash has to
                # load the document to compute one, and for a document that is only
                # in the blob that load is the whole 138 MB catalog. Paying it once
                # per catalog write is what keeps that off the render path.
                try:
                    version_hash = _as_text(
                        build_document_version_identity(
                            AuthoritativeDatumDocument.from_dict(entry)
                        ).get("version_hash")
                    )
                    policy = MSS_VERSION_HASH_POLICY
                except Exception:
                    version_hash, policy = "", ""
            entries.append(
                {
                    "document_id": document_id,
                    "source_kind": _as_text(entry.get("source_kind")),
                    "document_name": _as_text(entry.get("document_name")),
                    "relative_path": _as_text(entry.get("relative_path")),
                    "canonical_name": _as_text(entry.get("canonical_name")),
                    "tool_id": _as_text(entry.get("tool_id")),
                    "is_anchor": bool(entry.get("is_anchor")),
                    "row_count": len(rows)
                    if isinstance(rows, list)
                    else int(entry.get("row_count") or 0),
                    "version_hash": version_hash,
                    "version_hash_policy": policy,
                    "archetype": archetype,
                    "warnings": list(entry.get("warnings") or ()),
                }
            )
        return entries

    def _persist_catalog_index(
        self,
        connection: Any,
        tenant_id: str,
        entries: list[dict[str, Any]],
        version: tuple[int, ...] | None,
        *,
        commit: bool,
    ) -> None:
        """Upsert the projection, stamped with the tables' ``version`` (its first element
        in the column, for the reader's cheap check; the whole of it in the envelope).
        A ``None`` version — tables that hold nothing yet — is stamped ``(0, 0, 0)``, a
        version no populated table can have: the empty projection then EXISTS, so the
        doors that follow an empty bulk import edit it in their own transactions rather
        than leaving the first reader to build it (and move the store's mtime under every
        mtime-keyed memo above it).

        ``commit`` is FALSE when a write path calls this: that caller owns the
        transaction and commits the snapshot, the semantics and this index
        together. Committing here would split one catalog write into two, and a
        crash between them would leave an index that claims to describe a snapshot
        that was rolled back — exactly the stale-projection state the
        ``updated_at_unix_ms`` check exists to make unreachable.
        """
        version = tuple(version) if version else (0, 0, 0)
        try:
            connection.execute(
                """
                INSERT INTO authoritative_catalog_index (tenant_id, index_json, updated_at_unix_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    index_json = excluded.index_json,
                    updated_at_unix_ms = excluded.updated_at_unix_ms
                """,
                (
                    tenant_id,
                    dumps_json({
                        "format": _CATALOG_INDEX_FORMAT,
                        "tables_version": list(version),
                        "documents": entries,
                    }),
                    int(version[0]),
                ),
            )
            if commit:
                # `open_sqlite` closes without committing and sqlite3's default
                # isolation level opens an implicit transaction for DML, so an
                # uncommitted upsert on the READ path is silently ROLLED BACK on
                # close — the projection would rebuild on every single read and
                # that path would cost more than the blob it replaces.
                connection.commit()
        except Exception:  # a read-only store still gets a correct answer
            _log.warning("could not persist the catalog index for tenant %s", tenant_id)

    def _refresh_index_entry(
        self, connection: Any, *, tenant_id: str, document: AuthoritativeDatumDocument | None,
        prior_document_id: str = "", remove_ids: set[str] | None = None,
    ) -> None:
        """Refresh ONE document's entry in the persisted index, in the caller's
        transaction — what every door does instead of projecting the whole catalog
        (2026-09-21/22). The stored projection is edited in place: the prior id's
        entry (and any ``remove_ids``) go, the document's entry — when there is one — is
        projected from the document in hand beside the archetype library, so the shape
        pass sees what the whole projection would; the stamp is the tables' version
        after this write, read inside the caller's transaction. A projection that is absent or in an
        older format is left alone: the next read rebuilds it whole. Never commits, so
        the caller's transaction stays one; never raises, so a projection failure cannot
        make a write more fragile.
        """
        try:
            stored = connection.execute(
                "SELECT index_json FROM authoritative_catalog_index WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if stored is None:
                return
            parsed = loads_json(stored["index_json"])
            if not (isinstance(parsed, dict) and parsed.get("format") == _CATALOG_INDEX_FORMAT
                    and isinstance(parsed.get("documents"), list)):
                return
            stale = set(remove_ids or ()) | {_as_text(prior_document_id)}
            if document is not None:
                stale.add(_as_text(document.document_id))
            stale.discard("")
            entries = [e for e in parsed["documents"]
                       if isinstance(e, dict) and _as_text(e.get("document_id")) not in stale]
            if document is not None:
                library = self._archetype_library_dicts(connection, tenant_id)
                projected = self._project_catalog_index(
                    connection, tenant_id, [*library, document.to_dict()])
                fresh = [e for e in projected
                         if _as_text(e.get("document_id")) == _as_text(document.document_id)]
                # A re-key keeps its place, as it does in `documents`.
                at = next((i for i, e in enumerate(parsed["documents"])
                           if isinstance(e, dict) and _as_text(e.get("document_id")) in stale), None)
                if at is None or at > len(entries):
                    entries.extend(fresh)
                else:
                    entries[at:at] = fresh
            self._persist_catalog_index(
                connection, tenant_id, entries, self._tables_version(connection, tenant_id),
                commit=False)
        except Exception:
            _log.warning("could not refresh the index entry for %s; the next read rebuilds",
                         _as_text(getattr(document, "document_id", "")) or sorted(remove_ids or ()),
                         exc_info=True)

    def _archetype_library_dicts(self, connection: Any, tenant_id: str) -> list[dict[str, Any]]:
        """The archetype library's documents, as dicts, for a projection of ONE document:
        the shape pass that names an entry's archetype needs the registry the whole
        projection builds from the documents whose metadata role is `archetype`."""
        from micyte.core.archetypes import ARCHETYPE_SANDBOX

        out: list[dict[str, Any]] = []
        for row in connection.execute(
            "SELECT s.document_id AS document_id, s.canonical_payload_json AS payload "
            "FROM datum_document_semantics AS s JOIN documents AS d "
            "ON d.tenant_id = s.tenant_id AND d.document_id = s.document_id "
            "WHERE s.tenant_id = ? AND d.sandbox = ? AND d.prefix = 'lv'",
            (tenant_id, ARCHETYPE_SANDBOX),
        ):
            try:
                payload = loads_json(row["payload"])
            except Exception:
                continue
            metadata = payload.get("document_metadata") if isinstance(payload, dict) else None
            if isinstance(metadata, dict) and _as_text(metadata.get("role")) == "archetype":
                out.append({"document_id": _as_text(row["document_id"]),
                            "document_metadata": metadata, "rows": payload.get("rows") or [],
                            "source_kind": payload.get("source_kind") or "sandbox_source"})
        return out

    def _apply_index_deltas(
        self, connection: Any, tenant_id: str, entries: list[dict[str, Any]]
    ) -> None:
        """Fold ``document_creates`` / ``document_row_appends`` into the index.

        The same two deltas :func:`_apply_pending_appends` and
        :meth:`_apply_pending_creates` fold into the blob, applied to metadata only.
        An append carries its post-append ``document_id`` — so the new identity is
        READ, never recomputed, which is what keeps this off the hashing path.
        """
        by_id = {_as_text(entry.get("document_id")): entry for entry in entries}
        appends = connection.execute(
            "SELECT base_document_id, document_id, rows_json FROM document_row_appends "
            "WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        for record in appends:
            entry = by_id.get(_as_text(record["base_document_id"]))
            if entry is None:
                # Same rule as the blob path: a delta whose base is absent is
                # DROPPED rather than applied to whatever else is there.
                continue
            try:
                appended = loads_json(record["rows_json"])
            except Exception:
                continue
            entry["row_count"] = int(entry.get("row_count") or 0) + (
                len(appended) if isinstance(appended, list) else 0
            )
            entry["document_id"] = _as_text(record["document_id"])
            # The rows moved, so the recorded hash describes the PRE-append
            # document and must not be published for the new one. Recompute it
            # here rather than leaving it blank: the default document sort is
            # `version_hash`, so a blank sorts to the front and shifts the whole
            # list — a visible reordering of the workbench for every viewer.
            #
            # This is the one genuinely expensive step left, and it is placed here
            # deliberately: `_apply_index_deltas` runs inside the mtime-keyed cache,
            # so it costs one load per catalog write, not one per render. Only
            # documents carrying a pending append pay it at all.
            entry["version_hash"] = ""
            entry["version_hash_policy"] = ""
            document = self._read_document(
                connection, tenant_id=tenant_id, document_id=_as_text(record["base_document_id"])
            )
            if document is not None:
                try:
                    entry["version_hash"] = _as_text(
                        build_document_version_identity(
                            dataclasses.replace(
                                document,
                                document_id=entry["document_id"],
                                rows=tuple(document.rows)
                                + tuple(appended if isinstance(appended, list) else ()),
                            )
                        ).get("version_hash")
                    )
                    entry["version_hash_policy"] = MSS_VERSION_HASH_POLICY
                except Exception:
                    entry["version_hash"] = ""
                    entry["version_hash_policy"] = ""

        held = {_as_text(entry.get("document_id")) for entry in entries}
        creates = connection.execute(
            "SELECT document_id FROM document_creates WHERE tenant_id = ? "
            "ORDER BY created_at_unix_ms",
            (tenant_id,),
        ).fetchall()
        for record in creates:
            document_id = _as_text(record["document_id"])
            if not document_id or document_id in held:
                continue
            document = self._read_document(
                connection, tenant_id=tenant_id, document_id=document_id
            )
            if document is None:
                continue
            entries.append(
                AuthoritativeDatumDocumentSummary.from_document(document).to_dict()
            )
            held.add(document_id)

    def _apply_pending_creates(
        self, connection: Any, tenant_id: str, payload: dict[str, Any]
    ) -> int:
        """Add documents created since the snapshot, assembled from their semantics.

        Per-document and therefore cheap in exactly the case it applies to: a document
        that has just been created is small. A pending create the store can no longer read
        is DROPPED rather than guessed at — the same rule the append deltas follow.
        """
        documents = payload.get("documents")
        if not isinstance(documents, list):
            return 0
        pending = connection.execute(
            "SELECT document_id FROM document_creates WHERE tenant_id = ? ORDER BY created_at_unix_ms",
            (tenant_id,),
        ).fetchall()
        if not pending:
            return 0
        held = {
            _as_text(entry.get("document_id")) for entry in documents if isinstance(entry, dict)
        }
        # (msn, sandbox, name) -> position of the snapshot's entry. A pending create
        # whose id MOVED (`_record_row_append`'s cheap path, an append to a document
        # the snapshot already holds) is that entry's successor, not a second document
        # under its name: it REPLACES the entry. Before 2026-09-10 it was appended beside
        # it, and every name-grouping reader hid the pair — eight `analytics` documents
        # sat twice in the live catalog, the base beside the version that superseded it.
        position: dict[tuple[str, str, str], int] = {}
        for index, entry in enumerate(documents):
            key = _canonical_key(_as_text(entry.get("document_id"))) if isinstance(entry, dict) else None
            if key is not None:
                position.setdefault(key, index)
        added = 0
        for record in pending:
            document_id = _as_text(record["document_id"])
            if not document_id or document_id in held:
                continue
            document = self._read_document(
                connection, tenant_id=tenant_id, document_id=document_id)
            if document is None:
                continue
            key = _canonical_key(document_id)
            at = position.get(key) if key is not None else None
            if at is not None:
                documents[at] = dataclasses.asdict(document)
            else:
                documents.append(dataclasses.asdict(document))
                if key is not None:
                    position[key] = len(documents) - 1
            added += 1
        return added

    def _project_canonical_document_ids(
        self,
        connection: Any,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Phase E4: project canonical document ids over a catalog payload.

        Looks up each ``document_id`` in the ``documents`` table; if the row was
        seeded by the migration script (``legacy_alias`` matching the legacy
        identifier or ``document_id`` itself canonical), the catalog payload is
        rewritten in-place to:

        * carry the canonical identifier on ``documents[].document_id``
        * retain the original legacy identifier under
          ``documents[].document_metadata.legacy_alias`` for one-cycle
          compatibility
        """

        documents = payload.get("documents")
        if not isinstance(documents, list) or not documents:
            return
        cursor = connection.execute(
            "SELECT id, document_id, name, is_anchor, version_hash, created_at "
            "FROM documents WHERE tenant_id = ? ORDER BY created_at DESC, id DESC",
            (tenant_id,),
        )
        semantics_version_by_id = {
            str(row["document_id"]).strip(): _normalize_version_hash_token(row["version_hash"])
            for row in connection.execute(
                "SELECT document_id, version_hash FROM datum_document_semantics WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()
        }
        canonical_by_id: dict[str, dict[str, Any]] = {}
        canonical_by_id_version: dict[tuple[str, str], dict[str, Any]] = {}
        for row in cursor.fetchall():
            doc_id = str(row["document_id"]).strip()
            if not doc_id:
                continue
            normalized_version = _normalize_version_hash_token(row["version_hash"])
            details = {
                "document_id": doc_id,
                "canonical_name": str(row["name"] or "").strip(),
                "is_anchor": bool(row["is_anchor"]),
                "version_hash": normalized_version,
            }
            canonical_by_id_version[(doc_id, normalized_version)] = details
            canonical_by_id.setdefault(doc_id, details)
        if not canonical_by_id:
            return
        for entry in documents:
            if not isinstance(entry, dict):
                continue
            stored_id = str(entry.get("document_id") or "").strip()
            if not stored_id:
                continue
            stored_version = (
                _normalize_version_hash_token(entry.get("version_hash"))
                or semantics_version_by_id.get(stored_id, "")
            )
            metadata = entry.get("document_metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            details = (
                canonical_by_id_version.get((stored_id, stored_version))
                or canonical_by_id.get(stored_id)
            )
            if details is None:
                continue
            projected_id = str(details.get("document_id") or "").strip()
            if projected_id:
                entry["document_id"] = projected_id
            if str(details.get("canonical_name") or "").strip():
                entry["canonical_name"] = str(details.get("canonical_name") or "").strip()
            entry["is_anchor"] = bool(details.get("is_anchor")) or bool(entry.get("is_anchor"))
            entry["document_metadata"] = metadata

    def read_system_resource_workbench(self, request: SystemDatumStoreRequest) -> SystemDatumWorkbenchResult:
        normalized_request = (
            request if isinstance(request, SystemDatumStoreRequest) else SystemDatumStoreRequest.from_dict(request)
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM system_workbench_snapshots WHERE tenant_id = ?",
                (normalized_request.tenant_id,),
            ).fetchone()
            if row is None:
                return SystemDatumWorkbenchResult(
                    tenant_id=normalized_request.tenant_id,
                    rows=(),
                    source_files={},
                    materialization_status={"canonical_source": "missing", "authoritative_catalog": "missing"},
                    warnings=("sql_system_workbench_missing",),
                )
            payload = loads_json(row["payload_json"])
        return _workbench_from_payload(payload)

    def read_publication_tenant_summary(
        self,
        request: PublicationTenantSummaryRequest,
    ) -> PublicationTenantSummaryResult:
        normalized_request = (
            request
            if isinstance(request, PublicationTenantSummaryRequest)
            else PublicationTenantSummaryRequest.from_dict(request)
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM publication_summary_snapshots
                WHERE tenant_id = ? AND tenant_domain = ?
                """,
                (normalized_request.tenant_id, normalized_request.tenant_domain),
            ).fetchone()
        if row is None:
            return PublicationTenantSummaryResult(
                source=None,
                resolution_status={"publication_summary": "missing"},
                warnings=("sql_publication_summary_missing",),
            )
        return PublicationTenantSummaryResult.from_dict(loads_json(row["payload_json"]))

    def document_id_for(
        self, *, tenant_id: str, sandbox: str, name: str, msn_id: str = ""
    ) -> str:
        """One document's id, addressed by ``(msn, sandbox, name)``. ``""`` when absent.

        Six tools carried this query inline as
        ``WHERE tenant_id=? AND sandbox=? AND name=?``, which answers with whichever
        instance the index yields once every instance keeps a sandbox called ``system``.
        Stated once here so they cannot drift about what addresses a document.

        Two rules, the same ones the whole layer uses:

        * the ANCHOR is asked for by its FLAG, because it is called ``anchor`` in most
          sandboxes and ``anthology`` in a system one;
        * an explicit ``msn_id`` wins, else the request's instance scope DISAMBIGUATES —
          it never narrows, so a sandbox only one instance holds still answers without one.
        """
        from micyte.core.document_naming import ANCHOR_DOCUMENT_NAMES

        sandbox_token = _as_text(sandbox)
        name_token = _as_text(name)
        if not sandbox_token or not name_token:
            return ""
        normalized = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        anchor_wanted = name_token in ANCHOR_DOCUMENT_NAMES
        clause = "is_anchor = 1" if anchor_wanted else "name = ?"
        with self._connect() as connection:
            msn_token = _scoped_msn_for(
                connection, tenant_id=normalized.tenant_id,
                sandbox=sandbox_token, msn_id=msn_id,
            )
            params: list = [normalized.tenant_id, sandbox_token]
            if not anchor_wanted:
                params.append(name_token)
            if msn_token:
                params.append(msn_token)
            row = connection.execute(
                "SELECT document_id FROM documents "
                f"WHERE tenant_id=? AND sandbox=? AND {clause}"
                + (" AND msn_id=?" if msn_token else ""),
                tuple(params),
            ).fetchone()
        return row["document_id"] if row else ""

    def read_documents_by_sandbox(
        self, *, tenant_id: str, sandbox: str, msn_id: str = "",
        max_payload_bytes: int = 0,
    ) -> tuple[AuthoritativeDatumDocument, ...]:
        """Every document in one sandbox, assembled per-document — never via the catalog.

        ``read_authoritative_datum_documents`` parses one 138 MB JSON blob holding all 544
        documents, which is ~350 MB warm and the reason a document-level write costs this
        portal ~690 MB (see the delete task's report). But
        ``datum_document_semantics.canonical_payload_json`` already holds each document's
        rows on its own row of a table — the median document is 6 KB — and the ``documents``
        index holds the identity columns the payload omits (``is_anchor``, the name).

        So a surface that needs ONE sandbox reads exactly that sandbox. The archetype
        library is 34 documents totalling well under a megabyte; loading it through the
        catalog would cost 350 MB to look at 0.3% of the store.

        Documents are returned in name order. A row present in the index but missing its
        semantics payload is skipped rather than half-built.

        ``max_payload_bytes`` (0 = no limit) skips documents larger than the budget, using
        SQL ``LENGTH`` so an oversized payload is never read at all. That is what makes a
        whole-sandbox read safe on ``registrar``: 484 documents totalling 48 MB, of which
        ``address_nodes`` alone is 27 MB. A caller that wants the small name tables can ask
        for them without the one document that would blow its budget.
        """
        normalized = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        sandbox_token = _as_text(sandbox)
        if not sandbox_token:
            raise ValueError("sandbox is required")
        # An explicit msn wins; otherwise the request's own instance scope. See
        # micyte.core.instance_scope: threading this through 68 signatures would be
        # the same fact written 68 times, with 68 chances to omit it.
        budget = int(max_payload_bytes or 0)
        documents: list[AuthoritativeDatumDocument] = []
        db_path = str(self._db_file.resolve())
        db_mtime = self._db_mtime_ns()
        with self._connect() as connection:
            msn_token = _scoped_msn_for(
                connection, tenant_id=normalized.tenant_id,
                sandbox=sandbox_token, msn_id=msn_id,
            )
            memo_key = (db_path, normalized.tenant_id, sandbox_token, msn_token, budget)
            remembered = _GLOBAL_SANDBOX_CACHE.get(memo_key)
            if remembered is not None and remembered[0] == db_mtime:
                return remembered[1]
            rows = connection.execute(
                f"""
                SELECT d.document_id AS document_id, d.name AS name, d.is_anchor AS is_anchor,
                       s.canonical_payload_json AS payload
                FROM documents AS d
                LEFT JOIN datum_document_semantics AS s
                       ON s.tenant_id = d.tenant_id AND s.document_id = d.document_id
                WHERE d.tenant_id = ? AND d.sandbox = ?
                      {"AND d.msn_id = ?" if msn_token else ""}
                      {"AND LENGTH(s.canonical_payload_json) <= ?" if budget > 0 else ""}
                ORDER BY d.name
                """,
                tuple(
                    x for x in (normalized.tenant_id, sandbox_token,
                                msn_token or None, budget if budget > 0 else None)
                    if x is not None
                ),
            ).fetchall()
        for row in rows:
            if row["payload"] is None:
                continue
            payload = loads_json(row["payload"])
            documents.append(
                AuthoritativeDatumDocument(
                    document_id=row["document_id"],
                    source_kind=_as_text(payload.get("source_kind")) or "sandbox_source",
                    document_name=f"{row['name']}.json",
                    relative_path=f"{sandbox_token}/{row['name']}.json",
                    canonical_name=row["name"],
                    tool_id=sandbox_token,
                    is_anchor=bool(row["is_anchor"]),
                    rows=tuple(
                        AuthoritativeDatumDocumentRow(
                            datum_address=_as_text(item.get("datum_address")),
                            raw=item.get("raw"),
                        )
                        for item in payload.get("rows", ())
                    ),
                    document_metadata=payload.get("document_metadata") or {},
                )
            )
        result = tuple(documents)
        # Remember only what the store still IS: a write between the stat and the read
        # would park the new content under the old version.
        if self._db_mtime_ns() == db_mtime:
            _remember_sandbox(memo_key, db_mtime, result)
        return result

    def _read_document(
        self, connection: Any, *, tenant_id: str, document_id: str
    ) -> AuthoritativeDatumDocument | None:
        """One assembled document, from its semantics payload.

        Content comes from ``datum_document_semantics``, which is its authority; the
        sandbox and name come from the canonical ID, which carries them. The
        ``documents`` index is consulted only for ``is_anchor``, which lives nowhere else
        — and it is a LEFT JOIN because the index is not populated by
        ``store_authoritative_catalog``, so requiring it here would make a document
        created by a bulk load unreadable by a path that has nothing to do with the index.
        """
        row = connection.execute(
            """
            SELECT s.canonical_payload_json AS payload, d.is_anchor AS is_anchor
            FROM datum_document_semantics AS s
            LEFT JOIN documents AS d
                   ON d.tenant_id = s.tenant_id AND d.document_id = s.document_id
            WHERE s.tenant_id = ? AND s.document_id = ?
            """,
            (tenant_id, document_id),
        ).fetchone()
        if row is None:
            return None
        try:
            parsed = parse_canonical_document_id(document_id)
            sandbox, name = _as_text(parsed.sandbox), _as_text(parsed.name)
        except Exception:
            sandbox, name = "", document_id
        payload = loads_json(row["payload"])
        rows_payload = list(payload.get("rows", ()))
        mode = _bitstream_read_mode()
        if mode in ("1", "verify"):
            decoded = self._rows_from_bitstream(connection, tenant_id=tenant_id, document_id=document_id)
            if decoded is not None:
                if mode == "1":
                    rows_payload = [{"datum_address": a, "raw": r} for a, r in decoded]
                elif ([canonical_json([a, r]) for a, r in decoded]
                      != [canonical_json([_as_text(i.get("datum_address")), i.get("raw")]) for i in rows_payload]):
                    _log.error("bitstream of %s does not decode to its payload rows", document_id)
        given = connection.execute(
            "SELECT document_name, relative_path, source_authority, warnings_json, "
            "anchor_document_name, anchor_document_path, anchor_document_metadata_json, "
            "anchor_rows_json FROM datum_document_provenance WHERE tenant_id = ? AND document_id = ?",
            (tenant_id, document_id),
        ).fetchone()
        try:
            anchor_rows = tuple(loads_json(given["anchor_rows_json"]) or ()) if given else ()
            anchor_metadata = (loads_json(given["anchor_document_metadata_json"]) or None) if given else None
            warnings = tuple(loads_json(given["warnings_json"]) or ()) if given else ()
        except Exception:
            anchor_rows, anchor_metadata, warnings = (), None, ()
        return AuthoritativeDatumDocument(
            document_id=document_id,
            source_kind=_as_text(payload.get("source_kind")) or "sandbox_source",
            document_name=(_as_text(given["document_name"]) if given else "") or f"{name}.json",
            relative_path=(_as_text(given["relative_path"]) if given else "") or f"{sandbox}/{name}.json",
            canonical_name=name,
            tool_id=sandbox,
            source_authority=(_as_text(given["source_authority"]) if given else "") or "authoritative",
            is_anchor=bool(row["is_anchor"]),
            anchor_document_name=_as_text(given["anchor_document_name"]) if given else "",
            anchor_document_path=_as_text(given["anchor_document_path"]) if given else "",
            anchor_document_metadata=anchor_metadata,
            anchor_rows=anchor_rows,
            rows=tuple(
                AuthoritativeDatumDocumentRow(
                    datum_address=_as_text(item.get("datum_address")), raw=item.get("raw")
                )
                for item in rows_payload
            ),
            document_metadata=payload.get("document_metadata") or {},
            warnings=warnings,
        )

    def _rows_from_bitstream(
        self, connection: Any, *, tenant_id: str, document_id: str
    ) -> list[tuple[str, Any]] | None:
        """The document's rows decoded from its `mos.mss_binary_v4` bitstream, or ``None``
        when it has none (never written, or ``deferred`` over the cap)."""
        row = connection.execute(
            "SELECT policy, bitstream FROM datum_document_bitstream WHERE tenant_id = ? AND document_id = ?",
            (tenant_id, document_id),
        ).fetchone()
        if row is None or row["policy"] != MSS_TRANSPORT_POLICY:
            return None
        return decode_rows(unpack_bits(bytes(row["bitstream"])))

    def read_rows_from_bitstream(self, *, tenant_id: str, document_id: str) -> list[tuple[str, Any]] | None:
        """The dual read: ``(datum_address, raw)`` pairs from the bitstream alone."""
        with self._connect() as connection:
            return self._rows_from_bitstream(
                connection, tenant_id=_as_text(tenant_id).lower(), document_id=_as_text(document_id))

    def _archetype_cover(self, *, tenant_id: str, document_id: str, expects_archetype: str):
        """The I9 callback for a write filed under an archetype, or ``None`` for none.

        The writer names the archetype (the symbol is the caller's to supply); the ENGINE
        judges the rows against it. Before 2026-09-17 five write runtimes each read the
        library and called ``Archetype.covers`` themselves, and a sixth writer could skip
        it; now the door does it once and a writer that names an archetype the library
        does not declare is refused by name rather than covered by nothing.
        """
        name = _as_text(expects_archetype)
        if not name:
            return None
        from micyte.core import archetypes as arc
        from micyte.core.datum_ops import archetype_shape as ash
        from micyte.core.datum_ops import field_registry as fr

        sandbox, msn = "", ""
        try:
            parsed = parse_canonical_document_id(_as_text(document_id))
            sandbox, msn = _as_text(parsed.sandbox), _as_text(parsed.msn_id)
        except Exception:
            pass
        library = self.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
        archetype = arc.registry_for(library).get(name)
        if archetype is None:
            raise InvariantRefused([Refusal(
                "I9", "-", f"the archetype library declares no archetype named {name!r}")])
        namespace = fr.namespace_for_sandbox(sandbox, msn_id=msn) if sandbox else ""
        radices = None
        if archetype.has_parent_runs:
            # A parent-bound run judges a field by the radix the ANCHOR backs it with, so
            # the anchor is read — only for such archetypes; a field-named one costs nothing.
            from micyte.core.datum_ops.viewscope_edit import backing_radices

            anchor = next((doc for doc in self.read_documents_by_sandbox(
                tenant_id=tenant_id, sandbox=sandbox, msn_id=msn)
                if getattr(doc, "is_anchor", False)), None)
            radices = backing_radices(anchor) if anchor is not None else {}
        return lambda raw: archetype.covers(ash.row_shape(raw, sandbox=namespace, radices=radices))

    def binary_identity_of(self, *, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        """The dual-written binary identity of one document, or ``None`` when no write
        since 2026-09-17 has touched it (the backfill is `scripts/backfill_binary_identity.py`)."""
        tenant = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id).tenant_id
        with self._connect() as connection:
            row = connection.execute(
                "SELECT policy, mss_hash, datums, dropped_json FROM datum_document_binary "
                "WHERE tenant_id = ? AND document_id = ?",
                (tenant, _as_text(document_id)),
            ).fetchone()
        if row is None:
            return None
        return {"policy": row["policy"], "mss_hash": row["mss_hash"], "datums": int(row["datums"]),
                "dropped": loads_json(row["dropped_json"])}

    def create_document_rows(
        self,
        *,
        tenant_id: str,
        document: AuthoritativeDatumDocument,
        expects_archetype: str = "",
    ) -> dict[str, Any]:
        """Create ONE document without rewriting the catalog blob.

        The sibling of :meth:`append_document_rows`, and needed for the same reason:
        `replace_single_document_efficient` costs ~776 MB whatever the document's size,
        because the cost is the 138 MB blob. Onboarding a new instance creates four
        documents, so standing up one business was ~3 GB of transient allocation.

        Semantics are computed in FULL here, not incrementally: a new document has no
        prior anchor context to compare against, and it is small by definition — the
        incremental path exists for a 41,999-row document, which nothing creates in one
        go.

        Refuses a document that already exists, by id and by ``(msn, sandbox, name)``.
        Two documents under one address is the state the `documents` index cannot
        represent and `_upsert_documents_index` would silently resolve by replacing
        one. The msn is part of the address: four live instances legitimately hold
        ``system/anthology`` side by side, and a (sandbox, name)-only check refused
        the client instance got its own ``oveure/anchor`` because FND already had one — a shared NAME
        is not an address (caught by the C6 roster rehearsal, 2026-08-16).
        """
        tenant = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id).tenant_id
        new_id = _as_text(document.document_id)
        if not new_id:
            raise ValueError("document_id is required")
        if not is_canonical_document_id(new_id) and not self._allow_legacy_writes():
            raise NonCanonicalDocumentIdError(
                f"Refusing to persist non-canonical document id: {new_id!r}")
        sandbox, name, msn = "", _as_text(document.canonical_name), ""
        try:
            parsed = parse_canonical_document_id(new_id)
            sandbox, name = _as_text(parsed.sandbox), _as_text(parsed.name)
            msn = _as_text(parsed.msn_id)
        except Exception:
            pass

        # The engine's document-level invariants (core/mss/invariants.py), judged BEFORE
        # anything is computed or written. Arity (I7) is not judged on a new document: the
        # document's first rows set which convention it keeps.
        refusals = check_rows(
            document.rows, artifact=(new_id.split(".", 1)[0] == "art"), arity=False,
            covers=self._archetype_cover(
                tenant_id=tenant, document_id=new_id, expects_archetype=expects_archetype),
            archetype=_as_text(expects_archetype))
        if refusals:
            raise InvariantRefused(refusals)
        semantics = build_document_semantics(document)
        updated_at = self._clock()
        with self._connect() as connection:
            _refuse_identity_policy_mismatch(
                connection, tenant_id=tenant, policy=semantics["document"]["policy"])
            if connection.execute(
                "SELECT 1 FROM datum_document_semantics WHERE tenant_id=? AND document_id=?",
                (tenant, new_id),
            ).fetchone() is not None:
                raise ValueError(f"{new_id!r} already exists")
            clash = connection.execute(
                "SELECT document_id FROM documents WHERE tenant_id=? AND sandbox=? AND name=?"
                + (" AND msn_id=?" if msn else ""),
                (tenant, sandbox, name, *((msn,) if msn else ())),
            ).fetchone()
            if clash is not None:
                raise ValueError(
                    f"{msn or '?'}/{sandbox}/{name} already exists as "
                    f"{clash['document_id']!r}")

            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                connection.execute(
                    """
                    INSERT INTO datum_document_semantics (
                        tenant_id, document_id, policy, version_hash,
                        canonical_payload_json, updated_at_unix_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant, new_id,
                        semantics["document"]["policy"],
                        semantics["document"]["version_hash"],
                        dumps_json(semantics["document"]["canonical_payload"]),
                        updated_at,
                    ),
                )
                for datum_address, row_semantics in semantics["rows"].items():
                    connection.execute(
                        """
                        INSERT INTO datum_row_semantics (
                            tenant_id, document_id, datum_address, policy,
                            semantic_hash, hyphae_hash, hyphae_chain_json,
                            local_references_json, warnings_json, updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tenant, new_id, datum_address,
                            row_semantics["policy"], row_semantics["semantic_hash"],
                            row_semantics["hyphae_hash"],
                            dumps_json(row_semantics["hyphae_chain"]),
                            dumps_json(row_semantics["local_references"]),
                            dumps_json(row_semantics["warnings"]),
                            updated_at,
                        ),
                    )
                _upsert_documents_index(
                    connection, tenant_id=tenant, document=document, now=updated_at)
                _record_binary_identity(
                    connection, tenant_id=tenant, document_id=new_id, document=document,
                    now=updated_at)
                _record_bitstream(
                    connection, tenant_id=tenant, document_id=new_id, document=document,
                    now=updated_at)
                self._refresh_index_entry(
                    connection, tenant_id=tenant, document=document)
                connection.execute(
                    """
                    INSERT INTO document_creates (tenant_id, document_id, created_at_unix_ms)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tenant_id, document_id) DO UPDATE SET
                        created_at_unix_ms = excluded.created_at_unix_ms
                    """,
                    (tenant, new_id, updated_at),
                )
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
        return {"document_id": new_id, "sandbox": sandbox, "name": name,
                "rows": len(document.rows)}

    def append_document_rows(
        self,
        *,
        tenant_id: str,
        document_id: str,
        rows: Sequence[AuthoritativeDatumDocumentRow],
        expects_archetype: str = "",
    ) -> dict[str, Any]:
        """Append rows to ONE document without rewriting the catalog blob.

        **Why this exists.** Measured on a `VACUUM INTO` copy of the live store, inside an
        `RLIMIT_AS`-capped process:

        =========================================  =========  ==========
        operation                                     time     peak RSS
        =========================================  =========  ==========
        catalog READ alone                            3.1 s     479 MB
        `replace_single_document_efficient`, 2 rows    8.9 s     776 MB
        `replace_single_document_efficient`, 42k rows 32.1 s     890 MB
        the blob rewritten with NO json parsing       0.6 s     421 MB
        **this method, on 41,999 rows**             **~5 s**  **224 MB**
        =========================================  =========  ==========

        against ``MemoryHigh=900M`` on a service that boots at ~800 MB. A **two-row**
        write costs 776 MB — the cost is the 138 MB catalog blob and barely the document,
        which is why splitting a large name table would not have helped. The 421 MB floor
        for rewriting the blob at all says no cleverer patch of it helps either.

        So the catalog is not touched. The delta is recorded in ``document_row_appends``
        and applied by :meth:`read_authoritative_datum_documents` on the way out — the
        catalog stays a SNAPSHOT and the table is what has happened since. That is a
        stated relationship rather than the silent disagreement that had the catalog at 531
        and the ``documents`` index at 510.

        **Incremental semantics, with the precondition CHECKED.** Full
        ``build_document_semantics`` is 17.6 s on this document, almost all of it the
        per-row loop — ``_semantic_context`` is 1.76 s and only **1 of 41,999 rows** has
        any local dependency. So only the appended rows' semantics are computed. That is
        correct exactly when the append leaves ``anchor_context_hash`` alone, because that
        hash feeds every row's hyphae; so the hash is computed before and after and the
        append is REFUSED if it moved. A precondition that is checked is worth more than
        one that is argued.
        """
        from micyte.core.datum_semantics.engine import _semantic_context

        tenant = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id).tenant_id
        prior_id = _as_text(document_id)
        if not prior_id:
            raise ValueError("document_id is required")
        new_rows = tuple(rows)
        if not new_rows:
            raise ValueError("no rows to append")

        with self._connect() as connection:
            document = self._read_document(connection, tenant_id=tenant, document_id=prior_id)
            if document is None:
                raise UnknownPriorDocumentIdError(
                    f"document_id not in the {tenant!r} store: {prior_id!r}"
                )
            held = {row.datum_address for row in document.rows}
            clashes = sorted({row.datum_address for row in new_rows} & held)
            if clashes:
                # An append that lands on an occupied address is an EDIT, and doing it
                # here would edit a row while reporting an append.
                raise ValueError(
                    f"{len(clashes)} datum_address already in the document: {clashes[:3]}"
                )
            if len({row.datum_address for row in new_rows}) != len(new_rows):
                raise ValueError("the appended rows collide with each other")
            # The engine's invariants over the rows being WRITTEN (core/mss/invariants.py):
            # the head names its address, the family matches the arity where this document
            # keeps that convention, the row lands one past the family's highest, the title
            # fits the babelette, and — when the writer names one — the archetype covers it.
            refusals = check_new_rows(
                document.rows, new_rows, artifact=(prior_id.split(".", 1)[0] == "art"),
                covers=self._archetype_cover(
                    tenant_id=tenant, document_id=prior_id, expects_archetype=expects_archetype),
                archetype=_as_text(expects_archetype))
            if refusals:
                raise InvariantRefused(refusals)

            updated = dataclasses.replace(document, rows=(*document.rows, *new_rows))
            semantics = build_document_semantics(updated) if len(updated.rows) <= _FULL_SEMANTICS_ROWS else None
            if semantics is not None:
                _refuse_identity_policy_mismatch(
                    connection, tenant_id=tenant, policy=semantics["document"]["policy"])
            if semantics is None:
                before = _semantic_context(document)["anchor_context_hash"]
                context = _semantic_context(updated)
                if context["anchor_context_hash"] != before:
                    raise ValueError(
                        "the append moves anchor_context_hash, so every row's hyphae "
                        "changes and an incremental append would leave them stale"
                    )
                semantics = _document_semantics_for(
                    updated, context, [row.datum_address for row in new_rows]
                )
            new_id = _reidentified(prior_id, semantics["document"]["version_hash"])
            updated = dataclasses.replace(updated, document_id=new_id)
            updated_at = self._clock()

            prior_temp_store = int(connection.execute("PRAGMA temp_store").fetchone()[0])
            connection.execute("PRAGMA temp_store = MEMORY")
            try:
                # Parent first, then move the children onto it, then drop the old parent:
                # `datum_row_semantics` cascades on delete, so dropping first would take
                # 41,999 rows with it.
                connection.execute(
                    """
                    INSERT INTO datum_document_semantics (
                        tenant_id, document_id, policy, version_hash,
                        canonical_payload_json, updated_at_unix_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant, new_id,
                        semantics["document"]["policy"],
                        semantics["document"]["version_hash"],
                        dumps_json(semantics["document"]["canonical_payload"]),
                        updated_at,
                    ),
                )
                connection.execute(
                    "UPDATE datum_row_semantics SET document_id = ?, updated_at_unix_ms = ? "
                    "WHERE tenant_id = ? AND document_id = ?",
                    (new_id, updated_at, tenant, prior_id),
                )
                for datum_address, row_semantics in semantics["rows"].items():
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO datum_row_semantics (
                            tenant_id, document_id, datum_address, policy,
                            semantic_hash, hyphae_hash, hyphae_chain_json,
                            local_references_json, warnings_json, updated_at_unix_ms
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tenant, new_id, datum_address,
                            row_semantics["policy"],
                            row_semantics["semantic_hash"],
                            row_semantics["hyphae_hash"],
                            dumps_json(row_semantics["hyphae_chain"]),
                            dumps_json(row_semantics["local_references"]),
                            dumps_json(row_semantics["warnings"]),
                            updated_at,
                        ),
                    )
                connection.execute(
                    "DELETE FROM datum_document_semantics WHERE tenant_id = ? AND document_id = ?",
                    (tenant, prior_id),
                )
                _upsert_documents_index(
                    connection, tenant_id=tenant, document=updated,
                    prior_document_id=prior_id, now=updated_at,
                )
                _record_binary_identity(
                    connection, tenant_id=tenant, document_id=new_id, document=updated,
                    prior_document_id=prior_id, now=updated_at)
                _record_bitstream(
                    connection, tenant_id=tenant, document_id=new_id, document=updated,
                    prior_document_id=prior_id, now=updated_at)
                self._refresh_index_entry(
                    connection, tenant_id=tenant, document=updated,
                    prior_document_id=prior_id)
                _record_row_append(
                    connection, tenant_id=tenant, prior_document_id=prior_id,
                    document_id=new_id, rows=new_rows, now=updated_at,
                )
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute(f"PRAGMA temp_store = {prior_temp_store}")
        return {"document_id": new_id, "prior_document_id": prior_id,
                "appended": len(new_rows), "rows": len(updated.rows)}

    def iter_document_rows_by_sandbox(
        self, *, tenant_id: str, sandbox: str, msn_id: str = ""
    ) -> Iterator[tuple[str, str, Any]]:
        """``(document_id, name, raw)`` for every row in a sandbox, one row at a time.

        :meth:`read_documents_by_sandbox` assembles whole documents, which is right for a
        caller that keeps them and wrong for one that FOLDS them. Measured on
        ``registrar`` + ``taxonomy``: assembling costs **+237 MB** peak, because
        ``address_nodes``' 27 MB payload becomes ~42,000 row objects before the first one
        is looked at. Streaming the same rows costs **+68 MB** — the same as today's
        truncated read — and yields every name rather than 14% of them.

        The parse happens in SQLite (``json_each`` over the payload, ``json_extract`` of
        each row's ``raw``), so the whole document is never a Python object graph. Rows
        arrive grouped by document, in name order, which is what lets a caller fold one
        document at a time and commit or discard it before the next begins.

        This is a read of what is stored, not a projection of it: ``raw`` is handed back
        exactly as written, and naming what the cells MEAN stays with the decoder ring
        where it belongs. A reader that keyed on cell positions here would be the
        ``rf.3-1-N`` mistake one layer down.

        ``->`` rather than ``json_extract``: ``json_extract`` UNWRAPS a scalar, so a row
        whose ``raw`` is a bare string comes back as that string rather than as JSON and
        parsing it raises. Live, twelve rows are like that — four each in ``agnet/lcl``,
        two farm instances' ``lcl``, out of 105,811.
        ``->`` always yields JSON text (``'"hi"'``, ``'null'``, ``'[[…]]'``) and NULL only
        when the key is absent, which is the one case that means "no raw here" rather than
        "raw is null". Twelve rows in a hundred thousand is exactly the density that makes
        this the kind of bug a smaller corpus never shows.
        """
        normalized = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        sandbox_token = _as_text(sandbox)
        if not sandbox_token:
            raise ValueError("sandbox is required")
        with self._connect() as connection:
            msn_token = _scoped_msn_for(
                connection, tenant_id=normalized.tenant_id,
                sandbox=sandbox_token, msn_id=msn_id,
            )
            cursor = connection.execute(
                f"""
                SELECT d.document_id AS document_id, d.name AS name,
                       j.value -> '$.raw' AS raw
                FROM documents AS d
                JOIN datum_document_semantics AS s
                       ON s.tenant_id = d.tenant_id AND s.document_id = d.document_id,
                     json_each(s.canonical_payload_json, '$.rows') AS j
                WHERE d.tenant_id = ? AND d.sandbox = ?
                      {"AND d.msn_id = ?" if msn_token else ""}
                ORDER BY d.name
                """,
                (normalized.tenant_id, sandbox_token, msn_token) if msn_token
                else (normalized.tenant_id, sandbox_token),
            )
            for row in cursor:
                raw = row["raw"]
                yield row["document_id"], row["name"], None if raw is None else loads_json(raw)

    def count_document_rows(self, *, tenant_id: str, document_id: str) -> int:
        """How many rows a document holds, WITHOUT reading it.

        ``datum_row_semantics`` carries one row per ``(document, datum_address)`` and is
        indexed by document, so this is a b-tree count. Measured against parsing the
        payload: `address_nodes` answers in **11 ms** here, 105 ms via
        ``json_array_length``, and 5.5 s / 203 MB by actually reading the document — and
        the answer is identical, 41,999, in all three.

        That difference is what lets a caller decide NOT to render a document before
        paying to read it. Deciding afterwards is how a 27 MB refusal still cost 203 MB.
        """
        normalized = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        document_token = _as_text(document_id)
        if not document_token:
            raise ValueError("document_id is required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS n FROM datum_row_semantics
                WHERE tenant_id = ? AND document_id = ?
                """,
                (normalized.tenant_id, document_token),
            ).fetchone()
        return int(row["n"]) if row else 0

    def read_document_version_identity(self, *, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        normalized_request = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        document_token = _as_text(document_id)
        if not document_token:
            raise ValueError("document_id is required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT policy, version_hash, canonical_payload_json
                FROM datum_document_semantics
                WHERE tenant_id = ? AND document_id = ?
                """,
                (normalized_request.tenant_id, document_token),
            ).fetchone()
            if row is None:
                # Post-2026-05-17 reconciliation: every payload is keyed by
                # canonical document_id. The legacy_alias dual-lookup was
                # retired (see docs/contracts/mos_authority_enforcement.md).
                return None
        return {
            "policy": row["policy"],
            "version_hash": row["version_hash"],
            "canonical_payload": loads_json(row["canonical_payload_json"]),
        }

    def read_datum_semantic_identity(
        self,
        *,
        tenant_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any] | None:
        normalized_request = AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        document_token = _as_text(document_id)
        datum_token = _as_text(datum_address)
        if not document_token:
            raise ValueError("document_id is required")
        if not datum_token:
            raise ValueError("datum_address is required")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT policy, semantic_hash, hyphae_hash, hyphae_chain_json, local_references_json, warnings_json
                FROM datum_row_semantics
                WHERE tenant_id = ? AND document_id = ? AND datum_address = ?
                """,
                (normalized_request.tenant_id, document_token, datum_token),
            ).fetchone()
            # Post-2026-05-17 reconciliation: legacy_alias dual-lookup retired.
        if row is None:
            return None
        return {
            "policy": row["policy"],
            "semantic_hash": row["semantic_hash"],
            "hyphae_hash": row["hyphae_hash"],
            "hyphae_chain": loads_json(row["hyphae_chain_json"]),
            "local_references": loads_json(row["local_references_json"]),
            "warnings": loads_json(row["warnings_json"]),
        }

    def _catalog_with_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> tuple[AuthoritativeDatumDocumentCatalogResult, AuthoritativeDatumDocument]:
        catalog = self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
        for document in catalog.documents:
            if document.document_id == _as_text(document_id):
                return catalog, document
        raise ValueError("authoritative_document_missing")

    def _persist_updated_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        updated_document: AuthoritativeDatumDocument,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        catalog = self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
        documents: list[AuthoritativeDatumDocument] = []
        found = False
        for document in catalog.documents:
            if document.document_id == _as_text(document_id):
                documents.append(updated_document)
                found = True
            else:
                documents.append(document)
        if not found:
            raise ValueError("authoritative_document_missing")
        next_catalog = AuthoritativeDatumDocumentCatalogResult(
            tenant_id=catalog.tenant_id,
            documents=tuple(documents),
            source_files=dict(catalog.source_files),
            readiness_status=dict(catalog.readiness_status),
            warnings=tuple(catalog.warnings),
        )
        self.store_authoritative_catalog(next_catalog)
        return self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))

    def replace_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        updated_document: AuthoritativeDatumDocument,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        normalized_document = (
            updated_document
            if isinstance(updated_document, AuthoritativeDatumDocument)
            else AuthoritativeDatumDocument.from_dict(updated_document)
        )
        if normalized_document.document_id != _as_text(document_id):
            raise ValueError("updated_document.document_id must match document_id")
        return self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=normalized_document,
        )

    def delete_authoritative_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> AuthoritativeDatumDocumentCatalogResult:
        """The port's delete: the same door, then the catalog the port declares as its
        result — which ASSEMBLES every document (4.2 s, 666 MB peak on the live corpus,
        measured 2026-09-22). A caller that discards the result calls
        :meth:`delete_single_document_efficient` instead, as the document workbench does.
        """
        self.delete_single_document_efficient(tenant_id=tenant_id, document_id=document_id)
        return self.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))

    def preview_document_insert(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
        raw: Any,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_insert_mutation(document, target_address=target_address, raw=raw)
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_insert(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
        raw: Any,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_insert_mutation(document, target_address=target_address, raw=raw)
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def preview_document_delete(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_delete_mutation(document, target_address=target_address)
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_delete(
        self,
        *,
        tenant_id: str,
        document_id: str,
        target_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_delete_mutation(document, target_address=target_address)
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def preview_document_move(
        self,
        *,
        tenant_id: str,
        document_id: str,
        source_address: str,
        destination_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_move_mutation(
            document,
            source_address=source_address,
            destination_address=destination_address,
        )
        preview["updated_document"] = preview["updated_document"].to_dict()
        return preview

    def apply_document_move(
        self,
        *,
        tenant_id: str,
        document_id: str,
        source_address: str,
        destination_address: str,
    ) -> dict[str, Any]:
        _, document = self._catalog_with_document(tenant_id=tenant_id, document_id=document_id)
        preview = preview_document_move_mutation(
            document,
            source_address=source_address,
            destination_address=destination_address,
        )
        persisted_catalog = self._persist_updated_document(
            tenant_id=tenant_id,
            document_id=document_id,
            updated_document=preview["updated_document"],
        )
        latest_identity = self.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
        preview["updated_document"] = next(
            item.to_dict() for item in persisted_catalog.documents if item.document_id == _as_text(document_id)
        )
        preview["persisted_version_hash"] = latest_identity["version_hash"] if latest_identity else ""
        return preview

    def write_publication_profile_basics(
        self,
        request: PublicationProfileBasicsWriteRequest,
    ) -> PublicationProfileBasicsWriteResult:
        normalized_request = (
            request
            if isinstance(request, PublicationProfileBasicsWriteRequest)
            else PublicationProfileBasicsWriteRequest.from_dict(request)
        )
        current = self.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
            )
        )
        if current.source is None:
            raise ValueError("No SQL-backed publication summary exists for the requested tenant domain.")

        next_source = current.source.to_dict()
        tenant_profile = dict(next_source.get("tenant_profile") or {})
        tenant_profile["title"] = normalized_request.profile_title
        tenant_profile["summary"] = normalized_request.profile_summary
        tenant_profile["contact_email"] = normalized_request.contact_email
        tenant_profile["public_website_url"] = normalized_request.public_website_url
        next_source["tenant_profile"] = tenant_profile

        result = PublicationTenantSummaryResult(
            source=next_source,
            resolution_status=dict(current.resolution_status),
            warnings=tuple(current.warnings),
        )
        self.store_publication_summary(
            result,
            tenant_id=normalized_request.tenant_id,
            tenant_domain=normalized_request.tenant_domain,
        )
        confirmed = self.read_publication_tenant_summary(
            PublicationTenantSummaryRequest(
                tenant_id=normalized_request.tenant_id,
                tenant_domain=normalized_request.tenant_domain,
            )
        )
        if confirmed.source is None:
            raise ValueError("SQL publication profile basics read-after-write confirmation failed.")
        return PublicationProfileBasicsWriteResult(
            source=confirmed.source,
            resolution_status=confirmed.resolution_status,
            warnings=confirmed.warnings,
        )
