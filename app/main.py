"""LiveTrigger Main Application."""


import asyncio


from fastapi import FastAPI, Request
from fastapi.responses import (
    JSONResponse,
    RedirectResponse,
)

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


from app.storage.sqlite_store import (
    initialize_database,
    get_setting,
)

from app.api import actions_v2
from app.api.auth import (
    router as auth_router,
)
from app.api.subscription import (
    payment_router,
    subscription_router,
)
from app.core.config import settings
from app.core.paths import data_path, resource_path
from app.auth.repository import (
    initialize_auth_tables,
)
from app.auth.service import (
    SubscriptionError,
)

from app.api.routes import (
    router as gift_router,
)


from app.api.events import (
    router as event_router,
)

from app.api.settings import (
    router as settings_router,
)



from app.api.event_test import (
    router as event_test_router,
)

from app.api.tiktok import (
    router as tiktok_router,
)

from app.api.simulator import (
    router as simulator_router,
)

from app.api.websocket import (
    router as websocket_router,
)

from app.api.gift_catalog import (
    router as gift_catalog_router,
)
from app.api.update import (
    router as update_router,
)

from app.tiktok.connector import (
    TikTokConnector,
)


from app.tiktok import manager


app = FastAPI(
    title="LiveTrigger"
)


@app.middleware("http")
async def prevent_dashboard_cache(request: Request, call_next):
    """Always serve the installed dashboard version instead of stale HTML."""

    response = await call_next(request)
    if request.url.path.startswith("/dashboard/"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


# Database startup
initialize_database()
initialize_auth_tables()


@app.exception_handler(
    SubscriptionError
)
async def subscription_error_handler(
    request: Request,
    error: SubscriptionError,
):
    """Return stable auth errors without FastAPI's detail wrapper."""

    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": error.error,
            "message": error.message,
        },
    )


# API Routes
app.include_router(
    gift_router
)

app.include_router(
    settings_router
)

app.include_router(
    auth_router
)
app.include_router(subscription_router)
app.include_router(payment_router)

app.include_router(actions_v2.router)


app.include_router(
    event_router
)


app.include_router(
    event_test_router
)

app.include_router(
    tiktok_router
)

app.include_router(
    simulator_router
)

app.include_router(
    websocket_router
)

app.include_router(
    gift_catalog_router
)
app.include_router(
    update_router
)


# Dashboard
app.mount(
    "/dashboard",
    StaticFiles(
        directory=resource_path("dashboard"),
    ),
    name="dashboard",
)

app.mount(
    "/overlay",
    StaticFiles(
        directory=resource_path("web"),
    ),
    name="overlay",
)

app.mount(
    "/sounds",
    StaticFiles(
        directory=data_path("sounds"),
    ),
    name="sounds",
)

@app.on_event("startup")
async def startup_event():

    username = get_setting(
        "tiktok_username"
    )


    if username:

        print(
            "Starting TikTok connection:",
            username
        )


        manager.tiktok_client = (
            TikTokConnector(
                username
            )
        )


        asyncio.create_task(
            manager.tiktok_client.start()
        )


        print(
            "TikTok connector started."
        )

    else:

        print(
            "TikTok username not configured."
        )



@app.on_event("shutdown")
async def shutdown_event():

    if manager.tiktok_client:

        await manager.tiktok_client.stop()



@app.get("/")
def home():

    return RedirectResponse(
        url="/dashboard/events.html?v=1.0.8"
    )



@app.get("/health")
def health_check():

    return {

        "status":
        "OK",

    }
