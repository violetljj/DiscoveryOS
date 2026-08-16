from __future__ import annotations

from typing import Any

from .models import (
    CandidateSpec,
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    DataSplit,
    EvidenceRecord,
    EvidenceValidity,
    ExperimentSpec,
    Fidelity,
    HardConstraint,
    MetricDefinition,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    RunMode,
    WinnerRule,
)


def contract_from_dict(value: dict[str, Any]) -> ProblemContract:
    return ProblemContract(
        contract_id=value["contract_id"],
        version=value["version"],
        question=value["question"],
        baseline_candidate_id=value["baseline_candidate_id"],
        mutable_paths=tuple(value["mutable_paths"]),
        forbidden_paths=tuple(value["forbidden_paths"]),
        data_splits=tuple(
            DataSplit(
                split_id=item["split_id"],
                role=DataRole(item["role"]),
                relative_path=item["relative_path"],
                sha256=item["sha256"],
            )
            for item in value["data_splits"]
        ),
        fidelities=tuple(Fidelity(item) for item in value["fidelities"]),
        metrics=tuple(
            MetricDefinition(
                name=item["name"],
                direction=MetricDirection(item["direction"]),
                objective=bool(item["objective"]),
                available_from=Fidelity(item["available_from"]),
            )
            for item in value["metrics"]
        ),
        hard_constraints=tuple(
            HardConstraint(
                metric=item["metric"],
                operator=ConstraintOperator(item["operator"]),
                threshold=float(item["threshold"]),
                applies_from=Fidelity(item["applies_from"]),
            )
            for item in value["hard_constraints"]
        ),
        budget=ResourceBudget(**value["budget"]),
        winner_rule=WinnerRule(
            method=value["winner_rule"]["method"],
            metric_order=tuple(value["winner_rule"]["metric_order"]),
            require_fidelity=Fidelity(value["winner_rule"]["require_fidelity"]),
        ),
        evaluator_bindings=tuple((item[0], item[1]) for item in value["evaluator_bindings"]),
        claim_ceiling=ClaimCeiling(value["claim_ceiling"]),
        created_at=value["created_at"],
    )


def candidate_from_dict(value: dict[str, Any]) -> CandidateSpec:
    return CandidateSpec(
        candidate_id=value["candidate_id"],
        artifact_digest=value["artifact_digest"],
        parent_ids=tuple(value["parent_ids"]),
        operator_id=value["operator_id"],
        strategy_id=value["strategy_id"],
        hypothesis_id=value.get("hypothesis_id"),
        parameters=tuple((item[0], item[1]) for item in value["parameters"]),
        semantic_delta=value["semantic_delta"],
        expected_effects=tuple((item[0], item[1]) for item in value["expected_effects"]),
        environment_digest=value["environment_digest"],
        created_at=value["created_at"],
    )


def evidence_from_dict(value: dict[str, Any]) -> EvidenceRecord:
    return EvidenceRecord(
        receipt_id=value["receipt_id"],
        experiment_id=value["experiment_id"],
        candidate_id=value["candidate_id"],
        contract_digest=value["contract_digest"],
        evaluator_id=value["evaluator_id"],
        evaluator_digest=value["evaluator_digest"],
        data_digest=value.get("data_digest"),
        fidelity=Fidelity(value["fidelity"]),
        split_id=value.get("split_id"),
        split_role=DataRole(value["split_role"]) if value.get("split_role") else None,
        metrics=tuple((item[0], float(item[1])) for item in value["metrics"]),
        validity=EvidenceValidity(value["validity"]),
        failure_signature=value.get("failure_signature"),
        artifacts=tuple(value["artifacts"]),
        cpu_seconds=float(value["cpu_seconds"]),
        gpu_seconds=float(value["gpu_seconds"]),
        device_seconds=float(value["device_seconds"]),
        wall_seconds=float(value["wall_seconds"]),
        created_at=value["created_at"],
    )


def experiment_from_dict(value: dict[str, Any]) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=value["experiment_id"],
        candidate_id=value["candidate_id"],
        evaluator_id=value["evaluator_id"],
        fidelity=Fidelity(value["fidelity"]),
        split_id=value.get("split_id"),
        split_role=DataRole(value["split_role"]) if value.get("split_role") else None,
        seed=int(value["seed"]),
        resources=ResourceBudget(**value["resources"]),
        contract_digest=value["contract_digest"],
        mode=RunMode(value["mode"]),
        created_at=value["created_at"],
    )
