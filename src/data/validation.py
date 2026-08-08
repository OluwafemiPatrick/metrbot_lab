"""Scalar parsers and validation records for the Phase 2 data boundary."""

from __future__ import annotations

from datetime import datetime
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..domain import Bar
from ..domain.base import SerializableRecord, require_datetime, require_text
from ..errors import DataValidationError, DomainValidationError, ErrorCode
from .normalization import HeaderMap


@dataclass(frozen=True, slots=True)
class _NumberedRow:
    """One CSV logical record paired with its physical starting line."""

    values: tuple[str, ...]
    source_row: int


@dataclass(frozen=True, slots=True)
class ValidatedRows:
    """Validated row output before the dataset-level report is assembled."""

    bars: tuple[Bar, ...]
    symbol: str | None
    volume_present: bool


@dataclass(frozen=True, slots=True)
class ValidationReport(SerializableRecord):
    """Immutable summary of a successfully validated input dataset."""

    source_path: str
    row_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    symbol: str | None
    volume_present: bool
    columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text(self.source_path, "source_path")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 1:
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "row_count must be a positive integer",
                field="row_count",
            )
        require_datetime(self.first_timestamp, "first_timestamp")
        require_datetime(self.last_timestamp, "last_timestamp")
        if timestamp_is_aware(self.first_timestamp) != timestamp_is_aware(self.last_timestamp):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "report timestamps must use one awareness mode",
                field="timestamps",
            )
        if self.last_timestamp < self.first_timestamp:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "last_timestamp must not precede first_timestamp",
                field="last_timestamp",
            )
        if self.symbol is not None:
            require_text(self.symbol, "symbol")
        if not isinstance(self.volume_present, bool):
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "volume_present must be a boolean",
                field="volume_present",
            )
        _require_string_tuple(self.columns, "columns")
        _require_string_tuple(self.extra_columns, "extra_columns", allow_empty=True)
        _require_string_tuple(self.warnings, "warnings", allow_empty=True)


@dataclass(frozen=True, slots=True)
class LoadedDataset(SerializableRecord):
    """Validated bars and their source summary."""

    bars: tuple[Bar, ...]
    report: ValidationReport

    def __post_init__(self) -> None:
        if not isinstance(self.bars, tuple) or not self.bars or not all(isinstance(bar, Bar) for bar in self.bars):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "bars must be a non-empty tuple of Bar records",
                field="bars",
            )
        if not isinstance(self.report, ValidationReport):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "report must be a ValidationReport",
                field="report",
            )
        awareness_mode = timestamp_is_aware(self.bars[0].timestamp)
        previous_timestamp = self.bars[0].timestamp
        for bar in self.bars[1:]:
            current_awareness = timestamp_is_aware(bar.timestamp)
            if current_awareness != awareness_mode:
                raise DomainValidationError(
                    ErrorCode.MIXED_TIMEZONE_AWARENESS,
                    "bars must use one timestamp awareness mode",
                    field="bars",
                )
            if bar.timestamp == previous_timestamp:
                raise DomainValidationError(
                    ErrorCode.DUPLICATE_TIMESTAMP,
                    "bars must not contain duplicate timestamps",
                    field="bars",
                )
            if bar.timestamp < previous_timestamp:
                raise DomainValidationError(
                    ErrorCode.NON_MONOTONIC_TIMESTAMP,
                    "bars timestamps must be strictly increasing",
                    field="bars",
                )
            previous_timestamp = bar.timestamp
        if len(self.bars) != self.report.row_count:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "report row_count must match bars",
                field="row_count",
            )
        if self.bars[0].timestamp != self.report.first_timestamp:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "report first_timestamp must match bars",
                field="first_timestamp",
            )
        if self.bars[-1].timestamp != self.report.last_timestamp:
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "report last_timestamp must match bars",
                field="last_timestamp",
            )


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


def validate_rows(
    rows: Iterable[Sequence[str] | _NumberedRow],
    header_map: HeaderMap,
    *,
    source: str,
    first_data_row: int = 2,
) -> ValidatedRows:
    """Validate ordered rows and construct immutable internal bars."""
    bars: list[Bar] = []
    symbol: str | None = None
    previous_timestamp: datetime | None = None
    seen_timestamps: set[datetime] = set()
    expected_width = len(header_map.columns)
    awareness_mode: bool | None = None

    for offset, raw_row in enumerate(rows):
        if isinstance(raw_row, _NumberedRow):
            row = raw_row.values
            source_row = raw_row.source_row
        else:
            row = raw_row
            source_row = first_data_row + offset
        if len(row) != expected_width:
            raise DataValidationError(
                ErrorCode.MALFORMED_ROW,
                "row has a different number of fields than the header",
                source=source,
                row=source_row,
            )

        timestamp = parse_timestamp(
            row[header_map.index("Timestamp")],
            source=source,
            row=source_row,
        )
        current_awareness = timestamp_is_aware(timestamp)
        if awareness_mode is None:
            awareness_mode = current_awareness
        elif awareness_mode != current_awareness:
            raise DataValidationError(
                ErrorCode.MIXED_TIMEZONE_AWARENESS,
                "timestamps must use one awareness mode",
                source=source,
                row=source_row,
                column="Timestamp",
            )

        if timestamp in seen_timestamps:
            raise DataValidationError(
                ErrorCode.DUPLICATE_TIMESTAMP,
                "timestamp occurs more than once",
                source=source,
                row=source_row,
                column="Timestamp",
            )
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise DataValidationError(
                ErrorCode.NON_MONOTONIC_TIMESTAMP,
                "timestamps must be strictly increasing",
                source=source,
                row=source_row,
                column="Timestamp",
            )

        prices = {
            column: parse_price(
                row[header_map.index(column)],
                source=source,
                row=source_row,
                column=column,
            )
            for column in ("Open", "High", "Low", "Close")
        }
        if (
            prices["High"] < prices["Open"]
            or prices["High"] < prices["Close"]
            or prices["Low"] > prices["Open"]
            or prices["Low"] > prices["Close"]
            or prices["High"] < prices["Low"]
        ):
            raise DataValidationError(
                ErrorCode.INVALID_CANDLE_RANGE,
                "high and low must contain open and close",
                source=source,
                row=source_row,
                column="High/Low",
            )

        volume = None
        if header_map.has("Volume"):
            volume = parse_volume(
                row[header_map.index("Volume")],
                source=source,
                row=source_row,
            )

        row_symbol = None
        if header_map.has("Symbol"):
            row_symbol = parse_symbol(
                row[header_map.index("Symbol")],
                source=source,
                row=source_row,
            )
            if symbol is None:
                symbol = row_symbol
            elif symbol != row_symbol:
                raise DataValidationError(
                    ErrorCode.MULTIPLE_SYMBOLS,
                    "dataset contains more than one symbol",
                    source=source,
                    row=source_row,
                    column="Symbol",
                )

        try:
            bar = Bar(
                timestamp=timestamp,
                open=prices["Open"],
                high=prices["High"],
                low=prices["Low"],
                close=prices["Close"],
                volume=volume,
                source_row=source_row,
            )
        except DomainValidationError as exc:
            raise DataValidationError(
                ErrorCode.INVALID_CANDLE_RANGE,
                "row does not satisfy the OHLC candle contract",
                source=source,
                row=source_row,
                column="Open/High/Low/Close",
            ) from exc

        bars.append(bar)
        seen_timestamps.add(timestamp)
        previous_timestamp = timestamp

    if not bars:
        raise DataValidationError(ErrorCode.EMPTY_DATASET, "CSV contains a header but no data rows", source=source)

    return ValidatedRows(tuple(bars), symbol, header_map.has("Volume"))


def _require_string_tuple(value: tuple[str, ...], field: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, tuple) or (not allow_empty and not value) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise DomainValidationError(
            ErrorCode.INVALID_VALUE,
            "must be a tuple of non-empty strings",
            field=field,
        )


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
