from __future__ import annotations

import asyncio
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.contracts.admission import ProtocolAdmission
from discoveryos.contracts.codec import contract_from_dict
from discoveryos.contracts.models import (
    CandidateSpec,
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    DataSplit,
    EvaluationOutput,
    EvidenceValidity,
    Fidelity,
    HardConstraint,
    MetricDefinition,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    WinnerRule,
)
from discoveryos.evaluation import EvaluatorRegistry, GateEngine, ReplayEngine
from discoveryos.operators import ParameterRange, RandomSearchOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ComputeFabric, DiscoveryResult, DiscoveryRunner, ExperimentExecutor
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import canonical_json, digest_bytes, jsonable


class ClearanceEvaluator:
    evaluator_id = "clearance_rule_v1"
    version = "1.0.0"

    def evaluate(self, candidate: CandidateSpec, experiment, data: bytes | None) -> EvaluationOutput:
        parameters = candidate.parameter_dict()
        required = {"threshold", "scale", "bias", "smoothing"}
        if set(parameters) != required:
            return EvaluationOutput.from_metrics({}, validity=EvidenceValidity.INVALID_MECHANICS, failure_signature="PARAMETER_SCHEMA_MISMATCH")
        threshold = float(parameters["threshold"])
        scale = float(parameters["scale"])
        bias = float(parameters["bias"])
        smoothing = float(parameters["smoothing"])
        latency_ms = 0.55 + 1.9 * smoothing + 0.08 * abs(scale - 1.0)
        if experiment.fidelity is Fidelity.G0:
            valid = 0.25 <= threshold <= 0.8 and 0.7 <= scale <= 1.3 and -0.2 <= bias <= 0.2 and 0 <= smoothing <= 0.95
            return EvaluationOutput.from_metrics(
                {"latency_ms": round(latency_ms, 8), "parameter_count": 4.0},
                validity=EvidenceValidity.VALID if valid else EvidenceValidity.INVALID_MECHANICS,
                failure_signature=None if valid else "PARAMETER_OUT_OF_BOUNDS",
            )
        if data is None:
            return EvaluationOutput.from_metrics({}, validity=EvidenceValidity.NOT_EVALUABLE, failure_signature="DATA_REQUIRED")
        samples = json.loads(data.decode("utf-8"))["samples"]
        if experiment.fidelity is Fidelity.G1:
            samples = samples[:16]
        previous: float | None = None
        estimates: list[float] = []
        false_clear = false_block = unsafe_count = safe_count = 0
        absolute_error = 0.0
        for sample in samples:
            raw = max(0.0, float(sample["observed"]) * scale + bias)
            estimate = raw if previous is None else smoothing * previous + (1.0 - smoothing) * raw
            previous = estimate
            estimates.append(estimate)
            unsafe = float(sample["truth"]) < 0.45
            predicted_blocked = estimate < threshold
            unsafe_count += int(unsafe)
            safe_count += int(not unsafe)
            false_clear += int(unsafe and not predicted_blocked)
            false_block += int(not unsafe and predicted_blocked)
            absolute_error += abs(estimate - float(sample["truth"]))
        jitter = sum(abs(right - left) for left, right in zip(estimates, estimates[1:])) / max(1, len(estimates) - 1)
        metrics = {
            "false_clear": false_clear / max(1, unsafe_count),
            "false_block": false_block / max(1, safe_count),
            "clearance_mae": absolute_error / max(1, len(samples)),
            "temporal_jitter": jitter,
            "latency_ms": latency_ms,
        }
        return EvaluationOutput.from_metrics({name: round(value, 8) for name, value in metrics.items()})


@dataclass(slots=True)
class DemoContext:
    workspace: Path
    contract: ProblemContract
    baseline: CandidateSpec
    ledger: EvidenceLedger
    artifacts: ArtifactStore
    vault: SplitVault
    registry: EvaluatorRegistry
    runner: DiscoveryRunner


def _samples(seed: int, count: int, *, shift: float = 0.0) -> bytes:
    generator = random.Random(seed)
    samples: list[dict[str, float]] = []
    previous_truth = 0.5
    for index in range(count):
        wave = 0.34 * math.sin(index / 5.0) + 0.1 * math.sin(index / 2.3)
        truth = min(1.1, max(0.08, 0.52 + wave + shift + generator.uniform(-0.055, 0.055)))
        observed = min(1.2, max(0.02, truth + 0.035 + generator.gauss(0, 0.055) + 0.018 * (previous_truth - truth)))
        samples.append({"observed": round(observed, 8), "truth": round(truth, 8)})
        previous_truth = truth
    return (canonical_json({"samples": samples}) + "\n").encode("utf-8")


