"""Configuration, paths and defaults for OpenAgentCU."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_NAME = "OpenAgentCU"

DEFAULTS: dict[str, Any] = {
    "max_depth": 12,
    "max_elements": 3000,
    "max_age_s": 30,
    "snapshot_keep": 20,
    "port": 8765,
    "host": "127.0.0.1",
    "step_interval_ms": 120,
    "step_timeout_s": 1.5,
    "exec_timeout_s": 10.0,
    "backend": "auto",
}


_HOME_CACHE: tuple[tuple[str, ...], Path] | None = None


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def home_dir() -> Path:
    """Writable data directory: OACU_HOME > APPDATA > LOCALAPPDATA > ~/.opencu > cwd."""
    global _HOME_CACHE
    key = (
        os.environ.get("OACU_HOME", ""),
        os.environ.get("APPDATA", ""),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("PUBLIC", ""),
        os.environ.get("USERPROFILE", ""),
        str(Path.cwd()),
    )
    if _HOME_CACHE and _HOME_CACHE[0] == key:
        return _HOME_CACHE[1]

    override = key[0]
    if override:
        result = Path(override).expanduser()
    else:
        candidates: list[Path] = []
        for base in (key[1], key[2]):
            if base:
                candidates.append(Path(base) / APP_NAME)
        # Shared, non-admin-writable fallback for broken/roaming profiles.
        public = key[3] or "C:\\Users\\Public"
        if Path(public).is_dir():
            candidates.append(Path(public) / APP_NAME)
        candidates.append(Path.home() / ".opencu")
        candidates.append(Path.cwd() / ".opencu")
        result = next((item for item in candidates if _writable_dir(item)), candidates[-1])

    _HOME_CACHE = (key, result)
    return result


def db_path() -> Path:
    return home_dir() / "oacu.db"


def ir_dir() -> Path:
    return home_dir() / "ir"


def ensure_dirs() -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    ir_dir().mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.json merged over DEFAULTS. Missing/invalid file is ignored."""
    cfg = dict(DEFAULTS)
    target = Path(path) if path else home_dir() / "config.json"
    if target.is_file():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in cfg:
                    cfg[key] = value
    return cfg


@dataclass
class Settings:
    json: bool = False
    db: Path = None  # type: ignore[assignment]
    backend: str = "auto"
    timeout: float = 10.0
    verbose: bool = False
    config: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.db is None:
            self.db = db_path()
        if self.config is None:
            self.config = load_config()


def settings_from_args(args: Any) -> Settings:
    cfg = load_config()
    db = Path(args.db).expanduser() if getattr(args, "db", None) else db_path()
    backend = getattr(args, "backend", None) or str(cfg.get("backend", "auto"))
    timeout = getattr(args, "timeout", None)
    if timeout is None:
        timeout = float(cfg.get("exec_timeout_s", 10.0))
    return Settings(
        json=bool(getattr(args, "json", False)),
        db=db,
        backend=backend,
        timeout=float(timeout),
        verbose=bool(getattr(args, "verbose", False)),
        config=cfg,
    )
