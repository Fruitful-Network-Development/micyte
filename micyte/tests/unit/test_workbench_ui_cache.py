from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
from micyte.tools.workbench_ui.service import (
    _GLOBAL_SURFACE_CACHE,
    WorkbenchUiReadService,
)


class WorkbenchUiProjectionCacheTests(unittest.TestCase):
    """Stage 1a: read_surface memoizes the projection keyed by a catalog
    content fingerprint + normalized view params, returns independent copies
    on hit, and invalidates when the catalog changes."""

    def _bootstrap(self, db_file: Path) -> None:
        with TemporaryDirectory() as src:
            root = Path(src)
            data_dir = root / "data"
            public_dir = root / "public"
            (data_dir / "system").mkdir(parents=True)
            public_dir.mkdir(parents=True)
            (data_dir / "system" / "anthology.json").write_text(
                json.dumps(
                    {
                        "1-1-1": [["1-1-1", "~", "ROOT"], ["root"]],
                        "1-1-2": [["1-1-2", "1-1-1", "CHILD"], ["child"]],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            SqliteSystemDatumStoreAdapter(db_file).bootstrap_from_filesystem(
                data_dir=data_dir,
                public_dir=public_dir,
                tenant_id="fnd",
            )

    def test_identical_reads_hit_cache_and_return_independent_copies(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "authority.sqlite3"
            self._bootstrap(db_file)
            _GLOBAL_SURFACE_CACHE.clear()
            service = WorkbenchUiReadService(db_file)
            query = {"document": "system:anthology"}

            first = service.read_surface(
                portal_instance_id="fnd", portal_domain="d", surface_query=query
            )
            self.assertEqual(len(_GLOBAL_SURFACE_CACHE), 1, "no directive overlay -> cached")

            second = service.read_surface(
                portal_instance_id="fnd", portal_domain="d", surface_query=dict(query)
            )
            self.assertEqual(first["document_id"], second["document_id"])
            self.assertEqual(first["row_count"], second["row_count"])
            # The runtime mutates the returned model in place; a hit must hand
            # back an object that is NOT the cached instance.
            self.assertIsNot(first, second)

            # Mutating a returned model must not poison the cache for later reads.
            second["surface_payload"]["title"] = "MUTATED"
            third = service.read_surface(
                portal_instance_id="fnd", portal_domain="d", surface_query=dict(query)
            )
            self.assertNotEqual(third["surface_payload"].get("title"), "MUTATED")

    def test_cache_invalidates_when_catalog_fingerprint_changes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "authority.sqlite3"
            self._bootstrap(db_file)
            _GLOBAL_SURFACE_CACHE.clear()
            service = WorkbenchUiReadService(db_file)

            service.read_surface(
                portal_instance_id="fnd", portal_domain="d", surface_query={}
            )
            cached_keys_before = set(_GLOBAL_SURFACE_CACHE)
            self.assertTrue(cached_keys_before)

            # Re-bootstrap with an extra row -> the document content (and thus
            # the version_hash embedded in its id) changes, so the fingerprint
            # in the cache key differs and the prior entry is not reused.
            with TemporaryDirectory() as src:
                root = Path(src)
                data_dir = root / "data"
                public_dir = root / "public"
                (data_dir / "system").mkdir(parents=True)
                public_dir.mkdir(parents=True)
                (data_dir / "system" / "anthology.json").write_text(
                    json.dumps(
                        {
                            "1-1-1": [["1-1-1", "~", "ROOT"], ["root"]],
                            "1-1-2": [["1-1-2", "1-1-1", "CHILD"], ["child"]],
                            "1-1-3": [["1-1-3", "1-1-1", "CHILD"], ["child-2"]],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                SqliteSystemDatumStoreAdapter(db_file).bootstrap_from_filesystem(
                    data_dir=data_dir,
                    public_dir=public_dir,
                    tenant_id="fnd",
                )

            fresh = service.read_surface(
                portal_instance_id="fnd", portal_domain="d", surface_query={}
            )
            # The fresh read must reflect the added row (3, not the stale 2),
            # proving the content fingerprint invalidated the prior entry even
            # though the legacy document id ("system:anthology") is unchanged.
            self.assertEqual(fresh["row_count"], 3)
            # A new cache key (new fingerprint) was added; the stale key is not
            # served for the changed catalog.
            self.assertTrue(set(_GLOBAL_SURFACE_CACHE) - cached_keys_before)


if __name__ == "__main__":
    unittest.main()
