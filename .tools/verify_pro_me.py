"""Create a short-lived synthetic session and verify production /auth/me."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets

import httpx
import psycopg


database_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]
token = secrets.token_urlsafe(48)
token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
now = datetime.now(timezone.utc)

with psycopg.connect(database_url) as conn:
    user_id = conn.execute(
        """
        SELECT p.user_id
        FROM payment_logs AS p
        WHERE p.external_reference = %s
        """,
        ("LT4752B31076B07AFB8",),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO sessions (user_id, token_hash, expires_at, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, token_hash, now + timedelta(minutes=5), now),
    )
    conn.commit()

try:
    response = httpx.get(
        "https://subscription-api-production-2d7f.up.railway.app/api/auth/me",
        cookies={"livetrigger_session": token},
        timeout=30,
    )
    data = response.json()
    safe = {
        "status_code": response.status_code,
        "logged_in": data.get("logged_in"),
        "plan": data.get("plan"),
        "subscription_status": data.get("subscription_status"),
        "max_actions": data.get("limits", {}).get("max_actions"),
        "max_triggers": data.get("limits", {}).get("max_triggers"),
        "edge_tts": data.get("features", {}).get("edge_tts"),
        "expiry_date": data.get("expiry_date"),
    }
    print(json.dumps(safe, default=str))
finally:
    with psycopg.connect(database_url) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))
        conn.commit()
