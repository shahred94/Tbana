"""Tests for unified gift-trigger behavior."""

import unittest
from unittest.mock import patch

from app.core.events import LiveEvent
from app.rules.event_engine import event_engine
from app.storage.sqlite_store import (
    add_gift_rule,
    delete_gift_rule,
    get_gift_rule,
)


class GiftMatchingTest(unittest.TestCase):
    def test_gift_rule_api_uses_unified_event_trigger_storage(self):
        add_gift_rule(
            "Friendship Necklace",
            "assets/sounds/rose.mp3",
            "gift overlay",
        )

        rule = None
        try:
            rule = get_gift_rule("  friendship   necklace  ")

            self.assertIsNotNone(rule)
            self.assertEqual(rule["gift_name"], "Friendship Necklace")
            self.assertEqual(rule["sound"], "assets/sounds/rose.mp3")
            self.assertEqual(rule["overlay"], "gift overlay")
            self.assertTrue(rule["enabled"])
        finally:
            if rule:
                delete_gift_rule(rule["id"])

    def test_gift_event_repeats_once_per_count(self):
        with (
            patch(
                "app.auth.service.active_runtime_plan",
                return_value="free",
            ),
            patch(
                "app.auth.service.runtime_item_is_allowed",
                return_value=True,
            ),
            patch(
                "app.auth.service.runtime_allowed_item_ids",
                return_value=None,
            ),
            patch(
                "app.rules.event_engine.get_setting",
                return_value="false",
            ),
            patch(
                "app.rules.event_engine.get_event_triggers",
                return_value=[
                    {
                        "id": 1,
                        "enabled": 1,
                        "trigger_type": "GIFT",
                        "trigger_value": "Rose",
                        "user_filter": "ANY",
                        "action_id": 7,
                        "action_mode": "single",
                        "action_group": "",
                        "action": "Kickflip",
                        "duration": 0,
                        "media_volume": 100,
                        "overlay_screen": 1,
                        "global_cooldown": 0,
                        "user_cooldown": 0,
                        "fade_enabled": False,
                        "repeat_gift_combos": False,
                        "skip_on_next_action": False,
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.get_action_presets",
                return_value=[
                    {
                        "id": 7,
                        "enabled": True,
                        "name": "Kickflip",
                        "duration": 0,
                        "media_volume": 100,
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.get_action_steps",
                return_value=[
                    {
                        "id": 1,
                        "order": 1,
                        "type": "KEYBOARD",
                        "value": "space",
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.action_executor.execute",
            ) as execute_action,
        ):
            result = event_engine.process(
                LiveEvent(
                    event_type="gift",
                    user="Viewer",
                    data={
                        "gift_name": "Rose",
                        "count": 5,
                        "_simulator": True,
                    },
                )
            )

        self.assertTrue(result["matched"])
        self.assertEqual(execute_action.call_count, 5)


if __name__ == "__main__":
    unittest.main()
