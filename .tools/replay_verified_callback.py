"""Replay the paid sandbox callback after the multipart parser fix."""

import hashlib
import json
import os

import httpx


status = "1"
order_id = "LT4752B31076B07AFB8"
refno = "TP2606291015863341"
secret = os.environ["TOYYIBPAY_SECRET_KEY"]
signature = hashlib.md5(
    f"{secret}{status}{order_id}{refno}ok".encode("utf-8"),
    usedforsecurity=False,
).hexdigest()
payload = {
    "refno": refno,
    "status": status,
    "reason": "Approved",
    "billcode": "dpij9kat",
    "order_id": order_id,
    "amount": "30.00",
    "transaction_time": "2026-06-29 13:12:35",
    "hash": signature,
}

response = httpx.post(
    os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/api/payment/callback",
    files={key: (None, value) for key, value in payload.items()},
    timeout=30,
)
try:
    body = response.json()
except ValueError:
    body = response.text[:300]

print(json.dumps({"status_code": response.status_code, "body": body}))
