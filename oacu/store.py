"""SQLite persistence: snapshots, tokens and action audit log."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ensure_dirs
from .models import Snapshot, Token

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    window      TEXT NOT NULL,
    screen      TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    text        TEXT NOT NULL,
    stats       TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS tokens (
    snapshot_id INTEGER NOT NULL,
    token_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    ctype       TEXT NOT NULL,
    x           INTEGER NOT NULL,
    y           INTEGER NOT NULL,
    w           INTEGER NOT NULL,
    h           INTEGER NOT NULL,
    relations   TEXT NOT NULL,
    ord         INTEGER NOT NULL,
    PRIMARY KEY (snapshot_id, token_id)
);
CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT NOT NULL UNIQUE,
    snapshot_id INTEGER,
    instruction TEXT NOT NULL,
    plan        TEXT,
    ir          TEXT,
    status      TEXT NOT NULL,
    error       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_actions_trace ON actions(trace_id);
"""


@dataclass
class SnapshotRecord:
    id: int
    created_at: str
    window: list[str]
    screen: tuple[int, int]
    token_count: int
    text: str
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.id,
            "created_at": self.created_at,
            "window": self.window,
            "screen": list(self.screen),
            "token_count": self.token_count,
            "stats": self.stats,
        }


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def age_seconds(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return float("inf")
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now().astimezone() - created).total_seconds())


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.path.parent and str(self.path.parent) not in ("", "."):
                self.path.parent.mkdir(parents=True, exist_ok=True)
            else:
                ensure_dirs()
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---------------------------------------------------------------- snapshots
    def save_snapshot(self, snapshot: Snapshot, keep: int = 20) -> int:
        conn = self.connect()
        signature = json.dumps(snapshot.window, ensure_ascii=False)
        with conn:
            cursor = conn.execute(
                "INSERT INTO snapshots(created_at, window, screen, token_count, text, stats) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot.created_at or now_iso(),
                    signature,
                    json.dumps(list(snapshot.screen)),
                    len(snapshot.tokens),
                    snapshot.text,
                    json.dumps(snapshot.stats, ensure_ascii=False),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT OR REPLACE INTO tokens"
                "(snapshot_id, token_id, name, ctype, x, y, w, h, relations, ord) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        snapshot_id, token.id, token.name, token.ctype,
                        token.rect[0], token.rect[1], token.rect[2], token.rect[3],
                        json.dumps(token.relations, ensure_ascii=False), token.order,
                    )
                    for token in snapshot.tokens
                ],
            )
        self.prune(keep=keep)
        return snapshot_id

    def _record(self, row: sqlite3.Row) -> SnapshotRecord:
        screen = json.loads(row["screen"])
        return SnapshotRecord(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            window=json.loads(row["window"]),
            screen=(int(screen[0]), int(screen[1])),
            token_count=int(row["token_count"]),
            text=str(row["text"]),
            stats=json.loads(row["stats"] or "{}"),
        )

    def latest_snapshot(self, window: str | None = None) -> SnapshotRecord | None:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT 100"
        ).fetchall()
        needle = (window or "").strip().lower()
        for row in rows:
            record = self._record(row)
            if not needle:
                return record
            if any(needle in name.lower() for name in record.window):
                return record
        return None

    def get_snapshot(self, snapshot_id: int) -> SnapshotRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return self._record(row) if row else None

    def get_tokens(self, snapshot_id: int) -> list[Token]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM tokens WHERE snapshot_id = ? ORDER BY ord, rowid",
            (snapshot_id,),
        ).fetchall()
        tokens: list[Token] = []
        for row in rows:
            tokens.append(
                Token(
                    id=str(row["token_id"]),
                    name=str(row["name"]),
                    ctype=str(row["ctype"]),
                    rect=(int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"])),
                    relations=json.loads(row["relations"] or "{}"),
                    order=int(row["ord"]),
                )
            )
        return tokens

    def resolve(self, snapshot_id: int, token_id: str) -> Token | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM tokens WHERE snapshot_id = ? AND token_id = ?",
            (snapshot_id, token_id),
        ).fetchone()
        if not row:
            return None
        return Token(
            id=str(row["token_id"]),
            name=str(row["name"]),
            ctype=str(row["ctype"]),
            rect=(int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"])),
            relations=json.loads(row["relations"] or "{}"),
            order=int(row["ord"]),
        )

    def prune(self, keep: int = 20) -> int:
        conn = self.connect()
        removed = 0
        signatures = conn.execute("SELECT DISTINCT window FROM snapshots").fetchall()
        with conn:
            for row in signatures:
                signature = row["window"]
                stale = conn.execute(
                    "SELECT id FROM snapshots WHERE window = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                    (signature, keep),
                ).fetchall()
                ids = [int(item["id"]) for item in stale]
                for snapshot_id in ids:
                    conn.execute("DELETE FROM tokens WHERE snapshot_id = ?", (snapshot_id,))
                    conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
                    removed += 1
        return removed

    # ------------------------------------------------------------------ actions
    def record_action(self, trace_id: str, instruction: str, snapshot_id: int | None = None) -> int:
        conn = self.connect()
        with conn:
            cursor = conn.execute(
                "INSERT INTO actions(trace_id, snapshot_id, instruction, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (trace_id, snapshot_id, instruction, now_iso()),
            )
        return int(cursor.lastrowid)

    def update_action(
        self,
        trace_id: str,
        *,
        status: str,
        error: str | None = None,
        snapshot_id: int | None = None,
        plan: dict[str, Any] | None = None,
        ir: dict[str, Any] | None = None,
    ) -> None:
        sets = ["status = ?", "error = ?"]
        values: list[Any] = [status, error]
        if snapshot_id is not None:
            sets.append("snapshot_id = ?")
            values.append(snapshot_id)
        if plan is not None:
            sets.append("plan = ?")
            values.append(json.dumps(plan, ensure_ascii=False))
        if ir is not None:
            sets.append("ir = ?")
            values.append(json.dumps(ir, ensure_ascii=False))
        values.append(trace_id)
        conn = self.connect()
        with conn:
            conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE trace_id = ?", values)

    def get_action(self, trace_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM actions WHERE trace_id = ?", (trace_id,)).fetchone()
        return dict(row) if row else None

    def list_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]
