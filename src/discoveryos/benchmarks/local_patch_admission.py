from __future__ import annotations

import asyncio
import json
import math
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.real_code_tasks import LOCK_PAYLOAD, RealCodeTask, admission_tasks
from discoveryos.contracts.executable import CommandSpec, EnvironmentLock, ExecutableCandidateBundle
from discoveryos.contracts.codec import contract_from_dict
from discoveryos.contracts.models import (
    CandidateSpec,
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    DataSplit,
    EvidenceRecord,
    EvidenceValidity,
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
from discoveryos.contracts.patch import GenerationStatus, MECHANICAL_REPAIR_FAILURES, MechanicalDiagnostic
from discoveryos.evaluation import EvaluatorRegistry, GateEngine, ReplayEngine
from discoveryos.operators.local_patch import CandidateBuildSpec, LocalPatchOperator, PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.repository_runner import ExecutableCandidateEvaluator
from discoveryos.runtime.scheduler import ComputeFabric, ExperimentExecutor
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_bytes, digest_json, jsonable


DEFAULT_TOKEN_CEILING = 90_000
DEFAULT_ITERATIONS = 3
MIN_TASKS = 6
MIN_SUCCESS_MARGIN = 2
MIN_SUMMED_IMPROVEMENT_MARGIN = 0.25


@dataclass(slots=True)
class AdmissionArm:
    name: str
    root: Path
    contract: ProblemContract
    baseline: CandidateSpec
    ledger: EvidenceLedger
    artifacts: ArtifactStore
    vault: SplitVault
    registry: EvaluatorRegistry
    executor: ExperimentExecutor


def run_local_patch_admission(
    workspace: Path,
    *,
    provider: PatchProvider,
    token_ceiling: int = DEFAULT_TOKEN_CEILING,
    iterations: int = DEFAULT_ITERATIONS,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if token_ceiling <= 0 or iterations < 2:
        raise ValueError("real-code admission requires a positive token ceiling and at least two iterative calls")
    tasks = admission_tasks()
    if len(tasks) < MIN_TASKS:
        raise RuntimeError("real-code admission protocol requires at least six tasks")
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    task_reports: list[dict[str, Any]] = []
    for task in tasks:
        repository, base_commit = task.initialize_repository(workspace / "protocol")
        baseline_arm = _initialize_arm(
            workspace / "arms" / task.task_id / "baseline",
            task,
            repository,
            base_commit,
            token_ceiling,
        )
        one_shot_arm = _initialize_arm(
            workspace / "arms" / task.task_id / "one-shot",
            task,
            repository,
            base_commit,
            token_ceiling,
        )
        iterative_arm = _initialize_arm(
            workspace / "arms" / task.task_id / "iterative",
            task,
            repository,
            base_commit,
            token_ceiling,
        )
        baseline = asyncio.run(_run_arm(baseline_arm, task, provider=None, iterations=0, token_ceiling=token_ceiling))
        one_shot = asyncio.run(_run_arm(one_shot_arm, task, provider=provider, iterations=1, token_ceiling=token_ceiling))
        iterative = asyncio.run(
            _run_arm(iterative_arm, task, provider=provider, iterations=iterations, token_ceiling=token_ceiling)
        )
        if not math.isclose(baseline["best_score"], one_shot["baseline_score"]) or not math.isclose(
            baseline["best_score"], iterative["baseline_score"]
        ):
            raise RuntimeError(f"baseline drift across arms for {task.task_id}")
        task_reports.append(
            {
                "task_id": task.task_id,
                "category": task.category,
                "base_commit": base_commit,
                "baseline": baseline,
                "one_shot_llm": one_shot,
                "iterative_local_patch": iterative,
                "paired_delta": round(iterative["best_score"] - one_shot["best_score"], 8),
            }
        )
        if progress:
            progress(
                f"completed {task.task_id}: baseline={baseline['best_score']:.4f} "
                f"one_shot={one_shot['best_score']:.4f} iterative={iterative['best_score']:.4f}"
            )

    iterative_successes = sum(report["iterative_local_patch"]["improved"] for report in task_reports)
    one_shot_successes = sum(report["one_shot_llm"]["improved"] for report in task_reports)
    deltas = [float(report["paired_delta"]) for report in task_reports]
    wins = sum(delta > 0 for delta in deltas)
    ties = sum(delta == 0 for delta in deltas)
    losses = sum(delta < 0 for delta in deltas)
    one_shot_improvement = sum(report["one_shot_llm"]["best_feasible_improvement"] for report in task_reports)
    iterative_improvement = sum(report["iterative_local_patch"]["best_feasible_improvement"] for report in task_reports)
    mechanics_passed = all(
        report[arm]["checks"][check]
        for report in task_reports
        for arm in ("baseline", "one_shot_llm", "iterative_local_patch")
        for check in report[arm]["checks"]
    )
    matched_token_ceiling = all(
        report[arm]["token_ceiling"] == token_ceiling and report[arm]["actual_usage"]["tokens"] <= token_ceiling
        for report in task_reports
        for arm in ("one_shot_llm", "iterative_local_patch")
    )
    search_value_passed = (
        iterative_successes >= one_shot_successes + MIN_SUCCESS_MARGIN
        and iterative_improvement >= one_shot_improvement + MIN_SUMMED_IMPROVEMENT_MARGIN
        and wins >= 2
        and losses == 0
    )
    passed = mechanics_passed and matched_token_ceiling and search_value_passed
    report = {
        "benchmark_id": "matched_token_real_code_local_patch_admission_v1",
        "status": "PASS" if passed else "FAIL",
        "verdict": "LLM_LOCAL_PATCH_ADMITTED_REAL_CODE_ONLY" if passed else "LLM_LOCAL_PATCH_NOT_ADMITTED",
        "claim_ceiling": "REAL_CODE_SEARCH_MECHANISM_ONLY",
        "frozen_policy": {
            "provider": provider.provider_name,
            "model": provider.model,
            "task_count": len(tasks),
            "task_categories": [task.category for task in tasks],
            "arms": ["Baseline", "One-shot LLM", "Iterative Local Patch"],
            "token_ceiling_per_llm_arm_per_task": token_ceiling,
            "iterative_scientific_call_limit": iterations,
            "mechanical_repairs_per_generation": 1,
            "minimum_success_task_margin": MIN_SUCCESS_MARGIN,
            "minimum_summed_improvement_margin": MIN_SUMMED_IMPROVEMENT_MARGIN,
            "minimum_paired_wins": 2,
            "maximum_paired_losses": 0,
            "final_blind_allowed": False,
            "protocol_digest": digest_json(tuple(jsonable(task) for task in tasks)),
        },
        "summary": {
            "one_shot_success_tasks": one_shot_successes,
            "iterative_success_tasks": iterative_successes,
            "one_shot_summed_improvement": round(one_shot_improvement, 8),
            "iterative_summed_improvement": round(iterative_improvement, 8),
            "paired_wins": wins,
            "ties": ties,
            "losses": losses,
            "median_paired_delta": statistics.median(deltas),
            "matched_token_ceiling": matched_token_ceiling,
            "mechanics_passed": mechanics_passed,
            "search_value_passed": search_value_passed,
            "final_blind_receipts": sum(
                report[arm]["final_blind_receipts"]
                for report in task_reports
                for arm in ("baseline", "one_shot_llm", "iterative_local_patch")
            ),
        },
        "task_reports": task_reports,
        "not_authorized": ["BOHB", "qNEHVI", "Structural Rewrite", "Meta-Strategy", "learning-based Advisor"],
    }
    ArtifactStore(workspace / "admission-artifacts").write_record("local-patch-admission-report.json", report)
    return report


def audit_local_patch_admission_report(workspace: Path) -> dict[str, Any]:
    """Recompute candidate-validity fields from frozen ledgers without model calls."""
    workspace = workspace.resolve()
    original_path = workspace / "admission-artifacts" / "records" / "local-patch-admission-report.json"
    original_payload = original_path.read_bytes()
    report = json.loads(original_payload)
    for task_report in report["task_reports"]:
        task_id = task_report["task_id"]
        for report_key, arm_dir in (
            ("baseline", "baseline"),
            ("one_shot_llm", "one-shot"),
            ("iterative_local_patch", "iterative"),
        ):
            root = workspace / "arms" / task_id / arm_dir
            ledger = EvidenceLedger(root / "ledger.sqlite3")
            with ledger.connect() as connection:
                payload = json.loads(connection.execute("SELECT payload FROM contracts").fetchone()["payload"])
            contract = contract_from_dict(payload)
            generated_ids = {
                record.candidate_id for record in ledger.generation_records() if record.candidate_id is not None
            }
            by_candidate: dict[str, list[EvidenceRecord]] = {candidate_id: [] for candidate_id in generated_ids}
            for evidence in ledger.evidence_records():
                if evidence.candidate_id in by_candidate:
                    by_candidate[evidence.candidate_id].append(evidence)
            invalid = 0
            hard_violations = 0
            for records in by_candidate.values():
                g2 = next((item for item in records if item.fidelity is Fidelity.G2), None)
                decision = GateEngine().evaluate(contract, g2).decision if g2 else GateDecision.INVALID
                invalid += int(decision is not GateDecision.FEASIBLE)
                hard_violations += int(decision is GateDecision.REJECT_HARD_CONSTRAINT)
            arm_report = task_report[report_key]
            arm_report["generated_candidate_count"] = len(generated_ids)
            arm_report["invalid_candidate_count"] = invalid
            arm_report["invalid_rate"] = invalid / len(generated_ids) if generated_ids else 0.0
            arm_report["hard_gate_violations"] = hard_violations
    report["audit"] = {
        "original_report_sha256": digest_bytes(original_payload),
        "audit_kind": "candidate-validity-recount-v1",
        "model_calls_repeated": False,
        "verdict_changed": False,
    }
    ArtifactStore(workspace / "admission-artifacts").write_record("local-patch-admission-audited-report.json", report)
    return report


async def _run_arm(
    arm: AdmissionArm,
    task: RealCodeTask,
    *,
    provider: PatchProvider | None,
    iterations: int,
    token_ceiling: int,
) -> dict[str, Any]:
    started = time.monotonic()
    baseline_evidence = await _evaluate_candidate(arm, arm.baseline, attempt="baseline")
    baseline_score = _development_score(baseline_evidence)
    best_score = baseline_score
    best_candidate = arm.baseline
    first_improvement_tokens: int | None = None
    best_tokens: int | None = 0
    generated_candidates = 0
    invalid_candidates = 0
    hard_gate_violations = 0
    scientific_calls = 0
    parent = arm.baseline
    parent_evidence = baseline_evidence
    if provider is not None:
        operator = LocalPatchOperator(
            provider=provider,
            artifacts=arm.artifacts,
            ledger=arm.ledger,
            contract=arm.contract,
            strategy_id="one_shot_llm" if iterations == 1 else "iterative_local_patch",
        )
        for index in range(iterations):
            if best_score >= 1.0:
                break
            remaining_tokens = token_ceiling - _generation_tokens(arm)
            minimum_call_tokens = int(getattr(provider, "minimum_token_reservation", 1))
            if remaining_tokens < minimum_call_tokens:
                break
            parent_bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, parent.artifact_digest)
            mutable_files = _materialize_files(parent_bundle, arm.contract.mutable_paths)
            result = operator.propose(
                parent=parent,
                mutable_files=mutable_files,
                development_evidence_summary=_evidence_summary(parent_evidence, best_score),
                failure_signature=_failure_signature(parent_evidence),
                semantic_delta_memory=(parent.semantic_delta,),
                remaining_budget=ResourceBudget(tokens=remaining_tokens, wall_seconds=300),
                build=_build_spec(parent_bundle),
            )
            scientific_calls += 1
            if result.candidate is None:
                continue
            generated_candidates += 1
            candidate = result.candidate
            candidate_evidence = await _evaluate_candidate(arm, candidate, attempt=f"proposal-{index}")
            repaired = False
            mechanical = _mechanical_failure(candidate_evidence)
            if mechanical is not None and token_ceiling - _generation_tokens(arm) >= minimum_call_tokens:
                repaired_result = await _repair_once(
                    arm,
                    operator,
                    result.record.generation_id,
                    candidate,
                    candidate_evidence,
                    mechanical,
                    token_ceiling - _generation_tokens(arm),
                )
                if repaired_result is not None:
                    repaired = True
                    candidate, candidate_evidence = repaired_result
                    generated_candidates += 1
            score = _development_score(candidate_evidence, default=None)
            gate = _last_gate(arm, candidate_evidence)
            if score is None or gate is not GateDecision.FEASIBLE:
                invalid_candidates += 1
                hard_gate_violations += int(gate is GateDecision.REJECT_HARD_CONSTRAINT)
                parent_evidence = candidate_evidence
                if repaired:
                    parent = best_candidate
                continue
            cumulative_tokens = _generation_tokens(arm)
            if score > baseline_score and first_improvement_tokens is None:
                first_improvement_tokens = cumulative_tokens
            if score > best_score:
                best_score = score
                best_candidate = candidate
                best_tokens = cumulative_tokens
            parent = best_candidate
            parent_evidence = candidate_evidence if candidate.candidate_id == best_candidate.candidate_id else parent_evidence

    makespan = time.monotonic() - started
    evidence = arm.ledger.evidence_records()
    generations = arm.ledger.generation_records()
    generated_ids = {record.candidate_id for record in generations if record.candidate_id is not None}
    evidence_by_candidate = {
        candidate_id: [item for item in evidence if item.candidate_id == candidate_id]
        for candidate_id in generated_ids
    }
    generated_candidates = len(generated_ids)
    invalid_candidates = sum(
        _last_gate(arm, tuple(records)) is not GateDecision.FEASIBLE
        for records in evidence_by_candidate.values()
    )
    hard_gate_violations = sum(
        _last_gate(arm, tuple(records)) is GateDecision.REJECT_HARD_CONSTRAINT
        for records in evidence_by_candidate.values()
    )
    experiment_wall = sum(item.resource_usage.wall_seconds for item in evidence)
    generation_wall = sum(item.usage.wall_seconds for item in generations)
    repairs = sum(item.kind.value == "MECHANICAL_REPAIR" for item in generations)
    successful_proposals = sum(item.kind.value == "PROPOSAL" for item in generations)
    final_blind_receipts = sum(item.fidelity is Fidelity.G7 for item in evidence)
    replay_results = ReplayEngine(
        contract=arm.contract,
        ledger=arm.ledger,
        artifacts=arm.artifacts,
        vault=arm.vault,
        registry=arm.registry,
    ).replay_all()
    artifacts_complete = _generation_artifacts_complete(arm)
    usage_complete = all(
        record.usage_is_exact and (record.status is not GenerationStatus.SUCCEEDED or record.usage.tokens > 0)
        for record in generations
    )
    return {
        "arm": arm.name,
        "baseline_score": baseline_score,
        "best_score": best_score,
        "best_candidate_id": best_candidate.candidate_id,
        "best_feasible_improvement": round(best_score - baseline_score, 8),
        "improved": best_score > baseline_score,
        "token_ceiling": token_ceiling if provider is not None else 0,
        "scientific_calls": scientific_calls,
        "generation_count": len(generations),
        "generated_candidate_count": generated_candidates,
        "invalid_candidate_count": invalid_candidates,
        "invalid_rate": invalid_candidates / generated_candidates if generated_candidates else 0.0,
        "repair_count": repairs,
        "repair_rate": repairs / successful_proposals if successful_proposals else 0.0,
        "tokens_to_first_improvement": first_improvement_tokens,
        "tokens_to_best": best_tokens,
        "hard_gate_violations": hard_gate_violations,
        "final_blind_receipts": final_blind_receipts,
        "actual_usage": {
            "tokens": _generation_tokens(arm),
            "llm_input_tokens": sum(item.usage.llm_input_tokens for item in generations),
            "llm_output_tokens": sum(item.usage.llm_output_tokens for item in generations),
            "llm_cache_tokens": sum(item.usage.llm_cache_tokens for item in generations),
            "cpu_seconds": sum(item.resource_usage.cpu_seconds for item in evidence),
            "gpu_seconds": sum(item.resource_usage.gpu_seconds for item in evidence),
            "experiment_wall_sum": experiment_wall,
            "generation_wall_sum": generation_wall,
            "end_to_end_makespan": makespan,
            "orchestration_overhead": max(0.0, makespan - experiment_wall - generation_wall),
        },
        "checks": {
            "evidence_replay_complete": bool(replay_results) and all(
                item.bindings_valid and item.evaluator_reproduced for item in replay_results
            ),
            "generation_artifacts_complete": artifacts_complete,
            "successful_generation_usage_reported": usage_complete,
            "token_ceiling_respected": provider is None or _generation_tokens(arm) <= token_ceiling,
            "no_final_blind": final_blind_receipts == 0,
            "one_shot_scientific_limit": iterations != 1 or scientific_calls <= 1,
            "iterative_scientific_limit": scientific_calls <= iterations,
            "one_repair_per_generation": repairs <= successful_proposals,
        },
    }


async def _repair_once(
    arm: AdmissionArm,
    operator: LocalPatchOperator,
    generation_id: str,
    failed_candidate: CandidateSpec,
    evidence: tuple[EvidenceRecord, ...],
    mechanical: EvidenceRecord,
    remaining_tokens: int,
) -> tuple[CandidateSpec, tuple[EvidenceRecord, ...]] | None:
    failed_bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, failed_candidate.artifact_digest)
    diagnostic = MechanicalDiagnostic.from_evidence(mechanical, _mechanical_excerpt(arm, mechanical))
    try:
        mutable_files = _materialize_files(failed_bundle, arm.contract.mutable_paths)
        repair_stack = failed_bundle.effective_patch_stack
        repair_touched = failed_bundle.touched_paths
    except RuntimeError:
        repair_stack = failed_bundle.effective_patch_stack[:-1]
        repair_touched = tuple(
            sorted(
                path
                for patch in repair_stack
                for path in _patch_paths(patch)
            )
        )
        if not repair_stack:
            raise RuntimeError("repair cannot discard the frozen baseline patch")
        fallback = ExecutableCandidateBundle(
            base_repository=failed_bundle.base_repository,
            base_commit=failed_bundle.base_commit,
            patch_diff=repair_stack[-1],
            mutable_paths=failed_bundle.mutable_paths,
            forbidden_paths=failed_bundle.forbidden_paths,
            touched_paths=repair_touched or (failed_bundle.entrypoint,),
            entrypoint=failed_bundle.entrypoint,
            environment_lock=failed_bundle.environment_lock,
            build_command=failed_bundle.build_command,
            test_command=failed_bundle.test_command,
            evaluation_command=failed_bundle.evaluation_command,
            patch_stack=repair_stack,
        )
        mutable_files = _materialize_files(fallback, arm.contract.mutable_paths)
    result = operator.repair(
        generation_id=generation_id,
        parent=failed_candidate,
        mutable_files=mutable_files,
        diagnostic=diagnostic,
        semantic_delta_memory=(failed_candidate.semantic_delta,),
        remaining_budget=ResourceBudget(tokens=remaining_tokens, wall_seconds=300),
        build=CandidateBuildSpec(
            base_repository=Path(failed_bundle.base_repository),
            base_commit=failed_bundle.base_commit,
            entrypoint=failed_bundle.entrypoint,
            environment_lock=failed_bundle.environment_lock,
            build_command=failed_bundle.build_command,
            test_command=failed_bundle.test_command,
            evaluation_command=failed_bundle.evaluation_command,
            parent_patch_stack=repair_stack,
            parent_touched_paths=repair_touched,
        ),
    )
    if result.candidate is None:
        return None
    return result.candidate, await _evaluate_candidate(arm, result.candidate, attempt="mechanical-repair")


