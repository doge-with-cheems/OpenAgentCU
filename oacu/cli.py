"""Command line interface for OpenAgentCU."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Any

from . import __version__
from .config import Settings, ensure_dirs, home_dir, settings_from_args
from .errors import OacuError

COMMANDS = ("scan", "dump", "plan", "act", "exec", "serve", "mcp", "doctor", "gui", "input")


def _add_common(parser: argparse.ArgumentParser, *, suppress: bool = True) -> None:
    """Common options. On subparsers defaults are suppressed so global values win."""
    default: Any = argparse.SUPPRESS if suppress else None
    parser.add_argument("--json", action="store_true", default=default, help="machine readable output")
    parser.add_argument("--db", default=default, help="path to oacu.db")
    parser.add_argument("--backend", choices=("auto", "ps", "uia", "fake"), default=default,
                        help="UIA backend (default: auto)")
    parser.add_argument("--timeout", type=float, default=default, help="execution timeout seconds")
    parser.add_argument("--verbose", "-v", action="store_true", default=default, help="verbose diagnostics")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oacu",
        description="OpenAgentCU: Windows desktop perception + UIA action bridge",
    )
    parser.add_argument("--version", action="version", version=f"oacu {__version__}")
    _add_common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    common = argparse.ArgumentParser(add_help=False)
    _add_common(common)

    p_scan = sub.add_parser("scan", parents=[common], help="capture desktop, tokenize and store a snapshot")
    p_scan.add_argument("--raw", action="store_true", help="print raw elements instead of tokens")
    p_scan.add_argument("--window", default=None, help="only elements under this window title")
    p_scan.add_argument("--max-depth", type=int, default=None)
    p_scan.add_argument("--max-elements", type=int, default=None)
    p_scan.add_argument("--no-store", action="store_true", help="do not write to the database")
    p_scan.add_argument("--fixture", default=None, help="JSON fixture for --backend fake")
    p_scan.set_defaults(func=cmd_scan)

    p_dump = sub.add_parser("dump", parents=[common], help="print the latest stored snapshot")
    p_dump.add_argument("--limit", type=int, default=10)
    p_dump.add_argument("--snapshot", type=int, default=None)
    p_dump.add_argument("--text", action="store_true", help="print token text instead of JSON")
    p_dump.set_defaults(func=cmd_dump)

    p_plan = sub.add_parser("plan", parents=[common], help="compile an instruction into a plan + IR (no execution)")
    p_plan.add_argument("instruction")
    p_plan.add_argument("--window", default=None)
    p_plan.add_argument("--max-age", type=float, default=None)
    p_plan.add_argument("--fixture", default=None, help="JSON fixture for --backend fake")
    p_plan.set_defaults(func=cmd_plan)

    p_act = sub.add_parser("act", parents=[common], help="run one instruction end to end")
    p_act.add_argument("instruction")
    p_act.add_argument("--window", default=None)
    p_act.add_argument("--dry-run", action="store_true", help="plan only, never touch mouse/keyboard")
    p_act.add_argument("--inproc", action="store_true", help="execute inside this process (no daemon)")
    p_act.add_argument("--max-age", type=float, default=None)
    p_act.add_argument("--fixture", default=None, help="JSON fixture for --backend fake")
    p_act.add_argument("--host", default=None)
    p_act.add_argument("--port", type=int, default=None)
    p_act.set_defaults(func=cmd_act)

    p_exec = sub.add_parser("exec", parents=[common], help="execute an IR file")
    p_exec.add_argument("ir_file")
    p_exec.add_argument("--inproc", action="store_true")
    p_exec.add_argument("--host", default=None)
    p_exec.add_argument("--port", type=int, default=None)
    p_exec.set_defaults(func=cmd_exec)

    p_serve = sub.add_parser("serve", parents=[common], help="run the local interpreter daemon")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_mcp = sub.add_parser("mcp", parents=[common], help="MCP server mode")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_command", metavar="<action>")
    p_mcp_serve = mcp_sub.add_parser("serve", parents=[common], help="serve MCP over stdio")
    p_mcp_serve.set_defaults(func=cmd_mcp)

    p_doctor = sub.add_parser("doctor", parents=[common], help="check environment and backend availability")
    p_doctor.set_defaults(func=cmd_doctor)

    p_gui = sub.add_parser("gui", parents=[common], help="open the desktop GUI shell")
    p_gui.add_argument("--fixture", default=None, help="JSON fixture for --backend fake")
    p_gui.add_argument("--tab", type=int, choices=(0, 1, 2, 3, 4), default=0,
                       help="initial tab: 0 snapshot, 1 instruction, 2 records, 3 mcp, 4 input")
    p_gui.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    p_gui.set_defaults(func=cmd_gui)

    p_overlay = sub.add_parser("overlay", parents=[common], help=argparse.SUPPRESS)
    p_overlay.set_defaults(func=cmd_overlay)
    # argparse still lists SUPPRESS'd subcommands; drop the pseudo-action to keep it hidden.
    sub._choices_actions = [a for a in sub._choices_actions
                           if getattr(a, "dest", None) != "overlay"]

    p_input = sub.add_parser("input", parents=[common], help="direct mouse and keyboard control")
    input_sub = p_input.add_subparsers(dest="input_action", metavar="<action>")

    p_move = input_sub.add_parser("move", parents=[common], help="move the mouse")
    p_move.add_argument("--x", type=int, required=True)
    p_move.add_argument("--y", type=int, required=True)
    p_move.add_argument("--duration-ms", type=int, default=0)
    p_move.set_defaults(func=cmd_input)

    p_click = input_sub.add_parser("click", parents=[common], help="click the mouse")
    p_click.add_argument("--x", type=int, default=None)
    p_click.add_argument("--y", type=int, default=None)
    p_click.add_argument("--button", choices=("left", "right", "middle"), default="left")
    p_click.add_argument("--clicks", type=int, default=1)
    p_click.add_argument("--interval-ms", type=int, default=80)
    p_click.set_defaults(func=cmd_input)

    p_drag = input_sub.add_parser("drag", parents=[common], help="drag the mouse")
    p_drag.add_argument("--from-x", type=int, required=True)
    p_drag.add_argument("--from-y", type=int, required=True)
    p_drag.add_argument("--to-x", type=int, required=True)
    p_drag.add_argument("--to-y", type=int, required=True)
    p_drag.add_argument("--button", choices=("left", "right", "middle"), default="left")
    p_drag.add_argument("--duration-ms", type=int, default=500)
    p_drag.set_defaults(func=cmd_input)

    p_scroll = input_sub.add_parser("scroll", parents=[common], help="scroll the mouse wheel")
    p_scroll.add_argument("--x", type=int, default=None)
    p_scroll.add_argument("--y", type=int, default=None)
    p_scroll.add_argument("--dy", type=int, default=3, help="vertical notches (positive = up)")
    p_scroll.add_argument("--dx", type=int, default=0, help="horizontal notches")
    p_scroll.set_defaults(func=cmd_input)

    p_key = input_sub.add_parser("key", parents=[common], help="press, hold or release keys")
    key_mode = p_key.add_mutually_exclusive_group(required=True)
    key_mode.add_argument("--press", metavar="KEYS")
    key_mode.add_argument("--down", metavar="KEYS")
    key_mode.add_argument("--up", metavar="KEYS")
    key_mode.add_argument("--hold", metavar="KEYS")
    p_key.add_argument("--ms", type=int, default=500)
    p_key.set_defaults(func=cmd_input)

    p_type = input_sub.add_parser("type", parents=[common], help="type text into the focused control")
    p_type.add_argument("text")
    p_type.set_defaults(func=cmd_input)

    p_winrun = input_sub.add_parser("winrun", parents=[common], help="ShellExecute app/path/URL (virtual Win+R replacement)")
    p_winrun.add_argument("command")
    p_winrun.add_argument("--wait-ms", type=int, default=350)
    p_winrun.set_defaults(func=cmd_input)

    p_pos = input_sub.add_parser("pos", parents=[common], help="print the mouse position")
    p_pos.set_defaults(func=cmd_input)

    p_screen = input_sub.add_parser("screen", parents=[common], help="print the virtual screen bounds")
    p_screen.set_defaults(func=cmd_input)

    return parser


def _emit(settings: Settings, payload: dict[str, Any]) -> None:
    if settings.json:
        text = json.dumps(payload, ensure_ascii=False)
    else:
        text = payload.get("text") or json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)


def _fail(settings: Settings, err: OacuError) -> int:
    payload: dict[str, Any] = {"ok": False, "error": err.message, "code": err.code}
    if err.detail:
        payload["detail"] = err.detail
    if settings.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"error: {err.message}", file=sys.stderr)
        if err.detail:
            print(err.detail, file=sys.stderr)
    return err.code


def cmd_scan(args: argparse.Namespace, settings: Settings) -> int:
    from .store import Store
    from .tokens import build_snapshot
    from .uia.collector import capture
    from .uia.normalize import normalize
    from .uia.order import order_elements

    cfg = settings.config
    max_depth = args.max_depth if args.max_depth is not None else int(cfg.get("max_depth", 12))
    max_elements = args.max_elements if args.max_elements is not None else int(cfg.get("max_elements", 3000))
    result = capture(
        backend=settings.backend,
        max_depth=max_depth,
        max_elements=max_elements,
        window=args.window,
        fixture=args.fixture,
    )
    if args.raw:
        payload = {
            "ok": True,
            "count": len(result.elements),
            "meta": result.meta,
            "elements": [
                {
                    "name": e.name,
                    "control_type": e.control_type,
                    "rect": list(e.rect),
                    "automation_id": e.automation_id,
                    "class_name": e.class_name,
                    "parent": e.parent,
                    "depth": e.depth,
                    "enabled": e.enabled,
                    "offscreen": e.offscreen,
                }
                for e in result.elements
            ],
        }
        _emit(settings, payload)
        return 0

    elements, nstats = normalize(result.elements, window=args.window)
    ordered = order_elements(elements)
    screen = tuple(result.meta.get("screen") or (0, 0))
    snapshot = build_snapshot(ordered, screen=(int(screen[0]), int(screen[1])), stats=nstats.to_dict())

    snapshot_id = None
    if not args.no_store:
        store = Store(settings.db)
        try:
            snapshot_id = store.save_snapshot(snapshot, keep=int(cfg.get("snapshot_keep", 20)))
        finally:
            store.close()

    preview = "\n".join(snapshot.text.splitlines()[:10])
    header = (
        f"snapshot {snapshot_id}: {len(snapshot.tokens)} tokens, "
        f"{len(snapshot.window)} windows, dropped {nstats.dropped}"
    )
    payload = {
        "ok": True,
        "snapshot_id": snapshot_id,
        "count": len(snapshot.tokens),
        "windows": snapshot.window,
        "stats": snapshot.stats,
        "meta": result.meta,
        "preview": snapshot.text.splitlines()[:10],
        "text": header + ("\n" + preview if preview else ""),
    }
    _emit(settings, payload)
    return 0


def cmd_dump(args: argparse.Namespace, settings: Settings) -> int:
    from .errors import NoSnapshot
    from .store import Store

    store = Store(settings.db)
    try:
        record = store.get_snapshot(args.snapshot) if args.snapshot else store.latest_snapshot()
        if record is None:
            raise NoSnapshot()
        if args.text:
            payload = {"ok": True, "snapshot_id": record.id, "text": record.text}
        else:
            tokens = store.get_tokens(record.id)
            if args.limit and args.limit > 0:
                tokens = tokens[: args.limit]
            payload = {
                "ok": True,
                **record.to_dict(),
                "tokens": [
                    {
                        "id": token.id,
                        "name": token.name,
                        "ctype": token.ctype,
                        "rect": list(token.rect),
                        "relations": token.relations,
                        "order": token.order,
                    }
                    for token in tokens
                ],
            }
            payload["text"] = (
                f"snapshot {record.id}: {record.token_count} tokens, "
                f"created {record.created_at}"
            )
    finally:
        store.close()
    _emit(settings, payload)
    return 0


def cmd_plan(args: argparse.Namespace, settings: Settings) -> int:
    from .agent import build_plan_only

    result = build_plan_only(
        args.instruction,
        settings,
        window=args.window,
        max_age_s=args.max_age,
        fixture=args.fixture,
    )
    if not settings.json:
        result["text"] = _format_plan(result)
    _emit(settings, result)
    return 0


def _format_plan(result: dict[str, Any]) -> str:
    lines = [f"trace {result['trace_id']}  snapshot {result['snapshot_id']}"]
    for index, step in enumerate(result["plan"]["steps"], start=1):
        target = step.get("token_name") or step.get("token_id") or "-"
        extra = f" = {step['value']}" if step.get("value") else ""
        lines.append(f"{index}. {step['op']:<12} {target}{extra}")
    lines.append(f"IR: {len(result['ir']['steps'])} steps")
    return "\n".join(lines)


def cmd_act(args: argparse.Namespace, settings: Settings) -> int:
    from .agent import run_act

    result = run_act(
        args.instruction,
        settings,
        window=args.window,
        max_age_s=args.max_age,
        dry_run=args.dry_run,
        fixture=args.fixture,
        inproc=args.inproc,
        host=args.host,
        port=args.port,
    )
    if settings.json:
        payload = {k: v for k, v in result.items() if k not in ("plan", "ir", "results")}
        payload["results"] = result.get("results", [])
        _emit(settings, payload)
    else:
        if args.dry_run:
            print(f"trace {result['trace_id']}: dry-run, snapshot {result['snapshot_id']}, "
                  f"{result['tokens']} tokens")
        else:
            print(f"trace {result['trace_id']}: {result['status']}")
            for item in result.get("results", []):
                mark = "ok" if item.get("ok") else "FAIL"
                print(f"  [{mark}] {item.get('index')}. {item.get('op')} ({item.get('ms')} ms)")
    return 0 if result.get("ok") else 1


def cmd_exec(args: argparse.Namespace, settings: Settings) -> int:
    from .interpreter import execute
    from .ir import load_ir
    from .store import Store
    from .transport import send_ir

    ir = load_ir(args.ir_file)
    if args.inproc:
        store = Store(settings.db)
        try:
            results = execute(ir, store=store, settings=settings)
        finally:
            store.close()
    else:
        results = send_ir(
            ir,
            host=args.host or str(settings.config.get("host", "127.0.0.1")),
            port=args.port or int(settings.config.get("port", 8765)),
            timeout=settings.timeout,
        )
    failures = [item for item in results if not item.get("ok")]
    payload = {
        "ok": not failures,
        "trace_id": ir.get("trace_id"),
        "results": results,
    }
    if not settings.json:
        payload["text"] = "\n".join(
            f"{'ok' if item.get('ok') else 'FAIL'} {item.get('index')}. {item.get('op')} ({item.get('ms')} ms)"
            + (f"  {item.get('error')}" if item.get("error") else "")
            for item in results
        )
    _emit(settings, payload)
    return 0 if not failures else 1


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    from .store import Store
    from .transport import serve_forever

    host = args.host or str(settings.config.get("host", "127.0.0.1"))
    port = args.port or int(settings.config.get("port", 8765))
    store = Store(settings.db)
    store.connect()
    print(f"oacu interpreter listening on {host}:{port}", file=sys.stderr, flush=True)
    try:
        serve_forever(host, port, store, settings)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()
    return 0


def cmd_mcp(args: argparse.Namespace, settings: Settings) -> int:
    from .mcp.server import serve_stdio
    from .store import Store

    store = Store(settings.db)
    store.connect()
    try:
        return serve_stdio(store, settings)
    finally:
        store.close()


def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    from .uia import backend as backend_mod

    info = backend_mod.probe()
    ensure_dirs()
    db_writable = False
    probe_file = home_dir() / f".write_probe_{os.getpid()}"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        db_writable = True
    except OSError:
        db_writable = False
    finally:
        try:
            probe_file.unlink()
        except OSError:
            pass

    registry_ok = False
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\OpenAgentCU\Doctor")
        winreg.SetValueEx(key, "ok", 0, winreg.REG_SZ, "1")
        winreg.CloseKey(key)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\OpenAgentCU\Doctor")
        registry_ok = True
    except OSError:
        registry_ok = False
    try:
        import ctypes

        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        is_admin = False

    ok = bool(info["ps_uia"] or info["pywinauto"])
    payload = {
        "ok": ok,
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "home": str(home_dir()),
        "db": str(settings.db),
        "db_writable": db_writable,
        "registry_writable": registry_ok,
        "is_admin": is_admin,
        **info,
    }
    if not settings.json:
        lines = [
            f"oacu {__version__} on Python {payload['python']}",
            f"platform      : {payload['platform']}",
            f"home          : {payload['home']}",
            f"db            : {payload['db']} (writable={db_writable})",
            f"registry      : writable={registry_ok}  elevated={is_admin}",
            f"powershell    : {info['powershell'] or 'not found'}",
            f"powershell UIA: {info['ps_uia']}",
            f"pywinauto     : {info['pywinauto']}",
            f"backend       : {info['backend'] or 'none'}",
        ]
        payload["text"] = "\n".join(lines)
    _emit(settings, payload)
    return 0 if ok else 3


def cmd_input(args: argparse.Namespace, settings: Settings) -> int:
    from . import input as input_mod

    action = args.input_action
    if action == "screen":
        payload = input_mod.screen_info()
        summary = (f"screen {payload['width']}x{payload['height']} "
                   f"at {payload['x']},{payload['y']}")
    elif action == "pos":
        x, y = input_mod.mouse_position()
        payload = {"x": x, "y": y}
        summary = f"mouse at {x},{y}"
    elif action == "move":
        x, y = input_mod.move(args.x, args.y, args.duration_ms)
        payload = {"x": x, "y": y}
        summary = f"mouse moved to {x},{y}"
    elif action == "click":
        payload = input_mod.click(args.x, args.y, args.button, args.clicks, args.interval_ms)
        summary = f"clicked {payload['button']} x{payload['clicks']} at {payload['x']},{payload['y']}"
    elif action == "drag":
        payload = input_mod.drag(args.from_x, args.from_y, args.to_x, args.to_y,
                                 args.button, args.duration_ms)
        summary = f"dragged {args.from_x},{args.from_y} -> {args.to_x},{args.to_y}"
    elif action == "scroll":
        payload = input_mod.scroll(args.x, args.y, args.dy, args.dx)
        summary = f"scrolled dy={payload['dy']} dx={payload['dx']} at {payload['x']},{payload['y']}"
    elif action == "key":
        if args.press is not None:
            payload = input_mod.key_press(args.press)
        elif args.down is not None:
            payload = input_mod.key_down(args.down)
        elif args.up is not None:
            payload = input_mod.key_up(args.up)
        else:
            payload = input_mod.key_hold(args.hold, args.ms)
        summary = f"{payload['mode']} {payload['keys']}"
    elif action == "type":
        payload = input_mod.type_text(args.text)
        summary = f"typed {payload['chars']} chars"
    elif action == "winrun":
        payload = input_mod.win_run(args.command, args.wait_ms)
        summary = f"virtual launch: {payload['command']}"
    else:
        from .errors import UsageError

        raise UsageError("缺少 input 子命令，例如: oacu input screen")

    payload = {"ok": True, **payload, "text": summary}
    _emit(settings, payload)
    return 0


def cmd_overlay(args: argparse.Namespace, settings: Settings) -> int:
    from .overlay import main as overlay_main

    return overlay_main()


def cmd_gui(args: argparse.Namespace, settings: Settings) -> int:
    try:
        from .gui import run_gui
    except ImportError as exc:
        from .errors import EnvUnavailable

        raise EnvUnavailable("tkinter 不可用，无法打开图形界面", detail=str(exc)) from exc
    return run_gui(settings, fixture=args.fixture, self_test=args.self_test,
                   start_tab=args.tab)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    settings = settings_from_args(args)
    try:
        return int(args.func(args, settings) or 0)
    except OacuError as err:
        return _fail(settings, err)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
