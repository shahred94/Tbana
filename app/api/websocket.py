"""WebSocket and overlay status endpoints."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket_manager import websocket_manager


router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(
    websocket: WebSocket
):
    """Handle overlay WebSocket clients."""

    screen = websocket.query_params.get(
        "screen",
        "unknown",
    )

    await websocket_manager.connect(
        websocket,
        screen,
    )

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()

    except WebSocketDisconnect:

        websocket_manager.disconnect(
            websocket
        )


@router.get("/api/overlay/status")
def overlay_status():
    """Return overlay screen connection status."""

    return websocket_manager.get_overlay_status()
