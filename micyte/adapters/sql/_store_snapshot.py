"""Take and restore a snapshot of a WAL-mode store, through SQLite rather than the filesystem.

The capability half of what `fnd_app/scripts/_authority_backup.py` documents at length.
It lived there alone until 2026-08-26, which put it out of reach of the one caller that
needed it most: :mod:`micyte.adapters.sql.datum_workbook_apply` is in the public package
and cannot import from `fnd_app`, so it used ``shutil.copy2`` — for the backup AND for
both restore arms.

## Why `copy2` cannot back this store up

In WAL mode the main database file is only brought up to date at a checkpoint. Committed
transactions live in the ``-wal`` sidecar until then, and ``copy2`` copies the main file
alone, so a copy taken while the WAL is hot silently omits every transaction since the
last checkpoint. The result is not visibly broken — ``PRAGMA integrity_check`` returns
``ok``, because every page that IS present is internally consistent, and the tables are
simply not there.

## Why the RESTORE was worse than the backup

A bad backup fails when you try to use it. A bad restore fails while you are already
using it, and this one is reached only on a path where an apply has ALREADY failed:

    except Exception as exc:
        shutil.copy2(backup_path, authority_db)      # <- the recovery

Copying a file over a live WAL-mode database leaves the newer ``-wal`` and ``-shm``
sidecars sitting beside the older main file it just wrote. SQLite opens that pair and
replays the WAL on top — frames written against a different page history — and what comes
out is neither the backup nor the state before the restore. `copy2` is also not atomic, so
it can tear pages rather than merely omitting them.

The applier's own module docstring is what makes this load-bearing. It states the
non-atomicity of a multi-document cascade and then names the mitigation: *"the mandatory
pre-write backup + post-write verify + restore-on-failure"*. The entire safety story for
a partially-applied migration is the restore, and the restore was the one call that could
not perform it.

## What replaces it

``VACUUM INTO`` for the snapshot: it reads through a single read transaction, WAL
included, and writes a complete defragmented database. It works from a read-only
connection, so it is safe against a live store without stopping the portal.

``Connection.backup`` for the restore: page-by-page through the SQLite engine, which
takes the proper locks and leaves the destination's WAL coherent instead of stale beside
it. A ``wal_checkpoint(TRUNCATE)`` afterwards empties the sidecar so nothing from the
abandoned attempt can be replayed.

Both raise rather than falling back to a file copy. A silently-degraded copy is the exact
failure this module exists to prevent, so a caller that cannot get a good one should stop
before it starts writing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["SnapshotError", "consistent_copy", "restore_from_snapshot"]


class SnapshotError(RuntimeError):
    """A snapshot could not be taken, or could not be proved good."""


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "select name from sqlite_master where type='table'")}


def consistent_copy(db: Path, dest: Path) -> Path:
    """Copy `db` to `dest` as a transactionally consistent snapshot. NO naming rule.

    Retention is a deployment policy and lives with the deployment:
    `fnd_app.scripts._authority_backup.backup_authority_store` wraps this with the one
    rule that a RETAINED backup's filename must carry a stamp the retention ranker can
    read. A caller that wants a WAL-safe copy without wanting a retained backup wants
    this, which is a different job and says so.
    """
    db = Path(db)
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(
            f"{dest} already exists; VACUUM INTO will not overwrite a snapshot.")
    dest.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        expected = _table_names(source)
        # Single quotes doubled: the path is ours, but the failure mode if it ever
        # weren't is a broken snapshot, and this is the line that would cause it.
        source.execute("vacuum into '{}'".format(str(dest).replace("'", "''")))
    finally:
        source.close()

    # A snapshot nobody opened is a snapshot nobody knows is good. This is the check that
    # `copy2` passes while missing every table, so it asserts the TABLE SET too and not
    # just the integrity verdict.
    check = sqlite3.connect(f"file:{dest}?immutable=1", uri=True)
    try:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
        got = _table_names(check)
    finally:
        check.close()
    if verdict != "ok":
        raise SnapshotError(f"snapshot {dest} failed integrity_check: {verdict}")
    if got != expected:
        raise SnapshotError(
            f"snapshot {dest} is missing {sorted(expected - got)}; refusing to call it good.")
    return dest


def restore_from_snapshot(snapshot: Path, live: Path) -> None:
    """Put `snapshot`'s contents back into `live`, through SQLite.

    Never a file copy. See the module docstring: overwriting the main file leaves the
    newer `-wal` beside the older pages it just wrote, and SQLite replays it.

    The destination keeps its identity — same file, same inode, same journal mode — so
    open handles and the sidecars stay coherent. The TRUNCATE checkpoint at the end
    empties the WAL, which is what guarantees no frame from the abandoned attempt can be
    replayed on top of the restored pages.
    """
    snapshot = Path(snapshot)
    live = Path(live)
    if not snapshot.exists():
        raise SnapshotError(f"snapshot missing, cannot restore: {snapshot}")

    source = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(live))
        try:
            source.backup(target)
            target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target.commit()
        finally:
            target.close()
    finally:
        source.close()
