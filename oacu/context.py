"""Build the per-instruction context: latest snapshot or a fresh capture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .errors import NoSnapshot
from .models import Snapshot, Token
from .store import Store, age_seconds


@dataclass
class Context:
    snapshot_id: int
    created_at: str
    age_s: float
    tokens: list[Token]
    refreshed: bool
    window: str | None
    text: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "age_s": round(self.age_s, 3),
            "tokens": len(self.tokens),
            "refreshed": self.refreshed,
            "window": self.window,
        }


def get_context(
    store: Store,
    window: str | None = None,
    max_age_s: float = 30,
    refresh: Callable[[], Snapshot] | None = None,
) -> Context:
    record = store.latest_snapshot(window)
    refreshed = False

    if record is None or age_seconds(record.created_at) > max_age_s:
        if refresh is None:
            raise NoSnapshot()
        snapshot = refresh()
        snapshot_id = store.save_snapshot(snapshot)
        record = store.get_snapshot(snapshot_id)
        if record is None:
            raise NoSnapshot("快照写入后无法读回")
        tokens = snapshot.tokens
        refreshed = True
    else:
        tokens = store.get_tokens(record.id)

    return Context(
        snapshot_id=record.id,
        created_at=record.created_at,
        age_s=age_seconds(record.created_at),
        tokens=tokens,
        refreshed=refreshed,
        window=window,
        text=record.text,
    )
