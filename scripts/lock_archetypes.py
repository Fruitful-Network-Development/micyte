#!/usr/bin/env python3
"""Write ``micyte/tools/_archetypes.lock.json``: the archetype library this build is
developed against, as ``{archetype name: document hash}``.

An archetype is a datum document and its id carries its content hash, so the library
already versions itself; this file pins WHICH versions the packages in this build were
written for. ``micyte/tools/_packages.py`` fills every document requirement's
``archetype_hash`` from it (operator decision D4, 2026-09-17), and an instance whose
library holds a different hash is refused an install or update of that package —
``micyte.ports.tool_package.unmet_requirements`` — before the difference can break it.

Read-only against the store; the only write is the lockfile. Re-run it deliberately when
the library changes (a re-mint), and the packages' pins move with it in the same commit
— which is the point: a package and the archetypes it expects change together, on the
record, or the test that compares them fails.

    python scripts/lock_archetypes.py --db PATH [--out micyte/tools/_archetypes.lock.json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "micyte" / "tools" / "_archetypes.lock.json"
SANDBOX = "archetype"


def read_library(db: Path, *, tenant: str) -> dict[str, str]:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as cx:
        rows = cx.execute(
            "SELECT name, document_id FROM documents WHERE tenant_id=? AND sandbox=? "
            "AND is_anchor=0 ORDER BY name", (tenant, SANDBOX)).fetchall()
    return {str(name): str(document_id).rsplit(".", 1)[-1] for name, document_id in rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--tenant", default="fnd")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"no store at {args.db}", file=sys.stderr)
        return 2
    library = read_library(args.db, tenant=args.tenant)
    if not library:
        print("the store holds no archetype library; nothing to lock", file=sys.stderr)
        return 1
    payload = {
        "schema": "micyte.archetypes.lock.v1",
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sandbox": SANDBOX,
        "count": len(library),
        "archetypes": dict(sorted(library.items())),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{len(library)} archetypes locked into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
