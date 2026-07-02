"""ToyyibPay billing and subscription activation."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import hmac
import json
import secrets

import httpx

from app.auth.database import get_connection, is_postgres
from app.auth.repository import utc_now
from app.auth.service import SubscriptionError, current_subscription
from app.core.config import settings


def _api_url(endpoint: str) -> str:
    base = settings.toyyibpay_base_url.rstrip("/")
    if base.endswith("/index.php/api"):
        return f"{base}/{endpoint}"
    return f"{base}/index.php/api/{endpoint}"


def _safe_payload(payload: dict) -> str:
    clean = {
        key: value
        for key, value in payload.items()
        if key.lower() not in {"hash", "usersecretkey", "secretkey"}
    }
    return json.dumps(clean, separators=(",", ":"), default=str)


def _callback_amount_cents(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        ringgit = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None
    return int(
        (ringgit * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _insert_pending_payment(user: dict, external_reference: str) -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO payment_logs (
                user_id, provider, provider_reference,
                external_reference, amount_cents, currency,
                status, event_type, payload, created_at, updated_at
            )
            VALUES (?, 'toyyibpay', NULL, ?, ?, 'MYR',
                    'creating', 'create_bill', '{}', ?, ?)
            """,
            (
                user["id"],
                external_reference,
                settings.pro_price_cents,
                utc_now(),
                utc_now(),
            ),
        )
        connection.commit()


def _update_payment(
    external_reference: str,
    *,
    status: str,
    event_type: str,
    payload: dict,
    provider_reference: str | None = None,
) -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE payment_logs
            SET status = ?,
                event_type = ?,
                payload = ?,
                provider_reference = COALESCE(?, provider_reference),
                updated_at = ?
            WHERE external_reference = ?
            """,
            (
                status,
                event_type,
                _safe_payload(payload),
                provider_reference,
                utc_now(),
                external_reference,
            ),
        )
        connection.commit()


def create_toyyibpay_payment(user: dict) -> dict:
    """Create one fixed-price Pro bill for an authenticated user."""

    try:
        settings.require_payment_settings()
    except RuntimeError as error:
        raise SubscriptionError(
            "PAYMENT_NOT_CONFIGURED",
            str(error),
            503,
        ) from error

    external_reference = (
        f"LT{user['id']}{secrets.token_hex(8).upper()}"
    )
    _insert_pending_payment(user, external_reference)

    callback_url = settings.payment_callback_url
    return_url = settings.payment_return_url
    request_data = {
        "userSecretKey": settings.toyyibpay_secret_key,
        "categoryCode": settings.toyyibpay_category_code,
        "billName": "LiveTrigger Pro",
        "billDescription": "LiveTrigger Pro 30-day subscription (50% off)",
        "billPriceSetting": "1",
        # Registration does not collect a phone number. ToyyibPay rejects
        # required payer details when billPhone is empty, so the payment
        # page collects payer details while our signed external reference
        # continues to bind the bill to the authenticated account.
        "billPayorInfo": "0",
        "billAmount": str(settings.pro_price_cents),
        "billReturnUrl": return_url,
        "billCallbackUrl": callback_url,
        "billExternalReferenceNo": external_reference,
        "billTo": user.get("display_name") or "LiveTrigger User",
        "billEmail": user["email"],
        "billPhone": "",
        "billPaymentChannel": "0",
        "billExpiryDays": "3",
    }

    try:
        response = httpx.post(
            _api_url("createBill"),
            data=request_data,
            timeout=20.0,
        )
        response.raise_for_status()
        provider_data = response.json()
        bill_code = str(provider_data[0]["BillCode"]).strip()
        if not bill_code:
            raise ValueError("Empty BillCode")
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
        _update_payment(
            external_reference,
            status="create_failed",
            event_type="create_bill_failed",
            payload={"provider_error": type(error).__name__},
        )
        raise SubscriptionError(
            "PAYMENT_PROVIDER_ERROR",
            "ToyyibPay could not create a payment bill.",
            502,
        ) from error

    _update_payment(
        external_reference,
        status="pending",
        event_type="bill_created",
        payload={"bill_code": bill_code},
        provider_reference=bill_code,
    )

    return {
        "payment_url": f"{settings.payment_site_url}/{bill_code}",
        "bill_code": bill_code,
        "external_reference": external_reference,
        "amount_cents": settings.pro_price_cents,
        "currency": "MYR",
    }


def _verify_callback_hash(payload: dict) -> None:
    status = str(payload.get("status") or "")
    order_id = str(payload.get("order_id") or "")
    refno = str(payload.get("refno") or "")
    received = str(payload.get("hash") or "").lower()

    expected = hashlib.md5(
        (
            settings.toyyibpay_secret_key
            + status
            + order_id
            + refno
            + "ok"
        ).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()

    if not received or not hmac.compare_digest(received, expected):
        raise SubscriptionError(
            "INVALID_CALLBACK",
            "Payment callback signature is invalid.",
            400,
        )


def _payment_record(external_reference: str) -> dict:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, user_id, provider_reference, external_reference,
                   amount_cents, status
            FROM payment_logs
            WHERE external_reference = ?
            LIMIT 1
            """,
            (external_reference,),
        ).fetchone()

    if row is None:
        raise SubscriptionError(
            "PAYMENT_NOT_FOUND",
            "Payment reference was not found.",
            404,
        )
    return dict(row)


