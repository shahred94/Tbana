"""Goal overlay helpers."""

from app.core.websocket_manager import websocket_manager
from app.storage.sqlite_store import (
    get_action_presets,
    get_action_steps,
    get_setting,
    set_setting,
)
from app.rules.event_engine import EventEngine
from app.core.events import LiveEvent


like_goal_total = 0
like_goal_last_completed = 0


def _int_setting(
    key: str,
    default: int,
) -> int:
    try:
        return int(
            get_setting(
                key
            )
            or
            default
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def goal_settings() -> dict:
    """Return persisted goal overlay settings."""

    step = max(
        1,
        _int_setting(
            "goal_overlay_target",
            6000,
        ),
    )
    start = max(
        0,
        _int_setting(
            "goal_overlay_start",
            0,
        ),
    )
    current_target = max(
        step,
        _int_setting(
            "goal_overlay_current_target",
            step,
        ),
    )

    return {
        "title": get_setting("goal_overlay_title") or "Like Goal",
        "label": get_setting("goal_overlay_label") or "Likes",
        "step": step,
        "start": start,
        "target": current_target,
        "action_id": get_setting("goal_overlay_action_id") or "",
        "sound_volume": max(
            0,
            min(100, _int_setting("goal_overlay_sound_volume", 40)),
        ),
    }


def goal_status() -> dict:
    """Return current goal progress."""

    settings = goal_settings()
    visible_total = settings["start"] + like_goal_total
    return {
        **settings,
        "total": like_goal_total,
        "visible_total": visible_total,
        "completed_target": like_goal_last_completed,
    }


def reset_like_goal():
    """Reset the in-memory like goal counter for a live session."""

    global like_goal_total, like_goal_last_completed

    like_goal_total = 0
    like_goal_last_completed = 0
    settings = goal_settings()
    set_setting(
        "goal_overlay_current_target",
        str(settings["step"]),
    )
    broadcast_goal_state(
        user="",
        count=0,
    )


def add_like_goal(
    count: int,
    user: str = "Dashboard",
) -> int:
    """Add likes to the goal counter and broadcast the new state."""

    return broadcast_like_goal(
        user,
        count,
    )


def next_like_goal() -> int:
    """Advance the next target by one configured goal step."""

    settings = goal_settings()
    next_target = settings["target"] + settings["step"]
    set_setting(
        "goal_overlay_current_target",
        str(next_target),
    )
    broadcast_goal_state(
        user="",
        count=0,
    )
    return next_target


def broadcast_goal_state(
    user: str,
    count: int,
) -> None:
    """Broadcast the current goal status."""

    status = goal_status()

    websocket_manager.send_event(
        {
            "type": "goal",
            "name": "likes",
            "data": {
                "user": user,
                "count": count,
                **status,
            },
        }
    )


def trigger_goal_action(
    user: str,
    count: int,
    target: int,
) -> None:
    """Run the configured action when a like milestone is reached."""

    action_id = goal_settings().get(
        "action_id",
        "",
    )

    try:
        action_id_int = int(
            action_id
            or
            0
        )
    except (
        TypeError,
        ValueError,
    ):
        action_id_int = 0

    if action_id_int <= 0:
        return

    event = LiveEvent(
        event_type="GOAL",
        user=user,
        data={
            "count": count,
            "goal_target": target,
            "total_like_count": like_goal_total,
        },
    )

    preset = next(
        (
            item
            for item in get_action_presets()
            if int(item.get("id", 0)) == action_id_int
        ),
        None,
    )
    if not preset or not preset.get("enabled", True):
        return

    settings = goal_settings()
    engine = EventEngine()
    actions = []

    for step in get_action_steps(
        action_id_int
    ):
        action = engine.build_action_from_step(
            event,
            step,
        )
        if not action:
            continue

        action["_action_preset_id"] = action_id_int
        action["_action_preset_name"] = preset.get("name") or "Goal Reached"
        action["_step_id"] = step.get("id")
        action["_step_order"] = step.get("order")
        action["max_duration"] = preset.get("duration", 0)
        action["execution_type"] = preset.get("execution_type", "auto")
        if action.get("type") == "sound":
            action["volume"] = settings["sound_volume"]
        actions.append(action)

    engine.execute_action_group(
        actions,
        repeat_index=0,
        execution_count=1,
        log_prefix="[GOAL]",
    )


def broadcast_like_goal(
    user: str,
    count: int,
) -> int:
    """Accumulate TikTok likes and broadcast progress to goal overlays."""

    global like_goal_total, like_goal_last_completed

    safe_count = max(
        0,
        int(
            count or 0
        ),
    )

    like_goal_total += safe_count
    settings = goal_settings()
    visible_total = settings["start"] + like_goal_total
    target = settings["target"]

    if (
        visible_total >= target
        and
        like_goal_last_completed < target
    ):
        like_goal_last_completed = target
        trigger_goal_action(
            user,
            safe_count,
            target,
        )
        next_target = target + settings["step"]
        set_setting(
            "goal_overlay_current_target",
            str(next_target),
        )

    broadcast_goal_state(
        user,
        safe_count,
    )

    return like_goal_total