def initialize_demo(workspace: Path) -> DemoContext:
    workspace = workspace.resolve()
    ledger = EvidenceLedger(workspace / "ledger.sqlite3")
    artifacts = ArtifactStore(workspace / "artifacts")
    vault = SplitVault(workspace / "vault", ledger)
    registry = EvaluatorRegistry()
    registry.register(ClearanceEvaluator())
    existing_contract = artifacts.records / "protocol" / "contract.json"
    if existing_contract.exists():
        contract = contract_from_dict(json.loads(existing_contract.read_text(encoding="utf-8")))
        baseline = ledger.get_candidate(contract.baseline_candidate_id)
    else:
        payloads = {
            DataRole.DEVELOPMENT: _samples(100, 96),
            DataRole.CALIBRATION: _samples(200, 48),
            DataRole.SHADOW: _samples(300, 64, shift=0.015),
            DataRole.FINAL_BLIND: _samples(400, 96, shift=-0.012),
        }
        splits: list[DataSplit] = []
        for role, payload in payloads.items():
            relative_path = "clearance.json"
            digest = vault.put_split(role, relative_path, payload)
            splits.append(DataSplit(f"clearance_{role.value}", role, relative_path, digest))
        baseline_parameters = {"threshold": 0.52, "scale": 1.0, "bias": 0.0, "smoothing": 0.2}
        baseline_artifact = artifacts.put_json(
            {"algorithm": "parameterized_clearance_rule", "parameters": baseline_parameters},
            metadata={"role": "baseline"},
        )
        baseline = CandidateSpec.create(
            artifact_digest=baseline_artifact,
            operator_id="human_baseline_v1",
            strategy_id="frozen_baseline",
            parameters=baseline_parameters,
            semantic_delta="Frozen reference implementation.",
            environment_digest="python-stdlib-v1",
            expected_effects={"role": "baseline"},
        )
        contract = ProblemContract(
            contract_id="clearance_demo_v1",
            version="1.0.0",
            question="Improve a causal near-field clearance rule without increasing false-clear risk or latency beyond frozen limits.",
            baseline_candidate_id=baseline.candidate_id,
            mutable_paths=("candidate/parameters",),
            forbidden_paths=("vault", "evaluation", "protocol"),
            data_splits=tuple(splits),
            fidelities=(Fidelity.G0, Fidelity.G1, Fidelity.G2, Fidelity.G7),
            metrics=(
                MetricDefinition("false_clear", MetricDirection.MINIMIZE, objective=False, available_from=Fidelity.G1),
                MetricDefinition("false_block", MetricDirection.MINIMIZE, available_from=Fidelity.G1),
                MetricDefinition("clearance_mae", MetricDirection.MINIMIZE, available_from=Fidelity.G1),
                MetricDefinition("temporal_jitter", MetricDirection.MINIMIZE, available_from=Fidelity.G1),
                MetricDefinition("latency_ms", MetricDirection.MINIMIZE, available_from=Fidelity.G0),
                MetricDefinition("parameter_count", MetricDirection.MINIMIZE, objective=False, available_from=Fidelity.G0),
            ),
            hard_constraints=(
                HardConstraint("false_clear", ConstraintOperator.LE, 0.08, Fidelity.G1),
                HardConstraint("latency_ms", ConstraintOperator.LE, 2.5, Fidelity.G0),
            ),
            budget=ResourceBudget(tokens=0, cpu_seconds=250, gpu_seconds=0, device_seconds=0, wall_seconds=500),
            winner_rule=WinnerRule(
                method="lexicographic",
                metric_order=("false_block", "clearance_mae", "temporal_jitter", "latency_ms"),
                require_fidelity=Fidelity.G2,
            ),
            evaluator_bindings=((ClearanceEvaluator.evaluator_id, registry.digest(ClearanceEvaluator.evaluator_id)),),
            claim_ceiling=ClaimCeiling.CERTIFIED_BLIND,
        )
        report = ProtocolAdmission(registry, vault).check(contract, baseline)
        if not report.admitted:
            raise RuntimeError("demo protocol admission failed: " + ", ".join(report.issues))
        ledger.add_candidate(baseline)
        ledger.add_contract(contract)
        artifacts.write_record("protocol/contract.json", contract)
        artifacts.write_record("protocol/admission.json", report)
    executor = ExperimentExecutor(
        contract=contract,
        ledger=ledger,
        artifacts=artifacts,
        vault=vault,
        registry=registry,
        fabric=ComputeFabric(cpu_workers=4),
    )
    return DemoContext(workspace, contract, baseline, ledger, artifacts, vault, registry, DiscoveryRunner(executor))


