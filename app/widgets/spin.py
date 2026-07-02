"""Built-in TikTok LIVE spin widget."""

from __future__ import annotations

import random
import json
import time

from app.core.events import LiveEvent
from app.core.websocket_manager import websocket_manager
from app.actions.executor import action_executor
from app.storage.sqlite_store import (
    get_action_presets,
    get_action_steps,
    get_setting,
    set_setting,
)


SPIN_COMMAND = "!spin"

DEFAULT_SEGMENTS = [
    "Try Again",
    "Shoutout",
    "Bonus Sound",
    "Lucky Star",
    "Dance",
    "Mega Hype",
    "Mystery",
    "Jackpot",
]

SPIN_SEGMENTS_SETTING = "spin_wheel_segments"
SPIN_ENABLED_SETTING = "spin_wheel_enabled"
SPIN_REQUIRE_FOLLOWER_SETTING = "spin_wheel_require_follower"
SPIN_NON_FOLLOWER_COOLDOWN_SETTING = "spin_wheel_non_follower_cooldown_minutes"
SPIN_FOLLOWER_COOLDOWN_SETTING = "spin_wheel_follower_cooldown_minutes"
SPIN_FAN_CLUB_COOLDOWN_SETTING = "spin_wheel_fan_club_cooldown_minutes"
SPIN_SUBSCRIBER_COOLDOWN_SETTING = "spin_wheel_subscriber_cooldown_minutes"
SPIN_USER_COOLDOWNS_SETTING = "spin_wheel_user_cooldowns"

DEFAULT_NON_FOLLOWER_COOLDOWN_MINUTES = 30
DEFAULT_FOLLOWER_COOLDOWN_MINUTES = 10
DEFAULT_FAN_CLUB_COOLDOWN_MINUTES = 8
DEFAULT_SUBSCRIBER_COOLDOWN_MINUTES = 5


def spin_enabled() -> bool:
    """Return whether the built-in spin widget is enabled."""

    value = get_setting(
        SPIN_ENABLED_SETTING
    )

    return str(
        value or "true"
    ).lower() != "false"


def setting_bool(
    key: str,
    default: bool,
) -> bool:
    """Read a boolean setting with a safe fallback."""

    value = get_setting(
        key
    )

    if value is None:

        return default

    return str(
        value
    ).strip().lower() not in {
        "false",
        "0",
        "no",
        "off",
    }


