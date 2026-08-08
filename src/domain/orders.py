"""Strategy order-intent records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .base import SerializableRecord, require_non_negative, require_positive, require_text
from ..errors import DomainValidationError, ErrorCode


class OrderAction(StrEnum):
    """Actions a strategy may request in the MVP."""

    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"


@dataclass(frozen=True, slots=True)
class OrderIntent(SerializableRecord):
    """One strategy request for the next market event."""

    action: OrderAction
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    tag: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        action = self.action
        if isinstance(action, str):
            try:
                action = OrderAction(action.upper())
            except ValueError as exc:
                raise DomainValidationError(
                    ErrorCode.INVALID_ACTION,
                    "unsupported order action",
                    field="action",
                ) from exc
            object.__setattr__(self, "action", action)
        elif not isinstance(action, OrderAction):
            raise DomainValidationError(ErrorCode.INVALID_ACTION, "unsupported order action", field="action")

        if self.quantity is not None:
            require_positive(self.quantity, "quantity")
        for field_name, value in (("stop_loss", self.stop_loss), ("take_profit", self.take_profit)):
            if value is not None:
                require_positive(value, field_name)
        for field_name, value in (("tag", self.tag), ("reason", self.reason)):
            if value is not None:
                require_text(value, field_name)

        if action is OrderAction.CLOSE and any(
            value is not None for value in (self.quantity, self.stop_loss, self.take_profit)
        ):
            raise DomainValidationError(
                ErrorCode.INVALID_STATE,
                "CLOSE intents cannot carry quantity or protective levels",
                field="action",
            )
