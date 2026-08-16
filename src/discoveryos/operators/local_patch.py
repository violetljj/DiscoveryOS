from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from discoveryos.contracts.executable import CommandSpec, EnvironmentLock, ExecutableCandidateBundle, path_is_within
from discoveryos.contracts.models import CandidateSpec, ContractError, ProblemContract, ResourceBudget, ResourceUsage
from discoveryos.contracts.patch import (
    GenerationContext,
    GenerationKind,
    GenerationProviderError,
    GenerationProvenance,
    GenerationRecord,
    GenerationRequest,
    GenerationStatus,
    MechanicalDiagnostic,
    PatchProposal,
    ProviderGeneration,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import BudgetExceeded, EvidenceLedger
from discoveryos.util import canonical_json, digest_bytes, digest_json, jsonable, pairs, utc_now


LOCAL_PATCH_PROMPT_TEMPLATE = """You are a bounded local-patch operator. Return exactly one JSON object matching the supplied schema.

Scientific scope:
- Form one explicit hypothesis and one local unified diff.
- Touch only TARGET_FILES and at most three files.
- Never modify evaluators, tests, contracts, data, build policy, or forbidden paths.
- Treat development evidence as observations, never as final-blind evidence.
- Report risks and estimated resource cost honestly.
- Do not call tools, inspect the filesystem, or seek context beyond FROZEN_CONTEXT_JSON.
- The patch must be a standard unified diff relative to the visible parent file, with `--- a/path`,
  `+++ b/path`, and a numbered hunk header such as `@@ -1,3 +1,5 @@`.
- A bare `@@` header, `*** Begin Patch`, `*** Update File`, prose, or Markdown fence is invalid.

Mechanical repair scope:
- When GENERATION_KIND is MECHANICAL_REPAIR, fix only the supplied mechanical diagnostic.
- Do not make an additional scientific or metric-seeking change.

GENERATION_KIND
{generation_kind}

FROZEN_CONTEXT_JSON
{context_json}
"""


class PatchProvider(Protocol):
    provider_name: str
    model: str

    def generate(self, request: GenerationRequest) -> ProviderGeneration: ...


@dataclass(frozen=True, slots=True)
class CandidateBuildSpec:
    base_repository: Path
    base_commit: str
    entrypoint: str
    environment_lock: EnvironmentLock
    build_command: CommandSpec
    test_command: CommandSpec
    evaluation_command: CommandSpec
    parent_patch_stack: tuple[str, ...] = ()
    parent_touched_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.base_repository.is_absolute():
            raise ContractError("candidate build repository must be absolute")


@dataclass(frozen=True, slots=True)
class LocalPatchResult:
    record: GenerationRecord
    proposal: PatchProposal | None
    candidate: CandidateSpec | None


class LocalPatchOperator:
    operator_id = "bounded_llm_local_patch_v1"

    def __init__(
        self,
        *,
        provider: PatchProvider,
        artifacts: ArtifactStore,
        ledger: EvidenceLedger,
        contract: ProblemContract,
        strategy_id: str = "iterative_local_patch",
    ) -> None:
        self.provider = provider
        self.artifacts = artifacts
        self.ledger = ledger
        self.contract = contract
        self.strategy_id = strategy_id

    def propose(
        self,
        *,
        parent: CandidateSpec,
        mutable_files: dict[str, str],
        development_evidence_summary: str,
        failure_signature: str | None,
        semantic_delta_memory: tuple[str, ...],
        remaining_budget: ResourceBudget,
        build: CandidateBuildSpec,
    ) -> LocalPatchResult:
        context = self._context(
            parent=parent,
            mutable_files=mutable_files,
            development_evidence_summary=development_evidence_summary,
            failure_signature=failure_signature,
            semantic_delta_memory=semantic_delta_memory,
            remaining_budget=remaining_budget,
            mechanical_diagnostic=None,
        )
        return self._generate(
            kind=GenerationKind.PROPOSAL,
            root_generation_id=None,
            parent=parent,
            context=context,
            remaining_budget=remaining_budget,
            build=build,
        )

    def repair(
        self,
        *,
        generation_id: str,
        parent: CandidateSpec,
        mutable_files: dict[str, str],
        diagnostic: MechanicalDiagnostic,
        semantic_delta_memory: tuple[str, ...],
        remaining_budget: ResourceBudget,
        build: CandidateBuildSpec,
    ) -> LocalPatchResult:
        original = self.ledger.get_generation(generation_id)
        if original.status is not GenerationStatus.SUCCEEDED or original.candidate_id != parent.candidate_id:
            raise ContractError("mechanical repair requires the materialized candidate from a successful generation")
        if self.ledger.repair_for_root(original.root_generation_id) is not None:
            raise ContractError("only one mechanical repair is allowed per root generation")
        context = self._context(
            parent=parent,
            mutable_files=mutable_files,
            development_evidence_summary="",
            failure_signature=diagnostic.failure_signature,
            semantic_delta_memory=semantic_delta_memory,
            remaining_budget=remaining_budget,
            mechanical_diagnostic=diagnostic,
        )
        return self._generate(
            kind=GenerationKind.MECHANICAL_REPAIR,
            root_generation_id=original.root_generation_id,
            parent=parent,
            context=context,
            remaining_budget=remaining_budget,
            build=build,
        )

    def _context(
        self,
        *,
        parent: CandidateSpec,
        mutable_files: dict[str, str],
        development_evidence_summary: str,
        failure_signature: str | None,
        semantic_delta_memory: tuple[str, ...],
        remaining_budget: ResourceBudget,
        mechanical_diagnostic: MechanicalDiagnostic | None,
    ) -> GenerationContext:
        if not mutable_files:
            raise ContractError("local patch context requires mutable file contents")
        for path in mutable_files:
            if not path_is_within(path, self.contract.mutable_paths) or path_is_within(path, self.contract.forbidden_paths):
                raise ContractError(f"model-visible file is outside the mutable contract: {path}")
        contract_view = {
            "contract_id": self.contract.contract_id,
            "version": self.contract.version,
            "digest": self.contract.digest,
            "question": self.contract.question,
            "mutable_paths": self.contract.mutable_paths,
            "forbidden_paths": self.contract.forbidden_paths,
            "fidelities": tuple(item.value for item in self.contract.fidelities),
            "metrics": tuple(jsonable(item) for item in self.contract.metrics),
            "hard_constraints": tuple(jsonable(item) for item in self.contract.hard_constraints),
            "claim_ceiling": self.contract.claim_ceiling.value,
        }
        parent_view = {
            "candidate_id": parent.candidate_id,
            "parent_ids": parent.parent_ids,
            "semantic_delta": parent.semantic_delta,
            "expected_effects": parent.expected_effects,
            "parameters": parent.parameters,
        }
        return GenerationContext(
            problem_contract=pairs(contract_view),
            parent_candidate=pairs(parent_view),
            mutable_files=tuple(sorted(mutable_files.items())),
            development_evidence_summary=development_evidence_summary,
            failure_signature=failure_signature,
            semantic_delta_memory=semantic_delta_memory,
            remaining_budget=remaining_budget,
            mechanical_diagnostic=mechanical_diagnostic,
        )

    def _generate(
        self,
        *,
        kind: GenerationKind,
        root_generation_id: str | None,
        parent: CandidateSpec,
        context: GenerationContext,
        remaining_budget: ResourceBudget,
        build: CandidateBuildSpec,
    ) -> LocalPatchResult:
        prompt = LOCAL_PATCH_PROMPT_TEMPLATE.format(
            generation_kind=kind.value,
            context_json=canonical_json(context),
        )
        request = GenerationRequest.create(
            kind=kind,
            root_generation_id=root_generation_id,
            provider=self.provider.provider_name,
            model=self.provider.model,
            provider_settings_digest=getattr(
                self.provider,
                "settings_digest",
                digest_json({"provider": self.provider.provider_name, "model": self.provider.model}),
            ),
            prompt_template_digest=digest_bytes(LOCAL_PATCH_PROMPT_TEMPLATE.encode("utf-8")),
            context_digest=context.digest,
            prompt=prompt,
            token_ceiling=remaining_budget.tokens,
        )
        request_digest = self.artifacts.put_json(request, metadata={"kind": "llm-generation-request-v1"})
        reservation_id = f"reservation_{request.generation_id}"
        try:
            reservation, _ = self.ledger.reserve_resources(
                reservation_id=reservation_id,
                experiment_id=request.generation_id,
                requested=remaining_budget,
                limit=self.contract.budget,
            )
        except BudgetExceeded as error:
            record = self._record_failure(
                request=request,
                parent=parent,
                request_digest=request_digest,
                status=GenerationStatus.BUDGET_EXHAUSTED,
                signature=str(error),
            )
            self.ledger.record_resource_rejection(
                reservation_id=reservation_id,
                experiment_id=request.generation_id,
                requested=remaining_budget,
                exceeded_dimensions=_budget_dimensions(str(error)),
            )
            return LocalPatchResult(record, None, None)

        started = time.monotonic()
        try:
            generated = self.provider.generate(request)
        except GenerationProviderError as error:
            elapsed = error.latency_seconds if error.latency_seconds is not None else time.monotonic() - started
            usage_is_exact = error.usage is not None
            usage = error.usage or ResourceUsage(
                llm_input_tokens=request.token_ceiling,
                wall_seconds=elapsed,
            )
            self.ledger.reconcile_resources(reservation, usage, self.contract.budget)
            raw_digest = self._put_raw(error.raw_response) if error.raw_response else None
            if error.transport_log:
                self.artifacts.put_bytes(
                    error.transport_log.encode("utf-8"),
                    media_type="application/x-ndjson",
                    metadata={"kind": "llm-provider-transport-v1", "generation_id": request.generation_id},
                )
            record = self._record_failure(
                request=request,
                parent=parent,
                request_digest=request_digest,
                status=GenerationStatus.PROVIDER_FAILURE,
                signature=error.signature,
                raw_response_digest=raw_digest,
                usage=usage,
                usage_is_exact=usage_is_exact,
            )
            return LocalPatchResult(record, None, None)

        raw_digest = self._put_raw(generated.raw_response)
        transport_digest = (
            self.artifacts.put_bytes(
                generated.transport_log.encode("utf-8"),
                media_type="application/x-ndjson",
                metadata={"kind": "llm-provider-transport-v1", "generation_id": request.generation_id},
            )
            if generated.transport_log is not None
            else None
        )
        reconciliation = self.ledger.reconcile_resources(reservation, generated.usage, self.contract.budget)
        provenance = GenerationProvenance(
            generation_id=request.generation_id,
            kind=request.kind,
            root_generation_id=request.root_generation_id,
            provider=request.provider,
            model=request.model,
            provider_version=generated.provider_version,
            provider_settings_digest=request.provider_settings_digest,
            provider_request_id=generated.provider_request_id,
            prompt_template_digest=request.prompt_template_digest,
            context_digest=request.context_digest,
            request_artifact_digest=request_digest,
            raw_response_digest=raw_digest,
            transport_log_digest=transport_digest,
            usage=generated.usage,
            latency_seconds=generated.latency_seconds,
        )
        provenance_digest = self.artifacts.put_json(provenance, metadata={"kind": "llm-generation-provenance-v1"})
        if reconciliation.budget_exhausted:
            record = self._record_failure(
                request=request,
                parent=parent,
                request_digest=request_digest,
                status=GenerationStatus.BUDGET_EXHAUSTED,
                signature="GENERATION_BUDGET_EXCEEDED:" + ",".join(reconciliation.exceeded_dimensions),
                raw_response_digest=raw_digest,
                provenance_digest=provenance_digest,
                usage=generated.usage,
            )
            return LocalPatchResult(record, None, None)
        if generated.refused:
            record = self._record_failure(
                request=request,
                parent=parent,
                request_digest=request_digest,
                status=GenerationStatus.REFUSED,
                signature="PROVIDER_REFUSAL",
                raw_response_digest=raw_digest,
                provenance_digest=provenance_digest,
                usage=generated.usage,
            )
            return LocalPatchResult(record, None, None)
        try:
            payload = json.loads(generated.raw_response)
            if not isinstance(payload, dict):
                raise ContractError("patch proposal response must be an object")
            proposal = PatchProposal.from_dict(payload)
            self._validate_proposal(proposal, context)
        except (json.JSONDecodeError, TypeError, ValueError, ContractError) as error:
            record = self._record_failure(
                request=request,
                parent=parent,
                request_digest=request_digest,
                status=GenerationStatus.INVALID_RESPONSE,
                signature=f"INVALID_PATCH_PROPOSAL:{type(error).__name__}:{error}",
                raw_response_digest=raw_digest,
                provenance_digest=provenance_digest,
                usage=generated.usage,
            )
            return LocalPatchResult(record, None, None)

        bundle = ExecutableCandidateBundle(
            base_repository=str(build.base_repository.resolve()),
            base_commit=build.base_commit,
            patch_diff=proposal.patch,
            mutable_paths=self.contract.mutable_paths,
            forbidden_paths=self.contract.forbidden_paths,
            touched_paths=tuple(sorted(set(build.parent_touched_paths).union(proposal.target_files))),
            entrypoint=build.entrypoint,
            environment_lock=build.environment_lock,
            build_command=build.build_command,
            test_command=build.test_command,
            evaluation_command=build.evaluation_command,
            generation_provenance_digest=provenance_digest,
            patch_stack=(*build.parent_patch_stack, proposal.patch),
            format_version="executable-candidate-v2",
        )
        candidate_artifact_digest = bundle.store(self.artifacts)
        candidate = CandidateSpec.create(
            artifact_digest=candidate_artifact_digest,
            parent_ids=(parent.candidate_id,),
            operator_id=self.operator_id,
            strategy_id="mechanical_repair" if kind is GenerationKind.MECHANICAL_REPAIR else self.strategy_id,
            hypothesis_id=f"hyp_{digest_json(proposal.hypothesis)[:20]}",
            parameters={
                "generation_id": request.generation_id,
                "generation_provenance_digest": provenance_digest,
                "estimated_cost": jsonable(proposal.estimated_cost),
                "risks": proposal.risks,
            },
            semantic_delta=proposal.hypothesis,
            expected_effects=proposal.expected_effect_dict(),
            environment_digest=build.environment_lock.sha256,
        )
        self.ledger.add_candidate(candidate)
        record = GenerationRecord(
            generation_id=request.generation_id,
            kind=request.kind,
            root_generation_id=request.root_generation_id,
            parent_candidate_id=parent.candidate_id,
            status=GenerationStatus.SUCCEEDED,
            request_artifact_digest=request_digest,
            raw_response_digest=raw_digest,
            provenance_artifact_digest=provenance_digest,
            candidate_id=candidate.candidate_id,
            candidate_artifact_digest=candidate_artifact_digest,
            usage=generated.usage,
            failure_signature=None,
            usage_is_exact=True,
            created_at=utc_now(),
        )
        self.ledger.add_generation(record)
        self.ledger.record_event("LLM_GENERATION_RECORDED", jsonable(record))
        return LocalPatchResult(record, proposal, candidate)

    def _validate_proposal(self, proposal: PatchProposal, context: GenerationContext) -> None:
        visible = {path for path, _ in context.mutable_files}
        if set(proposal.target_files) - visible:
            raise ContractError("proposal targets a file absent from the frozen mutable-file context")
        for path in proposal.target_files:
            if not path_is_within(path, self.contract.mutable_paths) or path_is_within(path, self.contract.forbidden_paths):
                raise ContractError(f"proposal target violates contract path policy: {path}")
        touched = _touched_paths_from_patch(proposal.patch)
        if touched != tuple(sorted(proposal.target_files)):
            raise ContractError(f"patch headers do not match target_files: headers={touched}")

    def _record_failure(
        self,
        *,
        request: GenerationRequest,
        parent: CandidateSpec,
        request_digest: str,
        status: GenerationStatus,
        signature: str,
        raw_response_digest: str | None = None,
        provenance_digest: str | None = None,
        usage: ResourceUsage | None = None,
        usage_is_exact: bool = True,
    ) -> GenerationRecord:
        record = GenerationRecord(
            generation_id=request.generation_id,
            kind=request.kind,
            root_generation_id=request.root_generation_id,
            parent_candidate_id=parent.candidate_id,
            status=status,
            request_artifact_digest=request_digest,
            raw_response_digest=raw_response_digest,
            provenance_artifact_digest=provenance_digest,
            candidate_id=None,
            candidate_artifact_digest=None,
            usage=usage or ResourceUsage(),
            failure_signature=signature,
            usage_is_exact=usage_is_exact,
            created_at=utc_now(),
        )
        self.ledger.add_generation(record)
        self.ledger.record_event("LLM_GENERATION_FAILURE", jsonable(record))
        return record

    def _put_raw(self, value: str) -> str:
        return self.artifacts.put_bytes(
            value.encode("utf-8"),
            media_type="application/json",
            metadata={"kind": "llm-raw-response-v1"},
        )


def _touched_paths_from_patch(patch: str) -> tuple[str, ...]:
    paths: set[str] = set()
    for match in re.finditer(r"^\+\+\+\s+(?:b/)?([^\t\r\n]+)", patch, flags=re.MULTILINE):
        value = match.group(1).strip().replace("\\", "/")
        if value != "/dev/null":
            paths.add(value)
    return tuple(sorted(paths))


def _budget_dimensions(message: str) -> tuple[str, ...]:
    _, _, suffix = message.partition(":")
    return tuple(sorted(item.strip() for item in suffix.split(",") if item.strip())) or ("unknown",)
