"""One-off sanitized ToyyibPay createBill diagnostic."""

import json
import os
from urllib.parse import urlsplit

import httpx


base = os.environ["TOYYIBPAY_BASE_URL"].rstrip("/")
endpoint = (
    f"{base}/createBill"
    if base.endswith("/index.php/api")
    else f"{base}/index.php/api/createBill"
)
public_base = os.environ["PUBLIC_BASE_URL"].rstrip("/")
payload = {
    "userSecretKey": os.environ["TOYYIBPAY_SECRET_KEY"],
    "categoryCode": os.environ["TOYYIBPAY_CATEGORY_CODE"],
    "billName": "TBana Stream Pro",
    "billDescription": "TBana Stream Pro subscription",
    "billPriceSetting": "1",
    "billPayorInfo": "0",
    "billAmount": os.environ["PRO_PRICE_CENTS"],
    "billReturnUrl": f"{public_base}/api/payment/return",
    "billCallbackUrl": f"{public_base}/api/payment/callback",
    "billExternalReferenceNo": "LTDIAGNOSTICOPEN",
    "billTo": "TBana Stream Test",
    "billEmail": "codex-test@example.com",
    "billPhone": "",
    "billPaymentChannel": "0",
    "billExpiryDays": "3",
}

response = httpx.post(endpoint, data=payload, timeout=30)
try:
    provider_response = response.json()
except ValueError:
    provider_response = response.text[:500]

print(
    json.dumps(
        {
            "host": urlsplit(endpoint).netloc,
            "status_code": response.status_code,
            "response": provider_response,
        },
        default=str,
    )
)
