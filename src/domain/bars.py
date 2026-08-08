"""Validated internal OHLC bar records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .base import SerializableRecord, require_datetime, require_finite, require_non_negative, require_positive
from ..errors import DomainValidationError, ErrorCode


@dataclass(frozen=True, slots=True)
class Bar(SerializableRecord):
    """One already-normalized candle supplied to later engine phases."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source_row: int | None = None

    def __post_init__(self) -> None:
        require_datetime(self.timestamp, "timestamp")
        for field_name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            require_positive(value, field_name)
        if self.high < self.open or self.high < self.close or self.low > self.open or self.low > self.close:
            raise DomainValidationError(
                ErrorCode.INVALID_VALUE,
                "candle high and low do not contain open and close",
                field="high_low",
            )
        if self.high < self.low:
            raise DomainValidationError(ErrorCode.INVALID_VALUE, "high must not be below low", field="high")
        if self.volume is not None:
            require_non_negative(self.volume, "volume")
        if self.source_row is not None:
            if not isinstance(self.source_row, int) or isinstance(self.source_row, bool) or self.source_row < 1:
                raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a positive row number", field="source_row")
