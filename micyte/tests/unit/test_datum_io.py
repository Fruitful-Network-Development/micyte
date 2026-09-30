"""Round-trip tests for the datum_io YAML transport codec.

The contract that matters: a YAML round-trip must preserve the canonical MSS
version identity, so a document can leave MOS as YAML, be transformed, and
return with a stable hash where unchanged.
"""

from __future__ import annotations

import unittest

from micyte.core.datum_io import from_yaml, to_yaml
from micyte.core.mss import compute_mss_hash
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
    AuthoritativeDatumDocumentRow,
)


def _document() -> AuthoritativeDatumDocument:
    return AuthoritativeDatumDocument(
        document_id="lv.3-2-3.system.example.abc123",
        source_kind="sandbox_source",
        document_name="example",
        relative_path="system/example.json",
        canonical_name="lv.3-2-3.system.example.abc123",
        document_metadata={"creation_nonce": "deadbeef", "origin": "test"},
        rows=(
            # PAIRS
            AuthoritativeDatumDocumentRow(datum_address="4-2-1", raw=[["4-2-1", "ref.2-1-10", "1", "ref.3-1-4", "0110"], ["contract_request"]]),
            # RUDI
            AuthoritativeDatumDocumentRow(datum_address="0-0-1", raw=[["0-0-1", "~", "0-0-0"], ["time-ordinal-position"]]),
            # RECORD (dict tail)
            AuthoritativeDatumDocumentRow(datum_address="1-0-1", raw=[["1-0-1", "~", "0-0-11"], {"email": "a@b.c", "created_at": "2026"}]),
            # SCALAR
            AuthoritativeDatumDocumentRow(datum_address="0-0-3", raw="mycite.v2.datum.fnd.example.v2"),
        ),
    )


class DatumIoRoundTripTests(unittest.TestCase):
    def test_round_trip_preserves_mss_version_hash(self) -> None:
        document = _document()
        restored = from_yaml(to_yaml(document))
        self.assertEqual(
            compute_mss_hash(restored)["version_hash"],
            compute_mss_hash(document)["version_hash"],
        )

    def test_round_trip_preserves_rows(self) -> None:
        document = _document()
        restored = from_yaml(to_yaml(document))
        self.assertEqual(
            [(r.datum_address, r.raw) for r in restored.rows],
            [(r.datum_address, r.raw) for r in document.rows],
        )

    def test_round_trip_preserves_identity_fields(self) -> None:
        document = _document()
        restored = from_yaml(to_yaml(document))
        self.assertEqual(restored.document_id, document.document_id)
        self.assertEqual(restored.source_kind, document.source_kind)
        self.assertEqual(restored.document_name, document.document_name)

    def test_empty_metadata_round_trips_to_none(self) -> None:
        document = AuthoritativeDatumDocument(
            document_id="lv.1-1-1.system.empty.zzz",
            source_kind="sandbox_source",
            document_name="empty",
            relative_path="system/empty.json",
        )
        restored = from_yaml(to_yaml(document))
        self.assertEqual(
            compute_mss_hash(restored)["version_hash"],
            compute_mss_hash(document)["version_hash"],
        )

    def test_invalid_source_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            from_yaml("schema: x\nsource_kind: not_valid\nrows: []\n")


if __name__ == "__main__":
    unittest.main()
