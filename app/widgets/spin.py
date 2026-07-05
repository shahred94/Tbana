"""Built-in TikTok LIVE spin widget."""

from __future__ import annotations

import random
import json
import math
import queue
import threading
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
SPIN_DURATION_MS = 5200
SPIN_RESULT_HOLD_MS = 3000
SPIN_ACTION_START_BUFFER_MS = 200
SPIN_RARITIES = (
    "common",
    "rare",
    "epic",
)

_spin_jobs: queue.Queue[dict] = queue.Queue()
_spin_worker_lock = threading.Lock()
_spin_worker_started = False


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


def viewer_status_label(
    viewer_type: str,
) -> str:
    """Return a viewer-facing status label."""

    return {
        "subscriber": "Subscriber",
        "fan_club": "Fan",
        "follower": "Follower",
        "non_follower": "Viewer",
    }.get(
        viewer_type,
        "Viewer",
    )


def format_cooldown(
    remaining_seconds: int,
) -> str:
    """Format a cooldown using a useful live countdown precision."""

    seconds = max(
        1,
        int(
            math.ceil(
                remaining_seconds
            )
        ),
    )
    hours, remainder = divmod(
        seconds,
        3600,
    )
    minutes, seconds = divmod(
        remainder,
        60,
    )

    if hours:

        return f"{hours}h {minutes:02d}m {seconds:02d}s"

    if minutes:

        return f"{minutes}m {seconds:02d}s"

    return f"{seconds}s"


def spin_access_details(
    event: LiveEvent,
) -> dict:
    """Check spin access and return viewer-facing cooldown details."""

    viewer_type = viewer_type_from_event(
        event
    )
    status_label = viewer_status_label(
        viewer_type
    )
    display_user = event.user or "Guest"

    if event.data.get(
        "_simulator"
    ):

        return {
            "allowed": True,
            "reason": "",
            "reply": "",
            "viewer_type": viewer_type,
            "viewer_status": status_label,
            "remaining_seconds": 0,
        }

    require_follower = setting_bool(
        SPIN_REQUIRE_FOLLOWER_SETTING,
        True,
    )

    if (
        require_follower
        and
        viewer_type == "non_follower"
    ):

        message = (
            f"@{display_user} • {status_label} • "
            "!spin requires follower status."
        )

        return {
            "allowed": False,
            "reason": "!spin blocked: follower required.",
            "reply": message,
            "viewer_type": viewer_type,
            "viewer_status": status_label,
            "remaining_seconds": 0,
        }

    username = str(
        event.user
        or
        "guest"
    ).strip().lower()

    cooldown_minutes = spin_cooldown_minutes(
        viewer_type
    )

    if cooldown_minutes <= 0:

        return {
            "allowed": True,
            "reason": "",
            "reply": "",
            "viewer_type": viewer_type,
            "viewer_status": status_label,
            "remaining_seconds": 0,
        }

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

        rounded_remaining = max(
            1,
            int(
                math.ceil(
                    remaining_seconds
                )
            ),
        )
        duration = format_cooldown(
            rounded_remaining
        )
        message = (
            f"@{display_user} • {status_label} • "
            f"!spin cooldown: {duration} remaining."
        )

        return {
            "allowed": False,
            "reason": (
                f"!spin cooldown active for {event.user or 'Guest'} "
                f"({viewer_type.replace('_', ' ')}): "
                f"{duration} remaining."
            ),
            "reply": message,
            "viewer_type": viewer_type,
            "viewer_status": status_label,
            "remaining_seconds": rounded_remaining,
        }

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

    return {
        "allowed": True,
        "reason": "",
        "reply": "",
        "viewer_type": viewer_type,
        "viewer_status": status_label,
        "remaining_seconds": 0,
    }


def check_spin_access(
    event: LiveEvent,
) -> tuple[bool, str]:
    """Compatibility wrapper returning the original access tuple."""

    details = spin_access_details(
        event
    )

    return (
        bool(
            details["allowed"]
        ),
        str(
            details["reason"]
        ),
    )


def default_spin_entries() -> list[dict]:
    """Return default wheel entries."""

    return [
        {
            "label": segment,
            "action_id": None,
            "chance": 1,
            "rarity": (
                "common"
                if index < 4
                else "rare"
                if index < 6
                else "epic"
            ),
        }
        for index, segment in enumerate(DEFAULT_SEGMENTS)
    ]


