"""Single signed net-position contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .base import SerializableRecord, require_datetime, require_finite, require_positive, require_text
from ..errors import DomainValidationError, ErrorCode


@dataclass(frozen=True, slots=True)
class Position(SerializableRecord):
    """One flat, long, or short position; lifecycle transitions belong to later phases."""

    quantity: float = 0.0
    position_id: str | None = None
    symbol: str | None = None
    entry_timestamp: datetime | None = None
    reference_entry_price: float | None = None
    effective_entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy_tag: str | None = None

    def __post_init__(self) -> None:
        require_finite(self.quantity, "quantity")
        if self.quantity == 0:
            if any(
                value is not None
                for value in (
                    self.position_id,
                    self.symbol,
                    self.entry_timestamp,
                    self.reference_entry_price,
                    self.effective_entry_price,
                    self.stop_loss,
                    self.take_profit,
                    self.strategy_tag,
                )
            ):
                raise DomainValidationError(
                    ErrorCode.INVALID_STATE,
                    "flat positions cannot carry entry metadata",
                    field="quantity",
                )
            return

        if not isinstance(self.position_id, str) or not self.position_id.strip():
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "open positions require identifiers",
                field="position_id",
            )
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "open positions require identifiers",
                field="symbol",
            )
        require_datetime(self.entry_timestamp, "entry_timestamp")
        require_positive(self.reference_entry_price, "reference_entry_price")
        require_positive(self.effective_entry_price, "effective_entry_price")
        for field_name, value in (("stop_loss", self.stop_loss), ("take_profit", self.take_profit)):
            if value is not None:
                require_positive(value, field_name)
        if self.strategy_tag is not None:
            require_text(self.strategy_tag, "strategy_tag")

    @classmethod
    def flat(cls) -> "Position":
        """Return the canonical flat position."""
        return cls()

    @property
    def direction(self) -> str:
        """Return the stable human-readable position direction."""
        if self.quantity > 0:
            return "LONG"
        if self.quantity < 0:
            return "SHORT"
        return "FLAT"
