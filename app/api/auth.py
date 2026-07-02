"""LiveTrigger account and session API."""

from fastapi import (
    APIRouter,
    Request,
    Response,
)
from pydantic import BaseModel

from app.auth.service import (
    SESSION_COOKIE,
    auth_response,
    authenticate_account,
    create_session,
    current_subscription,
    current_user,
    delete_session,
    register_account,
)
from app.auth import remote_client
from app.core.config import settings


router = APIRouter(
    prefix="/api/auth",
    tags=[
        "Authentication"
    ],
)


class RegisterRequest(BaseModel):

    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):

    email: str
    password: str


def set_session_cookie(
    response: Response,
    token: str,
    expires_at,
) -> None:
    """Set a localhost-compatible secure session cookie."""

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        expires=expires_at,
        httponly=True,
        samesite="strict",
        secure=settings.secure_cookie,
        path="/",
    )


@router.post("/register")
def register(
    payload: RegisterRequest,
    response: Response,
):

    if remote_client.enabled():
        data, token = remote_client.register(
            payload.model_dump()
        )
        if not token:
            from app.auth.service import SubscriptionError
            raise SubscriptionError(
                "SESSION_ERROR",
                "Subscription server did not create a session.",
                502,
            )
        set_session_cookie(response, token, None)
        return data

    user = register_account(
        payload.email,
        payload.password,
        payload.display_name,
    )

    token, expires_at = (
        create_session(
            user["id"]
        )
    )

    set_session_cookie(
        response,
        token,
        expires_at,
    )

    return auth_response(
        {
            **user,
            "plan": "free",
            "subscription_status":
                "active",
            "expiry_date": None,
        }
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
):

    if remote_client.enabled():
        data, token = remote_client.login(
            payload.model_dump()
        )
        if not token:
            from app.auth.service import SubscriptionError
            raise SubscriptionError(
                "SESSION_ERROR",
                "Subscription server did not create a session.",
                502,
            )
        set_session_cookie(response, token, None)
        return data

    user = authenticate_account(
        payload.email,
        payload.password,
    )

    token, expires_at = (
        create_session(
            user["id"]
        )
    )

    set_session_cookie(
        response,
        token,
        expires_at,
    )

    request_user = {
        **user,
        "plan": "free",
        "subscription_status":
            "active",
        "expiry_date": None,
    }

    subscription = (
        current_subscription(
            user["id"]
        )
    )

    request_user.update({
        "plan": subscription["plan"],
        "subscription_status":
            subscription["status"],
        "expiry_date":
            subscription["expiry_date"],
    })

    return auth_response(
        request_user
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
):

    token = request.cookies.get(SESSION_COOKIE)

    if remote_client.enabled():
        remote_client.logout(token)
    else:
        delete_session(token)

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        samesite="strict",
    )

    return {
        "message": "Signed out"
    }


@router.get("/me")
def me(
    request: Request,
):

    return auth_response(current_user(request))
