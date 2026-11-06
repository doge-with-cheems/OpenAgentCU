"""Shared data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Rect = tuple[int, int, int, int]


@dataclass
class RawElement:
    name: str
    control_type: str
    rect: Rect
    automation_id: str = ""
    class_name: str = ""
    parent: int = -1
    depth: int = 0
    enabled: bool = True
    offscreen: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawElement":
        rect = data.get("rect") or [0, 0, 0, 0]
        if isinstance(rect, dict):
            rect = [rect.get("x", 0), rect.get("y", 0), rect.get("w", 0), rect.get("h", 0)]
        values = [int(float(v or 0)) for v in list(rect)[:4]]
        while len(values) < 4:
            values.append(0)
        return cls(
            name=str(data.get("name", "") or ""),
            control_type=str(data.get("control_type", "") or ""),
            rect=(values[0], values[1], values[2], values[3]),
            automation_id=str(data.get("automation_id", "") or ""),
            class_name=str(data.get("class_name", "") or ""),
            parent=int(data.get("parent", -1) if data.get("parent") is not None else -1),
            depth=int(data.get("depth", 0) or 0),
            enabled=bool(data.get("enabled", True)),
            offscreen=bool(data.get("offscreen", False)),
        )


@dataclass
class Element:
    name: str
    control_type: str
    rect: Rect
    automation_id: str = ""
    class_name: str = ""
    parent: int = -1
    depth: int = 0
    enabled: bool = True
    offscreen: bool = False
    window: str = ""
    parent_name: str = ""
    parent_ref: int = -1
    order: int = 0

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.rect
        return x + w // 2, y + h // 2


@dataclass
class Token:
    id: str
    name: str
    ctype: str
    rect: Rect
    relations: dict[str, str] = field(default_factory=dict)
    order: int = 0

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.rect
        return x + w // 2, y + h // 2


@dataclass
class Snapshot:
    snapshot_key: str
    window: list[str]
    screen: tuple[int, int]
    tokens: list[Token]
    text: str
    stats: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class CollectResult:
    elements: list[RawElement]
    meta: dict[str, Any] = field(default_factory=dict)
