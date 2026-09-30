from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.structures.samras import (
    InvalidSamrasStructure,
    decode_structure,
    encode_canonical_structure_from_addresses,
    find_structure_authorities,
    load_workspace_from_compact_payload,
    reconstruct_structure_from_rows,
    select_preferred_structure_authority,
)

_LIVE_INVALID_MSN_SAMRAS = (
    "000000000010000000000110011011100000000100000000010100000010010000001111"
    "000001000100000100100000010011000001011100000110000000011011000001110000"
    "00011110000010000100001000100000100011000010010000001001"
)


class SamrasStructureUnitTests(unittest.TestCase):
    def test_round_trips_a_canonical_breadth_first_address_tree(self) -> None:
        structure = encode_canonical_structure_from_addresses(
            ["1", "2", "2-1", "2-2", "2-2-1", "3"]
        )

        decoded = decode_structure(structure.bitstream)

        self.assertEqual(decoded.source_format, "canonical")
        self.assertEqual(decoded.canonical_state, "canonical")
        self.assertEqual(decoded.addresses, ("1", "2", "3", "2-1", "2-2", "2-2-1"))
        self.assertEqual(decoded.root_count, 3)
        self.assertEqual(decoded.node_count, 6)

    def test_current_live_like_invalid_magnitude_fails_closed(self) -> None:
        with self.assertRaises(InvalidSamrasStructure) as exc:
            decode_structure(_LIVE_INVALID_MSN_SAMRAS)

        self.assertIn("legacy address width must be positive", str(exc.exception))

    def test_prefers_valid_anchor_authority_over_invalid_cache_candidate(self) -> None:
        valid = encode_canonical_structure_from_addresses(
            ["1", "2", "3", "3-1", "3-2", "3-2-1"]
        ).bitstream
        invalid = _LIVE_INVALID_MSN_SAMRAS

        cache_authorities = find_structure_authorities(
            {
                "datum_addressing_abstraction_space": {
                    "1-1-1": [["1-1-1", "0-0-5", invalid], ["msn-SAMRAS"]],
                }
            },
            source_kind="administrative_payload_cache",
            source_path="/cache.json",
        )
        anchor_authorities = find_structure_authorities(
            {
                "datum_addressing_abstraction_space": {
                    "1-1-2": [["1-1-2", "0-0-5", valid], ["msn-SAMRAS"]],
                }
            },
            source_kind="tool_anchor",
            source_path="/tool.json",
        )

        selected = select_preferred_structure_authority(
            list(cache_authorities) + list(anchor_authorities),
            require_decodable=True,
        )

        self.assertEqual(selected.source_kind, "tool_anchor")
        self.assertEqual(selected.structure.node_count, 6)
        self.assertEqual(selected.structure.root_count, 3)

    def test_reconstructs_canonical_structure_from_staged_address_rows(self) -> None:
        payload = {
            "datum_addressing_abstraction_space": {
                "1-1-1": [["1-1-1", "0-0-5", _LIVE_INVALID_MSN_SAMRAS], ["msn-SAMRAS"]],
                "4-2-1": [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "01010010011011110110111101110100"], ["root"]],
                "4-2-2": [["4-2-2", "rf.3-1-2", "3", "rf.3-1-3", "010011100101011101001000"], ["nwh"]],
                "4-2-3": [["4-2-3", "rf.3-1-2", "3-2", "rf.3-1-3", "010101010101001101000001"], ["usa"]],
                "4-2-4": [["4-2-4", "rf.3-1-2", "3-2-1", "rf.3-1-3", "01000110010000010100100101010010"], ["fair"]],
            }
        }

        structure = reconstruct_structure_from_rows(payload)
        workspace = load_workspace_from_compact_payload(payload)

        self.assertEqual(structure.addresses, ("1", "2", "3", "3-1", "3-2", "3-2-1"))
        self.assertEqual(workspace.structure.addresses, structure.addresses)
        self.assertTrue(any("reconstructed from staged address rows" in item for item in workspace.warnings))
        self.assertEqual(workspace.nodes[-1].address_id, "3-2-1")


if __name__ == "__main__":
    unittest.main()
