"""Tests for the Windows game-compatible keyboard helper."""

import unittest
from unittest.mock import patch

from app.actions import windows_input


class WindowsInputTest(unittest.TestCase):
    def test_named_and_function_keys_resolve(self):
        self.assertEqual(windows_input.virtual_key_for("enter"), 0x0D)
        self.assertEqual(windows_input.virtual_key_for("F1"), 0x70)
        self.assertEqual(windows_input.virtual_key_for("f24"), 0x87)

    def test_unsupported_named_key_is_rejected(self):
        with self.assertRaises(ValueError):
            windows_input.virtual_key_for("not-a-real-key")

    def test_combo_releases_keys_in_reverse_order(self):
        calls = []

        def remember(key, key_up=False):
            calls.append((key, key_up))

        with (
            patch.object(windows_input.os, "name", "nt"),
            patch.object(windows_input, "_send", side_effect=remember),
            patch.object(windows_input.time, "sleep"),
        ):
            windows_input.send_key_combo(
                ["ctrl", "a"],
                hold_seconds=0.1,
            )

        self.assertEqual(
            calls,
            [
                ("ctrl", False),
                ("a", False),
                ("a", True),
                ("ctrl", True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
