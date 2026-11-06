"""UIA backend selection: PowerShell bridge (default) or pywinauto (optional)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..errors import EnvUnavailable
from ..models import CollectResult, RawElement

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def powershell_exe() -> str | None:
    for name in ("powershell", "pwsh"):
        found = shutil.which(name)
        if found:
            return found
    return None


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    exe = powershell_exe()
    if not exe:
        raise EnvUnavailable("找不到 powershell.exe，无法使用 UIA 后端")
    return subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        creationflags=NO_WINDOW,
    )


def ps_uia_available() -> tuple[bool, str]:
    script = (
        "$ErrorActionPreference='Stop'; "
        "Add-Type -AssemblyName UIAutomationClient; "
        "Add-Type -AssemblyName UIAutomationTypes; "
        "$r=[System.Windows.Automation.AutomationElement]::RootElement; "
        "Write-Output ('uia:' + [bool]$r)"
    )
    try:
        proc = run_powershell(script)
    except (OSError, EnvUnavailable, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "uia probe failed").strip()
    return "uia:True" in (proc.stdout or ""), (proc.stdout or "").strip()


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        raise EnvUnavailable("UIA 后端返回空结果")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnvUnavailable(f"UIA 后端返回的 JSON 无法解析: {exc}") from exc


def collect_ps(
    max_depth: int = 12,
    max_elements: int = 3000,
    window: str | None = None,
    time_budget_ms: int = 8000,
) -> CollectResult:
    exe = powershell_exe()
    if not exe:
        raise EnvUnavailable("找不到 powershell.exe，无法使用 UIA 后端")
    script = TOOLS_DIR / "uia_dump.ps1"
    if not script.is_file():
        raise EnvUnavailable(f"缺少 UIA 脚本: {script}")

    tmpdir = Path(tempfile.mkdtemp(prefix="oacu-uia-"))
    out = tmpdir / "desktop.json"
    cmd = [
        exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-MaxDepth", str(max_depth),
        "-MaxElements", str(max_elements),
        "-TimeBudgetMs", str(max(1000, int(time_budget_ms))),
        "-OutFile", str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise EnvUnavailable("UIA 采集超时（120s）") from exc
    if not out.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise EnvUnavailable("UIA 采集没有产出结果文件", detail=detail)
    payload = _load_json(out)
    try:
        out.unlink(missing_ok=True)
    except OSError:
        pass
    if not payload.get("ok"):
        raise EnvUnavailable(f"UIA 采集失败: {payload.get('error', 'unknown')}")
    elements = [RawElement.from_dict(item) for item in payload.get("elements") or []]
    screen = payload.get("screen") or [0, 0]
    meta = {
        "backend": "ps",
        "ps": payload.get("ps", ""),
        "screen": [int(screen[0]), int(screen[1])],
        "truncated": bool(payload.get("truncated")),
        "timeout": bool(payload.get("timeout")),
        "raw": len(elements),
    }
    return CollectResult(elements=elements, meta=meta)


def collect_pywinauto(
    max_depth: int = 12,
    max_elements: int = 3000,
    window: str | None = None,
) -> CollectResult:
    try:
        from pywinauto import Desktop  # type: ignore
    except ImportError as exc:
        raise EnvUnavailable("pywinauto 未安装，无法使用 --backend uia") from exc

    elements: list[RawElement] = []
    desktop = Desktop(backend="uia")

    def walk(node: Any, depth: int, parent: int) -> None:
        if len(elements) >= max_elements or depth > max_depth:
            return
        try:
            info = node.element_info
        except Exception:
            return
        rect = info.rectangle
        idx = len(elements)
        elements.append(
            RawElement(
                name=info.name or "",
                control_type=str(info.control_type or "").replace("ControlType.", ""),
                rect=(rect.left, rect.top, rect.width(), rect.height()),
                automation_id=info.automation_id or "",
                class_name=info.class_name or "",
                parent=parent,
                depth=depth,
                enabled=True,
                offscreen=False,
            )
        )
        try:
            children = node.children()
        except Exception:
            return
        for child in children:
            if len(elements) >= max_elements:
                break
            walk(child, depth + 1, idx)

    for node in desktop.windows(visible_only=True):
        name = ""
        try:
            name = node.window_text()
        except Exception:
            pass
        if window and window.lower() not in name.lower():
            continue
        walk(node, 0, -1)
    return CollectResult(
        elements=elements,
        meta={"backend": "uia", "ps": "", "screen": [0, 0], "truncated": len(elements) >= max_elements,
              "raw": len(elements)},
    )


def collect_fake(fixture: str | Path) -> CollectResult:
    path = Path(fixture)
    if not path.is_file():
        raise EnvUnavailable(f"fixture 不存在: {path}")
    payload = _load_json(path)
    elements = [RawElement.from_dict(item) for item in payload.get("elements") or []]
    screen = payload.get("screen") or [1920, 1080]
    return CollectResult(
        elements=elements,
        meta={"backend": "fake", "ps": "", "screen": [int(screen[0]), int(screen[1])],
              "truncated": False, "raw": len(elements)},
    )


def collect(
    backend: str = "auto",
    max_depth: int = 12,
    max_elements: int = 3000,
    window: str | None = None,
    fixture: str | Path | None = None,
) -> CollectResult:
    if backend == "fake":
        if not fixture:
            raise EnvUnavailable("--backend fake 需要 --fixture <desktop.json>")
        return collect_fake(fixture)

    if backend == "uia":
        return collect_pywinauto(max_depth=max_depth, max_elements=max_elements, window=window)

    if backend == "ps":
        return collect_ps(max_depth=max_depth, max_elements=max_elements, window=window)

    # auto: prefer pywinauto only if it is importable, otherwise the PS bridge.
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        return collect_ps(max_depth=max_depth, max_elements=max_elements, window=window)
    try:
        return collect_pywinauto(max_depth=max_depth, max_elements=max_elements, window=window)
    except EnvUnavailable:
        return collect_ps(max_depth=max_depth, max_elements=max_elements, window=window)


def probe() -> dict[str, Any]:
    ps = powershell_exe()
    ok_ps, detail = (False, "powershell not found")
    if ps:
        ok_ps, detail = ps_uia_available()
    try:
        import pywinauto  # noqa: F401
        has_pw = True
    except ImportError:
        has_pw = False
    return {
        "powershell": ps or "",
        "ps_uia": ok_ps,
        "ps_detail": detail,
        "pywinauto": has_pw,
        "backend": "ps" if ok_ps else ("uia" if has_pw else ""),
    }
