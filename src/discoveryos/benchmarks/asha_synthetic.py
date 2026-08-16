from __future__ import annotations

import asyncio
import math
import random
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.contracts.admission import ProtocolAdmission
from discoveryos.contracts.models import (
    CandidateSpec,
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    DataSplit,
    EvaluationOutput,
    EvidenceRecord,
    ExperimentSpec,
    Fidelity,
    GateDecision,
    HardConstraint,
    MetricDefinition,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    ResourceUsage,
    RunMode,
    WinnerRule,
)
from discoveryos.evaluation import EvaluatorRegistry, GateEngine, ReplayEngine
from discoveryos.operators.asha import ASHAOperator, MechanicalRetryRecord, RETRYABLE_FAILURES, RungDefinition
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.asha import ASHARunResult, ASHARunner
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ComputeFabric, ExperimentExecutor
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_bytes, jsonable


INITIAL_TRIALS = 18
ETA = 3
RUNG_RESOURCES = (
    RungDefinition("rung-low", Fidelity.G1, ResourceBudget(cpu_seconds=1, wall_seconds=2)),
    RungDefinition("rung-medium", Fidelity.G2, ResourceBudget(cpu_seconds=3, wall_seconds=2)),
    RungDefinition("rung-high", Fidelity.G3, ResourceBudget(cpu_seconds=9, wall_seconds=2)),
)
TOTAL_CPU_BUDGET = 54.0
DEFAULT_SEEDS = 12
MIN_PAIRED_WIN_RATE = 0.60


class SyntheticCurveEvaluator:
    evaluator_id = "synthetic_learning_curve_v1"
    version = "1.0.0"

    def evaluate(self, candidate: CandidateSpec, experiment: ExperimentSpec, data: bytes | None) -> EvaluationOutput:
        parameters = candidate.parameter_dict()
        if (
            parameters.get("fail_attempt_zero")
            and experiment.fidelity is Fidelity.G1
            and experiment.attempt_id == "attempt-0"
        ):
            raise RuntimeError("deterministic synthetic worker crash probe")
        delay_rank = int(parameters["completion_rank"])
        time.sleep(delay_rank * 0.002)
        quality_by_fidelity = {
            Fidelity.G0: float(parameters["quality_g1"]),
            Fidelity.G1: float(parameters["quality_g1"]),
            Fidelity.G2: float(parameters["quality_g2"]),
            Fidelity.G3: float(parameters["quality_g3"]),
            Fidelity.G7: float(parameters["quality_g3"]),
        }
        return EvaluationOutput.from_metrics(
            {"quality": round(quality_by_fidelity[experiment.fidelity], 8), "feasible": 1.0},
            reported_usage=ResourceUsage(cpu_seconds=experiment.resources.cpu_seconds, exit_code=0),
        )


@dataclass(frozen=True, slots=True)
class SyntheticProtocol:
    contract: ProblemContract
    candidates: tuple[CandidateSpec, ...]
    candidate_payloads: tuple[tuple[str, dict[str, Any]], ...]
    split_payloads: tuple[tuple[DataRole, bytes], ...]


@dataclass(slots=True)
class ArmContext:
    root: Path
    contract: ProblemContract
    candidates: tuple[CandidateSpec, ...]
    ledger: EvidenceLedger
    artifacts: ArtifactStore
    vault: SplitVault
    registry: EvaluatorRegistry
    executor: ExperimentExecutor


@dataclass(frozen=True, slots=True)
class RandomRunResult:
    run_id: str
    evidence: tuple[EvidenceRecord, ...]
    final_rung_evidence: tuple[EvidenceRecord, ...]
    retries: tuple[MechanicalRetryRecord, ...]
    total_usage: ResourceUsage


