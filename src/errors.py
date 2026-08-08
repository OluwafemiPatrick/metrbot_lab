"""Stable, safe errors for public Metrbot Lab boundaries."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ErrorCode(StrEnum):
    """Phase 1 error codes shared by domain and configuration boundaries."""

    INVALID_VALUE = "INVALID_VALUE"
    INVALID_ACTION = "INVALID_ACTION"
    INVALID_STATE = "INVALID_STATE"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"


class MetrbotLabError(Exception):
    """Base exception with a stable code and safe structured context."""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        field: str | None = None,
        context: Mapping[str, str] | None = None,
    ) -> None:
        if not message or not message.strip():
            raise ValueError("error message must not be empty")
        self.code = str(code)
        self.message = message
        self.field = field
        self.context = MappingProxyType(dict(sorted((context or {}).items())))
        super().__init__(self._display_message())

    def _display_message(self) -> str:
        location = f" field={self.field}" if self.field else ""
        return f"[{self.code}]{location} {self.message}"

    def as_dict(self) -> dict[str, object]:
        """Return deterministic JSON-compatible error data."""
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "context": dict(self.context),
        }


class DomainValidationError(MetrbotLabError):
    """Raised when a domain record violates its contract."""


class ConfigurationValidationError(MetrbotLabError):
    """Raised when a run configuration violates its contract."""


class SerializationError(MetrbotLabError):
    """Raised when a public domain value cannot be serialized safely."""
