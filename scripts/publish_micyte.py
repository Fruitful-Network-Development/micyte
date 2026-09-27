#!/usr/bin/env python3
"""Cut the public MiCyte tree from this one, gate it, build the wheel — and, with
``--apply``, tag and release it (``docs/standards/release_and_versioning.md``, D5).

Dry run by default. Every step prints what it did; nothing leaves this host without
``--apply``.

1. The version is ``micyte.__version__``. Refuses when the public repository already has
   the tag ``v<version>``: bump first, in the same commit as the CHANGELOG section.
2. Exports the PUBLIC tree into ``<out>/repo`` — a clone of the public repository when
   the network allows, else a fresh ``git init`` — replacing everything but ``.git``:
   ``micyte/`` (no caches), the public ``docs/`` (the release gate's own classification),
   ``LICENSE``, ``README.md``, ``CHANGELOG.md``, ``pyproject.toml`` and the public scripts.
3. Runs ``scripts/release_gate_scan.py`` against the export: a private document present or
   a sensitive literal in a public file is a refused cut (``--skip-gate`` exists for an
   incident and says so out loud).
4. Builds the wheel (``python -m build --wheel``) into ``<out>/dist``.
5. ``--apply``: commits ``MiCyte <version>``, tags ``v<version>``, pushes, and creates the
   GitHub release with the CHANGELOG section as notes and the wheel attached.

    python scripts/publish_micyte.py [--out /srv/tmp/micyte-publish] [--apply] [--skip-gate]
    python scripts/publish_micyte.py --rehearse      # what CI runs on every push
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PUBLIC_REPO = "Fruitful-Network-Development/micyte"
PUBLIC_REPO_URL = f"git@github.com:{PUBLIC_REPO}.git"
DEFAULT_OUT = Path("/srv/tmp/micyte-publish")

#: What the public tree is made of. `docs/` is filtered by the gate's own classification
#: so the two cannot disagree about what is private.
TOP_LEVEL_FILES = ("LICENSE", "README.md", "CHANGELOG.md", "pyproject.toml", ".gitignore")
PUBLIC_SCRIPTS = (
    "release_gate_scan.py", "lock_archetypes.py", "lock_packages.py",
    "audit_mss_invariants.py", "repair_mss_invariants.py", "publish_micyte.py",
)
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def _gate_module():
    spec = importlib.util.spec_from_file_location("release_gate_scan", REPO_ROOT / "scripts" / "release_gate_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, check=check, capture_output=True, text=True)


def version() -> str:
    import micyte

    return micyte.__version__


def public_tag_exists(tag: str) -> bool | None:
    """True/False from GitHub, ``None`` when GitHub cannot be asked (offline dry run)."""
    try:
        out = _run(["gh", "release", "list", "-R", PUBLIC_REPO, "--json", "tagName", "--limit", "100"])
    except (OSError, subprocess.CalledProcessError):
        return None
    return f'"{tag}"' in out.stdout


def _copy_tree(source: Path, target: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(source).parts):
            continue
        if path.is_file():
            dest = target / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            count += 1
    return count


def export(out: Path, *, clone: bool = True) -> Path:
    """Lay the public tree out under ``out/repo`` and return it."""
    repo = out / "repo"
    if repo.exists():
        shutil.rmtree(repo)
    out.mkdir(parents=True, exist_ok=True)
    cloned = False
    if clone:
        try:
            _run(["git", "clone", "--quiet", "--depth", "1", PUBLIC_REPO_URL, str(repo)])
            cloned = True
        except (OSError, subprocess.CalledProcessError):
            cloned = False
    if not cloned:
        repo.mkdir(parents=True)
        _run(["git", "init", "--quiet", str(repo)])
    for entry in list(repo.iterdir()):
        if entry.name == ".git":
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    gate = _gate_module()
    files = _copy_tree(REPO_ROOT / "micyte", repo / "micyte")
    for rel in gate.tracked_docs(REPO_ROOT):
        if gate.is_private(rel):
            continue
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dest)
        files += 1
    for name in TOP_LEVEL_FILES:
        if (REPO_ROOT / name).exists():
            shutil.copy2(REPO_ROOT / name, repo / name)
            files += 1
    (repo / "scripts").mkdir(exist_ok=True)
    for name in PUBLIC_SCRIPTS:
        shutil.copy2(REPO_ROOT / "scripts" / name, repo / "scripts" / name)
        files += 1
    _run(["git", "add", "-A"], cwd=repo)
    print(f"exported {files} files into {repo} ({'clone' if cloned else 'fresh repository'})")
    return repo


def gate(repo: Path) -> bool:
    result = _run([sys.executable, str(repo / "scripts" / "release_gate_scan.py"), "--repo", str(repo)], check=False)
    sys.stdout.write(result.stdout)
    return result.returncode == 0


def build_wheel(repo: Path, out: Path) -> Path:
    dist = out / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(repo)])
    wheel = next(dist.glob("micyte-*.whl"))
    print(f"built {wheel.name}")
    return wheel


def changelog_section(version_text: str) -> str:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(version_text)} — [^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no released section for {version_text}; write it first")
    return match.group(1).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--no-clone", action="store_true", help="export into a fresh repository (offline)")
    parser.add_argument("--get-page", type=Path, default=None,
                        help="micyte.com's get.html; the cut refuses when it does not offer this version")
    parser.add_argument("--rehearse", action="store_true",
                        help="export, gate and build only — the tag may already exist (CI, and a local check)")
    args = parser.parse_args(argv)

    tag = f"v{version()}"
    if args.rehearse:
        args.no_clone = True
        print(f"rehearsal of {version()}: export, gate, wheel; the tag is not checked and nothing is tagged")
    else:
        exists = public_tag_exists(tag)
        if exists:
            print(f"REFUSED: {PUBLIC_REPO} already has {tag}; bump micyte/__init__.py first")
            return 2
        print(f"version {version()} ({'tag free' if exists is False else 'GitHub not asked'})")
    notes = changelog_section(version())
    if args.get_page is not None:
        page = args.get_page.read_text(encoding="utf-8")
        offered = sorted(set(re.findall(r"MiCyte (\d+\.\d+\.\d+)", page)))
        if offered != [version()] or f"releases/tag/{tag}" not in page:
            print(f"REFUSED: {args.get_page} offers {offered} and links "
                  f"{'the tag' if f'releases/tag/{tag}' in page else 'another tag'}; the package is {version()}")
            return 2
        print(f"{args.get_page.name} offers {version()}")
    repo = export(args.out, clone=not args.no_clone)
    if args.skip_gate:
        print("!! RELEASE GATE SKIPPED (--skip-gate) — cutting UNGATED")
    elif not gate(repo):
        print("REFUSED: the release gate is red on the export")
        return 1
    wheel = build_wheel(repo, args.out)
    if not args.apply:
        print(f"dry run: {repo} is the tree, {wheel} is the wheel; --apply tags {tag} and releases")
        return 0
    _run(["git", "commit", "--quiet", "-m", f"MiCyte {version()}"], cwd=repo)
    _run(["git", "tag", tag], cwd=repo)
    _run(["git", "push", "--quiet", "origin", "HEAD:main", "--tags"], cwd=repo)
    notes_file = args.out / f"notes-{tag}.md"
    notes_file.write_text(notes, encoding="utf-8")
    _run(["gh", "release", "create", tag, str(wheel), "-R", PUBLIC_REPO,
          "--title", f"MiCyte {version()}", "--notes-file", str(notes_file)])
    print(f"released {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