def run_asha_admission(workspace: Path, *, seeds: int = DEFAULT_SEEDS) -> dict[str, Any]:
    if seeds < 3:
        raise ValueError("ASHA admission requires at least three independent seeds")
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    seed_reports: list[dict[str, Any]] = []
    for seed in range(seeds):
        protocol_store = ArtifactStore(workspace / f"seed-{seed:03d}" / "protocol-artifacts")
        protocol = _build_protocol(seed, protocol_store)
        asha_context = _initialize_arm(workspace / f"seed-{seed:03d}" / "asha", protocol)
        random_context = _initialize_arm(workspace / f"seed-{seed:03d}" / "random", protocol)
        asha_run_id = f"synthetic-asha-seed-{seed}"
        operator = ASHAOperator(
            run_id=asha_run_id,
            contract=protocol.contract,
            rungs=RUNG_RESOURCES,
            metric_name="quality",
            eta=ETA,
            initial_trials=INITIAL_TRIALS,
        )
        asha_result = asyncio.run(ASHARunner(asha_context.executor, operator).run(list(protocol.candidates), seed=seed))
        random_result = asyncio.run(_run_random_arm(random_context, seed=seed))
        asha_checks = _audit_asha(asha_context, operator, asha_result)
        random_checks = _audit_random(random_context, random_result)
        asha_best = max(item.metric_dict()["quality"] for item in asha_result.final_rung_evidence)
        random_best = max(item.metric_dict()["quality"] for item in random_result.final_rung_evidence)
        seed_reports.append(
            {
                "seed": seed,
                "asha": _arm_report(asha_result.evidence, asha_result.final_rung_evidence, asha_result.total_usage),
                "random": _arm_report(random_result.evidence, random_result.final_rung_evidence, random_result.total_usage),
                "asha_best_quality": asha_best,
                "random_best_quality": random_best,
                "paired_delta": round(asha_best - random_best, 8),
                "promotion_count": len(asha_result.promotions),
                "asha_retry_count": len(asha_result.retries),
                "random_retry_count": len(random_result.retries),
                "checks": {"asha": asha_checks, "random": random_checks},
            }
        )
    deltas = [float(report["paired_delta"]) for report in seed_reports]
    wins = sum(delta > 0 for delta in deltas)
    ties = sum(delta == 0 for delta in deltas)
    losses = sum(delta < 0 for delta in deltas)
    required_wins = math.ceil(seeds * MIN_PAIRED_WIN_RATE)
    matched_cpu = all(
        abs(float(report["asha"]["actual_usage"]["cpu_seconds"]) - TOTAL_CPU_BUDGET) < 1e-6
        and abs(float(report["random"]["actual_usage"]["cpu_seconds"]) - TOTAL_CPU_BUDGET) < 1e-6
        for report in seed_reports
    )
    mechanics_passed = all(
        all(report["checks"][arm].values())
        for report in seed_reports
        for arm in ("asha", "random")
    )
    search_value_passed = wins >= required_wins and statistics.median(deltas) > 0
    final_blind_receipts = sum(
        int(seed_report[arm]["final_blind_receipts"])
        for seed_report in seed_reports
        for arm in ("asha", "random")
    )
    passed = mechanics_passed and matched_cpu and search_value_passed and final_blind_receipts == 0
    report = {
        "benchmark_id": "deterministic_asha_admission_v1",
        "status": "PASS" if passed else "FAIL",
        "verdict": "ASHA_ADMITTED_SYNTHETIC_ONLY" if passed else "ASHA_NOT_ADMITTED",
        "claim_ceiling": "SYNTHETIC_SEARCH_ADMISSION_ONLY",
        "frozen_policy": {
            "initial_trials": INITIAL_TRIALS,
            "eta": ETA,
            "rungs": [jsonable(rung) for rung in RUNG_RESOURCES],
            "total_cpu_budget_per_arm": TOTAL_CPU_BUDGET,
            "seeds": seeds,
            "minimum_paired_win_rate": MIN_PAIRED_WIN_RATE,
            "minimum_paired_wins": required_wins,
            "require_positive_median_delta": True,
        },
        "summary": {
            "paired_wins": wins,
            "ties": ties,
            "losses": losses,
            "paired_win_rate": wins / seeds,
            "median_best_quality_delta": statistics.median(deltas),
            "matched_actual_cpu": matched_cpu,
            "mechanics_passed": mechanics_passed,
            "search_value_passed": search_value_passed,
            "final_blind_receipts": final_blind_receipts,
        },
        "seed_reports": seed_reports,
    }
    ArtifactStore(workspace / "admission-artifacts").write_record("asha-admission-report.json", report)
    return report


