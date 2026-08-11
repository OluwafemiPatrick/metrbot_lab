"""Pure CSV header normalization for the Phase 2 data boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from ..errors import DataValidationError, ErrorCode

REQUIRED_COLUMNS = ("Timestamp", "Open", "High", "Low", "Close")
OPTIONAL_COLUMNS = ("Volume", "Symbol")
CANONICAL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

_CANONICAL_BY_KEY = {column.casefold(): column for column in CANONICAL_COLUMNS}


@dataclass(frozen=True, slots=True)
class HeaderMap:
    """Immutable mapping from canonical column names to source positions."""

    columns: tuple[str, ...]
    positions: Mapping[str, int]
    extra_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.columns, tuple):
            raise TypeError("columns must be a tuple")
        if not isinstance(self.positions, Mapping):
            raise TypeError("positions must be a mapping")
        if not isinstance(self.extra_columns, tuple):
            raise TypeError("extra_columns must be a tuple")
        object.__setattr__(self, "positions", MappingProxyType(dict(self.positions)))

    def index(self, column: str) -> int:
        """Return the source index for a required or optional canonical column."""
        try:
            return self.positions[column]
        except KeyError as exc:
            raise KeyError(f"column is not present: {column}") from exc

    def has(self, column: str) -> bool:
        """Return whether a canonical column is present."""
        return column in self.positions


def normalize_headers(headers: Sequence[str], *, source: str = "<input>") -> HeaderMap:
    """Normalize and validate CSV headers without parsing any data rows."""
    if not headers:
        raise DataValidationError(ErrorCode.EMPTY_FILE, "CSV input has no header", source=source)

    columns: list[str] = []
    positions: dict[str, int] = {}
    extra_columns: list[str] = []
    seen_keys: set[str] = set()

    for index, raw_header in enumerate(headers):
        if not isinstance(raw_header, str):
            raise DataValidationError(
                ErrorCode.EMPTY_HEADER,
                "header must be text",
                source=source,
                row=1,
            )
        cleaned = raw_header.strip()
        if not cleaned:
            raise DataValidationError(
                ErrorCode.EMPTY_HEADER,
                "header must not be blank",
                source=source,
                row=1,
            )

        key = cleaned.casefold()
        if key in seen_keys:
            raise DataValidationError(
                ErrorCode.DUPLICATE_COLUMN,
                "duplicate header after normalization",
                source=source,
                row=1,
                column=cleaned,
            )
        seen_keys.add(key)

        canonical = _CANONICAL_BY_KEY.get(key, cleaned)
        columns.append(canonical)
        if canonical in _CANONICAL_BY_KEY.values():
            positions[canonical] = index
        else:
            extra_columns.append(cleaned)

    missing = next((column for column in REQUIRED_COLUMNS if column not in positions), None)
    if missing is not None:
        raise DataValidationError(
            ErrorCode.MISSING_COLUMN,
            "required column is missing",
            source=source,
            row=1,
            column=missing,
        )

    return HeaderMap(tuple(columns), positions, tuple(extra_columns))
