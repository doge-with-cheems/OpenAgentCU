"""Virtual mouse/keyboard control.

All actions go through :mod:`oacu.virtual` and never move the system cursor or
inject global keyboard/mouse input.
"""

from __future__ import annotations

from .keys import SINGLE_KEYS, canonical_keys
from .virtual import (
    VirtualInputError,
    click,
    drag,
    key_down,
    key_hold,
    key_press,
    key_up,
    mouse_position,
    move,
    physical_mouse_position,
    screen_info,
    scroll,
    type_text,
    validate_point,
    win_run,
)

InputError = VirtualInputError


def normalize_keys(keys: str) -> str:
    value = canonical_keys(keys)
    if value in SINGLE_KEYS:
        return "{" + value.upper() + "}"
    return value


__all__ = [
    "InputError",
    "VirtualInputError",
    "click",
    "drag",
    "key_down",
    "key_hold",
    "key_press",
    "key_up",
    "mouse_position",
    "move",
    "normalize_keys",
    "physical_mouse_position",
    "screen_info",
    "scroll",
    "type_text",
    "validate_point",
    "win_run",
]