def _build_protocol(seed: int, artifacts: ArtifactStore) -> SyntheticProtocol:
    generator = random.Random(seed)
    curves: list[dict[str, Any]] = [
        {
            "curve_role": "late-rung-champion",
            "quality_g1": 0.88,
            "quality_g2": 0.99,
            "quality_g3": 0.98,
            "completion_rank": 2,
            "fail_attempt_zero": False,
        },
        {
            "curve_role": "early-rung-decoy",
            "quality_g1": 0.99,
            "quality_g2": 0.74,
            "quality_g3": 0.72,
            "completion_rank": 0,
            "fail_attempt_zero": False,
        },
        {
            "curve_role": "consistently-strong",
            "quality_g1": 0.94,
            "quality_g2": 0.93,
            "quality_g3": 0.92,
            "completion_rank": 1,
            "fail_attempt_zero": False,
        },
    ]
    completion_ranks = list(range(3, INITIAL_TRIALS))
    generator.shuffle(completion_ranks)
    for index in range(3, INITIAL_TRIALS):
        final_quality = generator.uniform(0.18, 0.89)
        curves.append(
            {
                "curve_role": "partially-correlated",
                "quality_g1": min(0.86, max(0.05, 0.1 + 0.8 * final_quality + generator.uniform(-0.035, 0.035))),
                "quality_g2": min(0.91, max(0.05, 0.05 + 0.92 * final_quality + generator.uniform(-0.025, 0.025))),
                "quality_g3": final_quality,
                "completion_rank": completion_ranks[index - 3],
                "fail_attempt_zero": index == INITIAL_TRIALS - 1,
            }
        )
    candidate_payloads: list[tuple[str, dict[str, Any]]] = []
    candidates: list[CandidateSpec] = []
    for index, parameters in enumerate(curves):
        rounded = {
            name: round(value, 8) if isinstance(value, float) else value
            for name, value in parameters.items()
        }
        payload = {"algorithm": "synthetic_learning_curve", "candidate_index": index, "parameters": rounded}
        artifact_digest = artifacts.put_json(payload, metadata={"kind": "synthetic-candidate-v1"})
        candidate = CandidateSpec.create(
            artifact_digest=artifact_digest,
            operator_id="frozen_synthetic_pool_v1",
            strategy_id="asha_admission",
            parameters=rounded,
            semantic_delta=f"Frozen synthetic curve {index}; no adaptive mutation.",
            environment_digest="python-stdlib-synthetic-v1",
            expected_effects={"benchmark_only": True},
        )
        candidates.append(candidate)
        candidate_payloads.append((artifact_digest, payload))
    split_payloads = (
        (DataRole.DEVELOPMENT, b'{"synthetic":"development"}\n'),
        (DataRole.FINAL_BLIND, b'{"synthetic":"unused-final-blind"}\n'),
    )
    splits = tuple(
        DataSplit(
            split_id=f"synthetic_{role.value}",
            role=role,
            relative_path="synthetic.json",
            sha256=digest_bytes(payload),
        )
        for role, payload in split_payloads
    )
    registry = EvaluatorRegistry()
    registry.register(SyntheticCurveEvaluator())
    fidelities = (Fidelity.G0, Fidelity.G1, Fidelity.G2, Fidelity.G3, Fidelity.G7)
    contract = ProblemContract(
        contract_id=f"synthetic_asha_admission_seed_{seed}",
        version="1.0.0",
        question="Can asynchronous multi-fidelity allocation exploit a partially correlated curve under matched CPU budget?",
        baseline_candidate_id=candidates[0].candidate_id,
        mutable_paths=("synthetic/parameters",),
        forbidden_paths=("evaluation", "protocol", "vault"),
        data_splits=splits,
        fidelities=fidelities,
        metrics=(
            MetricDefinition("quality", MetricDirection.MAXIMIZE, available_from=Fidelity.G1),
            MetricDefinition("feasible", MetricDirection.MAXIMIZE, objective=False, available_from=Fidelity.G0),
        ),
        hard_constraints=(HardConstraint("feasible", ConstraintOperator.GE, 1.0, Fidelity.G0),),
        budget=ResourceBudget(cpu_seconds=TOTAL_CPU_BUDGET, wall_seconds=120),
        winner_rule=WinnerRule(metric_order=("quality",), require_fidelity=Fidelity.G3),
        evaluator_bindings=tuple(
            (fidelity.value, SyntheticCurveEvaluator.evaluator_id, registry.digest(SyntheticCurveEvaluator.evaluator_id))
            for fidelity in fidelities
        ),
        claim_ceiling=ClaimCeiling.DEVELOPMENT_ONLY,
    )
    return SyntheticProtocol(contract, tuple(candidates), tuple(candidate_payloads), split_payloads)


