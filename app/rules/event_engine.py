"""TBana Stream event engine."""

import json
import random
import time

from app.core.events import LiveEvent

from app.storage.sqlite_store import (
    get_event_triggers,
    get_action_presets,
    get_action_steps,
    normalize_gift_name,
)

from app.actions.executor import (
    action_executor,
)

from app.queue.manager import (
    gift_queue_manager,
)

from app.widgets.spin import (
    trigger_spin_command,
)
from app.core.activity import activity_feed

class EventEngine:
    """Process dynamic events."""


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
                ).strip().lower().startswith("!spin")
            ):

                # The built-in wheel owns !spin. Its linked action runs only
                # after the animation; generic triggers would fire too early.
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

            for repeat_index in range(
                execution_count
            ):

                gift_queue_manager.add_job_sync(
                    item["trigger_value"],
                    {
                        "user": event.user,
                        "actions": actions,
                        "combo_index": (
                            repeat_index + 1
                        ),
                        "combo_count": (
                            execution_count
                        ),
                    },
                )

            print(
                "[EVENT_ENGINE] Queued gift actions:",
                item["trigger_value"],
                "x",
                execution_count,
                actions
            )

            return


        for repeat_index in range(
            execution_count
        ):

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
                        "[EVENT_ENGINE] Action duration reached; skipping remaining steps."
                    )

                    break

                print(
                    "[EVENT_ENGINE] Executing action_step:",
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

                action_executor.execute(
                    action,
                    deadline=deadline,
                )

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

            return {
                "type": "webhook",
                "url": action_value,
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

event_engine = EventEngine()
