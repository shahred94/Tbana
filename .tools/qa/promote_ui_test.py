"""Promote the synthetic UI QA account to Pro for visual validation."""

from datetime import datetime, timedelta, timezone
import os

import psycopg


email = "codex-ui-1782714471977@example.invalid"
database_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]
now = datetime.now(timezone.utc)

with psycopg.connect(database_url) as conn:
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = %s",
        (email,),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO subscriptions
            (user_id, plan, status, expiry_date, created_at)
        VALUES (%s, 'pro', 'active', %s, %s)
        """,
        (user_id, now + timedelta(days=30), now),
    )
    conn.commit()

print("Synthetic UI account promoted to Pro.")
