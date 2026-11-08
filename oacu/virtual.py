"""Virtual pointer: overlay + targeted UIA/window-message input.

This module never moves the physical cursor and never uses SendInput /
mouse_event / keybd_event. Clicks and keys are delivered as UIA patterns or
targeted window messages, so the user's keyboard and mouse stay untouched.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import subprocess

from .errors import OacuError
from .keys import MOD_ORDER, MOD_VK, KeyParseError, canonical_keys, parse_keys

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

VIRTUAL_CURSOR = "▣"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

BUTTONS = {
    "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON),
    "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
    "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON),
}


class VirtualInputError(OacuError):
    pass


def _user32():
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD,
                                        ctypes.POINTER(GUITHREADINFO)]
    return user32


def _point(x: int, y: int) -> wintypes.POINT:
    return wintypes.POINT(int(x), int(y))


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
        raise VirtualInputError("坐标必须是整数") from exc
    info = screen_info()
    if not (info["x"] <= x < info["x"] + info["width"]
            and info["y"] <= y < info["y"] + info["height"]):
        raise VirtualInputError(
            f"坐标超出屏幕范围: {x},{y} (虚拟屏幕 {info['x']},{info['y']} "
            f"{info['width']}x{info['height']})")
    return x, y


def physical_mouse_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32().GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _window_at(x: int, y: int) -> int:
    handle = _user32().WindowFromPoint(_point(x, y))
    return int(handle or 0)


def _client_point(handle: int, x: int, y: int) -> tuple[int, int]:
    point = _point(x, y)
    _user32().ScreenToClient(handle, ctypes.byref(point))
    return int(point.x), int(point.y)


def _lparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


def _post(handle: int, message: int, wparam: int = 0, lparam: int = 0) -> bool:
    return bool(_user32().PostMessageW(handle, message, wparam, lparam))


def _parse_sequence(keys: str) -> list[tuple[int, frozenset[str]]]:
    try:
        return parse_keys(canonical_keys(keys))
    except KeyParseError as exc:
        raise VirtualInputError(str(exc)) from exc


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def _focus_at(x: int, y: int) -> dict[str, object]:
    try:
        from .interpreter import _run_uia_act

        return _run_uia_act({"op": "focus_point", "point": [int(x), int(y)]})
    except Exception:  # noqa: BLE001 - focus is optional
        return {"ok": False}


def _focus_window() -> int:
    user32 = _user32()
    foreground = int(user32.GetForegroundWindow() or 0)
    if not foreground:
        return 0
    pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if thread_id and user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return int(info.hwndFocus or info.hwndActive or foreground)
    return foreground


class _Overlay:
    """Click-through ▣ overlay, hosted in a separate main-thread Tk process."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._failed = False
        self._lock = threading.Lock()

    @property
    def disabled(self) -> bool:
        if os.environ.get("OACU_NO_OVERLAY"):
            return True
        return "oacu.gui" in sys.modules

    def _start(self) -> None:
        if getattr(sys, "frozen", False):
            command = [sys.executable, "overlay"]
            cwd = None
        else:
            command = [sys.executable, "-m", "oacu", "overlay"]
            cwd = str(Path(__file__).resolve().parents[1])
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def show(self, x: int, y: int, hold_ms: int = 900) -> None:
        if self.disabled:
            return
        with self._lock:
            if self._failed:
                return
            payload = json.dumps({"x": int(x), "y": int(y), "ms": int(hold_ms)}) + "\n"
            for _attempt in range(2):
                try:
                    if self._proc is None or self._proc.poll() is not None:
                        self._start()
                    assert self._proc is not None and self._proc.stdin is not None
                    self._proc.stdin.write(payload)
                    self._proc.stdin.flush()
                    return
                except (OSError, ValueError, AssertionError):
                    self._proc = None
            self._failed = True


def _state_path():
    from .config import home_dir

    return home_dir() / "pointer.json"


def _load_state() -> dict[str, int]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("x", "y", "hwnd"):
        value = data.get(key)
        if isinstance(value, int):
            result[key] = value
    return result


def _is_window(handle: int) -> bool:
    if not handle:
        return False
    user32 = _user32()
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    return bool(user32.IsWindow(handle))


