"""Capture -> normalize -> order -> tokenize, in one call."""

from __future__ import annotations

from .models import Snapshot
from .tokens import build_snapshot
from .uia.collector import capture
from .uia.normalize import normalize
from .uia.order import order_elements


def capture_snapshot(
    backend: str = "auto",
    window: str | None = None,
    max_depth: int = 12,
    max_elements: int = 3000,
    fixture: str | None = None,
) -> Snapshot:
    result = capture(
        backend=backend,
        max_depth=max_depth,
        max_elements=max_elements,
        window=window,
        fixture=fixture,
    )
    elements, stats = normalize(result.elements, window=window)
    ordered = order_elements(elements)
    screen = result.meta.get("screen") or (0, 0)
    snapshot = build_snapshot(
        ordered,
        screen=(int(screen[0]), int(screen[1])),
        stats={**stats.to_dict(), "backend": result.meta.get("backend", ""),
               "truncated": result.meta.get("truncated", False)},
    )
    return snapshot
