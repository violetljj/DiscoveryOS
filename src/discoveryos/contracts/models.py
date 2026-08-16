from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from discoveryos.util import digest_json, pairs, unpairs, utc_now


class ContractError(ValueError):
    pass


class DataRole(str, Enum):
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    SHADOW = "shadow"
    FINAL_BLIND = "final_blind"


class RunMode(str, Enum):
    DISCOVERY = "discovery"
    BENCHMARK = "benchmark"
    CERTIFICATION = "certification"


class Fidelity(str, Enum):
    G0 = "G0_STATIC"
    G1 = "G1_PROXY"
    G2 = "G2_DEVELOPMENT"
    G3 = "G3_REPLICATION"
    G4 = "G4_STRESS"
    G5 = "G5_DEVICE"
    G6 = "G6_SHADOW"
    G7 = "G7_FINAL_BLIND"

    @property
    def rank(self) -> int:
        return list(Fidelity).index(self)


class MetricDirection(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class ConstraintOperator(str, Enum):
    LE = "<="
    GE = ">="
    EQ = "=="


class EvidenceValidity(str, Enum):
    VALID = "VALID"
    INVALID_PROTOCOL = "INVALID_PROTOCOL"
    INVALID_MECHANICS = "INVALID_MECHANICS"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class GateDecision(str, Enum):
    FEASIBLE = "FEASIBLE"
    REJECT_HARD_CONSTRAINT = "REJECT_HARD_CONSTRAINT"
    INVALID = "INVALID"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ClaimCeiling(str, Enum):
    MECHANICS_ONLY = "MECHANICS_ONLY"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    SHADOW_SUPPORTED = "SHADOW_SUPPORTED"
    CERTIFIED_BLIND = "CERTIFIED_BLIND"


@dataclass(frozen=True, slots=True)
class DataSplit:
    split_id: str
    role: DataRole
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.split_id or not self.sha256:
            raise ContractError("data split requires split_id and sha256")
        if self.relative_path.startswith(("/", "\\")) or ".." in self.relative_path.replace("\\", "/").split("/"):
            raise ContractError("data split path must be relative and cannot escape its role directory")


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    name: str
    direction: MetricDirection
    objective: bool = True
    available_from: Fidelity = Fidelity.G1


@dataclass(frozen=True, slots=True)
class HardConstraint:
    metric: str
    operator: ConstraintOperator
    threshold: float
    applies_from: Fidelity


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    tokens: int = 0
    cpu_seconds: float = 0.0
    gpu_seconds: float = 0.0
    device_seconds: float = 0.0
    wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.as_dict().values()):
            raise ContractError("resource budgets cannot be negative")

    def as_dict(self) -> dict[str, float]:
        return {
            "tokens": float(self.tokens),
            "cpu_seconds": self.cpu_seconds,
            "gpu_seconds": self.gpu_seconds,
            "device_seconds": self.device_seconds,
            "wall_seconds": self.wall_seconds,
        }


@dataclass(frozen=True, slots=True)
class WinnerRule:
    method: str = "lexicographic"
    metric_order: tuple[str, ...] = ()
    require_fidelity: Fidelity = Fidelity.G2


