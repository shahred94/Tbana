"""Subscription and ToyyibPay HTTP endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth import remote_client
from app.auth.service import (
    SESSION_COOKIE,
    auth_response,
    current_user,
    require_authenticated,
)
from app.subscription.service import (
    create_toyyibpay_payment,
    process_callback,
)


subscription_router = APIRouter(
    prefix="/api/subscription",
    tags=["Subscription"],
)
payment_router = APIRouter(
    prefix="/api/payment",
    tags=["Payment"],
)


@subscription_router.post("/create-payment")
def create_payment(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if remote_client.enabled():
        return remote_client.create_payment(token)

    user = require_authenticated(
        request,
        "Please login before upgrading to Pro.",
    )
    return create_toyyibpay_payment(user)


@subscription_router.get("/status")
def subscription_status(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if remote_client.enabled():
        return remote_client.subscription_status(token)

    return auth_response(
        require_authenticated(
            request,
            "Please login to view subscription status.",
        )
    )


@payment_router.post("/callback")
async def payment_callback(request: Request):
    form = await request.form()
    payload = {
        str(key): str(value)
        for key, value in form.multi_items()
    }
    return process_callback(payload)


@payment_router.get("/return", response_class=HTMLResponse)
def payment_return():
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>TBana Stream Payment</title></head>
      <body style="font-family:sans-serif;max-width:600px;margin:60px auto">
        <h1>Payment submitted</h1>
        <p>Return to TBana Stream and refresh your subscription status.</p>
      </body>
    </html>
    """
