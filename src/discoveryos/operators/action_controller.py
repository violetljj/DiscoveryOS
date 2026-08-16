from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget, ResourceUsage
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_json, jsonable, utc_now


class SearchAction(str, Enum):
    LOCAL_PATCH = "LOCAL_PATCH"
    STRUCTURAL_ESCAPE = "STRUCTURAL_ESCAPE"
    REPLICATE = "REPLICATE"
    PROMOTE_FIDELITY = "PROMOTE_FIDELITY"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class ActionCost:
    action: SearchAction
    resource_floor: ResourceBudget

    def __post_init__(self) -> None:
        if self.action is SearchAction.STOP:
            raise ValueError("STOP cannot reserve resources")
        if not any(self.resource_floor.as_dict().values()):
            raise ValueError("each executable action requires a non-zero resource floor")


@dataclass(frozen=True, slots=True)
class CandidateSearchState:
    candidate_id: str
    branch_id: str
    fidelity: Fidelity
    latest_evidence_receipt_id: str | None
    scheduling_utility: float | None
    resource_consumed: ResourceUsage = field(default_factory=ResourceUsage)
    uncertainty: float = 0.0
    replicate_count: int = 0
    feasible: bool = True
    promotion_eligible: bool = False
    promotion_target: Fidelity | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.branch_id:
            raise ValueError("candidate and branch ids are required")
        if self.uncertainty < 0 or self.replicate_count < 0:
            raise ValueError("uncertainty and replicate count cannot be negative")
        if self.promotion_eligible and self.promotion_target is None:
            raise ValueError("an eligible promotion requires a target fidelity")
        if self.promotion_target is not None and self.promotion_target.rank <= self.fidelity.rank:
            raise ValueError("promotion target must increase fidelity")


@dataclass(frozen=True, slots=True)
class BranchSearchState:
    branch_id: str
    lineage_root_id: str
    parent_candidate_id: str
    algorithm_family: str
    generations_since_improvement: int
    recent_improvements: tuple[float, ...]
    recent_delta_similarity: float
    lineage_receipt_ids: tuple[str, ...]
    failure_signatures: tuple[str, ...]
    local_actions_remaining: int
    structural_actions_remaining: int
    active: bool = True

    def __post_init__(self) -> None:
        if not all((self.branch_id, self.lineage_root_id, self.parent_candidate_id, self.algorithm_family)):
            raise ValueError("branch identity and algorithm family are required")
        if self.generations_since_improvement < 0:
            raise ValueError("generations since improvement cannot be negative")
        if not 0.0 <= self.recent_delta_similarity <= 1.0:
            raise ValueError("recent delta similarity must be in [0, 1]")
        if self.local_actions_remaining < 0 or self.structural_actions_remaining < 0:
            raise ValueError("branch action budgets cannot be negative")


