from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.structures.hops.chronology import (
    build_chronology_authority,
    decode_hops_as_utc_datetime,
    encode_utc_datetime_as_hops,
)
from micyte.core.structures.hops.time_address import compare_time_addresses
from micyte.core.structures.hops.time_address_schema import (
    schema_from_anchor_payload,
    validate_address_with_schema,
)


class HopsChronologyTests(unittest.TestCase):
    def _anthology_payload(self) -> dict[str, object]:
        # the 2026-07-07 recompiled magnitude: day radix 1462 so the 1-based day
        # 1461 (the last day of each leap cycle) is encodable; slot 0 reserved
        return {
            "1-1-1": [
                [
                    "1-1-1",
                    "0-0-1",
                    "00000010000110000000110011010101111000011011001100011101111001111101000111110100011111010001011011011011000111100111100",
                ],
                ["HOPS-chornological"],
            ]
        }

    def _quadrennium_payload(self) -> dict[str, object]:
        return {
            "1-1-1": [["1-1-1", "rf.0-0-1", "00000100011100000101100100011011111101110110110101110001111001111001111101000"], ["HOPS-quadrennium_cycle"]],
            "2-0-1": [["2-0-1", "~", "1-1-1"], ["HOPS-space-quadrennium"]],
            "3-1-1": [["3-1-1", "2-0-1", "0"], ["HOPS-babelette-quadrennium_cycle"]],
        }

    def test_schema_decodes_live_chronology_authority(self) -> None:
        schema_payload = schema_from_anchor_payload(self._anthology_payload())
        self.assertTrue(bool(schema_payload.get("ok")))
        self.assertEqual(
            (schema_payload.get("schema") or {}).get("denotations"),
            [4, 1000, 1000, 1000, 1462, 24, 60, 60],
        )

    def test_encoder_projects_utc_time_onto_quadrennium_axis(self) -> None:
        schema_payload = schema_from_anchor_payload(self._anthology_payload())
        authority = build_chronology_authority(
            schema_payload=schema_payload,
            quadrennium_payload=self._quadrennium_payload(),
        )
        hops = encode_utc_datetime_as_hops(
            datetime(2026, 7, 4, 12, 34, 56, tzinfo=UTC),
            authority=authority,
        )
        self.assertEqual(hops, "0-0-0-507-916-12-34-56")
        self.assertTrue(bool(validate_address_with_schema(hops, schema_payload).get("ok")))

    def test_numeric_time_comparison_is_descoped_from_string_ordering(self) -> None:
        self.assertLess(
            compare_time_addresses("0-0-0-507-916-12-34-56", "0-0-0-507-916-12-34-57"),
            0,
        )

    def _authority(self):
        return build_chronology_authority(
            schema_payload=schema_from_anchor_payload(self._anthology_payload()),
            quadrennium_payload=self._quadrennium_payload(),
        )

    def test_decoder_round_trips_the_encoder(self) -> None:
        authority = self._authority()
        for dt in (
            datetime(2026, 7, 4, 12, 34, 56, tzinfo=UTC),
            datetime(2024, 2, 29, 23, 59, 59, tzinfo=UTC),   # leap day
            datetime(2027, 12, 30, 23, 59, 59, tzinfo=UTC),  # penultimate day of the cycle
            datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC),  # LAST day of the leap cycle
            datetime(2028, 1, 1, tzinfo=UTC),                # first day of the next cycle
        ):
            token = encode_utc_datetime_as_hops(dt, authority=authority)
            self.assertEqual(decode_hops_as_utc_datetime(token, authority=authority), dt)

    def test_decoder_accepts_day_specificity(self) -> None:
        authority = self._authority()
        self.assertEqual(
            decode_hops_as_utc_datetime("0-0-0-507-916", authority=authority),
            datetime(2026, 7, 4, tzinfo=UTC),
        )

    def test_decoder_rejects_shallow_or_foreign_prefix(self) -> None:
        authority = self._authority()
        with self.assertRaises(ValueError):
            decode_hops_as_utc_datetime("0-0-0-507", authority=authority)  # cycle depth only
        with self.assertRaises(ValueError):
            decode_hops_as_utc_datetime("0-1-0-507-916", authority=authority)  # wrong prefix

    def test_last_day_of_cycle_encodes_after_the_radix_recompile(self) -> None:
        # day-in-cycle is 1-based (1..1461); the 2026-07-07 anchor recompile widened
        # the day radix to 1462 (slot 0 reserved) so the LAST day of each leap cycle
        # encodes — closing the limitation pinned here since 2026-07-05.
        token = encode_utc_datetime_as_hops(
            datetime(2027, 12, 31, tzinfo=UTC), authority=self._authority())
        self.assertEqual(token.split("-")[4], "1461")
        self.assertEqual(
            decode_hops_as_utc_datetime(token, authority=self._authority()),
            datetime(2027, 12, 31, tzinfo=UTC))

    def test_weekday_drifts_across_cycles(self) -> None:
        # 1461 % 7 == 5: the same day-in-cycle lands on a DIFFERENT weekday next cycle —
        # why cyclical events store weekday cadence + a window instead of day-in-cycle sets.
        authority = self._authority()
        a = datetime(2026, 7, 4, tzinfo=UTC)              # a Saturday
        b = a + timedelta(days=1461)                       # same day-in-cycle, next cycle
        tok_a = encode_utc_datetime_as_hops(a, authority=authority)
        tok_b = encode_utc_datetime_as_hops(b, authority=authority)
        self.assertEqual(tok_a.split("-")[4], tok_b.split("-")[4])  # same day segment
        self.assertNotEqual(a.weekday(), b.weekday())


if __name__ == "__main__":
    unittest.main()
