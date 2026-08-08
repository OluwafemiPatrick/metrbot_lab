"""Public Phase 2 data-boundary contracts."""

from .normalization import (
    CANONICAL_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    HeaderMap,
    normalize_headers,
)

__all__ = [
    "CANONICAL_COLUMNS",
    "HeaderMap",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "normalize_headers",
]