def _initialize_arm(
    root: Path,
    task: RealCodeTask,
    repository: Path,
    base_commit: str,
    token_ceiling: int,
) -> AdmissionArm:
    artifacts = ArtifactStore(root / "artifacts")
    ledger = EvidenceLedger(root / "ledger.sqlite3")
    vault = SplitVault(root / "vault", ledger)
    development_payload = b"bounded real-code development split\n"
    blind_payload = b"unused final-blind sentinel\n"
    vault.put_split(DataRole.DEVELOPMENT, "development.bin", development_payload)
    vault.put_split(DataRole.FINAL_BLIND, "final-blind.bin", blind_payload)
    evaluator_digest = EvaluatorRegistry()
    probe = ExecutableCandidateEvaluator(artifacts)
    evaluator_digest.register(probe)
    digest = evaluator_digest.digest(probe.evaluator_id)
    baseline_patch = _baseline_patch(task.entrypoint, (repository / task.entrypoint).read_text(encoding="utf-8"))
    baseline_bundle = ExecutableCandidateBundle(
        base_repository=str(repository),
        base_commit=base_commit,
        patch_diff=baseline_patch,
        mutable_paths=(task.entrypoint,),
        forbidden_paths=("public_tests.py", "evaluate.py", "requirements.lock"),
        touched_paths=(task.entrypoint,),
        entrypoint=task.entrypoint,
        environment_lock=EnvironmentLock("requirements.lock", digest_bytes(LOCK_PAYLOAD)),
        build_command=CommandSpec(("python", "-m", "py_compile", task.entrypoint)),
        test_command=CommandSpec(("python", "public_tests.py")),
        evaluation_command=CommandSpec(("python", "evaluate.py")),
        patch_stack=(baseline_patch,),
    )
    baseline = CandidateSpec.create(
        artifact_digest=baseline_bundle.store(artifacts),
        operator_id="frozen_baseline",
        strategy_id="baseline",
        parameters={"task_id": task.task_id},
        semantic_delta="Content-addressed no-algorithm-change baseline marker.",
        environment_digest=task.environment_digest,
    )
    contract = ProblemContract(
        contract_id=f"r1-local-patch-{task.task_id}",
        version="1.0",
        question=task.question,
        baseline_candidate_id=baseline.candidate_id,
        mutable_paths=(task.entrypoint,),
        forbidden_paths=("public_tests.py", "evaluate.py", "requirements.lock"),
        data_splits=(
            DataSplit("development", DataRole.DEVELOPMENT, "development.bin", digest_bytes(development_payload)),
            DataSplit("final-blind", DataRole.FINAL_BLIND, "final-blind.bin", digest_bytes(blind_payload)),
        ),
        fidelities=(Fidelity.G0, Fidelity.G1, Fidelity.G2),
        metrics=(
            MetricDefinition("score", MetricDirection.MAXIMIZE, available_from=Fidelity.G0),
            MetricDefinition("valid", MetricDirection.MAXIMIZE, objective=False, available_from=Fidelity.G0),
        ),
        hard_constraints=(HardConstraint("valid", ConstraintOperator.GE, 1.0, Fidelity.G0),),
        budget=ResourceBudget(tokens=token_ceiling, cpu_seconds=600, wall_seconds=3600),
        winner_rule=WinnerRule(metric_order=("score",), require_fidelity=Fidelity.G2),
        evaluator_bindings=tuple((fidelity.value, probe.evaluator_id, digest) for fidelity in (Fidelity.G0, Fidelity.G1, Fidelity.G2)),
        claim_ceiling=ClaimCeiling.DEVELOPMENT_ONLY,
    )
    registry = EvaluatorRegistry()
    registry.register(ExecutableCandidateEvaluator(artifacts, contract=contract))
    ledger.add_contract(contract)
    ledger.add_candidate(baseline)
    return AdmissionArm(
        name=root.name,
        root=root,
        contract=contract,
        baseline=baseline,
        ledger=ledger,
        artifacts=artifacts,
        vault=vault,
        registry=registry,
        executor=ExperimentExecutor(
            contract=contract,
            ledger=ledger,
            artifacts=artifacts,
            vault=vault,
            registry=registry,
            fabric=ComputeFabric(cpu_workers=1),
        ),
    )