def _verify_success_with_provider(payment: dict) -> None:
    """Re-query ToyyibPay so a signed callback is not the sole proof."""

    try:
        response = httpx.post(
            _api_url("getBillTransactions"),
            data={
                "billCode": payment["provider_reference"],
                "billpaymentStatus": "1",
            },
            timeout=20.0,
        )
        response.raise_for_status()
        transactions = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise SubscriptionError(
            "PAYMENT_VERIFICATION_FAILED",
            "Payment could not be verified with ToyyibPay.",
            502,
        ) from error

    verified = any(
        str(transaction.get("billpaymentStatus")) == "1"
        and str(transaction.get("billExternalReferenceNo"))
        == payment["external_reference"]
        and _callback_amount_cents(transaction.get("billpaymentAmount"))
        == int(payment["amount_cents"])
        for transaction in transactions
        if isinstance(transaction, dict)
    )

    if not verified:
        raise SubscriptionError(
            "PAYMENT_NOT_VERIFIED",
            "ToyyibPay has not confirmed this payment as successful.",
            409,
        )


def _parse_expiry(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _activate_pro(payment: dict, payload: dict) -> dict:
    """Idempotently mark the payment paid and extend the Pro expiry."""

    with closing(get_connection()) as connection:
        lock_suffix = " FOR UPDATE" if is_postgres() else ""
        row = connection.execute(
            """
            SELECT id, user_id, status
            FROM payment_logs
            WHERE external_reference = ?
            """
            + lock_suffix,
            (payment["external_reference"],),
        ).fetchone()

        if row is None:
            raise SubscriptionError(
                "PAYMENT_NOT_FOUND",
                "Payment reference was not found.",
                404,
            )

        if row["status"] == "success":
            return current_subscription(int(row["user_id"]))

        subscription = connection.execute(
            """
            SELECT plan, status, expiry_date
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
            + lock_suffix,
            (row["user_id"],),
        ).fetchone()

        now = datetime.now(timezone.utc)
        current_expiry = (
            _parse_expiry(subscription["expiry_date"])
            if subscription
            and subscription["plan"] == "pro"
            and subscription["status"] == "active"
            else None
        )
        starts_at = current_expiry if current_expiry and current_expiry > now else now
        expiry = starts_at + timedelta(days=settings.pro_duration_days)

        connection.execute(
            """
            UPDATE payment_logs
            SET status = 'success',
                event_type = 'payment_success',
                payload = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (_safe_payload(payload), utc_now(), row["id"]),
        )
        connection.execute(
            """
            INSERT INTO subscriptions
                (user_id, plan, status, expiry_date, created_at)
            VALUES (?, 'pro', 'active', ?, ?)
            """,
            (row["user_id"], expiry.isoformat(), utc_now()),
        )
        connection.commit()

    return {
        "plan": "pro",
        "status": "active",
        "expiry_date": expiry.isoformat(),
    }


def process_callback(payload: dict) -> dict:
    """Validate a ToyyibPay callback and update the subscription."""

    try:
        settings.require_payment_settings()
    except RuntimeError as error:
        raise SubscriptionError(
            "PAYMENT_NOT_CONFIGURED",
            str(error),
            503,
        ) from error

    _verify_callback_hash(payload)

    external_reference = str(payload.get("order_id") or "")
    bill_code = str(payload.get("billcode") or "")
    status = str(payload.get("status") or "")
    payment = _payment_record(external_reference)

    if not bill_code or bill_code != payment["provider_reference"]:
        raise SubscriptionError(
            "INVALID_CALLBACK",
            "Payment bill reference does not match.",
            400,
        )

    received_cents = _callback_amount_cents(payload.get("amount"))
    if received_cents != int(payment["amount_cents"]):
        raise SubscriptionError(
            "INVALID_PAYMENT_AMOUNT",
            "Payment amount does not match the bill.",
            400,
        )

    if status == "1":
        _verify_success_with_provider(payment)
        subscription = _activate_pro(payment, payload)
        return {"ok": True, "status": "success", **subscription}

    mapped_status = "pending" if status == "2" else "failed"
    _update_payment(
        external_reference,
        status=mapped_status,
        event_type=f"payment_{mapped_status}",
        payload=payload,
    )
    return {"ok": True, "status": mapped_status}
