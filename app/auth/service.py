"""Password, session, and subscription policy for TBana Stream."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import sqlite3
import threading

import bcrypt
from fastapi import Request

from app.auth.repository import (
    count_action_presets,
    count_event_triggers,
    record_device,
    utc_now,
)
from app.auth.database import (
    get_connection,
    is_postgres,
)


SESSION_COOKIE = "livetrigger_session"
SESSION_DAYS = 30
PASSWORD_RESET_MINUTES = 15
PASSWORD_RESET_MAX_ATTEMPTS = 5
PASSWORD_RESET_REQUEST_SECONDS = 60
subscription_write_lock = (
    threading.RLock()
)

PLAN_LIMITS = {
    "guest": {
        "max_actions": 0,
        "max_triggers": 0,
    },
    "free": {
        "max_actions": 6,
        "max_triggers": 10,
    },
    "pro": {
        "max_actions": None,
        "max_triggers": None,
    },
}

PLAN_FEATURES = {
    "guest": {
        "edge_tts": False,
        "cloud_backup": False,
        "premium_features": False,
    },
    "free": {
        "edge_tts": False,
        "cloud_backup": False,
        "premium_features": False,
    },
    "pro": {
        "edge_tts": True,
        "cloud_backup": True,
        "premium_features": True,
    },
}


class SubscriptionError(Exception):
    """An expected API error with a stable client-facing code."""

    def __init__(
        self,
        error: str,
        message: str,
        status_code: int = 403,
    ):

        super().__init__(
            message
        )

        self.error = error
        self.message = message
        self.status_code = status_code


def normalize_email(
    email: str,
) -> str:
    """Validate and normalize an account email."""

    normalized = str(
        email
        or
        ""
    ).strip().lower()

    if (
        len(normalized) > 254
        or
        not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            normalized,
        )
    ):

        raise SubscriptionError(
            "INVALID_EMAIL",
            "Please enter a valid email address.",
            400,
        )

    return normalized


def validate_password(
    password: str,
) -> bytes:
    """Validate bcrypt-compatible password length."""

    encoded = str(
        password
        or
        ""
    ).encode(
        "utf-8"
    )

    if len(encoded) < 8:

        raise SubscriptionError(
            "WEAK_PASSWORD",
            "Password must contain at least 8 characters.",
            400,
        )

    if len(encoded) > 72:

        raise SubscriptionError(
            "PASSWORD_TOO_LONG",
            "Password must not exceed 72 UTF-8 bytes.",
            400,
        )

    return encoded


def hash_password(
    password: str,
) -> str:
    """Hash a password using bcrypt."""

    return bcrypt.hashpw(
        validate_password(
            password
        ),
        bcrypt.gensalt(
            rounds=12
        ),
    ).decode(
        "ascii"
    )


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """Safely verify a bcrypt password."""

    try:

        return bcrypt.checkpw(
            validate_password(
                password
            ),
            password_hash.encode(
                "ascii"
            ),
        )

    except (
        SubscriptionError,
        ValueError,
        TypeError,
    ):

        return False


def token_hash(
    token: str,
) -> str:
    """Hash a session token before database lookup/storage."""

    return hashlib.sha256(
        token.encode(
            "utf-8"
        )
    ).hexdigest()


def register_account(
    email: str,
    password: str,
    display_name: str,
) -> dict:
    """Create a free account and its initial subscription."""

    normalized_email = (
        normalize_email(
            email
        )
    )

    clean_name = str(
        display_name
        or
        ""
    ).strip()

    if not clean_name:

        clean_name = (
            normalized_email.split(
                "@",
                1,
            )[0]
        )

    if len(clean_name) > 80:

        raise SubscriptionError(
            "INVALID_DISPLAY_NAME",
            "Display name must not exceed 80 characters.",
            400,
        )

    password_hash = hash_password(
        password
    )

    now = utc_now()

    try:

        with closing(
            get_connection()
        ) as connection:

            insert_sql = (
                """
                INSERT INTO users
                (
                    email,
                    password_hash,
                    display_name,
                    created_at,
                    last_login
                )
                VALUES (?, ?, ?, ?, ?)
                """
                + (" RETURNING id" if is_postgres() else "")
            )

            cursor = connection.execute(
                insert_sql,
                (
                    normalized_email,
                    password_hash,
                    clean_name,
                    now,
                    now,
                ),
            )

            if is_postgres():
                user_id = int(cursor.fetchone()["id"])
            else:
                user_id = int(cursor.lastrowid)

            connection.execute(
                """
                INSERT INTO subscriptions
                (
                    user_id,
                    plan,
                    status,
                    expiry_date,
                    created_at
                )
                VALUES (?, 'free', 'active', NULL, ?)
                """,
                (
                    user_id,
                    now,
                ),
            )

            connection.commit()

    except sqlite3.IntegrityError as error:

        raise SubscriptionError(
            "EMAIL_ALREADY_REGISTERED",
            "An account already exists for this email.",
            409,
        ) from error

    record_device(
        user_id
    )

    return {
        "id": user_id,
        "email": normalized_email,
        "display_name": clean_name,
    }


def authenticate_account(
    email: str,
    password: str,
) -> dict:
    """Verify credentials without revealing which field was wrong."""

    normalized_email = (
        normalize_email(
            email
        )
    )

    with closing(
        get_connection()
    ) as connection:

        row = connection.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                display_name
            FROM users
            WHERE email = ?
            """,
            (
                normalized_email,
            ),
        ).fetchone()

        if (
            row is None
            or
            not verify_password(
                password,
                row["password_hash"],
            )
        ):

            raise SubscriptionError(
                "INVALID_CREDENTIALS",
                "Email or password is incorrect.",
                401,
            )

        now = utc_now()

        connection.execute(
            """
            UPDATE users
            SET last_login = ?
            WHERE id = ?
            """,
            (
                now,
                row["id"],
            ),
        )

        connection.commit()

        user = {
            "id": int(
                row["id"]
            ),
            "email": row["email"],
            "display_name": row[
                "display_name"
            ],
        }

    record_device(
        user["id"]
    )

    return user


