"""Application update endpoint tests."""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import update
from app.core.config import settings


class UpdateCheckTest(unittest.TestCase):
    def setUp(self):
        self.original_version = settings.app_version
        self.original_repository = settings.update_repository
        settings.app_version = "1.0.8"
        settings.update_repository = "shahred94/Tbana"

        app = FastAPI()
        app.include_router(update.router)
        self.client = TestClient(app)

    def tearDown(self):
        settings.app_version = self.original_version
        settings.update_repository = self.original_repository

    def test_version_parser_accepts_release_tags(self):
        self.assertEqual(update.parse_version("v2.4.1"), (2, 4, 1))
        self.assertEqual(update.parse_version("2.4.1"), (2, 4, 1))

    @patch.object(update, "_latest_release")
    def test_new_release_returns_setup_download(self, latest_release):
        latest_release.return_value = {
            "tag_name": "v1.0.9",
            "name": "TBana Stream 1.0.9",
            "body": "Faster startup.",
            "html_url": (
                "https://github.com/shahred94/Tbana/releases/tag/v1.0.9"
            ),
            "published_at": "2026-07-02T00:00:00Z",
            "assets": [
                {
                    "name": "TBana-Stream-Setup-1.0.9.exe",
                    "browser_download_url": (
                        "https://github.com/shahred94/Tbana/releases/"
                        "download/v1.0.9/TBana-Stream-Setup-1.0.9.exe"
                    ),
                }
            ],
        }

        response = self.client.get("/api/update/check")
        result = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(result["update_available"])
        self.assertTrue(result["direct_download"])
        self.assertTrue(result["download_url"].endswith(".exe"))

    @patch.object(update, "_latest_release")
    def test_current_release_reports_up_to_date(self, latest_release):
        latest_release.return_value = {
            "tag_name": "v1.0.8",
            "html_url": (
                "https://github.com/shahred94/Tbana/releases/tag/v1.0.8"
            ),
            "assets": [],
        }

        result = self.client.get("/api/update/check").json()

        self.assertFalse(result["update_available"])
        self.assertEqual(result["download_url"], "")

    @patch.object(
        update,
        "_latest_release",
        side_effect=update.UpdateLookupError(
            "No published release is available yet."
        ),
    )
    def test_missing_release_is_reported_safely(self, latest_release):
        result = self.client.get("/api/update/check").json()

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("No published release", result["message"])
