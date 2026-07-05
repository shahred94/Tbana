"""Tests for dashboard test/simulator delay validation."""

import unittest

from app.api.test_timing import normalize_test_delay


class TestTimingTest(unittest.TestCase):
    def test_delay_stays_within_allowed_range(self):
        self.assertEqual(normalize_test_delay(-5), 0)
        self.assertEqual(normalize_test_delay(3), 3)
        self.assertEqual(normalize_test_delay(50), 10)

    def test_invalid_delay_becomes_zero(self):
        self.assertEqual(normalize_test_delay("invalid"), 0)
        self.assertEqual(normalize_test_delay(float("nan")), 0)
        self.assertEqual(normalize_test_delay(float("inf")), 0)


if __name__ == "__main__":
    unittest.main()