@dataclass(frozen=True, slots=True)
class SearchState:
    run_id: str
    step: int
    incumbent_candidate_id: str
    incumbent_utility: float
    utility_metric_name: str
    metric_direction: MetricDirection
    candidates: tuple[CandidateSearchState, ...]
    branches: tuple[BranchSearchState, ...]
    reusable_component_ids: tuple[str, ...]
    remaining_budget: ResourceBudget
    elapsed_usage: ResourceUsage = field(default_factory=ResourceUsage)

    def __post_init__(self) -> None:
        if not self.run_id or not self.incumbent_candidate_id or not self.utility_metric_name:
            raise ValueError("run and incumbent ids are required")
        if self.step < 0:
            raise ValueError("search step cannot be negative")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        branch_ids = [branch.branch_id for branch in self.branches]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate ids must be unique within a search state")
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("branch ids must be unique within a search state")
        if self.incumbent_candidate_id not in set(candidate_ids):
            raise ValueError("incumbent must exist in the candidate state")
        if any(candidate.branch_id not in set(branch_ids) for candidate in self.candidates):
            raise ValueError("every candidate must refer to a known branch")

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class ActionControllerConfig:
    stagnation_generations: int = 2
    improvement_epsilon: float = 0.01
    uncertainty_threshold: float = 0.05
    incumbent_proximity: float = 0.05
    minimum_replicates: int = 2
    structural_similarity_threshold: float = 0.8
    costs: tuple[ActionCost, ...] = ()

    def __post_init__(self) -> None:
        if self.stagnation_generations < 1 or self.minimum_replicates < 1:
            raise ValueError("stagnation generations and minimum replicates must be positive")
        if self.improvement_epsilon < 0 or self.uncertainty_threshold < 0 or self.incumbent_proximity < 0:
            raise ValueError("controller thresholds cannot be negative")
        if not 0.0 <= self.structural_similarity_threshold <= 1.0:
            raise ValueError("structural similarity threshold must be in [0, 1]")
        actions = [item.action for item in self.costs]
        if len(actions) != len(set(actions)):
            raise ValueError("action costs must be unique")
        required = set(SearchAction) - {SearchAction.STOP}
        if set(actions) != required:
            raise ValueError("resource floors are required for every executable action")

    def resource_floor_for(self, action: SearchAction) -> ResourceBudget:
        return next(
            (item.resource_floor for item in self.costs if item.action is action),
            ResourceBudget(),
        )

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class SearchDecision:
    decision_id: str
    run_id: str
    step: int
    state_digest: str
    controller_digest: str
    action: SearchAction
    candidate_id: str | None
    branch_id: str | None
    operator_id: str | None
    fidelity: Fidelity | None
    reason_codes: tuple[str, ...]
    resource_floor: ResourceBudget
    reusable_component_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        state: SearchState,
        controller_digest: str,
        action: SearchAction,
        candidate_id: str | None,
        branch_id: str | None,
        operator_id: str | None,
        fidelity: Fidelity | None,
        reason_codes: tuple[str, ...],
        resource_floor: ResourceBudget,
        reusable_component_ids: tuple[str, ...] = (),
    ) -> "SearchDecision":
        identity = {
            "run_id": state.run_id,
            "step": state.step,
            "state_digest": state.digest,
            "controller_digest": controller_digest,
            "action": action,
            "candidate_id": candidate_id,
            "branch_id": branch_id,
            "operator_id": operator_id,
            "fidelity": fidelity,
            "reason_codes": reason_codes,
            "resource_floor": resource_floor,
            "reusable_component_ids": reusable_component_ids,
        }
        return cls(decision_id=f"decision_{digest_json(identity)[:24]}", **identity)


@dataclass(frozen=True, slots=True)
class AnytimeTraceRecord:
    trace_id: str
    run_id: str
    timestamp: str
    step: int
    state_digest: str
    selected_action: SearchAction
    decision_id: str
    candidate_id: str | None
    branch_id: str | None
    operator_id: str | None
    fidelity: Fidelity | None
    reason_codes: tuple[str, ...]
    budget_before: ResourceBudget
    budget_floor: ResourceBudget
    budget_actual: ResourceUsage
    budget_after: ResourceBudget
    incumbent_before: str
    incumbent_after: str
    best_utility_before: float
    best_utility_after: float
    wall_elapsed: float
    tokens_elapsed: int
    cpu_elapsed: float
    gpu_elapsed: float


