"""CLI smoke test: prints `cli 9/9` on success."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = str(ROOT / "tools" / "fixture_desktop.json")
WAIT_IR = str(ROOT / "tools" / "wait_ir.json")


def run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "oacu", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def as_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="oacu-smoke-") as tmp:
        env = dict(os.environ)
        env["OACU_HOME"] = tmp
        env["PYTHONIOENCODING"] = "utf-8"
        db = str(Path(tmp) / "smoke.db")

        proc = run(["--version"], env)
        checks.append(("version", proc.returncode == 0 and "oacu" in proc.stdout, proc.stdout.strip()))

        proc = run(["--help"], env)
        commands = ("scan", "dump", "plan", "act", "exec", "serve", "mcp", "doctor")
        checks.append(("help", proc.returncode == 0 and all(c in proc.stdout for c in commands),
                       "8 subcommands"))

        proc = run(["nope"], env)
        checks.append(("unknown", proc.returncode == 2, f"exit={proc.returncode}"))

        proc = run(["doctor", "--json"], env)
        payload = as_json(proc)
        checks.append(("doctor", proc.returncode == 0 and payload.get("ok") is True,
                       f"backend={payload.get('backend')} ps_uia={payload.get('ps_uia')}"))

        proc = run(["scan", "--json", "--db", db, "--backend", "fake", "--fixture", FIXTURE], env)
        payload = as_json(proc)
        checks.append(("scan", proc.returncode == 0 and payload.get("count") == 7
                       and payload.get("stats", {}).get("dropped") == 2,
                       f"count={payload.get('count')} dropped={payload.get('stats', {}).get('dropped')}"))

        proc = run(["dump", "--json", "--db", db], env)
        payload = as_json(proc)
        checks.append(("dump", proc.returncode == 0 and len(payload.get("tokens", [])) == 7,
                       f"tokens={len(payload.get('tokens', []))}"))

        proc = run(["plan", "点击七", "--json", "--db", db, "--backend", "fake",
                    "--fixture", FIXTURE], env)
        payload = as_json(proc)
        checks.append(("plan", proc.returncode == 0 and payload.get("trace_id")
                       and len(payload.get("plan", {}).get("steps", [])) == 1,
                       f"steps={len(payload.get('plan', {}).get('steps', []))}"))

        proc = run(["act", "点击七", "--dry-run", "--json", "--db", db, "--backend", "fake",
                    "--fixture", FIXTURE], env)
        payload = as_json(proc)
        checks.append(("act", proc.returncode == 0 and payload.get("dry_run") is True
                       and bool(payload.get("trace_id")), f"trace={payload.get('trace_id')}"))

        proc = run(["exec", WAIT_IR, "--inproc", "--json", "--db", db], env)
        payload = as_json(proc)
        checks.append(("exec", proc.returncode == 0 and payload.get("ok") is True
                       and len(payload.get("results", [])) == 2,
                       f"results={len(payload.get('results', []))}"))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"cli {passed}/{len(checks)}")
    for name, ok, detail in checks:
        if not ok:
            print(f"FAIL {name}: {detail}", file=sys.stderr)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
