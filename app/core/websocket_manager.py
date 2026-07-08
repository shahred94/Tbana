"""WebSocket connection manager."""

import asyncio

from fastapi import WebSocket


class WebSocketManager:
    """Tracks active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_screens: dict[WebSocket, str] = {}
        self.connection_overlays: dict[WebSocket, str] = {}
        self.loop: asyncio.AbstractEventLoop | None = None


    async def connect(
        self,
        websocket: WebSocket,
        screen: str = "unknown",
        overlay_type: str = "screen",
    ):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_screens[websocket] = screen
        self.connection_overlays[websocket] = (
            overlay_type
            if overlay_type in {
                "goal",
                "spin",
            }
            else "screen"
        )

        print(
            f"[WEBSOCKET] Client connected. "
            f"Screen: {screen}. "
            f"Overlay: {self.connection_overlays[websocket]}. "
            f"Total: {len(self.active_connections)}"
        )


    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

            screen = self.connection_screens.pop(
                websocket,
                "unknown",
            )
            overlay_type = self.connection_overlays.pop(
                websocket,
                "screen",
            )

            print(
                f"[WEBSOCKET] Client disconnected. "
                f"Screen: {screen}. "
                f"Overlay: {overlay_type}. "
                f"Total: {len(self.active_connections)}"
            )


    async def broadcast(self, message: dict):
        message_type = message.get(
            "type"
        )

        for connection in list(
            self.active_connections
        ):
            overlay_type = self.connection_overlays.get(
                connection,
                "screen",
            )

            if (
                message_type in {"spin", "spin_notice"}
                and
                overlay_type != "spin"
            ):

                continue

            if (
                message_type == "goal"
                and
                overlay_type != "goal"
            ):

                continue

            if (
                message_type not in {"spin", "spin_notice", "goal"}
                and
                overlay_type in {"goal", "spin"}
            ):

                continue

            try:
                await connection.send_json(message)

            except Exception:
                self.disconnect(connection)


    def get_overlay_status(
        self,
        screen_count: int = 8,
    ) -> dict:
        """Return connected overlay clients grouped by screen."""

        screens = []

        for screen_number in range(
            1,
            screen_count + 1,
        ):

            screen = str(
                screen_number
            )

            connections = sum(
                1
                for connection, value
                in self.connection_screens.items()
                if (
                    value == screen
                    and
                    self.connection_overlays.get(
                        connection,
                        "screen",
                    )
                    == "screen"
                )
            )

            screens.append(
                {
                    "screen": screen_number,
                    "connections": connections,
                    "online": connections > 0,
                }
            )

        return {
            "total": len(self.active_connections),
            "spin_connections": self.connection_count(
                "spin"
            ),
            "goal_connections": self.connection_count(
                "goal"
            ),
            "screens": screens,
        }


    def send_event(self, message: dict):
        """Allow sync modules to send WebSocket events."""

        try:
            loop = asyncio.get_running_loop()

            loop.create_task(
                self.broadcast(message)
            )

        except RuntimeError:
            if (
                self.loop
                and
                self.loop.is_running()
            ):

                asyncio.run_coroutine_threadsafe(
                    self.broadcast(message),
                    self.loop,
                )

            else:

                print(
                    "[WEBSOCKET] No running event loop"
                )

    def connection_count(
        self,
        overlay_type: str | None = None,
    ) -> int:
        """Count all connections or one overlay type."""

        if overlay_type is None:

            return len(
                self.active_connections
            )

        return sum(
            1
            for connection in self.active_connections
            if self.connection_overlays.get(
                connection,
                "screen",
            )
            == overlay_type
        )



websocket_manager = WebSocketManager()
