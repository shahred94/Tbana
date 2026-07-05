"""TikTok connection API."""

import asyncio

from fastapi import APIRouter, Request

from app.auth.service import require_authenticated
from app.tiktok import manager

from app.tiktok.connector import (
    TikTokConnector,
)

from app.tiktok.log_manager import (
    get_logs,
    clear_logs,
)


router = APIRouter(
    prefix="/api/tiktok",
    tags=[
        "TikTok"
    ],
)


@router.get("/status")
def get_status():

    if not manager.tiktok_client:

        return {
            "status": "OFFLINE",
            "username": None,
            "last_error": None,
        }


    return {
        "status":
        manager.tiktok_client.status,

        "username":
        manager.tiktok_client.username,

        "last_error":
        manager.tiktok_client.last_error,
    }
@router.get("/logs")
def get_tiktok_logs():

    return get_logs()
    
@router.delete("/logs")
def clear_tiktok_logs():

    clear_logs()

    return {

        "message":
        "TikTok logs cleared"

    }
    
@router.post("/reconnect/{username}")
async def reconnect_tiktok(
    username: str,
    request: Request,
):

    require_authenticated(
        request,
        "Please login to connect TikTok.",
    )

    # Stop old connection
    if manager.tiktok_client:

        await manager.tiktok_client.stop()

    # Create new TikTok connection
    manager.tiktok_client = (
        TikTokConnector(
            username
        )
    )

    # Start TikTok listener in background
    asyncio.create_task(
        manager.tiktok_client.start()
    )

    return {

        "message":
        f"Reconnecting to @{username}"

    }


@router.post("/disconnect")
async def disconnect_tiktok():

    client = manager.tiktok_client

    if client is None:

        return {
            "message": "TikTok is already disconnected",
            "status": "OFFLINE",
        }

    # Report OFFLINE immediately while the connection shuts down.
    manager.tiktok_client = None

    try:

        await asyncio.wait_for(
            client.stop(),
            timeout=5,
        )

    except (TimeoutError, Exception):

        return {
            "message": "TikTok disconnected",
            "status": "OFFLINE",
        }

    return {
        "message": "TikTok disconnected",
        "status": "OFFLINE",
    }
