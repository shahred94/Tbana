"""TBana Stream event engine."""

import json
import random
import threading
import time
from urllib.parse import quote

from app.core.events import LiveEvent

from app.storage.sqlite_store import (
    get_event_triggers,
    get_action_presets,
    get_action_steps,
    normalize_gift_name,
    get_setting,
)

from app.actions.executor import (
    action_executor,
)

from app.queue.manager import (
    gift_queue_manager,
)

from app.widgets.spin import (
    spin_command,
    trigger_spin_command,
)
from app.core.activity import activity_feed

class EventEngine:
    """Process dynamic events."""

    COMBO_SOUND_STAGGER_SECONDS = 0.08

    IMMEDIATE_STEP_TYPES = {
        "keyboard",
        "webhook",
    }

    def __init__(self):

        self.like_counters = {}
        self.follow_trigger_used = False


    def reset_live_session(self) -> None:

        """Reset per-live one-shot triggers."""

        self.follow_trigger_used = False


    def process(
        self,
        event: LiveEvent,
    ) -> dict:

        """Process incoming event."""

        from app.auth.service import (
            active_runtime_plan,
            runtime_allowed_item_ids,
        )

        runtime_plan = active_runtime_plan()

        if runtime_plan is None:

            print(
                "[EVENT_ENGINE] Event skipped: login is required."
            )

            return {
                "matched": False,
                "event_type": event.event_type,
                "actions": [],
                "spin": None,
                "blocked": "LOGIN_REQUIRED",
            }

        allowed_trigger_ids = runtime_allowed_item_ids(
            "trigger",
            runtime_plan,
        )
        allowed_action_ids = runtime_allowed_item_ids(
            "action",
            runtime_plan,
        )

        if (
            event.event_type.lower() == "follow"
            and self.follow_trigger_used
        ):

            print(
                "[EVENT_ENGINE] Follow skipped: already handled for this live."
            )

            return {
                "matched": False,
                "event_type": event.event_type,
                "actions": [],
                "spin": None,
                "blocked": "FOLLOW_ALREADY_HANDLED",
            }

        actions = []
        if event.event_type.lower() == "follow":

            self.follow_trigger_used = True

        spin_result = trigger_spin_command(
            event
        )

        triggers = get_event_triggers()
        action_presets = {
            action["id"]: action
            for action in get_action_presets()
        }


        for item in triggers:

            if (
                allowed_trigger_ids is not None
                and
                item["id"] not in allowed_trigger_ids
            ):

                print(
                    "[EVENT_ENGINE] Trigger locked by plan:",
                    item["id"],
                )

                continue

            if not item["enabled"]:

                continue

            if (
                spin_result
                and
                spin_result.get(
                    "handled"
                )
                and
                str(
                    item.get(
                        "trigger_type",
                        "",
                    )
                ).lower() == "comment"
                and
                str(
                    item.get(
                        "trigger_value",
                        "",
                    )
                ).strip().lower().startswith(
                    spin_command()
                )
            ):

                # The built-in wheel owns this command. Its linked action runs
                # only after the animation; generic triggers would fire too early.
                continue


            if not self.match_trigger(
                event,
                item,
            ):

                continue

            user_filter = (
                item["user_filter"]
            )

            if (
                user_filter
                and
                user_filter.upper()
                != "ANY"
            ):

                if (
                    not event.user
                    or
                    event.user.lower()
                    != user_filter.lower()
                ):

                    print(
                        "User blocked:",
                        event.user
                    )

                    continue

            item_actions = []

            for action_id in self.resolve_action_ids(
                item
            ):

                action_preset = (
                    action_presets.get(
                        action_id
                    )
                )

                if (
                    not action_preset
                    or
                    not action_preset["enabled"]
                    or
                    (
                        allowed_action_ids is not None
                        and
                        action_id not in allowed_action_ids
                    )
                ):

                    print(
                        "[EVENT_ENGINE] Action disabled or missing:",
                        action_id,
                    )

                    continue

                action_name = action_preset[
                    "name"
                ]

                action_steps = get_action_steps(
                    action_id
                )

                print(
                    "[EVENT_ENGINE] Trigger match:",
                    event.event_type,
                    "-> Action Preset:",
                    action_id,
                    action_name
                )

                print(
                    "[EVENT_ENGINE] action_steps loaded:",
                    action_steps
                )

                for action_step in action_steps:

                    action = self.build_action_from_step(
                        event,
                        action_step,
                    )


                    if action:

                        if (
                            action.get(
                                "type"
                            )
                            ==
                            "sound"
                        ):

                            action[
                                "volume"
                            ] = action_preset.get(
                                "media_volume",
                                100,
                            )

                        action[
                            "_action_preset_id"
                        ] = action_id

                        action[
                            "_action_preset_name"
                        ] = action_name

                        action[
                            "max_duration"
                        ] = action_preset.get(
                            "duration",
                            0,
                        )

                        action[
                            "execution_type"
                        ] = action_preset.get(
                            "execution_type",
                            "auto",
                        )

                        try:
                            action["stagger_delay_ms"] = max(
                                0,
                                min(10000, int(get_setting(
                                    f"action_stagger_delay_ms:{action_id}"
                                ) or 100)),
                            )
                        except (TypeError, ValueError):
                            action["stagger_delay_ms"] = 100

                        action[
                            "_step_id"
                        ] = action_step.get(
                            "id"
                        )

                        action[
                            "_step_order"
                        ] = action_step.get(
                            "order"
                        )

                        actions.append(
                            action
                        )

                        item_actions.append(
                            action
                        )

            if not item_actions:

                continue

            self.execute_actions(
                event,
                item,
                item_actions,
            )
        result = {
            "matched": len(actions) > 0,
            "event_type": event.event_type,
            "actions": actions,
            "spin": spin_result,
        }

        spin_triggered = bool(
            spin_result
            and
            spin_result.get(
                "triggered"
            )
        )

        if (
            result["matched"]
            or
            spin_triggered
            or
            event.event_type.lower()
            != "like"
        ):

            activity_feed.record(
                "event",
                (
                    "matched"
                    if result["matched"] or spin_triggered
                    else "ignored"
                ),
                f"{event.event_type.upper()} event",
                (
                    "Spin widget triggered"
                    if spin_triggered and not actions
                    else
                    ", ".join(
                        dict.fromkeys(
                            str(
                                action.get(
                                    "_action_preset_name",
                                    action.get("type", "Action"),
                                )
                            )
                            for action in actions
                        )
                    )
                    if actions
                    else "No matching enabled Action"
                ),
                event.user or "",
            )

        return result


    def resolve_action_ids(
        self,
        item: dict,
    ) -> list[int]:

        """Resolve one or more action presets for a trigger."""

        try:

            action_id = int(
                item.get(
                    "action_id",
                    0,
                )
                or
                0
            )

        except (
            TypeError,
            ValueError,
        ):

            action_id = 0

        action_mode = (
            item.get(
                "action_mode"
            )
            or
            "single"
        ).lower()

        try:

            action_ids = [
                int(value)
                for value in json.loads(
                    item.get(
                        "action_group",
                        "",
                    )
                    or
                    "[]"
                )
            ]

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):

            action_ids = []

        action_ids = [
            value
            for value in action_ids
            if value > 0
        ]

        if action_mode == "all":

            if action_ids:

                print(
                    "[EVENT_ENGINE] All actions selected:",
                    action_ids,
                )

                return action_ids

            return [
                action_id
            ] if action_id > 0 else []

        if action_mode != "random":

            return [
                action_id
            ] if action_id > 0 else action_ids

        if not action_ids:

            return [
                action_id
            ] if action_id > 0 else []

        chosen_action_id = random.choice(
            action_ids
        )

        print(
            "[EVENT_ENGINE] Random action selected:",
            chosen_action_id,
            "from",
            action_ids,
        )

        return [
            chosen_action_id
        ]


    def match_trigger(
        self,
        event: LiveEvent,
        item: dict,
    ) -> bool:

        """Check trigger match."""

        trigger_type = item[
            "trigger_type"
        ].lower()


        if trigger_type != event.event_type.lower():

            return False


        if trigger_type == "gift":

            trigger_gift_name = normalize_gift_name(
                item.get(
                    "trigger_value",
                    "",
                )
            )

            event_gift_name = normalize_gift_name(
                event.data.get(
                    "gift_name",
                    "",
                )
            )

            if not trigger_gift_name or not event_gift_name:

                return False

            return trigger_gift_name == event_gift_name


        if trigger_type == "comment":

            keyword = item[
                "trigger_value"
            ].lower().strip()


            comment = event.data.get(
                "comment",
                ""
            ).lower().strip()

            if keyword.startswith(
                "!"
            ):

                command = (
                    comment.split()[0]
                    if comment
                    else
                    ""
                )

                return command == keyword

            return keyword in comment


        if trigger_type == "like":

            return self.match_like_trigger(
                event,
                item,
            )


        if trigger_type == "follow":

            return True

        if trigger_type in {
            "share",
            "subscribe",
            "first_activity",
            "subscriber_emote",
            "fan_club_sticker",
            "tiktok_shop",
        }:

            return True

        if trigger_type == "gift_min_coins":

            required_value = int(
                item[
                    "trigger_value"
                ]
                or
                0
            )

            gift_value = int(
                event.data.get(
                    "coins",
                    event.data.get(
                        "diamond_count",
                        event.data.get(
                            "count",
                            0
                        )
                    )
                )
            )

            return gift_value >= required_value


        return False

    def match_like_trigger(
        self,
        event: LiveEvent,
        item: dict,
    ) -> bool:

        """Match cumulative TikTok like taps against a minimum threshold."""

        try:

            required_count = max(
                1,
                int(
                    item[
                        "trigger_value"
                    ]
                    or
                    1
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            required_count = 1

        try:

            event_count = max(
                0,
                int(
                    event.data.get(
                        "_raw_like_count",
                        event.data.get(
                            "count",
                            event.data.get(
                                "like_count",
                                0,
                            ),
                        ),
                    )
                    or
                    0
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            event_count = 0

        if event_count <= 0:

            return False

        event.data.setdefault(
            "_raw_like_count",
            event_count,
        )

        counter_key = (
            item.get(
                "id"
            ),
            event.user
            or
            "_anonymous",
        )

        accumulated_count = (
            self.like_counters.get(
                counter_key,
                0,
            )
            +
            event_count
        )

        if accumulated_count < required_count:

            self.like_counters[
                counter_key
            ] = accumulated_count

            print(
                "[EVENT_ENGINE] Like taps accumulated:",
                accumulated_count,
                "/",
                required_count,
                "for",
                event.user,
            )

            return False

        self.like_counters[
            counter_key
        ] = accumulated_count % required_count

        event.data[
            "count"
        ] = accumulated_count

        event.data[
            "like_threshold"
        ] = required_count

        print(
            "[EVENT_ENGINE] Like threshold matched:",
            accumulated_count,
            "/",
            required_count,
            "for",
            event.user,
        )

        return True


    def execute_actions(
        self,
        event: LiveEvent,
        item: dict,
        actions: list[dict],
    ) -> None:

        """Execute or queue matched actions."""

        execution_count = 1

        if event.event_type.lower() == "gift":

            try:

                execution_count = max(
                    1,
                    int(
                        event.data.get(
                            "count",
                            1,
                        )
                        or
                        1
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):

                execution_count = 1

        if (
            event.event_type.lower() == "gift"
            and
            not event.data.get(
                "_simulator"
            )
        ):

            action_groups = self.group_actions_by_preset(
                actions
            )

            queued_groups = []

            for action_group in action_groups:

                execution_type = self.action_execution_type(
                    action_group
                )

                if execution_type in {
                    "instant",
                    "staggered",
                }:

                    for repeat_index in range(
                        execution_count
                    ):

                        if execution_type == "staggered":
                            delay_ms = self.action_stagger_delay_ms(action_group)
                            timer = threading.Timer(
                                repeat_index * delay_ms / 1000,
                                self.execute_action_group,
                                args=(action_group, repeat_index, execution_count, "[STAGGERED]"),
                            )
                            timer.daemon = True
                            timer.start()
                        else:
                            self.execute_action_group(
                                action_group,
                                repeat_index,
                                execution_count,
                                log_prefix="[EVENT_ENGINE]",
                            )

                    print(
                        "[EVENT_ENGINE] Ran gift actions immediately:",
                        item["trigger_value"],
                        execution_type,
                        "x",
                        execution_count,
                        action_group,
                    )

                    continue

                queued_groups.append(
                    action_group
                )

            for repeat_index in range(
                execution_count
            ):

                for action_group in queued_groups:

                    gift_queue_manager.add_job_sync(
                        item["trigger_value"],
                        {
                            "user": event.user,
                            "actions": action_group,
                            "combo_index": (
                                repeat_index + 1
                            ),
                            "combo_count": (
                                execution_count
                            ),
                        },
                    )

            if queued_groups:

                print(
                    "[EVENT_ENGINE] Queued gift actions:",
                    item["trigger_value"],
                    "x",
                    execution_count,
                    queued_groups
                )

            return


        for repeat_index in range(
            execution_count
        ):

            self.execute_action_group(
                actions,
                repeat_index,
                execution_count,
                log_prefix="[EVENT_ENGINE]",
            )

    def execute_action_group(
        self,
        actions: list[dict],
        repeat_index: int,
        execution_count: int,
        log_prefix: str,
    ) -> None:

        """Execute one action preset group."""

        max_duration = self.action_max_duration(
            actions
        )

        deadline = (
            time.monotonic() + max_duration
            if max_duration > 0
            else None
        )

        for action in actions:

            if (
                deadline is not None
                and
                time.monotonic() >= deadline
            ):

                print(
                    log_prefix,
                    "Action duration reached; skipping remaining steps."
                )

                break

            print(
                log_prefix,
                "Executing action_step:",
                action.get(
                    "_step_order"
                ),
                action.get(
                    "type"
                ),
                "from",
                action.get(
                    "_action_preset_name"
                ),
                "combo",
                repeat_index + 1,
                "of",
                execution_count,
            )

            execution_action = {
                **action,
                "_combo_index": repeat_index + 1,
                "_combo_count": execution_count,
            }

            if (
                execution_action.get(
                    "type"
                )
                ==
                "sound"
                and
                execution_count > 1
            ):

                execution_action[
                    "_sound_start_delay"
                ] = (
                    repeat_index
                    *
                    self.COMBO_SOUND_STAGGER_SECONDS
                )

            action_executor.execute(
                execution_action,
                deadline=deadline,
            )

    def group_actions_by_preset(
        self,
        actions: list[dict],
    ) -> list[list[dict]]:

        """Keep each action preset together when deciding queue behavior."""

        groups = []
        current_group = []
        current_key = None

        for action in actions:

            action_key = (
                action.get(
                    "_action_preset_id"
                ),
                action.get(
                    "_action_preset_name"
                ),
            )

            if (
                current_group
                and
                action_key != current_key
            ):

                groups.append(
                    current_group
                )

                current_group = []

            current_key = action_key
            current_group.append(
                action
            )

        if current_group:

            groups.append(
                current_group
            )

        return groups

    def action_execution_type(
        self,
        actions: list[dict],
    ) -> str:

        """Classify action groups for gift execution."""

        for action in actions:

            execution_type = str(
                action.get(
                    "execution_type",
                    "",
                )
                or
                ""
            ).lower().strip()

            if execution_type in {
                "instant",
                "staggered",
                "long",
                "cinematic",
                "queue",
                "queued",
            }:

                if execution_type in {
                    "queue",
                    "queued",
                }:

                    return "long"

                return execution_type

        step_types = {
            str(
                action.get(
                    "type",
                    "",
                )
            ).lower().strip()
            for action in actions
        }

        duration = self.action_max_duration(actions)
        has_short_sound = (
            "sound" in step_types
            and 0 < duration <= 2
        )
        auto_instant_types = set(self.IMMEDIATE_STEP_TYPES)
        if has_short_sound:
            auto_instant_types.add("sound")

        if (
            step_types
            and step_types.issubset(auto_instant_types)
        ):

            return "instant"

        return "long"

    @staticmethod
    def action_stagger_delay_ms(actions: list[dict]) -> int:
        for action in actions:
            try:
                return max(0, min(10000, int(action.get("stagger_delay_ms", 100))))
            except (TypeError, ValueError):
                pass
        return 100

    @staticmethod
    def action_max_duration(
        actions: list[dict],
    ) -> float:

        """Return the action preset duration shared by its steps."""

        for action in actions:

            try:

                duration = float(
                    action.get(
                        "max_duration",
                        0,
                    )
                    or
                    0
                )

            except (
                TypeError,
                ValueError,
            ):

                duration = 0

            if duration > 0:

                return duration

        return 0


    def build_action_from_step(
        self,
        event: LiveEvent,
        item: dict,
    ) -> dict | None:

        """Create executor action from Action Builder V2 step."""

        action_type = (
            item.get(
                "type",
                ""
            )
            .lower()
        )

        action_value = item.get(
            "value"
        )


        return self.build_action_object(
            event,
            action_type,
            action_value,
        )


    def build_action(
        self,
        event: LiveEvent,
        item: dict,
    ) -> dict | None:

        """Create action object."""

        action_type = item[
            "action_type"
        ].lower()


        return self.build_action_object(
            event,
            action_type,
            item[
                "action_value"
            ],
        )


    def build_action_object(
        self,
        event: LiveEvent,
        action_type: str,
        action_value: str,
    ) -> dict | None:

        """Create executor action object."""

        if action_type == "sound":

            return {
                "type": "sound",
                "sound": action_value,
            }


        if action_type == "keyboard":

            return {
                "type": "keyboard",
                "key": action_value,
            }


        if action_type == "tts":

            tts_value = self.render_tts_value(
                event,
                action_value,
            )

            return {
                "type": "tts",
                "text": tts_value,
            }

        if action_type == "webhook":

            webhook_value = self.render_webhook_value(
                event,
                action_value,
            )

            return {
                "type": "webhook",
                "url": webhook_value,
                "payload": self.webhook_payload(
                    event
                ),
            }


        if action_type == "overlay":

            return {
                "type": "overlay",
                "name": action_value,
                "data": {
                    "user": event.user,
                    "event": event.event_type,
                },
            }


        return None


    @staticmethod
    def render_tts_value(
        event: LiveEvent,
        action_value: str,
    ) -> str:

        """Replace live-event placeholders in plain or JSON TTS values."""

        replacements = {
            "{user}": event.user or "",
            "{event}": event.event_type,
            "{comment}": event.data.get(
                "comment",
                "",
            ),
            "{gift}": event.data.get(
                "gift_name",
                "",
            ),
            "{count}": event.data.get(
                "count",
                "",
            ),
            "{coins}": event.data.get(
                "coins",
                event.data.get(
                    "diamond_count",
                    "",
                ),
            ),
        }

        try:

            config = json.loads(
                action_value
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):

            config = None

        if isinstance(
            config,
            dict,
        ):

            text = str(
                config.get(
                    "text",
                    "",
                )
            )

            for placeholder, value in replacements.items():

                text = text.replace(
                    placeholder,
                    str(value),
                )

            config["text"] = text

            return json.dumps(
                config,
                ensure_ascii=False,
            )

        text = str(
            action_value
            or
            ""
        )

        for placeholder, value in replacements.items():

            text = text.replace(
                placeholder,
                str(value),
            )

        return text

    @staticmethod
    def render_webhook_value(
        event: LiveEvent,
        action_value: str,
    ) -> str:

        """Replace live-event placeholders in webhook URLs."""

        count = event.data.get(
            "count",
            "",
        )

        replacements = {
            "{username}": event.user or "",
            "{nickname}": event.user or "",
            "{user}": event.user or "",
            "{event}": event.event_type,
            "{comment}": event.data.get(
                "comment",
                "",
            ),
            "{giftname}": event.data.get(
                "gift_name",
                "",
            ),
            "{gift}": event.data.get(
                "gift_name",
                "",
            ),
            "{repeatcount}": count,
            "{count}": count,
            "{likecount}": event.data.get(
                "like_count",
                count,
            ),
            "{totallikecount}": event.data.get(
                "total_like_count",
                event.data.get(
                    "totalLikeCount",
                    "",
                ),
            ),
            "{coins}": event.data.get(
                "coins",
                event.data.get(
                    "diamond_count",
                    "",
                ),
            ),
        }

        url = str(
            action_value
            or
            ""
        )

        for placeholder, value in replacements.items():

            url = url.replace(
                placeholder,
                quote(
                    str(
                        value
                    ),
                    safe="",
                ),
            )

        return url

    @staticmethod
    def webhook_payload(
        event: LiveEvent,
    ) -> dict:

        """Build TikFinity-style form data for local webhook receivers."""

        count = event.data.get(
            "count",
            "",
        )

        username = (
            event.data.get(
                "username"
            )
            or
            event.data.get(
                "unique_id"
            )
            or
            event.data.get(
                "uniqueId"
            )
            or
            event.user
            or
            ""
        )

        nickname = (
            event.data.get(
                "nickname"
            )
            or
            event.user
            or
            username
        )

        return {
            "username": username,
            "nickname": nickname,
            "user": username,
            "event": event.event_type,
            "comment": event.data.get(
                "comment",
                "",
            ),
            "giftname": event.data.get(
                "gift_name",
                "",
            ),
            "gift": event.data.get(
                "gift_name",
                "",
            ),
            "repeatcount": count,
            "count": count,
            "coins": event.data.get(
                "coins",
                event.data.get(
                    "diamond_count",
                    "",
                ),
            ),
        }

event_engine = EventEngine()
