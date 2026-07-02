"""Inspect safe ToyyibPay transaction fields for the sandbox test bill."""

import json
import os

import httpx


base = os.environ["TOYYIBPAY_BASE_URL"].rstrip("/")
endpoint = (
    f"{base}/getBillTransactions"
    if base.endswith("/index.php/api")
    else f"{base}/index.php/api/getBillTransactions"
)
response = httpx.post(
    endpoint,
    data={"billCode": "dpij9kat"},
    timeout=30,
)
response.raise_for_status()

allowed = {
    "billStatus",
    "billpaymentStatus",
    "billpaymentAmount",
    "billpaymentInvoiceNo",
    "billExternalReferenceNo",
    "billPaymentDate",
}
safe = [
    {key: value for key, value in transaction.items() if key in allowed}
    for transaction in response.json()
    if isinstance(transaction, dict)
]
print(json.dumps(safe, default=str))
