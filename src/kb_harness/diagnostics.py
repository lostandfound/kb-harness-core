"""Structured diagnostics shared by the library and CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: str | None = None
    field: str | None = None
    context: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class HarnessError(ValueError):
    """Expected user-facing failure with a stable diagnostic."""

    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic

