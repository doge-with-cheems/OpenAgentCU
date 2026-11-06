"""Tokenize elements as {[name][type][x,y,w,h][relations]}."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .models import Element, Snapshot, Token

MAX_NAME = 40
_WS = re.compile(r"\s+")


def clean_name(name: str, ctype: str) -> str:
    value = (name or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    value = _WS.sub(" ", value).strip()
    value = value.replace("[", "(").replace("]", ")")
    if not value:
        value = (ctype or "unknown").strip() or "unknown"
    if len(value) > MAX_NAME:
        value = value[: MAX_NAME - 1] + "…"
    return value


def clean_type(ctype: str) -> str:
    value = _WS.sub(" ", (ctype or "").strip()).replace("[", "(").replace("]", ")")
    return value or "Unknown"


def build_tokens(elements: list[Element]) -> list[Token]:
    tokens: list[Token] = []
    for index, element in enumerate(elements, start=1):
        order = element.order or index
        tokens.append(
            Token(
                id=f"t{index:04d}",
                name=clean_name(element.name, element.control_type),
                ctype=clean_type(element.control_type),
                rect=element.rect,
                relations={
                    "parent": element.parent_name or "",
                    "window": element.window or "",
                    "id": element.automation_id or "",
                    "order": str(order),
                },
                order=order,
            )
        )
    return tokens


def render_text(tokens: list[Token]) -> str:
    lines: list[str] = []
    for token in tokens:
        x, y, w, h = token.rect
        rel = ";".join(f"{key}={value}" for key, value in token.relations.items())
        lines.append(f"{{[{token.name}][{token.ctype}][{x},{y},{w},{h}][{rel}]}}")
    return "\n".join(lines)


def build_snapshot(
    elements: list[Element],
    screen: tuple[int, int] = (0, 0),
    stats: dict[str, Any] | None = None,
) -> Snapshot:
    tokens = build_tokens(elements)
    text = render_text(tokens)
    windows: list[str] = []
    for element in elements:
        if element.window and element.window not in windows:
            windows.append(element.window)
    digest = hashlib.sha1((text + json.dumps(list(screen))).encode("utf-8")).hexdigest()
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    token_stats = dict(stats or {})
    token_stats.update({"tokens": len(tokens), "windows": len(windows)})
    return Snapshot(
        snapshot_key=digest[:16],
        window=windows,
        screen=(int(screen[0]), int(screen[1])),
        tokens=tokens,
        text=text,
        stats=token_stats,
        created_at=created_at,
    )
