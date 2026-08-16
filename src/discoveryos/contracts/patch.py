from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from discoveryos.util import digest_json, pairs, unpairs, utc_now

from .models import ContractError, EvidenceRecord, EvidenceValidity, FailureKind, ResourceBudget, ResourceUsage


class GenerationKind(str, Enum):
    PROPOSAL = "PROPOSAL"
    MECHANICAL_REPAIR = "MECHANICAL_REPAIR"


class GenerationStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    REFUSED = "REFUSED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


MECHANICAL_REPAIR_FAILURES = frozenset(
    {
        FailureKind.PATCH_REJECTED,
        FailureKind.BUILD_FAILED,
        FailureKind.TEST_FAILED,
        FailureKind.TIMEOUT,
    }
)


@dataclass(frozen=True, slots=True)
class PatchProposal:
    hypothesis: str
    expected_effects: tuple[tuple[str, Any], ...]
    target_files: tuple[str, ...]
    patch: str
    risks: tuple[str, ...]
    estimated_cost: ResourceBudget

    def __post_init__(self) -> None:
        if not self.hypothesis.strip() or not self.patch.strip():
            raise ContractError("patch proposal requires a hypothesis and non-empty patch")
        if not 1 <= len(self.target_files) <= 3:
            raise ContractError("patch proposal must target between one and three files")
        if len(set(self.target_files)) != len(self.target_files):
            raise ContractError("patch proposal target files must be unique")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PatchProposal":
        required = {"hypothesis", "expected_effects", "target_files", "patch", "risks", "estimated_cost"}
        if set(value) != required:
            missing = sorted(required - set(value))
            extra = sorted(set(value) - required)
            raise ContractError(f"invalid patch proposal fields: missing={missing}:extra={extra}")
        raw_effects = value["expected_effects"]
        if isinstance(raw_effects, dict):
            effects = raw_effects
        elif isinstance(raw_effects, list) and all(
            isinstance(item, dict) and set(item) == {"metric", "effect"} for item in raw_effects
        ):
            grouped: dict[str, list[str]] = {}
            for item in raw_effects:
                grouped.setdefault(str(item["metric"]), []).append(str(item["effect"]))
            effects = {metric: "; ".join(values) for metric, values in grouped.items()}
        else:
            raise ContractError("expected_effects must be an object or metric/effect array")
        if not isinstance(value["target_files"], list) or not isinstance(value["risks"], list):
            raise ContractError("target_files and risks must be arrays")
        if not isinstance(value["estimated_cost"], dict):
            raise ContractError("estimated_cost must be an object")
        return cls(
            hypothesis=str(value["hypothesis"]),
            expected_effects=pairs(effects),
            target_files=tuple(str(item) for item in value["target_files"]),
            patch=str(value["patch"]),
            risks=tuple(str(item) for item in value["risks"]),
            estimated_cost=ResourceBudget(**value["estimated_cost"]),
        )

    def expected_effect_dict(self) -> dict[str, Any]:
        return unpairs(self.expected_effects)


@dataclass(frozen=True, slots=True)
class MechanicalDiagnostic:
    failure_kind: FailureKind
    failure_signature: str
    diagnostic_excerpt: str

    def __post_init__(self) -> None:
        if self.failure_kind not in MECHANICAL_REPAIR_FAILURES:
            raise ContractError(f"failure is not eligible for mechanical repair: {self.failure_kind.value}")
        if not self.failure_signature.strip():
            raise ContractError("mechanical diagnostic requires a failure signature")

    @classmethod
    def from_evidence(cls, evidence: EvidenceRecord, diagnostic_excerpt: str) -> "MechanicalDiagnostic":
        if evidence.validity is EvidenceValidity.VALID or evidence.failure_kind not in MECHANICAL_REPAIR_FAILURES:
            raise ContractError("only mechanical execution failures are repairable")
        return cls(
            failure_kind=evidence.failure_kind,
            failure_signature=evidence.failure_signature or evidence.failure_kind.value,
            diagnostic_excerpt=diagnostic_excerpt,
        )


@dataclass(frozen=True, slots=True)
class GenerationContext:
    problem_contract: tuple[tuple[str, Any], ...]
    parent_candidate: tuple[tuple[str, Any], ...]
    mutable_files: tuple[tuple[str, str], ...]
    development_evidence_summary: str
    failure_signature: str | None
    semantic_delta_memory: tuple[str, ...]
    remaining_budget: ResourceBudget
    mechanical_diagnostic: MechanicalDiagnostic | None = None

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    generation_id: str
    kind: GenerationKind
    root_generation_id: str
    provider: str
    model: str
    provider_settings_digest: str
    prompt_template_digest: str
    context_digest: str
    prompt: str
    token_ceiling: int
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        kind: GenerationKind,
        root_generation_id: str | None,
        provider: str,
        model: str,
        provider_settings_digest: str,
        prompt_template_digest: str,
        context_digest: str,
        prompt: str,
        token_ceiling: int,
    ) -> "GenerationRequest":
        identity = {
            "kind": kind,
            "root_generation_id": root_generation_id,
            "provider": provider,
            "model": model,
            "provider_settings_digest": provider_settings_digest,
            "prompt_template_digest": prompt_template_digest,
            "context_digest": context_digest,
            "prompt": prompt,
            "token_ceiling": token_ceiling,
        }
        generation_id = f"gen_{digest_json(identity)[:24]}"
        return cls(
            generation_id=generation_id,
            kind=kind,
            root_generation_id=root_generation_id or generation_id,
            provider=provider,
            model=model,
            provider_settings_digest=provider_settings_digest,
            prompt_template_digest=prompt_template_digest,
            context_digest=context_digest,
            prompt=prompt,
            token_ceiling=token_ceiling,
        )


@dataclass(frozen=True, slots=True)
class GenerationProvenance:
    generation_id: str
    kind: GenerationKind
    root_generation_id: str
    provider: str
    model: str
    provider_version: str
    provider_settings_digest: str
    provider_request_id: str | None
    prompt_template_digest: str
    context_digest: str
    request_artifact_digest: str
    raw_response_digest: str
    transport_log_digest: str | None
    usage: ResourceUsage
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    generation_id: str
    kind: GenerationKind
    root_generation_id: str
    parent_candidate_id: str
    status: GenerationStatus
    request_artifact_digest: str
    raw_response_digest: str | None
    provenance_artifact_digest: str | None
    candidate_id: str | None
    candidate_artifact_digest: str | None
    usage: ResourceUsage
    failure_signature: str | None
    usage_is_exact: bool = True
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ProviderGeneration:
    raw_response: str
    usage: ResourceUsage
    latency_seconds: float
    provider_version: str
    provider_request_id: str | None = None
    transport_log: str | None = None
    refused: bool = False


class GenerationProviderError(RuntimeError):
    def __init__(
        self,
        signature: str,
        *,
        raw_response: str = "",
        transport_log: str | None = None,
        usage: ResourceUsage | None = None,
        latency_seconds: float | None = None,
    ) -> None:
        super().__init__(signature)
        self.signature = signature
        self.raw_response = raw_response
        self.transport_log = transport_log
        self.usage = usage
        self.latency_seconds = latency_seconds
