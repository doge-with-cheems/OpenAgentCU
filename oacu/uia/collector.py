"""Desktop capture entry point (backend agnostic)."""

from __future__ import annotations

from pathlib import Path

from ..models import CollectResult
from . import backend as backend_mod


def capture(
    backend: str = "auto",
    max_depth: int = 12,
    max_elements: int = 3000,
    window: str | None = None,
    fixture: str | Path | None = None,
) -> CollectResult:
    return backend_mod.collect(
        backend=backend,
        max_depth=max_depth,
        max_elements=max_elements,
        window=window,
        fixture=fixture,
    )