def request_password_reset(
    email: str,
) -> dict:
    """Create and email a short-lived reset code without user enumeration."""

    from app.auth.email import send_password_reset_code
    from app.core.config import settings

    if (
        settings.app_env == "production"
        and
        not settings.email_enabled
    ):

        raise SubscriptionError(
            "PASSWORD_RESET_UNAVAILABLE",
            "Password recovery is temporarily unavailable.",
            503,
        )

    normalized_email = normalize_email(
        email
    )
    generic_response = {
        "message": (
            "If an account exists for that email, "
            "a reset code has been sent."
        )
    }
    now = datetime.now(
        timezone.utc
    )

    with closing(
        get_connection()
    ) as connection:

        user = connection.execute(
            """
            SELECT id, email
            FROM users
            WHERE email = ?
            """,
            (
                normalized_email,
            ),
        ).fetchone()

        if user is None:

            return generic_response

        latest = connection.execute(
            """
            SELECT created_at
            FROM password_reset_tokens
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (
                user["id"],
            ),
        ).fetchone()

        if latest is not None:

            try:

                latest_at = datetime.fromisoformat(
                    str(
                        latest["created_at"]
                    ).replace(
                        "Z",
                        "+00:00",
                    )
                )
                if latest_at.tzinfo is None:
                    latest_at = latest_at.replace(
                        tzinfo=timezone.utc
                    )

                if (
                    now
                    -
                    latest_at.astimezone(
                        timezone.utc
                    )
                ).total_seconds() < PASSWORD_RESET_REQUEST_SECONDS:

                    return generic_response

            except (
                TypeError,
                ValueError,
            ):

                pass

        code = f"{secrets.randbelow(100_000_000):08d}"
        expires_at = (
            now
            +
            timedelta(
                minutes=PASSWORD_RESET_MINUTES
            )
        )

        connection.execute(
            """
            DELETE FROM password_reset_tokens
            WHERE expires_at <= ? OR used_at IS NOT NULL
            """,
            (
                utc_now(),
            ),
        )
        connection.execute(
            """
            INSERT INTO password_reset_tokens
            (
                user_id,
                token_hash,
                expires_at,
                attempts,
                used_at,
                created_at
            )
            VALUES (?, ?, ?, 0, NULL, ?)
            """,
            (
                user["id"],
                token_hash(
                    code
                ),
                expires_at.isoformat(),
                now.isoformat(),
            ),
        )
        connection.commit()

    if settings.email_enabled:

        try:

            send_password_reset_code(
                normalized_email,
                code,
                PASSWORD_RESET_MINUTES,
            )

        except Exception as error:

            print(
                "[AUTH] Password reset email failed:",
                type(error).__name__,
            )
            raise SubscriptionError(
                "PASSWORD_RESET_UNAVAILABLE",
                "Password recovery is temporarily unavailable.",
                503,
            ) from error

    elif settings.app_env != "production":

        generic_response["reset_code"] = code
        generic_response["development_only"] = True

    return generic_response


def reset_password(
    email: str,
    code: str,
    new_password: str,
) -> dict:
    """Consume a reset code, replace the password, and revoke sessions."""

    normalized_email = normalize_email(
        email
    )
    clean_code = str(
        code
        or
        ""
    ).strip()

    if (
        len(clean_code) != 8
        or
        not clean_code.isdigit()
    ):

        raise SubscriptionError(
            "INVALID_RESET_CODE",
            "The reset code is invalid or has expired.",
            400,
        )

    new_password_hash = hash_password(
        new_password
    )
    now = utc_now()

    with closing(
        get_connection()
    ) as connection:

        row = connection.execute(
            """
            SELECT
                password_reset_tokens.id,
                password_reset_tokens.user_id,
                password_reset_tokens.token_hash,
                password_reset_tokens.attempts
            FROM password_reset_tokens
            JOIN users
                ON users.id = password_reset_tokens.user_id
            WHERE
                users.email = ?
                AND password_reset_tokens.used_at IS NULL
                AND password_reset_tokens.expires_at > ?
                AND password_reset_tokens.attempts < ?
            ORDER BY
                password_reset_tokens.created_at DESC,
                password_reset_tokens.id DESC
            LIMIT 1
            """,
            (
                normalized_email,
                now,
                PASSWORD_RESET_MAX_ATTEMPTS,
            ),
        ).fetchone()

        if row is None:

            raise SubscriptionError(
                "INVALID_RESET_CODE",
                "The reset code is invalid or has expired.",
                400,
            )

        if not secrets.compare_digest(
            row["token_hash"],
            token_hash(
                clean_code
            ),
        ):

            connection.execute(
                """
                UPDATE password_reset_tokens
                SET attempts = attempts + 1
                WHERE id = ?
                """,
                (
                    row["id"],
                ),
            )
            connection.commit()

            raise SubscriptionError(
                "INVALID_RESET_CODE",
                "The reset code is invalid or has expired.",
                400,
            )

        connection.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            (
                new_password_hash,
                row["user_id"],
            ),
        )
        connection.execute(
            """
            UPDATE password_reset_tokens
            SET used_at = ?
            WHERE user_id = ? AND used_at IS NULL
            """,
            (
                now,
                row["user_id"],
            ),
        )
        connection.execute(
            """
            DELETE FROM sessions
            WHERE user_id = ?
            """,
            (
                row["user_id"],
            ),
        )
        connection.commit()

    return {
        "message": (
            "Password updated. Please sign in with your new password."
        )
    }


def create_session(
    user_id: int,
) -> tuple[str, datetime]:
    """Create a random session and store only its SHA-256 hash."""

    token = secrets.token_urlsafe(
        48
    )

    expires_at = (
        datetime.now(
            timezone.utc
        )
        +
        timedelta(
            days=SESSION_DAYS
        )
    )

    with closing(
        get_connection()
    ) as connection:

        connection.execute(
            """
            DELETE FROM sessions
            WHERE expires_at <= ?
            """,
            (
                utc_now(),
            ),
        )

        connection.execute(
            """
            INSERT INTO sessions
            (
                user_id,
                token_hash,
                expires_at,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                token_hash(
                    token
                ),
                expires_at.isoformat(),
                utc_now(),
            ),
        )

        connection.commit()

    return token, expires_at


