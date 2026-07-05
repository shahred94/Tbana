"""Tests for dashboard recent activity storage."""

import unittest

from app.core.activity import ActivityFeed


class ActivityFeedTest(unittest.TestCase):
    def test_latest_activity_is_first_and_limit_applies(self):
        feed = ActivityFeed(limit=3)
        feed.record("event", "matched", "First")
        feed.record("queue", "completed", "Second")

        recent = feed.recent(1)

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["title"], "Second")
        self.assertEqual(recent[0]["id"], 2)

    def test_clear_removes_activity(self):
        feed = ActivityFeed()
        feed.record("event", "ignored", "No match")
        feed.clear()
        self.assertEqual(feed.recent(), [])


if __name__ == "__main__":
    unittest.main()
