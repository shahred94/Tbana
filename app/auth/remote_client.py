"""Server-to-server client used by the Windows desktop application."""

from datetime import datetime, timedelta, timezone
import json
import threading
import time

import httpx

from app.core.config import settings
from app.core.paths import data_path


_entitlement_lock = threading.Lock()
_pro_verified_until = 0.0
OFFLINE_GRACE_DAYS = 7
CACHE_PATH = data_path("subscription_cache.json")


def enabled() -> bool:
    return settings.is_remote_desktop


def _request(
    method: str,
    path: str,
    token: str | None = None,
    json_body: dict | None = None,
) -> tuple[dict, str | None]:
    headers = {}
    if token:
        headers["Cookie"] = f"livetrigger_session={token}"

    try:
        response = httpx.request(
            method,
            f"{settings.subscription_api_url}{path}",
            headers=headers,
            json=json_body,
            timeout=15.0,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        from app.auth.service import SubscriptionError

        raise SubscriptionError(
            "SUBSCRIPTION_API_UNAVAILABLE",
            "TBana Stream could not reach the subscription server.",
            503,
        ) from error

    try:
        data = response.json()
    except ValueError:
        data = {
            "error": "SUBSCRIPTION_API_ERROR",
            "message": "Subscription server returned an invalid response.",
        }

    if response.status_code >= 500:
        from app.auth.service import SubscriptionError

        raise SubscriptionError(
            "SUBSCRIPTION_API_UNAVAILABLE",
            "TBana Stream could not verify the subscription server.",
            503,
        )

    if response.status_code >= 400:
        from app.auth.service import SubscriptionError

        raise SubscriptionError(
            str(data.get("error") or "SUBSCRIPTION_API_ERROR"),
            str(data.get("message") or "Subscription request failed."),
            response.status_code,
        )

    session_token = response.cookies.get("livetrigger_session")
    return data, session_token


def register(payload: dict) -> tuple[dict, str | None]:
    data, token = _request(
        "POST",
        "/api/auth/register",
        json_body=payload,
    )
    _remember_online_state(data)
    return data, token


def login(payload: dict) -> tuple[dict, str | None]:
    data, token = _request(
        "POST",
        "/api/auth/login",
        json_body=payload,
    )
    _remember_online_state(data)
    return data, token


def request_password_reset(
    payload: dict,
) -> dict:
    data, _ = _request(
        "POST",
        "/api/auth/forgot-password",
        json_body=payload,
    )
    return data


def reset_password(
    payload: dict,
) -> dict:
    data, _ = _request(
        "POST",
        "/api/auth/reset-password",
        json_body=payload,
    )
    return data


def logout(token: str | None) -> None:
    try:
        _request("POST", "/api/auth/logout", token=token)
    finally:
        clear_cached_state()
        note_entitlement(None)


def me(token: str | None) -> dict:
    try:
        data, _ = _request("GET", "/api/auth/me", token=token)
    except Exception as error:
        from app.auth.service import SubscriptionError

        if (
            isinstance(error, SubscriptionError)
            and error.error == "SUBSCRIPTION_API_UNAVAILABLE"
        ):
            cached = cached_state()
            if cached is not None:
                note_entitlement(cached)
                return cached
        raise

    _remember_online_state(data)
    return data


def create_payment(token: str | None) -> dict:
    data, _ = _request(
        "POST",
        "/api/subscription/create-payment",
        token=token,
    )
    return data


def subscription_status(token: str | None) -> dict:
    try:
        data, _ = _request(
            "GET",
            "/api/subscription/status",
            token=token,
        )
    except Exception as error:
        from app.auth.service import SubscriptionError

        if (
            isinstance(error, SubscriptionError)
            and error.error == "SUBSCRIPTION_API_UNAVAILABLE"
        ):
            cached = cached_state()
            if cached is not None:
                note_entitlement(cached)
                return cached
        raise

    _remember_online_state(data)
    return data


def _utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _remember_online_state(data: dict) -> None:
    online = dict(data)
    online["connection_status"] = "connected"
    online["verified_at"] = (
        online.get("verified_at")
        or datetime.now(timezone.utc).isoformat()
    )

    if online.get("logged_in"):
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "auth": online,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary.replace(CACHE_PATH)
    else:
        clear_cached_state()

    data.update(online)
    note_entitlement(data)


def clear_cached_state() -> None:
    try:
        CACHE_PATH.unlink()
    except FileNotFoundError:
        pass


def cached_state() -> dict | None:
    """Return a valid logged-in entitlement within the seven-day grace."""

    try:
        record = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None

    cached_at = _utc_datetime(record.get("cached_at"))
    data = record.get("auth")
    now = datetime.now(timezone.utc)

    if (
        cached_at is None
        or not isinstance(data, dict)
        or not data.get("logged_in")
        or now - cached_at > timedelta(days=OFFLINE_GRACE_DAYS)
    ):
        clear_cached_state()
        return None

    expiry = _utc_datetime(data.get("expiry_date"))
    if (
        data.get("plan") == "pro"
        and expiry is not None
        and expiry <= now
    ):
        data = {
            **data,
            "plan": "free",
            "subscription_status": "expired",
            "features": {
                **data.get("features", {}),
                "edge_tts": False,
                "premium_features": False,
            },
            "limits": {
                "max_actions": 6,
                "max_triggers": 10,
            },
        }

    return {
        **data,
        "connection_status": "offline_verified",
        "offline_verified_at": cached_at.isoformat(),
        "offline_until": (
            cached_at + timedelta(days=OFFLINE_GRACE_DAYS)
        ).isoformat(),
    }


def note_entitlement(data: dict | None) -> None:
    """Cache a short-lived Pro check for background-triggered Edge TTS."""

    global _pro_verified_until

    valid = bool(
        data
        and data.get("logged_in")
        and data.get("plan") == "pro"
        and data.get("subscription_status") == "active"
    )

    if valid and data.get("expiry_date"):
        try:
            expiry = datetime.fromisoformat(
                str(data["expiry_date"]).replace("Z", "+00:00")
            )
            valid = expiry > datetime.now(timezone.utc)
        except ValueError:
            valid = False

    with _entitlement_lock:
        _pro_verified_until = time.monotonic() + 300 if valid else 0.0


def cached_pro_is_active() -> bool:
    with _entitlement_lock:
        return _pro_verified_until > time.monotonic()