async def _evaluate_candidate(arm: AdmissionArm, candidate: CandidateSpec, *, attempt: str) -> tuple[EvidenceRecord, ...]:
    evidence: list[EvidenceRecord] = []
    for fidelity, resources in (
        (Fidelity.G0, ResourceBudget(cpu_seconds=5, wall_seconds=15)),
        (Fidelity.G1, ResourceBudget(cpu_seconds=5, wall_seconds=15)),
        (Fidelity.G2, ResourceBudget(cpu_seconds=5, wall_seconds=15)),
    ):
        split_id = "development" if fidelity in {Fidelity.G1, Fidelity.G2} else None
        split_role = DataRole.DEVELOPMENT if split_id else None
        experiment = ExperimentSpec.create(
            candidate_id=candidate.candidate_id,
            evaluator_id=arm.contract.evaluator_id_for(fidelity),
            fidelity=fidelity,
            split_id=split_id,
            split_role=split_role,
            seed=0,
            resources=resources,
            contract_digest=arm.contract.digest,
            mode=RunMode.BENCHMARK,
            replicate_id="admission-seed-0",
            rung_id=fidelity.value,
            attempt_id=attempt,
        )
        item = await arm.executor.execute(candidate, experiment)
        evidence.append(item)
        if item.validity is not EvidenceValidity.VALID:
            break
    return tuple(evidence)


