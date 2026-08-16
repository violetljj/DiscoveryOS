from __future__ import annotations

from dataclasses import dataclass, field

from discoveryos.contracts.models import (
    EvidenceRecord,
    ExperimentSpec,
    FailureKind,
    Fidelity,
    GateDecision,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
)
from discoveryos.evaluation.gates import GateEngine
from discoveryos.util import digest_json, utc_now


RETRYABLE_FAILURES = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.OOM,
        FailureKind.WORKER_CRASH,
        FailureKind.EVALUATOR_EXCEPTION,
    }
)


@dataclass(frozen=True, slots=True)
class RungDefinition:
    rung_id: str
    fidelity: Fidelity
    resources: ResourceBudget

    def __post_init__(self) -> None:
        if not self.rung_id:
            raise ValueError("rung id is required")
        if not any(self.resources.as_dict().values()):
            raise ValueError("a rung must request a non-zero resource budget")


@dataclass(frozen=True, slots=True)
class PromotionRecord:
    record_id: str
    run_id: str
    candidate_id: str
    trial_id: str
    replicate_id: str
    source_rung_id: str
    target_rung_id: str
    source_experiment_id: str
    source_receipt_id: str
    observed_receipt_ids: tuple[str, ...]
    promoted_before: tuple[str, ...]
    metric_name: str
    eta: int
    promotion_capacity: int
    target_resource_fingerprint: str
    reason: str
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        candidate_id: str,
        trial_id: str,
        replicate_id: str,
        source_rung_id: str,
        target_rung_id: str,
        source_experiment_id: str,
        source_receipt_id: str,
        observed_receipt_ids: tuple[str, ...],
        promoted_before: tuple[str, ...],
        metric_name: str,
        eta: int,
        promotion_capacity: int,
        target_resource_fingerprint: str,
    ) -> "PromotionRecord":
        identity = {
            "run_id": run_id,
            "candidate_id": candidate_id,
            "trial_id": trial_id,
            "replicate_id": replicate_id,
            "source_rung_id": source_rung_id,
            "target_rung_id": target_rung_id,
            "source_experiment_id": source_experiment_id,
            "source_receipt_id": source_receipt_id,
            "observed_receipt_ids": observed_receipt_ids,
            "promoted_before": promoted_before,
            "metric_name": metric_name,
            "eta": eta,
            "promotion_capacity": promotion_capacity,
            "target_resource_fingerprint": target_resource_fingerprint,
        }
        return cls(
            record_id=f"promotion_{digest_json(identity)[:24]}",
            reason=f"ASHA top-1/{eta} admission from {source_rung_id} to {target_rung_id}",
            **identity,
        )


@dataclass(frozen=True, slots=True)
class MechanicalRetryRecord:
    record_id: str
    run_id: str
    candidate_id: str
    trial_id: str
    rung_id: str
    failed_experiment_id: str
    failed_receipt_id: str
    failure_kind: FailureKind
    prior_attempt_id: str
    retry_attempt_id: str
    retry_experiment_id: str
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        failed_experiment: ExperimentSpec,
        failed_evidence: EvidenceRecord,
        retry_attempt_id: str,
        retry_experiment_id: str,
    ) -> "MechanicalRetryRecord":
        if failed_evidence.failure_kind not in RETRYABLE_FAILURES:
            raise ValueError("only mechanical/system failures may enter the retry queue")
        identity = {
            "run_id": run_id,
            "candidate_id": failed_experiment.candidate_id,
            "trial_id": failed_experiment.trial_id,
            "rung_id": failed_experiment.rung_id,
            "failed_experiment_id": failed_experiment.experiment_id,
            "failed_receipt_id": failed_evidence.receipt_id,
            "failure_kind": failed_evidence.failure_kind,
            "prior_attempt_id": failed_experiment.attempt_id,
            "retry_attempt_id": retry_attempt_id,
            "retry_experiment_id": retry_experiment_id,
        }
        return cls(record_id=f"retry_{digest_json(identity)[:24]}", **identity)


