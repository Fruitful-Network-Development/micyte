from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.structures.hops.cyclical import (
    DAYS_PER_QUADRENNIUM,
    EPOCH,
    HC_MAGNITUDE_BITS,
    LC_MAGNITUDE_BITS,
    QC_MAGNITUDE_BITS,
    current_open_window,
    date_of_qc_day,
    encode_mixed_radix_magnitude,
    format_ic_stamp,
    hc_day_of,
    lc_day_of,
    next_hc_occurrences,
    open_runs_from_closures,
    parse_ic_stamp,
    qc_day_in_closures,
    qc_day_of,
)
from micyte.core.structures.hops.time_address_schema import (
    decode_mixed_radix_magnitude,
)

# The anthology-base chronological magnitude as it shipped before the day-radix
# recompile (1461 admits only 0..1460 — the 1-based day 1461 could not encode).
_LIVE_PRE_MIGRATION_BITS = (
    "0000001000011000000011001101010111100001101100110001110111100111"
    "1101000111110100011111010001011011010111000111100111100")


class MagnitudeEncoderTests(unittest.TestCase):
    def test_encoder_reproduces_the_anthology_base_convention(self) -> None:
        # byte-identical with the shipped uc magnitude for the same denotations —
        # proves the encoder mirrors the doctrine's minimal-width header format
        self.assertEqual(
            encode_mixed_radix_magnitude((4, 1000, 1000, 1000, 1461, 24, 60, 60)),
            _LIVE_PRE_MIGRATION_BITS)

    def test_ic_structure_magnitudes_round_trip(self) -> None:
        for bits, want in ((QC_MAGNITUDE_BITS, (1462, 24, 60)),
                           (HC_MAGNITUDE_BITS, (8, 24, 60)),
                           (LC_MAGNITUDE_BITS, (32, 24, 60))):
            self.assertEqual(decode_mixed_radix_magnitude(bits).denotations, want)

    def test_recompiled_uc_magnitude_round_trips(self) -> None:
        bits = encode_mixed_radix_magnitude((4, 1000, 1000, 1000, 1462, 24, 60, 60))
        self.assertEqual(decode_mixed_radix_magnitude(bits).denotations,
                         (4, 1000, 1000, 1000, 1462, 24, 60, 60))

    def test_rejects_non_positive_denotations(self) -> None:
        with self.assertRaises(ValueError):
            encode_mixed_radix_magnitude((0, 7))


class EpochPhaseTests(unittest.TestCase):
    def test_epoch_is_quadrennium_507_day_1_a_monday(self) -> None:
        self.assertEqual(EPOCH, date(2024, 1, 1))
        self.assertEqual(EPOCH.weekday(), 0)
        self.assertEqual(qc_day_of(EPOCH), 1)
        self.assertEqual(hc_day_of(EPOCH), 1)  # hebdomad day 1 == Monday, no offset

    def test_hc_day_matches_weekday_everywhere(self) -> None:
        for offset in (0, 1, 916, 1460, 1461, 2000, -365):
            d = EPOCH + timedelta(days=offset)
            self.assertEqual(hc_day_of(d), d.weekday() + 1)

    def test_hebdomad_is_epoch_continuous_across_the_cycle_boundary(self) -> None:
        # 1461 % 7 == 5: a per-cycle reset would jump the weekday at the boundary.
        # Epoch-continuous counting must NOT: consecutive days stay consecutive.
        last_of_cycle = date(2027, 12, 31)   # qc day 1461
        first_of_next = date(2028, 1, 1)     # qc day 1 of cycle 508
        self.assertEqual(qc_day_of(last_of_cycle), DAYS_PER_QUADRENNIUM)
        self.assertEqual(qc_day_of(first_of_next), 1)
        self.assertEqual(hc_day_of(first_of_next), hc_day_of(last_of_cycle) % 7 + 1)
        # and the same qc day next cycle is a DIFFERENT hebdomad day (the drift)
        self.assertNotEqual(hc_day_of(date(2026, 7, 4)),
                            hc_day_of(date(2026, 7, 4) + timedelta(days=1461)))

    def test_lunation_is_a_fixed_30_day_civil_cycle(self) -> None:
        self.assertEqual(lc_day_of(EPOCH), 1)
        self.assertEqual(lc_day_of(EPOCH + timedelta(days=29)), 30)
        self.assertEqual(lc_day_of(EPOCH + timedelta(days=30)), 1)

    def test_qc_day_round_trips_including_the_cycle_end(self) -> None:
        for d in (date(2024, 1, 1), date(2024, 2, 29), date(2026, 7, 4), date(2027, 12, 31)):
            self.assertEqual(date_of_qc_day(qc_day_of(d), cycle_start_year=2024), d)
        self.assertEqual(qc_day_of(date(2027, 12, 31)), 1461)  # encodable under radix 1462


class StampTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        self.assertEqual(parse_ic_stamp("6-9-0", structure="1-5-3"), (6, 9, 0))
        self.assertEqual(parse_ic_stamp("916", structure="1-5-2"), (916, 0, 0))
        self.assertEqual(parse_ic_stamp("1461", structure="1-5-2"), (1461, 0, 0))
        self.assertEqual(format_ic_stamp(6, 9, 0), "6-9-0")
        self.assertEqual(format_ic_stamp(916), "916")

    def test_range_enforcement_per_structure(self) -> None:
        for stamp, structure in (("8-0-0", "1-5-3"),    # hebdomad day > 7
                                 ("0-0-0", "1-5-3"),    # day is 1-based
                                 ("1462", "1-5-2"),     # qc day > 1461
                                 ("32-0-0", "1-5-4"),   # lunation day > 31
                                 ("6-24-0", "1-5-3"),   # hour out of radix
                                 ("6-9-60", "1-5-3")):  # minute out of radix
            with self.assertRaises(ValueError):
                parse_ic_stamp(stamp, structure=structure)
        with self.assertRaises(ValueError):
            parse_ic_stamp("6-9-0", structure="1-5-9")


class ClosureTests(unittest.TestCase):
    # a summer season open May 30 – Oct 31 each cycle year, expressed as closures
    def _closures(self):
        open_runs = []
        for y in range(2024, 2028):
            open_runs.append((qc_day_of(date(y, 5, 30)), qc_day_of(date(y, 10, 31))))
        closures = []
        cursor = 1
        for lo, hi in open_runs:
            if lo > cursor:
                closures.append((cursor, lo - cursor))
            cursor = hi + 1
        if cursor <= DAYS_PER_QUADRENNIUM:
            closures.append((cursor, DAYS_PER_QUADRENNIUM + 1 - cursor))
        return closures

    def test_open_runs_complement_closures(self) -> None:
        closures = self._closures()
        runs = open_runs_from_closures(closures)
        self.assertEqual(len(runs), 4)
        self.assertEqual(runs[0], (qc_day_of(date(2024, 5, 30)), qc_day_of(date(2024, 10, 31))))
        self.assertTrue(qc_day_in_closures(1, closures))
        self.assertFalse(qc_day_in_closures(qc_day_of(date(2026, 7, 4)), closures))

    def test_no_closures_means_the_whole_cycle_is_open(self) -> None:
        self.assertEqual(open_runs_from_closures([]), [(1, DAYS_PER_QUADRENNIUM)])

    def test_current_open_window_picks_the_containing_then_next_run(self) -> None:
        closures = self._closures()
        start, end = current_open_window(closures, now=date(2026, 7, 6))
        self.assertEqual((start, end), (date(2026, 5, 30), date(2026, 10, 31)))
        start, end = current_open_window(closures, now=date(2026, 12, 1))
        self.assertEqual((start, end), (date(2027, 5, 30), date(2027, 10, 31)))

    def test_next_hc_occurrences_respect_closures(self) -> None:
        closures = self._closures()
        # Saturdays (hc day 6) from Mon 2026-07-06 → 07-11, 07-18, 07-25
        got = next_hc_occurrences([6], closures, now=date(2026, 7, 6))
        self.assertEqual([d.isoformat() for d in got],
                         ["2026-07-11", "2026-07-18", "2026-07-25"])
        # from inside the closed tail: rolls to the NEXT season's first Saturdays
        got = next_hc_occurrences([6], closures, now=date(2026, 11, 15), limit=1)
        self.assertEqual(len(got), 1)
        self.assertGreaterEqual(got[0], date(2027, 5, 30))
        self.assertEqual(got[0].weekday(), 5)

    def test_occurrences_without_days_are_empty(self) -> None:
        self.assertEqual(next_hc_occurrences([], [], now=date(2026, 7, 6)), [])


if __name__ == "__main__":
    unittest.main()