class DeterministicActionController:
    """A replayable policy over frozen search state; it never invokes a model."""

    operator_id = "deterministic_action_controller_v0"

    def __init__(self, config: ActionControllerConfig) -> None:
        self.config = config

    def decide(self, state: SearchState) -> SearchDecision:
        candidates = tuple(candidate for candidate in state.candidates if candidate.active)
        branches = tuple(branch for branch in state.branches if branch.active)
        if not candidates or not branches:
            return self._stop(state, "NO_ACTIVE_SEARCH_FRONTIER")

        replicate = self._replication_candidate(state, candidates)
        if replicate is not None:
            reason = (
                "EVIDENCE_UNCERTAIN"
                if replicate.uncertainty > self.config.uncertainty_threshold
                else "INCUMBENT_DECISION_NOISE_SENSITIVE"
            )
            return self._decision_or_stop(
                state,
                action=SearchAction.REPLICATE,
                candidate=replicate,
                branch_id=replicate.branch_id,
                operator_id="replicate_evaluation_v1",
                fidelity=replicate.fidelity,
                reason_codes=(reason, "MINIMUM_REPLICATES_NOT_MET"),
            )

        promotion = self._promotion_candidate(state, candidates)
        if promotion is not None:
            return self._decision_or_stop(
                state,
                action=SearchAction.PROMOTE_FIDELITY,
                candidate=promotion,
                branch_id=promotion.branch_id,
                operator_id="asha_v1",
                fidelity=promotion.promotion_target,
                reason_codes=("ASHA_PROMOTION_ELIGIBLE", "UNCERTAINTY_ACCEPTABLE"),
            )

        branch = self._branch_for_next_action(state, branches)
        if branch is None:
            return self._stop(state, "ALL_BRANCHES_EXHAUSTED")
        parent = next(candidate for candidate in candidates if candidate.candidate_id == branch.parent_candidate_id)
        if branch.generations_since_improvement >= self.config.stagnation_generations:
            if not branch.lineage_receipt_ids or not branch.failure_signatures:
                return self._stop(state, "STRUCTURAL_EVIDENCE_REQUIRED")
            if branch.recent_delta_similarity < self.config.structural_similarity_threshold:
                return self._stop(state, "LOCAL_DELTAS_NOT_CONVERGED")
            if branch.structural_actions_remaining <= 0:
                return self._stop(state, "STRUCTURAL_BUDGET_EXHAUSTED")
            return self._decision_or_stop(
                state,
                action=SearchAction.STRUCTURAL_ESCAPE,
                candidate=parent,
                branch_id=branch.branch_id,
                operator_id="structural_rewrite_basin_jump_v1",
                fidelity=parent.fidelity,
                reason_codes=("LOCAL_STAGNATION", "SIMILAR_LOCAL_DELTAS", "LINEAGE_EVIDENCE_BOUND"),
                reusable_component_ids=tuple(sorted(set(state.reusable_component_ids))),
            )
        if branch.local_actions_remaining <= 0:
            return self._stop(state, "LOCAL_BUDGET_EXHAUSTED")
        reason = "RECENT_IMPROVEMENT" if self._branch_is_improving(branch) else "LOCAL_SEARCH_NOT_YET_STAGNANT"
        return self._decision_or_stop(
            state,
            action=SearchAction.LOCAL_PATCH,
            candidate=parent,
            branch_id=branch.branch_id,
            operator_id="bounded_llm_local_patch_v1",
            fidelity=parent.fidelity,
            reason_codes=(reason,),
        )

    def replay(self, decision: SearchDecision, state: SearchState) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []
        reconstructed = self.decide(state)
        if decision.state_digest != state.digest:
            issues.append("STATE_DIGEST_MISMATCH")
        comparable_fields = (
            "decision_id",
            "run_id",
            "step",
            "controller_digest",
            "action",
            "candidate_id",
            "branch_id",
            "operator_id",
            "fidelity",
            "reason_codes",
            "resource_floor",
            "reusable_component_ids",
        )
        if any(getattr(decision, name) != getattr(reconstructed, name) for name in comparable_fields):
            issues.append("DECISION_REPLAY_MISMATCH")
        return not issues, tuple(issues)

    def _replication_candidate(
        self,
        state: SearchState,
        candidates: tuple[CandidateSearchState, ...],
    ) -> CandidateSearchState | None:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.feasible
            and candidate.scheduling_utility is not None
            and candidate.latest_evidence_receipt_id is not None
            and candidate.replicate_count < self.config.minimum_replicates
            and (
                candidate.uncertainty > self.config.uncertainty_threshold
                or abs(candidate.scheduling_utility - state.incumbent_utility) <= self.config.incumbent_proximity
            )
        ]
        return min(
            eligible,
            key=lambda item: (abs(item.scheduling_utility - state.incumbent_utility), item.candidate_id),
            default=None,
        )

    def _promotion_candidate(
        self,
        state: SearchState,
        candidates: tuple[CandidateSearchState, ...],
    ) -> CandidateSearchState | None:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.feasible
            and candidate.scheduling_utility is not None
            and candidate.promotion_eligible
            and candidate.uncertainty <= self.config.uncertainty_threshold
            and candidate.replicate_count >= self.config.minimum_replicates
        ]
        reverse = state.metric_direction is MetricDirection.MAXIMIZE
        return min(
            eligible,
            key=lambda item: (
                (-item.scheduling_utility if reverse else item.scheduling_utility),
                item.candidate_id,
            ),
            default=None,
        )

    @staticmethod
    def _branch_for_next_action(
        state: SearchState,
        branches: tuple[BranchSearchState, ...],
    ) -> BranchSearchState | None:
        candidate_ids = {candidate.candidate_id for candidate in state.candidates if candidate.active}
        eligible = [branch for branch in branches if branch.parent_candidate_id in candidate_ids]
        return min(
            eligible,
            key=lambda item: (item.parent_candidate_id != state.incumbent_candidate_id, item.branch_id),
            default=None,
        )

    def _branch_is_improving(self, branch: BranchSearchState) -> bool:
        return bool(branch.recent_improvements) and branch.recent_improvements[-1] > self.config.improvement_epsilon

    def _decision_or_stop(
        self,
        state: SearchState,
        *,
        action: SearchAction,
        candidate: CandidateSearchState,
        branch_id: str,
        operator_id: str,
        fidelity: Fidelity | None,
        reason_codes: tuple[str, ...],
        reusable_component_ids: tuple[str, ...] = (),
    ) -> SearchDecision:
        resource_floor = self.config.resource_floor_for(action)
        if not _affords(state.remaining_budget, resource_floor):
            return self._stop(state, f"INSUFFICIENT_BUDGET_FOR_{action.value}")
        return SearchDecision.create(
            state=state,
            controller_digest=self.config.digest,
            action=action,
            candidate_id=candidate.candidate_id,
            branch_id=branch_id,
            operator_id=operator_id,
            fidelity=fidelity,
            reason_codes=reason_codes,
            resource_floor=resource_floor,
            reusable_component_ids=reusable_component_ids,
        )

    def _stop(self, state: SearchState, reason: str) -> SearchDecision:
        return SearchDecision.create(
            state=state,
            controller_digest=self.config.digest,
            action=SearchAction.STOP,
            candidate_id=None,
            branch_id=None,
            operator_id=self.operator_id,
            fidelity=None,
            reason_codes=(reason,),
            resource_floor=ResourceBudget(),
        )


