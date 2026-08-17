from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_escape_brief import _brief
from discoveryos.benchmarks.cmi_escape_operator import _source_distance, _structural_distance
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator


class CmiEscapeOperatorTests(unittest.TestCase):
    def test_operator_requires_frozen_functional_fingerprint(self) -> None:
        brief = _brief()
        brief["intervention_contract"]["source_difference_is_sufficient"] = True
        with self.assertRaisesRegex(ValueError, "source-only"):
            FunctionalBasinEscapeOperator(brief)

    def test_operator_transmits_brief_without_positive_control(self) -> None:
        operator = FunctionalBasinEscapeOperator(_brief())
        result = operator.propose(
            task_category="capacitated_cost_assignment",
            base_source="def assign_clients(costs, capacities):\n    return []\n",
        )
        self.assertIn("cost-aware", result.trace["selected_decomposition"])
        self.assertFalse(result.trace["positive_control_received"])
        self.assertIn("intervention_contract.admission_fingerprint", result.trace["field_paths_read"])

    def test_distance_metrics_reject_source_only_equivalence(self) -> None:
        left = "def f(x):\n    return x\n"
        right = "def f(value):\n    return value\n"
        self.assertGreater(_source_distance(left, right), 0.0)
        self.assertEqual(0.0, _structural_distance(left, right))


if __name__ == "__main__":
    unittest.main()