def delete_session(
    token: str | None,
) -> None:
    """Delete one authenticated session."""

    if not token:

        return

    with closing(
        get_connection()
    ) as connection:

        connection.execute(
            """
            DELETE FROM sessions
            WHERE token_hash = ?
            """,
            (
                token_hash(
                    token
                ),
            ),
        )

        connection.commit()


def current_subscription(
    user_id: int,
) -> dict:
    """Return the newest subscription and effective entitlement."""

    with closing(
        get_connection()
    ) as connection:

        row = connection.execute(
            """
            SELECT
                plan,
                status,
                expiry_date
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY
                created_at DESC,
                id DESC
            LIMIT 1
            """,
            (
                user_id,
            ),
        ).fetchone()

    if row is None:

        return {
            "plan": "free",
            "status": "active",
            "expiry_date": None,
        }

    plan = row["plan"]
    status = row["status"]
    raw_expiry = row["expiry_date"]
    expiry_date = (
        raw_expiry.isoformat()
        if isinstance(raw_expiry, datetime)
        else raw_expiry
    )

    if (
        expiry_date
        and
        expiry_date
        <=
        utc_now()
        and
        status == "active"
    ):

        status = "expired"

    effective_plan = (
        "pro"
        if (
            plan == "pro"
            and
            status == "active"
        )
        else
        "free"
    )

    return {
        "plan": effective_plan,
        "status": status,
        "expiry_date": expiry_date,
    }


