"""Keyboard parsing: aliases, combos and literal text sequences."""

from __future__ import annotations

import re

from .errors import OacuError

MOD_VK = {"win": 0x5B, "ctrl": 0x11, "alt": 0x12, "shift": 0x10}
MOD_ORDER = ("win", "ctrl", "alt", "shift")

VK = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "RETURN": 0x0D,
    "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12, "PAUSE": 0x13,
    "CAPSLOCK": 0x14, "ESC": 0x1B, "ESCAPE": 0x1B, "SPACE": 0x20,
    "PAGEUP": 0x21, "PGUP": 0x21, "PAGEDOWN": 0x22, "PGDN": 0x22,
    "END": 0x23, "HOME": 0x24, "LEFT": 0x25, "UP": 0x26,
    "RIGHT": 0x27, "DOWN": 0x28, "INSERT": 0x2D, "INS": 0x2D,
    "DELETE": 0x2E, "DEL": 0x2E,
    "WIN": 0x5B, "LWIN": 0x5B, "RWIN": 0x5C, "WINDOWS": 0x5B,
    "NUMLOCK": 0x90, "SCROLLLOCK": 0x91,
}

# VK for US punctuation (unshifted / shifted)
PUNCT = {
    ";": (0xBA, False), ":": (0xBA, True),
    "=": (0xBB, False), "+": (0xBB, True),
    ",": (0xBC, False), "<": (0xBC, True),
    "-": (0xBD, False), "_": (0xBD, True),
    ".": (0xBE, False), ">": (0xBE, True),
    "/": (0xBF, False), "?": (0xBF, True),
    "`": (0xC0, False), "~": (0xC0, True),
    "[": (0xDB, False), "{": (0xDB, True),
    "\\": (0xDC, False), "|": (0xDC, True),
    "]": (0xDD, False), "}": (0xDD, True),
    "'": (0xDE, False), '"': (0xDE, True),
    "!": (0x31, True), "@": (0x32, True), "#": (0x33, True),
    "$": (0x34, True), "%": (0x35, True), "^": (0x36, True),
    "&": (0x37, True), "*": (0x38, True), "(": (0x39, True),
    ")": (0x30, True),
}

KEY_ALIASES = {
    "win": "WIN", "windows": "WIN", "super": "WIN", "meta": "WIN", "cmd": "WIN",
    "徽标键": "WIN", "win键": "WIN", "windows徽标键": "WIN", "开始键": "WIN",
    "ctrl": "CTRL", "control": "CTRL", "alt": "ALT", "menu": "ALT", "shift": "SHIFT",
    "enter": "ENTER", "return": "ENTER", "回车": "ENTER",
    "esc": "ESC", "escape": "ESC", "退出": "ESC",
    "tab": "TAB", "制表": "TAB",
    "space": "SPACE", "spacebar": "SPACE", "空格": "SPACE",
    "backspace": "BACKSPACE", "back": "BACKSPACE", "退格": "BACKSPACE",
    "delete": "DELETE", "del": "DELETE", "删除": "DELETE",
    "insert": "INSERT", "ins": "INSERT",
    "home": "HOME", "end": "END",
    "pageup": "PAGEUP", "pgup": "PAGEUP",
    "pagedown": "PAGEDOWN", "pgdn": "PAGEDOWN",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
    "上": "UP", "下": "DOWN", "左": "LEFT", "右": "RIGHT",
}

# winr / WinR / wine / wind ... shortcuts
WIN_COMBOS = {
    "winr": "win+r", "wine": "win+e", "wind": "win+d", "winl": "win+l",
    "wini": "win+i", "wins": "win+s", "wina": "win+a", "winx": "win+x",
    "wint": "win+t", "winv": "win+v", "winp": "win+p", "wink": "win+k",
}

SINGLE_KEYS = {
    "win", "ctrl", "alt", "shift", "enter", "esc", "tab", "space",
    "backspace", "delete", "insert", "home", "end", "pageup", "pagedown",
    "up", "down", "left", "right",
}


class KeyParseError(OacuError):
    pass


def canonical_keys(keys: str) -> str:
    value = (keys or "").strip().lower()
    if not value:
        return ""
    value = value.replace(" ", "")
    for phrase in ("windows徽标键", "徽标键", "win键", "开始键"):
        value = value.replace(phrase, "win")
    for phrase in ("回车", "退格", "删除", "制表", "空格", "退出",
                   "上", "下", "左", "右"):
        if phrase in value and len(value) == len(phrase):
            value = value.replace(phrase, KEY_ALIASES.get(phrase, phrase).lower())
    if value in WIN_COMBOS:
        return WIN_COMBOS[value]
    value = {
        "windows": "win", "control": "ctrl", "escape": "esc", "return": "enter",
        "spacebar": "space", "del": "delete", "ins": "insert",
        "pgup": "pageup", "pgdn": "pagedown",
    }.get(value, value)
    if re.fullmatch(r"[a-z0-9](,[a-z0-9])+", value):
        return value.replace(",", "")
    return value


