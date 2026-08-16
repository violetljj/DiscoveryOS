from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass

from discoveryos.contracts.models import (
    CandidateSpec,
    DataRole,
    EvaluationOutput,
    EvidenceRecord,
    EvidenceValidity,
    ExperimentSpec,
    FailureKind,
    Fidelity,
    GateDecision,
    ProblemContract,
    ResourceBudget,
    ResourceUsage,
    RunMode,
)
from discoveryos.evaluation.base import EvaluatorRegistry
from discoveryos.evaluation.gates import GateEngine, pareto_front, select_winner
from discoveryos.runtime.artifacts import ArtifactStore, ImmutableWriteError
from discoveryos.runtime.ledger import BudgetExceeded, EvidenceLedger
from discoveryos.runtime.processes import current_rss_bytes
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_bytes, jsonable


class ComputeFabric:
    def __init__(self, *, cpu_workers: int = 4, gpu_workers: int = 1, device_workers: int = 1) -> None:
        self.pools = {
            "cpu": asyncio.Semaphore(max(1, cpu_workers)),
            "gpu": asyncio.Semaphore(max(1, gpu_workers)),
            "device": asyncio.Semaphore(max(1, device_workers)),
        }

    async def run(self, pool: str, function, *args):
        async with self.pools[pool]:
            return await asyncio.to_thread(function, *args)


class ExperimentExecutor:
    def __init__(
        self,
        *,
        contract: ProblemContract,
        ledger: EvidenceLedger,
        artifacts: ArtifactStore,
        vault: SplitVault,
        registry: EvaluatorRegistry,
        fabric: ComputeFabric,
    ) -> None:
        self.contract = contract
        self.ledger = ledger
        self.artifacts = artifacts
        self.vault = vault
        self.registry = registry
        self.fabric = fabric

    async def execute(self, candidate: CandidateSpec, experiment: ExperimentSpec) -> EvidenceRecord:
        self.ledger.add_experiment(experiment)
        existing = self.ledger.get_evidence_for_experiment(experiment.experiment_id)
        if existing:
            self.artifacts.write_record(
                f"receipts/{candidate.candidate_id}/{experiment.fidelity.value}/{experiment.experiment_id}.json",
                existing,
            )
            return existing
        reservation_id = f"reservation_{experiment.experiment_id}"
        try:
            reservation, _ = self.ledger.reserve_resources(
                reservation_id=reservation_id,
                experiment_id=experiment.experiment_id,
                requested=experiment.resources,
                limit=self.contract.budget,
            )
        except BudgetExceeded as error:
            exceeded_dimensions = tuple(
                dimension for dimension in str(error).removeprefix("budget exceeded: ").split(",") if dimension
            )
            self.ledger.record_resource_rejection(
                reservation_id=reservation_id,
                experiment_id=experiment.experiment_id,
                requested=experiment.resources,
                exceeded_dimensions=exceeded_dimensions,
            )
            output = EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.NOT_EVALUABLE,
                failure_signature="BUDGET_EXHAUSTED:" + ",".join(exceeded_dimensions),
                failure_kind=FailureKind.BUDGET_EXHAUSTED,
            )
            planned_data_digest = next(
                (split.sha256 for split in self.contract.data_splits if split.split_id == experiment.split_id),
                None,
            )
            return self._record(candidate, experiment, output, planned_data_digest, ResourceUsage())
        data: bytes | None = None
        data_digest: str | None = None
        if experiment.split_id:
            capability = self.vault.issue(
                self.contract,
                split_id=experiment.split_id,
                candidate_id=candidate.candidate_id,
                mode=experiment.mode,
                fidelity=experiment.fidelity,
            )
            data = self.vault.read(self.contract, capability)
            data_digest = digest_bytes(data)
        evaluator = self.registry.get(experiment.evaluator_id)
        pool = "device" if experiment.fidelity is Fidelity.G5 else "gpu" if experiment.resources.gpu_seconds else "cpu"
        started_wall = time.perf_counter()
        measured_cpu = 0.0
        exit_code: int | None = 0
        try:
            self.artifacts.get_bytes(candidate.artifact_digest)
            evaluation = self.fabric.run(pool, _evaluate_with_cpu, evaluator, candidate, experiment, data)
            if experiment.resources.wall_seconds > 0:
                cleanup_grace = 5.0 if getattr(evaluator, "enforces_hard_timeout", False) else 0.0
                output, measured_cpu = await asyncio.wait_for(
                    evaluation,
                    timeout=experiment.resources.wall_seconds + cleanup_grace,
                )
            else:
                output, measured_cpu = await evaluation
        except TimeoutError:
            exit_code = None
            output = EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.NOT_EVALUABLE,
                failure_signature="TIMEOUT",
                failure_kind=FailureKind.TIMEOUT,
            )
        except (FileNotFoundError, ImmutableWriteError):
            exit_code = 1
            output = EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.INVALID_MECHANICS,
                failure_signature="CANDIDATE_ARTIFACT_INTEGRITY_FAILURE",
                failure_kind=FailureKind.CANDIDATE_ARTIFACT,
            )
        except MemoryError:
            exit_code = 1
            output = EvaluationOutput.from_metrics(
                {}, validity=EvidenceValidity.NOT_EVALUABLE, failure_signature="OOM", failure_kind=FailureKind.OOM
            )
        except Exception as error:  # evaluator failures are evidence, never scientific negatives
            exit_code = 1
            output = EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.NOT_EVALUABLE,
                failure_signature=f"EVALUATOR_EXCEPTION:{type(error).__name__}",
                failure_kind=FailureKind.EVALUATOR_EXCEPTION,
            )
        wall_seconds = time.perf_counter() - started_wall
        reported = output.reported_usage
        usage = ResourceUsage(
            llm_input_tokens=reported.llm_input_tokens,
            llm_output_tokens=reported.llm_output_tokens,
            llm_cache_tokens=reported.llm_cache_tokens,
            cpu_seconds=max(measured_cpu, reported.cpu_seconds),
            gpu_seconds=reported.gpu_seconds or (wall_seconds if experiment.resources.gpu_seconds else 0.0),
            device_seconds=reported.device_seconds or (wall_seconds if experiment.resources.device_seconds else 0.0),
            wall_seconds=wall_seconds,
            peak_rss_bytes=max(current_rss_bytes(), reported.peak_rss_bytes),
            exit_code=reported.exit_code if reported.exit_code is not None else exit_code,
        )
        reconciliation = self.ledger.reconcile_resources(reservation, usage, self.contract.budget)
        if reconciliation.budget_exhausted:
            prior = output.failure_signature
            suffix = f":prior={prior}" if prior else ""
            output = EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.NOT_EVALUABLE,
                failure_signature="BUDGET_EXHAUSTED:" + ",".join(reconciliation.exceeded_dimensions) + suffix,
                failure_kind=FailureKind.BUDGET_EXHAUSTED,
                artifacts=output.artifacts,
                reported_usage=output.reported_usage,
            )
        return self._record(candidate, experiment, output, data_digest, usage)

    def _record(
        self,
        candidate: CandidateSpec,
        experiment: ExperimentSpec,
        output: EvaluationOutput,
        data_digest: str | None,
        usage: ResourceUsage,
    ) -> EvidenceRecord:
        evidence = EvidenceRecord.create(
            experiment=experiment,
            evaluator_digest=self.registry.digest(experiment.evaluator_id),
            data_digest=data_digest,
            output=output,
            resource_usage=usage,
        )
        self.artifacts.write_record(
            f"receipts/{candidate.candidate_id}/{experiment.fidelity.value}/{experiment.experiment_id}.json",
            evidence,
        )
        self.ledger.add_evidence(evidence)
        self.ledger.record_event("EVIDENCE_RECORDED", {"receipt_id": evidence.receipt_id, "fidelity": evidence.fidelity.value})
        return evidence