def _initialize_arm(root: Path, protocol: SyntheticProtocol) -> ArmContext:
    ledger = EvidenceLedger(root / "ledger.sqlite3")
    artifacts = ArtifactStore(root / "artifacts")
    vault = SplitVault(root / "vault", ledger)
    for role, payload in protocol.split_payloads:
        digest = vault.put_split(role, "synthetic.json", payload)
        expected = next(split.sha256 for split in protocol.contract.data_splits if split.role is role)
        if digest != expected:
            raise RuntimeError("synthetic split digest mismatch")
    for artifact_digest, payload in protocol.candidate_payloads:
        if artifacts.put_json(payload, metadata={"kind": "synthetic-candidate-v1"}) != artifact_digest:
            raise RuntimeError("synthetic candidate digest mismatch")
    registry = EvaluatorRegistry()
    registry.register(SyntheticCurveEvaluator())
    admission = ProtocolAdmission(registry, vault).check(protocol.contract, protocol.candidates[0])
    if not admission.admitted:
        raise RuntimeError("synthetic protocol admission failed: " + ",".join(admission.issues))
    ledger.add_contract(protocol.contract)
    for candidate in protocol.candidates:
        ledger.add_candidate(candidate)
    executor = ExperimentExecutor(
        contract=protocol.contract,
        ledger=ledger,
        artifacts=artifacts,
        vault=vault,
        registry=registry,
        fabric=ComputeFabric(cpu_workers=INITIAL_TRIALS),
    )
    return ArmContext(root, protocol.contract, protocol.candidates, ledger, artifacts, vault, registry, executor)


