from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.contracts.models import MetricDirection, ResourceBudget
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "R1.0-SP-A_RESIDUAL_HEADROOM_SEARCH_POLICY_V1"
MANIFEST_RECORD = "sealed-search-policy-admission-manifest.json"
CONTROL_ARM_ID = "one_shot"
REQUIRED_ARM_IDS = (
    CONTROL_ARM_ID,
    "iterative_local",
    "lineage_preserving",
    "structural_escape",
)
ALLOWED_HEADROOM_SOURCES = (
    "exact_oracle",
    "approximate_upper_bound",
    "historical_baseline_predating_protocol",
    "independent_difficulty_generator",
)
MINIMUM_TASK_COUNT = 8
MINIMUM_RESOLVABLE_HEADROOM_STEPS = 4
MINIMUM_DISTINCT_IMPROVEMENT_MAGNITUDES = 2
MINIMUM_TRAJECTORY_CLASSES = 2


METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "best_improvement": {
        "direction": "maximize",
        "definition": "best feasible direction-adjusted score delta from the frozen baseline",
    },
    "auc_over_token_budget": {
        "direction": "maximize",
        "definition": "area under best-so-far improvement versus consumed input-plus-output tokens, divided by the frozen token budget",
    },
    "success": {
        "direction": "maximize",
        "definition": "one iff best improvement reaches at least one frozen score-resolution step",
    },
    "valid_candidate_rate": {
        "direction": "maximize",
        "definition": "mechanically valid candidates divided by all materialized candidates",
    },
    "basin_jump_rate": {
        "direction": "descriptive",
        "definition": "improving valid transitions crossing frozen basin labels divided by all improving valid transitions",
    },
    "tokens_to_improvement": {
        "direction": "minimize",
        "definition": "first cumulative input-plus-output tokens reaching one score-resolution step; null when never reached",
    },
    "wall_time_to_improvement": {
        "direction": "minimize",
        "definition": "first cumulative wall seconds reaching one score-resolution step; null when never reached",
    },
}


