import json
import os
import tempfile
import unittest
from pathlib import Path

from oacu.errors import IRValidationError
from oacu.ir import build_ir, load_ir, validate_ir, write_ir
from oacu.models import Token
from oacu.planner import make_plan


def tokens() -> list[Token]:
    return [
        Token("t0001", "记事本", "Window", (0, 0, 800, 600), order=1),
        Token("t0002", "文本编辑器", "Edit", (10, 50, 780, 500), order=2),
        Token("t0003", "七", "Button", (20, 300, 60, 60), order=3),
    ]


def sample_ir(**overrides) -> dict:
    ir = {
        "version": "1.0",
        "trace_id": "trace-1",
        "snapshot_id": 1,
        "steps": [{"op": "click", "token": "t0003", "at": 0}],
    }
    ir.update(overrides)
    return ir


class IRTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("OACU_HOME")
        os.environ["OACU_HOME"] = self.tmp.name

    def tearDown(self) -> None:
        if self.old_home is None:
            os.environ.pop("OACU_HOME", None)
        else:
            os.environ["OACU_HOME"] = self.old_home
        self.tmp.cleanup()

    def test_build_offsets(self) -> None:
        plan = make_plan("点击七然后点击记事本", tokens())
        ir = build_ir(plan, snapshot_id=7, trace_id="trace-x", interval_ms=120)
        self.assertEqual([s["at"] for s in ir["steps"]], [0, 120])
        self.assertEqual(ir["steps"][0]["token"], "t0003")
        self.assertEqual(ir["snapshot_id"], 7)
        validate_ir(ir)

    def test_set_value_and_key(self) -> None:
        plan = make_plan("在文本编辑器输入你好然后按键回车", tokens())
        ir = build_ir(plan, snapshot_id=1, trace_id="trace-y")
        self.assertEqual(ir["steps"][0]["value"], "你好")
        self.assertEqual(ir["steps"][1]["keys"], "{ENTER}")
        validate_ir(ir)

    def test_unknown_op_rejected(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "explode", "at": 0}]))
        self.assertIn("op", str(ctx.exception))

    def test_invoke_requires_token(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "invoke", "at": 0}]))
        self.assertIn("token", str(ctx.exception))

    def test_negative_at_rejected(self) -> None:
        with self.assertRaises(IRValidationError):
            validate_ir(sample_ir(steps=[{"op": "click", "token": "t1", "at": -1}]))

    def test_decreasing_at_rejected(self) -> None:
        with self.assertRaises(IRValidationError):
            validate_ir(sample_ir(steps=[
                {"op": "click", "token": "t1", "at": 100},
                {"op": "click", "token": "t1", "at": 50},
            ]))

    def test_empty_steps_rejected(self) -> None:
        with self.assertRaises(IRValidationError):
            validate_ir(sample_ir(steps=[]))

    def test_set_value_requires_value(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "set_value", "token": "t1", "at": 0}]))
        self.assertIn("value", str(ctx.exception))

    def test_key_requires_keys(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "key", "at": 0}]))
        self.assertIn("keys", str(ctx.exception))

    def test_scroll_direction(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "scroll", "token": "t1", "at": 0, "direction": "sideways"}]))
        self.assertIn("direction", str(ctx.exception))

    def test_click_coordinates_without_token(self) -> None:
        validate_ir(sample_ir(steps=[{"op": "click", "at": 0, "x": 10, "y": 20}]))

    def test_launch_type_and_url_ops(self) -> None:
        validate_ir(sample_ir(steps=[
            {"op": "launch", "value": "chrome", "at": 0},
            {"op": "type", "value": "hello", "at": 1200},
            {"op": "open_url", "value": "https://www.youtube.com", "at": 1400},
        ]))

    def test_open_url_requires_http(self) -> None:
        with self.assertRaises(IRValidationError) as ctx:
            validate_ir(sample_ir(steps=[{"op": "open_url", "value": "youtube", "at": 0}]))
        self.assertIn("open_url", str(ctx.exception))

    def test_type_requires_value(self) -> None:
        with self.assertRaises(IRValidationError):
            validate_ir(sample_ir(steps=[{"op": "type", "at": 0}]))

    def test_write_and_load_roundtrip(self) -> None:
        ir = sample_ir()
        path = write_ir(ir, "trace-1")
        self.assertTrue(path.is_file())
        loaded = load_ir(path)
        self.assertEqual(loaded, ir)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["trace_id"], "trace-1")


if __name__ == "__main__":
    unittest.main()
