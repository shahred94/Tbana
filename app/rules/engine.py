"""LiveTrigger rules engine."""

from app.core.events import LiveEvent
from app.storage.sqlite_store import get_gift_rule


class RulesEngine:
    """Processes live events against configured rules."""


    def process(
        self,
        event: LiveEvent,
    ) -> dict:
        """Process incoming live event."""


        # Gift rules from SQLite
        if event.event_type == "gift":

            gift_name = event.data.get(
                "gift_name"
            )


            rule = get_gift_rule(
                gift_name
            )


            if rule:

                actions = []


                # Sound action
                if rule.get("sound"):

                    actions.append(
                        {
                            "type": "sound",
                            "sound": rule["sound"],
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