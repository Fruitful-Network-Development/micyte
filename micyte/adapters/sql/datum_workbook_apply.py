"""Store-bound executor for a planned datum-workbook migration.

This is the ONLY SQL-aware piece of the workbook pipeline: the pure planner
(:mod:`micyte.core.datum_ops.migrate`) produces a :class:`MigrationPlan`;
this module loads a sandbox into a :class:`Workbook`, backs up the DB, writes the
touched sheets in dependency order, updates the ``documents`` index, and verifies —
restoring from the backup if verification fails.

Atomicity caveat: ``replace_single_document_efficient`` opens its own connection
per call, so a multi-doc cascade is not a single transaction. The mitigation is the
mandatory pre-write backup + post-write verify + restore-on-failure, and the standing
discipline of applying in a quiet window (mirrors the ingest scripts).

That mitigation is the whole safety story for a half-applied cascade, and until
2026-08-26 all three of its file operations were ``shutil.copy2`` — which cannot back up
a WAL-mode store, and cannot restore one at all. See
:mod:`micyte.adapters.sql._store_snapshot` for what each of them was actually doing. This
module is reached from a live portal route (``apply_workbook`` in the datum workbench), so
the restore arms were reachable by an operator, on the path taken only after an apply had
already failed.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from micyte.adapters.sql._store_snapshot import consistent_copy, restore_from_snapshot
from micyte.core.datum_ops import Workbook, check_step
from micyte.core.datum_ops.migrate import MigrationPlan
from micyte.core.document_naming import (
    ANCHOR_DOCUMENT_NAMES,
    document_in_sandbox,
    parse_canonical_document_id,
)
from micyte.core.instances import sandbox_msn_id
from micyte.core.references import (
    ReferenceGrant,
    external_nodes_for,
    own_instance_nodes,
    parse_contract,
)
from micyte.core.structures.samras.codec import decode_canonical_bitstream
from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest

from .datum_store import SqliteSystemDatumStoreAdapter
from .mos import open_mos_store

_log = logging.getLogger(__name__)


class WorkbookApplyError(RuntimeError):
    """Raised when a workbook migration fails to write or verify."""


# Cross-instance references are resolved from the contract store beside the
# authority db — see micyte.core.references. This replaces
# `REFERENCE_SANDBOXES = ("taxonomy",)`, the stand-in that granted EVERY sandbox
# the taxonomy's nodes with nothing having declared it, and that carried no owner
# msn so it could not tell one instance's `txa` from another's. The declaration it
# stood in for was never missing: `contract-<owner>.<counterparty>.json` has been
# on disk since April, and config.json registers it.
CONTRACTS_DIRNAME = "contracts"


def contracts_dir_for(authority_db: Path | str) -> Path:
    """The contract store beside the authority db (`<private>/contracts/`)."""
    return Path(authority_db).parent / CONTRACTS_DIRNAME


def read_reference_grants(contracts_dir: Path | str | None) -> list[ReferenceGrant]:
    """Every declared cross-instance grant. Missing store -> no grants."""
    if contracts_dir is None:
        return []
    root = Path(contracts_dir)
    if not root.is_dir():
        return []
    grants: list[ReferenceGrant] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        grant = parse_contract(payload)
        if grant is not None:
            grants.append(grant)
    return grants


def _external_defined_nodes(documents, *, sandbox: str, contracts_dir: Path | str | None) -> frozenset[str]:
    """Node addresses `sandbox`'s instance is DECLARED to be able to reference.

    Resolved from the contract store, per instance. This was
    `REFERENCE_SANDBOXES = ("taxonomy",)` — a global hardcode that granted every
    sandbox the taxonomy's nodes whether or not anything had said it could, and
    that carried no owner msn, so it could not distinguish one instance's `txa`
    from another's. The live FND->farm contract already declares the real thing.
    """
    documents = list(documents)
    consumer_msn = sandbox_msn_id(documents, sandbox)
    if not consumer_msn:
        return frozenset()
    # Two sources, and only the second one is contractual: an instance may always
    # reference its OWN other sandboxes, and a contract is what lets it reference
    # someone else's. Omitting the first made FND's `agnet` sandbox unable to resolve
    # FND's own `taxonomy` nodes while its counterparty the farm could — see
    # `own_instance_nodes`.
    return own_instance_nodes(
        documents, msn_id=consumer_msn, exclude_sandbox=sandbox
    ) | external_nodes_for(
        documents, read_reference_grants(contracts_dir), consumer_msn_id=consumer_msn
    )


def load_workbook(
    store: SqliteSystemDatumStoreAdapter,
    *,
    tenant_id: str,
    sandbox: str,
    msn_id: str = "",
    contracts_dir: Path | str | None = None,
) -> Workbook:
    """Load every document of one sandbox into a Workbook keyed by document name.

    Sheets are this sandbox's documents only — the workbook is still the unit of
    edit, and a referenced sandbox is never written through it. Sandboxes this
    instance is DECLARED to reference (``contracts_dir``) contribute only their
    defined node addresses, so the rule check can tell a real dangling ref from a
    legitimate cross-instance one.

    ``msn_id`` scopes the sheets to ONE instance's copy of the sandbox. A 2026-07
    tripwire in ``test_instances.py`` named this function as the reason a per-instance
    ``system`` sandbox could not ship: selecting sheets by the dot-bounded substring
    matches across msns, so two instances' documents would land in one workbook and be
    written back through it. Omitting it keeps the old behaviour, which is still right
    for a sandbox only one instance can hold.

    ``contracts_dir`` defaults to the store beside the authority db. Passing it
    explicitly is for tests and for a store whose contracts live elsewhere.
    """
    catalog = store.read_authoritative_datum_documents(AuthoritativeDatumDocumentRequest(tenant_id=tenant_id))
    sheets = {
        d.document_id.split(".")[3]: d
        for d in catalog.documents
        if document_in_sandbox(d.document_id, sandbox, msn_id=msn_id)
    }
    if not sheets:
        raise WorkbookApplyError(f"no documents found for sandbox {sandbox!r}")
    if contracts_dir is None and store.db_file is not None:
        contracts_dir = contracts_dir_for(store.db_file)
    # Cross-instance grants live in a directory BESIDE the authority db. If the db
    # was relocated/copied without it, grants resolve to none and every legitimate
    # cross-instance reference is (correctly, fail-closed) reported as dangling —
    # which reads as a baffling pile of errors. Surface the real cause once.
    if contracts_dir is not None and not Path(contracts_dir).is_dir():
        _log.warning(
            "cross-instance grant store %s is absent; a workbook apply will treat "
            "every declared cross-instance reference as dangling. If this authority "
            "db was relocated, bring its sibling contracts/ directory with it.",
            contracts_dir,
        )
    return Workbook(
        sandbox=sandbox,
        sheets=sheets,
        external_nodes=_external_defined_nodes(
            catalog.documents, sandbox=sandbox, contracts_dir=contracts_dir
        ),
    )


def _upsert_documents_index(
    authority_db: Path,
    *,
    tenant_id: str,
    document_id: str,
    version_hash: str,
    is_anchor: bool,
    prior_document_id: str | None = None,
) -> None:
    """Upsert the documents-index row, keyed by tenant/msn/sandbox/name.

    The msn is part of the key because it is part of the document id: a sandbox
    token identifies a scope only WITHIN an instance. Today no two instances share
    one, so this changes nothing — a save re-keys the same row either way, since a
    save changes content (and so the hash) but never the msn. It matters the moment
    two instances do share a token (each instance's own `system`, say), where
    keying on the token alone would delete the other instance's row and leave this
    one duplicated.

    ``prior_document_id`` is for the one write that moves the KEY rather than the
    value: a rename. Every other caller changes a document's hash while its name
    stays put, so deleting on the new key is enough to replace the row. A rename
    changes the name, so the old key survives untouched and the index ends up
    holding both — the document listed twice, once under an id that no longer
    resolves. Passing the prior id drops that row in the same transaction.
    """
    parsed = parse_canonical_document_id(document_id)
    now = int(time.time() * 1000)
    conn = sqlite3.connect(authority_db)
    try:
        if prior_document_id and prior_document_id != document_id:
            prior = parse_canonical_document_id(prior_document_id)
            conn.execute(
                "DELETE FROM documents WHERE tenant_id=? AND msn_id=? AND sandbox=? AND name=?",
                (tenant_id, prior.msn_id, prior.sandbox, prior.name),
            )
        conn.execute(
            "DELETE FROM documents WHERE tenant_id=? AND msn_id=? AND sandbox=? AND name=?",
            (tenant_id, parsed.msn_id, parsed.sandbox, parsed.name),
        )
        conn.execute(
            "INSERT INTO documents (tenant_id, document_id, prefix, msn_id, sandbox, name, "
            "version_hash, is_anchor, origin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', ?)",
            (tenant_id, document_id, parsed.prefix, parsed.msn_id, parsed.sandbox, parsed.name,
             f"sha256:{version_hash}", 1 if is_anchor else 0, now),
        )
        conn.commit()
    finally:
        conn.close()


def _upsert_documents_index_batch(
    authority_db: Path,
    *,
    tenant_id: str,
    entries: Sequence[tuple[str, str, str, bool]],
) -> None:
    """Re-key SEVERAL documents-index rows at once. ``(document_id, version_hash,
    prior_document_id, is_anchor)``.

    **Every delete happens before every insert**, and that ordering is the whole point.
    The index is keyed by NAME, so applying :func:`_upsert_documents_index` in a loop lets
    one rename delete the row another just wrote: renaming ``note_1-1-4 -> note_1-1-4-1``
    while ``note_1-1-4-1 -> note_1-1-4-1-1`` moves out of the way makes the second call
    delete the target key the first had already claimed, and the document vanishes from
    the index while remaining perfectly correct in the catalog. That is a shift by one —
    the commonest restructure there is.

    Ordering the calls instead would work only until two renames swapped names, which the
    catalog side handles natively. Deleting first handles both.
    """
    now = int(time.time() * 1000)
    conn = sqlite3.connect(authority_db)
    try:
        for document_id, _version_hash, prior_document_id, _is_anchor in entries:
            for key in filter(None, (prior_document_id, document_id)):
                parsed = parse_canonical_document_id(key)
                conn.execute(
                    "DELETE FROM documents WHERE tenant_id=? AND msn_id=? AND sandbox=? "
                    "AND name=?",
                    (tenant_id, parsed.msn_id, parsed.sandbox, parsed.name),
                )
        for document_id, version_hash, _prior, is_anchor in entries:
            parsed = parse_canonical_document_id(document_id)
            conn.execute(
                "INSERT INTO documents (tenant_id, document_id, prefix, msn_id, sandbox, "
                "name, version_hash, is_anchor, origin, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', ?)",
                (tenant_id, document_id, parsed.prefix, parsed.msn_id, parsed.sandbox,
                 parsed.name, f"sha256:{version_hash}", 1 if is_anchor else 0, now),
            )
        conn.commit()
    finally:
        conn.close()


def _plan_msn_id(plan: MigrationPlan) -> str:
    """Whose sandbox this plan is about, read off its own document ids.

    Derived rather than carried, so it cannot disagree with what the plan actually
    touches. A canonical id is ``lv.<msn>.<sandbox>.<name>.<hash>`` and a workbook holds
    ONE instance's documents by construction, so the first touched id answers it. Returns
    ``""`` for a plan whose ids are not canonical, which reads as "unscoped" — the prior
    behaviour, and still right for a sandbox only one instance holds.
    """
    for touched in plan.touched.values():
        parts = str(getattr(touched.new_document, "document_id", "")).split(".")
        if len(parts) > 4:
            return parts[1]
    return ""


def _verify(authority_db: Path, plan: MigrationPlan, *, tenant_id: str) -> list[str]:
    """Re-read with a fresh adapter and assert the plan's invariants."""
    store = open_mos_store(authority_db)
    # Scoped to the instance the plan touches. Unscoped, a sandbox name four instances
    # hold loads all four into one workbook, and this verify then compared a plan built
    # from one farm's `lcl` against another instance's — reporting 21 rows where 27 were
    # planned, and restoring from backup on a write that had actually succeeded.
    wb = load_workbook(store, tenant_id=tenant_id, sandbox=plan.sandbox,
                       msn_id=_plan_msn_id(plan))
    failures: list[str] = []

    for name, expected in plan.expectations.get("row_counts", {}).items():
        actual = len(wb.sheet(name).rows) if name in wb.sheets else -1
        if actual != expected:
            failures.append(f"{name} rows={actual} expected {expected}")

    # The anchor by whichever reserved name it carries: `anchor` in most sandboxes and
    # `anthology` in a system one. Asking only for `anchor` skipped the SAMRAS check
    # entirely in exactly the sandboxes this migration now runs against.
    anchor_sheet = next((n for n in sorted(ANCHOR_DOCUMENT_NAMES) if n in wb.sheets), "")
    if anchor_sheet:
        anchor_rows = {r.datum_address: r for r in wb.sheet(anchor_sheet).rows}
        for addr, expected in plan.expectations.get("samras", {}).items():
            row = anchor_rows.get(addr)
            if row is None:
                failures.append(f"anchor {addr} missing")
                continue
            actual = len(decode_canonical_bitstream(str(row.raw[0][2])).addresses)
            if actual != expected:
                failures.append(f"{addr} decoded {actual} nodes, expected {expected}")

    report = check_step(wb)
    if not report.ok:
        failures.extend(f"rule:{h}" for h in report.hard[:10])

    # the touched docs must be persisted under their new ids
    for name, ts in plan.touched.items():
        if name in wb.sheets and wb.sheet(name).document_id != ts.new_document.document_id:
            failures.append(f"{name} id {wb.sheet(name).document_id} != planned {ts.new_document.document_id}")
    return failures


def _restore(backup_path: Path | None, authority_db: Path) -> str:
    """Put the store back, and return the phrase that says what actually happened.

    The old code raised ``"apply failed (...); restored from backup"`` from a branch that
    restored only ``if backup_path is not None``. Called with ``backup=False`` — which the
    signature allows — it reported a restore it had not performed, on the one message an
    operator reads to decide whether the store is safe to touch. Three states, three
    phrases, and the caller interpolates whichever is true.

    A failure to restore is reported as part of the phrase rather than swallowed or
    allowed to replace the original error: the operator needs both the reason the apply
    failed AND the fact that the rollback did not work, and losing either one of those to
    the other is how a half-applied cascade gets left in place.
    """
    if backup_path is None:
        return "NOT restored — this apply was asked to take no backup"
    try:
        restore_from_snapshot(backup_path, authority_db)
    except Exception as restore_exc:  # broad ON PURPOSE — reported, never swallowed
        _log.error("restore from %s failed: %s", backup_path, restore_exc)
        return (
            f"RESTORE ALSO FAILED ({restore_exc}) — the store may be half-applied; "
            f"the backup is at {backup_path}"
        )
    return f"restored from {backup_path}"


def execute_migration(
    authority_db: Path | str,
    plan: MigrationPlan,
    *,
    tenant_id: str = "fnd",
    backup: bool = True,
    backup_suffix: str = "",
) -> dict[str, Any]:
    """Apply a planned migration to the live DB: backup → write → index → verify.

    Returns a summary dict. On a verify failure (and ``backup=True``) the DB is
    restored from the backup and :class:`WorkbookApplyError` is raised.
    """
    authority_db = Path(authority_db)
    if not authority_db.exists():
        raise WorkbookApplyError(f"authority db missing: {authority_db}")
    if not plan.touched:
        return {"status": "noop", "written": [], "backup": None}

    backup_path: Path | None = None
    if backup:
        stamp = backup_suffix or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        backup_path = authority_db.with_name(authority_db.name + f".pre-workbook-{stamp}.bak")
        if backup_path.exists():
            raise WorkbookApplyError(f"backup target already exists: {backup_path}")
        # NOT copy2: this store runs in WAL mode, and a file copy omits every transaction
        # since the last checkpoint while still passing integrity_check.
        consistent_copy(authority_db, backup_path)

    store = open_mos_store(authority_db)
    written: list[str] = []
    try:
        for name in plan.write_order:
            ts = plan.touched[name]
            store.replace_single_document_efficient(
                tenant_id=tenant_id, prior_document_id=ts.prior_id or None, updated_document=ts.new_document
            )
            _upsert_documents_index(
                authority_db,
                tenant_id=tenant_id,
                document_id=ts.new_document.document_id,
                version_hash=ts.new_hash,
                is_anchor=ts.new_document.is_anchor,
            )
            written.append(name)
        failures = _verify(authority_db, plan, tenant_id=tenant_id)
    except Exception as exc:
        restored = _restore(backup_path, authority_db)
        raise WorkbookApplyError(f"apply failed ({exc}); {restored}") from exc

    if failures:
        restored = _restore(backup_path, authority_db)
        raise WorkbookApplyError(
            f"post-write verify FAILED; {restored}:\n  " + "\n  ".join(failures)
        )

    return {
        "status": "applied",
        "written": written,
        "backup": str(backup_path) if backup_path else None,
        "document_ids": {name: ts.new_document.document_id for name, ts in plan.touched.items()},
    }