def normalize_spin_rarity(
    rarity: object,
) -> str:
    """Return a safe rarity bucket for a spin entry."""

    value = str(
        rarity or ""
    ).strip().lower()

    return value if value in SPIN_RARITIES else "common"


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
            chance = item.get(
                "chance",
                1,
            )
            rarity = normalize_spin_rarity(
                item.get(
                    "rarity",
                    "common",
                )
            )

        else:

            label = str(
                item
            ).strip()

            action_id = None
            chance = 1
            rarity = "common"

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

        try:

            chance = float(
                chance
            )

            if (
                not math.isfinite(
                    chance
                )
                or
                chance < 0
            ):

                chance = 1

            chance = min(
                chance,
                1_000_000,
            )

        except (
            TypeError,
            ValueError,
        ):

            chance = 1

        entries.append(
            {
                "label": label,
                "action_id": action_id,
                "chance": chance,
                "rarity": rarity,
            }
        )

    return entries or default_spin_entries()


def choose_spin_entry(
    entries: list[dict],
) -> dict:
    """Choose a wheel entry using its configured chance weight."""

    weighted_entries = []
    rarity_weights = {}

    for entry in entries:

        rarity = normalize_spin_rarity(
            entry.get(
                "rarity",
                "common",
            )
        )
        weight = max(
            0,
            float(
                entry.get(
                    "chance",
                    1,
                )
            ),
        )

        weighted_entries.append(
            (
                rarity,
                entry,
                weight,
            )
        )
        rarity_weights[rarity] = (
            rarity_weights.get(
                rarity,
                0,
            )
            + weight
        )

    if not any(
        weight > 0
        for weight in rarity_weights.values()
    ):

        rarity_weights = {
            rarity: 1
            for rarity in SPIN_RARITIES
            if any(
                normalize_spin_rarity(
                    entry.get(
                        "rarity",
                        "common",
                    )
                ) == rarity
                for entry in entries
            )
        }

    available_rarities = [
        rarity
        for rarity in SPIN_RARITIES
        if rarity_weights.get(
            rarity,
            0,
        ) > 0
    ]

    if not available_rarities:

        available_rarities = [
            "common"
        ]

    if len(available_rarities) == 1:

        chosen_entries = [
            entry
            for rarity, entry, _weight in weighted_entries
            if rarity == available_rarities[0]
        ]
        chosen_weights = [
            max(
                0,
                float(
                    entry.get(
                        "chance",
                        1,
                    )
                ),
            )
            for entry in chosen_entries
        ]

        if not any(chosen_weights):

            chosen_weights = [
                1
                for _entry in chosen_entries
            ]

        return random.choices(
            chosen_entries,
            weights=chosen_weights,
            k=1,
        )[0]

    chosen_rarity = random.choices(
        available_rarities,
        weights=[
            rarity_weights[rarity]
            for rarity in available_rarities
        ],
        k=1,
    )[0]

    chosen_entries = [
        entry
        for rarity, entry, _weight in weighted_entries
        if rarity == chosen_rarity
    ]

    chosen_weights = [
        max(
            0,
            float(
                entry.get(
                    "chance",
                    1,
                )
            ),
        )
        for entry in chosen_entries
    ]

    if not any(chosen_weights):

        chosen_weights = [
            1
            for _ in chosen_entries
        ]

    return random.choices(
        chosen_entries,
        weights=chosen_weights,
        k=1,
    )[0]


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
) -> bool | None:
    """Execute the action preset linked to a winning spin item."""

    if not action_id:

        return None

    from app.auth.service import (
        active_runtime_plan,
        runtime_item_is_allowed,
    )

    runtime_plan = active_runtime_plan()

    if (
        runtime_plan is None
        or
        not runtime_item_is_allowed(
            "action",
            action_id,
            runtime_plan,
        )
    ):

        print(
            "[SPIN_WIDGET] Linked action locked by plan:",
            action_id,
        )

        return False

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

        return False

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

            action[
                "_action_preset_id"
            ] = action_id

            action_executor.execute(
                action,
                deadline=deadline,
            )

    print(
        "[SPIN_WIDGET] Linked action executed:",
        action_id,
    )

    return True


def send_spin_notice(
    event: LiveEvent,
    access: dict,
) -> None:
    """Show an automatic access/cooldown reply on connected overlays."""

    websocket_manager.send_event(
        {
            "type": "spin_notice",
            "data": {
                "user": event.user or "Guest",
                "message": access.get(
                    "reply",
                    "",
                ),
                "viewer_type": access.get(
                    "viewer_type",
                    "non_follower",
                ),
                "viewer_status": access.get(
                    "viewer_status",
                    "Viewer",
                ),
                "remaining_seconds": access.get(
                    "remaining_seconds",
                    0,
                ),
            },
        }
    )


