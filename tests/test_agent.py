import os
import tempfile
import threading
import unittest
from pathlib import Path

from oacu.agent import build_plan_only, run_act
from oacu.config import DEFAULTS, Settings
from oacu.errors import UsageError
from oacu.store import Store
from oacu.transport import serve_forever

FIXTURE = str(Path(__file__).resolve().parents[1] / "tools" / "fixture_desktop.json")


class AgentDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("OACU_HOME")
        os.environ["OACU_HOME"] = self.tmp.name
        self.settings = Settings(
            json=True,
            db=Path(self.tmp.name) / "agent.db",
            backend="fake",
            timeout=5.0,
            verbose=False,
            config=dict(DEFAULTS),
        )
        self.store = Store(self.settings.db)

    def tearDown(self) -> None:
        self.store.close()
        if self.old_home is None:
            os.environ.pop("OACU_HOME", None)
        else:
            os.environ["OACU_HOME"] = self.old_home
        self.tmp.cleanup()

    @staticmethod
    def ok_executor(ir):
        return [
            {"index": index, "op": step["op"], "ok": True, "ms": 1.0, "at": step.get("at", 0)}
            for index, step in enumerate(ir["steps"])
        ]

    def test_dry_run_returns_trace_and_creates_snapshot(self) -> None:
        result = run_act("点击记事本", self.settings, store=self.store, dry_run=True, fixture=FIXTURE)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["trace_id"])
        self.assertEqual(result["tokens"], 7)
        self.assertIsNotNone(self.store.latest_snapshot())
        record = self.store.get_action(result["trace_id"])
        self.assertEqual(record["status"], "dry_run")

    def test_empty_instruction_rejected(self) -> None:
        with self.assertRaises(UsageError) as ctx:
            run_act("   ", self.settings, store=self.store, dry_run=True, fixture=FIXTURE)
        self.assertEqual(ctx.exception.code, 2)

    def test_too_long_instruction_rejected(self) -> None:
        with self.assertRaises(UsageError):
            run_act("x" * 2001, self.settings, store=self.store, dry_run=True, fixture=FIXTURE)

    def test_second_dry_run_reuses_fresh_snapshot(self) -> None:
        first = run_act("点击记事本", self.settings, store=self.store, dry_run=True, fixture=FIXTURE)
        second = run_act("点击记事本", self.settings, store=self.store, dry_run=True, fixture=FIXTURE)
        self.assertFalse(second["refreshed"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])

    def test_full_run_success(self) -> None:
        result = run_act("点击七", self.settings, store=self.store, fixture=FIXTURE,
                         executor=self.ok_executor)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["steps"], 1)
        self.assertTrue(Path(result["ir_path"]).is_file())
        record = self.store.get_action(result["trace_id"])
        self.assertEqual(record["status"], "ok")
        self.assertIsNone(record["error"])

    def test_full_run_failure_marks_error(self) -> None:
        def failing(ir):
            return [{"index": 0, "op": ir["steps"][0]["op"], "ok": False,
                     "ms": 1.0, "at": 0, "error": "boom"}]

        result = run_act("点击七", self.settings, store=self.store, fixture=FIXTURE,
                         executor=failing)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        record = self.store.get_action(result["trace_id"])
        self.assertEqual(record["status"], "error")
        self.assertIn("boom", record["error"])

    def test_plan_only_builds_ir(self) -> None:
        result = build_plan_only("点击七", self.settings, store=self.store, fixture=FIXTURE)
        self.assertTrue(result["ok"])
        self.assertEqual(result["plan"]["steps"][0]["token_id"], "t0006")
        self.assertEqual(len(result["ir"]["steps"]), 1)

    def test_daemon_success_path(self) -> None:
        port_holder = {}
        ready = threading.Event()

        def handler(request, store, settings):
            steps = request["ir"]["steps"]
            return {"ok": True, "results": [
                {"index": i, "op": s["op"], "ok": True, "ms": 1.0, "at": s.get("at", 0)}
                for i, s in enumerate(steps)
            ]}

        thread = threading.Thread(
            target=serve_forever,
            args=("127.0.0.1", 0, self.store, self.settings),
            kwargs={"handler": handler, "ready": lambda p: (port_holder.update(port=p), ready.set()),
                    "max_connections": 1},
            daemon=True,
        )
        thread.start()
        self.assertTrue(ready.wait(3))
        result = run_act("点击七", self.settings, store=self.store, fixture=FIXTURE,
                         inproc=False, port=port_holder["port"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        thread.join(timeout=3)

    def test_daemon_failure_returns_error(self) -> None:
        port_holder = {}
        ready = threading.Event()

        def handler(request, store, settings):
            return {"ok": False, "results": [
                {"index": 0, "op": "click", "ok": False, "ms": 1.0, "at": 0, "error": "boom"}
            ], "error": "boom"}

        thread = threading.Thread(
            target=serve_forever,
            args=("127.0.0.1", 0, self.store, self.settings),
            kwargs={"handler": handler, "ready": lambda p: (port_holder.update(port=p), ready.set()),
                    "max_connections": 1},
            daemon=True,
        )
        thread.start()
        self.assertTrue(ready.wait(3))
        result = run_act("点击七", self.settings, store=self.store, fixture=FIXTURE,
                         inproc=False, port=port_holder["port"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
