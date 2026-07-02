"""Sound action."""

from pathlib import Path

import pygame


class SoundAction:
    """Play sound files."""

    def __init__(self):
        pygame.mixer.init()

        self.sound_folder = (
            Path(__file__)
            .parent.parent.parent
            / "assets"
            / "sounds"
        )


    def play(self, sound_name: str) -> dict[str, str]:
        """Play an MP3 file."""

        sound_path = self.sound_folder / sound_name


        if not sound_path.exists():
            return {
                "action": "sound",
                "sound": sound_name,
                "status": "file_not_found",
            }


        try:
            pygame.mixer.music.load(
                str(sound_path)
            )

            pygame.mixer.music.play()

            return {
                "action": "sound",
                "sound": sound_name,
                "status": "playing",
            }


        except Exception as error:
            return {
                "action": "sound",
                "sound": sound_name,
                "status": f"error: {error}",
            }


sound_action = SoundAction()