@dataclass(frozen=True, slots=True)
class ProblemContract:
    contract_id: str
    version: str
    question: str
    baseline_candidate_id: str
    mutable_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    data_splits: tuple[DataSplit, ...]
    fidelities: tuple[Fidelity, ...]
    metrics: tuple[MetricDefinition, ...]
    hard_constraints: tuple[HardConstraint, ...]
    budget: ResourceBudget
    winner_rule: WinnerRule
    evaluator_bindings: tuple[tuple[str, str], ...]
    claim_ceiling: ClaimCeiling = ClaimCeiling.DEVELOPMENT_ONLY
    created_at: str = field(default_factory=utc_now)

    @property
    def digest(self) -> str:
        return digest_json(self)

    @property
    def evaluator_ids(self) -> tuple[str, ...]:
        return tuple(binding[0] for binding in self.evaluator_bindings)

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        metric_names = [metric.name for metric in self.metrics]
        split_ids = [split.split_id for split in self.data_splits]
        if len(set(metric_names)) != len(metric_names):
            issues.append("DUPLICATE_METRIC")
        if len(set(split_ids)) != len(split_ids):
            issues.append("DUPLICATE_SPLIT")
        if DataRole.DEVELOPMENT not in {split.role for split in self.data_splits}:
            issues.append("DEVELOPMENT_SPLIT_REQUIRED")
        if DataRole.FINAL_BLIND not in {split.role for split in self.data_splits}:
            issues.append("FINAL_BLIND_SPLIT_REQUIRED")
        if Fidelity.G0 not in self.fidelities or Fidelity.G2 not in self.fidelities:
            issues.append("G0_AND_G2_REQUIRED")
        for constraint in self.hard_constraints:
            if constraint.metric not in metric_names:
                issues.append(f"UNKNOWN_CONSTRAINT_METRIC:{constraint.metric}")
        for metric in self.winner_rule.metric_order:
            if metric not in metric_names:
                issues.append(f"UNKNOWN_WINNER_METRIC:{metric}")
        if self.winner_rule.method != "lexicographic":
            issues.append("UNSUPPORTED_WINNER_RULE")
        mutable = {path.replace("\\", "/").rstrip("/") for path in self.mutable_paths}
        forbidden = {path.replace("\\", "/").rstrip("/") for path in self.forbidden_paths}
        if any(left == right or left.startswith(right + "/") for left in mutable for right in forbidden):
            issues.append("MUTABLE_FORBIDDEN_OVERLAP")
        if not self.evaluator_bindings:
            issues.append("EVALUATOR_REQUIRED")
        if len(set(self.evaluator_ids)) != len(self.evaluator_ids):
            issues.append("DUPLICATE_EVALUATOR")
        if any(not evaluator_id or len(digest) != 64 for evaluator_id, digest in self.evaluator_bindings):
            issues.append("INVALID_EVALUATOR_BINDING")
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    candidate_id: str
    artifact_digest: str
    parent_ids: tuple[str, ...]
    operator_id: str
    strategy_id: str
    hypothesis_id: str | None
    parameters: tuple[tuple[str, Any], ...]
    semantic_delta: str
    expected_effects: tuple[tuple[str, Any], ...]
    environment_digest: str
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        artifact_digest: str,
        parent_ids: tuple[str, ...] = (),
        operator_id: str,
        strategy_id: str,
        parameters: dict[str, Any],
        semantic_delta: str,
        environment_digest: str,
        hypothesis_id: str | None = None,
        expected_effects: dict[str, Any] | None = None,
    ) -> "CandidateSpec":
        identity = {
            "artifact_digest": artifact_digest,
            "parent_ids": parent_ids,
            "operator_id": operator_id,
            "strategy_id": strategy_id,
            "parameters": parameters,
            "semantic_delta": semantic_delta,
            "environment_digest": environment_digest,
            "hypothesis_id": hypothesis_id,
        }
        return cls(
            candidate_id=f"cand_{digest_json(identity)[:20]}",
            artifact_digest=artifact_digest,
            parent_ids=parent_ids,
            operator_id=operator_id,
            strategy_id=strategy_id,
            hypothesis_id=hypothesis_id,
            parameters=pairs(parameters),
            semantic_delta=semantic_delta,
            expected_effects=pairs(expected_effects),
            environment_digest=environment_digest,
            created_at=utc_now(),
        )

    def parameter_dict(self) -> dict[str, Any]:
        return unpairs(self.parameters)


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    candidate_id: str
    evaluator_id: str
    fidelity: Fidelity
    split_id: str | None
    split_role: DataRole | None
    seed: int
    resources: ResourceBudget
    contract_digest: str
    mode: RunMode
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        evaluator_id: str,
        fidelity: Fidelity,
        split_id: str | None,
        split_role: DataRole | None,
        seed: int,
        resources: ResourceBudget,
        contract_digest: str,
        mode: RunMode,
    ) -> "ExperimentSpec":
        identity = {
            "candidate_id": candidate_id,
            "evaluator_id": evaluator_id,
            "fidelity": fidelity,
            "split_id": split_id,
            "split_role": split_role,
            "seed": seed,
            "contract_digest": contract_digest,
            "mode": mode,
        }
        return cls(
            experiment_id=f"exp_{digest_json(identity)[:20]}",
            candidate_id=candidate_id,
            evaluator_id=evaluator_id,
            fidelity=fidelity,
            split_id=split_id,
            split_role=split_role,
            seed=seed,
            resources=resources,
            contract_digest=contract_digest,
            mode=mode,
            created_at=utc_now(),
        )


