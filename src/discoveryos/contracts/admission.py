from __future__ import annotations

from dataclasses import dataclass

from discoveryos.contracts.models import CandidateSpec, ExperimentSpec, Fidelity, ProblemContract, ResourceBudget, RunMode
from discoveryos.evaluation.base import EvaluatorRegistry
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_json


@dataclass(frozen=True, slots=True)
class AdmissionReport:
    admitted: bool
    issues: tuple[str, ...]
    contract_digest: str
    evaluator_digests: tuple[tuple[str, str], ...]


class ProtocolAdmission:
    def __init__(self, registry: EvaluatorRegistry, vault: SplitVault) -> None:
        self.registry = registry
        self.vault = vault

    def check(self, contract: ProblemContract, baseline: CandidateSpec) -> AdmissionReport:
        issues = list(contract.validate())
        issues.extend(self.vault.verify_contract_splits(contract))
        evaluator_digests: list[tuple[str, str]] = []
        checked: set[tuple[str, str]] = set()
        for fidelity in contract.fidelities:
            try:
                evaluator_id, expected_digest = contract.evaluator_binding_for(fidelity)
            except ValueError:
                continue
            if (evaluator_id, expected_digest) in checked:
                continue
            checked.add((evaluator_id, expected_digest))
            if not self.registry.contains(evaluator_id):
                issues.append(f"EVALUATOR_MISSING:{evaluator_id}")
            else:
                actual_digest = self.registry.digest(evaluator_id)
                evaluator_digests.append((evaluator_id, actual_digest))
                if actual_digest != expected_digest:
                    issues.append(f"EVALUATOR_HASH_MISMATCH:{evaluator_id}")
        if baseline.candidate_id != contract.baseline_candidate_id:
            issues.append("BASELINE_BINDING_MISMATCH")
        if not issues and contract.evaluator_ids:
            experiment = ExperimentSpec.create(
                candidate_id=baseline.candidate_id,
                evaluator_id=contract.evaluator_id_for(Fidelity.G0),
                fidelity=Fidelity.G0,
                split_id=None,
                split_role=None,
                seed=0,
                resources=ResourceBudget(cpu_seconds=1, wall_seconds=1),
                contract_digest=contract.digest,
                mode=RunMode.DISCOVERY,
            )
            evaluator = self.registry.get(experiment.evaluator_id)
            first = evaluator.evaluate(baseline, experiment, None)
            second = evaluator.evaluate(baseline, experiment, None)
            if digest_json(first) != digest_json(second):
                issues.append("BASELINE_G0_NOT_REPRODUCIBLE")
        return AdmissionReport(not issues, tuple(issues), contract.digest, tuple(evaluator_digests))