def run_demo_discovery(workspace: Path, *, candidate_count: int = 12, seed: int = 7) -> dict[str, Any]:
    context = initialize_demo(workspace)
    decision_path = context.artifacts.records / "decisions" / "discovery_winner.json"
    if decision_path.exists():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        return {"status": "ALREADY_COMPLETE", "winner_id": decision["candidate_id"], "counts": context.ledger.counts()}
    operator = RandomSearchOperator(
        context.artifacts,
        {
            "threshold": ParameterRange(0.40, 0.66),
            "scale": ParameterRange(0.88, 1.12),
            "bias": ParameterRange(-0.08, 0.05),
            "smoothing": ParameterRange(0.0, 0.82),
        },
        seed=seed,
    )
    candidates = [context.baseline, *operator.generate(candidate_count, parent=context.baseline)]
    result: DiscoveryResult = asyncio.run(context.runner.run(candidates, seed=seed))
    return {
        "status": "DISCOVERY_COMPLETE",
        "winner_id": result.winner_id,
        "pareto_candidate_ids": result.pareto_candidate_ids,
        "evaluated_by_fidelity": dict(result.evaluated_by_fidelity),
        "receipt_count": len(result.receipts),
        "blind_receipt_count": len(context.ledger.evidence_payloads(fidelity=Fidelity.G7.value)),
        "counts": context.ledger.counts(),
    }


def run_demo_certification(workspace: Path, *, seed: int = 7001) -> dict[str, Any]:
    context = initialize_demo(workspace)
    decision_path = context.artifacts.records / "decisions" / "discovery_winner.json"
    if not decision_path.exists():
        raise RuntimeError("run demo-discovery before certification")
    winner_id = json.loads(decision_path.read_text(encoding="utf-8"))["candidate_id"]
    candidate = context.ledger.get_candidate(winner_id)
    existing_path = context.artifacts.records / "decisions" / f"certification_{winner_id}.json"
    if existing_path.exists():
        decision = json.loads(existing_path.read_text(encoding="utf-8"))
        return {"status": "ALREADY_CERTIFIED", "winner_id": winner_id, "decision": decision, "counts": context.ledger.counts()}
    evidence = asyncio.run(context.runner.certify(candidate, seed=seed))
    gate = GateEngine().evaluate(context.contract, evidence)
    return {
        "status": "CERTIFICATION_COMPLETE",
        "winner_id": winner_id,
        "receipt_id": evidence.receipt_id,
        "metrics": evidence.metric_dict(),
        "gate_decision": gate.decision.value,
        "claim_ceiling": gate.claim_ceiling.value,
        "winner_changed": False,
        "counts": context.ledger.counts(),
    }


def demo_status(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    ledger_path = workspace / "ledger.sqlite3"
    if not ledger_path.exists():
        return {"status": "NOT_INITIALIZED", "workspace": str(workspace)}
    ledger = EvidenceLedger(ledger_path)
    records = workspace / "artifacts" / "records" / "decisions"
    discovery = records / "discovery_winner.json"
    certifications = sorted(records.glob("certification_*.json")) if records.exists() else []
    return {
        "status": "READY",
        "workspace": str(workspace),
        "counts": ledger.counts(),
        "discovery": json.loads(discovery.read_text(encoding="utf-8")) if discovery.exists() else None,
        "certifications": [json.loads(path.read_text(encoding="utf-8")) for path in certifications],
    }


def replay_demo(workspace: Path) -> dict[str, Any]:
    context = initialize_demo(workspace)
    results = ReplayEngine(
        contract=context.contract,
        ledger=context.ledger,
        artifacts=context.artifacts,
        vault=context.vault,
        registry=context.registry,
    ).replay_all()
    passed = sum(result.bindings_valid and result.evaluator_reproduced for result in results)
    return {
        "status": "REPLAY_COMPLETE" if passed == len(results) else "REPLAY_FAILED",
        "passed": passed,
        "total": len(results),
        "failures": [jsonable(result) for result in results if not (result.bindings_valid and result.evaluator_reproduced)],
    }
