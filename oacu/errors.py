"""Typed application errors mapped to stable CLI exit codes."""

from __future__ import annotations


class OacuError(Exception):
    """Base error. code is the process exit code."""

    code = 1

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class UsageError(OacuError):
    code = 2


class EnvUnavailable(OacuError):
    code = 3


class NoSnapshot(OacuError):
    code = 3

    def __init__(self, message: str = "还没有可用快照，请先执行 `oacu scan`") -> None:
        super().__init__(message)


class NoMatch(OacuError):
    pass


class IRValidationError(OacuError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"IR 校验失败: {field}: {message}")
        self.field = field


class TransportError(OacuError):
    pass


class StaleToken(OacuError):
    pass
