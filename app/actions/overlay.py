"""Overlay action."""

from app.core.websocket_manager import websocket_manager


class OverlayAction:
    """Send overlay events to browser."""

    def show(
        self,
        overlay_name: str,
        data: dict | None = None,
    ) -> dict:
        """
        Send overlay event using WebSocket.
        """

        payload = {
            "type": "overlay",
            "name": overlay_name,
            "data": data or {},
        }

        websocket_manager.send_event(
            payload
        )

        return {
            "action": "overlay",
            "overlay": overlay_name,
            "status": "sent",
        }


overlay_action = OverlayAction()