"""MCP server over stdio (JSON-RPC 2.0, one message per line)."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from ..config import Settings
from ..store import Store
from .protocol import PARSE_ERROR, error, handle


def serve_stdio(store: Store, settings: Settings, stdin: TextIO | None = None,
                stdout: TextIO | None = None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            stdout.write(json.dumps(error(None, PARSE_ERROR, f"parse error: {exc}")) + "\n")
            stdout.flush()
            continue
        if not isinstance(message, dict):
            stdout.write(json.dumps(error(None, -32600, "invalid request")) + "\n")
            stdout.flush()
            continue
        reply = handle(message, store, settings)
        if reply is None:
            continue
        stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0
