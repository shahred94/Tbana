"""Auth repository supporting PostgreSQL production and SQLite development."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
import platform
import sqlite3
import uuid

from app.auth.database import get_connection, is_postgres


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        last_login TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        plan TEXT NOT NULL DEFAULT 'free'
            CHECK (plan IN ('free', 'pro')),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'expired', 'cancelled')),
        expiry_date TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        machine_id TEXT NOT NULL,
        device_name TEXT NOT NULL,
        last_seen TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        UNIQUE (user_id, machine_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        provider TEXT,
        provider_reference TEXT,
        external_reference TEXT,
        amount_cents INTEGER,
        currency TEXT,
        status TEXT NOT NULL,
        event_type TEXT,
        payload TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ
    )
    """,
]

SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_login TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free'
            CHECK (plan IN ('free', 'pro')),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'expired', 'cancelled')),
        expiry_date TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        machine_id TEXT NOT NULL,
        device_name TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE (user_id, machine_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        provider TEXT,
        provider_reference TEXT,
        external_reference TEXT,
        amount_cents INTEGER,
        currency TEXT,
        status TEXT NOT NULL,
        event_type TEXT,
        payload TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    )
    """,
]


def initialize_auth_tables() -> None:
    """Apply idempotent auth/payment migrations on application startup."""

    with closing(get_connection()) as connection:
        for statement in POSTGRES_SCHEMA if is_postgres() else SQLITE_SCHEMA:
            connection.execute(statement)

        if is_postgres():
            for statement in (
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS provider TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS provider_reference TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS external_reference TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS amount_cents INTEGER",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS currency TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS status TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS event_type TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS payload TEXT",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",
                "ALTER TABLE payment_logs "
                "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
            ):
                connection.execute(statement)
        else:
            for statement in (
                "ALTER TABLE payment_logs ADD COLUMN external_reference TEXT",
                "ALTER TABLE payment_logs ADD COLUMN updated_at TEXT",
            ):
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError:
                    pass

        for statement in (
            """
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user_created
            ON subscriptions(user_id, created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_token_expiry
            ON sessions(token_hash, expires_at)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_external_reference
            ON payment_logs(external_reference)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_payment_provider_reference
            ON payment_logs(provider_reference)
            """,
        ):
            connection.execute(statement)

        connection.commit()


def machine_identity() -> tuple[str, str]:
    raw_id = f"{platform.system()}|{platform.machine()}|{uuid.getnode()}"
    machine_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    device_name = (
        os.environ.get("COMPUTERNAME") or platform.node() or "Windows PC"
    )
    return machine_id, device_name


def record_device(user_id: int) -> None:
    machine_id, device_name = machine_identity()
    now = utc_now()

    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO devices
                (user_id, machine_id, device_name, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, machine_id)
            DO UPDATE SET
                device_name = excluded.device_name,
                last_seen = excluded.last_seen
            """,
            (user_id, machine_id, device_name, now, now),
        )
        connection.commit()


def count_action_presets() -> int:
    """Cloud stores entitlements only; action data remains on the desktop."""

    if is_postgres():
        return 0

    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM action_presets"
        ).fetchone()
        return int(row["total"])


def count_event_triggers() -> int:
    if is_postgres():
        return 0

    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM event_triggers"
        ).fetchone()
        return int(row["total"])
