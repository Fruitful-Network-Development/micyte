#!/usr/bin/env python3
"""Repair the document-level invariants the audit found, as engine transforms.

Read-only by default: for every document with a finding it prints what
``core/mss/transform`` would do — ``reindex_heads`` for I6 (a head that names the address
the row was moved FROM; 2,114 rows live on 2026-09-17, 2,103 of them in one registrar
document), ``compact`` for I8 (a layer-4 family with a gap; 64 live), and with
``--readdress`` the I7 move (``readdress``) for a document the operator has decided keeps
the arity convention. Nothing is written without ``--apply``, and ``--apply`` wants a
backup.

THE COST, said out loud. A repair rewrites a WHOLE document, and the only door for that is
``replace_single_document_efficient`` — which rewrites the 139 MB tenant catalog blob:
~776 MB of transient allocation on a service that boots at ~800 MB under
``MemoryHigh=900M`` (measured; see the append door's docstring). So ``--apply`` is an
operator's window, not a routine: stop or drain the portal, or run against a ``/srv/tmp``
copy and swap. TASK-2026-09-17-001 (the binary representation in SQL) is what retires
this cost.

    python scripts/repair_mss_invariants.py --db PATH [--sandbox S] [--document NAME]
                                             [--readdress] [--apply --backup | --backup-taken PATH]
"""

from __future__ import annotations

import argparse
import dataclasses
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import open_mos_store
from micyte.core.datum_documents import AuthoritativeDatumDocumentRow
from micyte.core.datum_ops.migrate import mint_canonical_id
from micyte.core.mss import transform as tf
from micyte.core.mss.invariants import InvariantRefused, check_rows

TENANT = "fnd"


def _sandboxes(db: Path, tenant: str) -> list[tuple[str, str]]:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as cx:
        return [(str(r[0] or ""), str(r[1] or "")) for r in cx.execute(
            "SELECT DISTINCT sandbox, msn_id FROM documents WHERE tenant_id=? AND sandbox IS NOT NULL "
            "AND sandbox != '' ORDER BY 1, 2", (tenant,))]


def _has_pending_appends(db: Path, tenant: str, document_id: str) -> bool:
    """Is this id the product of an append the catalog snapshot has not absorbed?

    `append_document_rows` records its rows in `document_row_appends` and leaves the
    catalog blob alone; the read path applies them. A replace names the PRIOR id the
    catalog holds, which for such a document is an older one — so the repair of it
    waits for TASK-2026-09-17-001 rather than guessing the chain here.
    """
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as cx:
        return cx.execute(
            "SELECT 1 FROM document_row_appends WHERE tenant_id=? AND document_id=? LIMIT 1",
            (tenant, document_id)).fetchone() is not None