def user_from_token(
    token: str | None,
) -> dict | None:
    """Resolve a valid session token to a user entitlement."""

    if not token:

        return None

    with closing(
        get_connection()
    ) as connection:

        row = connection.execute(
            """
            SELECT
                users.id,
                users.email,
                users.display_name,
                sessions.expires_at
            FROM sessions
            JOIN users
                ON users.id = sessions.user_id
            WHERE
                sessions.token_hash = ?
                AND sessions.expires_at > ?
            LIMIT 1
            """,
            (
                token_hash(
                    token
                ),
                utc_now(),
            ),
        ).fetchone()

    if row is None:

        return None

    subscription = (
        current_subscription(
            int(
                row["id"]
            )
        )
    )

    return {
        "id": int(
            row["id"]
        ),
        "email": row["email"],
        "display_name": row[
            "display_name"
        ],
        "plan": subscription[
            "plan"
        ],
        "subscription_status":
            subscription["status"],
        "expiry_date":
            subscription["expiry_date"],
    }


def current_user(
    request: Request,
) -> dict | None:
    """Resolve the request's HttpOnly cookie."""

    token = request.cookies.get(SESSION_COOKIE)

    from app.auth import remote_client

    if remote_client.enabled():
        data = remote_client.me(token)
        if not data.get("logged_in"):
            return None
        return {
            "id": data.get("id"),
            "email": data["email"],
            "display_name": data["display_name"],
            "plan": data["plan"],
            "subscription_status": data["subscription_status"],
            "expiry_date": data.get("expiry_date"),
            "connection_status": data.get(
                "connection_status",
                "connected",
            ),
            "verified_at": data.get("verified_at"),
            "offline_verified_at": data.get("offline_verified_at"),
            "offline_until": data.get("offline_until"),
        }

    return user_from_token(token)