@dataclass(frozen=True, slots=True)
class EvaluationOutput:
    metrics: tuple[tuple[str, float], ...]
    validity: EvidenceValidity = EvidenceValidity.VALID
    failure_signature: str | None = None
    artifacts: tuple[str, ...] = ()

    @classmethod
    def from_metrics(
        cls,
        metrics: dict[str, float],
        *,
        validity: EvidenceValidity = EvidenceValidity.VALID,
        failure_signature: str | None = None,
        artifacts: tuple[str, ...] = (),
    ) -> "EvaluationOutput":
        return cls(tuple(sorted(metrics.items())), validity, failure_signature, artifacts)


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    receipt_id: str
    experiment_id: str
    candidate_id: str
    contract_digest: str
    evaluator_id: str
    evaluator_digest: str
    data_digest: str | None
    fidelity: Fidelity
    split_id: str | None
    split_role: DataRole | None
    metrics: tuple[tuple[str, float], ...]
    validity: EvidenceValidity
    failure_signature: str | None
    artifacts: tuple[str, ...]
    cpu_seconds: float
    gpu_seconds: float
    device_seconds: float
    wall_seconds: float
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        experiment: ExperimentSpec,
        evaluator_digest: str,
        data_digest: str | None,
        output: EvaluationOutput,
        cpu_seconds: float,
        gpu_seconds: float = 0.0,
        device_seconds: float = 0.0,
        wall_seconds: float,
    ) -> "EvidenceRecord":
        identity = {
            "experiment_id": experiment.experiment_id,
            "candidate_id": experiment.candidate_id,
            "contract_digest": experiment.contract_digest,
            "evaluator_id": experiment.evaluator_id,
            "evaluator_digest": evaluator_digest,
            "data_digest": data_digest,
            "fidelity": experiment.fidelity,
            "split_id": experiment.split_id,
            "metrics": output.metrics,
            "validity": output.validity,
            "failure_signature": output.failure_signature,
            "artifacts": output.artifacts,
        }
        return cls(
            receipt_id=f"rcpt_{digest_json(identity)[:24]}",
            experiment_id=experiment.experiment_id,
            candidate_id=experiment.candidate_id,
            contract_digest=experiment.contract_digest,
            evaluator_id=experiment.evaluator_id,
            evaluator_digest=evaluator_digest,
            data_digest=data_digest,
            fidelity=experiment.fidelity,
            split_id=experiment.split_id,
            split_role=experiment.split_role,
            metrics=output.metrics,
            validity=output.validity,
            failure_signature=output.failure_signature,
            artifacts=output.artifacts,
            cpu_seconds=cpu_seconds,
            gpu_seconds=gpu_seconds,
            device_seconds=device_seconds,
            wall_seconds=wall_seconds,
            created_at=utc_now(),
        )

    def metric_dict(self) -> dict[str, float]:
        return dict(self.metrics)


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: GateDecision
    violations: tuple[str, ...]
    claim_ceiling: ClaimCeiling
