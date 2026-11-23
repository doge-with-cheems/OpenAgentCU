import threading
import time
import unittest

from oacu.cancel import CancelToken, TaskScope
from oacu.interpreter import Backends, execute


class CancelTests(unittest.TestCase):
    def test_scope_reuses_outer_token(self) -> None:
        with TaskScope(cancel_on_esc=False) as outer:
            with TaskScope() as inner:
                self.assertIs(outer, inner)

    def test_token_sleep_cancels(self) -> None:
        token = CancelToken()
        token.cancel()
        started = time.monotonic()
        self.assertTrue(token.sleep(1.0))
        self.assertLess(time.monotonic() - started, 0.5)

    def test_interpreter_cancels_before_first_step(self) -> None:
        event = threading.Event()
        event.set()
        calls = []
        backends = Backends(
            mouse=lambda *args: calls.append(args),
            key=lambda _keys: calls.append("key"),
            pattern=lambda _spec: {"ok": True},
            sleep=time.sleep,
            clock=time.perf_counter,
        )
        ir = {"snapshot_id": 0, "steps": [
            {"op": "click", "x": 10, "y": 10, "at": 0},
        ]}
        with TaskScope(event=event):
            results = execute(ir, backends=backends)
        self.assertEqual(results[0]["code"], "cancelled")
        self.assertEqual(calls, [])

    def test_interpreter_cancels_during_wait(self) -> None:
        event = threading.Event()

        def sleep(_seconds: float) -> None:
            event.set()

        backends = Backends(
            mouse=lambda *args: None,
            key=lambda _keys: None,
            pattern=lambda _spec: {"ok": True},
            sleep=sleep,
            clock=time.perf_counter,
        )
        ir = {"snapshot_id": 0, "steps": [
            {"op": "wait", "ms": 100, "at": 0},
        ]}
        with TaskScope(event=event):
            results = execute(ir, backends=backends)
        self.assertEqual(results[0]["code"], "cancelled")


if __name__ == "__main__":
    unittest.main()
