"""Local integration tests for auth, limits, and ToyyibPay activation."""

from hashlib import md5
from pathlib import Path
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.storage import sqlite_store


class ProviderResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class SubscriptionFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        sqlite_store.DATABASE_PATH = (
            Path(self.temp_dir.name) / "livetrigger-test.db"
        )
        sqlite_store.initialize_database()

        from app.api.auth import router as auth_router
        from app.api.actions_v2 import router as actions_router
        from app.api.routes import router as base_router
        from app.api.subscription import payment_router, subscription_router
        from app.auth.repository import initialize_auth_tables
        from app.auth.service import SubscriptionError
        from app.auth.service import (
            enforce_action_creation,
            enforce_trigger_creation,
        )
        from app.core.config import settings

        initialize_auth_tables()
        settings.public_base_url = "https://api.example.test"
        settings.toyyibpay_base_url = "https://dev.toyyibpay.com"
        settings.toyyibpay_category_code = "TESTCATEGORY"
        settings.toyyibpay_secret_key = "test-secret"
        settings.pro_price_cents = 1000
        settings.pro_duration_days = 30
        settings.subscription_api_url = ""

        app = FastAPI()

        @app.exception_handler(SubscriptionError)
        async def handle_subscription_error(
            request: Request,
            error: SubscriptionError,
        ):
            return JSONResponse(
                status_code=error.status_code,
                content={"error": error.error, "message": error.message},
            )

        app.include_router(auth_router)
        app.include_router(base_router)
        app.include_router(actions_router)
        app.include_router(subscription_router)
        app.include_router(payment_router)

        @app.post("/test/action")
        def protected_action(request: Request):
            enforce_action_creation(request)
            return {"ok": True}

        @app.post("/test/trigger")
        def protected_trigger(request: Request):
            enforce_trigger_creation(request)
            return {"ok": True}

        self.client = TestClient(
            app,
            base_url="https://api.example.test",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_register_limits_payment_callback_and_pro(self):
        guest = self.client.get("/api/auth/me")
        self.assertEqual(guest.status_code, 200)
        self.assertEqual(guest.json()["plan"], "guest")

        register = self.client.post(
            "/api/auth/register",
            json={
                "email": "tester@example.com",
                "password": "correct-horse-battery",
                "display_name": "Tester",
            },
        )
        self.assertEqual(register.status_code, 200)
        self.assertEqual(register.json()["plan"], "free")
        self.assertEqual(register.json()["limits"]["max_actions"], 6)
        self.assertEqual(register.json()["limits"]["max_triggers"], 30)

        me = self.client.get("/api/auth/me")
        self.assertTrue(me.json()["logged_in"])
        self.assertEqual(me.json()["plan"], "free")

        with closing(sqlite_store.get_connection()) as connection:
            for number in range(6):
                connection.execute(
                    "INSERT INTO action_presets (name) VALUES (?)",
                    (f"Action {number}",),
                )
            action_id = connection.execute(
                "SELECT id FROM action_presets ORDER BY id LIMIT 1"
            ).fetchone()["id"]
            for number in range(30):
                connection.execute(
                    """
                    INSERT INTO event_triggers (
                        enabled, trigger_type, trigger_value,
                        user_filter, action_id
                    )
                    VALUES (1, 'GIFT', ?, 'ANY', ?)
                    """,
                    (f"Gift {number}", action_id),
                )
            connection.commit()

        action_limit = self.client.post("/test/action")
        trigger_limit = self.client.post("/test/trigger")
        duplicate_action_limit = self.client.post(
            f"/api/actions/{action_id}/duplicate"
        )
        first_trigger_id = self.client.get(
            "/api/actions/event-triggers"
        ).json()["events"][0]["id"]
        duplicate_trigger_limit = self.client.post(
            f"/api/actions/event-triggers/{first_trigger_id}/duplicate"
        )
        self.assertEqual(action_limit.status_code, 403)
        self.assertEqual(trigger_limit.status_code, 403)
        self.assertEqual(
            duplicate_action_limit.status_code,
            403,
        )
        self.assertEqual(
            duplicate_trigger_limit.status_code,
            403,
        )
        self.assertEqual(
            action_limit.json()["error"],
            "FREE_LIMIT_REACHED",
        )
        self.assertEqual(
            trigger_limit.json()["error"],
            "FREE_LIMIT_REACHED",
        )

        with patch(
            "app.subscription.service.httpx.post",
            return_value=ProviderResponse([{"BillCode": "TESTBILL"}]),
        ):
            payment = self.client.post(
                "/api/subscription/create-payment"
            )

        self.assertEqual(payment.status_code, 200)
        payment_data = payment.json()
        self.assertEqual(
            payment_data["payment_url"],
            "https://dev.toyyibpay.com/TESTBILL",
        )

        order_id = payment_data["external_reference"]
        refno = "TP-TEST-001"
        callback_hash = md5(
            f"test-secret1{order_id}{refno}ok".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()

        transaction = {
            "billpaymentStatus": "1",
            "billExternalReferenceNo": order_id,
            "billpaymentAmount": "10.00",
        }
        callback_body = {
            "refno": refno,
            "status": "1",
            "reason": "Approved",
            "billcode": "TESTBILL",
            "order_id": order_id,
            "amount": "10.00",
            "hash": callback_hash,
        }

        with patch(
            "app.subscription.service.httpx.post",
            return_value=ProviderResponse([transaction]),
        ):
            callback = self.client.post(
                "/api/payment/callback",
                files={
                    key: (None, value)
                    for key, value in callback_body.items()
                },
            )

        self.assertEqual(callback.status_code, 200)
        self.assertEqual(callback.json()["plan"], "pro")

        upgraded = self.client.get("/api/auth/me").json()
        self.assertEqual(upgraded["plan"], "pro")
        self.assertIsNone(upgraded["limits"]["max_actions"])
        self.assertIsNone(upgraded["limits"]["max_triggers"])
        self.assertTrue(upgraded["features"]["edge_tts"])

        with patch(
            "app.subscription.service.httpx.post",
            return_value=ProviderResponse([transaction]),
        ):
            repeat = self.client.post(
                "/api/payment/callback",
                files={
                    key: (None, value)
                    for key, value in callback_body.items()
                },
            )
        self.assertEqual(repeat.status_code, 200)

    def test_invalid_callback_hash_is_rejected(self):
        response = self.client.post(
            "/api/payment/callback",
            data={
                "status": "1",
                "order_id": "missing",
                "refno": "bad",
                "hash": "not-valid",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "INVALID_CALLBACK")

    def test_duplicate_and_disable_action_and_event(self):
        register = self.client.post(
            "/api/auth/register",
            json={
                "email": "clone@example.com",
                "password": "correct-horse-battery",
                "display_name": "Clone Tester",
            },
        )
        self.assertEqual(register.status_code, 200)

        created = self.client.post(
            "/api/actions",
            json={
                "name": "Kickflip",
                "duration": 3,
                "description": "Keyboard test",
            },
        )
        self.assertEqual(created.status_code, 200)
        action_id = created.json()["id"]

        step = self.client.post(
            f"/api/actions/{action_id}/steps",
            json={
                "order": 1,
                "type": "KEYBOARD",
                "value": "space",
            },
        )
        self.assertEqual(step.status_code, 200)

        duplicate = self.client.post(
            f"/api/actions/{action_id}/duplicate"
        )
        self.assertEqual(duplicate.status_code, 200)
        duplicate_id = duplicate.json()["id"]

        actions = self.client.get(
            "/api/actions"
        ).json()["actions"]
        copied = next(
            action
            for action in actions
            if action["id"] == duplicate_id
        )
        self.assertEqual(copied["name"], "Kickflip (Copy)")
        copied_steps = self.client.get(
            f"/api/actions/{duplicate_id}/steps"
        ).json()["steps"]
        self.assertEqual(len(copied_steps), 1)
        self.assertEqual(copied_steps[0]["value"], "space")

        disabled = self.client.put(
            f"/api/actions/{action_id}/status",
            json={"enabled": False},
        )
        self.assertEqual(disabled.status_code, 200)

        event = self.client.post(
            "/api/actions/event-triggers",
            json={
                "trigger_type": "GIFT",
                "trigger_value": "Rose",
                "user_filter": "ANY",
                "action_id": action_id,
            },
        )
        self.assertEqual(event.status_code, 200)

        events = self.client.get(
            "/api/actions/event-triggers"
        ).json()["events"]
        event_id = events[0]["id"]

        from app.core.events import LiveEvent
        from app.rules.event_engine import event_engine

        result = event_engine.process(
            LiveEvent(
                event_type="gift",
                user="Viewer",
                data={
                    "gift_name": "Rose",
                    "_simulator": True,
                },
            )
        )
        self.assertFalse(result["matched"])

        activity = self.client.get(
            "/activity/recent"
        )
        self.assertEqual(activity.status_code, 200)
        self.assertGreaterEqual(
            len(activity.json()["activity"]),
            1,
        )

        paused = self.client.post(
            "/queue/pause"
        )
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(
            self.client.get(
                "/queue/status"
            ).json()["paused"]
        )
        resumed = self.client.post(
            "/queue/resume"
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertFalse(
            self.client.get(
                "/queue/status"
            ).json()["paused"]
        )

        event_duplicate = self.client.post(
            f"/api/actions/event-triggers/{event_id}/duplicate"
        )
        self.assertEqual(event_duplicate.status_code, 200)
        duplicated_events = self.client.get(
            "/api/actions/event-triggers"
        ).json()["events"]
        self.assertEqual(len(duplicated_events), 2)


if __name__ == "__main__":
    unittest.main()
