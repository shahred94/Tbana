"""Desktop subscription cache and API-unavailable behavior."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.auth import remote_client
from app.auth.service import SubscriptionError
from app.core.config import settings


class OfflineCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_cache_path = remote_client.CACHE_PATH
        self.original_api_url = settings.subscription_api_url
        remote_client.CACHE_PATH = (
            Path(self.temp_dir.name) / "subscription_cache.json"
        )
        settings.subscription_api_url = "https://subscription.example.test"

    def tearDown(self):
        remote_client.CACHE_PATH = self.original_cache_path
        settings.subscription_api_url = self.original_api_url
        self.temp_dir.cleanup()

    @staticmethod
    def free_user():
        return {
            "logged_in": True,
            "email": "free@example.com",
            "display_name": "Free User",
            "plan": "free",
            "subscription_status": "active",
            "expiry_date": None,
            "limits": {
                "max_actions": 6,
                "max_triggers": 10,
            },
            "features": {
                "edge_tts": False,
                "premium_features": False,
            },
            "usage": {"actions": 2, "triggers": 4},
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    def test_recent_online_state_is_used_when_api_is_unavailable(self):
        with patch.object(
            remote_client,
            "_request",
            return_value=(self.free_user(), None),
        ):
            online = remote_client.me("token")

        self.assertEqual(online["connection_status"], "connected")

        unavailable = SubscriptionError(
            "SUBSCRIPTION_API_UNAVAILABLE",
            "offline",
            503,
        )
        with patch.object(
            remote_client,
            "_request",
            side_effect=unavailable,
        ):
            cached = remote_client.me("token")

        self.assertEqual(cached["connection_status"], "offline_verified")
        self.assertEqual(cached["plan"], "free")

    def test_cache_older_than_seven_days_is_rejected(self):
        remote_client.CACHE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        remote_client.CACHE_PATH.write_text(
            json.dumps(
                {
                    "cached_at": (
                        datetime.now(timezone.utc)
                        - timedelta(days=8)
                    ).isoformat(),
                    "auth": self.free_user(),
                }
            ),
            encoding="utf-8",
        )

        self.assertIsNone(remote_client.cached_state())
        self.assertFalse(remote_client.CACHE_PATH.exists())

    def test_expired_pro_cache_downgrades_to_free(self):
        pro = {
            **self.free_user(),
            "plan": "pro",
            "expiry_date": (
                datetime.now(timezone.utc)
                - timedelta(minutes=1)
            ).isoformat(),
            "limits": {
                "max_actions": None,
                "max_triggers": None,
            },
            "features": {
                "edge_tts": True,
                "premium_features": True,
            },
        }
        remote_client._remember_online_state(pro)

        cached = remote_client.cached_state()
        self.assertEqual(cached["plan"], "free")
        self.assertEqual(cached["subscription_status"], "expired")
        self.assertFalse(cached["features"]["edge_tts"])

    def test_online_guest_clears_previous_user_cache(self):
        remote_client._remember_online_state(self.free_user())
        self.assertTrue(remote_client.CACHE_PATH.exists())

        guest = {
            "logged_in": False,
            "plan": "guest",
            "subscription_status": "disconnected",
        }
        with patch.object(
            remote_client,
            "_request",
            return_value=(guest, None),
        ):
            result = remote_client.me("expired-token")

        self.assertEqual(result["plan"], "guest")
        self.assertFalse(remote_client.CACHE_PATH.exists())


if __name__ == "__main__":
    unittest.main()
