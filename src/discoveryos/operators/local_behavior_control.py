from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Any

from discoveryos.util import digest_bytes


@dataclass(frozen=True)
class LocalBehaviorControlResult:
    source: str
    trace: dict[str, Any]


class LocalBehaviorControlOperator:
    """Source-local control that preserves the incumbent functional policy."""

    def propose(self, *, task_category: str, base_source: str) -> LocalBehaviorControlResult:
        try:
            source = _TEMPLATES[task_category]
        except KeyError as error:
            raise ValueError(f"unsupported local-control task category: {task_category}") from error
        normalized = textwrap.dedent(source).strip() + "\n"
        return LocalBehaviorControlResult(
            source=normalized,
            trace={
                "operator": type(self).__name__,
                "task_category": task_category,
                "intervention": "source_local_behavior_preserving_refactor",
                "base_source_sha256": digest_bytes((textwrap.dedent(base_source).strip() + "\n").encode("utf-8")),
                "candidate_source_sha256": digest_bytes(normalized.encode("utf-8")),
                "positive_control_received": False,
                "evaluator_feedback_received": False,
            },
        )


_TEMPLATES = {
    "capacitated_cost_assignment": """
def assign_clients(costs, capacities):
    spaces = list(capacities)
    assignments = []
    for client_costs in costs:
        del client_costs
        selected = next(index for index, available in enumerate(spaces) if available > 0)
        assignments.append(selected)
        spaces[selected] -= 1
    return assignments
""",
    "budgeted_weighted_coverage": """
def choose_sets(sets, weights, limit):
    del weights
    selected = []
    for index in range(min(limit, len(sets))):
        selected.append(index)
    return selected
""",
}
