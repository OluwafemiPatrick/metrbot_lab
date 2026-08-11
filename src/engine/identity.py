"""Deterministic identity helpers for complete backtest runs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..config import effective_configuration
from ..domain.account import RunConfig, freeze_configuration_mapping
from ..domain.base import SerializableRecord, to_json_compatible
from ..errors import ErrorCode, RunIdentityError
from ..strategies.loader import ensure_current_directory_importable
from ..version import __version__


@dataclass(frozen=True, slots=True)
class RunIdentity(SerializableRecord):
    """Immutable reproducibility inputs and identifiers for one run."""

    input_sha256: str
    effective_configuration: Mapping[str, object]
    engine_version: str
    python_version: str
    strategy: str
    custom_strategy_sha256: str | None
    run_fingerprint: str
    run_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("input_sha256", self.input_sha256),
            ("engine_version", self.engine_version),
            ("python_version", self.python_version),
            ("strategy", self.strategy),
            ("run_fingerprint", self.run_fingerprint),
            ("run_id", self.run_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise RunIdentityError(
                    ErrorCode.RUN_FINGERPRINT_ERROR, "identity field must be non-empty text", field=field_name
                )
        if self.custom_strategy_sha256 is not None and (
            not isinstance(self.custom_strategy_sha256, str) or not self.custom_strategy_sha256.strip()
        ):
            raise RunIdentityError(
                ErrorCode.RUN_FINGERPRINT_ERROR,
                "custom strategy source hash must be non-empty text",
                field="custom_strategy_sha256",
            )
        if not isinstance(self.effective_configuration, Mapping):
            raise RunIdentityError(
                ErrorCode.RUN_FINGERPRINT_ERROR,
                "effective configuration must be a mapping",
                field="effective_configuration",
            )
        object.__setattr__(
            self,
            "effective_configuration",
            freeze_configuration_mapping(self.effective_configuration, field_name="effective_configuration"),
        )


def canonical_json(value: object) -> str:
    """Serialize supported identity input into deterministic compact JSON."""
    try:
        compatible = to_json_compatible(value)
        return json.dumps(
            compatible,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except Exception as exc:
        if isinstance(exc, RunIdentityError):
            raise
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "identity input could not be serialized canonically",
        ) from exc


def build_run_identity(
    input_path: str | Path,
    config: RunConfig,
    *,
    engine_version: str = __version__,
    python_version: str | None = None,
) -> RunIdentity:
    """Build a deterministic identity from all material simulation inputs."""
    if not isinstance(config, RunConfig):
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "run identity requires a RunConfig",
            field="config",
        )
    raw_hash = _hash_file(input_path, field="input")
    runtime_version = platform.python_version() if python_version is None else python_version
    custom_source_hash = _hash_custom_strategy_source(config.strategy)
    effective = effective_configuration(config)
    components = {
        "input_sha256": raw_hash,
        "effective_configuration": effective,
        "engine_version": engine_version,
        "python_version": runtime_version,
        "strategy": config.strategy,
        "custom_strategy_sha256": custom_source_hash,
    }
    fingerprint = hashlib.sha256(canonical_json(components).encode("utf-8")).hexdigest()
    return RunIdentity(
        input_sha256=raw_hash,
        effective_configuration=effective,
        engine_version=engine_version,
        python_version=runtime_version,
        strategy=config.strategy,
        custom_strategy_sha256=custom_source_hash,
        run_fingerprint=fingerprint,
        run_id=f"run-{fingerprint[:16]}",
    )


def canonical_result_payload(result: SerializableRecord) -> dict[str, object]:
    """Return a result payload excluding only documented display metadata."""
    payload = result.to_dict()
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata.pop("created_at", None)
        payload["metadata"] = metadata
    return payload


def _hash_file(path: str | Path, *, field: str) -> str:
    try:
        input_path = Path(path)
        digest = hashlib.sha256()
        with input_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, TypeError, ValueError) as exc:
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "input bytes could not be hashed",
            field=field,
        ) from exc


def _hash_custom_strategy_source(reference: str) -> str | None:
    if ":" not in reference:
        return None
    ensure_current_directory_importable()
    module_name, _symbol_name = reference.split(":", 1)
    if not module_name.strip():
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "custom strategy module could not be identified",
            field="strategy",
        )
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ModuleNotFoundError, ValueError) as exc:
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "custom strategy source could not be located",
            field="strategy",
        ) from exc
    if spec is None or spec.origin is None or spec.origin in {"built-in", "frozen"}:
        raise RunIdentityError(
            ErrorCode.RUN_FINGERPRINT_ERROR,
            "custom strategy source is not a readable file",
            field="strategy",
        )
    return _hash_file(spec.origin, field="strategy")
