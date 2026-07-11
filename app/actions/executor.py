"""TBana Stream action executor."""

from pathlib import Path

import asyncio
import json
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import edge_tts
import pygame
import pyautogui

from app.actions.windows_input import send_key_combo
from app.core.paths import data_path


class ActionExecutor:
    """Execute actions from Event Engine."""


    def __init__(self):

        self.audio_lock = threading.RLock()
        self.music_generation = 0
        self.sound_cache = {}

        try:

            pygame.mixer.init()
            pygame.mixer.set_num_channels(
                max(
                    pygame.mixer.get_num_channels(),
                    32,
                )
            )

            print(
                "Audio system initialized."
            )

        except Exception as error:

            print(
                "Audio initialization failed:",
                error
            )


    def execute(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Execute action."""

        from app.auth.service import (
            active_runtime_plan,
            runtime_item_is_allowed,
        )

        runtime_plan = active_runtime_plan()

        if runtime_plan is None:

            print(
                "Action skipped: login is required."
            )

            return

        action_preset_id = action.get(
            "_action_preset_id"
        )

        if (
            action_preset_id is not None
            and
            not runtime_item_is_allowed(
                "action",
                int(action_preset_id),
                runtime_plan,
            )
        ):

            print(
                "Action skipped: locked by plan:",
                action_preset_id,
            )

            return

        if deadline is None:

            deadline = self.deadline_from_action(
                action
            )

        action_type = (
            action.get(
                "type",
                ""
            )
            .lower()
            .strip()
        )


        if action_type == "sound":

            self.play_sound(
                action,
                deadline=deadline,
            )


        elif action_type == "keyboard":

            self.press_key(
                action,
                deadline=deadline,
            )


        elif action_type == "overlay":

            self.show_overlay(
                action,
                deadline=deadline,
            )


        elif action_type == "tts":

            self.speak_text(
                action,
                deadline=deadline,
            )

        elif action_type == "webhook":

            self.trigger_webhook(
                action,
                deadline=deadline,
            )


        else:

            print(
                "Unknown action:",
                action_type
            )

    def stop_audio(self) -> None:
        """Stop the shared streamed audio channel, including active TTS."""

        # Do not take audio_lock here: playback intentionally owns it for the
        # whole clip and Skip must be able to interrupt that clip.
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

    @staticmethod
    def deadline_from_action(
        action: dict,
    ) -> float | None:

        """Build a deadline from an action max duration."""

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

        if duration <= 0:

            return None

        return time.monotonic() + duration

    @staticmethod
    def remaining_seconds(
        deadline: float | None,
    ) -> float | None:

        """Return remaining seconds before an optional deadline."""

        if deadline is None:

            return None

        return max(
            0,
            deadline - time.monotonic(),
        )


    def play_sound(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Play sound action."""

        sound_file = data_path(
            "sounds",
            Path(action.get("sound", "")).name,
        )


        if not sound_file.exists():

            print(
                "Sound file not found:",
                sound_file
            )

            return


        try:

            volume = max(
                0,
                min(
                    100,
                    int(
                        action.get(
                            "volume",
                            100,
                        )
                    )
                )
            )

            sound = self.get_sound_effect(
                sound_file
            )

            sound.set_volume(
                volume / 100
            )

            start_delay = self.sound_start_delay(
                action
            )

            if start_delay > 0:

                timer = threading.Timer(
                    start_delay,
                    self.start_sound_effect,
                    args=(
                        sound,
                        deadline,
                    ),
                )

                timer.daemon = True
                timer.start()

            else:

                self.start_sound_effect(
                    sound,
                    deadline,
                )

            print(
                "Playing sound:",
                sound_file.name,
                "volume:",
                volume,
                "delay:",
                round(
                    start_delay,
                    3,
                ),
            )


        except Exception as error:

            print(
                "Sound playback failed:",
                error
            )

    @staticmethod
    def sound_start_delay(
        action: dict,
    ) -> float:

        """Return optional delayed start for repeated combo sound effects."""

        try:

            return max(
                0.0,
                float(
                    action.get(
                        "_sound_start_delay",
                        0,
                    )
                    or
                    0
                ),
            )

        except (
            TypeError,
            ValueError,
        ):

            return 0.0

    def start_sound_effect(
        self,
        sound,
        deadline: float | None = None,
    ) -> None:

        """Start one sound-effect playback and stop it at the deadline."""

        channel = sound.play()

        remaining = self.remaining_seconds(
            deadline
        )

        if (
            channel is not None
            and
            remaining is not None
            and
            remaining > 0
        ):

            timer = threading.Timer(
                remaining,
                self.stop_sound_channel,
                args=(
                    channel,
                ),
            )

            timer.daemon = True
            timer.start()

    def get_sound_effect(
        self,
        sound_file: Path,
    ):

        """Load and cache a sound effect for overlapping playback."""

        if not pygame.mixer.get_init():

            pygame.mixer.init()

        pygame.mixer.set_num_channels(
            max(
                pygame.mixer.get_num_channels(),
                32,
            )
        )

        cache_key = str(
            sound_file.resolve()
        )

        modified_time = sound_file.stat().st_mtime

        with self.audio_lock:

            cached = self.sound_cache.get(
                cache_key
            )

            if (
                cached
                and
                cached[0] == modified_time
            ):

                return cached[1]

            sound = pygame.mixer.Sound(
                str(sound_file)
            )

            self.sound_cache[
                cache_key
            ] = (
                modified_time,
                sound,
            )

            return sound

    @staticmethod
    def stop_sound_channel(
        channel,
    ) -> None:

        """Stop one sound-effect channel when an action deadline expires."""

        try:

            if (
                channel is not None
                and
                channel.get_busy()
            ):

                channel.stop()

        except Exception as error:

            print(
                "Timed sound channel stop failed:",
                error,
            )

    def stop_music_if_busy(
        self,
        music_generation: int,
    ):

        """Stop currently playing mixer music when action duration expires."""

        try:

            if music_generation != self.music_generation:

                return

            if (
                pygame.mixer.get_init()
                and
                pygame.mixer.music.get_busy()
            ):

                pygame.mixer.music.stop()

        except Exception as error:

            print(
                "Timed sound stop failed:",
                error
            )

    def next_music_generation(
        self,
    ) -> int:

        """Mark a new mixer music playback generation."""

        with self.audio_lock:

            self.music_generation += 1

            return self.music_generation


    def press_key(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Execute keyboard action."""

        key = action.get(
            "key"
        )


        if not key:

            print(
                "Keyboard key missing."
            )

            return

        if (
            deadline is not None
            and
            self.remaining_seconds(
                deadline
            )
            <= 0
        ):

            print(
                "Keyboard action skipped: action duration reached."
            )

            return


        try:

            key = key.lower().strip()

            if key.startswith("{"):

                self.press_key_config(
                    key,
                    deadline=deadline,
                )

                return


            if "+" in key:

                keys = [
                    k.strip()
                    for k in key.split("+")
                ]


                pyautogui.hotkey(
                    *keys
                )


                print(
                    "Key combo pressed:",
                    " + ".join(keys)
                )


            else:

                pyautogui.press(
                    key
                )


                print(
                    "Key pressed:",
                    key
                )


        except Exception as error:

            print(
                "Keyboard action failed:",
                error
            )


    def press_key_config(
        self,
        key_config: str,
        deadline: float | None = None,
    ):

        """Execute structured keyboard config."""

        config = json.loads(
            key_config
        )

        sequence = str(
            config.get(
                "sequence",
                "",
            )
        )

        modifiers = [
            value
            for value in [
                "ctrl"
                if config.get(
                    "ctrl"
                )
                else None,
                "alt"
                if config.get(
                    "alt"
                )
                else None,
                "shift"
                if config.get(
                    "shift"
                )
                else None,
            ]
            if value
        ]

        hold_seconds = max(
            0,
            int(
                config.get(
                    "hold_ms",
                    100,
                )
            )
        ) / 1000

        remaining = self.remaining_seconds(
            deadline
        )

        if remaining is not None:

            if remaining <= 0:

                print(
                    "Configured keyboard action skipped: action duration reached."
                )

                return

            hold_seconds = min(
                hold_seconds,
                remaining,
            )

        compatibility_mode = bool(
            config.get(
                "compatibility_mode"
            )
        )

        if not sequence:

            print(
                "Keyboard sequence missing."
            )

            return

        normalized = sequence.lower().strip()

        mouse_actions = {
            "left_mouse_click":
            pyautogui.click,
            "right_mouse_click":
            pyautogui.rightClick,
        }

        if normalized in mouse_actions:

            mouse_actions[
                normalized
            ]()

            print(
                "Mouse action:",
                normalized
            )

            return

        special_keys = {
            "enter": "enter",
            "space": "space",
            "esc": "esc",
            "tab": "tab",
            "backspace": "backspace",
            "break": "pause",
            "caps lock": "capslock",
            "delete": "delete",
            "up arrow": "up",
            "right arrow": "right",
            "left arrow": "left",
            "down arrow": "down",
            "end": "end",
            "home": "home",
            "insert": "insert",
        }

        if normalized in special_keys:

            key_name = special_keys[
                normalized
            ]

            keys = modifiers + [
                key_name
            ]

            self.send_keyboard_combo(
                keys,
                compatibility_mode,
                hold_seconds,
            )

            print(
                "Configured key pressed:",
                " + ".join(keys)
            )

            return

        if re_match := (
            normalized
            if normalized.startswith(
                "f"
            )
            and normalized[1:].isdigit()
            else None
        ):

            keys = modifiers + [
                re_match
            ]

            self.send_keyboard_combo(
                keys,
                compatibility_mode,
                hold_seconds,
            )

            print(
                "Configured function key pressed:",
                " + ".join(keys)
            )

            return

        for character in sequence:

            keys = modifiers + [
                character.lower()
            ]

            self.send_keyboard_combo(
                keys,
                compatibility_mode,
                hold_seconds,
            )

        print(
            "Configured key sequence pressed:",
            sequence,
        )

    @staticmethod
    def send_keyboard_combo(
        keys: list[str],
        compatibility_mode: bool,
        hold_seconds: float,
    ):

        """Send a key combo using Windows scan codes when requested."""

        if compatibility_mode:

            try:

                send_key_combo(
                    keys,
                    hold_seconds,
                )

                return

            except Exception as error:

                print(
                    "Windows game input failed; using standard input:",
                    error,
                )

        pyautogui.hotkey(
            *keys
        )


    def show_overlay(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Show overlay action."""

        print(
            "Showing overlay:",
            action.get(
                "name"
            )
        )


    def speak_text(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Generate and play speech using Microsoft Edge TTS."""

        from app.auth.service import (
            active_pro_session_exists,
        )

        if not active_pro_session_exists():

            print(
                "Edge TTS skipped: an active Pro login is required."
            )

            return

        raw_value = (
            action.get(
                "text"
            )
            or
            action.get(
                "value"
            )
            or
            ""
        )

        config = self.parse_tts_config(
            raw_value
        )

        speech_text = config[
            "text"
        ].strip()


        if not speech_text:

            print(
                "TTS text missing."
            )

            return

        try:

            self.run_async(
                self.generate_and_play_tts(
                    speech_text,
                    config,
                    deadline=deadline,
                )
            )

            print(
                "Edge TTS spoken:",
                config["voice"],
                speech_text,
            )


        except Exception as error:

            print(
                "Edge TTS failed:",
                error
            )

    @staticmethod
    def parse_tts_config(
        raw_value,
    ) -> dict:

        """Parse new JSON settings while supporting old plain-text TTS."""

        defaults = {
            "text": "",
            "voice": "ms-MY-YasminNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
        }

        if isinstance(
            raw_value,
            dict,
        ):

            value = raw_value

        else:

            text_value = str(
                raw_value
                or
                ""
            ).strip()

            try:

                decoded = json.loads(
                    text_value
                )

                value = (
                    decoded
                    if isinstance(
                        decoded,
                        dict,
                    )
                    else {
                        "text": text_value
                    }
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):

                value = {
                    "text": text_value
                }

        for key in defaults:

            if key in value:

                defaults[key] = str(
                    value[key]
                    or
                    defaults[key]
                )

        return defaults

    @staticmethod
    def run_async(
        coroutine,
    ):

        """Run an async Edge TTS operation from sync or async callers."""

        try:

            asyncio.get_running_loop()

        except RuntimeError:

            return asyncio.run(
                coroutine
            )

        result = {}
        failure = {}

        def runner():

            try:

                result["value"] = asyncio.run(
                    coroutine
                )

            except Exception as error:

                failure["error"] = error

        worker = threading.Thread(
            target=runner,
            daemon=True,
        )

        worker.start()
        worker.join()

        if "error" in failure:

            raise failure["error"]

        return result.get(
            "value"
        )

    async def generate_and_play_tts(
        self,
        speech_text: str,
        config: dict,
        deadline: float | None = None,
    ) -> None:

        """Download Edge TTS audio to a temporary MP3 and play it."""

        temporary_path = None

        try:

            with tempfile.NamedTemporaryFile(
                suffix=".mp3",
                delete=False,
            ) as temporary_file:

                temporary_path = Path(
                    temporary_file.name
                )

            communicate = edge_tts.Communicate(
                speech_text,
                config["voice"],
                rate=config["rate"],
                volume=config["volume"],
                pitch=config["pitch"],
            )

            await communicate.save(
                str(
                    temporary_path
                )
            )

            with self.audio_lock:

                if not pygame.mixer.get_init():

                    pygame.mixer.init()

                pygame.mixer.music.load(
                    str(
                        temporary_path
                    )
                )

                self.next_music_generation()

                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():

                    if (
                        deadline is not None
                        and
                        self.remaining_seconds(
                            deadline
                        )
                        <= 0
                    ):

                        pygame.mixer.music.stop()
                        break

                    time.sleep(
                        0.05
                    )

                pygame.mixer.music.unload()

        finally:

            if (
                temporary_path
                and
                temporary_path.exists()
            ):

                try:

                    temporary_path.unlink()

                except OSError:

                    pass


    def trigger_webhook(
        self,
        action: dict,
        deadline: float | None = None,
    ):

        """Trigger a webhook URL."""

        url = (
            action.get(
                "url"
            )
            or
            action.get(
                "webhook"
            )
            or
            action.get(
                "value"
            )
            or
            ""
        ).strip()

        if not url:

            print(
                "Webhook URL missing."
            )

            return

        if not (
            url.startswith(
                "http://"
            )
            or
            url.startswith(
                "https://"
            )
        ):

            print(
                "Webhook URL must start with http:// or https://:",
                url
            )

            return

        try:

            timeout = 5

            remaining = self.remaining_seconds(
                deadline
            )

            if remaining is not None:

                if remaining <= 0:

                    print(
                        "Webhook skipped: action duration reached."
                    )

                    return

                timeout = max(
                    0.1,
                    min(
                        timeout,
                        remaining,
                    ),
                )

            webhook_payload = action.get(
                "payload"
            )

            parsed_url = urllib.parse.urlparse(
                url
            )

            use_tikfinity_form = (
                isinstance(
                    webhook_payload,
                    dict,
                )
                and
                parsed_url.hostname
                in {
                    "127.0.0.1",
                    "localhost",
                }
                and
                parsed_url.port == 6721
            )

            data = None
            method = "GET"
            headers = {
                "User-Agent":
                "TBanaStream/2.0",
            }

            if use_tikfinity_form:

                data = urllib.parse.urlencode(
                    webhook_payload
                ).encode(
                    "utf-8"
                )
                method = "POST"
                headers[
                    "Content-Type"
                ] = "application/x-www-form-urlencoded"

            request = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers=headers,
            )

            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:

                print(
                    "Webhook triggered:",
                    url,
                    "status:",
                    response.status,
                )

        except urllib.error.URLError as error:

            print(
                "Webhook failed:",
                url,
                error,
            )

        except Exception as error:

            print(
                "Webhook failed:",
                url,
                error,
            )


action_executor = ActionExecutor()
