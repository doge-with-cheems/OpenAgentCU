import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None  # type: ignore

from oacu.config import DEFAULTS, Settings

FIXTURE = str(Path(__file__).resolve().parents[1] / "tools" / "fixture_desktop.json")


def pump(root, predicate, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            root.update()
        except tk.TclError:
            return False
        if predicate():
            return True
        time.sleep(0.02)
    return False


@unittest.skipIf(tk is None, "tkinter unavailable")
class GuiInteractionTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no desktop session: {exc}")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("OACU_HOME")
        os.environ["OACU_HOME"] = self.tmp.name
        self.settings = Settings(
            json=True,
            db=Path(self.tmp.name) / "gui.db",
            backend="fake",
            timeout=5.0,
            verbose=False,
            config=dict(DEFAULTS),
        )

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        if self.old_home is None:
            os.environ.pop("OACU_HOME", None)
        else:
            os.environ["OACU_HOME"] = self.old_home
        self.tmp.cleanup()

    def test_scan_then_plan_through_ui_threads(self) -> None:
        from oacu.gui import GuiApp

        app = GuiApp(self.root, self.settings, FIXTURE)
        app.scan()
        self.assertTrue(pump(self.root, lambda: not app.busy), "scan did not finish")
        self.assertEqual(len(app.tokens), 7)
        self.assertEqual(len(app.token_tree.get_children()), 7)
        self.assertIn("snapshot #", app.stat_snapshot.get())

        app.instruction_var.set("点击七")
        app.do_plan()
        self.assertTrue(pump(self.root, lambda: not app.busy), "plan did not finish")
        self.assertEqual(len(app.plan_tree.get_children()), 1)
        self.assertIn("token", app.ir_text.get("1.0", "end").lower())

        app.refresh_records()
        self.assertTrue(pump(self.root, lambda: not app.busy), "records did not finish")
        self.assertGreaterEqual(len(app.records), 1)

    def test_mcp_config_is_valid_json(self) -> None:
        import json

        from oacu.gui import GuiApp

        app = GuiApp(self.root, self.settings, FIXTURE)
        payload = json.loads(app.mcp_config())
        self.assertEqual(payload["mcpServers"]["opencu"]["args"], ["-m", "oacu", "mcp", "serve"])


if __name__ == "__main__":
    unittest.main()