def _evaluate_with_cpu(evaluator, candidate: CandidateSpec, experiment: ExperimentSpec, data: bytes | None):
    started_cpu = time.thread_time()
    output = evaluator.evaluate(candidate, experiment, data)
    return output, time.thread_time() - started_cpu


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    winner_id: str
    pareto_candidate_ids: tuple[str, ...]
    evaluated_by_fidelity: tuple[tuple[str, int], ...]
    receipts: tuple[str, ...]


class SafeRacing:
    def __init__(self, contract: ProblemContract) -> None:
        self.contract = contract
        self.gate = GateEngine()

    def promote(self, evidence: list[EvidenceRecord], target: int) -> list[str]:
        feasible = [item for item in evidence if self.gate.evaluate(self.contract, item).decision is GateDecision.FEASIBLE]
        if len(feasible) <= target:
            return [item.candidate_id for item in feasible]
        front = pareto_front(self.contract, feasible, self.gate)
        definitions = {metric.name: metric for metric in self.contract.metrics}

        def frozen_key(item: EvidenceRecord) -> tuple[float, ...]:
            metrics = item.metric_dict()
            values: list[float] = []
            for name in self.contract.winner_rule.metric_order:
                if name not in metrics:
                    continue
                value = metrics[name]
                values.append(value if definitions[name].direction.value == "minimize" else -value)
            values.append(float(int(item.candidate_id.removeprefix("cand_")[:12], 16)))
            return tuple(values)

        ordered_front = sorted(front, key=frozen_key)
        selected = ordered_front[:target]
        if len(selected) < target:
            selected_ids = {item.candidate_id for item in selected}
            remainder = sorted((item for item in feasible if item.candidate_id not in selected_ids), key=frozen_key)
            selected.extend(remainder[: target - len(selected)])
        return [item.candidate_id for item in selected]


