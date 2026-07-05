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
        from app.api.simulator import router as simulator_router
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
        settings.pro_price_cents = 2990
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
        app.include_router(simulator_router)
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
        self.assertEqual(register.json()["limits"]["max_triggers"], 10)

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
            for number in range(10):
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
        ) as payment_post:
            payment = self.client.post(
                "/api/subscription/create-payment"
            )

        self.assertEqual(payment.status_code, 200)
        request_data = payment_post.call_args.kwargs["data"]
        self.assertEqual(
            request_data["billName"],
            "TBana Stream Pro",
        )
        self.assertEqual(
            request_data["billDescription"],
            "TBana Stream Pro 30-day subscription (50% off)",
        )
        self.assertEqual(request_data["billAmount"], "2990")
        payment_data = payment.json()
        self.assertEqual(payment_data["amount_cents"], 2990)
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
            "billpaymentAmount": "29.90",
        }
        callback_body = {
            "refno": refno,
            "status": "1",
            "reason": "Approved",
            "billcode": "TESTBILL",
            "order_id": order_id,
            "amount": "29.90",
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

    def test_password_reset_code_changes_password_and_revokes_sessions(self):
        from app.core.config import settings

        register = self.client.post(
            "/api/auth/register",
            json={
                "email": "reset@example.com",
                "password": "original-password",
                "display_name": "Reset Tester",
            },
        )
        self.assertEqual(register.status_code, 200)

        with (
            patch.object(settings, "app_env", "development"),
            patch.object(settings, "smtp_host", ""),
            patch.object(settings, "smtp_from_email", ""),
        ):
            request_reset = self.client.post(
                "/api/auth/forgot-password",
                json={
                    "email": "reset@example.com",
                },
            )
            unknown_reset = self.client.post(
                "/api/auth/forgot-password",
                json={
                    "email": "unknown@example.com",
                },
            )

        self.assertEqual(request_reset.status_code, 200)
        self.assertEqual(unknown_reset.status_code, 200)
        self.assertEqual(
            request_reset.json()["message"],
            unknown_reset.json()["message"],
        )
        self.assertNotIn(
            "reset_code",
            unknown_reset.json(),
        )

        reset_code = request_reset.json()["reset_code"]

        wrong_code = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "reset@example.com",
                "code": "00000000",
                "new_password": "replacement-password",
            },
        )
        self.assertEqual(wrong_code.status_code, 400)
        self.assertEqual(
            wrong_code.json()["error"],
            "INVALID_RESET_CODE",
        )

        completed = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "reset@example.com",
                "code": reset_code,
                "new_password": "replacement-password",
            },
        )
        self.assertEqual(completed.status_code, 200)

        revoked_session = self.client.get(
            "/api/auth/me"
        )
        self.assertFalse(
            revoked_session.json()["logged_in"]
        )

        old_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "reset@example.com",
                "password": "original-password",
            },
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "reset@example.com",
                "password": "replacement-password",
            },
        )
        self.assertEqual(new_login.status_code, 200)

        reused_code = self.client.post(
            "/api/auth/reset-password",
            json={
                "email": "reset@example.com",
                "code": reset_code,
                "new_password": "another-password",
            },
        )
        self.assertEqual(reused_code.status_code, 400)

    def test_free_spin_preview_bypasses_cooldown_and_limits_linked_actions(self):
        register = self.client.post(
            "/api/auth/register",
            json={
                "email": "spin@example.com",
                "password": "correct-horse-battery",
                "display_name": "Spin Tester",
            },
        )
        self.assertEqual(register.status_code, 200)
        self.assertEqual(register.json()["plan"], "free")

        action_ids = []

        with closing(sqlite_store.get_connection()) as connection:
            for number in range(7):
                cursor = connection.execute(
                    """
                    INSERT INTO action_presets (name)
                    VALUES (?)
                    """,
                    (f"Spin Action {number + 1}",),
                )
                action_id = int(cursor.lastrowid)
                action_ids.append(action_id)
                connection.execute(
                    """
                    INSERT INTO action_steps (
                        action_id, step_order, step_type, step_value
                    )
                    VALUES (?, 1, 'KEYBOARD', 'space')
                    """,
                    (action_id,),
                )
            connection.commit()

        from app.actions.executor import action_executor
        from app.core.websocket_manager import websocket_manager
        from app.widgets import spin

        def run_spin_immediately(job):
            spin.run_spin_job(job)
            return 1

        sqlite_store.set_setting(
            "spin_wheel_enabled",
            "false",
        )
        sqlite_store.set_setting(
            "spin_wheel_segments",
            (
                '[{"label":"Free prize","action_id":'
                f"{action_ids[0]}"
                "}]"
            ),
        )

        payload = {
            "event_type": "comment",
            "user": "Dashboard Simulator",
            "data": {
                "comment": "!spin",
                "viewer_type": "follower",
                "is_follower": True,
            },
        }

        original_connections = list(
            websocket_manager.active_connections
        )
        original_overlays = dict(
            websocket_manager.connection_overlays
        )
        spin_connection = object()
        websocket_manager.active_connections = [
            spin_connection
        ]
        websocket_manager.connection_overlays = {
            spin_connection: "spin"
        }

        try:
            with (
                patch.object(
                    websocket_manager,
                    "send_event",
                ) as send_event,
                patch.object(
                    action_executor,
                    "press_key",
                ) as press_key,
                patch.object(
                    spin,
                    "enqueue_spin_job",
                    side_effect=run_spin_immediately,
                ),
                patch.object(
                    spin.time,
                    "sleep",
                ),
            ):
                first = self.client.post(
                    "/simulate",
                    json=payload,
                )
                second = self.client.post(
                    "/simulate",
                    json=payload,
                )

            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.json()["spin"]["triggered"])
            self.assertEqual(
                first.json()["spin"]["overlay_connections"],
                1,
            )
            self.assertTrue(second.json()["spin"]["triggered"])
            self.assertEqual(press_key.call_count, 2)
            self.assertEqual(send_event.call_count, 2)

            sqlite_store.set_setting(
                "spin_wheel_segments",
                (
                    '[{"label":"Locked prize","action_id":'
                    f"{action_ids[6]}"
                    "}]"
                ),
            )

            with (
                patch.object(
                    websocket_manager,
                    "send_event",
                ),
                patch.object(
                    action_executor,
                    "press_key",
                ) as locked_press_key,
                patch.object(
                    spin,
                    "enqueue_spin_job",
                    side_effect=run_spin_immediately,
                ),
                patch.object(
                    spin.time,
                    "sleep",
                ),
            ):
                locked = self.client.post(
                    "/simulate",
                    json=payload,
                )

            self.assertTrue(locked.json()["spin"]["triggered"])
            self.assertTrue(locked.json()["spin"]["queued"])
            locked_press_key.assert_not_called()

        finally:
            websocket_manager.active_connections = (
                original_connections
            )
            websocket_manager.connection_overlays = (
                original_overlays
            )

    def test_guest_cannot_execute_existing_actions_or_events(self):
        credentials = {
            "email": "runtime@example.com",
            "password": "correct-horse-battery",
            "display_name": "Runtime Tester",
        }
        register = self.client.post(
            "/api/auth/register",
            json=credentials,
        )
        self.assertEqual(register.status_code, 200)

        created = self.client.post(
            "/api/actions",
            json={
                "name": "Guest Lock",
                "duration": 0,
                "description": "Must require login",
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

        trigger = self.client.post(
            "/api/actions/event-triggers",
            json={
                "trigger_type": "GIFT",
                "trigger_value": "Rose",
                "user_filter": "ANY",
                "action_id": action_id,
            },
        )
        self.assertEqual(trigger.status_code, 200)
        self.assertEqual(
            self.client.post("/api/auth/logout").status_code,
            200,
        )

        from app.actions.executor import action_executor
        from app.core.events import LiveEvent
        from app.rules.event_engine import event_engine

        live_event = LiveEvent(
            event_type="gift",
            user="Viewer",
            data={
                "gift_name": "Rose",
                "_simulator": True,
            },
        )

        with patch.object(
            action_executor,
            "press_key",
        ) as press_key:
            blocked = event_engine.process(live_event)
            action_executor.execute({
                "type": "keyboard",
                "key": "space",
            })

        self.assertFalse(blocked["matched"])
        self.assertEqual(
            blocked["blocked"],
            "LOGIN_REQUIRED",
        )
        press_key.assert_not_called()
        action_test = self.client.post(
            f"/api/actions/{action_id}/test"
        )
        self.assertEqual(action_test.status_code, 401)
        self.assertEqual(
            action_test.json()["error"],
            "LOGIN_REQUIRED",
        )

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": credentials["email"],
                "password": credentials["password"],
            },
        )
        self.assertEqual(login.status_code, 200)

        with patch.object(
            action_executor,
            "press_key",
        ) as press_key:
            allowed = event_engine.process(live_event)

        self.assertTrue(allowed["matched"])
        press_key.assert_called_once()

        with closing(
            sqlite_store.get_connection()
        ) as connection:
            overflow_action_id = None
            for number in range(6):
                cursor = connection.execute(
                    """
                    INSERT INTO action_presets (name)
                    VALUES (?)
                    """,
                    (f"Overflow Action {number}",),
                )
                overflow_action_id = cursor.lastrowid

            for number in range(9):
                connection.execute(
                    """
                    INSERT INTO event_triggers (
                        enabled, trigger_type, trigger_value,
                        user_filter, action_id
                    )
                    VALUES (1, 'GIFT', ?, 'ANY', ?)
                    """,
                    (f"Allowed Gift {number}", action_id),
                )

            connection.execute(
                """
                INSERT INTO event_triggers (
                    enabled, trigger_type, trigger_value,
                    user_filter, action_id
                )
                VALUES (1, 'GIFT', 'Locked Gift', 'ANY', ?)
                """,
                (action_id,),
            )
            connection.commit()

        with patch.object(
            action_executor,
            "press_key",
        ) as press_key:
            locked_event = event_engine.process(
                LiveEvent(
                    event_type="gift",
                    user="Viewer",
                    data={
                        "gift_name": "Locked Gift",
                        "_simulator": True,
                    },
                )
            )
            action_executor.execute({
                "type": "keyboard",
                "key": "space",
                "_action_preset_id": overflow_action_id,
            })

        self.assertFalse(locked_event["matched"])
        press_key.assert_not_called()



if __name__ == "__main__":
    unittest.main()
