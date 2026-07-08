"""Tests for dedicated overlay WebSocket routing."""

import asyncio
import unittest

from app.core.websocket_manager import WebSocketManager


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)


class OverlayRoutingTest(unittest.TestCase):
    def test_spin_events_only_reach_spin_overlay(self):
        async def run_test():
            manager = WebSocketManager()
            screen_overlay = FakeWebSocket()
            spin_overlay = FakeWebSocket()
            goal_overlay = FakeWebSocket()

            await manager.connect(
                screen_overlay,
                "1",
                "screen",
            )
            await manager.connect(
                spin_overlay,
                "1",
                "spin",
            )
            await manager.connect(
                goal_overlay,
                "1",
                "goal",
            )

            await manager.broadcast({
                "type": "spin",
                "data": {
                    "result": "Winner",
                },
            })

            self.assertEqual(
                screen_overlay.messages,
                [],
            )
            self.assertEqual(
                len(spin_overlay.messages),
                1,
            )
            self.assertEqual(
                goal_overlay.messages,
                [],
            )

            await manager.broadcast({
                "type": "overlay",
                "name": "gift",
                "data": {},
            })

            self.assertEqual(
                len(screen_overlay.messages),
                1,
            )
            self.assertEqual(
                len(spin_overlay.messages),
                1,
            )
            self.assertEqual(
                goal_overlay.messages,
                [],
            )

            await manager.broadcast({
                "type": "goal",
                "name": "likes",
                "data": {
                    "total": 100,
                },
            })

            self.assertEqual(
                len(screen_overlay.messages),
                1,
            )
            self.assertEqual(
                len(spin_overlay.messages),
                1,
            )
            self.assertEqual(
                len(goal_overlay.messages),
                1,
            )

            status = manager.get_overlay_status()
            self.assertEqual(
                status["screens"][0]["connections"],
                1,
            )
            self.assertEqual(
                status["spin_connections"],
                1,
            )
            self.assertEqual(
                status["goal_connections"],
                1,
            )

        asyncio.run(
            run_test()
        )


if __name__ == "__main__":
    unittest.main()
