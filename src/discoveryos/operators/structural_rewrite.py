from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from discoveryos.contracts.models import CandidateSpec, ContractError, ProblemContract, ResourceBudget
from discoveryos.contracts.patch import (
    GenerationContext,
    GenerationKind,
    GenerationRequest,
    PatchProposal,
)
from discoveryos.operators.local_patch import (
    CandidateBuildSpec,
    LocalPatchOperator,
    LocalPatchResult,
    PatchProvider,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import canonical_json, digest_json, jsonable


STRUCTURAL_REWRITE_PROMPT_TEMPLATE = """You are the bounded Structural Rewrite / Basin-Jump operator inside DiscoveryOS.
Return exactly one JSON object with these fields and no others:
`hypothesis`, `expected_effects`, `target_files`, `patch`, `risks`, `estimated_cost`,
`algorithm_family`, `escape_rationale`, and `reused_component_ids`.

Scientific scope:
- Work only from FROZEN_CONTEXT_JSON. Do not call tools or inspect any other state.
- The current branch is stagnating. Propose a real algorithm-family change, not a cosmetic rename,
  constant tweak, formatting change, or another rejected local delta.
- `algorithm_family` must differ from the current family in STRUCTURAL_REWRITE_BRIEF_JSON.
- Preserve the current parent lineage: the diff is relative to the visible parent files, never a reset
  to the baseline. Retain required interfaces and explicitly explain the basin escape.
- `reused_component_ids` may contain only component ids offered in the frozen brief. Use an empty
  array when no offered component is applicable; never invent a component reference.
- Treat development evidence and semantic memory as observations, not final-blind truth.
- Touch only visible mutable files and at most three files. Never modify evaluators, tests,
  contracts, data, environment locks, build policy, or forbidden paths.
- The patch must be a standard unified diff with numbered hunk headers and correct line counts.
  Binary patches, renames, copies, file creation/deletion, mode or dependency changes are forbidden.
- Report risks and estimated input/output resource cost honestly.

GENERATION_KIND
{generation_kind}

FROZEN_CONTEXT_JSON
{context_json}
"""

STRUCTURAL_CONTEXT_PREFIX = "STRUCTURAL_REWRITE_BRIEF_JSON\n"


def _require_digest(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class LineageSnapshot:
    candidate_id: str
    algorithm_family: str
    family_label_digest: str
    semantic_delta: str
    evidence_receipt_ids: tuple[str, ...]
    evidence_summary: str

    def __post_init__(self) -> None:
        if not all((self.candidate_id, self.algorithm_family.strip(), self.semantic_delta.strip(), self.evidence_summary.strip())):
            raise ContractError("lineage snapshots require candidate, family, delta, and evidence summary")
        _require_digest("algorithm family label digest", self.family_label_digest)
        if not self.evidence_receipt_ids or len(set(self.evidence_receipt_ids)) != len(self.evidence_receipt_ids):
            raise ContractError("lineage snapshots require unique evidence receipts")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LineageSnapshot":
        required = {
            "candidate_id",
            "algorithm_family",
            "family_label_digest",
            "semantic_delta",
            "evidence_receipt_ids",
            "evidence_summary",
        }
        if set(value) != required:
            raise ContractError("invalid structural lineage snapshot fields")
        if not isinstance(value["evidence_receipt_ids"], list):
            raise ContractError("lineage evidence receipt ids must be an array")
        return cls(
            candidate_id=str(value["candidate_id"]),
            algorithm_family=str(value["algorithm_family"]),
            family_label_digest=str(value["family_label_digest"]),
            semantic_delta=str(value["semantic_delta"]),
            evidence_receipt_ids=tuple(str(item) for item in value["evidence_receipt_ids"]),
            evidence_summary=str(value["evidence_summary"]),
        )


@dataclass(frozen=True, slots=True)
class ReusableComponentReference:
    component_id: str
    source_candidate_id: str
    artifact_digest: str
    interface: str
    effect_summary: str

    def __post_init__(self) -> None:
        if not self.component_id.startswith("cmp_") or not self.source_candidate_id:
            raise ContractError("component references require component and source candidate ids")
        _require_digest("component artifact digest", self.artifact_digest)
        if not self.interface.strip() or not self.effect_summary.strip():
            raise ContractError("component references require interface and effect summary")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReusableComponentReference":
        required = {"component_id", "source_candidate_id", "artifact_digest", "interface", "effect_summary"}
        if set(value) != required:
            raise ContractError("invalid reusable component fields")
        return cls(**{key: str(value[key]) for key in required})


@dataclass(frozen=True, slots=True)
class BasinEscapeBrief:
    lineage: tuple[LineageSnapshot, ...]
    stagnation_reason: str
    failure_signatures: tuple[str, ...]
    rejected_local_deltas: tuple[str, ...]
    reusable_components: tuple[ReusableComponentReference, ...]

    def __post_init__(self) -> None:
        if len(self.lineage) < 2:
            raise ContractError("structural rewrite requires at least a parent and one ancestor snapshot")
        if len({snapshot.candidate_id for snapshot in self.lineage}) != len(self.lineage):
            raise ContractError("structural rewrite lineage candidates must be unique")
        if not self.stagnation_reason.strip():
            raise ContractError("structural rewrite requires a frozen stagnation reason")
        if not self.failure_signatures and not self.rejected_local_deltas:
            raise ContractError("structural rewrite requires failed local-search evidence")
        if len(set(self.failure_signatures)) != len(self.failure_signatures):
            raise ContractError("failure signatures must be unique")
        if len(set(self.rejected_local_deltas)) != len(self.rejected_local_deltas):
            raise ContractError("rejected local deltas must be unique")
        component_ids = [component.component_id for component in self.reusable_components]
        if len(set(component_ids)) != len(component_ids):
            raise ContractError("reusable component ids must be unique")

    @property
    def digest(self) -> str:
        return digest_json(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BasinEscapeBrief":
        required = {
            "lineage",
            "stagnation_reason",
            "failure_signatures",
            "rejected_local_deltas",
            "reusable_components",
        }
        if set(value) != required:
            raise ContractError("invalid basin-escape brief fields")
        for field in ("lineage", "failure_signatures", "rejected_local_deltas", "reusable_components"):
            if not isinstance(value[field], list):
                raise ContractError(f"basin-escape {field} must be an array")
        return cls(
            lineage=tuple(LineageSnapshot.from_dict(item) for item in value["lineage"]),
            stagnation_reason=str(value["stagnation_reason"]),
            failure_signatures=tuple(str(item) for item in value["failure_signatures"]),
            rejected_local_deltas=tuple(str(item) for item in value["rejected_local_deltas"]),
            reusable_components=tuple(ReusableComponentReference.from_dict(item) for item in value["reusable_components"]),
        )


@dataclass(frozen=True, slots=True)
class StructuralRewriteProposal:
    hypothesis: str
    expected_effects: tuple[tuple[str, Any], ...]
    target_files: tuple[str, ...]
    patch: str
    risks: tuple[str, ...]
    estimated_cost: ResourceBudget
    algorithm_family: str
    escape_rationale: str
    reused_component_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StructuralRewriteProposal":
        structural = {"algorithm_family", "escape_rationale", "reused_component_ids"}
        patch_fields = {"hypothesis", "expected_effects", "target_files", "patch", "risks", "estimated_cost"}
        if set(value) != structural | patch_fields:
            raise ContractError("invalid structural rewrite proposal fields")
        base = PatchProposal.from_dict({key: value[key] for key in patch_fields})
        if not isinstance(value["reused_component_ids"], list):
            raise ContractError("reused_component_ids must be an array")
        reused = tuple(str(item) for item in value["reused_component_ids"])
        if len(set(reused)) != len(reused):
            raise ContractError("reused component ids must be unique")
        algorithm_family = str(value["algorithm_family"]).strip()
        escape_rationale = str(value["escape_rationale"]).strip()
        if not algorithm_family or not escape_rationale:
            raise ContractError("structural rewrite requires algorithm family and escape rationale")
        return cls(
            hypothesis=base.hypothesis,
            expected_effects=base.expected_effects,
            target_files=base.target_files,
            patch=base.patch,
            risks=base.risks,
            estimated_cost=base.estimated_cost,
            algorithm_family=algorithm_family,
            escape_rationale=escape_rationale,
            reused_component_ids=reused,
        )

    def expected_effect_dict(self) -> dict[str, Any]:
        return dict(self.expected_effects)


class StructuralRewriteOperator(LocalPatchOperator):
    operator_id = "structural_rewrite_basin_jump_v1"

    def __init__(
        self,
        *,
        provider: PatchProvider,
        artifacts: ArtifactStore,
        ledger: EvidenceLedger,
        contract: ProblemContract,
    ) -> None:
        super().__init__(
            provider=provider,
            artifacts=artifacts,
            ledger=ledger,
            contract=contract,
            strategy_id="lineage_preserving_structural_escape",
            prompt_template=STRUCTURAL_REWRITE_PROMPT_TEMPLATE,
        )

    def propose(
        self,
        *,
        parent: CandidateSpec,
        mutable_files: dict[str, str],
        development_evidence_summary: str,
        semantic_delta_memory: tuple[str, ...],
        remaining_budget: ResourceBudget,
        build: CandidateBuildSpec,
        brief: BasinEscapeBrief,
    ) -> LocalPatchResult:
        self._validate_brief(parent, build, brief)
        if not development_evidence_summary.strip():
            raise ContractError("structural rewrite requires a development-evidence summary")
        structural_context = STRUCTURAL_CONTEXT_PREFIX + canonical_json(brief)
        context = self._context(
            parent=parent,
            mutable_files=mutable_files,
            development_evidence_summary=development_evidence_summary,
            failure_signature="BASIN_STAGNATION:" + brief.stagnation_reason,
            semantic_delta_memory=(*semantic_delta_memory, structural_context),
            remaining_budget=remaining_budget,
            mechanical_diagnostic=None,
        )
        result = self._generate(
            kind=GenerationKind.PROPOSAL,
            root_generation_id=None,
            parent=parent,
            context=context,
            remaining_budget=remaining_budget,
            build=build,
        )
        if result.candidate is not None and isinstance(result.proposal, StructuralRewriteProposal):
            self._record_structural_graph(result.candidate, result.proposal, brief)
        return result

    def repair(self, *args: Any, **kwargs: Any) -> LocalPatchResult:
        del args, kwargs
        raise ContractError("mechanical repair of a structural candidate must use the bounded LocalPatchOperator")

    def _parse_proposal(self, payload: dict[str, object], context: GenerationContext) -> StructuralRewriteProposal:
        del context
        return StructuralRewriteProposal.from_dict(payload)

    def _validate_proposal(self, proposal: StructuralRewriteProposal, context: GenerationContext) -> None:
        super()._validate_proposal(proposal, context)
        brief = self._brief_from_context(context)
        current_family = brief.lineage[0].algorithm_family.strip().casefold()
        if proposal.algorithm_family.strip().casefold() == current_family:
            raise ContractError("structural rewrite must leave the current algorithm family")
        offered = {component.component_id for component in brief.reusable_components}
        unknown = set(proposal.reused_component_ids) - offered
        if unknown:
            raise ContractError(f"structural rewrite invented component references: {sorted(unknown)}")

    def _candidate_parent_ids(
        self,
        parent: CandidateSpec,
        proposal: StructuralRewriteProposal,
        context: GenerationContext,
    ) -> tuple[str, ...]:
        brief = self._brief_from_context(context)
        components = {component.component_id: component for component in brief.reusable_components}
        parents = [parent.candidate_id]
        for component_id in proposal.reused_component_ids:
            source = components[component_id].source_candidate_id
            if source not in parents:
                parents.append(source)
        return tuple(parents)

    def _candidate_parameters(
        self,
        proposal: StructuralRewriteProposal,
        context: GenerationContext,
        request: GenerationRequest,
        provenance_digest: str,
    ) -> dict[str, object]:
        parameters = super()._candidate_parameters(proposal, context, request, provenance_digest)
        brief = self._brief_from_context(context)
        parameters.update(
            {
                "basin_escape_brief_digest": brief.digest,
                "source_algorithm_family": brief.lineage[0].algorithm_family,
                "target_algorithm_family": proposal.algorithm_family,
                "escape_rationale": proposal.escape_rationale,
                "reused_component_ids": proposal.reused_component_ids,
            }
        )
        return parameters

    def _validate_brief(self, parent: CandidateSpec, build: CandidateBuildSpec, brief: BasinEscapeBrief) -> None:
        if not parent.parent_ids or not build.parent_patch_stack:
            raise ContractError("structural rewrite cannot be a baseline reset; a materialized parent lineage is required")
        if brief.lineage[0].candidate_id != parent.candidate_id:
            raise ContractError("the first lineage snapshot must be the visible parent candidate")

        try:
            recorded_parent = self.ledger.get_candidate(parent.candidate_id)
        except KeyError as error:
            raise ContractError("the visible parent candidate is absent from the unified ledger") from error
        if recorded_parent != parent:
            raise ContractError("the visible parent differs from the unified-ledger candidate")

        current = parent
        for snapshot, next_snapshot in zip(brief.lineage, brief.lineage[1:]):
            if snapshot.candidate_id != current.candidate_id:
                raise ContractError("basin-escape lineage is not contiguous")
            if snapshot.semantic_delta != current.semantic_delta:
                raise ContractError("lineage semantic delta differs from the unified-ledger candidate")
            self._verify_family_label(snapshot)
            if next_snapshot.candidate_id not in current.parent_ids:
                raise ContractError("basin-escape lineage omits the parent ancestry")
            try:
                current = self.ledger.get_candidate(next_snapshot.candidate_id)
            except KeyError as error:
                raise ContractError(f"unknown lineage candidate: {next_snapshot.candidate_id}") from error
        final_snapshot = brief.lineage[-1]
        if final_snapshot.semantic_delta != current.semantic_delta:
            raise ContractError("lineage semantic delta differs from the unified-ledger candidate")
        self._verify_family_label(final_snapshot)

        evidence_by_id = {evidence.receipt_id: evidence for evidence in self.ledger.evidence_records()}
        for snapshot in brief.lineage:
            for receipt_id in snapshot.evidence_receipt_ids:
                evidence = evidence_by_id.get(receipt_id)
                if evidence is None or evidence.candidate_id != snapshot.candidate_id:
                    raise ContractError(f"lineage evidence receipt mismatch: {receipt_id}")

        for component in brief.reusable_components:
            try:
                self.ledger.get_candidate(component.source_candidate_id)
                self.artifacts.get_bytes(component.artifact_digest)
            except (KeyError, FileNotFoundError) as error:
                raise ContractError(f"unavailable reusable component: {component.component_id}") from error

    def _verify_family_label(self, snapshot: LineageSnapshot) -> None:
        try:
            payload = json.loads(self.artifacts.get_bytes(snapshot.family_label_digest).decode("utf-8"))
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContractError(f"missing or invalid algorithm-family label: {snapshot.candidate_id}") from error
        expected = {
            "candidate_id": snapshot.candidate_id,
            "algorithm_family": snapshot.algorithm_family,
        }
        if payload != expected:
            raise ContractError(f"algorithm-family label mismatch: {snapshot.candidate_id}")

    def _brief_from_context(self, context: GenerationContext) -> BasinEscapeBrief:
        encoded = [item.removeprefix(STRUCTURAL_CONTEXT_PREFIX) for item in context.semantic_delta_memory if item.startswith(STRUCTURAL_CONTEXT_PREFIX)]
        if len(encoded) != 1:
            raise ContractError("structural rewrite requires exactly one frozen basin-escape brief")
        try:
            payload = json.loads(encoded[0])
        except json.JSONDecodeError as error:
            raise ContractError("invalid frozen basin-escape brief") from error
        if not isinstance(payload, dict):
            raise ContractError("frozen basin-escape brief must be an object")
        return BasinEscapeBrief.from_dict(payload)

    def _record_structural_graph(
        self,
        candidate: CandidateSpec,
        proposal: StructuralRewriteProposal,
        brief: BasinEscapeBrief,
    ) -> None:
        components = {component.component_id: component for component in brief.reusable_components}
        self.ledger.add_edge(
            brief.lineage[0].candidate_id,
            candidate.candidate_id,
            "BASIN_ESCAPE",
            {
                "from_family": brief.lineage[0].algorithm_family,
                "to_family": proposal.algorithm_family,
                "brief_digest": brief.digest,
            },
        )
        for component_id in proposal.reused_component_ids:
            component = components[component_id]
            self.ledger.add_node(component.component_id, "component", jsonable(component))
            self.ledger.add_edge(
                component.source_candidate_id,
                component.component_id,
                "EXTRACTED_COMPONENT",
                {"artifact_digest": component.artifact_digest},
            )
            self.ledger.add_edge(
                component.component_id,
                candidate.candidate_id,
                "REUSED_BY_STRUCTURAL_REWRITE",
                {"interface": component.interface},
            )
        self.ledger.record_event(
            "STRUCTURAL_REWRITE_RECORDED",
            {
                "candidate_id": candidate.candidate_id,
                "brief_digest": brief.digest,
                "source_algorithm_family": brief.lineage[0].algorithm_family,
                "target_algorithm_family": proposal.algorithm_family,
                "reused_component_ids": proposal.reused_component_ids,
            },
        )
