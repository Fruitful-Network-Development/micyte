#!/usr/bin/env python3
"""Write ``micyte/tools/_packages.lock.json``: every package this build ships, with a
digest of what it DECLARES — tools, requirements (and their archetype pins), writes, port
declarations and fills, app sandbox, features — beside its version.

The rule this enforces (TASK-2026-09-16-002 P3/P4): **a package whose declarations change
bumps its version.** An instance decides whether to update by comparing versions
(``check_updates``); a change that kept its version would be invisible to every instance
and applied to none. So this script REFUSES to record a changed digest under an unchanged
version, and ``fnd_app/tests/unit/test_gadget_compatibility.py`` refuses a build whose
packages disagree with the lock. The workflow is: change the declaration, bump the
version, run this, commit all three together.

    python scripts/lock_packages.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOCK_PATH = REPO_ROOT / "micyte" / "tools" / "_packages.lock.json"
SCHEMA = "micyte.packages.lock.v1"
# The digest is DEFINED where the manifest that crosses the network is written and read
# (`micyte/tools/_packages_manifest.py`), so what this lock pins is what an instance
# computes over what it pulled. One definition.
from micyte.tools._packages_manifest import declaration_digest


def current() -> dict[str, dict[str, str]]:
    from micyte.tools._packages import catalogue

    return {p.package_id: {"version": p.version, "digest": declaration_digest(p)}
            for p in sorted(catalogue(), key=lambda p: p.package_id)}


def read_lock() -> dict[str, dict[str, str]]:
    if not LOCK_PATH.exists():
        return {}
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"{LOCK_PATH.name} is not a {SCHEMA} file")
    return dict(payload.get("packages") or {})


def unbumped(now: dict[str, dict[str, str]], locked: dict[str, dict[str, str]]) -> list[str]:
    """Packages whose declarations changed while their version did not."""
    return sorted(
        package_id for package_id, entry in now.items()
        if package_id in locked
        and locked[package_id]["digest"] != entry["digest"]
        and locked[package_id]["version"] == entry["version"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare only; write nothing")
    args = parser.parse_args(argv)
    now, locked = current(), read_lock()
    stale = unbumped(now, locked)
    if stale:
        for package_id in stale:
            print(f"REFUSED: {package_id} changed its declarations and kept version "
                  f"{now[package_id]['version']}; bump it first")
        return 1
    if args.check:
        drift = sorted(p for p in now if locked.get(p) != now[p])
        if drift:
            print("lock is behind the build for: " + ", ".join(drift))
            return 1
        print(f"{len(now)} packages match the lock")
        return 0
    LOCK_PATH.write_text(json.dumps(
        {"schema": SCHEMA, "packages": now}, indent=2) + "\n", encoding="utf-8")
    print(f"{len(now)} packages locked into {LOCK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
