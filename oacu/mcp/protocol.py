"""Minimal MCP (Model Context Protocol) JSON-RPC 2.0 implementation."""

from __future__ import annotations

import json
from typing import Any

from .. import __version__
from ..config import Settings
from ..errors import OacuError
from ..store import Store
from .compact import FIELDS, diff_tokens, is_noise, removed_table, token_table

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "opencu"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": True,
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "desktop_scan",
            "description": "Capture the desktop and return a compact token table (id|name|type|x|y|w|h|win).",
            "inputSchema": _schema({
                "window": {"type": "string", "description": "only keep tokens under this window title"},
                "max_elements": {"type": "integer", "minimum": 1, "default": 3000},
                "limit": {"type": "integer", "minimum": 0, "default": 80,
                          "description": "max token rows to return (0 = all); use desktop_find for a specific element"},
                "diff": {"type": "boolean", "default": False,
                         "description": "only return added/removed tokens compared with the latest snapshot"},
                "fixture": {"type": "string", "description": "test fixture (backend=fake only)"},
            }),
        },
        {
            "name": "desktop_tokens",
            "description": "Return a page of the latest token table (compact, no duplicate text).",
            "inputSchema": _schema({
                "limit": {"type": "integer", "minimum": 0, "default": 20},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            }),
        },
        {
            "name": "desktop_find",
            "description": "Find elements in the latest snapshot by name; returns only matches (much cheaper than a full scan).",
            "inputSchema": _schema({
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 8},
            }, required=["query"]),
        },
        {
            "name": "desktop_summary",
            "description": "Return only the latest snapshot summary: windows, counts and timestamps.",
            "inputSchema": _schema({}),
        },
        {
            "name": "launch_app",
            "description": "Launch an application by name/path (no desktop scan needed).",
            "inputSchema": _schema({
                "app": {"type": "string"},
                "wait_ms": {"type": "integer", "minimum": 0, "default": 800},
            }, required=["app"]),
        },
        {
            "name": "open_url",
            "description": "Open a URL in the default browser (no desktop scan needed).",
            "inputSchema": _schema({
                "url": {"type": "string"},
                "wait_ms": {"type": "integer", "minimum": 0, "default": 500},
            }, required=["url"]),
        },
        {
            "name": "search_web",
            "description": "Open a search results page (google/bing/youtube) without scanning the desktop.",
            "inputSchema": _schema({
                "query": {"type": "string"},
                "engine": {"type": "string", "enum": ["google", "bing", "youtube"], "default": "google"},
                "wait_ms": {"type": "integer", "minimum": 0, "default": 500},
            }, required=["query"]),
        },
        {
            "name": "win_run",
            "description": "Open Win+R, type a command and press Enter (no desktop scan needed).",
            "inputSchema": _schema({
                "command": {"type": "string"},
                "wait_ms": {"type": "integer", "minimum": 0, "default": 350},
            }, required=["command"]),
        },
        {
            "name": "computer_act",
            "description": "Plan and execute one natural-language desktop instruction in a single round.",
            "inputSchema": _schema({
                "instruction": {"type": "string"},
                "window": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "verbose": {"type": "boolean", "default": False,
                            "description": "include plan/IR in the result (debugging only)"},
                "fixture": {"type": "string"},
            }, required=["instruction"]),
        },
        {
            "name": "mouse_move",
            "description": "Move the mouse cursor to absolute virtual-screen coordinates.",
            "inputSchema": _schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration_ms": {"type": "integer", "minimum": 0, "default": 0},
            }, required=["x", "y"]),
        },
        {
            "name": "mouse_click",
            "description": "Click the mouse at coordinates (or at the current position).",
            "inputSchema": _schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "minimum": 1, "default": 1},
                "interval_ms": {"type": "integer", "minimum": 0, "default": 80},
            }),
        },
        {
            "name": "mouse_drag",
            "description": "Press a mouse button at the start point, move to the end point and release.",
            "inputSchema": _schema({
                "from_x": {"type": "integer"},
                "from_y": {"type": "integer"},
                "to_x": {"type": "integer"},
                "to_y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "duration_ms": {"type": "integer", "minimum": 1, "default": 500},
            }, required=["from_x", "from_y", "to_x", "to_y"]),
        },
        {
            "name": "mouse_scroll",
            "description": "Scroll the wheel at coordinates (or at the current position).",
            "inputSchema": _schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "dy": {"type": "integer", "default": 3},
                "dx": {"type": "integer", "default": 0},
            }),
        },
        {
            "name": "key_press",
            "description": "Press and release keys, e.g. 'win', 'ctrl+s', 'enter'.",
            "inputSchema": _schema({
                "keys": {"type": "string"},
            }, required=["keys"]),
        },
        {
            "name": "key_hold",
            "description": "Hold keys for a duration, then release.",
            "inputSchema": _schema({
                "keys": {"type": "string"},
                "ms": {"type": "integer", "minimum": 0, "default": 500},
            }, required=["keys"]),
        },
        {
            "name": "type_text",
            "description": "Type Unicode text into the currently focused control.",
            "inputSchema": _schema({
                "text": {"type": "string"},
            }, required=["text"]),
        },
        {
            "name": "screen_info",
            "description": "Return virtual screen bounds and primary display size.",
            "inputSchema": _schema({}),
        },
        {
            "name": "mouse_position",
            "description": "Return the current mouse cursor coordinates.",
            "inputSchema": _schema({}),
        },
    ]


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _render_tool_content(name: str, payload: dict[str, Any]) -> str:
    if not payload.get("ok", True):
        return json.dumps(payload, ensure_ascii=False)
    if name == "desktop_scan":
        header = (f"snapshot #{payload.get('snapshot_id')}: {payload.get('token_count')} tokens, "
                  f"{len(payload.get('windows') or [])} windows ({payload.get('mode')})")
        if payload.get("mode") == "diff":
            return (header + "\nadded:\n" + (payload.get("added") or "(none)")
                    + "\nremoved:\n" + (payload.get("removed") or "(none)"))
        header += f"\nshown: {payload.get('shown')}/{payload.get('token_count')}"
        text = header + "\nfields: " + "|".join(FIELDS) + "\n" + (payload.get("tokens") or "")
        if payload.get("shown", 0) < payload.get("token_count", 0):
            text += (f"\n(more rows: desktop_tokens(offset={payload.get('shown')}) "
                     f"or desktop_find(query))")
        return text
    if name == "desktop_tokens":
        header = (f"snapshot #{payload.get('snapshot_id')}: "
                  f"{payload.get('returned')}/{payload.get('total')} tokens "
                  f"(offset {payload.get('offset')})")
        return header + "\nfields: " + "|".join(FIELDS) + "\n" + (payload.get("tokens") or "")
    if name == "desktop_find":
        header = (f"snapshot #{payload.get('snapshot_id')}: {payload.get('matches')} matches "
                  f"for {payload.get('query')!r} ({payload.get('total')} candidates)")
        return header + "\nfields: " + "|".join(FIELDS) + "\n" + (payload.get("tokens") or "")
    if name == "desktop_summary":
        return (f"snapshot #{payload.get('snapshot_id')}: {payload.get('token_count')} tokens\n"
                f"windows: {json.dumps(payload.get('windows') or [], ensure_ascii=False)}\n"
                f"created_at: {payload.get('created_at')}")
    return json.dumps(payload, ensure_ascii=False)


