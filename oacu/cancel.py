"""Cooperative task cancellation for OpenCU (Esc or explicit event)."""

from __future__ import annotations

import ctypes
import sys
import threading
import time

from .errors import OacuError

VK_ESCAPE = 0x1B


class TaskCancelled(OacuError):
    """Raised when the current OpenCU task is cancelled."""

    code = 130

    def __init__(self, message: str = "任务已取消 (Esc)") -> None:
        super().__init__(message)


class CancelToken:
    def __init__(self, event: threading.Event | None = None) -> None:
        self._event = event or threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise TaskCancelled()

    def sleep(self, seconds: float) -> bool:
        """Cancellable sleep; returns True when cancelled."""
        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            if self.is_set():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.03, remaining))


class _EscWatcher:
    """Observe Esc globally without consuming it or installing a hook."""

    def __init__(self, token: CancelToken) -> None:
        self.token = token
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if sys.platform != "win32":
            return
        if ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            self.token.cancel()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _watch(self) -> None:
        user32 = ctypes.windll.user32
        while not self._stop.is_set():
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self.token.cancel()
                return
            self._stop.wait(0.03)


_local = threading.local()


class TaskScope:
    """Bind a cancel token to the current thread and start the Esc watcher.

    Nested scopes reuse the outer token, so a GUI/agent task and its chain share
    one cancellation source.
    """

    def __init__(self, *, cancel_on_esc: bool = True,
                 event: threading.Event | None = None) -> None:
        self.cancel_on_esc = cancel_on_esc
        self.event = event
        self.token: CancelToken | None = None
        self._owner = False
        self._watcher: _EscWatcher | None = None

    def __enter__(self) -> CancelToken:
        current = getattr(_local, "token", None)
        if current is not None:
            self.token = current
            return current
        self.token = CancelToken(self.event)
        _local.token = self.token
        self._owner = True
        if self.cancel_on_esc and self.event is None:
            self._watcher = _EscWatcher(self.token)
            self._watcher.start()
        return self.token

    def __exit__(self, *_exc: object) -> None:
        if not self._owner:
            return
        if self._watcher is not None:
            self._watcher.stop()
        _local.token = None


def current_token() -> CancelToken | None:
    return getattr(_local, "token", None)


def check() -> None:
    token = current_token()
    if token is not None:
        token.check()


def sleep(seconds: float) -> bool:
    token = current_token()
    if token is not None:
        return token.sleep(seconds)
    time.sleep(max(0.0, float(seconds)))
    return False


def request_cancel() -> None:
    """Cancel the current thread's task (used by tests and UI hooks)."""
    token = current_token()
    if token is not None:
        token.cancel()