def require_authenticated(
    request: Request,
    message: str,
) -> dict:
    """Require a valid login for a protected operation."""

    user = current_user(
        request
    )

    if user is None:

        raise SubscriptionError(
            "LOGIN_REQUIRED",
            message,
            401,
        )

    return user


def require_feature(
    request: Request,
    feature: str,
    message: str,
) -> dict:
    """Require a plan feature such as Edge TTS."""

    user = require_authenticated(
        request,
        "Please login to use this feature.",
    )

    if not PLAN_FEATURES[
        user["plan"]
    ].get(
        feature,
        False,
    ):

        raise SubscriptionError(
            "PRO_REQUIRED",
            message,
            403,
        )

    return user


def enforce_action_creation(
    request: Request,
) -> dict:
    """Enforce guest and Free Action Library limits."""

    user = require_authenticated(
        request,
        "Please login to create actions.",
    )

    maximum = PLAN_LIMITS[
        user["plan"]
    ]["max_actions"]

    if (
        maximum is not None
        and
        count_action_presets()
        >=
        maximum
    ):

        raise SubscriptionError(
            "FREE_LIMIT_REACHED",
            (
                "Free plan allows up to "
                f"{maximum} actions only."
            ),
            403,
        )

    return user


def enforce_trigger_creation(
    request: Request,
) -> dict:
    """Enforce guest and Free event-trigger limits."""

    user = require_authenticated(
        request,
        "Please login to create event triggers.",
    )

    maximum = PLAN_LIMITS[
        user["plan"]
    ]["max_triggers"]

    if (
        maximum is not None
        and
        count_event_triggers()
        >=
        maximum
    ):

        raise SubscriptionError(
            "FREE_LIMIT_REACHED",
            (
                "Free plan allows up to "
                f"{maximum} event triggers only."
            ),
            403,
        )

    return user


def enforce_import_limits(
    request: Request,
    action_count: int | None,
    trigger_count: int | None,
) -> dict:
    """Validate replacement backup counts before an import transaction."""

    user = require_authenticated(
        request,
        "Please login to restore actions and event triggers.",
    )

    limits = PLAN_LIMITS[
        user["plan"]
    ]

    if (
        action_count is not None
        and
        limits["max_actions"] is not None
        and
        action_count
        >
        limits["max_actions"]
    ):

        raise SubscriptionError(
            "FREE_LIMIT_REACHED",
            (
                "Free plan allows up to "
                f"{limits['max_actions']} actions only."
            ),
            403,
        )

    if (
        trigger_count is not None
        and
        limits["max_triggers"] is not None
        and
        trigger_count
        >
        limits["max_triggers"]
    ):

        raise SubscriptionError(
            "FREE_LIMIT_REACHED",
            (
                "Free plan allows up to "
                f"{limits['max_triggers']} "
                "event triggers only."
            ),
            403,
        )

    return user


def auth_response(
    user: dict | None,
) -> dict:
    """Build the stable /api/auth/me response."""

    if user is None:

        return {
            "logged_in": False,
            "plan": "guest",
            "subscription_status":
                "disconnected",
            "limits": PLAN_LIMITS[
                "guest"
            ],
            "features": PLAN_FEATURES[
                "guest"
            ],
            "usage": {
                "actions":
                    count_action_presets(),
                "triggers":
                    count_event_triggers(),
            },
            "verified_at": utc_now(),
        }

    return {
        "logged_in": True,
        "email": user["email"],
        "display_name":
            user["display_name"],
        "plan": user["plan"],
        "subscription_status":
            user["subscription_status"],
        "expiry_date":
            user["expiry_date"],
        "connection_status": user.get(
            "connection_status",
            "connected",
        ),
        "offline_verified_at": user.get(
            "offline_verified_at"
        ),
        "offline_until": user.get(
            "offline_until"
        ),
        "limits": PLAN_LIMITS[
            user["plan"]
        ],
        "features": PLAN_FEATURES[
            user["plan"]
        ],
        "usage": {
            "actions":
                count_action_presets(),
            "triggers":
                count_event_triggers(),
        },
        "verified_at": user.get(
            "verified_at"
        ) or utc_now(),
    }


