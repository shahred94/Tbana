"""TikTok connection control endpoint tests."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.tiktok import router
from app.tiktok import manager


class TikTokApiTest(unittest.TestCase):
    def setUp(self):
        self.original_client = manager.tiktok_client
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        manager.tiktok_client = self.original_client

    def test_disconnect_stops_active_client(self):
        active_client = Mock()
        active_client.stop = AsyncMock()
        manager.tiktok_client = active_client

        response = self.client.post("/api/tiktok/disconnect")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "OFFLINE")
        self.assertIsNone(manager.tiktok_client)
        active_client.stop.assert_awaited_once()

    def test_disconnect_is_safe_when_already_offline(self):
        manager.tiktok_client = None

        response = self.client.post("/api/tiktok/disconnect")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["message"],
            "TikTok is already disconnected",
        )

    @patch(
        "app.api.tiktok.asyncio.wait_for",
        new_callable=AsyncMock,
        side_effect=TimeoutError,
    )
    def test_disconnect_timeout_still_reports_offline(self, wait_for):
        active_client = Mock()
        active_client.stop = Mock(return_value=object())
        manager.tiktok_client = active_client

        response = self.client.post("/api/tiktok/disconnect")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "OFFLINE")
        self.assertIsNone(manager.tiktok_client)
        wait_for.assert_awaited_once()