def run_spin_job(
    job: dict,
) -> None:
    """Play one complete spin, then run its linked action."""

    spin_ms = int(
        job.get(
            "spin_ms",
            SPIN_DURATION_MS,
        )
    )
    result_hold_ms = int(
        job.get(
            "result_hold_ms",
            SPIN_RESULT_HOLD_MS,
        )
    )

    websocket_manager.send_event(
        {
            "type": "spin",
            "data": {
                "user": job["event"].user or "Guest",
                "viewer_avatar_url": (
                    job.get(
                        "viewer_avatar_url",
                        ""
                    )
                    or ""
                ),
                "command": SPIN_COMMAND,
                "segments": job["segments"],
                "chances": job.get(
                    "chances",
                    [],
                ),
                "rarities": job.get(
                    "rarities",
                    [],
                ),
                "result": job["result"],
                "winner_index": job.get(
                    "winner_index",
                    0,
                ),
                "winner_rarity": job.get(
                    "winner_rarity",
                    "common",
                ),
                "action_id": job["action_id"],
                "spin_ms": spin_ms,
                "result_hold_ms": result_hold_ms,
            },
        }
    )

    action_start_buffer_ms = int(
        job.get(
            "action_start_buffer_ms",
            SPIN_ACTION_START_BUFFER_MS,
        )
    )

    time.sleep(
        (spin_ms + action_start_buffer_ms) / 1000
    )

    action_started = time.monotonic()
    execute_linked_action(
        job["action_id"],
        job["event"],
    )
    action_elapsed = (
        time.monotonic()
        -
        action_started
    )

    remaining_hold = max(
        0,
        (
            result_hold_ms
            -
            action_start_buffer_ms
        )
        / 1000
        -
        action_elapsed,
    )
    if remaining_hold:

        time.sleep(
            remaining_hold
        )


def spin_worker() -> None:
    """Process spin jobs sequentially so animations never overlap."""

    while True:

        job = _spin_jobs.get()

        try:

            run_spin_job(
                job
            )

        except Exception as error:

            print(
                "[SPIN_WIDGET] Spin job failed:",
                error,
            )

        finally:

            _spin_jobs.task_done()


def enqueue_spin_job(
    job: dict,
) -> int:
    """Queue a spin and lazily start the single background worker."""

    global _spin_worker_started

    with _spin_worker_lock:

        queue_position = max(
            1,
            _spin_jobs.qsize() + 1,
        )
        _spin_jobs.put(
            job
        )

        if not _spin_worker_started:

            threading.Thread(
                target=spin_worker,
                name="tbana-spin-worker",
                daemon=True,
            ).start()
            _spin_worker_started = True

    return queue_position


def trigger_spin_command(
    event: LiveEvent,
) -> dict | None:
    """Trigger spin widget when a viewer comments !spin."""

    simulator_event = bool(
        event.data.get(
            "_simulator"
        )
    )

    if (
        not simulator_event
        and
        not spin_enabled()
    ):

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

    if not command.startswith(SPIN_COMMAND):

        return None

    access = spin_access_details(
        event
    )

    if not access["allowed"]:

        print(
            "[SPIN_WIDGET]",
            access["reason"],
        )
        send_spin_notice(
            event,
            access,
        )

        return {
            "handled": True,
            "triggered": False,
            "reason": access["reason"],
            "reply": access["reply"],
            "viewer_type": access["viewer_type"],
            "viewer_status": access["viewer_status"],
            "remaining_seconds": access["remaining_seconds"],
        }

    entries = load_spin_entries()

    winning_entry = choose_spin_entry(
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
    winner_index = entries.index(
        winning_entry
    )
    winner_rarity = normalize_spin_rarity(
        winning_entry.get(
            "rarity",
            "common",
        )
    )

    action_id = winning_entry.get(
        "action_id"
    )

    overlay_connections = websocket_manager.connection_count(
        "spin"
    )

    queue_position = enqueue_spin_job(
        {
            "event": event,
            "viewer_avatar_url": (
                event.data.get(
                    "viewer_avatar_url",
                    ""
                )
                or ""
            ),
            "segments": segments,
            "chances": [
                entry.get(
                    "chance",
                    1,
                )
                for entry in entries
            ],
            "rarities": [
                normalize_spin_rarity(
                    entry.get(
                        "rarity",
                        "common",
                    )
                )
                for entry in entries
            ],
            "result": result,
            "winner_index": winner_index,
            "winner_rarity": winner_rarity,
            "action_id": action_id,
            "spin_ms": SPIN_DURATION_MS,
            "result_hold_ms": SPIN_RESULT_HOLD_MS,
            "action_start_buffer_ms": SPIN_ACTION_START_BUFFER_MS,
        }
    )

    print(
        "[SPIN_WIDGET] Queued:",
        event.user,
        "->",
        result,
        "(position",
        queue_position,
        ")",
    )

    return {
        "handled": True,
        "triggered": True,
        "queued": True,
        "queue_position": queue_position,
        "result": result,
        "winner_rarity": winner_rarity,
        "action_id": action_id,
        "action_blocked": False,
        "overlay_connections": overlay_connections,
        "viewer_avatar_url": (
            event.data.get(
                "viewer_avatar_url",
                ""
            )
            or ""
        ),
        "viewer_type": access["viewer_type"],
        "viewer_status": access["viewer_status"],
    }