def setting_int(
    key: str,
    default: int,
) -> int:
    """Read a positive integer setting with a safe fallback."""

    try:

        return max(
            0,
            int(
                float(
                    get_setting(
                        key
                    )
                    or
                    default
                )
            ),
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


def load_user_cooldowns() -> dict:
    """Load per-user spin cooldown timestamps."""

    raw_value = get_setting(
        SPIN_USER_COOLDOWNS_SETTING
    )

    if not raw_value:

        return {}

    try:

        decoded = json.loads(
            raw_value
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):

        return {}

    if not isinstance(
        decoded,
        dict,
    ):

        return {}

    return decoded


def save_user_cooldowns(
    cooldowns: dict,
) -> None:
    """Persist per-user spin cooldown timestamps."""

    set_setting(
        SPIN_USER_COOLDOWNS_SETTING,
        json.dumps(
            cooldowns,
            separators=(
                ",",
                ":",
            ),
        ),
    )


def viewer_type_from_event(
    event: LiveEvent,
) -> str:
    """Return normalized viewer type for cooldown rules."""

    explicit_type = str(
        event.data.get(
            "viewer_type",
            "",
        )
        or
        ""
    ).strip().lower().replace(
        "-",
        "_",
    ).replace(
        " ",
        "_",
    )

    if explicit_type in {
        "subscriber",
        "fan_club",
        "follower",
        "non_follower",
    }:

        return explicit_type

    if event.data.get(
        "is_subscriber"
    ):

        return "subscriber"

    if event.data.get(
        "is_fan_club_member"
    ):

        return "fan_club"

    if event.data.get(
        "is_follower"
    ):

        return "follower"

    return "non_follower"


def spin_cooldown_minutes(
    viewer_type: str,
) -> int:
    """Return cooldown minutes for a viewer type."""

    if viewer_type == "subscriber":

        return setting_int(
            SPIN_SUBSCRIBER_COOLDOWN_SETTING,
            DEFAULT_SUBSCRIBER_COOLDOWN_MINUTES,
        )

    if viewer_type == "fan_club":

        return setting_int(
            SPIN_FAN_CLUB_COOLDOWN_SETTING,
            DEFAULT_FAN_CLUB_COOLDOWN_MINUTES,
        )

    if viewer_type == "non_follower":

        return setting_int(
            SPIN_NON_FOLLOWER_COOLDOWN_SETTING,
            DEFAULT_NON_FOLLOWER_COOLDOWN_MINUTES,
        )

    return setting_int(
        SPIN_FOLLOWER_COOLDOWN_SETTING,
        DEFAULT_FOLLOWER_COOLDOWN_MINUTES,
    )


def check_spin_access(
    event: LiveEvent,
) -> tuple[bool, str]:
    """Check follower requirement and per-user cooldown."""

    viewer_type = viewer_type_from_event(
        event
    )

    require_follower = setting_bool(
        SPIN_REQUIRE_FOLLOWER_SETTING,
        True,
    )

    if (
        require_follower
        and
        viewer_type == "non_follower"
    ):

        return (
            False,
            "!spin blocked: follower required.",
        )

    username = str(
        event.user
        or
        "guest"
    ).strip().lower()

    cooldown_minutes = spin_cooldown_minutes(
        viewer_type
    )

    if cooldown_minutes <= 0:

        return (
            True,
            "",
        )

    now = time.time()
    cooldowns = load_user_cooldowns()
    user_record = cooldowns.get(
        username,
        {},
    )

    if isinstance(
        user_record,
        (int, float),
    ):

        last_spin_at = float(
            user_record
        )

    else:

        try:

            last_spin_at = float(
                user_record.get(
                    "last_spin_at",
                    0,
                )
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):

            last_spin_at = 0

    remaining_seconds = (
        cooldown_minutes
        *
        60
        -
        (
            now
            -
            last_spin_at
        )
    )

    if remaining_seconds > 0:

        remaining_minutes = max(
            1,
            int(
                remaining_seconds
                //
                60
                +
                (
                    1
                    if remaining_seconds % 60
                    else
                    0
                )
            ),
        )

        return (
            False,
            (
                f"!spin cooldown active for {event.user or 'Guest'} "
                f"({viewer_type.replace('_', ' ')}): "
                f"{remaining_minutes} minute(s) remaining."
            ),
        )

    cutoff = now - 86400
    cleaned_cooldowns = {}

    for key, record in cooldowns.items():

        try:

            record_time = (
                float(
                    record
                )
                if isinstance(
                    record,
                    (int, float),
                )
                else
                float(
                    record.get(
                        "last_spin_at",
                        0,
                    )
                )
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):

            continue

        if record_time >= cutoff:

            cleaned_cooldowns[
                key
            ] = record

    cleaned_cooldowns[
        username
    ] = {
        "last_spin_at": now,
        "viewer_type": viewer_type,
    }

    save_user_cooldowns(
        cleaned_cooldowns
    )

    return (
        True,
        "",
    )


def default_spin_entries() -> list[dict]:
    """Return default wheel entries."""

    return [
        {
            "label": segment,
            "action_id": None,
        }
        for segment in DEFAULT_SEGMENTS
    ]


def load_spin_entries() -> list[dict]:
    """Load configured spin wheel entries with a safe fallback."""

    raw_value = get_setting(
        SPIN_SEGMENTS_SETTING
    )

    if not raw_value:

        return default_spin_entries()

    try:

        decoded = json.loads(
            raw_value
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):

        return default_spin_entries()

    if not isinstance(
        decoded,
        list,
    ):

        return default_spin_entries()

    entries = []

    for item in decoded:

        if isinstance(
            item,
            dict,
        ):

            label = str(
                item.get(
                    "label",
                    "",
                )
                or
                ""
            ).strip()

            action_id = item.get(
                "action_id"
            )

        else:

            label = str(
                item
            ).strip()

            action_id = None

        if not label:

            continue

        try:

            action_id = (
                int(
                    action_id
                )
                if action_id
                else
                None
            )

        except (
            TypeError,
            ValueError,
        ):

            action_id = None

        entries.append(
            {
                "label": label,
                "action_id": action_id,
            }
        )

    return entries or default_spin_entries()


def build_action_from_step(
    event: LiveEvent,
    step: dict,
    preset: dict,
) -> dict | None:
    """Build an executor action from an action preset step."""

    action_type = str(
        step.get(
            "type",
            "",
        )
        or
        ""
    ).lower()

    value = step.get(
        "value",
        "",
    )

    if action_type == "sound":

        return {
            "type": "sound",
            "sound": value,
            "volume": preset.get(
                "media_volume",
                100,
            ),
            "max_duration": preset.get(
                "duration",
                0,
            ),
        }

    if action_type == "keyboard":

        return {
            "type": "keyboard",
            "key": value,
            "max_duration": preset.get(
                "duration",
                0,
            ),
        }

    if action_type == "tts":

        text = str(
            value
            or
            ""
        ).replace(
            "{user}",
            event.user or "",
        ).replace(
            "{comment}",
            str(
                event.data.get(
                    "comment",
                    "",
                )
            ),
        )

        return {
            "type": "tts",
            "text": text,
            "max_duration": preset.get(
                "duration",
                0,
            ),
        }

    if action_type == "webhook":

        return {
            "type": "webhook",
            "url": value,
            "max_duration": preset.get(
                "duration",
                0,
            ),
        }

    if action_type == "overlay":

        return {
            "type": "overlay",
            "name": value,
            "data": {
                "user": event.user,
                "event": event.event_type,
            },
            "max_duration": preset.get(
                "duration",
                0,
            ),
        }

    return None


def execute_linked_action(
    action_id: int | None,
    event: LiveEvent,
) -> None:
    """Execute the action preset linked to a winning spin item."""

    if not action_id:

        return

    preset = next(
        (
            item
            for item in get_action_presets()
            if item.get(
                "id"
            ) == action_id
        ),
        None,
    )

    if not preset:

        print(
            "[SPIN_WIDGET] Linked action not found:",
            action_id,
        )

        return

    deadline = action_executor.deadline_from_action(
        {
            "max_duration": preset.get(
                "duration",
                0,
            )
        }
    )

    for step in get_action_steps(
        action_id
    ):

        action = build_action_from_step(
            event,
            step,
            preset,
        )

        if action:

            action_executor.execute(
                action,
                deadline=deadline,
            )

    print(
        "[SPIN_WIDGET] Linked action executed:",
        action_id,
    )


def trigger_spin_command(
    event: LiveEvent,
) -> dict | None:
    """Trigger spin widget when a viewer comments !spin."""

    if not spin_enabled():

        return None

    if event.event_type.lower() != "comment":

        return None

    comment = str(
        event.data.get(
            "comment",
            "",
        )
        or
        ""
    ).strip()

    command = (
        comment.split()[0].lower()
        if comment
        else ""
    )

    if command != SPIN_COMMAND:

        return None

    allowed, blocked_reason = check_spin_access(
        event
    )

    if not allowed:

        print(
            "[SPIN_WIDGET]",
            blocked_reason,
        )

        return {
            "handled": True,
            "triggered": False,
            "reason": blocked_reason,
        }

    entries = load_spin_entries()

    winning_entry = random.choice(
        entries
    )

    segments = [
        entry[
            "label"
        ]
        for entry in entries
    ]

    result = winning_entry[
        "label"
    ]

    action_id = winning_entry.get(
        "action_id"
    )

    websocket_manager.send_event(
        {
            "type": "spin",
            "data": {
                "user": event.user or "Guest",
                "command": SPIN_COMMAND,
                "segments": segments,
                "result": result,
                "action_id": action_id,
                "spin_ms": 5200,
            },
        }
    )

    execute_linked_action(
        action_id,
        event,
    )

    print(
        "[SPIN_WIDGET] Triggered:",
        event.user,
        "->",
        result,
    )

    return {
        "handled": True,
        "triggered": True,
        "result": result,
        "action_id": action_id,
    }
