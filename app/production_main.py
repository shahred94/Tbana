"""Self-hosted production entry point for authentication and billing."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.subscription import payment_router, subscription_router
from app.auth.repository import initialize_auth_tables
from app.auth.service import SubscriptionError
from app.core.config import settings


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Validate configuration and initialize PostgreSQL before serving."""

    settings.require_production_settings()
    initialize_auth_tables()
    yield


app = FastAPI(
    title="Tbana Stream Subscription API",
    debug=False,
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.trusted_hosts),
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


@app.exception_handler(SubscriptionError)
async def subscription_error_handler(
    request: Request,
    error: SubscriptionError,
):
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": error.error,
            "message": error.message,
        },
    )


app.include_router(auth_router)
app.include_router(subscription_router)
app.include_router(payment_router)


@app.get("/")
def root():
    return {
        "service": "Tbana Stream Subscription API",
        "status": "ok",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
