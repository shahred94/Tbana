"""Read the latest synthetic production test payment without secrets."""

import json
import os

import psycopg
from psycopg.rows import dict_row


with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
    row = conn.execute(
        """
        SELECT p.provider_reference, p.external_reference, p.status, u.email
        FROM payment_logs AS p
        JOIN users AS u ON u.id = p.user_id
        WHERE u.email LIKE 'codex-live-%@example.invalid'
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT 1
        """
    ).fetchone()

print(json.dumps(dict(row) if row else {}))
