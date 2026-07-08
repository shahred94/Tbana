"""TikTok LIVE Connector."""

import asyncio

from TikTokLive import TikTokLiveClient

from TikTokLive.events import (
    ConnectEvent,
    CommentEvent,
    GiftEvent,
    LikeEvent,
    FollowEvent,
)

from app.core.events import (
    LiveEvent,
)

from app.rules.event_engine import (
    event_engine,
)
from app.widgets.goal import (
    broadcast_like_goal,
    reset_like_goal,
)

from app.tiktok.log_manager import (
    add_log,
)


def _read_attr(
    source,
    *names,
):
    """Read the first available attribute or dict key."""

    for name in names:

        if source is None:

            continue

        if isinstance(
            source,
            dict,
        ):

            if name in source:

                return source.get(
                    name
                )

            continue

        if hasattr(
            source,
            name,
        ):

            return getattr(
                source,
                name,
            )

    return None


def _read_nested(
    source,
    *path,
):
    """Read a nested attribute/dict path."""

    current = source

    for name in path:

        current = _read_attr(
            current,
            name,
        )

        if current is None:

            return None

    return current


def _as_bool(
    value,
) -> bool:
    """Convert common TikTokLive metadata values to bool."""

    if isinstance(
        value,
        bool,
    ):

        return value

    if isinstance(
        value,
        (int, float),
    ):

        return value > 0

    if isinstance(
        value,
        str,
    ):

        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "follow",
            "follower",
            "following",
            "subscriber",
            "subscribed",
            "member",
            "fan_club",
        }

    return bool(
        value
    )


def _badge_texts(
    user,
) -> list[str]:
    """Extract badge labels from a TikTokLive user object."""

    badges = _read_attr(
        user,
        "badges",
        "badge_list",
        "badgeList",
    )

    if not badges:

        return []

    texts = []

    for badge in badges:

        for name in (
            "name",
            "display_name",
            "displayName",
            "title",
            "label",
            "type",
        ):

            value = _read_attr(
                badge,
                name,
            )

            if value:

                texts.append(
                    str(
                        value
                    ).lower()
                )

    return texts


def viewer_metadata(
    user,
) -> dict:
    """Build normalized viewer metadata for access/cooldown rules."""

    avatar_url = _read_attr(
        user,
        "profile_picture_url",
        "profilePictureUrl",
        "profile_pic_url",
        "profilePicUrl",
        "avatar_url",
        "avatarUrl",
        "avatar_thumb",
        "avatarThumb",
        "avatar",
        "image_url",
        "imageUrl",
    )

    badges = _badge_texts(
        user
    )

    is_subscriber = any(
        [
            _as_bool(
                _read_attr(
                    user,
                    "is_subscriber",
                    "isSubscriber",
                    "subscriber",
                    "subscribed",
                    "is_subscribed",
                    "isSubscribed",
                )
            ),
            _as_bool(
                _read_nested(
                    user,
                    "subscribe_info",
                    "status",
                )
            ),
            any(
                "subscriber" in text
                or
                "subscribed" in text
                for text in badges
            ),
        ]
    )

    is_fan_club_member = any(
        [
            _as_bool(
                _read_attr(
                    user,
                    "is_fan_club_member",
                    "isFanClubMember",
                    "fan_club_member",
                    "fanClubMember",
                    "is_member",
                    "isMember",
                )
            ),
            _as_bool(
                _read_attr(
                    user,
                    "member_level",
                    "memberLevel",
                )
            ),
            _as_bool(
                _read_nested(
                    user,
                    "fan_club",
                    "level",
                )
            ),
            any(
                "fan" in text
                or
                "member" in text
                for text in badges
            ),
        ]
    )

    is_follower = any(
        [
            _as_bool(
                _read_attr(
                    user,
                    "is_follower",
                    "isFollower",
                    "follower",
                    "followed",
                    "is_following",
                    "isFollowing",
                )
            ),
            _as_bool(
                _read_nested(
                    user,
                    "follow_info",
                    "follow_status",
                )
            ),
            _as_bool(
                _read_nested(
                    user,
                    "followInfo",
                    "followStatus",
                )
            ),
            any(
                "follower" in text
                or
                "following" in text
                for text in badges
            ),
        ]
    )

    if is_subscriber:

        viewer_type = "subscriber"

    elif is_fan_club_member:

        viewer_type = "fan_club"

    elif is_follower:

        viewer_type = "follower"

    else:

        viewer_type = "non_follower"

    return {
        "viewer_type": viewer_type,
        "is_follower": is_follower,
        "is_fan_club_member": is_fan_club_member,
        "is_subscriber": is_subscriber,
        "viewer_avatar_url": (
            str(
                avatar_url
            ).strip()
            if avatar_url
            else ""
        ),
    }


