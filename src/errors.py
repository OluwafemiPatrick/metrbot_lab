"""Stable, safe errors for public Metrbot Lab boundaries."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ErrorCode(StrEnum):
    """Stable error codes shared by public domain, configuration, and data boundaries."""

    INVALID_VALUE = "INVALID_VALUE"
    INVALID_ACTION = "INVALID_ACTION"
    INVALID_STATE = "INVALID_STATE"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    NOT_A_FILE = "NOT_A_FILE"
    UNREADABLE_FILE = "UNREADABLE_FILE"
    INVALID_ENCODING = "INVALID_ENCODING"
    EMPTY_FILE = "EMPTY_FILE"
    MALFORMED_CSV = "MALFORMED_CSV"
    EMPTY_HEADER = "EMPTY_HEADER"
    DUPLICATE_COLUMN = "DUPLICATE_COLUMN"
    MISSING_COLUMN = "MISSING_COLUMN"
    MALFORMED_ROW = "MALFORMED_ROW"
    EMPTY_DATASET = "EMPTY_DATASET"
    MISSING_VALUE = "MISSING_VALUE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    MIXED_TIMEZONE_AWARENESS = "MIXED_TIMEZONE_AWARENESS"
    NON_FINITE_PRICE = "NON_FINITE_PRICE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    INVALID_VOLUME = "INVALID_VOLUME"
    INVALID_CANDLE_RANGE = "INVALID_CANDLE_RANGE"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    NON_MONOTONIC_TIMESTAMP = "NON_MONOTONIC_TIMESTAMP"
    EMPTY_SYMBOL = "EMPTY_SYMBOL"
    MULTIPLE_SYMBOLS = "MULTIPLE_SYMBOLS"


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


class DataValidationError(MetrbotLabError):
    """Raised when an external CSV dataset violates the input contract."""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        source: str | None = None,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        if row is not None and (not isinstance(row, int) or isinstance(row, bool) or row < 1):
            raise ValueError("data error row must be a positive integer")
        if column is not None and (not isinstance(column, str) or not column.strip()):
            raise ValueError("data error column must be a non-empty string")
        context = {}
        if source is not None:
            context["source"] = source
        if row is not None:
            context["row"] = str(row)
        if column is not None:
            context["column"] = column
        super().__init__(code, message, field=column, context=context)
        self.source = source
        self.row = row
        self.column = column


class SerializationError(MetrbotLabError):
    """Raised when a public domain value cannot be serialized safely."""
