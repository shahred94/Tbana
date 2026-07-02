"""Windows keyboard input helpers for game compatibility mode."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time


KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1
MAPVK_VK_TO_VSC = 0

VIRTUAL_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
}

EXTENDED_KEYS = {
    "pageup",
    "pagedown",
    "end",
    "home",
    "left",
    "up",
    "right",
    "down",
    "insert",
    "delete",
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


def virtual_key_for(key: str) -> int:
    """Resolve a PyAutoGUI-style key name to a Windows virtual key."""

    normalized = str(key).lower().strip()

    if normalized in VIRTUAL_KEYS:
        return VIRTUAL_KEYS[normalized]

    if (
        normalized.startswith("f")
        and normalized[1:].isdigit()
        and 1 <= int(normalized[1:]) <= 24
    ):
        return 0x70 + int(normalized[1:]) - 1

    if len(normalized) == 1:
        result = ctypes.windll.user32.VkKeyScanW(ord(normalized))
        if result == -1:
            raise ValueError(f"Unsupported keyboard key: {key}")
        return result & 0xFF

    raise ValueError(f"Unsupported keyboard key: {key}")


def _keyboard_input(key: str, key_up: bool = False) -> INPUT:
    virtual_key = virtual_key_for(key)
    scan_code = ctypes.windll.user32.MapVirtualKeyW(
        virtual_key,
        MAPVK_VK_TO_VSC,
    )

    if not scan_code:
        raise OSError(f"Windows scan code unavailable for key: {key}")

    flags = KEYEVENTF_SCANCODE
    if str(key).lower().strip() in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP

    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )


def _send(key: str, key_up: bool = False) -> None:
    keyboard_input = _keyboard_input(key, key_up=key_up)
    sent = ctypes.windll.user32.SendInput(
        1,
        ctypes.byref(keyboard_input),
        ctypes.sizeof(INPUT),
    )
    if sent != 1:
        raise ctypes.WinError()


def send_key_combo(
    keys: list[str],
    hold_seconds: float = 0.1,
) -> None:
    """Send a key combination using Windows scan-code input."""

    if os.name != "nt":
        raise OSError("Windows SendInput is only available on Windows.")

    normalized = [
        str(key).lower().strip()
        for key in keys
        if str(key).strip()
    ]
    if not normalized:
        raise ValueError("Keyboard combination is empty.")

    pressed: list[str] = []
    try:
        for key in normalized:
            _send(key)
            pressed.append(key)

        time.sleep(max(0.0, float(hold_seconds)))
    finally:
        for key in reversed(pressed):
            _send(key, key_up=True)