class AnytimeTraceRecorder:
    def __init__(self, artifacts: ArtifactStore, ledger: EvidenceLedger) -> None:
        self.artifacts = artifacts
        self.ledger = ledger

    def record(
        self,
        *,
        decision: SearchDecision,
        state_before: SearchState,
        state_after: SearchState,
        actual_usage: ResourceUsage,
    ) -> AnytimeTraceRecord:
        if decision.run_id != state_before.run_id or state_after.run_id != state_before.run_id:
            raise ValueError("trace states and decision must share a run")
        if decision.state_digest != state_before.digest:
            raise ValueError("decision is not bound to the before state")
        if state_after.step != state_before.step + 1:
            raise ValueError("an action must advance the search state by exactly one step")
        expected_remaining = _consume(state_before.remaining_budget, actual_usage)
        if state_after.remaining_budget != expected_remaining:
            raise ValueError("after-state budget does not match actual resource usage")
        expected_elapsed = _add_usage(state_before.elapsed_usage, actual_usage)
        if state_after.elapsed_usage != expected_elapsed:
            raise ValueError("after-state elapsed usage does not include actual resource usage")
        identity = {
            "run_id": decision.run_id,
            "step": decision.step,
            "decision_id": decision.decision_id,
            "state_digest": decision.state_digest,
            "budget_actual": actual_usage,
            "budget_after": state_after.remaining_budget,
            "incumbent_after": state_after.incumbent_candidate_id,
            "best_utility_after": state_after.incumbent_utility,
        }
        record = AnytimeTraceRecord(
            trace_id=f"trace_{digest_json(identity)[:24]}",
            run_id=decision.run_id,
            timestamp=utc_now(),
            step=decision.step,
            state_digest=decision.state_digest,
            selected_action=decision.action,
            decision_id=decision.decision_id,
            candidate_id=decision.candidate_id,
            branch_id=decision.branch_id,
            operator_id=decision.operator_id,
            fidelity=decision.fidelity,
            reason_codes=decision.reason_codes,
            budget_before=state_before.remaining_budget,
            budget_floor=decision.resource_floor,
            budget_actual=actual_usage,
            budget_after=state_after.remaining_budget,
            incumbent_before=state_before.incumbent_candidate_id,
            incumbent_after=state_after.incumbent_candidate_id,
            best_utility_before=state_before.incumbent_utility,
            best_utility_after=state_after.incumbent_utility,
            wall_elapsed=state_after.elapsed_usage.wall_seconds,
            tokens_elapsed=state_after.elapsed_usage.tokens,
            cpu_elapsed=state_after.elapsed_usage.cpu_seconds,
            gpu_elapsed=state_after.elapsed_usage.gpu_seconds,
        )
        self.artifacts.write_record(
            f"search/{record.run_id}/anytime/{record.step:06d}-{record.trace_id}.json",
            record,
        )
        self.ledger.record_event("SEARCH_ACTION_SETTLED", jsonable(record))
        return record


