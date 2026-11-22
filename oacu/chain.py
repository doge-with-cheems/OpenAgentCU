"""Prewritten operation chains executed in batch on one virtual pointer.

A chain is a JSON list of small, atomic steps. The caller (usually an LLM)
writes the whole chain first; OpenCU validates every step before touching the
desktop, then executes the chain sequentially against one virtual pointer.
"""

from __future__ import annotations

import time
from typing import Any

from . import input as input_mod
from .errors import OacuError
from .virtual import (
    VirtualInputError,
    pointer_lock,
    validate_keys,
    validate_point,
    validate_pointer,
)

CHAIN_VERSION = 1
MAX_STEPS = 32
RECOMMENDED_MIN = 6
RECOMMENDED_MAX = 12
MAX_TEXT = 2000
MAX_WAIT_MS = 10000
DEFAULT_TIMEOUT_MS = 30000
MAX_TIMEOUT_MS = 120000
RECENT_TTL_S = 120.0
RECENT_MAX = 16

_RECENT: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(chain_id: str) -> dict[str, Any] | None:
    now = time.monotonic()
    for key, (stamp, payload) in list(_RECENT.items()):
        if now - stamp > RECENT_TTL_S:
            _RECENT.pop(key, None)
    item = _RECENT.get(chain_id)
    return item[1] if item else None


def _cache_put(chain_id: str, payload: dict[str, Any]) -> None:
    _RECENT[chain_id] = (time.monotonic(), payload)
    while len(_RECENT) > RECENT_MAX:
        _RECENT.pop(next(iter(_RECENT)))


BUTTONS = ("left", "right", "middle")
DIRECTIONS = ("up", "down", "left", "right")

OP_KEYS: dict[str, set[str]] = {
    "move": {"op", "x", "y", "duration_ms"},
    "click": {"op", "x", "y", "button", "clicks", "interval_ms"},
    "drag": {"op", "from_x", "from_y", "to_x", "to_y", "button", "duration_ms"},
    "scroll": {"op", "direction", "times"},
    "key": {"op", "keys", "ms"},
    "type": {"op", "text", "replace"},
    "wait": {"op", "ms"},
}