SEARCH_VALUE_GATE: dict[str, Any] = {
    "control_arm": CONTROL_ARM_ID,
    "applies_independently_to_each_challenger": True,
    "minimum_paired_win_rate_best_improvement": 0.50,
    "maximum_paired_loss_rate_best_improvement": 0.25,
    "minimum_median_best_improvement_delta_steps": 1.0,
    "require_positive_median_auc_delta": True,
    "maximum_valid_candidate_rate_regression": 0.10,
    "require_all_accepted_evidence_replay": True,
    "require_no_budget_overrun": True,
    "final_blind_receipts": 0,
    "efficiency_cannot_compensate_for_missing_search_value": True,
    "family_wide_or_general_operator_superiority_claim": False,
}


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_sha256(name: str, value: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ResidualHeadroomEvidence:
    task_id: str
    task_payload_digest: str
    initial_state_digest: str
    evaluator_id: str
    evaluator_digest: str
    baseline_candidate_digest: str
    baseline_receipt_digest: str
    baseline_score: float
    score_direction: MetricDirection
    score_resolution: float
    reference_score: float
    reference_kind: str
    reference_digest: str
    selection_provenance_digest: str
    valid_intermediate_scores: tuple[float, ...]
    trajectory_classes: tuple[str, ...]
    baseline_basin_id: str
    basin_labeler_digest: str
    baseline_executable: bool
    baseline_replay_count: int
    baseline_replay_consistent: bool
    source_independent_of_compared_policies: bool
    pre_admission_model_calls: int

    def __post_init__(self) -> None:
        if not self.task_id or not self.evaluator_id or not self.baseline_basin_id:
            raise ValueError("task, evaluator, and baseline basin identifiers are required")
        for name in (
            "task_payload_digest",
            "initial_state_digest",
            "evaluator_digest",
            "baseline_candidate_digest",
            "baseline_receipt_digest",
            "reference_digest",
            "selection_provenance_digest",
            "basin_labeler_digest",
        ):
            _require_sha256(name, getattr(self, name))
        numeric = (self.baseline_score, self.score_resolution, self.reference_score, *self.valid_intermediate_scores)
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("headroom scores must be finite")
        if self.score_resolution <= 0:
            raise ValueError("score resolution must be positive")
        if self.reference_kind not in ALLOWED_HEADROOM_SOURCES:
            raise ValueError(f"unsupported headroom source: {self.reference_kind}")
        if self.baseline_replay_count < 0 or self.pre_admission_model_calls < 0:
            raise ValueError("counts cannot be negative")
        if len(set(self.trajectory_classes)) != len(self.trajectory_classes):
            raise ValueError("trajectory classes must be unique")


@dataclass(frozen=True, slots=True)
class FrozenModelConfig:
    provider: str
    model: str
    provider_version: str
    settings_digest: str

    def __post_init__(self) -> None:
        if not self.provider or not self.model or not self.provider_version:
            raise ValueError("provider, model, and provider version are required")
        _require_sha256("settings_digest", self.settings_digest)


@dataclass(frozen=True, slots=True)
class PolicyImplementation:
    arm_id: str
    controller_digest: str
    prompt_template_digest: str

    def __post_init__(self) -> None:
        if self.arm_id not in REQUIRED_ARM_IDS:
            raise ValueError(f"unsupported search-policy arm: {self.arm_id}")
        _require_sha256("controller_digest", self.controller_digest)
        _require_sha256("prompt_template_digest", self.prompt_template_digest)


@dataclass(frozen=True, slots=True)
class SearchObservation:
    candidate_id: str
    parent_id: str | None
    cumulative_tokens: int
    cumulative_wall_seconds: float
    score: float | None
    valid: bool
    feasible: bool
    basin_id: str | None

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate id is required")
        if self.cumulative_tokens < 0 or self.cumulative_wall_seconds < 0:
            raise ValueError("cumulative usage cannot be negative")
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("candidate score must be finite")
        if self.valid and self.feasible and (self.score is None or not self.basin_id):
            raise ValueError("valid feasible candidates require a score and frozen basin label")


def evaluate_task_admission(evidence: ResidualHeadroomEvidence) -> dict[str, Any]:
    direction = 1.0 if evidence.score_direction is MetricDirection.MAXIMIZE else -1.0
    reference_gap = direction * (evidence.reference_score - evidence.baseline_score)
    headroom_steps = reference_gap / evidence.score_resolution
    magnitude_steps = {
        round(direction * (score - evidence.baseline_score) / evidence.score_resolution, 8)
        for score in evidence.valid_intermediate_scores
        if direction * (score - evidence.baseline_score) >= evidence.score_resolution - 1e-12
        and direction * (score - evidence.baseline_score) <= reference_gap + 1e-12
    }
    checks = {
        "deterministic_baseline_executable": (
            evidence.baseline_executable
            and evidence.baseline_replay_consistent
            and evidence.baseline_replay_count >= 2
        ),
        "no_pre_admission_model_calls": evidence.pre_admission_model_calls == 0,
        "policy_independent_headroom_source": evidence.source_independent_of_compared_policies,
        "independently_established_positive_headroom": reference_gap > 0,
        "baseline_not_near_reference": headroom_steps >= MINIMUM_RESOLVABLE_HEADROOM_STEPS,
        "multiple_valid_improvement_magnitudes": (
            len(magnitude_steps) >= MINIMUM_DISTINCT_IMPROVEMENT_MAGNITUDES
        ),
        "multiple_meaningful_trajectory_classes": (
            len(evidence.trajectory_classes) >= MINIMUM_TRAJECTORY_CLASSES
        ),
        "scoring_resolves_incremental_progress": (
            headroom_steps >= MINIMUM_RESOLVABLE_HEADROOM_STEPS
        ),
        "frozen_basin_labeler": _is_sha256(evidence.basin_labeler_digest),
    }
    return {
        "task_id": evidence.task_id,
        "admitted": all(checks.values()),
        "checks": checks,
        "headroom_steps": round(headroom_steps, 8),
        "distinct_improvement_magnitude_steps": sorted(magnitude_steps),
    }


def compute_policy_metrics(
    evidence: ResidualHeadroomEvidence,
    observations: tuple[SearchObservation, ...],
    *,
    token_budget: int,
    wall_budget: float,
) -> dict[str, Any]:
    if token_budget <= 0 or wall_budget <= 0:
        raise ValueError("token and wall budgets must be positive")
    direction = 1.0 if evidence.score_direction is MetricDirection.MAXIMIZE else -1.0
    previous_tokens = 0
    previous_wall = 0.0
    previous_best = 0.0
    auc = 0.0
    seen: dict[str, tuple[float | None, str | None, bool]] = {}
    first_tokens: int | None = None
    first_wall: float | None = None
    valid_count = 0
    improving_transitions = 0
    basin_jumps = 0
    candidate_ids: set[str] = set()

    for observation in observations:
        if observation.candidate_id in candidate_ids:
            raise ValueError(f"duplicate candidate observation: {observation.candidate_id}")
        candidate_ids.add(observation.candidate_id)
        if observation.cumulative_tokens < previous_tokens or observation.cumulative_wall_seconds < previous_wall:
            raise ValueError("search observations must have monotonic cumulative usage")
        if observation.cumulative_tokens > token_budget or observation.cumulative_wall_seconds > wall_budget:
            raise ValueError("search observation exceeds the frozen shared budget")
        if observation.parent_id is not None and observation.parent_id not in seen:
            raise ValueError(f"parent must precede child in the trace: {observation.parent_id}")

        auc += previous_best * (observation.cumulative_tokens - previous_tokens)
        valid_count += int(observation.valid)
        improvement: float | None = None
        if observation.valid and observation.feasible and observation.score is not None:
            improvement = max(0.0, direction * (observation.score - evidence.baseline_score))
            previous_best = max(previous_best, improvement)
            if first_tokens is None and previous_best >= evidence.score_resolution - 1e-12:
                first_tokens = observation.cumulative_tokens
                first_wall = observation.cumulative_wall_seconds

            if observation.parent_id is None:
                parent_score = evidence.baseline_score
                parent_basin = evidence.baseline_basin_id
                parent_valid = True
            else:
                parent_score, parent_basin, parent_valid = seen[observation.parent_id]
            if parent_valid and parent_score is not None:
                parent_delta = direction * (observation.score - parent_score)
                if parent_delta >= evidence.score_resolution - 1e-12:
                    improving_transitions += 1
                    basin_jumps += int(observation.basin_id != parent_basin)

        seen[observation.candidate_id] = (
            observation.score,
            observation.basin_id,
            observation.valid and observation.feasible,
        )
        previous_tokens = observation.cumulative_tokens
        previous_wall = observation.cumulative_wall_seconds

    auc += previous_best * (token_budget - previous_tokens)
    materialized = len(observations)
    return {
        "best_improvement": round(previous_best, 8),
        "best_improvement_steps": round(previous_best / evidence.score_resolution, 8),
        "auc_over_token_budget": round(auc / token_budget, 8),
        "success": previous_best >= evidence.score_resolution - 1e-12,
        "valid_candidate_rate": round(valid_count / materialized, 8) if materialized else 0.0,
        "basin_jump_rate": round(basin_jumps / improving_transitions, 8) if improving_transitions else 0.0,
        "improving_transition_count": improving_transitions,
        "basin_jump_count": basin_jumps,
        "tokens_to_improvement": first_tokens,
        "wall_time_to_improvement": first_wall,
        "materialized_candidate_count": materialized,
    }


def seal_search_policy_protocol(
    workspace: Path,
    *,
    tasks: tuple[ResidualHeadroomEvidence, ...],
    model_config: FrozenModelConfig,
    policies: tuple[PolicyImplementation, ...],
    shared_budget: ResourceBudget,
    replicates_per_task: int,
    execution_order_seed: int,
) -> dict[str, Any]:
    """Seal task admission and matched-policy comparison before any model call."""

    if len(tasks) < MINIMUM_TASK_COUNT:
        raise ValueError(f"search-policy admission requires at least {MINIMUM_TASK_COUNT} tasks")
    if replicates_per_task < 1:
        raise ValueError("replicates per task must be positive")
    if shared_budget.tokens <= 0 or shared_budget.wall_seconds <= 0:
        raise ValueError("the shared budget must freeze positive token and wall ceilings")
    if tuple(sorted(policy.arm_id for policy in policies)) != tuple(sorted(REQUIRED_ARM_IDS)):
        raise ValueError(f"policies must define exactly these arms: {REQUIRED_ARM_IDS}")
    if len({(policy.controller_digest, policy.prompt_template_digest) for policy in policies}) != len(policies):
        raise ValueError("search-policy arms must freeze distinct controller/prompt implementations")
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("task ids must be unique")
    if len({task.task_payload_digest for task in tasks}) != len(tasks):
        raise ValueError("task payloads must be unique")
    task_reports = tuple(evaluate_task_admission(task) for task in tasks)
    failures = {
        report["task_id"]: tuple(name for name, passed in report["checks"].items() if not passed)
        for report in task_reports
        if not report["admitted"]
    }
    if failures:
        raise ValueError(f"task admission failed: {failures}")
    if sum(task.pre_admission_model_calls for task in tasks) != 0:
        raise ValueError("protocol sealing must precede every candidate-model call")

    payload = {
        "protocol": PROTOCOL_ID,
        "status": "SEALED_PRE_MODEL",
        "claim_ceiling": "SEARCH_POLICY_PROTOCOL_ONLY",
        "scope": "LOCAL_OPERATOR_MECHANISM_ADMISSION_WITHIN_UNIFIED_KERNEL",
        "model_calls_before_seal": 0,
        "architecture_boundary": {
            "shared_research_graph_evidence_candidate_store_budget_memory_runtime": True,
            "official_external_systems_used_as_internal_arms": False,
            "official_external_systems_role": "isolated_benchmark_challengers_only",
            "full_unified_search_kernel_admitted_by_this_protocol": False,
        },
        "protocol_implementation_sha256": digest_bytes(Path(__file__).read_bytes()),
        "task_admission_policy": {
            "allowed_headroom_sources": ALLOWED_HEADROOM_SOURCES,
            "minimum_task_count": MINIMUM_TASK_COUNT,
            "minimum_resolvable_headroom_steps": MINIMUM_RESOLVABLE_HEADROOM_STEPS,
            "minimum_distinct_improvement_magnitudes": MINIMUM_DISTINCT_IMPROVEMENT_MAGNITUDES,
            "minimum_trajectory_classes": MINIMUM_TRAJECTORY_CLASSES,
            "one_shot_or_other_candidate_policy_probe_used_for_selection": False,
            "task_replacement_after_model_feedback": False,
        },
        "tasks": [
            {"evidence": jsonable(task), "admission": report}
            for task, report in zip(tasks, task_reports, strict=True)
        ],
        "model_config_shared_by_all_arms": jsonable(model_config),
        "arms": [jsonable(policy) for policy in sorted(policies, key=lambda item: item.arm_id)],
        "fairness_invariants": {
            "same_model_and_settings": True,
            "same_total_budget": jsonable(shared_budget),
            "same_evaluator_per_task": True,
            "same_initial_state_per_task": True,
            "same_replicate_schedule": True,
            "replicates_per_task": replicates_per_task,
            "execution_order_seed": execution_order_seed,
            "actual_token_accounting": "input_plus_output; cache reported separately",
            "no_free_model_repair_calls": True,
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "search_value_gate": SEARCH_VALUE_GATE,
        "stop_rule": {
            "per_arm_task_replicate": "stop at shared token or wall ceiling; unused budget is not transferable",
            "global": "run every sealed task and replicate for every arm; no task replacement or threshold relaxation",
        },
        "not_authorized": [
            "candidate-model execution before this manifest is sealed",
            "task selection using one-shot or challenger feedback",
            "operator admission from protocol-only evidence",
            "family-wide or out-of-distribution superiority claims",
            "claims about the complete DiscoveryOS unified search kernel",
            "final-blind access",
        ],
    }
    manifest = {**payload, "protocol_manifest_digest": digest_json(payload)}
    store = ArtifactStore(workspace.resolve() / "admission-artifacts")
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "task_count": len(tasks),
        "protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "manifest_path": str(path),
    }


def verify_search_policy_manifest(manifest: dict[str, Any], expected_digest: str) -> None:
    recorded_digest = manifest.get("protocol_manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "protocol_manifest_digest"}
    if recorded_digest != digest_json(payload) or recorded_digest != expected_digest:
        raise RuntimeError("sealed search-policy manifest digest mismatch")
    if manifest.get("model_calls_before_seal") != 0 or manifest.get("status") != "SEALED_PRE_MODEL":
        raise RuntimeError("search-policy manifest was not sealed before model execution")
    if manifest.get("protocol_implementation_sha256") != digest_bytes(Path(__file__).read_bytes()):
        raise RuntimeError("search-policy protocol implementation has drifted since sealing")