def _affords(remaining: ResourceBudget, requested: ResourceBudget) -> bool:
    return all(
        requested.as_dict()[dimension] <= available
        for dimension, available in remaining.as_dict().items()
    )


def _consume(remaining: ResourceBudget, actual: ResourceUsage) -> ResourceBudget:
    available = remaining.as_dict()
    used = actual.as_budget_dict()
    exceeded = [dimension for dimension, value in used.items() if value > available[dimension]]
    if exceeded:
        raise ValueError("actual usage exceeds remaining search budget: " + ",".join(exceeded))
    return ResourceBudget(
        tokens=int(available["tokens"] - used["tokens"]),
        cpu_seconds=available["cpu_seconds"] - used["cpu_seconds"],
        gpu_seconds=available["gpu_seconds"] - used["gpu_seconds"],
        device_seconds=available["device_seconds"] - used["device_seconds"],
        wall_seconds=available["wall_seconds"] - used["wall_seconds"],
    )


def _add_usage(before: ResourceUsage, actual: ResourceUsage) -> ResourceUsage:
    exit_codes = [value for value in (before.exit_code, actual.exit_code) if value is not None]
    return ResourceUsage(
        llm_input_tokens=before.llm_input_tokens + actual.llm_input_tokens,
        llm_output_tokens=before.llm_output_tokens + actual.llm_output_tokens,
        llm_cache_tokens=before.llm_cache_tokens + actual.llm_cache_tokens,
        cpu_seconds=before.cpu_seconds + actual.cpu_seconds,
        gpu_seconds=before.gpu_seconds + actual.gpu_seconds,
        device_seconds=before.device_seconds + actual.device_seconds,
        wall_seconds=before.wall_seconds + actual.wall_seconds,
        peak_rss_bytes=max(before.peak_rss_bytes, actual.peak_rss_bytes),
        exit_code=max(exit_codes, default=None),
    )
