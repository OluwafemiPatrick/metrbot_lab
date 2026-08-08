"""CSV file access and composition of the Phase 2 validation pipeline."""

from __future__ import annotations

import csv
from pathlib import Path

from ..errors import DataValidationError, ErrorCode
from .normalization import normalize_headers
from .validation import LoadedDataset, ValidationReport, validate_rows


def load_csv(path: str | Path) -> LoadedDataset:
    """Load one CSV file into validated bars and a deterministic input report."""
    input_path = Path(path)
    source = _safe_source_label(input_path)
    if not input_path.exists():
        raise DataValidationError(ErrorCode.FILE_NOT_FOUND, "CSV input file was not found", source=source)
    if not input_path.is_file():
        raise DataValidationError(ErrorCode.NOT_A_FILE, "CSV input path is not a regular file", source=source)

    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                headers = next(reader, None)
                header_map = normalize_headers(headers or [], source=source)
                validated = validate_rows(reader, header_map, source=source)
            except csv.Error as exc:
                raise DataValidationError(
                    ErrorCode.MALFORMED_CSV,
                    "CSV parser rejected the input",
                    source=source,
                ) from exc
    except UnicodeDecodeError as exc:
        raise DataValidationError(
            ErrorCode.INVALID_ENCODING,
            "CSV input is not valid UTF-8 text",
            source=source,
        ) from exc
    except PermissionError as exc:
        raise DataValidationError(
            ErrorCode.UNREADABLE_FILE,
            "CSV input file could not be read",
            source=source,
        ) from exc
    except OSError as exc:
        raise DataValidationError(
            ErrorCode.UNREADABLE_FILE,
            "CSV input file could not be read",
            source=source,
        ) from exc

    warnings = ()
    if header_map.extra_columns:
        warnings = (f"ignored extra columns: {', '.join(header_map.extra_columns)}",)
    bars = validated.bars
    report = ValidationReport(
        source_path=source,
        row_count=len(bars),
        first_timestamp=bars[0].timestamp,
        last_timestamp=bars[-1].timestamp,
        symbol=validated.symbol,
        volume_present=validated.volume_present,
        columns=header_map.columns,
        extra_columns=header_map.extra_columns,
        warnings=warnings,
    )
    return LoadedDataset(bars=bars, report=report)


def _safe_source_label(path: Path) -> str:
    """Return a user-useful source label without exposing unrelated host paths."""
    if path.is_absolute():
        return path.name or "<input>"
    return str(path)
