"""Built-in !spin sequencing and cooldown behavior."""

import unittest
from unittest.mock import patch

from app.core.events import LiveEvent
from app.widgets import spin


class SpinWidgetTest(unittest.TestCase):

    @staticmethod
    def event(**data):
        return LiveEvent(
            event_type="COMMENT",
            user="Aina",
            data={
                "comment": "!spin",
                **data,
            },
        )

    def test_subscriber_status_has_highest_priority(self):
        event = self.event(
            is_follower=True,
            is_fan_club_member=True,
            is_subscriber=True,
        )

        self.assertEqual(
            spin.viewer_type_from_event(event),
            "subscriber",
        )
        self.assertEqual(
            spin.viewer_status_label("subscriber"),
            "Subscriber",
        )

    def test_active_cooldown_reports_exact_time_and_status(self):
        with (
            patch.object(
                spin,
                "setting_bool",
                return_value=True,
            ),
            patch.object(
                spin,
                "spin_cooldown_minutes",
                return_value=10,
            ),
            patch.object(
                spin,
                "load_user_cooldowns",
                return_value={
                    "aina": {
                        "last_spin_at": 1000,
                        "viewer_type": "follower",
                    }
                },
            ),
            patch.object(
                spin.time,
                "time",
                return_value=1060,
            ),
        ):
            access = spin.spin_access_details(
                self.event(
                    is_follower=True
                )
            )

        self.assertFalse(access["allowed"])
        self.assertEqual(access["viewer_status"], "Follower")
        self.assertEqual(access["remaining_seconds"], 540)
        self.assertIn("9m 00s", access["reply"])

    def test_non_follower_reply_identifies_viewer_status(self):
        with patch.object(
            spin,
            "setting_bool",
            return_value=True,
        ):
            access = spin.spin_access_details(
                self.event()
            )

        self.assertFalse(access["allowed"])
        self.assertEqual(access["viewer_status"], "Viewer")
        self.assertIn("requires follower", access["reply"])

    def test_spin_entries_load_chance_with_backward_compatible_default(self):
        with patch.object(
            spin,
            "get_setting",
            return_value=(
                '[{"label":"Common","chance":7},'
                '{"label":"Legacy"},'
                '{"label":"Never","chance":0}]'
            ),
        ):
            entries = spin.load_spin_entries()

        self.assertEqual(
            [entry["chance"] for entry in entries],
            [7.0, 1.0, 0.0],
        )

    def test_winner_selection_uses_configured_chance_weights(self):
        entries = [
            {
                "label": "Common",
                "chance": 9,
            },
            {
                "label": "Rare",
                "chance": 1,
            },
        ]

        with patch.object(
            spin.random,
            "choices",
            return_value=[entries[1]],
        ) as choices:
            winner = spin.choose_spin_entry(
                entries
            )

        self.assertEqual(
            winner["label"],
            "Rare",
        )
        choices.assert_called_once_with(
            entries,
            weights=[9.0, 1.0],
            k=1,
        )

    def test_action_runs_only_after_spin_animation(self):
        order = []
        job = {
            "event": self.event(
                is_follower=True
            ),
            "segments": ["A", "B"],
            "result": "B",
            "action_id": 17,
            "spin_ms": 5200,
            "result_hold_ms": 3000,
        }

        with (
            patch.object(
                spin.websocket_manager,
                "send_event",
                side_effect=lambda message: order.append("animation"),
            ),
            patch.object(
                spin,
                "execute_linked_action",
                side_effect=lambda action_id, event: order.append("action"),
            ),
            patch.object(
                spin.time,
                "sleep",
                side_effect=lambda seconds: order.append(
                    f"sleep:{seconds:.1f}"
                ),
            ),
            patch.object(
                spin.time,
                "monotonic",
                side_effect=[10.0, 10.1],
            ),
        ):
            spin.run_spin_job(job)

        self.assertEqual(
            order[:3],
            [
                "animation",
                "sleep:5.4",
                "action",
            ],
        )
        self.assertEqual(order[3], "sleep:2.7")

    def test_spin_job_broadcast_includes_viewer_avatar(self):
        job = {
            "event": self.event(
                viewer_avatar_url="https://example.com/avatar.png",
                is_follower=True,
            ),
            "viewer_avatar_url": "https://example.com/avatar.png",
            "segments": ["A", "B"],
            "result": "B",
            "action_id": 17,
            "spin_ms": 10,
            "result_hold_ms": 10,
        }

        with (
            patch.object(
                spin.websocket_manager,
                "send_event",
            ) as send_event,
            patch.object(
                spin,
                "execute_linked_action",
            ),
            patch.object(
                spin.time,
                "sleep",
                return_value=None,
            ),
            patch.object(
                spin.time,
                "monotonic",
                side_effect=[10.0, 10.1],
            ),
        ):
            spin.run_spin_job(job)

        self.assertEqual(
            send_event.call_args.args[0]["data"]["viewer_avatar_url"],
            "https://example.com/avatar.png",
        )

    def test_simulator_spin_queues_action_instead_of_running_immediately(self):
        event = self.event(
            _simulator=True,
            is_follower=True,
        )

        with (
            patch.object(
                spin,
                "spin_access_details",
                return_value={
                    "allowed": True,
                    "reason": "",
                    "reply": "",
                    "viewer_type": "follower",
                    "viewer_status": "Follower",
                    "remaining_seconds": 0,
                },
            ),
            patch.object(
                spin,
                "load_spin_entries",
                return_value=[
                    {
                        "label": "Kickflip",
                        "action_id": 17,
                    }
                ],
            ),
            patch.object(
                spin,
                "enqueue_spin_job",
                return_value=1,
            ) as enqueue,
            patch.object(
                spin,
                "execute_linked_action",
            ) as execute,
        ):
            result = spin.trigger_spin_command(event)

        enqueue.assert_called_once()
        execute.assert_not_called()
        self.assertTrue(result["queued"])

    def test_spin_queue_carries_viewer_avatar(self):
        event = self.event(
            viewer_avatar_url="https://example.com/avatar.png",
            is_follower=True,
        )

        with (
            patch.object(
                spin,
                "spin_access_details",
                return_value={
                    "allowed": True,
                    "reason": "",
                    "reply": "",
                    "viewer_type": "follower",
                    "viewer_status": "Follower",
                    "remaining_seconds": 0,
                },
            ),
            patch.object(
                spin,
                "load_spin_entries",
                return_value=[
                    {
                        "label": "Kickflip",
                        "action_id": 17,
                    }
                ],
            ),
            patch.object(
                spin,
                "enqueue_spin_job",
                return_value=1,
            ) as enqueue,
        ):
            spin.trigger_spin_command(event)

        queued_job = enqueue.call_args.args[0]
        self.assertEqual(
            queued_job["viewer_avatar_url"],
            "https://example.com/avatar.png",
        )

    def test_custom_spin_command_requires_bang_and_allows_prefix(self):
        def run(comment):
            event = self.event(
                comment=comment,
                is_follower=True,
            )

            with (
                patch.object(
                    spin,
                    "spin_enabled",
                    return_value=True,
                ),
                patch.object(
                    spin,
                    "get_setting",
                    return_value="chaos",
                ),
                patch.object(
                    spin,
                    "spin_access_details",
                    return_value={
                        "allowed": True,
                        "reason": "",
                        "reply": "",
                        "viewer_type": "follower",
                        "viewer_status": "Follower",
                        "remaining_seconds": 0,
                    },
                ),
                patch.object(
                    spin,
                    "load_spin_entries",
                    return_value=[
                        {
                            "label": "Kickflip",
                            "action_id": 17,
                        }
                    ],
                ),
                patch.object(
                    spin,
                    "enqueue_spin_job",
                    return_value=1,
                ) as enqueue,
            ):
                result = spin.trigger_spin_command(event)

            return result, enqueue

        no_bang, no_bang_enqueue = run("chaos")
        exact, exact_enqueue = run("!chaos")
        prefix, prefix_enqueue = run("!chaosablnetgd")

        self.assertIsNone(no_bang)
        no_bang_enqueue.assert_not_called()
        self.assertTrue(exact["triggered"])
        exact_enqueue.assert_called_once()
        self.assertTrue(prefix["triggered"])
        prefix_enqueue.assert_called_once()

    def test_blocked_spin_sends_auto_reply_notice(self):
        access = {
            "allowed": False,
            "reason": "cooldown",
            "reply": "@Aina • Fan • !spin cooldown: 1m remaining.",
            "viewer_type": "fan_club",
            "viewer_status": "Fan",
            "remaining_seconds": 60,
        }

        with (
            patch.object(
                spin,
                "spin_enabled",
                return_value=True,
            ),
            patch.object(
                spin,
                "spin_access_details",
                return_value=access,
            ),
            patch.object(
                spin,
                "send_spin_notice",
            ) as send_notice,
            patch.object(
                spin,
                "enqueue_spin_job",
            ) as enqueue,
        ):
            result = spin.trigger_spin_command(
                self.event()
            )

        send_notice.assert_called_once()
        enqueue.assert_not_called()
        self.assertEqual(result["viewer_status"], "Fan")
        self.assertEqual(result["remaining_seconds"], 60)


if __name__ == "__main__":
    unittest.main()