def _development_score(evidence: tuple[EvidenceRecord, ...], default: float | None = -math.inf) -> float | None:
    item = next((record for record in evidence if record.fidelity is Fidelity.G2), None)
    if item is None or item.validity is not EvidenceValidity.VALID:
        return default
    return item.metric_dict().get("score", default)


def _last_gate(arm: AdmissionArm, evidence: tuple[EvidenceRecord, ...]) -> GateDecision:
    item = next((record for record in reversed(evidence) if record.fidelity is Fidelity.G2), evidence[-1])
    return GateEngine().evaluate(arm.contract, item).decision


def _mechanical_failure(evidence: tuple[EvidenceRecord, ...]) -> EvidenceRecord | None:
    return next(
        (
            item
            for item in evidence
            if item.validity is not EvidenceValidity.VALID and item.failure_kind in MECHANICAL_REPAIR_FAILURES
        ),
        None,
    )


def _mechanical_excerpt(arm: AdmissionArm, evidence: EvidenceRecord) -> str:
    blocks: list[str] = []
    for digest in evidence.artifacts:
        try:
            value = json.loads(arm.artifacts.get_bytes(digest))
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            continue
        if isinstance(value, dict) and value.get("step") in {"build", "test"}:
            blocks.append(f"{value.get('step')} stdout:\n{value.get('stdout', '')}\nstderr:\n{value.get('stderr', '')}")
    return ("\n\n".join(blocks) or evidence.failure_signature or "mechanical failure")[-4000:]


