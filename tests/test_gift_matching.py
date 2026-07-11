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

    def test_live_keyboard_gifts_bypass_queue(self):
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
                    },
                    {
                        "id": 2,
                        "enabled": 1,
                        "trigger_type": "GIFT",
                        "trigger_value": "Finger Heart",
                        "user_filter": "ANY",
                        "action_id": 8,
                        "action_mode": "single",
                        "action_group": "",
                        "action": "Nitro",
                        "duration": 0,
                        "media_volume": 100,
                        "overlay_screen": 1,
                        "global_cooldown": 0,
                        "user_cooldown": 0,
                        "fade_enabled": False,
                        "repeat_gift_combos": False,
                        "skip_on_next_action": False,
                    },
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
                        "execution_type": "instant",
                    },
                    {
                        "id": 8,
                        "enabled": True,
                        "name": "Nitro",
                        "duration": 0,
                        "media_volume": 100,
                        "execution_type": "buff",
                    },
                ],
            ),
            patch(
                "app.rules.event_engine.get_action_steps",
                side_effect=lambda action_id: [
                    {
                        "id": action_id,
                        "order": 1,
                        "type": "KEYBOARD",
                        "value": (
                            "space"
                            if action_id == 7
                            else "n"
                        ),
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.gift_queue_manager.add_job_sync",
            ) as add_job,
            patch(
                "app.rules.event_engine.action_executor.execute",
            ) as execute_action,
        ):
            rose = event_engine.process(
                LiveEvent(
                    event_type="gift",
                    user="Viewer",
                    data={
                        "gift_name": "Rose",
                        "count": 1,
                    },
                )
            )
            finger_heart = event_engine.process(
                LiveEvent(
                    event_type="gift",
                    user="Viewer",
                    data={
                        "gift_name": "Finger Heart",
                        "count": 1,
                    },
                )
            )

        self.assertTrue(rose["matched"])
        self.assertTrue(finger_heart["matched"])
        add_job.assert_not_called()
        self.assertEqual(execute_action.call_count, 2)
        self.assertEqual(
            [
                call.args[0]["key"]
                for call in execute_action.call_args_list
            ],
            [
                "space",
                "n",
            ],
        )

    def test_live_sound_gift_still_uses_queue(self):
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
                        "action": "Cinematic Rose",
                        "duration": 3,
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
                        "name": "Cinematic Rose",
                        "duration": 3,
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
                        "type": "SOUND",
                        "value": "rose.mp3",
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.gift_queue_manager.add_job_sync",
            ) as add_job,
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
                        "count": 1,
                    },
                )
            )

        self.assertTrue(result["matched"])
        add_job.assert_called_once()
        execute_action.assert_not_called()

    def test_instant_sound_gift_combo_retriggers_with_stagger(self):
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
                        "execution_type": "instant",
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.get_action_steps",
                return_value=[
                    {
                        "id": 1,
                        "order": 1,
                        "type": "SOUND",
                        "value": "kickflip.mp3",
                    }
                ],
            ),
            patch(
                "app.rules.event_engine.gift_queue_manager.add_job_sync",
            ) as add_job,
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
                        "count": 3,
                    },
                )
            )

        self.assertTrue(result["matched"])
        add_job.assert_not_called()
        self.assertEqual(
            execute_action.call_count,
            3,
        )
        self.assertEqual(
            [
                call.args[0].get(
                    "_sound_start_delay"
                )
                for call in execute_action.call_args_list
            ],
            [
                0.0,
                0.08,
                0.16,
            ],
        )

    def test_live_keyboard_gift_can_be_forced_to_queue(self):
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
                        "action": "Queued Kickflip",
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
                        "name": "Queued Kickflip",
                        "duration": 0,
                        "media_volume": 100,
                        "execution_type": "queued",
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
                "app.rules.event_engine.gift_queue_manager.add_job_sync",
            ) as add_job,
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
                        "count": 1,
                    },
                )
            )

        self.assertTrue(result["matched"])
        add_job.assert_called_once()
        execute_action.assert_not_called()

    def test_follow_trigger_runs_only_once_per_live_session(self):
        event_engine.reset_live_session()

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
                "app.rules.event_engine.get_event_triggers",
                return_value=[
                    {
                        "id": 2,
                        "enabled": 1,
                        "trigger_type": "FOLLOW",
                        "trigger_value": "",
                        "user_filter": "ANY",
                        "action_id": 7,
                        "action_mode": "single",
                        "action_group": "",
                        "action": "Follow Action",
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
                        "name": "Follow Action",
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
            first = event_engine.process(
                LiveEvent(
                    event_type="FOLLOW",
                    user="Viewer1",
                    data={},
                )
            )
            second = event_engine.process(
                LiveEvent(
                    event_type="FOLLOW",
                    user="Viewer2",
                    data={},
                )
            )

        self.assertTrue(first["matched"])
        self.assertEqual(execute_action.call_count, 1)
        self.assertEqual(
            second["blocked"],
            "FOLLOW_ALREADY_HANDLED",
        )
        self.assertEqual(execute_action.call_count, 1)


if __name__ == "__main__":
    unittest.main()
