"""Action execution manager."""

from app.actions.sound import sound_action
from app.actions.overlay import overlay_action


class ActionManager:
    """Execute actions from Rules Engine."""

    def execute(
        self,
        actions: list[dict]
    ) -> None:

        for action in actions:

            action_type = action.get("type")

            if action_type == "message":

                print(
                    "[MESSAGE]",
                    action.get("text")
                )


            elif action_type == "sound":

                result = sound_action.play(
                    action.get("sound")
                )

                print(
                    "[SOUND]",
                    result
                )


            elif action_type == "overlay":

                result = overlay_action.show(
                    action.get("overlay"),
                    action.get("data")
                )

                print(
                    "[OVERLAY]",
                    result
                )


action_manager = ActionManager()