"""Strict project-local strategy registry persisted as deterministic TOML."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib

from ..errors import ErrorCode, StrategyValidationError


PROJECT_REGISTRY_SCHEMA_VERSION = 1
PROJECT_STRATEGIES_DIRECTORY = "strategies"
PROJECT_REGISTRY_FILENAME = "registry.toml"
_PROJECT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$", re.ASCII)
_CLASS_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$", re.ASCII)
_RECORD_KEYS = frozenset({"class_name", "reference", "directory", "description"})


@dataclass(frozen=True, slots=True)
class ProjectStrategyRecord:
    """One immutable project strategy alias and its safe import metadata."""

    name: str
    class_name: str
    reference: str
    directory: str
    description: str

    def __post_init__(self) -> None:
        validate_project_strategy_name(self.name)
        validate_strategy_class_name(self.class_name)
        expected_directory = f"{PROJECT_STRATEGIES_DIRECTORY}/{self.name}"
        expected_reference = f"{PROJECT_STRATEGIES_DIRECTORY}.{self.name}.strategy:{self.class_name}"
        if self.directory != expected_directory:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy directory does not match its name",
                field="directory",
            )
        if self.reference != expected_reference:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy reference does not match its name and class",
                field="reference",
            )
        if not isinstance(self.description, str) or not self.description.strip():
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy description must be non-empty text",
                field="description",
            )

    @classmethod
    def create(cls, name: str, class_name: str, *, description: str | None = None) -> ProjectStrategyRecord:
        """Construct the canonical record for one generated strategy."""
        validate_project_strategy_name(name)
        validate_strategy_class_name(class_name)
        return cls(
            name=name,
            class_name=class_name,
            reference=f"{PROJECT_STRATEGIES_DIRECTORY}.{name}.strategy:{class_name}",
            directory=f"{PROJECT_STRATEGIES_DIRECTORY}/{name}",
            description=(description or f"Project strategy {class_name}.").strip(),
        )


class ProjectStrategyRegistry:
    """Read and atomically replace the registry rooted in one project directory."""

    __slots__ = ("_root",)

    def __init__(self, root: str | Path = ".") -> None:
        if not isinstance(root, (str, Path)):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project root must be a filesystem path",
                field="root",
            )
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def strategies_directory(self) -> Path:
        return self._root / PROJECT_STRATEGIES_DIRECTORY

    @property
    def manifest_path(self) -> Path:
        return self.strategies_directory / PROJECT_REGISTRY_FILENAME

    def list(self) -> tuple[ProjectStrategyRecord, ...]:
        """Return validated records in deterministic name order without importing code."""
        records = self._read_records()
        return tuple(records[name] for name in sorted(records))

    def resolve(self, name: str) -> ProjectStrategyRecord:
        """Resolve one project alias or raise a stable unknown-strategy error."""
        validate_project_strategy_name(name)
        records = self._read_records()
        try:
            return records[name]
        except KeyError as exc:
            raise StrategyValidationError(
                ErrorCode.UNKNOWN_STRATEGY,
                "project strategy is not registered",
                field="name",
            ) from exc

    def add(self, record: ProjectStrategyRecord) -> None:
        """Atomically add one record without overwriting an existing alias."""
        if not isinstance(record, ProjectStrategyRecord):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project registry entries must be ProjectStrategyRecord values",
                field="record",
            )
        records = self._read_records()
        if record.name in records:
            raise StrategyValidationError(
                ErrorCode.DUPLICATE_STRATEGY,
                "project strategy name is already registered",
                field="name",
            )
        records[record.name] = record
        self._write_records(records.values())

    def remove(self, name: str) -> ProjectStrategyRecord:
        """Atomically remove and return one project record."""
        validate_project_strategy_name(name)
        records = self._read_records()
        try:
            removed = records.pop(name)
        except KeyError as exc:
            raise StrategyValidationError(
                ErrorCode.UNKNOWN_STRATEGY,
                "project strategy is not registered",
                field="name",
            ) from exc
        self._write_records(records.values())
        return removed

    def replace(self, records: Iterable[ProjectStrategyRecord]) -> None:
        """Atomically publish a complete validated record set."""
        by_name: dict[str, ProjectStrategyRecord] = {}
        for record in records:
            if not isinstance(record, ProjectStrategyRecord):
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY_REGISTRY,
                    "project registry entries must be ProjectStrategyRecord values",
                    field="record",
                )
            if record.name in by_name:
                raise StrategyValidationError(
                    ErrorCode.DUPLICATE_STRATEGY,
                    "project strategy records must have unique names",
                    field="name",
                )
            by_name[record.name] = record
        self._write_records(by_name.values())

    def _read_records(self) -> dict[str, ProjectStrategyRecord]:
        path = self.manifest_path
        if not path.exists():
            return {}
        if path.is_symlink() or not path.is_file():
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy registry must be a regular file",
                field="registry",
            )
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy registry could not be read",
                field="registry",
            ) from exc
        if set(raw) != {"schema_version", "strategies"}:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy registry has unknown or missing keys",
                field="registry",
            )
        schema_version = raw["schema_version"]
        if isinstance(schema_version, bool) or schema_version != PROJECT_REGISTRY_SCHEMA_VERSION:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy registry schema version is unsupported",
                field="schema_version",
            )
        strategies = raw["strategies"]
        if not isinstance(strategies, Mapping):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategies must be a TOML table",
                field="strategies",
            )
        records: dict[str, ProjectStrategyRecord] = {}
        for name, payload in strategies.items():
            if not isinstance(payload, Mapping) or set(payload) != _RECORD_KEYS:
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY_REGISTRY,
                    "project strategy record has invalid keys",
                    field=name,
                )
            try:
                record = ProjectStrategyRecord(
                    name=name,
                    class_name=payload["class_name"],
                    reference=payload["reference"],
                    directory=payload["directory"],
                    description=payload["description"],
                )
            except TypeError as exc:
                raise StrategyValidationError(
                    ErrorCode.INVALID_STRATEGY_REGISTRY,
                    "project strategy record has invalid value types",
                    field=name,
                ) from exc
            records[name] = record
        return records

    def _write_records(self, records: Iterable[ProjectStrategyRecord]) -> None:
        strategy_root = self.strategies_directory
        if strategy_root.exists() and (strategy_root.is_symlink() or not strategy_root.is_dir()):
            raise StrategyValidationError(
                ErrorCode.UNSAFE_STRATEGY_PATH,
                "project strategies path must be a regular directory",
                field="strategies",
            )
        try:
            strategy_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategies directory could not be created",
                field="strategies",
            ) from exc
        if self.manifest_path.is_symlink():
            raise StrategyValidationError(
                ErrorCode.UNSAFE_STRATEGY_PATH,
                "project strategy registry must not be a symbolic link",
                field="registry",
            )
        serialized = serialize_project_registry(records)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                prefix=".registry-",
                suffix=".toml.tmp",
                dir=strategy_root,
                delete=False,
            ) as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            temporary_path.chmod(0o644)
            os.replace(temporary_path, self.manifest_path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project strategy registry could not be written",
                field="registry",
            ) from exc


def validate_project_strategy_name(name: str) -> str:
    """Validate and return one lowercase project strategy alias."""
    if not isinstance(name, str) or not _PROJECT_NAME_PATTERN.fullmatch(name):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_NAME,
            "project strategy names must be lowercase ASCII identifiers",
            field="name",
        )
    return name


def validate_strategy_class_name(class_name: str) -> str:
    """Validate and return one public generated class name."""
    if not isinstance(class_name, str) or not _CLASS_NAME_PATTERN.fullmatch(class_name):
        raise StrategyValidationError(
            ErrorCode.INVALID_STRATEGY_NAME,
            "strategy class names must use ASCII PascalCase",
            field="class_name",
        )
    return class_name


def serialize_project_registry(records: Iterable[ProjectStrategyRecord]) -> str:
    """Serialize records as deterministic strict TOML."""
    by_name: dict[str, ProjectStrategyRecord] = {}
    for record in records:
        if not isinstance(record, ProjectStrategyRecord):
            raise StrategyValidationError(
                ErrorCode.INVALID_STRATEGY_REGISTRY,
                "project registry entries must be ProjectStrategyRecord values",
                field="record",
            )
        if record.name in by_name:
            raise StrategyValidationError(
                ErrorCode.DUPLICATE_STRATEGY,
                "project strategy records must have unique names",
                field="name",
            )
        by_name[record.name] = record
    lines = [f"schema_version = {PROJECT_REGISTRY_SCHEMA_VERSION}", "", "[strategies]"]
    for name in sorted(by_name):
        record = by_name[name]
        lines.extend(
            (
                "",
                f"[strategies.{record.name}]",
                f"class_name = {json.dumps(record.class_name)}",
                f"reference = {json.dumps(record.reference)}",
                f"directory = {json.dumps(record.directory)}",
                f"description = {json.dumps(record.description)}",
            )
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "PROJECT_REGISTRY_FILENAME",
    "PROJECT_REGISTRY_SCHEMA_VERSION",
    "PROJECT_STRATEGIES_DIRECTORY",
    "ProjectStrategyRecord",
    "ProjectStrategyRegistry",
    "serialize_project_registry",
    "validate_project_strategy_name",
    "validate_strategy_class_name",
]