class ChainStepError(Exception):
    """A step failed after the chain started."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _issue(index: int, field: str, code: str, message: str) -> dict[str, Any]:
    return {"index": index, "field": field, "code": code, "message": message}


def _as_int(value: Any, index: int, field: str, errors: list[dict[str, Any]],
            *, default: int | None = None, minimum: int | None = None,
            maximum: int | None = None) -> int | None:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(_issue(index, field, "not_int", "必须是整数"))
        return None
    if minimum is not None and value < minimum:
        errors.append(_issue(index, field, "out_of_range",
                             f"必须 >= {minimum}"))
        return None
    if maximum is not None and value > maximum:
        errors.append(_issue(index, field, "out_of_range",
                             f"必须 <= {maximum}"))
        return None
    return value


def _as_point(x: Any, y: Any, index: int, *, required: bool,
              errors: list[dict[str, Any]]) -> tuple[int, int] | None:
    if x is None and y is None:
        if required:
            errors.append(_issue(index, "x/y", "missing", "必须同时提供 x 和 y"))
        return None
    if x is None or y is None:
        errors.append(_issue(index, "x/y", "pair_required", "x 和 y 必须同时提供"))
        return None
    if isinstance(x, bool) or not isinstance(x, int) or isinstance(y, bool) or not isinstance(y, int):
        errors.append(_issue(index, "x/y", "not_int", "坐标必须是整数"))
        return None
    try:
        return validate_point(x, y)
    except VirtualInputError as exc:
        errors.append(_issue(index, "x/y", "out_of_screen", str(exc)))
        return None


def validate_chain(
    steps: Any,
    *,
    pointer: int = 1,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None, int]:
    """Validate and normalize a chain without touching the desktop pointer.

    Returns (steps, warnings, hint, estimated_ms). Raises ValueError carrying
    ``errors`` when the chain is invalid; no step is executed in that case.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        pointer_id = validate_pointer(pointer)
    except VirtualInputError as exc:
        errors.append(_issue(-1, "pointer", "invalid_pointer", str(exc)))
        pointer_id = 1

    timeout = _as_int(timeout_ms, -1, "timeout_ms", errors,
                      minimum=1000, maximum=MAX_TIMEOUT_MS)
    if timeout is None:
        timeout = DEFAULT_TIMEOUT_MS

    if not isinstance(steps, list):
        errors.append(_issue(-1, "steps", "not_list", "steps 必须是数组"))
        steps = []
    if not steps:
        errors.append(_issue(-1, "steps", "empty", "至少要有一个步骤"))
    if len(steps) > MAX_STEPS:
        errors.append(_issue(-1, "steps", "too_many",
                             f"最多 {MAX_STEPS} 步，当前 {len(steps)} 步"))

    normalized: list[dict[str, Any]] = []
    anchored = False
    estimated = 0

    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            errors.append(_issue(index, "steps", "not_object", "每一步必须是对象"))
            continue
        op = raw.get("op")
        if not isinstance(op, str) or op not in OP_KEYS:
            errors.append(_issue(index, "op", "unknown_op",
                                 f"不支持的操作: {op!r}"))
            continue
        allowed = OP_KEYS[op]
        for key in raw:
            if key not in allowed:
                errors.append(_issue(index, key, "unknown_field",
                                     f"{op} 不支持字段 {key!r}"))

        step: dict[str, Any] = {"op": op}
        if op == "move":
            point = _as_point(raw.get("x"), raw.get("y"), index,
                              required=True, errors=errors)
            if point is None:
                continue
            step.update(x=point[0], y=point[1])
            step["duration_ms"] = _as_int(raw.get("duration_ms"), index, "duration_ms",
                                          errors, default=0, minimum=0, maximum=5000)
            estimated += step["duration_ms"] or 0
        elif op == "click":
            point = _as_point(raw.get("x"), raw.get("y"), index,
                              required=False, errors=errors)
            if point is not None:
                step.update(x=point[0], y=point[1])
            button = raw.get("button", "left")
            if button not in BUTTONS:
                errors.append(_issue(index, "button", "invalid_button",
                                     f"button 必须是 {', '.join(BUTTONS)}"))
                button = "left"
            step["button"] = button
            step["clicks"] = _as_int(raw.get("clicks"), index, "clicks", errors,
                                     default=1, minimum=1, maximum=3)
            step["interval_ms"] = _as_int(raw.get("interval_ms"), index, "interval_ms",
                                          errors, default=80, minimum=0, maximum=1000)
            max_clicks = 3 if button == "left" else 2
            if step["clicks"] and step["clicks"] > max_clicks:
                errors.append(_issue(index, "clicks", "out_of_range",
                                     f"{button} 最多 {max_clicks} 次"))
            estimated += 40 + (step["clicks"] or 1) * (step["interval_ms"] or 80)
            anchored = True
        elif op == "drag":
            to = _as_point(raw.get("to_x"), raw.get("to_y"), index,
                           required=True, errors=errors)
            if to is None:
                continue
            start = _as_point(raw.get("from_x"), raw.get("from_y"), index,
                              required=False, errors=errors)
            if start is not None:
                step.update(from_x=start[0], from_y=start[1])
            step.update(to_x=to[0], to_y=to[1])
            button = raw.get("button", "left")
            if button not in BUTTONS:
                errors.append(_issue(index, "button", "invalid_button",
                                     f"button 必须是 {', '.join(BUTTONS)}"))
                button = "left"
            step["button"] = button
            step["duration_ms"] = _as_int(raw.get("duration_ms"), index, "duration_ms",
                                          errors, default=500, minimum=1, maximum=5000)
            estimated += step["duration_ms"] or 500
            anchored = True
        elif op == "scroll":
            direction = raw.get("direction", "down")
            if direction not in DIRECTIONS:
                errors.append(_issue(index, "direction", "invalid_direction",
                                     f"direction 必须是 {', '.join(DIRECTIONS)}"))
                direction = "down"
            step["direction"] = direction
            step["times"] = _as_int(raw.get("times"), index, "times", errors,
                                    default=3, minimum=1, maximum=10)
            estimated += 30
        elif op == "key":
            keys = raw.get("keys")
            if not isinstance(keys, str) or not keys.strip():
                errors.append(_issue(index, "keys", "missing", "keys 不能为空"))
            else:
                try:
                    step["keys"] = validate_keys(keys)
                except VirtualInputError as exc:
                    errors.append(_issue(index, "keys", "invalid_keys", str(exc)))
            step["ms"] = _as_int(raw.get("ms"), index, "ms", errors,
                                 default=0, minimum=0, maximum=5000)
            estimated += 30 + (step["ms"] or 0)
            if not anchored:
                errors.append(_issue(index, "keys", "no_target",
                                     "key 之前必须先有 click 或 drag，以绑定本链的目标窗口"))
        elif op == "type":
            if not anchored:
                errors.append(_issue(index, "text", "no_target",
                                     "type 之前必须先有 click 或 drag，以绑定本链的目标窗口"))
            text = raw.get("text")
            if not isinstance(text, str) or text == "":
                errors.append(_issue(index, "text", "missing", "text 不能为空"))
            elif len(text) > MAX_TEXT:
                errors.append(_issue(index, "text", "text_too_long",
                                     f"text 最多 {MAX_TEXT} 个字符"))
            else:
                step["text"] = text
            replace = raw.get("replace", True)
            if not isinstance(replace, bool):
                errors.append(_issue(index, "replace", "not_bool",
                                     "replace 必须是布尔值"))
                replace = True
            step["replace"] = replace
            estimated += 20 + min(len(text) if isinstance(text, str) else 0, 200) * 2
        elif op == "wait":
            step["ms"] = _as_int(raw.get("ms"), index, "ms", errors,
                                 default=0, minimum=0, maximum=MAX_WAIT_MS)
            estimated += step["ms"] or 0

        normalized.append(step)

    if estimated > timeout:
        errors.append(_issue(-1, "timeout_ms", "timeout_too_small",
                             f"预计 {estimated}ms，超过 timeout_ms={timeout}ms"))
    if len(steps) < RECOMMENDED_MIN or len(steps) > RECOMMENDED_MAX:
        warnings.append(_issue(-1, "steps", "length_hint",
                               f"建议 6-12 步，当前 {len(steps)} 步"))

    if errors:
        error = ValueError("chain validation failed")
        error.errors = errors  # type: ignore[attr-defined]
        raise error
    hint = None
    if warnings:
        hint = "建议把操作链拆成 6-12 步，便于失败后定位"
    return normalized, warnings, hint, estimated


