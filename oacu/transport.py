"""JSON-lines transport between the CLI and the local interpreter daemon."""

from __future__ import annotations

import json
import socket
from typing import Any, Callable

from .config import Settings
from .errors import TransportError
from .ir import validate_ir
from .store import Store

MAX_LINE = 8 * 1024 * 1024

Handler = Callable[[dict[str, Any], Store, Settings], dict[str, Any]]


def default_handler(request: dict[str, Any], store: Store, settings: Settings) -> dict[str, Any]:
    from .interpreter import execute

    if request.get("type") == "ping":
        return {"ok": True, "pong": True}
    if request.get("type") != "execute":
        return {"ok": False, "error": f"unknown request type: {request.get('type')!r}"}
    ir = request.get("ir")
    if not isinstance(ir, dict):
        return {"ok": False, "error": "missing ir object"}
    try:
        validate_ir(ir)
    except Exception as exc:  # noqa: BLE001 - protocol must answer, not crash
        return {"ok": False, "error": str(exc)}
    results = execute(ir, store=store, settings=settings)
    failures = [item for item in results if not item.get("ok")]
    payload: dict[str, Any] = {"ok": not failures, "results": results}
    if failures:
        first = failures[0]
        payload["error"] = f"step {first.get('index')} {first.get('op')}: {first.get('error')}"
    return payload


def send_ir(
    ir: dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 8765,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    payload = json.dumps({"type": "execute", "ir": ir}, ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        with socket.create_connection((host, port), timeout=0.5) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)
            buffer = b""
            while b"\n" not in buffer:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_LINE:
                    break
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        raise TransportError(
            f"无法连接本地解释器 {host}:{port}；请先运行 `oacu serve`，或使用 --inproc",
            detail=str(exc),
        ) from exc

    line = buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
    if not line:
        raise TransportError("本地解释器没有返回内容")
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TransportError("本地解释器返回了非 JSON 内容", detail=line[:200]) from exc
    results = list(response.get("results") or [])
    if not response.get("ok") and not results:
        raise TransportError(response.get("error") or "解释器执行失败")
    return results


def serve_forever(
    host: str,
    port: int,
    store: Store,
    settings: Settings,
    *,
    handler: Handler | None = None,
    ready: Callable[[int], None] | None = None,
    max_connections: int | None = None,
    on_request: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    handler = handler or default_handler
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((host, port))
        server.listen(8)
        bound_port = server.getsockname()[1]
        if ready:
            ready(bound_port)
        served = 0
        while max_connections is None or served < max_connections:
            conn, _addr = server.accept()
            served += 1
            with conn:
                conn.settimeout(30)
                try:
                    buffer = b""
                    while b"\n" not in buffer:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buffer += chunk
                        if len(buffer) > MAX_LINE:
                            break
                    line = buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        request = json.loads(line)
                    except json.JSONDecodeError:
                        response = {"ok": False, "error": "invalid json"}
                    else:
                        if on_request:
                            on_request(request)
                        response = handler(request, store, settings)
                    conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
                except OSError:
                    continue
    finally:
        server.close()
