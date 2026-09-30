from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_semantics import build_document_version_identity
from micyte.core.mss.datum_identity import compute_mss_hash, derive_hyphae_chain
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)


def _doc(
    rows: list[tuple[str, object]],
    *,
    document_id: str = "test:doc",
    source_kind: str = "system_anthology",
    metadata: dict | None = None,
) -> AuthoritativeDatumDocument:
    return AuthoritativeDatumDocument(
        document_id=document_id,
        source_kind=source_kind,
        document_name="test.json",
        relative_path="test/test.json",
        document_metadata=metadata or {},
        rows=tuple(AuthoritativeDatumDocumentRow(datum_address=addr, raw=raw) for addr, raw in rows),
    )


class TestComputeMssHash(unittest.TestCase):
    def test_matches_sql_adapter_single_row(self) -> None:
        doc = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["time-ordinal-position"]])])
        core_result = compute_mss_hash(doc)
        sql_result = build_document_version_identity(doc)
        self.assertEqual(core_result["version_hash"], sql_result["version_hash"])
        self.assertEqual(core_result["policy"], sql_result["policy"])

    def test_matches_sql_adapter_multi_row(self) -> None:
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("0-0-2", [["0-0-2", "~", "0-0-0"], ["space"]]),
            ("1-1-1", [["1-1-1", "0-0-1", "100"], ["first"]]),
            ("2-0-1", [["2-0-1", "~", "1-1-1"], ["binding"]]),
        ])
        core_result = compute_mss_hash(doc)
        sql_result = build_document_version_identity(doc)
        self.assertEqual(core_result["version_hash"], sql_result["version_hash"])

    def test_deterministic(self) -> None:
        doc = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["x"]])])
        h1 = compute_mss_hash(doc)["version_hash"]
        h2 = compute_mss_hash(doc)["version_hash"]
        self.assertEqual(h1, h2)

    def test_different_content_produces_different_hash(self) -> None:
        doc_a = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["alpha"]])])
        doc_b = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["beta"]])])
        self.assertNotEqual(
            compute_mss_hash(doc_a)["version_hash"],
            compute_mss_hash(doc_b)["version_hash"],
        )

    def test_hash_prefixed_sha256(self) -> None:
        doc = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["x"]])])
        result = compute_mss_hash(doc)
        self.assertTrue(result["version_hash"].startswith("sha256:"))
        self.assertEqual(len(result["version_hash"]), len("sha256:") + 64)

    def test_policy_field(self) -> None:
        doc = _doc([("0-0-1", None)])
        result = compute_mss_hash(doc)
        self.assertEqual(result["policy"], "mos.mss_sha256_v1")


class TestDeriveHyphaeChain(unittest.TestCase):
    def test_no_rudi_returns_empty(self) -> None:
        doc = _doc([("1-1-1", [["1-1-1", "~", "0"], ["x"]])])
        self.assertEqual(derive_hyphae_chain(doc, "1-1-1"), [])

    def test_single_rudi_reference(self) -> None:
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("1-1-1", [["1-1-1", "0-0-1", "5"], ["val"]]),
        ])
        self.assertEqual(derive_hyphae_chain(doc, "1-1-1"), ["0-0-1"])

    def test_chain_includes_all_positions_up_to_max(self) -> None:
        # datum 1-1-1 only directly references 0-0-3 but chain must include 0-0-1 and 0-0-2
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("0-0-2", [["0-0-2", "~", "0-0-0"], ["space"]]),
            ("0-0-3", [["0-0-3", "~", "0-0-0"], ["nominal"]]),
            ("1-1-1", [["1-1-1", "0-0-3", "5"], ["val"]]),
        ])
        self.assertEqual(derive_hyphae_chain(doc, "1-1-1"), ["0-0-1", "0-0-2", "0-0-3"])

    def test_transitive_rudi_discovery(self) -> None:
        # 1-1-1 → 0-0-2 → 0-0-1; chain = [0-0-1, 0-0-2]
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("0-0-2", [["0-0-2", "0-0-1", "0"], ["space"]]),
            ("1-1-1", [["1-1-1", "0-0-2", "5"], ["val"]]),
        ])
        self.assertEqual(derive_hyphae_chain(doc, "1-1-1"), ["0-0-1", "0-0-2"])

    def test_only_rudi_datums_returned(self) -> None:
        # chain must not include non-rudi datums even if in closure
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("1-1-1", [["1-1-1", "0-0-1", "10"], ["mid"]]),
            ("2-0-1", [["2-0-1", "~", "1-1-1"], ["binding"]]),
            ("3-1-1", [["3-1-1", "2-0-1", "0"], ["leaf"]]),
        ])
        chain = derive_hyphae_chain(doc, "3-1-1")
        for addr in chain:
            layer, vg, _ = addr.split("-")
            self.assertEqual((int(layer), int(vg)), (0, 0))

    def test_deterministic(self) -> None:
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("1-1-1", [["1-1-1", "0-0-1", "1"], ["val"]]),
        ])
        c1 = derive_hyphae_chain(doc, "1-1-1")
        c2 = derive_hyphae_chain(doc, "1-1-1")
        self.assertEqual(c1, c2)

    def test_missing_datum_address_raises(self) -> None:
        doc = _doc([("0-0-1", [["0-0-1", "~", "0-0-0"], ["x"]])])
        with self.assertRaises(ValueError):
            derive_hyphae_chain(doc, "9-9-9")

    def test_rudi_datum_itself(self) -> None:
        # A rudi datum's own chain: only itself
        doc = _doc([
            ("0-0-1", [["0-0-1", "~", "0-0-0"], ["time"]]),
            ("0-0-2", [["0-0-2", "~", "0-0-0"], ["space"]]),
        ])
        chain = derive_hyphae_chain(doc, "0-0-2")
        self.assertEqual(chain, ["0-0-1", "0-0-2"])


if __name__ == "__main__":
    unittest.main()