def _execute(vp: Any, step: dict[str, Any]) -> dict[str, Any]:
    op = step["op"]
    if op == "move":
        vp.move(step["x"], step["y"], step["duration_ms"])
        return {"mode": "move"}
    if op == "click":
        return vp.click(step.get("x"), step.get("y"), step["button"],
                        step["clicks"], step["interval_ms"])
    if op == "drag":
        if "from_x" in step:
            from_x, from_y = step["from_x"], step["from_y"]
        else:
            from_x, from_y = vp.position()
        return vp.drag(from_x, from_y, step["to_x"], step["to_y"],
                       step["button"], step["duration_ms"])
    if op == "scroll":
        times = step["times"]
        direction = step["direction"]
        dy = times if direction == "up" else -times if direction == "down" else 0
        dx = times if direction == "right" else -times if direction == "left" else 0
        return vp.scroll(None, None, dy, dx)
    if op == "key":
        if step["ms"] > 0:
            return vp.key_hold(step["keys"], step["ms"])
        return vp.key_press(step["keys"])
    if op == "type":
        return vp.type_text(step["text"], step["replace"])
    if op == "wait":
        time.sleep(step["ms"] / 1000.0)
        return {"mode": "wait"}
    raise ChainStepError("unknown_op", f"不支持的操作: {op}")


