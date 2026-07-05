"""Local feedback submission endpoint tests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import feedback
from app.auth import email as email_delivery


class FeedbackEndpointTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.feedback_root = Path(
            self.temp_dir.name
        )
        app = FastAPI()
        app.include_router(
            feedback.router
        )
        self.client = TestClient(
            app
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_feedback_is_saved_with_account_details(self):
        with (
            patch.object(
                feedback,
                "data_path",
                side_effect=lambda *parts: (
                    self.feedback_root.joinpath(
                        *parts
                    )
                ),
            ),
            patch.object(
                feedback,
                "current_user",
                return_value={
                    "email": "user@example.com",
                    "plan": "pro",
                },
            ),
            patch.object(
                feedback,
                "send_feedback_email",
            ) as send_email,
        ):
            response = self.client.post(
                "/api/feedback",
                json={
                    "category": "Bug Report",
                    "subject": "Keyboard action issue",
                    "description": "Keyboard action is not working.",
                    "email": "ignored@example.com",
                    "plan": "free",
                    "created_at": "ignored",
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.json()["message"],
            "Thank you! Your feedback has been submitted.",
        )
        self.assertRegex(
            response.json()["filename"],
            r"^\d{4}-\d{2}-\d{2}_\d{6}_feedback\.json$",
        )

        files = list(
            (
                self.feedback_root
                /
                "feedback"
            ).glob(
                "*.json"
            )
        )
        self.assertEqual(
            len(files),
            1,
        )
        saved = json.loads(
            files[0].read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            saved["email"],
            "user@example.com",
        )
        self.assertEqual(
            saved["plan"],
            "Pro",
        )
        self.assertIn(
            "app_version",
            saved,
        )
        self.assertNotEqual(
            saved["created_at"],
            "ignored",
        )
        send_email.assert_called_once_with(
            "shahred94@gmail.com",
            saved,
        )

    def test_email_failure_still_keeps_local_json(self):
        with (
            patch.object(
                feedback,
                "data_path",
                side_effect=lambda *parts: (
                    self.feedback_root.joinpath(
                        *parts
                    )
                ),
            ),
            patch.object(
                feedback,
                "current_user",
                return_value=None,
            ),
            patch.object(
                feedback,
                "send_feedback_email",
                side_effect=RuntimeError(
                    "SMTP unavailable"
                ),
            ),
        ):
            response = self.client.post(
                "/api/feedback",
                json={
                    "category": "Feature Request",
                    "email": "guest@example.com",
                    "subject": "New option",
                    "description": "Please add this option.",
                    "plan": "guest",
                },
            )

        self.assertEqual(
            response.status_code,
            502,
        )
        self.assertTrue(
            response.json()["saved"]
        )
        self.assertIn(
            "saved locally",
            response.json()["message"],
        )
        self.assertEqual(
            len(
                list(
                    (
                        self.feedback_root
                        /
                        "feedback"
                    ).glob(
                        "*.json"
                    )
                )
            ),
            1,
        )

    def test_required_fields_and_description_limit_are_validated(self):
        cases = [
            {
                "category": "Bug Report",
                "email": " ",
                "subject": "Subject",
                "description": "Details",
            },
            {
                "category": "Bug Report",
                "email": "user@example.com",
                "subject": " ",
                "description": "Details",
            },
            {
                "category": "Bug Report",
                "email": "user@example.com",
                "subject": "Subject",
                "description": " ",
            },
            {
                "category": "Bug Report",
                "email": "user@example.com",
                "subject": "Subject",
                "description": "x" * 5001,
            },
            {
                "category": "Unknown",
                "email": "user@example.com",
                "subject": "Subject",
                "description": "Details",
            },
        ]

        for payload in cases:
            with self.subTest(
                payload=payload
            ):
                response = self.client.post(
                    "/api/feedback",
                    json=payload,
                )
                self.assertEqual(
                    response.status_code,
                    422,
                )

    def test_feedback_email_contains_required_details(self):
        payload = {
            "category": "UI Improvement",
            "email": "user@example.com",
            "plan": "Free",
            "app_version": "1.0.8",
            "created_at": "2026-07-03T14:30:00+08:00",
            "subject": "Improve spacing",
            "description": "Please improve the modal spacing.",
        }

        with patch.object(
            email_delivery,
            "send_message",
        ) as send_message:
            email_delivery.send_feedback_email(
                "shahred94@gmail.com",
                payload,
            )

        message = send_message.call_args.args[0]
        self.assertEqual(
            message["To"],
            "shahred94@gmail.com",
        )
        self.assertEqual(
            message["Subject"],
            (
                "[TBana Stream] UI Improvement - "
                "Improve spacing"
            ),
        )
        body = message.get_content()
        for expected in (
            "Category: UI Improvement",
            "User Email: user@example.com",
            "User Plan: Free",
            "App Version: 1.0.8",
            "Date & Time: 2026-07-03T14:30:00+08:00",
            "Subject: Improve spacing",
            "Please improve the modal spacing.",
        ):
            self.assertIn(
                expected,
                body,
            )


if __name__ == "__main__":
    unittest.main()
