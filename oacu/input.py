"""Direct mouse and keyboard control (SendInput / mouse_event)."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .errors import OacuError
from .interpreter import KEYEVENTF_KEYUP, send_keys, send_text
from .keys import MOD_ORDER, MOD_VK, SINGLE_KEYS, canonical_keys, parse_keys

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class InputError(OacuError):
    pass


def normalize_keys(keys: str) -> str:
    value = canonical_keys(keys)
    if value in SINGLE_KEYS:
        return "{" + value.upper() + "}"
    return value


def _user32():
    return ctypes.windll.user32


def screen_info() -> dict[str, int]:
    user32 = _user32()
    return {
        "x": int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        "y": int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        "width": int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
        "height": int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
        "primary_width": int(user32.GetSystemMetrics(0)),
        "primary_height": int(user32.GetSystemMetrics(1)),
    }


def validate_point(x: int, y: int) -> tuple[int, int]:
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError) as exc:
        raise InputError("坐标必须是整数") from exc
    info = screen_info()
    if not (info["x"] <= x < info["x"] + info["width"]
            and info["y"] <= y < info["y"] + info["height"]):
        raise InputError(f"坐标超出屏幕范围: {x},{y} (虚拟屏幕 {info['x']},{info['y']} "
                         f"{info['width']}x{info['height']})")
    return x, y


def mouse_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32().GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _set_position(x: int, y: int) -> None:
    _user32().SetCursorPos(int(x), int(y))


def move(x: int, y: int, duration_ms: int = 0) -> tuple[int, int]:
    x, y = validate_point(x, y)
    if duration_ms <= 0:
        _set_position(x, y)
        return mouse_position()
    start_x, start_y = mouse_position()
    steps = max(1, min(200, int(duration_ms) // 10))
    delay = max(0.001, (int(duration_ms) / 1000.0) / steps)
    for index in range(1, steps + 1):
        ratio = index / steps
        _set_position(round(start_x + (x - start_x) * ratio),
                      round(start_y + (y - start_y) * ratio))
        time.sleep(delay)
    return mouse_position()


def _button_events(button: str) -> tuple[int, int]:
    key = (button or "left").lower()
    if key not in BUTTONS:
        raise InputError(f"不支持的鼠标键: {button}")
    return BUTTONS[key]


def click(x: int | None = None, y: int | None = None, button: str = "left",
          clicks: int = 1, interval_ms: int = 80) -> dict[str, object]:
    if (x is None) != (y is None):
        raise InputError("x 和 y 必须同时提供")
    if x is not None and y is not None:
        move(x, y)
    down, up = _button_events(button)
    count = max(1, int(clicks))
    user32 = _user32()
    for index in range(count):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        if index + 1 < count:
            time.sleep(max(0, int(interval_ms)) / 1000.0)
    px, py = mouse_position()
    return {"x": px, "y": py, "button": button.lower(), "clicks": count}


def drag(from_x: int, from_y: int, to_x: int, to_y: int,
         button: str = "left", duration_ms: int = 500) -> dict[str, object]:
    from_x, from_y = validate_point(from_x, from_y)
    to_x, to_y = validate_point(to_x, to_y)
    down, up = _button_events(button)
    user32 = _user32()
    move(from_x, from_y)
    user32.mouse_event(down, 0, 0, 0, 0)
    try:
        duration_ms = max(1, int(duration_ms))
        steps = max(1, min(200, duration_ms // 10))
        delay = max(0.001, (duration_ms / 1000.0) / steps)
        for index in range(1, steps + 1):
            ratio = index / steps
            _set_position(round(from_x + (to_x - from_x) * ratio),
                          round(from_y + (to_y - from_y) * ratio))
            time.sleep(delay)
    finally:
        user32.mouse_event(up, 0, 0, 0, 0)
    px, py = mouse_position()
    return {"from": [from_x, from_y], "to": [to_x, to_y], "button": button.lower(),
            "cursor": [px, py]}


def scroll(x: int | None = None, y: int | None = None,
           dy: int = 3, dx: int = 0) -> dict[str, object]:
    if (x is None) != (y is None):
        raise InputError("x 和 y 必须同时提供")
    if x is not None and y is not None:
        move(x, y)
    dy = int(dy)
    dx = int(dx)
    if dy == 0 and dx == 0:
        raise InputError("dy 和 dx 不能同时为 0")
    user32 = _user32()
    if dy:
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(dy) * 120, 0)
    if dx:
        user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, int(dx) * 120, 0)
    px, py = mouse_position()
    return {"x": px, "y": py, "dy": dy, "dx": dx}


def key_press(keys: str) -> dict[str, object]:
    if not (keys or "").strip():
        raise InputError("按键不能为空")
    send_keys(normalize_keys(keys))
    return {"keys": keys, "mode": "press"}


def _emit_keys(sequence: list[tuple[int, frozenset[str]]], down: bool) -> None:
    user32 = _user32()
    if down:
        for vk, mods in sequence:
            for name in MOD_ORDER:
                if name in mods:
                    user32.keybd_event(MOD_VK[name], 0, 0, 0)
            user32.keybd_event(vk, 0, 0, 0)
    else:
        for vk, mods in reversed(sequence):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            for name in reversed(MOD_ORDER):
                if name in mods:
                    user32.keybd_event(MOD_VK[name], 0, KEYEVENTF_KEYUP, 0)


def key_down(keys: str) -> dict[str, object]:
    sequence = parse_keys(normalize_keys(keys))
    if not sequence:
        raise InputError(f"无法识别按键: {keys}")
    _emit_keys(sequence, down=True)
    return {"keys": keys, "mode": "down"}


def key_up(keys: str) -> dict[str, object]:
    sequence = parse_keys(normalize_keys(keys))
    if not sequence:
        raise InputError(f"无法识别按键: {keys}")
    _emit_keys(sequence, down=False)
    return {"keys": keys, "mode": "up"}


def win_run(command: str, wait_ms: int = 350) -> dict[str, object]:
    """Open the Windows Run dialog with Win+R, type a command and press Enter."""
    text = (command or "").strip()
    if not text:
        raise InputError("Win+R 命令不能为空")
    key_press("win+r")
    time.sleep(max(100, int(wait_ms)) / 1000.0)
    type_text(text)
    time.sleep(0.12)
    key_press("enter")
    return {"command": text, "mode": "win+r"}


def key_hold(keys: str, ms: int = 500) -> dict[str, object]:
    sequence = parse_keys(normalize_keys(keys))
    if not sequence:
        raise InputError(f"无法识别按键: {keys}")
    _emit_keys(sequence, down=True)
    try:
        time.sleep(max(0, int(ms)) / 1000.0)
    finally:
        _emit_keys(sequence, down=False)
    return {"keys": keys, "mode": "hold", "ms": max(0, int(ms))}


def type_text(text: str) -> dict[str, object]:
    if text is None or text == "":
        raise InputError("输入文本不能为空")
    send_text(str(text))
    return {"text": str(text), "chars": len(str(text))}