def run_chain(
    steps: Any,
    *,
    pointer: int = 1,
    stop_on_error: bool = True,
    dry_run: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    chain_id: str | None = None,
    runtime: Any = None,
) -> dict[str, Any]:
    """Validate and execute a chain on one virtual pointer.

    Validation errors return ``{"ok": false, "code": "invalid_chain", ...}``
    with ``executed: 0``. Execution errors return per-step results and never
    raise. A caller-supplied ``chain_id`` is idempotent for 120 seconds.
    """
    if chain_id is not None:
        if (not isinstance(chain_id, str) or not chain_id.strip()
                or len(chain_id) > 64):
            return {"ok": False, "code": "invalid_argument",
                    "error": "chain_id 必须是 1-64 字符的字符串", "executed": 0,
                    "retry_safe": True}
        cached = _cache_get(chain_id)
        if cached is not None:
            return {**cached, "duplicate": True,
                    "hint": "相同 chain_id 已执行；返回上次结果，未重复操作"}
    base: dict[str, Any] = {
        "version": CHAIN_VERSION,
        "pointer": pointer,
        "dry_run": dry_run,
    }
    if chain_id:
        base["chain_id"] = chain_id

    if not isinstance(stop_on_error, bool):
        return {**base, "ok": False, "code": "invalid_argument",
                "error": "stop_on_error 必须是布尔值", "executed": 0}
    if not isinstance(dry_run, bool):
        return {**base, "ok": False, "code": "invalid_argument",
                "error": "dry_run 必须是布尔值", "executed": 0}

    try:
        normalized, warnings, hint, estimated = validate_chain(
            steps, pointer=pointer, timeout_ms=timeout_ms)
    except ValueError as exc:
        return {**base, "ok": False, "code": "invalid_chain",
                "error": "操作链校验失败", "executed": 0,
                "errors": getattr(exc, "errors", []), "retry_safe": True}

    pointer_id = validate_pointer(pointer)
    base["pointer"] = pointer_id
    base["timeout_ms"] = timeout_ms
    if dry_run:
        return {**base, "ok": True, "steps": len(normalized),
                "est_ms": estimated, "plan": normalized,
                "warnings": warnings, "hint": hint,
                "retry_safe": True}

    runtime = runtime or input_mod
    lock = pointer_lock(pointer_id)
    if not lock.acquire(blocking=False):
        return {**base, "ok": False, "code": "pointer_busy",
                "error": f"虚拟指针 {pointer_id} 正在执行另一条操作链",
                "executed": 0, "retry_safe": False}

    results: list[list[Any]] = []
    failures = 0
    stopped_at: int | None = None
    status = "done"
    error_message: str | None = None
    started = time.perf_counter()
    deadline = started + timeout_ms / 1000.0
    vp = None
    try:
        vp = runtime.pointer(pointer_id)
        for index, step in enumerate(normalized):
            if time.perf_counter() > deadline:
                status = "timeout"
                error_message = f"操作链超过 {timeout_ms}ms"
                break
            step_started = time.perf_counter()
            code: str | None = None
            message: str | None = None
            try:
                result = _execute(vp, step)
                if result.get("delivered") is False:
                    raise ChainStepError("post_failed",
                                         "目标窗口未接收定向消息")
            except ChainStepError as exc:
                code, message = exc.code, exc.message
            except VirtualInputError as exc:
                code, message = "step_error", str(exc)
            except OacuError as exc:
                code, message = "step_error", exc.message
            except Exception as exc:  # noqa: BLE001 - chain must report
                code, message = "internal", f"{type(exc).__name__}: {exc}"
            elapsed = int((time.perf_counter() - step_started) * 1000)
            ok = code is None
            results.append([index, step["op"], ok, elapsed, code])
            if not ok:
                failures += 1
                stopped_at = index
                if error_message is None:
                    error_message = message
                if stop_on_error:
                    status = "stopped"
                    break
                status = "partial"
    finally:
        lock.release()

    state = None
    if vp is not None:
        try:
            state = {"x": vp.x, "y": vp.y, "hwnd": vp.last_hwnd}
        except Exception:  # noqa: BLE001 - state is best effort
            state = None

    executed = len(results)
    payload: dict[str, Any] = {
        **base,
        "ok": status == "done",
        "status": status,
        "steps": len(normalized),
        "executed": executed,
        "partial": bool(failures and status != "stopped"),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "results": results,
        "retry_safe": False,
    }
    if stopped_at is not None and executed < len(normalized):
        payload["stopped_at"] = stopped_at
        payload["resume_from"] = stopped_at + 1
    elif status == "timeout" and executed < len(normalized):
        payload["resume_from"] = executed
    if error_message:
        payload["error"] = error_message
    if state:
        payload["state"] = state
    if warnings:
        payload["warnings"] = warnings
    if status == "done":
        payload["hint"] = (hint + "；" if hint else "") + "用 desktop_scan(diff=true) 或截图验证结果"
    elif executed:
        payload["hint"] = ("不要重发整链；若剩余步骤以 key/type 开头，"
                           "先补 click/drag 重新绑定目标窗口，再重发剩余步骤")
    if chain_id:
        _cache_put(chain_id, payload)
    return payload
