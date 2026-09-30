"""The module-level catalog cache must not grow without bound.

`_GLOBAL_CATALOG_CACHE` is keyed `(resolved_db_path, tenant_id)` and had no bound at all.
In production that is invisible — one store, one tenant, one entry, revalidated by mtime.
In any process that opens more than one store it was a leak of a whole catalog per store,
and a test process is exactly that: it mints a temp store per test and deletes it in
teardown, so every test installed a permanent entry under a key nothing could ever
produce again. At the live store's size that is ~290 MiB per test, which is what
OOM-killed `test_portal_workbench_modes` on a 3.8 GB box.

These tests use tiny fabricated stores, so they check the *rule* rather than the size.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import datum_store as ds
from micyte.adapters.sql._sqlite import connect_sqlite
from micyte.adapters.sql.datum_store import SqliteSystemDatumStoreAdapter
from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest


def _tiny_store(path: Path, tenant: str = "fnd") -> Path:
    """The smallest store `read_authoritative_datum_documents` will answer from.

    The schema comes from `connect_sqlite`, which applies the canonical DDL — hand-rolling
    the two tables produces a store the adapter then refuses to open.
    """
    connect_sqlite(path).close()
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO authoritative_catalog_snapshots "
            "(tenant_id, payload_json, updated_at_unix_ms) VALUES (?, ?, 0)",
            (tenant, json.dumps({"tenant_id": tenant, "documents": [], "source_files": {}})),
        )
    connection.close()
    return path


def _read(db: Path, tenant: str = "fnd"):
    return SqliteSystemDatumStoreAdapter(db).read_authoritative_datum_documents(
        AuthoritativeDatumDocumentRequest(tenant_id=tenant)
    )


class CatalogCacheBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="catalog_cache_bounds_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self._dir, ignore_errors=True))
        self._saved = dict(ds._GLOBAL_CATALOG_CACHE)
        ds._GLOBAL_CATALOG_CACHE.clear()
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        ds._GLOBAL_CATALOG_CACHE.clear()
        ds._GLOBAL_CATALOG_CACHE.update(self._saved)

    def _store(self, name: str) -> Path:
        return _tiny_store(self._dir / f"{name}.sqlite3")

    # --- the rule that fits the key ------------------------------------

    def test_an_entry_for_a_deleted_store_is_dropped(self) -> None:
        # The key IS the path. Once the path is gone the entry can never be hit again,
        # so keeping it is pure retention — this is the leak the workbench tests hit.
        gone = self._store("gone")
        _read(gone)
        self.assertEqual(len(ds._GLOBAL_CATALOG_CACHE), 1)

        gone.unlink()
        survivor = self._store("survivor")
        _read(survivor)

        keys = set(ds._GLOBAL_CATALOG_CACHE)
        self.assertEqual(len(keys), 1, f"the dead key should be gone, got {keys}")
        self.assertEqual({k[0] for k in keys}, {str(survivor.resolve())})

    def test_many_deleted_stores_leave_nothing_behind(self) -> None:
        # The shape of a test run: a fresh store per test, each deleted after use.
        for index in range(12):
            db = self._store(f"ephemeral_{index}")
            _read(db)
            db.unlink()
            self.assertLessEqual(
                len(ds._GLOBAL_CATALOG_CACHE),
                ds._GLOBAL_CATALOG_CACHE_MAX,
                "cache grew past its bound while churning stores",
            )
        # One live store now; every dead key should be evicted by the next insert.
        live = self._store("live")
        _read(live)
        self.assertEqual({k[0] for k in ds._GLOBAL_CATALOG_CACHE}, {str(live.resolve())})

    # --- the backstop ---------------------------------------------------

    def test_the_cache_is_capped_even_when_every_store_still_exists(self) -> None:
        stores = [self._store(f"live_{index}") for index in range(ds._GLOBAL_CATALOG_CACHE_MAX + 3)]
        for db in stores:
            _read(db)
        self.assertLessEqual(len(ds._GLOBAL_CATALOG_CACHE), ds._GLOBAL_CATALOG_CACHE_MAX)
        # The most recent read is what a caller is most likely to want next, and is the
        # one entry eviction must never take.
        self.assertIn(
            (str(stores[-1].resolve()), "fnd"),
            ds._GLOBAL_CATALOG_CACHE,
            "the just-remembered entry was evicted",
        )

    # --- what must NOT have changed -------------------------------------

    def test_a_cached_catalog_is_still_served_and_still_revalidated_by_mtime(self) -> None:
        db = self._store("stable")
        first = _read(db)
        self.assertIs(_read(db), first, "a second read should be served from the cache")

        # Invalidation is by the main file's mtime, so move it directly. (An external
        # write would NOT move it: this store runs in WAL mode and a committed
        # transaction sits in the -wal sidecar until a checkpoint. Writes through the
        # adapter invalidate explicitly via _invalidate_catalog, so that window is not
        # reachable in-process — but it is why this test touches the file rather than
        # writing a row.)
        stat = db.stat()
        os.utime(db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        refreshed = _read(db)
        self.assertIsNot(refreshed, first, "a changed store must not serve the stale catalog")

    def test_eviction_does_not_leak_into_the_per_instance_cache(self) -> None:
        # The per-instance cache is checked before the global one. Evicting a global
        # entry must not resurrect a stale per-instance one, or a bounded cache would
        # have bought a correctness bug.
        db = self._store("instance_scoped")
        adapter = SqliteSystemDatumStoreAdapter(db)
        request = AuthoritativeDatumDocumentRequest(tenant_id="fnd")
        first = adapter.read_authoritative_datum_documents(request)

        for index in range(ds._GLOBAL_CATALOG_CACHE_MAX + 2):
            _read(self._store(f"pressure_{index}"))
        self.assertNotIn((str(db.resolve()), "fnd"), ds._GLOBAL_CATALOG_CACHE)

        stat = db.stat()
        os.utime(db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        self.assertIsNot(
            adapter.read_authoritative_datum_documents(request),
            first,
            "the per-instance cache served a catalog its store had moved past",
        )


if __name__ == "__main__":
    unittest.main()
