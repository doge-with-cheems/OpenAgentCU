"""Compact serialization for MCP tool results."""

from __future__ import annotations

from collections import Counter

from ..models import Token

FIELDS = ["id", "name", "type", "x", "y", "w", "h", "win"]

GENERIC_NAMES = {"", "pane", "group", "custom"}
GENERIC_TYPES = {"pane", "group", "custom"}


def is_noise(token: Token) -> bool:
    return (token.ctype.strip().lower() in GENERIC_TYPES
            and token.name.strip().lower() in GENERIC_NAMES)


def _clean(value: object) -> str:
    return str(value or "").replace("|", "/").replace("\r", " ").replace("\n", " ").strip()


def _window_index(name: str, windows: list[str]) -> int:
    try:
        return windows.index(name)
    except ValueError:
        return -1


def token_table(tokens: list[Token], windows: list[str],
                include_containers: bool = False) -> str:
    lines: list[str] = []
    for token in tokens:
        if not include_containers and is_noise(token):
            continue
        x, y, w, h = token.rect
        lines.append("|".join([
            token.id,
            _clean(token.name),
            _clean(token.ctype),
            str(x), str(y), str(w), str(h),
            str(_window_index(token.relations.get("window", ""), windows)),
        ]))
    return "\n".join(lines)


def removed_table(tokens: list[Token], windows: list[str]) -> str:
    lines: list[str] = []
    for token in tokens:
        x, y, w, h = token.rect
        lines.append("|".join([
            _clean(token.name),
            _clean(token.ctype),
            str(x), str(y), str(w), str(h),
            str(_window_index(token.relations.get("window", ""), windows)),
        ]))
    return "\n".join(lines)


def signature(token: Token) -> tuple[str, str, tuple[int, int, int, int]]:
    return token.name, token.ctype, token.rect


def diff_tokens(old: list[Token], new: list[Token]) -> tuple[list[Token], list[Token]]:
    old_counts = Counter(signature(token) for token in old)
    new_counts = Counter(signature(token) for token in new)

    remaining_added = Counter(new_counts - old_counts)
    added: list[Token] = []
    for token in new:
        key = signature(token)
        if remaining_added[key] > 0:
            added.append(token)
            remaining_added[key] -= 1

    remaining_removed = Counter(old_counts - new_counts)
    removed: list[Token] = []
    for token in old:
        key = signature(token)
        if remaining_removed[key] > 0:
            removed.append(token)
            remaining_removed[key] -= 1
    return added, removed
