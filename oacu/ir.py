"""IR (interpreter instruction) compilation, validation and storage."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ir_dir
from .errors import IRValidationError
from .planner import Plan

IR_VERSION = "1.0"

OPS = {
    "invoke", "set_value", "click", "double_click", "right_click",
    "scroll", "key", "wait", "activate", "type", "launch", "open_url",
}
TOKEN_OPS = {"invoke", "set_value", "activate"}
DIRECTIONS = {"up", "down", "left", "right"}


def build_ir(plan: Plan, *, snapshot_id: int, trace_id: str, interval_ms: int = 120) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    at = 0
    for plan_step in plan.steps:
        item: dict[str, Any] = {"op": plan_step.op, "at": at}
        if plan_step.token_id:
            item["token"] = plan_step.token_id
        if plan_step.value:
            item["value"] = plan_step.value
        if plan_step.keys:
            item["keys"] = plan_step.keys
        if plan_step.direction:
            item["direction"] = plan_step.direction
        if plan_step.times and plan_step.times != 1:
            item["times"] = plan_step.times
        if plan_step.ms:
            item["ms"] = plan_step.ms
        steps.append(item)
        at += max(1, interval_ms)

    return {
        "version": IR_VERSION,
        "trace_id": trace_id,
        "snapshot_id": int(snapshot_id),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": steps,
    }


def _require(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise IRValidationError(field, message)


def validate_ir(ir: dict[str, Any]) -> None:
    _require(isinstance(ir, dict), "ir", "必须是对象")
    _require(ir.get("version") == IR_VERSION, "version", f"必须是 {IR_VERSION}")
    _require(bool(ir.get("trace_id")), "trace_id", "不能为空")
    _require(isinstance(ir.get("snapshot_id"), int), "snapshot_id", "必须是整数")
    steps = ir.get("steps")
    _require(isinstance(steps, list) and bool(steps), "steps", "至少要有 1 个步骤")

    previous_at = -1
    for index, step in enumerate(steps):
        prefix = f"steps[{index}]"
        _require(isinstance(step, dict), prefix, "必须是对象")
        op = step.get("op")
        _require(op in OPS, f"{prefix}.op", f"未知 op: {op!r}")
        at = step.get("at", 0)
        _require(isinstance(at, int) and at >= 0, f"{prefix}.at", "必须是非负整数毫秒")
        _require(at >= previous_at, f"{prefix}.at", "时间偏移不能倒退")
        previous_at = at

        token = step.get("token")
        if op in TOKEN_OPS:
            _require(isinstance(token, str) and token.startswith("t"), f"{prefix}.token",
                     f"{op} 必须指定 token")
        if op in ("click", "double_click", "right_click"):
            has_token = isinstance(token, str) and bool(token)
            has_xy = isinstance(step.get("x"), int) and isinstance(step.get("y"), int)
            _require(has_token or has_xy, f"{prefix}.token", f"{op} 必须指定 token 或 x/y 坐标")
        if op in ("set_value", "type", "launch"):
            _require(isinstance(step.get("value"), str) and bool(step.get("value")),
                     f"{prefix}.value", f"{op} 必须带非空字符串 value")
        if op == "open_url":
            _require(isinstance(step.get("value"), str)
                     and str(step.get("value")).startswith(("http://", "https://")),
                     f"{prefix}.value", "open_url 必须带 http(s) URL")
        if op == "key":
            _require(isinstance(step.get("keys"), str) and bool(step.get("keys")),
                     f"{prefix}.keys", "key 必须带 keys")
        if op == "scroll":
            _require(step.get("direction") in DIRECTIONS, f"{prefix}.direction",
                     "direction 必须是 up/down/left/right")
            times = step.get("times", 1)
            _require(isinstance(times, int) and times >= 1, f"{prefix}.times", "times 必须是正整数")
        if op == "wait":
            _require(isinstance(step.get("ms"), int) and step.get("ms") >= 0,
                     f"{prefix}.ms", "wait 必须带非负整数 ms")


def write_ir(ir: dict[str, Any], trace_id: str) -> Path:
    folder = ir_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{trace_id}.json"
    path.write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_ir(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise IRValidationError("ir", "文件内容必须是 JSON 对象")
    validate_ir(data)
    return data
