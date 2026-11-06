"""Linearize elements in reading order: top-left to bottom-right.

Parent elements are emitted before their children; siblings are sorted by
visual row band and then by x, so a window title always precedes its controls.
"""

from __future__ import annotations

from ..models import Element

BAND_PX = 20


def row_band(element: Element, band: int = BAND_PX) -> int:
    _, cy = element.center
    return int(round(cy / band))


def _sort_siblings(items: list[Element], band: int) -> list[Element]:
    """Reading order for one sibling set: cluster by y, then sort by x."""
    by_y = sorted(items, key=lambda e: (e.center[1], e.center[0], e.name))
    rows: list[list[Element]] = []
    current: list[Element] = []
    row_start = 0
    for element in by_y:
        cy = element.center[1]
        if not current:
            current = [element]
            row_start = cy
            continue
        if cy - row_start <= band:
            current.append(element)
        else:
            rows.append(current)
            current = [element]
            row_start = cy
    if current:
        rows.append(current)
    for row in rows:
        row.sort(key=lambda e: (e.center[0], e.center[1], e.name))
    ordered: list[Element] = []
    for row in rows:
        ordered.extend(row)
    return ordered


def order_elements(elements: list[Element], band: int = BAND_PX) -> list[Element]:
    """Hierarchical linearization; windows keep first-appearance (z-order) order."""
    groups: dict[str, list[Element]] = {}
    order_keys: list[str] = []
    for element in elements:
        key = element.window or ""
        if key not in groups:
            groups[key] = []
            order_keys.append(key)
        groups[key].append(element)

    ordered: list[Element] = []
    for key in order_keys:
        group = groups[key]
        group_set = {id(item) for item in group}
        children: dict[int, list[Element]] = {}
        roots: list[Element] = []

        for index_in_group, element in enumerate(group):
            parent: Element | None = None
            ref = element.parent_ref
            if 0 <= ref < len(elements) and id(elements[ref]) in group_set:
                parent = elements[ref]
            if parent is None:
                roots.append(element)
            else:
                children.setdefault(id(parent), []).append(element)

        visited: set[int] = set()

        def emit(element: Element) -> None:
            if id(element) in visited:
                return
            visited.add(id(element))
            ordered.append(element)
            for child in _sort_siblings(children.get(id(element), []), band):
                emit(child)

        for root in _sort_siblings(roots, band):
            emit(root)
        for element in group:  # safety net: cycles or dangling parents
            emit(element)

    for index, element in enumerate(ordered, start=1):
        element.order = index
    return ordered