def _tool_desktop_scan(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from ..pipeline import capture_snapshot

    window = arguments.get("window")
    old = store.latest_snapshot(window)
    old_tokens = store.get_tokens(old.id) if old is not None else []

    snapshot = capture_snapshot(
        backend=settings.backend,
        window=window,
        max_elements=int(arguments.get("max_elements") or settings.config.get("max_elements", 3000)),
        fixture=arguments.get("fixture"),
    )
    snapshot_id = store.save_snapshot(snapshot, keep=int(settings.config.get("snapshot_keep", 20)))

    visible = [token for token in snapshot.tokens if not is_noise(token)]
    payload: dict[str, Any] = {
        "ok": True,
        "snapshot_id": snapshot_id,
        "token_count": len(visible),
        "raw_token_count": len(snapshot.tokens),
        "windows": snapshot.window,
        "mode": "full",
    }

    if arguments.get("diff") and old is not None:
        added, removed = diff_tokens(old_tokens, snapshot.tokens)
        if len(added) + len(removed) <= max(20, len(snapshot.tokens) // 2):
            payload.update({
                "mode": "diff",
                "changed": bool(added or removed),
                "added": token_table(added, snapshot.window),
                "removed": removed_table(removed, old.window),
                "removed_fields": ["name", "type", "x", "y", "w", "h", "win"],
            })
            return payload

    limit = int(arguments.get("limit", 80))
    if limit < 0:
        limit = 80
    selected = visible if limit == 0 else visible[:limit]
    payload["total"] = len(visible)
    payload["shown"] = len(selected)
    payload["fields"] = FIELDS
    payload["tokens"] = token_table(selected, snapshot.window)
    return payload


def _tool_desktop_tokens(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    record = store.latest_snapshot()
    if record is None:
        return {"ok": False, "error": "no snapshot; call desktop_scan first"}
    tokens = [token for token in store.get_tokens(record.id) if not is_noise(token)]
    total = len(tokens)
    offset = max(0, int(arguments.get("offset", 0)))
    limit = int(arguments.get("limit", 20))
    if limit < 0:
        limit = 20
    selected = tokens[offset:] if limit == 0 else tokens[offset:offset + limit]
    return {
        "ok": True,
        "snapshot_id": record.id,
        "created_at": record.created_at,
        "windows": record.window,
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(selected),
        "fields": FIELDS,
        "tokens": token_table(selected, record.window),
    }


def _tool_desktop_find(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    import difflib

    record = store.latest_snapshot()
    if record is None:
        return {"ok": False, "error": "no snapshot; call desktop_scan first"}
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is empty"}
    limit = max(1, min(30, int(arguments.get("limit", 8))))
    needle = query.lower()
    scored: list[tuple[float, Any]] = []
    for token in store.get_tokens(record.id):
        name = (token.name or "").lower()
        if name == needle:
            score = 1.0
        elif needle in name:
            score = 0.92 - min(len(name) - len(needle), 30) * 0.004
        elif name in needle:
            score = 0.85
        else:
            ratio = difflib.SequenceMatcher(None, name, needle).ratio()
            if ratio < 0.5:
                continue
            score = ratio * 0.8
        scored.append((score, token))
    scored.sort(key=lambda item: (-item[0], item[1].order))
    matches = [token for _score, token in scored[:limit]]
    return {
        "ok": True,
        "snapshot_id": record.id,
        "query": query,
        "total": len(scored),
        "matches": len(matches),
        "fields": FIELDS,
        "tokens": token_table(matches, record.window),
    }


def _tool_desktop_summary(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    record = store.latest_snapshot()
    if record is None:
        return {"ok": False, "error": "no snapshot; call desktop_scan first"}
    return {
        "ok": True,
        "snapshot_id": record.id,
        "created_at": record.created_at,
        "token_count": record.token_count,
        "windows": record.window,
    }


def _tool_computer_act(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from ..agent import run_act

    instruction = str(arguments.get("instruction") or "")
    verbose = bool(arguments.get("verbose", False))
    result = run_act(
        instruction,
        settings,
        store=store,
        window=arguments.get("window"),
        dry_run=bool(arguments.get("dry_run", False)),
        fixture=arguments.get("fixture"),
        inproc=True,
    )
    results = result.get("results") or []
    compact: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "trace_id": result.get("trace_id"),
        "status": result.get("status"),
        "snapshot_id": result.get("snapshot_id"),
        "dry_run": bool(result.get("dry_run")),
        "steps": len(results),
    }
    if result.get("dry_run"):
        compact["tokens"] = result.get("tokens")
        compact["refreshed"] = result.get("refreshed")
    else:
        compact["results"] = [
            [item.get("index"), item.get("op"), bool(item.get("ok")),
             item.get("ms"), item.get("error")]
            for item in results
        ]
        if result.get("error"):
            compact["error"] = result.get("error")
    if verbose:
        compact["plan"] = result.get("plan")
        compact["ir"] = result.get("ir")
        compact["ir_path"] = result.get("ir_path")
    return compact


def _tool_launch_app(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    import time

    from ..interpreter import launch_app

    app = str(arguments.get("app") or "").strip()
    if not app:
        return {"ok": False, "error": "app is empty"}
    exe = launch_app(app)
    time.sleep(max(0, int(arguments.get("wait_ms", 800))) / 1000.0)
    return {"ok": True, "app": app, "exe": exe}


def _tool_open_url(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    import time

    from ..interpreter import open_url

    url = str(arguments.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://"}
    open_url(url)
    time.sleep(max(0, int(arguments.get("wait_ms", 500))) / 1000.0)
    return {"ok": True, "url": url}


def _tool_search_web(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    import time
    from urllib.parse import quote_plus

    from ..interpreter import open_url

    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query is empty"}
    engine = str(arguments.get("engine") or "google").lower()
    if engine == "youtube":
        url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    elif engine == "bing":
        url = "https://www.bing.com/search?q=" + quote_plus(query)
    else:
        engine = "google"
        url = "https://www.google.com/search?q=" + quote_plus(query)
    open_url(url)
    time.sleep(max(0, int(arguments.get("wait_ms", 500))) / 1000.0)
    return {"ok": True, "engine": engine, "query": query, "url": url}


def _tool_win_run(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    command = str(arguments.get("command") or "").strip()
    if not command:
        return {"ok": False, "error": "command is empty"}
    return {"ok": True, **input_mod.win_run(command, int(arguments.get("wait_ms", 350)))}


def _tool_mouse_move(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    x, y = input_mod.move(int(arguments["x"]), int(arguments["y"]),
                          int(arguments.get("duration_ms", 0)))
    return {"ok": True, "x": x, "y": y}


def _tool_mouse_click(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    x = arguments.get("x")
    y = arguments.get("y")
    result = input_mod.click(
        int(x) if x is not None else None,
        int(y) if y is not None else None,
        str(arguments.get("button", "left")),
        int(arguments.get("clicks", 1)),
        int(arguments.get("interval_ms", 80)),
    )
    return {"ok": True, **result}


def _tool_mouse_drag(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    result = input_mod.drag(
        int(arguments["from_x"]), int(arguments["from_y"]),
        int(arguments["to_x"]), int(arguments["to_y"]),
        str(arguments.get("button", "left")),
        int(arguments.get("duration_ms", 500)),
    )
    return {"ok": True, **result}


def _tool_mouse_scroll(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    x = arguments.get("x")
    y = arguments.get("y")
    result = input_mod.scroll(
        int(x) if x is not None else None,
        int(y) if y is not None else None,
        int(arguments.get("dy", 3)),
        int(arguments.get("dx", 0)),
    )
    return {"ok": True, **result}


def _tool_key_press(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    return {"ok": True, **input_mod.key_press(str(arguments["keys"]))}


def _tool_key_hold(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    return {"ok": True, **input_mod.key_hold(str(arguments["keys"]), int(arguments.get("ms", 500)))}


def _tool_type_text(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    return {"ok": True, **input_mod.type_text(str(arguments["text"]))}


def _tool_screen_info(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    return {"ok": True, **input_mod.screen_info()}


def _tool_mouse_position(arguments: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .. import input as input_mod

    x, y = input_mod.mouse_position()
    return {"ok": True, "x": x, "y": y}


TOOLS = {
    "desktop_scan": _tool_desktop_scan,
    "desktop_tokens": _tool_desktop_tokens,
    "desktop_find": _tool_desktop_find,
    "desktop_summary": _tool_desktop_summary,
    "launch_app": _tool_launch_app,
    "open_url": _tool_open_url,
    "search_web": _tool_search_web,
    "win_run": _tool_win_run,
    "computer_act": _tool_computer_act,
    "mouse_move": _tool_mouse_move,
    "mouse_click": _tool_mouse_click,
    "mouse_drag": _tool_mouse_drag,
    "mouse_scroll": _tool_mouse_scroll,
    "key_press": _tool_key_press,
    "key_hold": _tool_key_hold,
    "type_text": _tool_type_text,
    "screen_info": _tool_screen_info,
    "mouse_position": _tool_mouse_position,
}


def response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def handle(message: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")

    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return error(request_id, INVALID_REQUEST, "invalid JSON-RPC request")

    if method == "initialize":
        return response(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return response(request_id, {})

    if method == "tools/list":
        return response(request_id, {"tools": tool_definitions()})

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = TOOLS.get(str(name))
        if handler is None:
            return response(request_id, _text_result(
                json.dumps({"ok": False, "error": f"unknown tool: {name}"}, ensure_ascii=False),
                is_error=True))
        try:
            payload = handler(arguments, store, settings)
        except OacuError as exc:
            return response(request_id, _text_result(
                json.dumps({"ok": False, "error": exc.message, "code": exc.code}, ensure_ascii=False),
                is_error=True))
        except Exception as exc:  # noqa: BLE001 - MCP must answer
            return response(request_id, _text_result(
                json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False),
                is_error=True))
        return response(request_id, _text_result(
            _render_tool_content(str(name), payload),
            is_error=not payload.get("ok", True)))

    if method == "resources/list":
        return response(request_id, {"resources": []})

    if method == "prompts/list":
        return response(request_id, {"prompts": []})

    return error(request_id, METHOD_NOT_FOUND, f"method not found: {method}")