class TikTokConnector:
    """TikTok LIVE listener."""


    def __init__(
        self,
        username: str,
    ):

        self.username = username

        self.status = "OFFLINE"

        self.last_error = None

        self.client = TikTokLiveClient(
            unique_id=username
        )
        self.running = True
        self.register_events()


    def register_events(self):

        """Register TikTok callbacks."""


        @self.client.on(ConnectEvent)
        async def on_connect(event):

            print(
                "Connected to TikTok LIVE:",
                self.username
            )

            self.status = "CONNECTED"

            self.last_error = None

            add_log(
                f"🟢 Connected to @{self.username}",
                "SYSTEM"
            )


        @self.client.on(CommentEvent)
        async def on_comment(event):

            print(
                "COMMENT:",
                event.user.nickname,
                event.comment
            )

            add_log(
                f"💬 {event.user.nickname}: {event.comment}",
                "COMMENT"
            )

            live_event = LiveEvent(
                event_type="COMMENT",
                user=event.user.nickname,
                data={
                    "comment": event.comment,
                    **viewer_metadata(
                        event.user
                    ),
                }
            )

            result = event_engine.process(
                live_event
            )

            spin_result = result.get(
                "spin"
            )
            if (
                spin_result
                and
                spin_result.get(
                    "reply"
                )
            ):

                add_log(
                    (
                        "↩ Auto reply: "
                        f"{spin_result['reply']}"
                    ),
                    "SPIN",
                )

            print(
                "Actions:",
                result
            )


        @self.client.on(GiftEvent)
        async def on_gift(event):

            # Streakable gifts emit interim updates followed by one
            # final event. Process only the final event to avoid
            # duplicate logs and duplicate actions.
            if getattr(
                event,
                "streaking",
                False,
            ):

                print(
                    "GIFT STREAK UPDATE:",
                    event.user.nickname,
                    getattr(
                        event,
                        "repeat_count",
                        1,
                    ),
                )

                return

            gift_name = getattr(
                event.gift,
                "name",
                "Unknown"
            )

            repeat_count = max(
                1,
                int(
                    getattr(
                        event,
                        "repeat_count",
                        1,
                    )
                    or
                    1
                ),
            )

            diamond_count = max(
                0,
                int(
                    getattr(
                        event.gift,
                        "diamond_count",
                        0,
                    )
                    or
                    0
                ),
            )

            gift_label = (
                gift_name
                if repeat_count == 1
                else
                f"{gift_name} x{repeat_count}"
            )


            print(
                "GIFT:",
                event.user.nickname,
                gift_label
            )


            add_log(
                f"🎁 {event.user.nickname}: {gift_label}",
                "GIFT"
            )


            live_event = LiveEvent(
                event_type="GIFT",
                user=event.user.nickname,
                data={
                    "gift_name": gift_name,
                    "count": repeat_count,
                    "diamond_count": diamond_count,
                    "coins": (
                        diamond_count
                        *
                        repeat_count
                    ),
                    **viewer_metadata(
                        event.user
                    ),
                }
            )

            result = event_engine.process(
                live_event
            )

            print(
                "Actions:",
                result
            )


        @self.client.on(LikeEvent)
        async def on_like(event):

            print(
                "LIKE:",
                event.user.nickname,
                event.count
            )

            add_log(
                f"❤️ {event.user.nickname}: {event.count}",
                "LIKE"
            )


            live_event = LiveEvent(
                event_type="LIKE",
                user=event.user.nickname,
                data={
                    "count": event.count
                }
            )

            broadcast_like_goal(
                event.user.nickname,
                event.count,
            )

            result = event_engine.process(
                live_event
            )

            print(
                "Actions:",
                result
            )


        @self.client.on(FollowEvent)
        async def on_follow(event):

            print(
                "FOLLOW:",
                event.user.nickname
            )

            add_log(
                f"👤 {event.user.nickname} followed",
                "FOLLOW"
            )


            live_event = LiveEvent(
                event_type="FOLLOW",
                user=event.user.nickname,
                data={}
            )

            result = event_engine.process(
                live_event
            )

            print(
                "Actions:",
                result
            )


    async def start(self):

        """Start TikTok listener."""

        try:

            event_engine.reset_live_session()
            reset_like_goal()

            print(
                "Starting TikTok listener:",
                self.username
            )

            self.status = "CONNECTING"

            add_log(
                f"🟡 Connecting to @{self.username}",
                "SYSTEM"
            )

            await self.client.start()


        except Exception as error:

            self.status = "FAILED"

            self.last_error = str(
                error
            )

            print(
                "TikTok connection failed:",
                error
            )

            add_log(
                f"🔴 Connection failed: {error}",
                "ERROR"
            )


    async def stop(self):

        """Stop TikTok listener."""

        await self.client.disconnect()
        event_engine.reset_live_session()
        reset_like_goal()

        self.status = "OFFLINE"

        self.last_error = None

        add_log(
            "🔌 TikTok disconnected",
            "SYSTEM"
        )

        print(
            "TikTok listener stopped."
        )
