"""Production entry-point and environment configuration tests."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.production_main import app


class ProductionMainTests(unittest.TestCase):

    def test_health_returns_expected_payload(self):
        with (
            patch.object(settings, "app_env", "production"),
            patch.object(
                settings,
                "database_url",
                "postgresql://user:password@127.0.0.1/database",
            ),
            patch.object(settings, "secret_key", "x" * 32),
            patch.object(settings, "subscription_api_url", ""),
            patch.object(
                settings,
                "public_base_url",
                "https://api.tbanastream.com",
            ),
            patch("app.production_main.initialize_auth_tables"),
            TestClient(app) as client,
        ):
            response = client.get(
                "/health",
                headers={"host": "api.tbanastream.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_payment_urls_can_be_configured_independently(self):
        with (
            patch.object(
                settings,
                "toyyibpay_callback_url",
                "https://payments.example/api/payment/callback",
            ),
            patch.object(
                settings,
                "toyyibpay_return_url",
                "https://payments.example/api/payment/return",
            ),
        ):
            self.assertEqual(
                settings.payment_callback_url,
                "https://payments.example/api/payment/callback",
            )
            self.assertEqual(
                settings.payment_return_url,
                "https://payments.example/api/payment/return",
            )

    def test_production_rejects_desktop_proxy_url(self):
        with (
            patch.object(settings, "app_env", "production"),
            patch.object(
                settings,
                "database_url",
                "postgresql://user:password@127.0.0.1/database",
            ),
            patch.object(settings, "secret_key", "x" * 32),
            patch.object(
                settings,
                "public_base_url",
                "https://api.tbanastream.com",
            ),
            patch.object(
                settings,
                "subscription_api_url",
                "https://api.tbanastream.com",
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "desktop-only",
            ):
                settings.require_production_settings()


if __name__ == "__main__":
    unittest.main()