def _evidence_summary(evidence: tuple[EvidenceRecord, ...], best_score: float) -> str:
    rows = []
    for item in evidence:
        rows.append(
            {
                "fidelity": item.fidelity.value,
                "validity": item.validity.value,
                "metrics": item.metric_dict() if item.validity is EvidenceValidity.VALID else {},
                "failure_signature": item.failure_signature,
            }
        )
    return json.dumps({"parent_development_evidence": rows, "best_development_score": best_score}, sort_keys=True)


def _failure_signature(evidence: tuple[EvidenceRecord, ...]) -> str | None:
    return next((item.failure_signature for item in evidence if item.failure_signature), None)


def _build_spec(bundle: ExecutableCandidateBundle) -> CandidateBuildSpec:
    return CandidateBuildSpec(
        base_repository=Path(bundle.base_repository),
        base_commit=bundle.base_commit,
        entrypoint=bundle.entrypoint,
        environment_lock=bundle.environment_lock,
        build_command=bundle.build_command,
        test_command=bundle.test_command,
        evaluation_command=bundle.evaluation_command,
        parent_patch_stack=bundle.effective_patch_stack,
        parent_touched_paths=bundle.touched_paths,
    )


def _materialize_files(bundle: ExecutableCandidateBundle, paths: tuple[str, ...]) -> dict[str, str]:
    repository = Path(bundle.base_repository)
    with tempfile.TemporaryDirectory(prefix="discoveryos-context-") as temporary:
        worktree = Path(temporary) / "repo"
        _git(repository, "worktree", "add", "--detach", "--force", str(worktree), bundle.base_commit)
        try:
            for patch in bundle.effective_patch_stack:
                result = subprocess.run(
                    ("git", "-C", str(worktree), "apply", "--whitespace=nowarn", "-"),
                    input=patch,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "candidate patch failed to materialize")
            return {path: (worktree / path).read_text(encoding="utf-8") for path in paths}
        finally:
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "remove", "--force", str(worktree)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "prune"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def _generation_tokens(arm: AdmissionArm) -> int:
    return sum(item.usage.tokens for item in arm.ledger.generation_records())


