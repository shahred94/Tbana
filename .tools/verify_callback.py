"""Verify the completed sandbox callback using PostgreSQL public TCP."""

import json
import os

import psycopg
from psycopg.rows import dict_row


external_reference = "LT4752B31076B07AFB8"
database_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]

with psycopg.connect(database_url, row_factory=dict_row) as conn:
    row = conn.execute(
        """
        SELECT
            p.status AS payment_status,
            p.provider_reference AS bill_code,
            p.amount_cents,
            p.event_type,
            s.plan,
            s.status AS subscription_status,
            s.expiry_date,
            u.email
        FROM payment_logs AS p
        JOIN users AS u ON u.id = p.user_id
        LEFT JOIN LATERAL (
            SELECT plan, status, expiry_date
            FROM subscriptions
            WHERE user_id = p.user_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        ) AS s ON TRUE
        WHERE p.external_reference = %s
        LIMIT 1
        """,
        (external_reference,),
    ).fetchone()

safe = dict(row) if row else {}
if "email" in safe:
    safe["test_account"] = str(safe.pop("email")).startswith("codex-callback-")

print(json.dumps(safe, default=str))
