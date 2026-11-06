"""Normalize the raw UIA tree into a stable element group."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Element, RawElement


@dataclass
class NormalizeStats:
    raw: int = 0
    kept: int = 0
    dropped: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.dropped += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "kept": self.kept,
            "dropped": self.dropped,
            "reasons": dict(self.reasons),
        }


def _parent_of(raws: list[RawElement], index: int) -> int:
    parent = raws[index].parent
    if parent < 0 or parent >= len(raws) or parent == index:
        return -1
    return parent


def _ancestors(raws: list[RawElement], index: int) -> list[int]:
    chain: list[int] = []
    seen: set[int] = set()
    current = _parent_of(raws, index)
    while current >= 0 and current not in seen:
        seen.add(current)
        chain.append(current)
        current = _parent_of(raws, current)
    return chain


def _window_of(raws: list[RawElement], index: int) -> str:
    chain = _ancestors(raws, index)
    if not chain:
        return raws[index].name if raws[index].control_type.lower() == "window" else ""
    top = chain[-1]
    return raws[top].name or raws[top].control_type


def normalize(raws: list[RawElement], window: str | None = None) -> tuple[list[Element], NormalizeStats]:
    stats = NormalizeStats(raw=len(raws))
    child_count: dict[int, int] = {}
    for idx in range(len(raws)):
        parent = _parent_of(raws, idx)
        if parent >= 0:
            child_count[parent] = child_count.get(parent, 0) + 1

    seen: set[tuple[str, str, tuple[int, int, int, int], str]] = set()
    keep = [False] * len(raws)
    windows = [""] * len(raws)
    filter_text = (window or "").strip().lower()

    for idx, raw in enumerate(raws):
        x, y, w, h = raw.rect
        if x <= -30000 or y <= -30000:
            stats.drop("offscreen")
            continue
        if w <= 1 or h <= 1:
            stats.drop("zero_area")
            continue

        name = (raw.name or "").strip()
        if not name and not raw.automation_id and child_count.get(idx, 0) == 0:
            stats.drop("empty_leaf")
            continue

        key = (name, raw.control_type, raw.rect, raw.automation_id)
        if key in seen:
            stats.drop("duplicate")
            continue
        seen.add(key)

        win = _window_of(raws, idx)
        if filter_text and filter_text not in win.lower():
            stats.drop("window_filter")
            continue

        keep[idx] = True
        windows[idx] = win

    # raw index -> normalized index (parents are emitted before children by construction)
    norm_index = [-1] * len(raws)
    counter = 0
    for idx, kept in enumerate(keep):
        if kept:
            norm_index[idx] = counter
            counter += 1

    elements: list[Element] = []
    for idx, raw in enumerate(raws):
        if not keep[idx]:
            continue
        parent_ref = -1
        for ancestor in _ancestors(raws, idx):
            if norm_index[ancestor] >= 0:
                parent_ref = norm_index[ancestor]
                break
        parent = _parent_of(raws, idx)
        parent_name = ""
        if parent >= 0:
            parent_name = (raws[parent].name or raws[parent].control_type or "").strip()
        elements.append(
            Element(
                name=(raw.name or "").strip(),
                control_type=raw.control_type,
                rect=raw.rect,
                automation_id=raw.automation_id,
                class_name=raw.class_name,
                parent=parent,
                depth=raw.depth,
                enabled=raw.enabled,
                offscreen=raw.offscreen,
                window=windows[idx],
                parent_name=parent_name,
                parent_ref=parent_ref,
            )
        )

    stats.kept = len(elements)
    return elements, stats
