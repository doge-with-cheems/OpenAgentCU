"""Single-round agent orchestration."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Callable

from .config import Settings
from .context import Context, get_context
from .errors import NoSnapshot, UsageError
from .pipeline import capture_snapshot
from .store import Store, age_seconds

MAX_INSTRUCTION = 2000


def new_trace_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def _refresher(settings: Settings, window: str | None, fixture: str | None):
    def refresh():
        return capture_snapshot(
            backend=settings.backend,
            window=window,
            max_depth=int(settings.config.get("max_depth", 12)),
            max_elements=int(settings.config.get("max_elements", 3000)),
            fixture=fixture,
        )

    return refresh


def _validate(instruction: str) -> str:
    text = (instruction or "").strip()
    if not text:
        raise UsageError("指令不能为空")
    if len(text) > MAX_INSTRUCTION:
        raise UsageError(f"指令过长（{len(text)} > {MAX_INSTRUCTION} 字）")
    return text


def _load_context(store: Store, settings: Settings, trace_id: str, *,
                  window: str | None, max_age_s: float | None,
                  fixture: str | None) -> Context:
    age_limit = float(max_age_s if max_age_s is not None else settings.config.get("max_age_s", 30))
    context = get_context(
        store,
        window=window,
        max_age_s=age_limit,
        refresh=_refresher(settings, window, fixture),
    )
    store.update_action(trace_id, status="context", snapshot_id=context.snapshot_id)
    return context


def run_act(
    instruction: str,
    settings: Settings,
    *,
    store: Store | None = None,
    window: str | None = None,
    max_age_s: float | None = None,
    dry_run: bool = False,
    fixture: str | None = None,
    executor: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    inproc: bool = True,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    text = _validate(instruction)
    own_store = store is None
    store = store or Store(settings.db)
    trace_id = new_trace_id()
    try:
        store.record_action(trace_id, text)
        try:
            context = _load_context(store, settings, trace_id, window=window,
                                    max_age_s=max_age_s, fixture=fixture)

            result: dict[str, Any] = {
                "ok": True,
                "trace_id": trace_id,
                "status": "dry_run" if dry_run else "context",
                "snapshot_id": context.snapshot_id,
                "tokens": len(context.tokens),
                "refreshed": context.refreshed,
                "dry_run": dry_run,
                "instruction": text,
            }
            if dry_run:
                store.update_action(trace_id, status="dry_run", snapshot_id=context.snapshot_id)
                return result

            from . import ir as ir_mod
            from . import planner

            plan = planner.make_plan(text, context.tokens)
            ir = ir_mod.build_ir(plan, snapshot_id=context.snapshot_id, trace_id=trace_id,
                                 interval_ms=int(settings.config.get("step_interval_ms", 120)))
            ir_mod.validate_ir(ir)
            ir_path = ir_mod.write_ir(ir, trace_id)
            store.update_action(trace_id, status="planned", snapshot_id=context.snapshot_id,
                                plan=plan.to_dict(), ir=ir)
            result.update({"status": "planned", "plan": plan.to_dict(), "ir": ir,
                           "ir_path": str(ir_path), "steps": len(ir["steps"])})

            if executor is None:
                if inproc:
                    from .interpreter import execute as execute_ir

                    results = execute_ir(ir, store=store, settings=settings)
                else:
                    from .transport import send_ir

                    results = send_ir(ir, host=host or str(settings.config.get("host", "127.0.0.1")),
                                      port=port or int(settings.config.get("port", 8765)),
                                      timeout=settings.timeout)
            else:
                results = executor(ir)

            failures = [item for item in results if not item.get("ok")]
            status = "error" if failures else "ok"
            error = None
            if failures:
                first = failures[0]
                error = f"step {first.get('index')} {first.get('op')}: {first.get('error')}"
            store.update_action(trace_id, status=status, error=error,
                                snapshot_id=context.snapshot_id, plan=plan.to_dict(), ir=ir)
            result.update({"status": status, "results": results, "ok": not failures})
            if failures:
                result["error"] = error
            return result
        except (UsageError, NoSnapshot):
            store.update_action(trace_id, status="error", error="usage or snapshot error")
            raise
        except Exception as exc:
            store.update_action(trace_id, status="error", error=f"{type(exc).__name__}: {exc}")
            raise
    finally:
        if own_store:
            store.close()


def build_plan_only(
    instruction: str,
    settings: Settings,
    *,
    store: Store | None = None,
    window: str | None = None,
    max_age_s: float | None = None,
    fixture: str | None = None,
) -> dict[str, Any]:
    text = _validate(instruction)
    own_store = store is None
    store = store or Store(settings.db)
    trace_id = new_trace_id()
    try:
        store.record_action(trace_id, text)
        context = _load_context(store, settings, trace_id, window=window,
                                max_age_s=max_age_s, fixture=fixture)
        from . import ir as ir_mod
        from . import planner

        plan = planner.make_plan(text, context.tokens)
        ir = ir_mod.build_ir(plan, snapshot_id=context.snapshot_id, trace_id=trace_id,
                             interval_ms=int(settings.config.get("step_interval_ms", 120)))
        ir_mod.validate_ir(ir)
        store.update_action(trace_id, status="planned", snapshot_id=context.snapshot_id,
                            plan=plan.to_dict(), ir=ir)
        return {
            "ok": True,
            "trace_id": trace_id,
            "snapshot_id": context.snapshot_id,
            "plan": plan.to_dict(),
            "ir": ir,
        }
    except Exception as exc:
        store.update_action(trace_id, status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if own_store:
            store.close()


def context_age(created_at: str) -> float:
    return age_seconds(created_at)
