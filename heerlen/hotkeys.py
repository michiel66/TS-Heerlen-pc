"""A selected Windows keyboard/mouse key, read globally using GetAsyncKeyState.

The app does not install a keyboard hook, record typing, or send key presses
to other applications. It only reads the currently selected key's held state.
"""
from __future__ import annotations

import ctypes
import os

PTT_CHOICES = {
    "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78,
    "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "Spatie": 0x20,
    "Rechter Ctrl": 0xA3,
    "Rechter Alt": 0xA5,
    "Muis zijknop 1": 0x05,
    "Muis zijknop 2": 0x06,
}


def is_pressed(choice: str) -> bool:
    code = PTT_CHOICES.get(choice)
    if code is None or os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(code) & 0x8000)
    except (OSError, AttributeError):
        return False