async def _run_random_arm(context: ArmContext, *, seed: int) -> RandomRunResult:
    run_id = f"synthetic-random-seed-{seed}"
    generator = random.Random(10_000 + seed)
    selected = generator.sample(list(context.candidates), int(TOTAL_CPU_BUDGET // RUNG_RESOURCES[-1].resources.cpu_seconds))
    split = next(split for split in context.contract.data_splits if split.role is DataRole.DEVELOPMENT)

    async def execute(candidate: CandidateSpec, attempt: int, trial_id: str | None = None) -> tuple[EvidenceRecord, ExperimentSpec]:
        experiment = ExperimentSpec.create(
            candidate_id=candidate.candidate_id,
            evaluator_id=context.contract.evaluator_id_for(Fidelity.G3),
            fidelity=Fidelity.G3,
            split_id=split.split_id,
            split_role=split.role,
            seed=seed,
            resources=RUNG_RESOURCES[-1].resources,
            contract_digest=context.contract.digest,
            mode=RunMode.BENCHMARK,
            trial_id=trial_id,
            replicate_id=f"{run_id}-seed-{seed}",
            rung_id=RUNG_RESOURCES[-1].rung_id,
            attempt_id=f"attempt-{attempt}",
            promotion_reason="matched-budget random high-fidelity draw" if attempt == 0 else "mechanical retry",
        )
        return await context.executor.execute(candidate, experiment), experiment

    initial = await asyncio.gather(*(execute(candidate, 0) for candidate in selected))
    evidence: list[EvidenceRecord] = []
    final: list[EvidenceRecord] = []
    retries: list[MechanicalRetryRecord] = []
    for candidate, (item, experiment) in zip(selected, initial):
        evidence.append(item)
        if item.failure_kind in RETRYABLE_FAILURES:
            retry_evidence, retry_experiment = await execute(candidate, 1, experiment.trial_id)
            evidence.append(retry_evidence)
            retry = MechanicalRetryRecord.create(
                run_id=run_id,
                failed_experiment=experiment,
                failed_evidence=item,
                retry_attempt_id=retry_experiment.attempt_id,
                retry_experiment_id=retry_experiment.experiment_id,
            )
            context.artifacts.write_record(f"random/{run_id}/retries/{retry.record_id}.json", retry)
            context.ledger.record_event("MECHANICAL_RETRY", jsonable(retry))
            retries.append(retry)
            item = retry_evidence
        if item.failure_kind is None:
            final.append(item)
    return RandomRunResult(run_id, tuple(evidence), tuple(final), tuple(retries), _sum_usage(evidence))


def _audit_asha(context: ArmContext, operator: ASHAOperator, result: ASHARunResult) -> dict[str, bool]:
    evidence_by_receipt = {item.receipt_id: item for item in result.evidence}
    experiments = {item.experiment_id: context.ledger.get_experiment(item.experiment_id) for item in result.evidence}
    promotion_replay = all(
        operator.replay_promotion(record, evidence_by_receipt=evidence_by_receipt, experiment_by_id=experiments)[0]
        for record in result.promotions
    )
    retry_replay = all(
        operator.replay_retry(record, evidence_by_receipt=evidence_by_receipt, experiment_by_id=experiments)[0]
        for record in result.retries
    )
    counts = {rung.rung_id: 0 for rung in RUNG_RESOURCES}
    for item in result.evidence:
        experiment = experiments[item.experiment_id]
        if item.failure_kind is None:
            counts[experiment.rung_id] += 1
    successful_g1 = [
        item
        for item in result.evidence
        if item.failure_kind is None and experiments[item.experiment_id].rung_id == "rung-low"
    ]
    g1_leader = max(successful_g1, key=lambda item: (item.metric_dict()["quality"], item.candidate_id))
    high_leader = max(result.final_rung_evidence, key=lambda item: (item.metric_dict()["quality"], item.candidate_id))
    return {
        "expected_rung_counts": counts == {"rung-low": 18, "rung-medium": 6, "rung-high": 2},
        "promotion_replay": promotion_replay and len(result.promotions) == 8,
        "multi_rung_reordering": g1_leader.candidate_id != high_leader.candidate_id,
        "retry_replay": retry_replay and len(result.retries) == 1,
        "evidence_replay": _replay_all(context),
        "resource_reconciliation": _reconciliations_complete(context, result.evidence),
        "system_failures_not_ranked": _system_failures_not_scientific(context, result.evidence, result.final_rung_evidence),
        "no_final_blind": not any(item.fidelity is Fidelity.G7 for item in result.evidence),
    }


def _audit_random(context: ArmContext, result: RandomRunResult) -> dict[str, bool]:
    evidence_by_receipt = {item.receipt_id: item for item in result.evidence}
    experiments = {item.experiment_id: context.ledger.get_experiment(item.experiment_id) for item in result.evidence}
    retry_replay = all(
        ASHAOperator.replay_retry(record, evidence_by_receipt=evidence_by_receipt, experiment_by_id=experiments)[0]
        for record in result.retries
    )
    expected_retries = sum(item.failure_kind in RETRYABLE_FAILURES for item in result.evidence)
    return {
        "expected_high_fidelity_count": len(result.final_rung_evidence) == 6,
        "retry_replay": retry_replay and len(result.retries) == expected_retries,
        "evidence_replay": _replay_all(context),
        "resource_reconciliation": _reconciliations_complete(context, result.evidence),
        "system_failures_not_ranked": _system_failures_not_scientific(context, result.evidence, result.final_rung_evidence),
        "no_final_blind": not any(item.fidelity is Fidelity.G7 for item in result.evidence),
    }


def _replay_all(context: ArmContext) -> bool:
    results = ReplayEngine(
        contract=context.contract,
        ledger=context.ledger,
        artifacts=context.artifacts,
        vault=context.vault,
        registry=context.registry,
    ).replay_all()
    return all(result.bindings_valid and result.evaluator_reproduced for result in results)


def _reconciliations_complete(context: ArmContext, evidence: tuple[EvidenceRecord, ...]) -> bool:
    return all(context.ledger.resource_reconciliation(f"reservation_{item.experiment_id}") is not None for item in evidence)


def _system_failures_not_scientific(
    context: ArmContext,
    evidence: tuple[EvidenceRecord, ...],
    final_evidence: tuple[EvidenceRecord, ...],
) -> bool:
    final_receipts = {item.receipt_id for item in final_evidence}
    failures = [item for item in evidence if item.failure_kind is not None]
    return all(
        GateEngine().evaluate(context.contract, item).decision is GateDecision.NOT_EVALUABLE
        and item.receipt_id not in final_receipts
        for item in failures
    )


def _arm_report(
    evidence: tuple[EvidenceRecord, ...],
    final_evidence: tuple[EvidenceRecord, ...],
    usage: ResourceUsage,
) -> dict[str, Any]:
    return {
        "evidence_count": len(evidence),
        "final_rung_count": len(final_evidence),
        "final_blind_receipts": sum(item.fidelity is Fidelity.G7 for item in evidence),
        "actual_usage": jsonable(usage),
        "failure_counts": {
            kind: sum(item.failure_kind is not None and item.failure_kind.value == kind for item in evidence)
            for kind in sorted({item.failure_kind.value for item in evidence if item.failure_kind is not None})
        },
    }


def _sum_usage(evidence: list[EvidenceRecord]) -> ResourceUsage:
    usages = [item.resource_usage for item in evidence]
    return ResourceUsage(
        llm_input_tokens=sum(item.llm_input_tokens for item in usages),
        llm_output_tokens=sum(item.llm_output_tokens for item in usages),
        llm_cache_tokens=sum(item.llm_cache_tokens for item in usages),
        cpu_seconds=sum(item.cpu_seconds for item in usages),
        gpu_seconds=sum(item.gpu_seconds for item in usages),
        device_seconds=sum(item.device_seconds for item in usages),
        wall_seconds=sum(item.wall_seconds for item in usages),
        peak_rss_bytes=max((item.peak_rss_bytes for item in usages), default=0),
        exit_code=max((item.exit_code or 0 for item in usages), default=0),
    )