class VirtualPointer:
    def __init__(self) -> None:
        self.x, self.y = physical_mouse_position()
        self.last_hwnd = 0
        self.last_point: tuple[int, int] | None = None
        saved = _load_state()
        if saved:
            info = screen_info()
            x = saved.get("x", self.x)
            y = saved.get("y", self.y)
            if (info["x"] <= x < info["x"] + info["width"]
                    and info["y"] <= y < info["y"] + info["height"]):
                self.x, self.y = x, y
            if _is_window(saved.get("hwnd", 0)):
                self.last_hwnd = saved["hwnd"]
        self.last_point = (self.x, self.y)
        self.overlay = _Overlay()

    def _save(self) -> None:
        try:
            _state_path().write_text(
                json.dumps({"x": self.x, "y": self.y, "hwnd": self.last_hwnd}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def position(self) -> tuple[int, int]:
        return self.x, self.y

    def show(self, hold_ms: int = 900) -> None:
        self.overlay.show(self.x, self.y, hold_ms)

    def move(self, x: int, y: int, duration_ms: int = 0) -> tuple[int, int]:
        x, y = validate_point(x, y)
        if duration_ms <= 0:
            self.x, self.y = x, y
        else:
            start_x, start_y = self.x, self.y
            steps = max(1, min(120, int(duration_ms) // 12))
            delay = max(0.001, (int(duration_ms) / 1000.0) / steps)
            for index in range(1, steps + 1):
                ratio = index / steps
                self.x = round(start_x + (x - start_x) * ratio)
                self.y = round(start_y + (y - start_y) * ratio)
                time.sleep(delay)
        self.last_point = (self.x, self.y)
        self.show()
        self._save()
        return self.x, self.y

    def click(self, x: int | None = None, y: int | None = None,
              button: str = "left", clicks: int = 1,
              interval_ms: int = 80) -> dict[str, object]:
        if (x is None) != (y is None):
            raise VirtualInputError("x 和 y 必须同时提供")
        if x is not None and y is not None:
            self.move(x, y)
        key = (button or "left").lower()
        if key not in BUTTONS:
            raise VirtualInputError(f"不支持的鼠标键: {button}")
        self.last_point = (self.x, self.y)
        focus = _focus_at(self.x, self.y)
        focus_handle = int(focus.get("hwnd") or 0)
        if focus_handle:
            self.last_hwnd = focus_handle
        if focus.get("invoked"):
            self.show()
            self._save()
            return {"x": self.x, "y": self.y, "button": key, "clicks": max(1, int(clicks)),
                    "mode": "uia_pattern", "method": focus.get("method")}
        handle = focus_handle or _window_at(self.x, self.y)
        if not handle:
            raise VirtualInputError(f"坐标 {self.x},{self.y} 没有窗口")
        self.last_hwnd = handle
        cx, cy = _client_point(handle, self.x, self.y)
        down, up, flag = BUTTONS[key]
        count = max(1, int(clicks))
        for index in range(count):
            _post(handle, down, flag, _lparam(cx, cy))
            _post(handle, up, 0, _lparam(cx, cy))
            if index + 1 < count:
                time.sleep(max(0, int(interval_ms)) / 1000.0)
        self.show()
        self._save()
        return {"x": self.x, "y": self.y, "button": key, "clicks": count,
                "mode": "virtual", "hwnd": handle}

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
             button: str = "left", duration_ms: int = 500) -> dict[str, object]:
        from_x, from_y = validate_point(from_x, from_y)
        to_x, to_y = validate_point(to_x, to_y)
        key = (button or "left").lower()
        if key not in BUTTONS:
            raise VirtualInputError(f"不支持的鼠标键: {button}")
        focus = _focus_at(from_x, from_y)
        handle = int(focus.get("hwnd") or 0) or _window_at(from_x, from_y)
        if not handle:
            raise VirtualInputError(f"坐标 {from_x},{from_y} 没有窗口")
        self.last_hwnd = handle
        down, up, flag = BUTTONS[key]
        sx, sy = _client_point(handle, from_x, from_y)
        _post(handle, down, flag, _lparam(sx, sy))
        try:
            steps = max(1, min(120, int(duration_ms) // 12))
            delay = max(0.001, (int(duration_ms) / 1000.0) / steps)
            for index in range(1, steps + 1):
                ratio = index / steps
                x = round(from_x + (to_x - from_x) * ratio)
                y = round(from_y + (to_y - from_y) * ratio)
                cx, cy = _client_point(handle, x, y)
                _post(handle, WM_MOUSEMOVE, flag, _lparam(cx, cy))
                self.x, self.y = x, y
                time.sleep(delay)
        finally:
            ex, ey = _client_point(handle, to_x, to_y)
            _post(handle, up, 0, _lparam(ex, ey))
            self.x, self.y = to_x, to_y
        self.last_point = (self.x, self.y)
        self.show()
        self._save()
        return {"from": [from_x, from_y], "to": [to_x, to_y],
                "button": key, "mode": "virtual", "hwnd": handle}

    def scroll(self, x: int | None = None, y: int | None = None,
               dy: int = 3, dx: int = 0) -> dict[str, object]:
        if (x is None) != (y is None):
            raise VirtualInputError("x 和 y 必须同时提供")
        if x is not None and y is not None:
            self.move(x, y)
        dy = int(dy)
        dx = int(dx)
        if dy == 0 and dx == 0:
            raise VirtualInputError("dy 和 dx 不能同时为 0")
        handle = _window_at(self.x, self.y)
        if not handle:
            raise VirtualInputError(f"坐标 {self.x},{self.y} 没有窗口")
        screen_point = _lparam(self.x, self.y)
        if dy:
            _post(handle, WM_MOUSEWHEEL, (dy * 120 & 0xFFFF) << 16, screen_point)
        if dx:
            _post(handle, WM_MOUSEHWHEEL, (dx * 120 & 0xFFFF) << 16, screen_point)
        self.show()
        return {"x": self.x, "y": self.y, "dy": dy, "dx": dx, "mode": "virtual"}

    def _focused_handle(self) -> int:
        handle = _focus_window()
        if not handle:
            raise VirtualInputError("没有可接收按键的前台窗口")
        return handle

    def key_press(self, keys: str) -> dict[str, object]:
        sequence = _parse_sequence(keys)
        if not sequence:
            raise VirtualInputError(f"无法识别按键: {keys}")
        self._reject_system_combo(sequence)
        handle = self.last_hwnd or self._focused_handle()
        for vk, mods in sequence:
            for name in MOD_ORDER:
                if name in mods:
                    _post(handle, WM_KEYDOWN, MOD_VK[name], 1)
            _post(handle, WM_KEYDOWN, vk, 1)
            _post(handle, WM_KEYUP, vk, 0xC0000001)
            for name in reversed(MOD_ORDER):
                if name in mods:
                    _post(handle, WM_KEYUP, MOD_VK[name], 0xC0000001)
        self.show()
        return {"keys": keys, "mode": "virtual_press", "hwnd": handle}

    def key_down(self, keys: str) -> dict[str, object]:
        sequence = _parse_sequence(keys)
        if not sequence:
            raise VirtualInputError(f"无法识别按键: {keys}")
        self._reject_system_combo(sequence)
        handle = self.last_hwnd or self._focused_handle()
        _emit_virtual(handle, sequence, down=True)
        self.show()
        return {"keys": keys, "mode": "virtual_down", "hwnd": handle}

    def key_up(self, keys: str) -> dict[str, object]:
        sequence = _parse_sequence(keys)
        if not sequence:
            raise VirtualInputError(f"无法识别按键: {keys}")
        handle = self.last_hwnd or self._focused_handle()
        _emit_virtual(handle, sequence, down=False)
        self.show()
        return {"keys": keys, "mode": "virtual_up", "hwnd": handle}

    def key_hold(self, keys: str, ms: int = 500) -> dict[str, object]:
        sequence = _parse_sequence(keys)
        if not sequence:
            raise VirtualInputError(f"无法识别按键: {keys}")
        self._reject_system_combo(sequence)
        handle = self.last_hwnd or self._focused_handle()
        _emit_virtual(handle, sequence, down=True)
        self.show(hold_ms=max(900, int(ms)))
        try:
            time.sleep(max(0, int(ms)) / 1000.0)
        finally:
            _emit_virtual(handle, sequence, down=False)
        return {"keys": keys, "mode": "virtual_hold", "ms": max(0, int(ms)),
                "hwnd": handle}

    @staticmethod
    def _reject_system_combo(sequence: list[tuple[int, frozenset[str]]]) -> None:
        for vk, mods in sequence:
            if "win" in mods or vk in (0x5B, 0x5C):
                raise VirtualInputError(
                    "虚拟模式不支持 Win 系统快捷键；请用 launch_app / open_url / search_web / win_run")
            if "alt" in mods and vk in (0x09, 0x73):
                raise VirtualInputError(
                    "虚拟模式不支持 Alt+Tab / Alt+F4；请用窗口操作或 launch_app")
            if {"ctrl", "shift"} <= set(mods) and vk == 0x1B:
                raise VirtualInputError(
                    "虚拟模式不支持 Ctrl+Shift+Esc（安全界面）；请用 launch_app")

    def type_text(self, text: str) -> dict[str, object]:
        text = str(text)
        if text == "":
            raise VirtualInputError("输入文本不能为空")
        handle = 0
        try:
            from .interpreter import _run_uia_act

            if self.last_point:
                response = _run_uia_act({
                    "op": "set_value_point",
                    "point": [self.last_point[0], self.last_point[1]],
                    "value": text,
                })
                if response.get("ok"):
                    self.show()
                    return {"text": text, "chars": len(text), "mode": "point_value"}
                handle = int(response.get("hwnd") or 0)
            response = _run_uia_act({"op": "focused_set_value", "value": text})
            if response.get("ok"):
                self.show()
                return {"text": text, "chars": len(text), "mode": "uia_value"}
            handle = self.last_hwnd or handle or int(response.get("hwnd") or 0)
        except Exception:  # noqa: BLE001 - fall through to targeted WM_CHAR
            pass
        handle = handle or self.last_hwnd or self._focused_handle()
        for char in text:
            if char in ("\n", "\r"):
                unit = 0x0D
            else:
                chunk = char.encode("utf-16-le")
                for offset in range(0, len(chunk), 2):
                    unit = chunk[offset] | (chunk[offset + 1] << 8)
                    _post(handle, WM_CHAR, unit, 1)
                continue
            _post(handle, WM_CHAR, unit, 1)
        self.show()
        return {"text": text, "chars": len(text), "mode": "wm_char", "hwnd": handle}


def _emit_virtual(handle: int, sequence: list[tuple[int, frozenset[str]]],
                  *, down: bool) -> None:
    if down:
        for vk, mods in sequence:
            for name in MOD_ORDER:
                if name in mods:
                    _post(handle, WM_KEYDOWN, MOD_VK[name], 1)
            _post(handle, WM_KEYDOWN, vk, 1)
    else:
        for vk, mods in reversed(sequence):
            _post(handle, WM_KEYUP, vk, 0xC0000001)
            for name in reversed(MOD_ORDER):
                if name in mods:
                    _post(handle, WM_KEYUP, MOD_VK[name], 0xC0000001)


_POINTER: VirtualPointer | None = None


def pointer() -> VirtualPointer:
    global _POINTER
    if _POINTER is None:
        _POINTER = VirtualPointer()
    return _POINTER


def mouse_position() -> tuple[int, int]:
    return pointer().position()


def move(x: int, y: int, duration_ms: int = 0) -> tuple[int, int]:
    return pointer().move(x, y, duration_ms)


def click(x: int | None = None, y: int | None = None, button: str = "left",
          clicks: int = 1, interval_ms: int = 80) -> dict[str, object]:
    return pointer().click(x, y, button, clicks, interval_ms)


def drag(from_x: int, from_y: int, to_x: int, to_y: int,
         button: str = "left", duration_ms: int = 500) -> dict[str, object]:
    return pointer().drag(from_x, from_y, to_x, to_y, button, duration_ms)


def scroll(x: int | None = None, y: int | None = None,
           dy: int = 3, dx: int = 0) -> dict[str, object]:
    return pointer().scroll(x, y, dy, dx)


def key_press(keys: str) -> dict[str, object]:
    return pointer().key_press(keys)


def key_down(keys: str) -> dict[str, object]:
    return pointer().key_down(keys)


def key_up(keys: str) -> dict[str, object]:
    return pointer().key_up(keys)


def key_hold(keys: str, ms: int = 500) -> dict[str, object]:
    return pointer().key_hold(keys, ms)


def type_text(text: str) -> dict[str, object]:
    return pointer().type_text(text)


def launch_app(app: str) -> str:
    from .interpreter import launch_app as launch

    return launch(app)


def open_url(url: str) -> str:
    from .interpreter import open_url as open_link

    return open_link(url)


def win_run(command: str, wait_ms: int = 350) -> dict[str, object]:
    """Virtual Win+R replacement: launch an app/path/URL via ShellExecute."""
    text = (command or "").strip()
    if not text:
        raise VirtualInputError("Win+R 命令不能为空")
    lower = text.lower()
    if lower.startswith(("http://", "https://")):
        open_url(text)
        return {"command": text, "mode": "virtual_open_url"}
    if os.path.exists(text):
        os.startfile(text)  # type: ignore[attr-defined]
        return {"command": text, "mode": "virtual_open_path"}
    from .interpreter import launch_app as launch

    exe = launch(text)
    return {"command": text, "mode": "virtual_launch", "exe": exe}
