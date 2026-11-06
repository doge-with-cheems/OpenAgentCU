"""MCP protocol probe: drives `oacu mcp serve` over stdio and prints mcp N/4."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=None, help="test a frozen oacu.exe instead of python -m oacu")
    args = parser.parse_args(argv)
    checks: list[bool] = []
    temp_parent = str(ROOT) if args.exe else None
    with tempfile.TemporaryDirectory(prefix="oacu-mcp-", dir=temp_parent) as tmp:
        env = dict(os.environ)
        env["OACU_HOME"] = tmp
        env["PYTHONIOENCODING"] = "utf-8"
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "nope", "arguments": {}}},
        ]
        payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"
        if args.exe:
            command = [str(Path(args.exe)), "mcp", "serve", "--db", str(Path(tmp) / "probe.db")]
        else:
            command = [sys.executable, "-m", "oacu", "mcp", "serve", "--db", str(Path(tmp) / "probe.db")]
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
        )
        lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        replies: list[dict] = []
        for line in lines:
            try:
                replies.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        checks.append(
            len(replies) >= 1
            and replies[0].get("result", {}).get("protocolVersion") == "2024-11-05"
            and replies[0].get("result", {}).get("serverInfo", {}).get("name") == "opencu"
        )
        tools = []
        if len(replies) >= 2:
            tools = replies[1].get("result", {}).get("tools", [])
        expected = {
            "desktop_scan", "desktop_tokens", "desktop_find", "desktop_summary", "launch_app", "open_url", "search_web", "win_run", "computer_act",
            "mouse_move", "mouse_click", "mouse_drag", "mouse_scroll",
            "key_press", "key_hold", "type_text", "screen_info", "mouse_position",
        }
        checks.append({tool.get("name") for tool in tools} == expected)
        checks.append(
            len(replies) >= 3
            and replies[2].get("result", {}).get("isError") is True
        )
        checks.append(proc.returncode == 0)

    passed = sum(1 for check in checks if check)
    print(f"mcp {passed}/4")
    if passed != 4:
        print("FAILED CHECKS:", [i + 1 for i, ok in enumerate(checks) if not ok], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
