from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from discoveryos.util import canonical_json, digest_bytes, digest_json, jsonable, utc_now


class ImmutableWriteError(RuntimeError):
    pass


class ArtifactStore:
    """Content-addressed immutable objects plus create-once named records."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.objects = self.root / "objects"
        self.records = self.root / "records"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.records.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, payload: bytes, *, media_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> str:
        digest = digest_bytes(payload)
        object_dir = self.objects / digest[:2] / digest
        object_dir.mkdir(parents=True, exist_ok=True)
        payload_path = object_dir / "payload"
        if payload_path.exists():
            if digest_bytes(payload_path.read_bytes()) != digest:
                raise ImmutableWriteError(f"artifact hash collision: {digest}")
            return digest
        self._create_once(payload_path, payload)
        manifest = {
            "sha256": digest,
            "size": len(payload),
            "media_type": media_type,
            "metadata": metadata or {},
            "created_at": utc_now(),
        }
        self._create_once(object_dir / "manifest.json", (canonical_json(manifest) + "\n").encode("utf-8"))
        return digest

    def put_json(self, value: Any, *, metadata: dict[str, Any] | None = None) -> str:
        return self.put_bytes((canonical_json(value) + "\n").encode("utf-8"), media_type="application/json", metadata=metadata)

    def get_bytes(self, digest: str) -> bytes:
        path = self.objects / digest[:2] / digest / "payload"
        payload = path.read_bytes()
        if digest_bytes(payload) != digest:
            raise ImmutableWriteError(f"artifact integrity failure: {digest}")
        return payload

    def write_record(self, relative_path: str, value: Any) -> Path:
        normalized = Path(relative_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("record path must remain inside the record store")
        path = self.records / normalized
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (canonical_json(jsonable(value)) + "\n").encode("utf-8")
        if path.exists():
            if path.read_bytes() == payload:
                return path
            raise ImmutableWriteError(f"create-once record already exists: {relative_path}")
        self._create_once(path, payload)
        return path

    @staticmethod
    def _create_once(path: Path, payload: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