class DiscoveryRunner:
    def __init__(self, executor: ExperimentExecutor) -> None:
        self.executor = executor
        self.contract = executor.contract
        self.racing = SafeRacing(self.contract)

    async def run(self, candidates: list[CandidateSpec], *, seed: int = 0) -> DiscoveryResult:
        for candidate in candidates:
            self.executor.ledger.add_candidate(candidate)
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        active = list(candidates)
        all_evidence: list[EvidenceRecord] = []
        stage_counts: list[tuple[str, int]] = []
        stages = (Fidelity.G0, Fidelity.G1, Fidelity.G2)
        for fidelity in stages:
            evidence = await self._run_stage(active, fidelity, seed)
            all_evidence.extend(evidence)
            stage_counts.append((fidelity.value, len(evidence)))
            if fidelity is Fidelity.G0:
                promoted_ids = self.racing.promote(evidence, len(evidence))
            elif fidelity is Fidelity.G1:
                promoted_ids = self.racing.promote(evidence, max(2, math.ceil(len(evidence) / 2)))
            else:
                break
            active = [by_id[candidate_id] for candidate_id in promoted_ids]
            if not active:
                raise RuntimeError(f"all candidates failed at {fidelity.value}")
        final_evidence = [item for item in all_evidence if item.fidelity is Fidelity.G2]
        winner = select_winner(self.contract, final_evidence)
        front = pareto_front(self.contract, final_evidence)
        self.executor.ledger.freeze_candidate(winner.candidate_id, self.contract.digest, "frozen winner rule after discovery G2")
        self.executor.artifacts.write_record(
            "decisions/discovery_winner.json",
            {
                "candidate_id": winner.candidate_id,
                "receipt_id": winner.receipt_id,
                "rule": jsonable(self.contract.winner_rule),
                "pareto_candidate_ids": [item.candidate_id for item in front],
                "blind_used": False,
            },
        )
        self.executor.ledger.record_event("CANDIDATE_FROZEN", {"candidate_id": winner.candidate_id, "receipt_id": winner.receipt_id})
        return DiscoveryResult(
            winner_id=winner.candidate_id,
            pareto_candidate_ids=tuple(item.candidate_id for item in front),
            evaluated_by_fidelity=tuple(stage_counts),
            receipts=tuple(item.receipt_id for item in all_evidence),
        )

    async def certify(self, candidate: CandidateSpec, *, seed: int = 0) -> EvidenceRecord:
        if not self.executor.ledger.is_frozen(candidate.candidate_id, self.contract.digest):
            raise RuntimeError("certification requires a candidate frozen before blind access")
        evidence = await self._run_stage([candidate], Fidelity.G7, seed, mode=RunMode.CERTIFICATION)
        result = evidence[0]
        gate = GateEngine().evaluate(self.contract, result)
        self.executor.artifacts.write_record(
            f"decisions/certification_{candidate.candidate_id}.json",
            {"candidate_id": candidate.candidate_id, "receipt_id": result.receipt_id, "gate": jsonable(gate), "winner_changed": False},
        )
        return result

    async def _run_stage(
        self,
        candidates: list[CandidateSpec],
        fidelity: Fidelity,
        seed: int,
        *,
        mode: RunMode = RunMode.DISCOVERY,
    ) -> list[EvidenceRecord]:
        split_role: DataRole | None = None
        split_id: str | None = None
        if fidelity in {Fidelity.G1, Fidelity.G2, Fidelity.G3, Fidelity.G4}:
            split_role = DataRole.DEVELOPMENT
        elif fidelity is Fidelity.G5:
            split_role = DataRole.CALIBRATION
        elif fidelity is Fidelity.G6:
            split_role = DataRole.SHADOW
        elif fidelity is Fidelity.G7:
            split_role = DataRole.FINAL_BLIND
        if split_role:
            split_id = next(split.split_id for split in self.contract.data_splits if split.role is split_role)
        resources = {
            Fidelity.G0: ResourceBudget(cpu_seconds=1, wall_seconds=2),
            Fidelity.G1: ResourceBudget(cpu_seconds=2, wall_seconds=4),
            Fidelity.G2: ResourceBudget(cpu_seconds=5, wall_seconds=10),
            Fidelity.G7: ResourceBudget(cpu_seconds=5, wall_seconds=10),
        }.get(fidelity, ResourceBudget(cpu_seconds=5, wall_seconds=10))
        experiments = [
            ExperimentSpec.create(
                candidate_id=candidate.candidate_id,
                evaluator_id=self.contract.evaluator_id_for(fidelity),
                fidelity=fidelity,
                split_id=split_id,
                split_role=split_role,
                seed=seed,
                resources=resources,
                contract_digest=self.contract.digest,
                mode=mode,
                replicate_id=f"seed-{seed}",
                rung_id=fidelity.value,
                attempt_id="attempt-0",
                promotion_reason="fixed G0-G2 safe racing" if fidelity is not Fidelity.G0 else None,
            )
            for candidate in candidates
        ]
        return list(await asyncio.gather(*(self.executor.execute(candidate, experiment) for candidate, experiment in zip(candidates, experiments))))
