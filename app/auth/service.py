"""Password, session, and subscription policy for LiveTrigger."""

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
        "max_triggers": 30,
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
