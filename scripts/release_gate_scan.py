#!/usr/bin/env python3
"""Release-gate scan for the MiCyte doc set (Phase 5).

Two jobs, both a precondition for making the repo public:

1. CLASSIFY every file under ``docs/`` as public (ships with MiCyte) or private
   (FND's own domain — audits, personal notes, internal plans, and the FND-domain
   contract clusters). Private files must not exist in the published tree.

2. SCAN the public set for sensitive literals that must never leave the building:
   live registrar msns, absolute ``/srv`` paths, Route53 hosted-zone ids, the AWS
   account id / ARNs. A hit in a public file fails the gate.

Exit non-zero if any private file is still present OR any public file carries a
sensitive literal, so this can gate a release in CI. ``--list-private`` prints the
private paths (one per line) for a caller that wants to ``git rm`` them.

This exists because the repo once went public with the whole private tree in it;
this is the check that makes that a red build instead of an incident.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --- classification (path-based; the boundary is domain, not folder) ----------

# Whole private subtrees: FND's internal working docs, not part of the software.
PRIVATE_DIR_PREFIXES = (
    "docs/audits/",
    "docs/personal_notes/",
    "docs/plans/",
)

# Private FND-domain clusters that live INSIDE the otherwise-public contracts dir.
# Matched on the basename stem so a new cts_gis_* / fnd_* file is caught too.
PRIVATE_CONTRACT_PATTERNS = (
    re.compile(r"(^|/)cts_gis[_-]"),
    re.compile(r"(^|/)fnd_csm[_-]"),
    re.compile(r"(^|/)fnd_dcm[_-]"),
    re.compile(r"(^|/)fnd_newsletter[_-]"),
    re.compile(r"(^|/)analytics_event_schema\b"),
    re.compile(r"(^|/)agro_erp_workbench_contract\b"),
)


def is_private(rel_path: str) -> bool:
    if any(rel_path.startswith(p) for p in PRIVATE_DIR_PREFIXES):
        return True
    if rel_path.startswith("docs/contracts/"):
        return any(p.search(rel_path) for p in PRIVATE_CONTRACT_PATTERNS)
    return False


# --- sensitive literals (only ever checked against PUBLIC files) --------------

SENSITIVE = {
    "live_msn": re.compile(r"\b3-2-3-17-(?:66|77)(?:-\d+)+\b"),
    "srv_path": re.compile(r"/srv/[a-z]"),
    "route53_zone": re.compile(r"\bZ[A-Z0-9]{12,}\b"),
    "aws_account": re.compile(r"\b0659\d{8}\b"),
    "aws_arn": re.compile(r"\barn:aws:"),
}


def tracked_docs(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "docs"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def scan_literals(repo: Path, rel_path: str) -> list[tuple[int, str, str]]:
    """(line_no, kind, snippet) for every sensitive literal in a text file."""
    path = repo / rel_path
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []  # binary/unreadable public asset — nothing to leak as text
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for kind, pat in SENSITIVE.items():
            m = pat.search(line)
            if m:
                hits.append((lineno, kind, line.strip()[:120]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--list-private", action="store_true",
                    help="print private tracked doc paths, one per line, and exit 0")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    files = tracked_docs(repo)
    private = [f for f in files if is_private(f)]
    public = [f for f in files if not is_private(f)]

    if args.list_private:
        print("\n".join(private))
        return 0

    leaks: list[tuple[str, int, str, str]] = []
    for f in public:
        for lineno, kind, snippet in scan_literals(repo, f):
            leaks.append((f, lineno, kind, snippet))

    print(f"docs tracked : {len(files)}")
    print(f"  public     : {len(public)}")
    print(f"  private    : {len(private)}")
    if private:
        print("\nPRIVATE still present (must be removed before publish):")
        for f in private:
            print(f"  - {f}")
    if leaks:
        print(f"\nSENSITIVE LITERALS in public docs ({len(leaks)}):")
        for f, lineno, kind, snippet in leaks:
            print(f"  {f}:{lineno} [{kind}] {snippet}")

    ok = not private and not leaks
    print("\nGATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
