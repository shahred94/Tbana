"""Webhook placeholder rendering."""

import unittest

from app.core.events import LiveEvent
from app.rules.event_engine import EventEngine


class WebhookPlaceholderTest(unittest.TestCase):
    def test_webhook_uses_dashboard_placeholder_aliases(self):
        event = LiveEvent(
            event_type="GIFT",
            user="Aina Live",
            data={
                "gift_name": "Rose",
                "count": 3,
                "coins": 15,
            },
        )

        action = EventEngine().build_action_object(
            event,
            "webhook",
            (
                "https://example.test/hook?"
                "username={username}&nickname={nickname}"
                "&gift={giftname}&repeat={repeatcount}&coins={coins}"
            ),
        )

        self.assertEqual(
            action["url"],
            (
                "https://example.test/hook?"
                "username=Aina%20Live&nickname=Aina%20Live"
                "&gift=Rose&repeat=3&coins=15"
            ),
        )

    def test_webhook_keeps_legacy_user_placeholder(self):
        event = LiveEvent(
            event_type="COMMENT",
            user="Viewer",
            data={
                "comment": "hello world",
            },
        )

        action = EventEngine().build_action_object(
            event,
            "webhook",
            "https://example.test/hook?user={user}&comment={comment}",
        )

        self.assertEqual(
            action["url"],
            "https://example.test/hook?user=Viewer&comment=hello%20world",
        )


if __name__ == "__main__":
    unittest.main()
