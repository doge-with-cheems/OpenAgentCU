import threading
import time
import unittest
from unittest.mock import patch

from oacu.cancel import CancelToken, _EscWatcher
from oacu.chain import MAX_STEPS, run_chain


class FakePointer:
    def __init__(self, *, delivered=True) -> None:
        self.calls = []
        self.delivered = delivered
        self.x = 0
        self.y = 0
        self.last_hwnd = 0

    def move(self, x, y, duration_ms=0):
        self.calls.append(("move", x, y, duration_ms))
        self.x, self.y = x, y

    def click(self, x=None, y=None, button="left", clicks=1, interval_ms=80):
        self.calls.append(("click", x, y, button, clicks, interval_ms))
        if x is not None:
            self.x, self.y = x, y
        return {"mode": "virtual", "delivered": self.delivered}

    def drag(self, from_x, from_y, to_x, to_y, button="left", duration_ms=500):
        self.calls.append(("drag", from_x, from_y, to_x, to_y, button, duration_ms))
        self.x, self.y = to_x, to_y
        return {"mode": "virtual", "delivered": self.delivered}

    def scroll(self, x=None, y=None, dy=3, dx=0):
        self.calls.append(("scroll", dy, dx))
        return {"mode": "virtual", "delivered": self.delivered}

    def key_press(self, keys):
        self.calls.append(("key_press", keys))
        return {"mode": "virtual_press", "delivered": self.delivered}

    def key_hold(self, keys, ms):
        self.calls.append(("key_hold", keys, ms))
        return {"mode": "virtual_hold", "delivered": self.delivered}

    def type_text(self, text, replace=True):
        self.calls.append(("type", text, replace))
        return {"mode": "point_value", "delivered": self.delivered}

    def position(self):
        return self.x, self.y


class FakeRuntime:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.pointers = {}
        self.pointer_calls = []

    def pointer(self, pointer_id):
        self.pointer_calls.append(pointer_id)
        if pointer_id not in self.pointers:
            self.pointers[pointer_id] = FakePointer(**self.kwargs)
        return self.pointers[pointer_id]


def steps(*items):
    return list(items)


