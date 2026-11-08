"""Local interpreter: execute a timed IR against UIA elements."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .models import Token
from .keys import parse_keys
from .store import Store

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def _noop_text(_text: str) -> None:
    return None


def _noop_launch(target: str) -> str:
    return target


@dataclass
class Backends:
    mouse: Callable[[str, int, int, int], None]
    key: Callable[[str], None]
    pattern: Callable[[dict[str, Any]], dict[str, Any]]
    sleep: Callable[[float], None]
    clock: Callable[[], float]
    type_text: Callable[[str], None] = _noop_text
    launch: Callable[[str], str] = _noop_launch
    open_url: Callable[[str], str] = _noop_launch


def _send_text(text: str) -> None:
    from . import virtual

    virtual.type_text(text)


class StepError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _send_keys(keys: str) -> None:
    from . import virtual

    virtual.key_press(keys)


send_keys = _send_keys
send_text = _send_text


def _mouse(op: str, x: int, y: int, times: int = 1) -> None:
    from . import virtual

    if op == "click":
        virtual.click(x, y, "left", 1)
    elif op == "double_click":
        virtual.click(x, y, "left", 2)
    elif op == "right_click":
        virtual.click(x, y, "right", 1)
    elif op == "scroll_up":
        virtual.scroll(x, y, max(1, times), 0)
    elif op == "scroll_down":
        virtual.scroll(x, y, -max(1, times), 0)
    elif op == "scroll_right":
        virtual.scroll(x, y, 0, max(1, times))
    elif op == "scroll_left":
        virtual.scroll(x, y, 0, -max(1, times))
    else:
        raise StepError("bad_mouse_op", op)


def _run_uia_act(spec: dict[str, Any], timeout: float = 6.0) -> dict[str, Any]:
    script = TOOLS_DIR / "uia_act.ps1"
    if not script.is_file():
        return {"ok": False, "error": "missing uia_act.ps1", "code": "ps_missing"}
    folder = Path(tempfile.mkdtemp(prefix="oacu-act-"))
    spec_file = folder / "spec.json"
    out_file = folder / "out.json"
    spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-SpecFile", str(spec_file), "-OutFile", str(out_file)],
            capture_output=True, timeout=timeout, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "code": "ps_timeout"}
    if not out_file.is_file():
        return {"ok": False, "error": "no output from uia_act.ps1", "code": "ps_error"}
    try:
        return json.loads(out_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "code": "ps_error"}
    finally:
        for path in (spec_file, out_file):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


SITE_URLS = {
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "bilibili": "https://www.bilibili.com",
    "baidu": "https://www.baidu.com",
}

APP_ALIASES: dict[str, tuple[str, str]] = {
    "chrome": ("chrome.exe", ""),
    "google chrome": ("chrome.exe", ""),
    "edge": ("msedge.exe", ""),
    "microsoft edge": ("msedge.exe", ""),
    "notepad": ("notepad.exe", ""),
    "记事本": ("notepad.exe", ""),
    "calc": ("calc.exe", ""),
    "calculator": ("calc.exe", ""),
    "计算器": ("calc.exe", ""),
    "explorer": ("explorer.exe", ""),
    "文件资源管理器": ("explorer.exe", ""),
    "libreoffice": ("soffice.exe", ""),
    "libreoffice writer": ("soffice.exe", "--writer"),
    "writer": ("soffice.exe", "--writer"),
    "spotify": ("spotify.exe", ""),
    "cmd": ("cmd.exe", ""),
    "powershell": ("powershell.exe", ""),
}

COMMON_APP_PATHS: dict[str, list[str]] = {
    "chrome.exe": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "soffice.exe": [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ],
    "spotify.exe": [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
    ],
}


def _strip_app_words(target: str) -> str:
    value = target.strip().strip("「」『』“”\"'")
    for word in ("浏览器", "应用程序", "应用", "程序", "软件"):
        if value.endswith(word) and len(value) > len(word):
            value = value[: -len(word)]
    return value.strip()


def _resolve_app(target: str) -> tuple[str, str]:
    value = _strip_app_words(target)
    lower = value.lower()
    if lower in APP_ALIASES:
        name, args = APP_ALIASES[lower]
        found = shutil.which(name)
        if found:
            return found, args
        for path in COMMON_APP_PATHS.get(name, []):
            if path and Path(path).is_file():
                return path, args
        return name, args
    found = shutil.which(value)
    if found:
        return found, ""
    return value, ""


def _shell_open(file: str, args: str = "") -> None:
    result = ctypes.windll.shell32.ShellExecuteW(None, "open", file, args or None, None, 1)
    if int(result) <= 32:
        raise StepError("launch_failed", f"无法启动: {file}")


def _launch(target: str) -> str:
    value = _strip_app_words(target)
    lower = value.lower()
    if lower in SITE_URLS:
        _shell_open(SITE_URLS[lower])
        return SITE_URLS[lower]
    exe, args = _resolve_app(value)
    _shell_open(exe, args)
    return exe


def _open_url(url: str) -> str:
    _shell_open(url)
    return url


launch_app = _launch
open_url = _open_url


def default_backends(settings: Settings | None = None) -> Backends:
    return Backends(
        mouse=_mouse,
        key=_send_keys,
        pattern=_run_uia_act,
        sleep=time.sleep,
        clock=time.perf_counter,
        type_text=_send_text,
        launch=_launch,
        open_url=_open_url,
    )


def _spec_for(step: dict[str, Any], token: Token | None) -> dict[str, Any]:
    match: dict[str, Any] = {}
    if token is not None:
        match = {
            "name": token.name,
            "control_type": token.ctype,
            "automation_id": token.relations.get("id", ""),
            "rect": list(token.rect),
        }
    return {
        "op": step["op"],
        "match": match,
        "value": step.get("value", ""),
        "direction": step.get("direction", ""),
        "times": int(step.get("times", 1)),
    }


def _resolve(step: dict[str, Any], store: Store | None, snapshot_id: int) -> Token | None:
    token_id = step.get("token")
    if not token_id:
        return None
    if store is None:
        raise StepError("stale_token", f"{token_id}: 没有可用的快照库")
    token = store.resolve(snapshot_id, str(token_id))
    if token is None:
        raise StepError("stale_token", f"{token_id} 不在快照 {snapshot_id} 中，请重新执行 oacu scan")
    return token


def _coords(step: dict[str, Any], token: Token | None) -> tuple[int, int]:
    if isinstance(step.get("x"), int) and isinstance(step.get("y"), int):
        return int(step["x"]), int(step["y"])
    if token is None:
        raise StepError("bad_step", "缺少坐标且没有 token")
    return token.center


def execute(
    ir: dict[str, Any],
    store: Store | None = None,
    settings: Settings | None = None,
    backends: Backends | None = None,
) -> list[dict[str, Any]]:
    backends = backends or default_backends(settings)
    timeout = float(settings.config.get("step_timeout_s", 1.5)) if settings else 1.5
    steps = sorted(enumerate(ir.get("steps") or []), key=lambda pair: (int(pair[1].get("at", 0)), pair[0]))
    start_all = backends.clock()
    results: list[dict[str, Any]] = []

    for index, step in steps:
        op = str(step.get("op"))
        at = int(step.get("at", 0))
        delay = start_all + at / 1000.0 - backends.clock()
        if delay > 0:
            backends.sleep(delay)
        step_start = backends.clock()
        try:
            token = _resolve(step, store, int(ir.get("snapshot_id", 0)))
            if op == "wait":
                backends.sleep(int(step.get("ms", 0)) / 1000.0)
            elif op in ("click", "double_click", "right_click"):
                used_pattern = False
                if op == "click" and token is not None:
                    response = backends.pattern(_spec_for(step, token))
                    used_pattern = bool(response.get("ok"))
                if not used_pattern:
                    x, y = _coords(step, token)
                    backends.mouse(op, x, y, 1)
            elif op in ("invoke", "set_value", "activate"):
                response = backends.pattern(_spec_for(step, token))
                if not response.get("ok"):
                    if response.get("code") == "pattern_unavailable" and op == "set_value":
                        x, y = _coords(step, token)
                        backends.mouse("click", x, y, 1)
                        backends.sleep(0.15)
                        backends.type_text(str(step.get("value", "")))
                    elif response.get("code") == "pattern_unavailable" and op in ("invoke", "activate"):
                        x, y = _coords(step, token)
                        backends.mouse("click", x, y, 1)
                    else:
                        raise StepError(str(response.get("code") or "pattern_failed"),
                                        str(response.get("error") or "UIA pattern 执行失败"))
            elif op == "type":
                backends.type_text(str(step.get("value", "")))
            elif op == "launch":
                backends.launch(str(step.get("value", "")))
            elif op == "open_url":
                backends.open_url(str(step.get("value", "")))
            elif op == "scroll":
                direction = str(step.get("direction") or "down")
                times = max(1, int(step.get("times", 1)))
                response = backends.pattern(_spec_for(step, token))
                if not response.get("ok"):
                    if response.get("code") == "pattern_unavailable":
                        x, y = _coords(step, token)
                        backends.mouse(f"scroll_{direction}", x, y, times)
                    else:
                        raise StepError(str(response.get("code") or "pattern_failed"),
                                        str(response.get("error") or "滚动失败"))
            elif op == "key":
                backends.key(str(step.get("keys", "")))
            else:
                raise StepError("unsupported_op", op)

            elapsed = backends.clock() - step_start
            if elapsed > timeout:
                raise StepError("timeout", f"{elapsed:.2f}s > {timeout:.2f}s")
            results.append({
                "index": index, "op": op, "ok": True,
                "ms": round(elapsed * 1000, 1), "at": at,
            })
        except StepError as exc:
            results.append({
                "index": index, "op": op, "ok": False,
                "ms": round((backends.clock() - step_start) * 1000, 1), "at": at,
                "error": str(exc), "code": exc.code,
            })
            break
        except Exception as exc:  # noqa: BLE001 - report, do not crash the daemon
            results.append({
                "index": index, "op": op, "ok": False,
                "ms": round((backends.clock() - step_start) * 1000, 1), "at": at,
                "error": f"exception: {exc}", "code": "exception",
            })
            break

    return results
