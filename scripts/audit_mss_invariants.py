#!/usr/bin/env python3
"""Count, per sandbox and per invariant, how many stored rows violate the MSS engine's
document-level invariants (I6–I8, I10; ``docs/contracts/mss_engine_invariants.md``).

READ-ONLY, and cheap on purpose: it reads each document's rows from
``datum_document_semantics.canonical_payload_json`` — one document at a time, never the
139 MB tenant catalog blob (a catalog read alone is 479 MB of RSS on the live host, which
is the number that decides how an audit may be run there). Opens the store with
``mode=ro`` so a typo cannot turn a count into a write.

Why it exists: the write door refuses the rows being WRITTEN, and a door that judged a
whole document would refuse every append to a document whose OLD rows already violate a
rule — which blocks the repair. So the old violations are counted here, and the door is
armed once these counts are the expected ones (the 2026-06-01 cutover audit's 31 rows, the
blanks, and whatever this finds).

    python scripts/audit_mss_invariants.py --db /path/to/mos_authority.sqlite3 [--tenant fnd]
                                           [--per-document] [--limit N]

Exit 0 always — a count is a finding, not a failure. I9 (archetype coverage) is not
audited here: which archetype a document was filed under is a fact the writer knew and
the store does not record.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.mss.invariants import DOCUMENT_INVARIANTS, check_rows


def _rows(payload_json: str) -> list[tuple[str, object]]:
    payload = json.loads(payload_json)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    out: list[tuple[str, object]] = []
    for row in rows or ():
        if isinstance(row, dict):
            out.append((str(row.get("datum_address") or ""), row.get("raw")))
    return out


def audit(db: Path, *, tenant: str, per_document: bool, limit: int) -> int:
    uri = f"file:{db}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    query = (
        "SELECT s.document_id, d.sandbox, d.msn_id, d.prefix, s.canonical_payload_json "
        "FROM datum_document_semantics s LEFT JOIN documents d "
        "ON d.tenant_id = s.tenant_id AND d.document_id = s.document_id "
        "WHERE s.tenant_id = ? ORDER BY d.sandbox, s.document_id"
    )
    by_sandbox: dict[str, Counter] = defaultdict(Counter)
    documents = 0
    rows_seen = 0
    offenders: list[tuple[str, str, int]] = []
    for record in connection.execute(query, (tenant,)):
        if limit and documents >= limit:
            break
        documents += 1
        rows = _rows(record["canonical_payload_json"] or "{}")
        rows_seen += len(rows)
        refusals = check_rows(rows, artifact=(str(record["prefix"] or "") == "art"))
        if not refusals:
            continue
        sandbox = str(record["sandbox"] or record["prefix"] or "?")
        for refusal in refusals:
            by_sandbox[sandbox][refusal.invariant] += 1
        offenders.append((sandbox, str(record["document_id"]), len(refusals)))
        if per_document:
            print(f"{sandbox:12} {record['document_id'][:80]}")
            for refusal in refusals[:12]:
                print(f"    {refusal}")
            if len(refusals) > 12:
                print(f"    … {len(refusals) - 12} more")
    connection.close()

    ids = [i.id for i in DOCUMENT_INVARIANTS if i.id != "I9"]
    print(f"documents {documents}  rows {rows_seen}  documents with findings {len(offenders)}")
    print("sandbox      " + "".join(f"{i:>7}" for i in ids))
    total: Counter = Counter()
    for sandbox in sorted(by_sandbox):
        counts = by_sandbox[sandbox]
        total.update(counts)
        print(f"{sandbox:12} " + "".join(f"{counts.get(i, 0):>7}" for i in ids))
    print(f"{'TOTAL':12} " + "".join(f"{total.get(i, 0):>7}" for i in ids))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--tenant", default="fnd")
    parser.add_argument("--per-document", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"no store at {args.db}", file=sys.stderr)
        return 2
    return audit(args.db, tenant=args.tenant, per_document=args.per_document, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
