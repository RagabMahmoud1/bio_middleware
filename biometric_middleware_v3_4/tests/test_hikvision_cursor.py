import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cursors import compute_fetch_start


class HikvisionCursorTests(unittest.TestCase):
    def test_first_run_starts_from_floor(self):
        start = compute_fetch_start(
            floor="2026-07-19 00:00:00",
            cursor=None,
            overlap_minutes=360,
        )
        self.assertEqual(str(start), "2026-07-19 00:00:00")

    def test_cursor_rewinds_by_overlap(self):
        start = compute_fetch_start(
            floor="2026-07-19 00:00:00",
            cursor="2026-09-27T11:00:00+03:00",
            overlap_minutes=360,
        )
        self.assertEqual(str(start), "2026-09-27 05:00:00")

    def test_overlap_never_crosses_production_floor(self):
        start = compute_fetch_start(
            floor="2026-09-27 08:00:00",
            cursor="2026-09-27T10:00:00+03:00",
            overlap_minutes=360,
        )
        self.assertEqual(str(start), "2026-09-27 08:00:00")

    def test_two_day_downtime_keeps_old_cursor_as_recovery_base(self):
        start = compute_fetch_start(
            floor="2026-07-19 00:00:00",
            cursor="2026-09-25T18:00:00+03:00",
            overlap_minutes=360,
        )
        self.assertEqual(str(start), "2026-09-25 12:00:00")

    def test_zero_overlap_is_supported(self):
        start = compute_fetch_start(
            floor="2026-07-19 00:00:00",
            cursor="2026-09-27T11:00:00+03:00",
            overlap_minutes=0,
        )
        self.assertEqual(str(start), "2026-09-27 11:00:00")


if __name__ == "__main__":
    unittest.main()
