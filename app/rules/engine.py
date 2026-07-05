"""TBana Stream rules engine."""

from app.core.events import LiveEvent
from app.storage.sqlite_store import (
    get_gift_rule,
)


class RulesEngine:
    """Processes live events against configured rules."""


    def process(
        self,
        event: LiveEvent,
    ) -> dict:
        """Process incoming live event."""

        from app.auth.service import (
            active_authenticated_session_exists,
        )

        if not active_authenticated_session_exists():

            return {
                "matched": False,
                "event_type": event.event_type,
                "actions": [],
                "blocked": "LOGIN_REQUIRED",
            }

        # Gift rules from SQLite
        if event.event_type == "gift":

            gift_name = event.data.get(
                "gift_name"
            )

            try:

                gift_repeat_count = max(
                    1,
                    int(
                        event.data.get(
                            "count",
                            1
                        )
                        or
                        1
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):

                gift_repeat_count = 1

            rule = get_gift_rule(
                gift_name
            )


            if rule and not rule.get("enabled", True):

                return {
                    "matched": False,
                    "event_type": event.event_type,
                    "actions": [],
                }


            if rule:

                actions = []


                # Sound action
                sound_file = (
                    rule.get("sound")
                    or
                    rule.get("sound_file")
                )

                if sound_file:

                    actions.append(
                        {
                            "type": "sound",
                            "sound": sound_file,
                        }
                    )


                # Overlay action
                if rule.get("overlay"):

                    actions.append(
                        {
                            "type": "overlay",
                            "name": rule["overlay"],
                            "data": {
                                "user": event.user,
                                "gift": gift_name,
                                "count": event.data.get(
                                    "count",
                                    1
                                ),
                            },
                        }
                    )

                actions = actions * gift_repeat_count


                return {
                    "matched": True,
                    "event_type": event.event_type,
                    "actions": actions,
                }


        # No matching rule
        return {
            "matched": False,
            "event_type": event.event_type,
            "actions": [],
        }


rules_engine = RulesEngine()