def _vk_for(name: str) -> int | None:
    value = (name or "").strip()
    if not value:
        return None
    upper = value.upper()
    if upper in VK:
        return VK[upper]
    if value in KEY_ALIASES:
        return _vk_for(KEY_ALIASES[value])
    if value in PUNCT:
        return PUNCT[value][0]
    if len(value) == 1:
        char = value.upper()
        if "A" <= char <= "Z" or "0" <= char <= "9":
            return ord(char)
    match = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", value.lower())
    if match:
        return 0x70 + int(match.group(1)) - 1
    return None


def _mod_for(name: str) -> str | None:
    value = (name or "").strip().lower()
    if value in ("win", "windows", "super", "meta", "cmd", "徽标键", "win键", "开始键"):
        return "win"
    if value in ("ctrl", "control"):
        return "ctrl"
    if value in ("alt", "menu"):
        return "alt"
    if value in ("shift",):
        return "shift"
    return None


def _literal_events(text: str) -> list[tuple[int, frozenset[str]]]:
    events: list[tuple[int, frozenset[str]]] = []
    for char in text:
        if char in ("\n", "\r"):
            events.append((VK["ENTER"], frozenset()))
            continue
        if char == " ":
            events.append((VK["SPACE"], frozenset()))
            continue
        upper = char.upper()
        if "A" <= upper <= "Z":
            mods = frozenset({"shift"}) if char.isupper() else frozenset()
            events.append((ord(upper), mods))
            continue
        if "0" <= char <= "9":
            events.append((ord(char), frozenset()))
            continue
        if char in PUNCT:
            vk, shifted = PUNCT[char]
            events.append((vk, frozenset({"shift"}) if shifted else frozenset()))
            continue
        raise KeyParseError(f"无法作为按键处理: {char!r}；文本请用 type_text")
    return events


def _parse_legacy(text: str) -> list[tuple[int, frozenset[str]]]:
    events: list[tuple[int, frozenset[str]]] = []
    mods: set[str] = set()
    index = 0
    while index < len(text):
        char = text[index]
        if char == "^":
            mods.add("ctrl")
            index += 1
            continue
        if char == "%":
            mods.add("alt")
            index += 1
            continue
        if char == "+":
            mods.add("shift")
            index += 1
            continue
        if char == "{":
            end = text.find("}", index)
            if end < 0:
                raise KeyParseError("按键缺少右花括号")
            vk = _vk_for(text[index + 1:end])
            if vk is None:
                raise KeyParseError(f"未知按键: {text[index + 1:end]}")
            events.append((vk, frozenset(mods)))
            mods = set()
            index = end + 1
            continue
        vk = _vk_for(char)
        if vk is None:
            raise KeyParseError(f"未知按键: {char!r}")
        current = set(mods)
        if char.isupper():
            current.add("shift")
        events.append((vk, frozenset(current)))
        mods = set()
        index += 1
    return events


def parse_keys(keys: str) -> list[tuple[int, frozenset[str]]]:
    """Parse 'win+r', 'WinR', 'ctrl+shift+esc', '^s', '{F5}', 'enter' or 'chrome'."""
    text = (keys or "").strip()
    if not text:
        raise KeyParseError("按键不能为空")
    if any(char in text for char in "^%{}") or text.startswith("+"):
        return _parse_legacy(text)

    value = canonical_keys(text)
    if not value:
        raise KeyParseError("按键不能为空")

    if "+" in value:
        parts = [part for part in value.split("+") if part]
        if len(parts) < 2:
            raise KeyParseError(f"组合键格式不正确: {keys}")
        mods: set[str] = set()
        for part in parts[:-1]:
            modifier = _mod_for(part)
            if modifier is None:
                raise KeyParseError(f"不是修饰键: {part}")
            mods.add(modifier)
        vk = _vk_for(parts[-1])
        if vk is None:
            raise KeyParseError(f"未知按键: {parts[-1]}")
        return [(vk, frozenset(mods))]

    vk = _vk_for(value)
    if vk is not None and (len(value) > 1 or value.isdigit()):
        return [(vk, frozenset())]
    if len(value) == 1:
        vk = _vk_for(value)
        if vk is None:
            raise KeyParseError(f"未知按键: {value}")
        return [(vk, frozenset({"shift"}) if value.isupper() else frozenset())]
    if all(0x20 <= ord(char) <= 0x7E for char in value):
        return _literal_events(value)
    raise KeyParseError(f"未知按键: {keys}")
