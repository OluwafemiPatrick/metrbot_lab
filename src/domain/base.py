"""Shared validation and serialization behavior for domain records."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..errors import DomainValidationError, ErrorCode, SerializationError


class SerializableRecord:
    """Mixin for immutable records with stable JSON-compatible serialization."""

    __slots__ = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible representation."""
        value = to_json_compatible(self)
        if not isinstance(value, dict):  # pragma: no cover - guarded by record contract
            raise SerializationError(ErrorCode.SERIALIZATION_ERROR, "record did not serialize to an object")
        return value

    def to_json(self) -> str:
        """Serialize the record with finite-number enforcement and stable key ordering."""
        try:
            return json.dumps(self.to_dict(), allow_nan=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:  # pragma: no cover - to_dict handles normal failures
            raise SerializationError(ErrorCode.SERIALIZATION_ERROR, "record could not be serialized") from exc


def to_json_compatible(value: Any, *, field: str | None = None) -> Any:
    """Convert supported domain values to JSON-compatible values without lossy coercion."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError(
                ErrorCode.SERIALIZATION_ERROR,
                "non-finite numbers cannot be serialized",
                field=field,
            )
        return value
    if isinstance(value, Enum):
        return to_json_compatible(value.value, field=field)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if is_dataclass(value):
        return {
            item.name: to_json_compatible(getattr(value, item.name), field=item.name)
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise SerializationError(
                ErrorCode.SERIALIZATION_ERROR,
                "mapping keys must be strings",
                field=field,
            )
        result: dict[str, Any] = {}
        for key in sorted(value):
            result[key] = to_json_compatible(value[key], field=key)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [to_json_compatible(item, field=field) for item in value]
    raise SerializationError(
        ErrorCode.SERIALIZATION_ERROR,
        f"unsupported value type: {type(value).__name__}",
        field=field,
    )


def require_datetime(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a datetime", field=field)


def require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a non-empty string", field=field)


def require_finite(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be a finite number", field=field)


def require_positive(value: float, field: str) -> None:
    require_finite(value, field)
    if float(value) <= 0:
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "must be greater than zero", field=field)


def require_non_negative(value: float, field: str) -> None:
    require_finite(value, field)
    if float(value) < 0:
        raise DomainValidationError(ErrorCode.INVALID_VALUE, "must not be negative", field=field)
