from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationProviderError, GenerationRequest, ProviderGeneration
from discoveryos.util import digest_json


PATCH_PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["hypothesis", "expected_effects", "target_files", "patch", "risks", "estimated_cost"],
    "properties": {
        "hypothesis": {"type": "string", "minLength": 1},
        "expected_effects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["metric", "effect"],
                "properties": {
                    "metric": {"type": "string"},
                    "effect": {"type": "string"},
                },
            },
        },
        "target_files": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string", "minLength": 1},
        },
        "patch": {"type": "string", "minLength": 1},
        "risks": {"type": "array", "items": {"type": "string"}},
        "estimated_cost": {
            "type": "object",
            "additionalProperties": False,
            "required": ["tokens", "cpu_seconds", "gpu_seconds", "device_seconds", "wall_seconds"],
            "properties": {
                "tokens": {"type": "integer", "minimum": 0},
                "cpu_seconds": {"type": "number", "minimum": 0},
                "gpu_seconds": {"type": "number", "minimum": 0},
                "device_seconds": {"type": "number", "minimum": 0},
                "wall_seconds": {"type": "number", "minimum": 0},
            },
        },
    },
}


class CodexExecProvider:
    """Subscription-capable Codex CLI provider with a read-only generation workspace.

    The provider never points Codex at the candidate repository. The complete
    model-visible context is the frozen prompt supplied on stdin.
    """

    provider_name = "codex_exec"
    minimum_token_reservation = 20_000

    def __init__(
        self,
        *,
        command: tuple[str, ...] = ("codex",),
        model: str,
        timeout_seconds: float = 300.0,
        reasoning_effort: str | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        if not command or not model:
            raise ValueError("Codex provider requires a command and frozen model")
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.output_schema = output_schema or PATCH_PROPOSAL_SCHEMA
        self._provider_version: str | None = None

    @property
    def settings_digest(self) -> str:
        return digest_json(
            {
                "provider": self.provider_name,
                "model": self.model,
                "reasoning_effort": self.reasoning_effort,
                "sandbox": "read-only",
                "ephemeral": True,
                "ignore_user_config": True,
                "ignore_rules": True,
                "output_schema": self.output_schema,
            }
        )

    @property
    def provider_version(self) -> str:
        if self._provider_version is None:
            try:
                result = subprocess.run(
                    (*self.command, "--version"),
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
                self._provider_version = result.stdout.strip() or result.stderr.strip() or "unknown"
            except (OSError, subprocess.SubprocessError):
                self._provider_version = "unknown"
        return self._provider_version

    def generate(self, request: GenerationRequest) -> ProviderGeneration:
        with tempfile.TemporaryDirectory(prefix="discoveryos-generation-") as temporary:
            root = Path(temporary)
            schema_path = root / "patch-proposal.schema.json"
            response_path = root / "response.json"
            schema_path.write_text(json.dumps(self.output_schema, sort_keys=True), encoding="utf-8")
            arguments = [
                *self.command,
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--model",
                self.model,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(response_path),
            ]
            if self.reasoning_effort:
                arguments.extend(("--config", f'model_reasoning_effort="{self.reasoning_effort}"'))
            arguments.append("-")
            environment = os.environ.copy()
            environment.update({"NO_COLOR": "1", "TERM": "dumb"})
            started = time.monotonic()
            try:
                result = subprocess.run(
                    arguments,
                    cwd=root,
                    env=environment,
                    input=request.prompt,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                stdout = _text(error.stdout)
                stderr = _text(error.stderr)
                raise GenerationProviderError(
                    "CODEX_EXEC_TIMEOUT",
                    raw_response=stdout,
                    transport_log=stderr,
                    latency_seconds=time.monotonic() - started,
                ) from error
            except OSError as error:
                raise GenerationProviderError(
                    f"CODEX_EXEC_START_FAILED:{type(error).__name__}",
                    usage=ResourceUsage(),
                    latency_seconds=time.monotonic() - started,
                ) from error
            latency = time.monotonic() - started
            transport_log = result.stdout + ("\nSTDERR\n" + result.stderr if result.stderr else "")
            raw_response = response_path.read_text(encoding="utf-8") if response_path.is_file() else ""
            if result.returncode != 0:
                failed_usage, _ = _usage_from_jsonl(result.stdout)
                raise GenerationProviderError(
                    f"CODEX_EXEC_FAILED:exit={result.returncode}",
                    raw_response=raw_response,
                    transport_log=transport_log,
                    usage=ResourceUsage(
                        llm_input_tokens=failed_usage[0],
                        llm_output_tokens=failed_usage[1],
                        llm_cache_tokens=failed_usage[2],
                        wall_seconds=latency,
                        exit_code=result.returncode,
                    ),
                    latency_seconds=latency,
                )
            usage, request_id = _usage_from_jsonl(result.stdout)
            return ProviderGeneration(
                raw_response=raw_response,
                usage=ResourceUsage(
                    llm_input_tokens=usage[0],
                    llm_output_tokens=usage[1],
                    llm_cache_tokens=usage[2],
                    wall_seconds=latency,
                    exit_code=result.returncode,
                ),
                latency_seconds=latency,
                provider_version=self.provider_version,
                provider_request_id=request_id,
                transport_log=transport_log,
                refused=_looks_refused(result.stdout, raw_response),
            )


def _usage_from_jsonl(value: str) -> tuple[tuple[int, int, int], str | None]:
    usages: list[tuple[int, int, int]] = []
    request_id: str | None = None
    for line in value.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if request_id is None:
            request_id = _find_string(payload, ("request_id", "response_id", "turn_id", "thread_id"))
        usages.extend(_find_usages(payload))
    return (usages[-1] if usages else (0, 0, 0)), request_id


def _find_usages(value: Any) -> list[tuple[int, int, int]]:
    found: list[tuple[int, int, int]] = []
    if isinstance(value, dict):
        input_value = value.get("input_tokens", value.get("inputTokens"))
        output_value = value.get("output_tokens", value.get("outputTokens"))
        if isinstance(input_value, (int, float)) and isinstance(output_value, (int, float)):
            cached = value.get("cached_input_tokens", value.get("cachedInputTokens", 0))
            found.append((int(input_value), int(output_value), int(cached or 0)))
        for item in value.values():
            found.extend(_find_usages(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_usages(item))
    return found


def _find_string(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), str):
                return value[key]
        for item in value.values():
            found = _find_string(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_string(item, keys)
            if found:
                return found
    return None


def _looks_refused(event_stream: str, raw_response: str) -> bool:
    lowered = f"{event_stream}\n{raw_response}".lower()
    return '"refusal"' in lowered or '"refused"' in lowered


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
