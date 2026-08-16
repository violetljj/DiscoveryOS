from __future__ import annotations

from discoveryos.contracts.models import (
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    EvidenceRecord,
    EvidenceValidity,
    Fidelity,
    GateDecision,
    GateResult,
    MetricDirection,
    ProblemContract,
)


class GateEngine:
    """Frozen scientific authority: validity and hard constraints never become a scalar score."""

    def evaluate(self, contract: ProblemContract, evidence: EvidenceRecord) -> GateResult:
        if evidence.contract_digest != contract.digest:
            return GateResult(GateDecision.INVALID, ("CONTRACT_BINDING_MISMATCH",), ClaimCeiling.MECHANICS_ONLY)
        try:
            expected_evaluator_id, expected_evaluator_digest = contract.evaluator_binding_for(evidence.fidelity)
        except ValueError:
            return GateResult(GateDecision.INVALID, ("FIDELITY_EVALUATOR_BINDING_MISSING",), ClaimCeiling.MECHANICS_ONLY)
        if evidence.evaluator_id != expected_evaluator_id or evidence.evaluator_digest != expected_evaluator_digest:
            return GateResult(GateDecision.INVALID, ("EVALUATOR_BINDING_MISMATCH",), ClaimCeiling.MECHANICS_ONLY)
        if evidence.fidelity is Fidelity.G0:
            if evidence.split_id is not None or evidence.data_digest is not None:
                return GateResult(GateDecision.INVALID, ("G0_MUST_NOT_BIND_DATA",), ClaimCeiling.MECHANICS_ONLY)
        else:
            split = next((item for item in contract.data_splits if item.split_id == evidence.split_id), None)
            if split is None or split.sha256 != evidence.data_digest or split.role is not evidence.split_role:
                return GateResult(GateDecision.INVALID, ("DATA_BINDING_MISMATCH",), ClaimCeiling.MECHANICS_ONLY)
            expected_roles = {
                Fidelity.G1: DataRole.DEVELOPMENT,
                Fidelity.G2: DataRole.DEVELOPMENT,
                Fidelity.G3: DataRole.DEVELOPMENT,
                Fidelity.G4: DataRole.DEVELOPMENT,
                Fidelity.G5: DataRole.CALIBRATION,
                Fidelity.G6: DataRole.SHADOW,
                Fidelity.G7: DataRole.FINAL_BLIND,
            }
            if expected_roles.get(evidence.fidelity) is not split.role:
                return GateResult(GateDecision.INVALID, ("FIDELITY_SPLIT_ROLE_MISMATCH",), ClaimCeiling.MECHANICS_ONLY)
        if evidence.validity is EvidenceValidity.NOT_EVALUABLE:
            return GateResult(GateDecision.NOT_EVALUABLE, (evidence.failure_signature or "NOT_EVALUABLE",), ClaimCeiling.MECHANICS_ONLY)
        if evidence.validity is not EvidenceValidity.VALID:
            return GateResult(GateDecision.INVALID, (evidence.failure_signature or evidence.validity.value,), ClaimCeiling.MECHANICS_ONLY)
        metrics = evidence.metric_dict()
        violations: list[str] = []
        for constraint in contract.hard_constraints:
            if evidence.fidelity.rank < constraint.applies_from.rank:
                continue
            if constraint.metric not in metrics:
                violations.append(f"MISSING_HARD_METRIC:{constraint.metric}")
                continue
            value = metrics[constraint.metric]
            passed = {
                ConstraintOperator.LE: value <= constraint.threshold,
                ConstraintOperator.GE: value >= constraint.threshold,
                ConstraintOperator.EQ: value == constraint.threshold,
            }[constraint.operator]
            if not passed:
                violations.append(f"{constraint.metric}{constraint.operator.value}{constraint.threshold}:observed={value}")
        if violations:
            return GateResult(GateDecision.REJECT_HARD_CONSTRAINT, tuple(violations), ClaimCeiling.MECHANICS_ONLY)
        ceiling = ClaimCeiling.MECHANICS_ONLY
        if evidence.fidelity.rank >= Fidelity.G2.rank:
            ceiling = ClaimCeiling.DEVELOPMENT_ONLY
        if evidence.fidelity is Fidelity.G6:
            ceiling = ClaimCeiling.SHADOW_SUPPORTED
        if evidence.fidelity is Fidelity.G7:
            ceiling = ClaimCeiling.CERTIFIED_BLIND
        ceiling = _min_ceiling(ceiling, contract.claim_ceiling)
        return GateResult(GateDecision.FEASIBLE, (), ceiling)


def _min_ceiling(left: ClaimCeiling, right: ClaimCeiling) -> ClaimCeiling:
    order = list(ClaimCeiling)
    return order[min(order.index(left), order.index(right))]


def pareto_front(contract: ProblemContract, evidence: list[EvidenceRecord], gate: GateEngine | None = None) -> list[EvidenceRecord]:
    authority = gate or GateEngine()
    feasible = [item for item in evidence if authority.evaluate(contract, item).decision is GateDecision.FEASIBLE]
    objectives = [metric for metric in contract.metrics if metric.objective]

    def dominates(left: EvidenceRecord, right: EvidenceRecord) -> bool:
        left_metrics = left.metric_dict()
        right_metrics = right.metric_dict()
        relevant = [metric for metric in objectives if metric.name in left_metrics and metric.name in right_metrics]
        if not relevant:
            return False
        weakly_better = all(
            left_metrics[metric.name] <= right_metrics[metric.name]
            if metric.direction is MetricDirection.MINIMIZE
            else left_metrics[metric.name] >= right_metrics[metric.name]
            for metric in relevant
        )
        strictly_better = any(
            left_metrics[metric.name] < right_metrics[metric.name]
            if metric.direction is MetricDirection.MINIMIZE
            else left_metrics[metric.name] > right_metrics[metric.name]
            for metric in relevant
        )
        return weakly_better and strictly_better

    return [candidate for candidate in feasible if not any(other is not candidate and dominates(other, candidate) for other in feasible)]


def select_winner(contract: ProblemContract, evidence: list[EvidenceRecord]) -> EvidenceRecord:
    eligible = [
        item
        for item in evidence
        if item.fidelity.rank >= contract.winner_rule.require_fidelity.rank
        and GateEngine().evaluate(contract, item).decision is GateDecision.FEASIBLE
    ]
    if not eligible:
        raise ValueError("no feasible evidence satisfies the frozen winner rule")
    definitions = {metric.name: metric for metric in contract.metrics}

    def key(item: EvidenceRecord) -> tuple[float, ...]:
        metrics = item.metric_dict()
        values: list[float] = []
        for name in contract.winner_rule.metric_order:
            definition = definitions[name]
            value = metrics[name]
            values.append(value if definition.direction is MetricDirection.MINIMIZE else -value)
        values.append(float(int(item.candidate_id.removeprefix("cand_")[:12], 16)))
        return tuple(values)

    return min(eligible, key=key)