def active_pro_session_exists() -> bool:
    """Return whether a currently logged-in Pro entitlement exists."""

    from app.auth import remote_client

    if remote_client.enabled():
        return remote_client.cached_pro_is_active()

    with closing(
        get_connection()
    ) as connection:

        rows = connection.execute(
            """
            SELECT DISTINCT sessions.user_id
            FROM sessions
            WHERE sessions.expires_at > ?
            """,
            (
                utc_now(),
            ),
        ).fetchall()

    return any(
        current_subscription(
            int(
                row["user_id"]
            )
        )["plan"]
        ==
        "pro"
        for row in rows
    )

def active_authenticated_session_exists() -> bool:
    """Return whether runtime actions may execute for a logged-in account."""

    return active_runtime_plan() is not None

def active_runtime_plan() -> str | None:
    """Return the strongest active desktop plan, or None for a guest."""

    from app.auth import remote_client

    if remote_client.enabled():
        cached = remote_client.cached_state()
        if not cached or not cached.get("logged_in"):
            return None
        plan = str(cached.get("plan") or "free")
        return plan if plan in PLAN_LIMITS else "free"

    with closing(
        get_connection()
    ) as connection:

        rows = connection.execute(
            """
            SELECT DISTINCT user_id
            FROM sessions
            WHERE expires_at > ?
            """,
            (
                utc_now(),
            ),
        ).fetchall()

    plans = {
        current_subscription(
            int(row["user_id"])
        )["plan"]
        for row in rows
    }

    if "pro" in plans:
        return "pro"
    if plans:
        return "free"
    return None

def enforce_runtime_item(
    request: Request,
    item_type: str,
    item_id: int,
) -> dict:
    """Require login and ensure a saved item is within the account limit."""

    user = require_authenticated(
        request,
        "Please login to use saved actions and events.",
    )

    if runtime_item_is_allowed(
        item_type,
        item_id,
        user["plan"],
    ):
        return user

    limit_name = (
        "max_actions"
        if item_type == "action"
        else "max_triggers"
    )
    maximum = PLAN_LIMITS[user["plan"]][limit_name]

    raise SubscriptionError(
        "PLAN_ITEM_LOCKED",
        (
            f"Your plan can use the first {maximum} "
            f"{item_type}s only. Delete an earlier item or upgrade to Pro."
        ),
        403,
    )

def runtime_allowed_item_ids(
    item_type: str,
    plan: str,
) -> set[int] | None:
    """Return usable IDs for a plan, or None when the plan is unlimited."""

    config = {
        "action": (
            "action_presets",
            "max_actions",
        ),
        "trigger": (
            "event_triggers",
            "max_triggers",
        ),
    }

    if item_type not in config:
        raise ValueError(
            f"Unsupported runtime item type: {item_type}"
        )

    table, limit_name = config[item_type]
    safe_plan = plan if plan in PLAN_LIMITS else "free"
    maximum = PLAN_LIMITS[safe_plan][limit_name]

    if maximum is None:
        return None
    if maximum <= 0:
        return set()

    with closing(
        get_connection()
    ) as connection:

        rows = connection.execute(
            f"""
            SELECT id
            FROM {table}
            ORDER BY id
            LIMIT ?
            """,
            (
                maximum,
            ),
        ).fetchall()

    return {
        int(row["id"])
        for row in rows
    }

def runtime_item_is_allowed(
    item_type: str,
    item_id: int,
    plan: str | None = None,
) -> bool:
    """Return whether one saved action or trigger is usable at runtime."""

    effective_plan = plan or active_runtime_plan()
    if effective_plan is None:
        return False

    allowed_ids = runtime_allowed_item_ids(
        item_type,
        effective_plan,
    )

    return (
        allowed_ids is None
        or int(item_id) in allowed_ids
    )