class ChainTests(unittest.TestCase):
    def test_dry_run_never_creates_pointer(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "type", "text": "hi"},
                {"op": "wait", "ms": 10},
                {"op": "key", "keys": "enter"},
                {"op": "scroll", "direction": "down", "times": 2},
                {"op": "move", "x": 200, "y": 200},
            ),
            dry_run=True,
            runtime=runtime,
        )
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(len(payload["plan"]), 6)
        self.assertEqual(runtime.pointer_calls, [])

    def test_unknown_fields_rejected_before_execution(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "click", "x": 100, "y": 100, "stops_on_error": False},
            ),
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_chain")
        self.assertEqual(payload["executed"], 0)
        self.assertEqual(runtime.pointer_calls, [])
        self.assertEqual(payload["errors"][0]["code"], "unknown_field")

    def test_key_and_type_require_anchor(self) -> None:
        runtime = FakeRuntime()
        for step in ({"op": "key", "keys": "enter"},
                     {"op": "type", "text": "hi"}):
            payload = run_chain([step], runtime=runtime)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["errors"][0]["code"], "no_target")
        self.assertEqual(runtime.pointer_calls, [])

    def test_system_combo_rejected_during_validation(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps({"op": "click", "x": 100, "y": 100},
                  {"op": "key", "keys": "win+r"}),
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_chain")
        self.assertEqual(payload["errors"][0]["code"], "invalid_keys")
        self.assertEqual(runtime.pointer_calls, [])

    def test_stop_on_error_stops_at_first_failure(self) -> None:
        runtime = FakeRuntime(delivered=False)
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "click", "x": 120, "y": 120},
                {"op": "wait", "ms": 1},
            ),
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["executed"], 1)
        self.assertEqual(payload["resume_from"], 1)
        self.assertEqual(payload["results"][0][4], "post_failed")

    def test_keep_going_marks_partial(self) -> None:
        runtime = FakeRuntime(delivered=False)
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "wait", "ms": 1},
                {"op": "wait", "ms": 1},
            ),
            stop_on_error=False,
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["executed"], 3)
        self.assertTrue(payload["partial"])

    def test_pointer_isolation(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "wait", "ms": 1},
                {"op": "wait", "ms": 1},
            ),
            pointer=2,
            runtime=runtime,
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(runtime.pointer_calls, [2])
        self.assertEqual(payload["pointer"], 2)
        self.assertEqual(payload["state"]["hwnd"], 0)

    def test_scroll_direction_mapping(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "scroll", "direction": "down", "times": 2},
                {"op": "scroll", "direction": "up", "times": 1},
            ),
            runtime=runtime,
        )
        self.assertTrue(payload["ok"])
        calls = runtime.pointers[1].calls
        self.assertEqual(calls[-2], ("scroll", -2, 0))
        self.assertEqual(calls[-1], ("scroll", 1, 0))

    def test_type_replace_flag_forwarded(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "type", "text": "hi", "replace": False},
            ),
            runtime=runtime,
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(runtime.pointers[1].calls[-1], ("type", "hi", False))

    def test_length_hint_does_not_block(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            steps({"op": "click", "x": 100, "y": 100},
                  {"op": "wait", "ms": 1}),
            runtime=runtime,
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["warnings"][0]["code"], "length_hint")
        self.assertIsNotNone(payload["hint"])

    def test_chain_id_is_idempotent(self) -> None:
        runtime = FakeRuntime()
        chain = steps(
            {"op": "click", "x": 100, "y": 100},
            {"op": "wait", "ms": 1},
            {"op": "wait", "ms": 1},
            {"op": "wait", "ms": 1},
            {"op": "wait", "ms": 1},
            {"op": "wait", "ms": 1},
        )
        first = run_chain(chain, chain_id="test-idempotent-1", runtime=runtime)
        calls = len(runtime.pointers[1].calls)
        second = run_chain(chain, chain_id="test-idempotent-1", runtime=runtime)
        self.assertTrue(first["ok"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(runtime.pointers[1].calls), calls)

    def test_cancel_before_start_executes_nothing(self) -> None:
        runtime = FakeRuntime()
        cancel = threading.Event()
        cancel.set()
        payload = run_chain(
            steps({"op": "click", "x": 100, "y": 100}),
            cancel_event=cancel,
            cancel_on_esc=False,
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cancelled")
        self.assertTrue(payload["cancelled"])
        self.assertTrue(payload["stop_conversation"])
        self.assertEqual(payload["executed"], 0)
        self.assertTrue(payload["retry_safe"])
        self.assertEqual(runtime.pointer_calls, [])

    def test_cancel_during_wait(self) -> None:
        runtime = FakeRuntime()
        cancel = threading.Event()

        def trigger() -> None:
            time.sleep(0.05)
            cancel.set()

        threading.Thread(target=trigger, daemon=True).start()
        payload = run_chain(
            steps(
                {"op": "click", "x": 100, "y": 100},
                {"op": "wait", "ms": 5000},
                {"op": "wait", "ms": 1},
            ),
            cancel_event=cancel,
            cancel_on_esc=False,
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(payload["executed"], 2)
        self.assertTrue(payload["stop_conversation"])
        self.assertTrue(payload["results"][0][2])
        self.assertFalse(payload["results"][1][2])
        self.assertEqual(payload["results"][1][4], "cancelled")
        self.assertEqual(payload["resume_from"], 1)

    def test_esc_watcher_detects_key_state(self) -> None:
        token = CancelToken()
        with patch("oacu.cancel.ctypes.windll.user32.GetAsyncKeyState",
                   return_value=0x8000):
            watcher = _EscWatcher(token)
            watcher.start()
            try:
                self.assertTrue(token.is_set())
            finally:
                watcher.stop()

    def test_too_many_steps_rejected(self) -> None:
        runtime = FakeRuntime()
        payload = run_chain(
            [{"op": "wait", "ms": 1}] * (MAX_STEPS + 1),
            runtime=runtime,
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "invalid_chain")
        self.assertEqual(runtime.pointer_calls, [])


if __name__ == "__main__":
    unittest.main()