def _generation_artifacts_complete(arm: AdmissionArm) -> bool:
    try:
        for record in arm.ledger.generation_records():
            arm.artifacts.get_bytes(record.request_artifact_digest)
            if record.raw_response_digest:
                arm.artifacts.get_bytes(record.raw_response_digest)
            if record.provenance_artifact_digest:
                arm.artifacts.get_bytes(record.provenance_artifact_digest)
            if record.candidate_artifact_digest:
                bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, record.candidate_artifact_digest)
                if bundle.generation_provenance_digest != record.provenance_artifact_digest:
                    return False
        return True
    except (FileNotFoundError, RuntimeError, ValueError, KeyError, json.JSONDecodeError):
        return False


def _baseline_patch(path: str, source: str) -> str:
    lines = source.splitlines()
    context = lines[: min(2, len(lines))]
    count = len(context)
    if count == 0:
        raise RuntimeError("real-code baseline entrypoint cannot be empty")
    body = "".join(f" {line}\n" for line in context)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,{count} +1,{count + 1} @@\n"
        "+# DiscoveryOS frozen baseline marker; no algorithm change.\n"
        + body
    )


def _patch_paths(patch: str) -> tuple[str, ...]:
    paths = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            paths.append(line.removeprefix("+++ b/"))
    return tuple(sorted(set(paths)))


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout
