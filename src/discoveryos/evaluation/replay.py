from __future__ import annotations

from dataclasses import dataclass

from discoveryos.contracts.models import EvidenceRecord, FailureKind, ProblemContract
from discoveryos.evaluation.base import EvaluatorRegistry
from discoveryos.evaluation.gates import GateEngine
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_bytes, digest_json


@dataclass(frozen=True, slots=True)
class ReplayResult:
    receipt_id: str
    bindings_valid: bool
    evaluator_reproduced: bool
    issues: tuple[str, ...]


class ReplayEngine:
    def __init__(
        self,
        *,
        contract: ProblemContract,
        ledger: EvidenceLedger,
        artifacts: ArtifactStore,
        vault: SplitVault,
        registry: EvaluatorRegistry,
    ) -> None:
        self.contract = contract
        self.ledger = ledger
        self.artifacts = artifacts
        self.vault = vault
        self.registry = registry

    def replay(self, evidence: EvidenceRecord) -> ReplayResult:
        issues: list[str] = []
        experiment = self.ledger.get_experiment(evidence.experiment_id)
        candidate = self.ledger.get_candidate(evidence.candidate_id)
        if experiment.candidate_id != candidate.candidate_id:
            issues.append("CANDIDATE_EXPERIMENT_MISMATCH")
        if experiment.contract_digest != self.contract.digest or evidence.contract_digest != self.contract.digest:
            issues.append("CONTRACT_BINDING_MISMATCH")
        expected_evaluator = self.registry.digest(experiment.evaluator_id)
        if experiment.evaluator_id != evidence.evaluator_id or expected_evaluator != evidence.evaluator_digest:
            issues.append("EVALUATOR_BINDING_MISMATCH")
        try:
            self.artifacts.get_bytes(candidate.artifact_digest)
        except (FileNotFoundError, RuntimeError):
            issues.append("CANDIDATE_ARTIFACT_INTEGRITY_FAILURE")
        for artifact_digest in evidence.artifacts:
            try:
                self.artifacts.get_bytes(artifact_digest)
            except (FileNotFoundError, RuntimeError):
                issues.append(f"EVIDENCE_ARTIFACT_INTEGRITY_FAILURE:{artifact_digest}")
        data: bytes | None = None
        if experiment.split_id:
            capability = self.vault.issue(
                self.contract,
                split_id=experiment.split_id,
                candidate_id=candidate.candidate_id,
                mode=experiment.mode,
                fidelity=experiment.fidelity,
            )
            data = self.vault.read(self.contract, capability)
            if digest_bytes(data) != evidence.data_digest:
                issues.append("DATA_BINDING_MISMATCH")
        gate = GateEngine().evaluate(self.contract, evidence)
        if gate.decision.value == "INVALID":
            issues.extend(gate.violations)
        if issues:
            return ReplayResult(evidence.receipt_id, False, False, tuple(dict.fromkeys(issues)))
        if evidence.failure_kind is FailureKind.BUDGET_EXHAUSTED:
            reservation_id = f"reservation_{experiment.experiment_id}"
            reconciliation = self.ledger.resource_reconciliation(reservation_id)
            rejection = self.ledger.resource_rejection(reservation_id)
            verified = bool((reconciliation and reconciliation.budget_exhausted) or rejection)
            return ReplayResult(
                evidence.receipt_id,
                True,
                verified,
                () if verified else ("BUDGET_RECEIPT_MISSING",),
            )
        output = self.registry.get(experiment.evaluator_id).evaluate(candidate, experiment, data)
        if evidence.evaluation_output_digest:
            reproduced = output.replay_digest == evidence.evaluation_output_digest
        else:
            expected = {
                "metrics": evidence.metrics,
                "validity": evidence.validity,
                "failure_signature": evidence.failure_signature,
                "artifacts": evidence.artifacts,
            }
            actual = {
                "metrics": output.metrics,
                "validity": output.validity,
                "failure_signature": output.failure_signature,
                "artifacts": output.artifacts,
            }
            reproduced = digest_json(expected) == digest_json(actual)
        return ReplayResult(evidence.receipt_id, True, reproduced, () if reproduced else ("EVALUATOR_OUTPUT_MISMATCH",))

    def replay_all(self) -> list[ReplayResult]:
        return [self.replay(evidence) for evidence in self.ledger.evidence_records()]
