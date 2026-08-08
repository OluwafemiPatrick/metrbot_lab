"""Scalar parsers and validation records for the Phase 2 data boundary."""

from __future__ import annotations

from datetime import datetime
import math

from ..errors import DataValidationError, ErrorCode


def parse_timestamp(raw: str, *, source: str, row: int, column: str = "Timestamp") -> datetime:
    """Parse one ISO timestamp without changing its timezone awareness or offset."""
    text = _require_text(raw, source=source, row=row, column=column)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise DataValidationError(
            ErrorCode.INVALID_TIMESTAMP,
            "timestamp could not be parsed as ISO datetime",
            source=source,
            row=row,
            column=column,
        ) from exc


def parse_price(raw: str, *, source: str, row: int, column: str) -> float:
    """Parse one positive finite OHLC price."""
    text = _require_text(raw, source=source, row=row, column=column)
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise DataValidationError(
            ErrorCode.INVALID_PRICE,
            "price must be numeric",
            source=source,
            row=row,
            column=column,
        ) from exc
    if not math.isfinite(value):
        raise DataValidationError(
            ErrorCode.NON_FINITE_PRICE,
            "price must be finite",
            source=source,
            row=row,
            column=column,
        )
    if value <= 0:
        raise DataValidationError(
            ErrorCode.NON_POSITIVE_PRICE,
            "price must be greater than zero",
            source=source,
            row=row,
            column=column,
        )
    return value


def parse_volume(raw: str, *, source: str, row: int, column: str = "Volume") -> float:
    """Parse one non-negative finite volume value."""
    text = _require_text(raw, source=source, row=row, column=column, blank_code=ErrorCode.INVALID_VOLUME)
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise DataValidationError(
            ErrorCode.INVALID_VOLUME,
            "volume must be numeric",
            source=source,
            row=row,
            column=column,
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise DataValidationError(
            ErrorCode.INVALID_VOLUME,
            "volume must be finite and non-negative",
            source=source,
            row=row,
            column=column,
        )
    return value


def parse_symbol(raw: str, *, source: str, row: int, column: str = "Symbol") -> str:
    """Parse one non-empty symbol value without changing its case."""
    return _require_text(raw, source=source, row=row, column=column, blank_code=ErrorCode.EMPTY_SYMBOL)


def timestamp_is_aware(value: datetime) -> bool:
    """Return the standard-library awareness state for a parsed timestamp."""
    return value.tzinfo is not None and value.utcoffset() is not None


def _require_text(
    raw: str,
    *,
    source: str,
    row: int,
    column: str,
    blank_code: ErrorCode = ErrorCode.MISSING_VALUE,
) -> str:
    if not isinstance(raw, str):
        raise DataValidationError(
            blank_code,
            "value must be text",
            source=source,
            row=row,
            column=column,
        )
    text = raw.strip()
    if not text:
        raise DataValidationError(
            blank_code,
            "value must not be blank",
            source=source,
            row=row,
            column=column,
        )
    return text
