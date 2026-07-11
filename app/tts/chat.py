"""Queued text-to-speech for TikTok LIVE comments."""

from __future__ import annotations

import json
import queue
import re
import threading
from dataclasses import asdict, dataclass

from app.actions.executor import action_executor
from app.storage.sqlite_store import get_setting, set_setting


SETTING_KEY = "chat_tts_config"


@dataclass
class ChatTTSConfig:
    enabled: bool = False
    voice: str = "ms-MY-YasminNeural"
    rate: int = 0
    volume: int = 0
    pitch: int = 0
    template: str = "{nickname} berkata, {comment}"
    comment_mode: str = "any"
    prefix: str = "."
    command: str = "!tts"
    allow_non_followers: bool = True
    allow_followers: bool = True
    allow_fan_club: bool = True
    allow_subscribers: bool = True
    allowed_users: str = ""
    blocked_users: str = ""
    blocked_words: str = ""
    max_length: int = 180
    max_queue: int = 20


def _bounded(value, minimum: int, maximum: int, default: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_config(value: dict | None) -> ChatTTSConfig:
    defaults = asdict(ChatTTSConfig())
    incoming = value if isinstance(value, dict) else {}
    merged = {**defaults, **{key: incoming[key] for key in defaults if key in incoming}}
    merged["comment_mode"] = (
        merged["comment_mode"] if merged["comment_mode"] in {"any", "prefix", "command"} else "any"
    )
    merged["rate"] = _bounded(merged["rate"], -50, 100, 0)
    merged["volume"] = _bounded(merged["volume"], -100, 100, 0)
    merged["pitch"] = _bounded(merged["pitch"], -100, 100, 0)
    merged["max_length"] = _bounded(merged["max_length"], 20, 500, 180)
    merged["max_queue"] = _bounded(merged["max_queue"], 1, 100, 20)
    for key in (
        "enabled", "allow_non_followers", "allow_followers",
        "allow_fan_club", "allow_subscribers",
    ):
        merged[key] = bool(merged[key])
    for key in (
        "voice", "template", "prefix", "command", "allowed_users",
        "blocked_users", "blocked_words",
    ):
        merged[key] = str(merged[key] or defaults[key]).strip()
    return ChatTTSConfig(**merged)


def load_config() -> ChatTTSConfig:
    raw = get_setting(SETTING_KEY)
    try:
        return normalize_config(json.loads(raw) if raw else None)
    except (json.JSONDecodeError, TypeError):
        return ChatTTSConfig()


def save_config(value: dict) -> ChatTTSConfig:
    config = normalize_config(value)
    set_setting(SETTING_KEY, json.dumps(asdict(config), ensure_ascii=False))
    return config


def _items(value: str) -> set[str]:
    return {
        item.strip().lstrip("@").casefold()
        for item in re.split(r"[,\n]", value or "")
        if item.strip()
    }


class ChatTTSService:
    def __init__(self) -> None:
        self.jobs: queue.Queue[dict] = queue.Queue()
        self.lock = threading.RLock()
        self.current: dict | None = None
        self.skipped = 0
        self.dropped = 0
        threading.Thread(target=self._worker, daemon=True, name="chat-tts").start()

    def submit(self, nickname: str, username: str, comment: str, metadata: dict) -> bool:
        config = load_config()
        if not config.enabled:
            return False

        username_key = (username or nickname).strip().lstrip("@").casefold()
        allowed = _items(config.allowed_users)
        blocked = _items(config.blocked_users)
        if username_key in blocked or (allowed and username_key not in allowed):
            return False

        viewer_type = str(metadata.get("viewer_type", "non_follower"))
        access = {
            "non_follower": config.allow_non_followers,
            "follower": config.allow_followers,
            "fan_club": config.allow_fan_club,
            "subscriber": config.allow_subscribers,
        }
        if not access.get(viewer_type, config.allow_non_followers):
            return False

        spoken_comment = (comment or "").strip()
        if config.comment_mode == "prefix":
            if not spoken_comment.startswith(config.prefix):
                return False
            spoken_comment = spoken_comment[len(config.prefix):].strip()
        elif config.comment_mode == "command":
            command = config.command.strip()
            command_match = spoken_comment.casefold().startswith(command.casefold())
            command_boundary = (
                len(spoken_comment) == len(command)
                or spoken_comment[len(command):len(command) + 1].isspace()
            )
            if not command or not command_match or not command_boundary:
                return False
            spoken_comment = spoken_comment[len(command):].strip()
        if not spoken_comment:
            return False

        lowered = spoken_comment.casefold()
        if any(word in lowered for word in _items(config.blocked_words)):
            return False
        spoken_comment = spoken_comment[: config.max_length]

        with self.lock:
            if self.jobs.qsize() >= config.max_queue:
                self.dropped += 1
                return False
            self.jobs.put({
                "nickname": nickname or username,
                "username": username or nickname,
                "comment": spoken_comment,
                "config": config,
            })
        return True

    def _worker(self) -> None:
        while True:
            job = self.jobs.get()
            with self.lock:
                self.current = job
            config: ChatTTSConfig = job["config"]
            try:
                text = config.template.format_map({
                    "nickname": job["nickname"],
                    "username": job["username"],
                    "comment": job["comment"],
                }).strip()
            except (KeyError, ValueError):
                text = f'{job["nickname"]} berkata, {job["comment"]}'
            if text:
                action_executor.speak_text({"text": {
                    "text": text,
                    "voice": config.voice,
                    "rate": f'{config.rate:+d}%',
                    "volume": f'{config.volume:+d}%',
                    "pitch": f'{config.pitch:+d}Hz',
                }})
            with self.lock:
                self.current = None
            self.jobs.task_done()

    def clear(self, skip_current: bool = False) -> int:
        cleared = 0
        while True:
            try:
                self.jobs.get_nowait()
                self.jobs.task_done()
                cleared += 1
            except queue.Empty:
                break
        if skip_current:
            self.skip()
        return cleared

    def skip(self) -> bool:
        with self.lock:
            active = self.current is not None
            if active:
                self.skipped += 1
        if active:
            action_executor.stop_audio()
        return active

    def status(self) -> dict:
        with self.lock:
            current = None if self.current is None else {
                "nickname": self.current["nickname"],
                "comment": self.current["comment"],
            }
            return {
                "pending": self.jobs.qsize(),
                "current": current,
                "skipped": self.skipped,
                "dropped": self.dropped,
            }


chat_tts_service = ChatTTSService()
