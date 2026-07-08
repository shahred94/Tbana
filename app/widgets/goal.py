"""Goal overlay helpers."""

from app.core.websocket_manager import websocket_manager


like_goal_total = 0


def reset_like_goal():
    """Reset the in-memory like goal counter for a live session."""

    global like_goal_total

    like_goal_total = 0


def broadcast_like_goal(
    user: str,
    count: int,
) -> int:
    """Accumulate TikTok likes and broadcast progress to goal overlays."""

    global like_goal_total

    safe_count = max(
        0,
        int(
            count or 0
        ),
    )

    like_goal_total += safe_count

    websocket_manager.send_event(
        {
            "type": "goal",
            "name": "likes",
            "data": {
                "user": user,
                "count": safe_count,
                "total": like_goal_total,
            },
        }
    )

    return like_goal_total