def _citations(db: Path, tenant: str, document_id: str) -> int:
    """Rows in OTHER documents whose local references cite this document's id."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as cx:
        return int(cx.execute(
            "SELECT COUNT(*) FROM datum_row_semantics WHERE tenant_id=? AND document_id != ? "
            "AND local_references_json LIKE ?", (tenant, document_id, f"%{document_id}%")).fetchone()[0])


def _plan(document, *, readdress: bool):
    rows = [(r.datum_address, r.raw) for r in document.rows]
    artifact = str(document.document_id).split(".", 1)[0] == "art"
    findings = check_rows(rows, artifact=artifact)
    if not findings:
        return None
    steps = []
    current = rows
    wanted = {f.invariant for f in findings}
    verbs = []
    if "I6" in wanted and not artifact:
        verbs.append(tf.reindex_heads)
    if "I8" in wanted:
        verbs.append(tf.compact)
    if readdress and "I7" in wanted:
        verbs.append(tf.readdress)
    for verb in verbs:
        out = verb(current)
        steps.append(out)
        current = out.rows
    remaining = check_rows(current, artifact=artifact, arity=readdress)
    return findings, steps, current, remaining


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--tenant", default=TENANT)
    parser.add_argument("--sandbox", default="")
    parser.add_argument("--document", default="")
    parser.add_argument("--readdress", action="store_true", help="also move rows to the family their arity names (I7)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="store_true", help="take a stamped backup before writing")
    parser.add_argument("--backup-taken", default="", metavar="PATH")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"no store at {args.db}", file=sys.stderr)
        return 2
    store = open_mos_store(args.db)
    planned = 0
    # ONE catalog rewrite for every document repaired, not one per document: the blob is
    # the whole cost (see the module docstring), and `replace_documents_efficient` pays it
    # once for a batch — the rule every bulk MOS write follows.
    replacements: list[tuple[str, Any]] = []
    backed_up = False
    for sandbox, msn in _sandboxes(args.db, args.tenant):
        if args.sandbox and sandbox != args.sandbox:
            continue
        for document in store.read_documents_by_sandbox(tenant_id=args.tenant, sandbox=sandbox, msn_id=msn):
            if args.document and document.canonical_name != args.document:
                continue
            try:
                plan = _plan(document, readdress=args.readdress)
            except InvariantRefused as exc:
                print(f"{sandbox:12} {document.document_id[:70]}\n    REFUSED by the engine: {exc}")
                continue
            if plan is None:
                continue
            findings, steps, rows, remaining = plan
            planned += 1
            print(f"{sandbox:12} {document.document_id[:70]}")
            print(f"    findings: {', '.join(sorted({f.invariant for f in findings}))} ({len(findings)})")
            for step in steps:
                print(f"    {step.note}; {step.moved} addresses moved")
            if remaining:
                print(f"    still open after repair: {', '.join(sorted({f.invariant for f in remaining}))} "
                      f"({len(remaining)}) — I7 needs --readdress and a decision")
            if not args.apply or not steps:
                continue
            if not backed_up:
                if args.backup:
                    from fnd_app.scripts._authority_backup import (
                        backup_authority_store,
                        stamped_backup_path,
                    )
                    taken = stamped_backup_path(args.db, "pre-repair-mss")
                    backup_authority_store(args.db, taken)
                    print(f"    backup: {taken}")
                elif args.backup_taken:
                    if not Path(args.backup_taken).is_file():
                        print(f"    REFUSED: --backup-taken names {args.backup_taken}, which does not exist")
                        return 2
                    print(f"    backup (already taken): {args.backup_taken}")
                else:
                    print("    REFUSED: --apply wants --backup or --backup-taken PATH")
                    return 2
                backed_up = True
            if _has_pending_appends(args.db, args.tenant, document.document_id):
                print("    DEFERRED: this id carries appends the catalog snapshot has not absorbed; "
                      "its repair waits for the binary store (TASK-2026-09-17-001)")
                continue
            cited = _citations(args.db, args.tenant, document.document_id)
            if cited:
                print(f"    REFUSED: {cited} row(s) elsewhere cite this document; re-point them first")
                continue
            rebuilt = tuple(AuthoritativeDatumDocumentRow(datum_address=a, raw=r) for a, r in rows)
            updated, _version = mint_canonical_id(dataclasses.replace(document, rows=rebuilt))
            replacements.append((document.document_id, updated))
            print(f"    queued as {updated.document_id[:70]}")
    print(f"documents with a plan: {planned}" + ("" if args.apply else "  (dry run; --apply writes)"))
    if args.apply and replacements:
        store.replace_documents_efficient(tenant_id=args.tenant, replacements=replacements)
        print(f"written: {len(replacements)} documents in one catalog rewrite")
        again = open_mos_store(args.db)
        missing = [new.document_id for _old, new in replacements
                   if again.read_authoritative_document(tenant_id=args.tenant, document_id=new.document_id) is None]
        if missing:
            print(f"WRITE FAILED: {len(missing)} repaired documents are not readable back: {missing[:3]}")
            return 1
        print("read back: every repaired document is readable under its new id")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