class ASHAOperator:
    operator_id = "asha_v1"

    def __init__(
        self,
        *,
        run_id: str,
        contract: ProblemContract,
        rungs: tuple[RungDefinition, ...],
        metric_name: str,
        eta: int,
        initial_trials: int,
    ) -> None:
        if eta < 2:
            raise ValueError("ASHA eta must be at least 2")
        if len(rungs) < 2:
            raise ValueError("ASHA requires at least two rungs")
        if initial_trials < eta:
            raise ValueError("initial trials must be at least eta")
        if any(left.fidelity.rank >= right.fidelity.rank for left, right in zip(rungs, rungs[1:])):
            raise ValueError("ASHA rungs must have strictly increasing fidelity")
        definitions = {metric.name: metric for metric in contract.metrics}
        if metric_name not in definitions:
            raise ValueError(f"unknown ASHA metric: {metric_name}")
        self.run_id = run_id
        self.contract = contract
        self.rungs = rungs
        self.metric_name = metric_name
        self.direction = definitions[metric_name].direction
        self.eta = eta
        self.initial_trials = initial_trials
        self.gate = GateEngine()
        self._observed: dict[str, list[tuple[EvidenceRecord, ExperimentSpec]]] = {
            rung.rung_id: [] for rung in rungs
        }
        self._observed_receipts: set[str] = set()
        self._promoted: dict[str, list[str]] = {rung.rung_id: [] for rung in rungs[:-1]}

    def observe(self, evidence: EvidenceRecord, experiment: ExperimentSpec) -> tuple[PromotionRecord, ...]:
        if evidence.experiment_id != experiment.experiment_id:
            raise ValueError("evidence and experiment identity mismatch")
        if evidence.receipt_id in self._observed_receipts:
            return ()
        rung_index = self._rung_index(experiment.rung_id)
        rung = self.rungs[rung_index]
        if experiment.fidelity is not rung.fidelity or evidence.fidelity is not rung.fidelity:
            raise ValueError("experiment fidelity does not match its ASHA rung")
        self._observed[experiment.rung_id].append((evidence, experiment))
        self._observed_receipts.add(evidence.receipt_id)
        if rung_index == len(self.rungs) - 1:
            return ()
        feasible = self._ranked_feasible(experiment.rung_id)
        allowed_by_observations = len(feasible) // self.eta
        capacity = self._promotion_capacity(rung_index)
        available_slots = min(allowed_by_observations, capacity) - len(self._promoted[experiment.rung_id])
        records: list[PromotionRecord] = []
        while available_slots > 0:
            promoted = set(self._promoted[experiment.rung_id])
            selected = next((item for item in feasible if item[0].candidate_id not in promoted), None)
            if selected is None:
                break
            selected_evidence, selected_experiment = selected
            target = self.rungs[rung_index + 1]
            record = PromotionRecord.create(
                run_id=self.run_id,
                candidate_id=selected_evidence.candidate_id,
                trial_id=selected_experiment.trial_id,
                replicate_id=selected_experiment.replicate_id,
                source_rung_id=rung.rung_id,
                target_rung_id=target.rung_id,
                source_experiment_id=selected_experiment.experiment_id,
                source_receipt_id=selected_evidence.receipt_id,
                observed_receipt_ids=tuple(item[0].receipt_id for item in self._observed[rung.rung_id]),
                promoted_before=tuple(self._promoted[rung.rung_id]),
                metric_name=self.metric_name,
                eta=self.eta,
                promotion_capacity=capacity,
                target_resource_fingerprint=digest_json(target.resources),
            )
            self._promoted[rung.rung_id].append(selected_evidence.candidate_id)
            records.append(record)
            available_slots -= 1
        return tuple(records)

    def replay_promotion(
        self,
        record: PromotionRecord,
        *,
        evidence_by_receipt: dict[str, EvidenceRecord],
        experiment_by_id: dict[str, ExperimentSpec],
    ) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []
        reconstructed = PromotionRecord.create(
            run_id=record.run_id,
            candidate_id=record.candidate_id,
            trial_id=record.trial_id,
            replicate_id=record.replicate_id,
            source_rung_id=record.source_rung_id,
            target_rung_id=record.target_rung_id,
            source_experiment_id=record.source_experiment_id,
            source_receipt_id=record.source_receipt_id,
            observed_receipt_ids=record.observed_receipt_ids,
            promoted_before=record.promoted_before,
            metric_name=record.metric_name,
            eta=record.eta,
            promotion_capacity=record.promotion_capacity,
            target_resource_fingerprint=record.target_resource_fingerprint,
        )
        if reconstructed.record_id != record.record_id or reconstructed.reason != record.reason:
            issues.append("PROMOTION_RECORD_ID_MISMATCH")
        try:
            source_index = self._rung_index(record.source_rung_id)
            target = self.rungs[source_index + 1]
        except (ValueError, IndexError):
            return False, ("UNKNOWN_PROMOTION_RUNG",)
        if target.rung_id != record.target_rung_id or digest_json(target.resources) != record.target_resource_fingerprint:
            issues.append("TARGET_RUNG_BINDING_MISMATCH")
        observed: list[tuple[EvidenceRecord, ExperimentSpec]] = []
        for receipt_id in record.observed_receipt_ids:
            evidence = evidence_by_receipt.get(receipt_id)
            if evidence is None:
                issues.append(f"OBSERVED_RECEIPT_MISSING:{receipt_id}")
                continue
            experiment = experiment_by_id.get(evidence.experiment_id)
            if experiment is None:
                issues.append(f"OBSERVED_EXPERIMENT_MISSING:{evidence.experiment_id}")
                continue
            if experiment.rung_id != record.source_rung_id:
                issues.append(f"OBSERVED_RUNG_MISMATCH:{receipt_id}")
            observed.append((evidence, experiment))
        feasible = self._rank_items(observed)
        allowed = min(len(feasible) // record.eta, record.promotion_capacity)
        if len(record.promoted_before) >= allowed:
            issues.append("PROMOTION_SLOT_NOT_AVAILABLE")
        selected = next((item for item in feasible if item[0].candidate_id not in set(record.promoted_before)), None)
        if selected is None or selected[0].candidate_id != record.candidate_id:
            issues.append("PROMOTION_SELECTION_MISMATCH")
        elif selected[0].receipt_id != record.source_receipt_id or selected[1].experiment_id != record.source_experiment_id:
            issues.append("PROMOTION_SOURCE_BINDING_MISMATCH")
        elif selected[1].trial_id != record.trial_id or selected[1].replicate_id != record.replicate_id:
            issues.append("PROMOTION_TRIAL_BINDING_MISMATCH")
        if record.metric_name != self.metric_name or record.eta != self.eta:
            issues.append("PROMOTION_POLICY_MISMATCH")
        return not issues, tuple(issues)

    @staticmethod
    def replay_retry(
        record: MechanicalRetryRecord,
        *,
        evidence_by_receipt: dict[str, EvidenceRecord],
        experiment_by_id: dict[str, ExperimentSpec],
    ) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []
        failed_evidence = evidence_by_receipt.get(record.failed_receipt_id)
        failed_experiment = experiment_by_id.get(record.failed_experiment_id)
        retry_experiment = experiment_by_id.get(record.retry_experiment_id)
        if failed_evidence is None or failed_experiment is None:
            issues.append("FAILED_ATTEMPT_BINDING_MISSING")
        elif failed_evidence.failure_kind not in RETRYABLE_FAILURES or failed_evidence.failure_kind is not record.failure_kind:
            issues.append("NON_RETRYABLE_FAILURE")
        elif (
            failed_evidence.experiment_id != failed_experiment.experiment_id
            or failed_evidence.candidate_id != record.candidate_id
            or failed_experiment.trial_id != record.trial_id
            or failed_experiment.rung_id != record.rung_id
            or failed_experiment.attempt_id != record.prior_attempt_id
        ):
            issues.append("FAILED_ATTEMPT_IDENTITY_MISMATCH")
        if retry_experiment is None:
            issues.append("RETRY_EXPERIMENT_MISSING")
        elif failed_experiment is not None:
            if (
                retry_experiment.candidate_id != failed_experiment.candidate_id
                or retry_experiment.trial_id != failed_experiment.trial_id
                or retry_experiment.rung_id != failed_experiment.rung_id
                or retry_experiment.resource_fingerprint != failed_experiment.resource_fingerprint
                or retry_experiment.attempt_id != record.retry_attempt_id
            ):
                issues.append("RETRY_IDENTITY_MISMATCH")
        if failed_evidence is not None and failed_experiment is not None and retry_experiment is not None:
            reconstructed = MechanicalRetryRecord.create(
                run_id=record.run_id,
                failed_experiment=failed_experiment,
                failed_evidence=failed_evidence,
                retry_attempt_id=record.retry_attempt_id,
                retry_experiment_id=retry_experiment.experiment_id,
            )
            if reconstructed.record_id != record.record_id:
                issues.append("RETRY_RECORD_ID_MISMATCH")
        return not issues, tuple(issues)

    def rung_for(self, rung_id: str) -> RungDefinition:
        return self.rungs[self._rung_index(rung_id)]

    def next_rung(self, rung_id: str) -> RungDefinition:
        return self.rungs[self._rung_index(rung_id) + 1]

    def _ranked_feasible(self, rung_id: str) -> list[tuple[EvidenceRecord, ExperimentSpec]]:
        return self._rank_items(self._observed[rung_id])

    def _rank_items(
        self,
        items: list[tuple[EvidenceRecord, ExperimentSpec]],
    ) -> list[tuple[EvidenceRecord, ExperimentSpec]]:
        feasible = [
            item
            for item in items
            if self.gate.evaluate(self.contract, item[0]).decision is GateDecision.FEASIBLE
            and self.metric_name in item[0].metric_dict()
        ]

        def key(item: tuple[EvidenceRecord, ExperimentSpec]) -> tuple[float, str]:
            value = item[0].metric_dict()[self.metric_name]
            primary = value if self.direction is MetricDirection.MINIMIZE else -value
            return primary, item[0].candidate_id

        return sorted(feasible, key=key)

    def _promotion_capacity(self, source_rung_index: int) -> int:
        return self.initial_trials // (self.eta ** (source_rung_index + 1))

    def _rung_index(self, rung_id: str) -> int:
        for index, rung in enumerate(self.rungs):
            if rung.rung_id == rung_id:
                return index
        raise ValueError(f"unknown ASHA rung: {rung_id}")
