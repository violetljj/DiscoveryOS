from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(jsonable(item) for item in value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def pairs(mapping: dict[str, Any] | None = None, **kwargs: Any) -> tuple[tuple[str, Any], ...]:
    merged = dict(mapping or {})
    merged.update(kwargs)
    return tuple(sorted(merged.items()))


def unpairs(value: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return dict(value)


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
