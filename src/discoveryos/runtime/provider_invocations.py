from __future__ import annotations

import os
import platform
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationProviderError, GenerationRequest, ProviderGeneration
from discoveryos.runtime.artifacts import ArtifactStore, ImmutableWriteError
from discoveryos.util import digest_json, jsonable, utc_now


class Provider(Protocol):
    def generate(self, request: GenerationRequest) -> ProviderGeneration: ...


class InvocationStateUnknown(RuntimeError):
    """Raised when a provider call was claimed but has no durable terminal record."""


@dataclass(frozen=True, slots=True)
class DurableInvocationResult:
    generation: ProviderGeneration
    recovered: bool


class DurableProviderInvoker:
    """At-most-once provider invocation journal with fail-closed crash recovery.

    A claim is written before provider entry. A terminal record is written immediately
    after a normal provider return or a GenerationProviderError. An orphaned claim is
    deliberately never reclaimed because the external call may still be running or may
    already have incurred unrecorded usage.
    """

    def __init__(self, root: Path, *, namespace: str) -> None:
        self.store = ArtifactStore(root)
        self.namespace = namespace

    def invoke(self, provider: Provider, request: GenerationRequest) -> DurableInvocationResult:
        binding = _request_binding(request)
        invocation_id = digest_json({"namespace": self.namespace, "request": binding})
        claim_name = f"provider-invocations/{invocation_id}/claim.json"
        terminal_name = f"provider-invocations/{invocation_id}/terminal.json"
        terminal_path = self.store.records / terminal_name
        if terminal_path.is_file():
            return self._recover(terminal_path, invocation_id, binding)

        owner_id = str(uuid.uuid4())
        claim = {
            "journal_version": "PROVIDER_INVOCATION_V1",
            "invocation_id": invocation_id,
            "namespace": self.namespace,
            "request_binding": binding,
            "owner": {
                "owner_id": owner_id,
                "pid": os.getpid(),
                "host": platform.node(),
                "claimed_at": utc_now(),
            },
            "attempt": 1,
            "reclaim_policy": "NEVER_RECLAIM_WITHOUT_PROVIDER_IDEMPOTENCY_PROOF",
        }
        try:
            self.store.write_record(claim_name, claim)
        except ImmutableWriteError:
            if terminal_path.is_file():
                return self._recover(terminal_path, invocation_id, binding)
            self._verify_claim(self.store.records / claim_name, invocation_id, binding)
            raise InvocationStateUnknown(
                f"provider invocation {invocation_id} is claimed without a terminal record; retry forbidden"
            )

        started = time.monotonic()
        try:
            generated = provider.generate(request)
        except GenerationProviderError as error:
            elapsed = error.latency_seconds if error.latency_seconds is not None else time.monotonic() - started
            raw_digest = self._put_optional(error.raw_response, "application/json")
            transport_digest = self._put_optional(error.transport_log, "application/x-ndjson")
            terminal = {
                "journal_version": "PROVIDER_INVOCATION_V1",
                "invocation_id": invocation_id,
                "request_binding": binding,
                "owner_id": owner_id,
                "status": "PROVIDER_FAILURE",
                "failure_signature": error.signature,
                "raw_response_digest": raw_digest,
                "transport_log_digest": transport_digest,
                "usage": jsonable(error.usage) if error.usage is not None else None,
                "usage_is_exact": error.usage is not None,
                "latency_seconds": elapsed,
                "completed_at": utc_now(),
            }
            self.store.write_record(terminal_name, terminal)
            raise

        raw_digest = self.store.put_bytes(generated.raw_response.encode("utf-8"), media_type="application/json")
        transport_digest = self._put_optional(generated.transport_log, "application/x-ndjson")
        terminal = {
            "journal_version": "PROVIDER_INVOCATION_V1",
            "invocation_id": invocation_id,
            "request_binding": binding,
            "owner_id": owner_id,
            "status": "SUCCEEDED",
            "raw_response_digest": raw_digest,
            "transport_log_digest": transport_digest,
            "usage": jsonable(generated.usage),
            "usage_is_exact": True,
            "latency_seconds": generated.latency_seconds,
            "provider_version": generated.provider_version,
            "provider_request_id": generated.provider_request_id,
            "refused": generated.refused,
            "completed_at": utc_now(),
        }
        self.store.write_record(terminal_name, terminal)
        return DurableInvocationResult(generation=generated, recovered=False)

    def _recover(self, path: Path, invocation_id: str, binding: dict[str, Any]) -> DurableInvocationResult:
        terminal = _load_json(path)
        if terminal.get("invocation_id") != invocation_id or terminal.get("request_binding") != binding:
            raise RuntimeError("provider invocation terminal binding mismatch")
        status = terminal.get("status")
        raw_response = self._get_optional(terminal.get("raw_response_digest"))
        transport_log = self._get_optional(terminal.get("transport_log_digest"))
        usage_value = terminal.get("usage")
        usage = ResourceUsage(**usage_value) if isinstance(usage_value, dict) else None
        if status == "PROVIDER_FAILURE":
            raise GenerationProviderError(
                str(terminal.get("failure_signature", "RECOVERED_PROVIDER_FAILURE")),
                raw_response=raw_response or "",
                transport_log=transport_log,
                usage=usage,
                latency_seconds=float(terminal.get("latency_seconds", 0.0)),
            )
        if status != "SUCCEEDED" or usage is None or raw_response is None:
            raise RuntimeError("provider invocation terminal record is incomplete")
        generated = ProviderGeneration(
            raw_response=raw_response,
            usage=usage,
            latency_seconds=float(terminal["latency_seconds"]),
            provider_version=str(terminal["provider_version"]),
            provider_request_id=terminal.get("provider_request_id"),
            transport_log=transport_log,
            refused=bool(terminal.get("refused", False)),
        )
        return DurableInvocationResult(generation=generated, recovered=True)

    def _verify_claim(self, path: Path, invocation_id: str, binding: dict[str, Any]) -> None:
        claim = _load_json(path)
        if claim.get("invocation_id") != invocation_id or claim.get("request_binding") != binding:
            raise RuntimeError("provider invocation claim binding mismatch")

    def _put_optional(self, value: str | None, media_type: str) -> str | None:
        if value is None:
            return None
        return self.store.put_bytes(value.encode("utf-8"), media_type=media_type)

    def _get_optional(self, digest: str | None) -> str | None:
        if not digest:
            return None
        return self.store.get_bytes(digest).decode("utf-8")


def assert_no_orphaned_invocations(root: Path) -> None:
    records = root.resolve() / "records" / "provider-invocations"
    if not records.is_dir():
        return
    orphaned = [claim.parent.name for claim in records.glob("*/claim.json") if not (claim.parent / "terminal.json").is_file()]
    if orphaned:
        raise InvocationStateUnknown(
            "provider phase contains claimed invocations without terminal records; new calls forbidden: "
            + ",".join(sorted(orphaned))
        )


def _request_binding(request: GenerationRequest) -> dict[str, Any]:
    value = jsonable(request)
    value.pop("created_at", None)
    return {"generation_id": request.generation_id, "request_digest": digest_json(value)}


def _load_json(path: Path) -> dict[str, Any]:
    import json

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"provider invocation record is not an object: {path}")
    return value
