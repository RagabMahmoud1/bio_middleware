import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import device_poll_interval


class ServicePollingTests(unittest.TestCase):
    def test_hikvision_default_is_five_minutes(self):
        self.assertEqual(
            device_poll_interval({"type": "hikvision"}),
            300,
        )

    def test_zkteco_default_is_one_hour(self):
        self.assertEqual(
            device_poll_interval({"type": "zkteco"}),
            3600,
        )

    def test_device_override_is_respected(self):
        self.assertEqual(
            device_poll_interval({
                "type": "hikvision",
                "poll_interval_seconds": 600,
            }),
            600,
        )

    def test_too_small_override_is_clamped(self):
        self.assertEqual(
            device_poll_interval({
                "type": "hikvision",
                "poll_interval_seconds": 5,
            }),
            60,
        )


if __name__ == "__main__":
    unittest.main()
