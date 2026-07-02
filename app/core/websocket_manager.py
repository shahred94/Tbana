"""WebSocket connection manager."""

import asyncio

from fastapi import WebSocket


class WebSocketManager:
    """Tracks active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_screens: dict[WebSocket, str] = {}
        self.loop: asyncio.AbstractEventLoop | None = None


    async def connect(
        self,
        websocket: WebSocket,
        screen: str = "unknown",
    ):
        self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_screens[websocket] = screen

        print(
            f"[WEBSOCKET] Client connected. "
            f"Screen: {screen}. "
            f"Total: {len(self.active_connections)}"
        )


    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

            screen = self.connection_screens.pop(
                websocket,
                "unknown",
            )

            print(
                f"[WEBSOCKET] Client disconnected. "
                f"Screen: {screen}. "
                f"Total: {len(self.active_connections)}"
            )


    async def broadcast(self, message: dict):
        for connection in self.active_connections:
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
                for value in self.connection_screens.values()
                if value == screen
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


websocket_manager = WebSocketManager()
