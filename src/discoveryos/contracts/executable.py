from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from discoveryos.util import digest_bytes, jsonable

from .models import ContractError

if TYPE_CHECKING:
    from discoveryos.runtime.artifacts import ArtifactStore


@dataclass(frozen=True, slots=True)
class CommandSpec:
    argv: tuple[str, ...]
    uses_gpu: bool = False
    uses_device: bool = False

    def __post_init__(self) -> None:
        if not self.argv or any(not argument for argument in self.argv):
            raise ContractError("commands require a non-empty argv vector")


@dataclass(frozen=True, slots=True)
class EnvironmentLock:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path)
        if len(self.sha256) != 64:
            raise ContractError("environment lock requires a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ExecutableCandidateBundle:
    base_repository: str
    base_commit: str
    patch_diff: str
    mutable_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    touched_paths: tuple[str, ...]
    entrypoint: str
    environment_lock: EnvironmentLock
    build_command: CommandSpec
    test_command: CommandSpec
    evaluation_command: CommandSpec
    format_version: str = "executable-candidate-v1"

    def __post_init__(self) -> None:
        if not Path(self.base_repository).is_absolute():
            raise ContractError("base repository must be an absolute path")
        if not self.base_commit or not self.patch_diff.strip():
            raise ContractError("bundle requires a base commit and non-empty patch")
        for path in (*self.mutable_paths, *self.forbidden_paths, *self.touched_paths, self.entrypoint):
            _validate_relative_path(path)
        if len(set(self.touched_paths)) != len(self.touched_paths):
            raise ContractError("touched paths must be unique")
        mutable = tuple(_normalize_path(path) for path in self.mutable_paths)
        forbidden = tuple(_normalize_path(path) for path in self.forbidden_paths)
        for path in self.touched_paths:
            normalized = _normalize_path(path)
            if not _within(normalized, mutable):
                raise ContractError(f"touched path is outside mutable paths: {path}")
            if _within(normalized, forbidden):
                raise ContractError(f"touched path is forbidden: {path}")

    def artifact_payload(self) -> dict[str, Any]:
        value = jsonable(self)
        patch = value.pop("patch_diff")
        return {"candidate_manifest": value, "patch.diff": patch}

    def store(self, artifacts: ArtifactStore) -> str:
        return artifacts.put_json(self.artifact_payload(), metadata={"kind": self.format_version})

    @classmethod
    def from_artifact(cls, artifacts: ArtifactStore, artifact_digest: str) -> "ExecutableCandidateBundle":
        payload = json.loads(artifacts.get_bytes(artifact_digest).decode("utf-8"))
        manifest = payload["candidate_manifest"]
        return cls(
            base_repository=manifest["base_repository"],
            base_commit=manifest["base_commit"],
            patch_diff=payload["patch.diff"],
            mutable_paths=tuple(manifest["mutable_paths"]),
            forbidden_paths=tuple(manifest["forbidden_paths"]),
            touched_paths=tuple(manifest["touched_paths"]),
            entrypoint=manifest["entrypoint"],
            environment_lock=EnvironmentLock(**manifest["environment_lock"]),
            build_command=CommandSpec(tuple(manifest["build_command"]["argv"]), manifest["build_command"]["uses_gpu"], manifest["build_command"]["uses_device"]),
            test_command=CommandSpec(tuple(manifest["test_command"]["argv"]), manifest["test_command"]["uses_gpu"], manifest["test_command"]["uses_device"]),
            evaluation_command=CommandSpec(
                tuple(manifest["evaluation_command"]["argv"]),
                manifest["evaluation_command"]["uses_gpu"],
                manifest["evaluation_command"]["uses_device"],
            ),
            format_version=manifest["format_version"],
        )

    def verify_environment_lock(self, worktree: Path) -> bool:
        path = worktree / Path(self.environment_lock.relative_path)
        return path.is_file() and digest_bytes(path.read_bytes()) == self.environment_lock.sha256


def _normalize_path(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().rstrip("/")


def _validate_relative_path(value: str) -> None:
    normalized = _normalize_path(value)
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or ".git" in path.parts or ":" in normalized:
        raise ContractError(f"unsafe repository-relative path: {value}")


def _within(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)


def path_is_within(path: str, roots: tuple[str, ...]) -> bool:
    return _within(_normalize_path(path), tuple(_normalize_path(root) for root in roots))
