"""Professional TikTok Live listener."""

import asyncio
from datetime import datetime

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent,
    CommentEvent,
    GiftEvent,
    LikeEvent,
    JoinEvent,
)

from app.core.events import LiveEvent
from app.rules.event_engine import event_engine


class TikTokListener:
    """Professional TikTok LIVE listener."""

    def __init__(self, username: str):
        self.username = username
        self.client = None
        self.retry_delay = 30
        self.running = False


    def log(self, level: str, message: str):
        """Display timestamp log."""

        current_time = datetime.now().strftime("%H:%M:%S")

        print(
            f"[{current_time}] [{level}] {message}"
        )


    async def start(self):
        """Start listener with auto reconnect."""

        self.running = True

        self.log(
            "INFO",
            f"Starting TBana Stream for @{self.username}"
        )


        while self.running:

            try:
                self.create_client()

                self.log(
                    "INFO",
                    f"Connecting to @{self.username}..."
                )

                await self.client.connect()


            except Exception as error:

                self.log(
                    "ERROR",
                    str(error)
                )

                self.log(
                    "RETRY",
                    f"Reconnect in {self.retry_delay} seconds"
                )

                await asyncio.sleep(
                    self.retry_delay
                )


    async def stop(self):
        """Stop listener."""

        self.running = False

        if self.client:
            await self.client.disconnect()

        self.log(
            "INFO",
            "Listener stopped"
        )


    def create_client(self):
        """Create a fresh TikTok client."""

        self.client = TikTokLiveClient(
            unique_id=self.username
        )

        self.register_events()
    def register_events(self):
        """Register TikTok events."""

        self.client.on(ConnectEvent)(self.on_connect)
        self.client.on(CommentEvent)(self.on_comment)
        self.client.on(LikeEvent)(self.on_like)
        self.client.on(JoinEvent)(self.on_join)
        self.client.on(GiftEvent)(self.on_gift)


    def process_live_event(self, live_event: LiveEvent):
        """Send event to Rules Engine and execute actions."""

        result = event_engine.process(
            live_event
        )

        self.log(
            "RULES",
            str(result)
        )


    async def on_connect(self, event: ConnectEvent):
        """Triggered when connected."""

        self.log(
            "CONNECTED",
            f"Connected to @{event.unique_id}"
        )


    async def on_comment(self, event: CommentEvent):
        """Handle comment event."""

        live_event = LiveEvent(
            event_type="comment",
            user=event.user.nickname,
            data={
                "comment": event.comment
            }
        )

        self.log(
            "COMMENT",
            f"{event.user.nickname}: {event.comment}"
        )

        self.process_live_event(
            live_event
        )


    async def on_like(self, event: LikeEvent):
        """Handle like event."""

        live_event = LiveEvent(
            event_type="like",
            user=event.user.nickname,
            data={
                "count": event.count
            }
        )

        self.log(
            "LIKE",
            f"{event.user.nickname} sent {event.count} likes"
        )

        self.process_live_event(
            live_event
        )


    async def on_join(self, event: JoinEvent):
        """Handle join event."""

        live_event = LiveEvent(
            event_type="join",
            user=event.user.nickname,
            data={}
        )

        self.log(
            "JOIN",
            f"{event.user.nickname} joined"
        )

        self.process_live_event(
            live_event
        )


    async def on_gift(self, event: GiftEvent):
        """Handle gift event."""

        live_event = LiveEvent(
            event_type="gift",
            user=event.user.nickname,
            data={
                "gift_name": event.gift.name,
                "count": event.repeat_count
            }
        )

        self.log(
            "GIFT",
            f"{event.user.nickname} sent "
            f"{event.gift.name} x{event.repeat_count}"
        )

        self.process_live_event(
            live_event
        )


# ======================================
# Application entry point
# ======================================

tiktok_listener = TikTokListener(
    "uiisora"
)


if __name__ == "__main__":

    try:
        asyncio.run(
            tiktok_listener.start()
        )

    except KeyboardInterrupt:

        print(
            "\n[INFO] TBana Stream stopped by user"
        )
