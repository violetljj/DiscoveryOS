from __future__ import annotations

import asyncio
from dataclasses import dataclass

from discoveryos.contracts.models import (
    CandidateSpec,
    DataRole,
    EvidenceRecord,
    ExperimentSpec,
    Fidelity,
    ResourceUsage,
    RunMode,
)
from discoveryos.operators.asha import (
    ASHAOperator,
    MechanicalRetryRecord,
    PromotionRecord,
    RETRYABLE_FAILURES,
    RungDefinition,
)
from discoveryos.runtime.scheduler import ExperimentExecutor
from discoveryos.util import jsonable


@dataclass(frozen=True, slots=True)
class ASHARunResult:
    run_id: str
    evidence: tuple[EvidenceRecord, ...]
    final_rung_evidence: tuple[EvidenceRecord, ...]
    promotions: tuple[PromotionRecord, ...]
    retries: tuple[MechanicalRetryRecord, ...]
    total_usage: ResourceUsage


class ASHARunner:
    def __init__(self, executor: ExperimentExecutor, operator: ASHAOperator, *, max_mechanical_retries: int = 1) -> None:
        if executor.contract.digest != operator.contract.digest:
            raise ValueError("ASHA operator and executor must share the frozen contract")
        if max_mechanical_retries not in {0, 1}:
            raise ValueError("R1.0-A permits at most one mechanical retry")
        self.executor = executor
        self.operator = operator
        self.max_mechanical_retries = max_mechanical_retries

    async def run(self, candidates: list[CandidateSpec], *, seed: int) -> ASHARunResult:
        if len(candidates) != self.operator.initial_trials:
            raise ValueError("candidate count must equal ASHA initial_trials")
        for candidate in candidates:
            self.executor.ledger.add_candidate(candidate)
        candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        pending: dict[asyncio.Task[EvidenceRecord], tuple[CandidateSpec, ExperimentSpec]] = {}
        experiments: dict[str, ExperimentSpec] = {}
        evidence_records: list[EvidenceRecord] = []
        promotion_records: list[PromotionRecord] = []
        retry_records: list[MechanicalRetryRecord] = []

        def schedule(
            candidate: CandidateSpec,
            rung: RungDefinition,
            *,
            attempt_index: int,
            trial_id: str | None = None,
            reason: str | None = None,
        ) -> ExperimentSpec:
            split_role, split_id = _split_binding(self.executor.contract, rung.fidelity)
            experiment = ExperimentSpec.create(
                candidate_id=candidate.candidate_id,
                evaluator_id=self.executor.contract.evaluator_id_for(rung.fidelity),
                fidelity=rung.fidelity,
                split_id=split_id,
                split_role=split_role,
                seed=seed,
                resources=rung.resources,
                contract_digest=self.executor.contract.digest,
                mode=RunMode.BENCHMARK,
                trial_id=trial_id,
                replicate_id=f"{self.operator.run_id}-seed-{seed}",
                rung_id=rung.rung_id,
                attempt_id=f"attempt-{attempt_index}",
                promotion_reason=reason,
            )
            experiments[experiment.experiment_id] = experiment
            task = asyncio.create_task(self.executor.execute(candidate, experiment))
            pending[task] = (candidate, experiment)
            return experiment

        first_rung = self.operator.rungs[0]
        for candidate in candidates:
            schedule(candidate, first_rung, attempt_index=0)

        while pending:
            done, _ = await asyncio.wait(tuple(pending), return_when=asyncio.FIRST_COMPLETED)
            completed: list[tuple[EvidenceRecord, CandidateSpec, ExperimentSpec]] = []
            for task in done:
                candidate, experiment = pending.pop(task)
                completed.append((task.result(), candidate, experiment))
            completed.sort(key=lambda item: (item[0].created_at, item[0].candidate_id))
            for evidence, candidate, experiment in completed:
                evidence_records.append(evidence)
                attempt_index = int(experiment.attempt_id.removeprefix("attempt-"))
                if evidence.failure_kind in RETRYABLE_FAILURES and attempt_index < self.max_mechanical_retries:
                    retry_attempt = attempt_index + 1
                    retry_experiment = schedule(
                        candidate,
                        self.operator.rung_for(experiment.rung_id),
                        attempt_index=retry_attempt,
                        trial_id=experiment.trial_id,
                        reason=f"mechanical retry after {evidence.receipt_id}",
                    )
                    retry_record = MechanicalRetryRecord.create(
                        run_id=self.operator.run_id,
                        failed_experiment=experiment,
                        failed_evidence=evidence,
                        retry_attempt_id=retry_experiment.attempt_id,
                        retry_experiment_id=retry_experiment.experiment_id,
                    )
                    self._persist_retry(retry_record)
                    retry_records.append(retry_record)
                    continue
                promotions = self.operator.observe(evidence, experiment)
                for promotion in promotions:
                    self._persist_promotion(promotion)
                    promotion_records.append(promotion)
                    promoted_candidate = candidates_by_id[promotion.candidate_id]
                    schedule(
                        promoted_candidate,
                        self.operator.next_rung(promotion.source_rung_id),
                        attempt_index=0,
                        trial_id=promotion.trial_id,
                        reason=promotion.record_id,
                    )

        final_rung_id = self.operator.rungs[-1].rung_id
        final_evidence = tuple(
            evidence
            for evidence in evidence_records
            if experiments[evidence.experiment_id].rung_id == final_rung_id and evidence.failure_kind is None
        )
        return ASHARunResult(
            run_id=self.operator.run_id,
            evidence=tuple(evidence_records),
            final_rung_evidence=final_evidence,
            promotions=tuple(promotion_records),
            retries=tuple(retry_records),
            total_usage=_sum_usage(evidence_records),
        )

    def _persist_promotion(self, record: PromotionRecord) -> None:
        self.executor.artifacts.write_record(
            f"asha/{self.operator.run_id}/promotions/{record.record_id}.json",
            record,
        )
        self.executor.ledger.record_event("ASHA_PROMOTION", jsonable(record))

    def _persist_retry(self, record: MechanicalRetryRecord) -> None:
        self.executor.artifacts.write_record(
            f"asha/{self.operator.run_id}/retries/{record.record_id}.json",
            record,
        )
        self.executor.ledger.record_event("MECHANICAL_RETRY", jsonable(record))


def _split_binding(contract, fidelity: Fidelity) -> tuple[DataRole | None, str | None]:
    role: DataRole | None = None
    if fidelity in {Fidelity.G1, Fidelity.G2, Fidelity.G3, Fidelity.G4}:
        role = DataRole.DEVELOPMENT
    elif fidelity is Fidelity.G5:
        role = DataRole.CALIBRATION
    elif fidelity is Fidelity.G6:
        role = DataRole.SHADOW
    elif fidelity is Fidelity.G7:
        role = DataRole.FINAL_BLIND
    if role is None:
        return None, None
    split = next((split for split in contract.data_splits if split.role is role), None)
    if split is None:
        raise ValueError(f"contract has no split for {role.value}")
    return role, split.split_id


def _sum_usage(evidence: list[EvidenceRecord]) -> ResourceUsage:
    usages = [item.resource_usage for item in evidence]
    exit_codes = [usage.exit_code for usage in usages if usage.exit_code is not None]
    return ResourceUsage(
        llm_input_tokens=sum(usage.llm_input_tokens for usage in usages),
        llm_output_tokens=sum(usage.llm_output_tokens for usage in usages),
        llm_cache_tokens=sum(usage.llm_cache_tokens for usage in usages),
        cpu_seconds=sum(usage.cpu_seconds for usage in usages),
        gpu_seconds=sum(usage.gpu_seconds for usage in usages),
        device_seconds=sum(usage.device_seconds for usage in usages),
        wall_seconds=sum(usage.wall_seconds for usage in usages),
        peak_rss_bytes=max((usage.peak_rss_bytes for usage in usages), default=0),
        exit_code=max(exit_codes, default=0),
    )
