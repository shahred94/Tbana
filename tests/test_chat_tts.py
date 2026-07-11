"""Tests for automatic TikTok chat TTS filtering."""

import queue
import threading

from app.tts import chat


def bare_service():
    service = chat.ChatTTSService.__new__(chat.ChatTTSService)
    service.jobs = queue.Queue()
    service.lock = threading.RLock()
    service.current = None
    service.skipped = 0
    service.dropped = 0
    return service


def test_normalize_config_bounds_values():
    config = chat.normalize_config({
        "rate": 999,
        "pitch": -999,
        "max_queue": 0,
        "comment_mode": "invalid",
    })
    assert config.rate == 100
    assert config.pitch == -100
    assert config.max_queue == 1
    assert config.comment_mode == "any"


def test_command_mode_removes_command(monkeypatch):
    config = chat.ChatTTSConfig(enabled=True, comment_mode="command", command="!tts")
    monkeypatch.setattr(chat, "load_config", lambda: config)
    service = bare_service()

    assert service.submit("Bana", "bana", "!tts hello semua", {"viewer_type": "follower"})
    assert service.jobs.get_nowait()["comment"] == "hello semua"
    assert not service.submit("Bana", "bana", "!ttshello", {"viewer_type": "follower"})


def test_viewer_and_word_filters(monkeypatch):
    config = chat.ChatTTSConfig(
        enabled=True,
        allow_non_followers=False,
        blocked_words="kasar, spam",
    )
    monkeypatch.setattr(chat, "load_config", lambda: config)
    service = bare_service()

    assert not service.submit("A", "a", "hello", {"viewer_type": "non_follower"})
    assert not service.submit("B", "b", "ini spam", {"viewer_type": "follower"})
    assert service.jobs.empty()


def test_queue_limit_drops_new_message(monkeypatch):
    config = chat.ChatTTSConfig(enabled=True, max_queue=1)
    monkeypatch.setattr(chat, "load_config", lambda: config)
    service = bare_service()

    assert service.submit("A", "a", "first", {"viewer_type": "follower"})
    assert not service.submit("B", "b", "second", {"viewer_type": "follower"})
    assert service.dropped == 1
