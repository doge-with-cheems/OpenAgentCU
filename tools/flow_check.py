"""End-to-end replay with a fake UIA backend: prints `e2e 12/12`."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oacu.agent import run_act  # noqa: E402
from oacu.config import DEFAULTS, Settings  # noqa: E402
from oacu.interpreter import Backends, execute  # noqa: E402
from oacu.ir import build_ir, validate_ir  # noqa: E402
from oacu.pipeline import capture_snapshot  # noqa: E402
from oacu.planner import make_plan  # noqa: E402
from oacu.store import Store  # noqa: E402

FIXTURE = str(ROOT / "tools" / "fixture_desktop.json")


def main() -> int:
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="oacu-e2e-") as tmp:
        os.environ["OACU_HOME"] = tmp
        settings = Settings(json=True, db=Path(tmp) / "e2e.db", backend="fake",
                            timeout=5.0, verbose=False, config=dict(DEFAULTS))
        store = Store(settings.db)
        try:
            snapshot = capture_snapshot(backend="fake", fixture=FIXTURE)
            checks.append(("capture", len(snapshot.tokens) == 7))
            checks.append(("window_first", snapshot.tokens[0].ctype == "Window"
                           and snapshot.tokens[0].order == 1))
            checks.append(("normalize", snapshot.stats.get("dropped") == 2))
            checks.append(("text", len(snapshot.text.splitlines()) == 7))

            snapshot_id = store.save_snapshot(snapshot)
            record = store.latest_snapshot()
            checks.append(("store", record is not None and record.token_count == 7))

            tokens = store.get_tokens(snapshot_id)
            plan = make_plan("点击七然后点击等于", tokens)
            checks.append(("plan", [s.token_id for s in plan.steps] == ["t0006", "t0007"]))

            ir = build_ir(plan, snapshot_id=snapshot_id, trace_id="e2e", interval_ms=120)
            checks.append(("ir_offsets", [s["at"] for s in ir["steps"]] == [0, 120]))
            try:
                validate_ir(ir)
                checks.append(("ir_valid", True))
            except Exception:
                checks.append(("ir_valid", False))

            now = [0.0]
            calls: list[tuple] = []

            def sleep(seconds: float) -> None:
                now[0] += seconds

            def mouse(op: str, x: int, y: int, times: int) -> None:
                calls.append((op, x, y, round(now[0], 3)))

            def key(keys: str) -> None:
                calls.append(("key", keys, round(now[0], 3)))

            def pattern(spec):
                return {"ok": True}

            backends = Backends(mouse=mouse, key=key, pattern=pattern,
                                sleep=sleep, clock=lambda: now[0])
            results = execute(ir, store=store, settings=settings, backends=backends)
            checks.append(("exec_ok", len(results) == 2 and all(r["ok"] for r in results)))
            checks.append(("click_coords", [c[1:3] for c in calls] == [
                tokens[5].center, tokens[6].center]))
            checks.append(("timing", calls[1][3] - calls[0][3] >= 0.11))

            def ok_executor(ir_payload):
                return [{"index": i, "op": s["op"], "ok": True, "ms": 1.0, "at": s.get("at", 0)}
                        for i, s in enumerate(ir_payload["steps"])]

            traced = run_act("点击七", settings, store=store, fixture=FIXTURE,
                             executor=ok_executor)
            audit = store.get_action(traced["trace_id"])
            checks.append(("audit", traced["status"] == "ok" and audit["status"] == "ok"
                           and Path(traced["ir_path"]).is_file()))
        finally:
            store.close()

    passed = sum(1 for _, ok in checks if ok)
    print(f"e2e {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"FAIL {name}", file=sys.stderr)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
