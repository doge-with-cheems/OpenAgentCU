"""GUI shell probe: prints `gui 5/5`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = str(ROOT / "tools" / "fixture_desktop.json")


def main() -> int:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "oacu", "gui", "--self-test", "--fixture", FIXTURE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )
    output = (proc.stdout or "").strip().splitlines()
    line = output[-1] if output else ""
    print(line or "gui 0/5")
    if proc.returncode != 0:
        print((proc.stderr or "").strip(), file=sys.stderr)
        return 1
    return 0 if line == "gui 5/5" else 1


if __name__ == "__main__":
    raise SystemExit(main())
