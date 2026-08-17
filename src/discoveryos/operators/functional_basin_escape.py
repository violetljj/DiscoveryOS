from __future__ import annotations

from dataclasses import dataclass
import textwrap
from typing import Any

from discoveryos.util import digest_json


_REQUIRED_CONTEXT = {
    "frozen_task_contract_and_public_api",
    "frozen_state_local_functional_probe",
    "incumbent_functional_signature",
    "matched_resource_ceiling",
}


@dataclass(frozen=True)
class FunctionalBasinEscapeResult:
    source: str
    trace: dict[str, Any]


class FunctionalBasinEscapeOperator:
    """Minimal deterministic Operator for the CMI-R3 mechanics question.

    The templates are development-only algorithmic decompositions.  They are
    selected from the frozen task category and never receive the positive
    control or evaluator output.
    """

    def __init__(self, brief: dict[str, Any]) -> None:
        contract = brief.get("intervention_contract", {})
        if brief.get("causal_target") != "functional_output_basin":
            raise ValueError("escape Operator requires the functional-output-basin target")
        if contract.get("required_change") != "change algorithmic decomposition before source generation":
            raise ValueError("escape Operator requires the frozen decomposition intervention")
        if contract.get("source_difference_is_sufficient") is not False:
            raise ValueError("source-only diversity cannot authorize the escape Operator")
        if "greater than 0.10" not in contract.get("admission_fingerprint", ""):
            raise ValueError("escape Operator requires the frozen functional-distance fingerprint")
        if not _REQUIRED_CONTEXT.issubset(set(brief.get("required_context", []))):
            raise ValueError("escape Operator is missing required frozen context")
        self._brief = brief

    @property
    def brief_digest(self) -> str:
        return digest_json(self._brief)

    def propose(self, *, task_category: str, base_source: str) -> FunctionalBasinEscapeResult:
        try:
            decomposition, source = _TEMPLATES[task_category]
        except KeyError as error:
            raise ValueError(f"unsupported escape task category: {task_category}") from error
        normalized_base = _normalized_source(base_source)
        normalized_candidate = _normalized_source(source)
        trace = {
            "operator": type(self).__name__,
            "brief_digest": self.brief_digest,
            "task_category": task_category,
            "selected_decomposition": decomposition,
            "field_paths_read": [
                "causal_target",
                "required_context",
                "intervention_contract.required_change",
                "intervention_contract.admission_fingerprint",
                "intervention_contract.source_difference_is_sufficient",
            ],
            "base_source_digest": digest_json({"source": normalized_base}),
            "candidate_source_digest": digest_json({"source": normalized_candidate}),
            "positive_control_received": False,
            "evaluator_feedback_received": False,
        }
        return FunctionalBasinEscapeResult(source=normalized_candidate, trace=trace)


def _normalized_source(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"


_TEMPLATES = {
    "capacitated_cost_assignment": (
        "cost-aware feasible allocation instead of capacity-order fill",
        """
def assign_clients(costs, capacities):
    remaining = list(capacities)
    result = []
    for row in costs:
        available = (facility for facility, space in enumerate(remaining) if space > 0)
        facility = min(available, key=lambda value: (row[value], value))
        result.append(facility)
        remaining[facility] -= 1
    return result
""",
    ),
    "budgeted_weighted_coverage": (
        "iterative weighted marginal coverage instead of input-prefix selection",
        """
def choose_sets(sets, weights, limit):
    chosen = []
    covered = set()
    while len(chosen) < min(limit, len(sets)):
        available = (index for index in range(len(sets)) if index not in chosen)
        best = max(
            available,
            key=lambda index: (
                sum(weights[element] for element in set(sets[index]) - covered),
                -index,
            ),
        )
        chosen.append(best)
        covered.update(sets[best])
    return chosen
""",
    ),
}
