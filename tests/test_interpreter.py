import tempfile
import unittest
from pathlib import Path

from oacu.config import DEFAULTS, Settings
from oacu.interpreter import Backends, execute, parse_keys
from oacu.models import Element
from oacu.store import Store
from oacu.tokens import build_snapshot


def make_store(tmp: str) -> tuple[Store, int, Settings]:
    store = Store(Path(tmp) / "i.db")
    elements = [
        Element(name="记事本", control_type="Window", rect=(0, 0, 800, 600), order=1),
        Element(name="文本编辑器", control_type="Edit", rect=(10, 50, 780, 500),
                automation_id="15", order=2),
    ]
    snapshot = build_snapshot(elements, (1920, 1080))
    snapshot_id = store.save_snapshot(snapshot)
    settings = Settings(json=True, db=Path(tmp) / "i.db", backend="fake",
                        timeout=5.0, verbose=False, config=dict(DEFAULTS))
    return store, snapshot_id, settings


def make_backends(now, calls, pattern=None):
    def sleep(seconds: float) -> None:
        now[0] += seconds

    def mouse(op: str, x: int, y: int, times: int) -> None:
        calls.append(("mouse", op, round(now[0], 3), x, y, times))

    def key(keys: str) -> None:
        calls.append(("key", keys, round(now[0], 3)))

    def pat(spec):
        calls.append(("pattern", spec["op"], round(now[0], 3)))
        if pattern:
            return pattern(spec)
        return {"ok": True}

    def text(value: str) -> None:
        calls.append(("type", value, round(now[0], 3)))

    def launch(value: str) -> str:
        calls.append(("launch", value, round(now[0], 3)))
        return value

    def open_url(value: str) -> str:
        calls.append(("open_url", value, round(now[0], 3)))
        return value

    return Backends(mouse=mouse, key=key, pattern=pat, sleep=sleep, clock=lambda: now[0],
                    type_text=text, launch=launch, open_url=open_url)


class InterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.snapshot_id, self.settings = make_store(self.tmp.name)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def ir(self, steps):
        return {"version": "1.0", "trace_id": "tr", "snapshot_id": self.snapshot_id, "steps": steps}

    def test_all_nine_ops(self) -> None:
        steps = [
            {"op": "invoke", "token": "t0001", "at": 0},
            {"op": "set_value", "token": "t0002", "value": "hi", "at": 100},
            {"op": "click", "token": "t0001", "at": 200},
            {"op": "double_click", "token": "t0001", "at": 300},
            {"op": "right_click", "token": "t0001", "at": 400},
            {"op": "scroll", "token": "t0001", "direction": "down", "times": 2, "at": 500},
            {"op": "key", "keys": "{ENTER}", "at": 600},
            {"op": "wait", "ms": 50, "at": 700},
            {"op": "activate", "token": "t0001", "at": 800},
        ]
        now = [0.0]
        calls: list = []
        results = execute(self.ir(steps), store=self.store, settings=self.settings,
                          backends=make_backends(now, calls))
        self.assertEqual([r["op"] for r in results], [s["op"] for s in steps])
        self.assertTrue(all(r["ok"] for r in results), results)
        mouse_ops = [c[1] for c in calls if c[0] == "mouse"]
        self.assertEqual(mouse_ops, ["double_click", "right_click"])
        self.assertIn(("key", "{ENTER}", 0.6), calls)
        pattern_ops = [c[1] for c in calls if c[0] == "pattern"]
        self.assertEqual(pattern_ops, ["invoke", "set_value", "click", "scroll", "activate"])

    def test_out_of_order_steps_are_sorted(self) -> None:
        steps = [
            {"op": "click", "token": "t0001", "at": 500},
            {"op": "invoke", "token": "t0001", "at": 0},
        ]
        now = [0.0]
        calls: list = []
        results = execute(self.ir(steps), store=self.store, settings=self.settings,
                          backends=make_backends(now, calls))
        self.assertEqual([r["op"] for r in results], ["invoke", "click"])
        self.assertEqual([c[1] for c in calls if c[0] == "mouse"], [])
        self.assertGreaterEqual(now[0], 0.5)

    def test_stale_token_stops_execution(self) -> None:
        steps = [
            {"op": "click", "token": "t9999", "at": 0},
            {"op": "click", "token": "t0001", "at": 100},
        ]
        now = [0.0]
        calls: list = []
        results = execute(self.ir(steps), store=self.store, settings=self.settings,
                          backends=make_backends(now, calls))
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["code"], "stale_token")

    def test_pattern_fallback_click(self) -> None:
        steps = [{"op": "invoke", "token": "t0001", "at": 0}]
        now = [0.0]
        calls: list = []
        results = execute(
            self.ir(steps), store=self.store, settings=self.settings,
            backends=make_backends(now, calls, pattern=lambda spec: {"ok": False, "code": "pattern_unavailable"}),
        )
        self.assertTrue(results[0]["ok"])
        self.assertEqual([c[1] for c in calls if c[0] == "mouse"], ["click"])

    def test_step_timeout(self) -> None:
        def slow(spec):
            now[0] += 2.0
            return {"ok": True}

        now = [0.0]
        calls: list = []
        results = execute(
            self.ir([{"op": "invoke", "token": "t0001", "at": 0}]),
            store=self.store, settings=self.settings,
            backends=make_backends(now, calls, pattern=slow),
        )
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["code"], "timeout")

    def test_click_coordinates_override_token(self) -> None:
        now = [0.0]
        calls: list = []
        execute(self.ir([{"op": "click", "x": 5, "y": 6, "at": 0}]),
                store=self.store, settings=self.settings, backends=make_backends(now, calls))
        self.assertEqual(calls[0][3:5], (5, 6))


    def test_type_op(self) -> None:
        now = [0.0]
        calls: list = []
        execute(self.ir([{"op": "type", "value": "chrome", "at": 0}]),
                store=self.store, settings=self.settings, backends=make_backends(now, calls))
        self.assertEqual(calls[0][0:2], ("type", "chrome"))

    def test_launch_and_url_ops(self) -> None:
        now = [0.0]
        calls: list = []
        execute(self.ir([
            {"op": "launch", "value": "chrome", "at": 0},
            {"op": "open_url", "value": "https://www.youtube.com", "at": 500},
        ]), store=self.store, settings=self.settings, backends=make_backends(now, calls))
        self.assertEqual([c[0] for c in calls], ["launch", "open_url"])
        self.assertEqual(calls[1][1], "https://www.youtube.com")

    def test_set_value_fallback_clicks_then_types(self) -> None:
        now = [0.0]
        calls: list = []
        execute(self.ir([{"op": "set_value", "token": "t0002", "value": "hi", "at": 0}]),
                store=self.store, settings=self.settings,
                backends=make_backends(now, calls,
                                       pattern=lambda spec: {"ok": False, "code": "pattern_unavailable"}))
        self.assertEqual(calls[-2][0], "mouse")
        self.assertEqual(calls[-2][1], "click")
        self.assertEqual(calls[-1][0], "type")
        self.assertEqual(calls[-1][1], "hi")

    def test_win_key_parses(self) -> None:
        self.assertEqual(parse_keys("{WIN}"), [(0x5B, frozenset())])


class KeyParserTests(unittest.TestCase):
    def test_named_key(self) -> None:
        self.assertEqual(parse_keys("{ENTER}"), [(0x0D, frozenset())])

    def test_ctrl_combo(self) -> None:
        self.assertEqual(parse_keys("^s"), [(ord("S"), frozenset({"ctrl"}))])

    def test_single_letter_is_case_insensitive_key(self) -> None:
        self.assertEqual(parse_keys("A"), [(ord("A"), frozenset())])

    def test_win_combos(self) -> None:
        self.assertEqual(parse_keys("win+r"), [(ord("R"), frozenset({"win"}))])
        self.assertEqual(parse_keys("WinR"), [(ord("R"), frozenset({"win"}))])
        self.assertEqual(parse_keys("ctrl+shift+esc"), [(0x1B, frozenset({"ctrl", "shift"}))])
        self.assertEqual(parse_keys("alt+tab"), [(0x09, frozenset({"alt"}))])
        self.assertEqual(parse_keys("alt+f4"), [(0x73, frozenset({"alt"}))])

    def test_sequence(self) -> None:
        parsed = parse_keys("{TAB}abc")
        self.assertEqual([vk for vk, _ in parsed], [0x09, ord("A"), ord("B"), ord("C")])


if __name__ == "__main__":
    unittest.main()
