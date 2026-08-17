from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_causal_value import _analyze
from discoveryos.operators.local_behavior_control import LocalBehaviorControlOperator


class CmiCausalValueTests(unittest.TestCase):
    def test_local_control_is_source_changed_but_policy_preserving(self) -> None:
        result = LocalBehaviorControlOperator().propose(
            task_category="budgeted_weighted_coverage",
            base_source="def choose_sets(sets, weights, limit):\n    return list(range(min(limit, len(sets))))\n",
        )
        self.assertIn("for index", result.source)
        self.assertEqual("source_local_behavior_preserving_refactor", result.trace["intervention"])
        self.assertFalse(result.trace["positive_control_received"])

    def test_paired_positive_passes_and_tie_fails(self) -> None:
        positive = [self._state("a", 0.003, 0.10), self._state("b", 0.005, 0.12)]
        analysis, gate = _analyze(positive)
        self.assertTrue(gate["passed"])
        self.assertEqual(1.0, analysis["endpoint_summary"]["functional_escape_rate"]["treatment"])
        tied = [self._state("a", 0.003, 0.0), self._state("b", 0.005, 0.0)]
        _, tied_gate = _analyze(tied)
        self.assertFalse(tied_gate["passed"])

    @staticmethod
    def _state(state_id: str, resolution: float, utility_delta: float) -> dict:
        incumbent = 0.4
        control_score = incumbent
        treatment_score = control_score + utility_delta
        return {
            "state_id": state_id,
            "score_resolution": resolution,
            "arms": {
                "control": {
                    "valid": True,
                    "score": control_score,
                    "functional_distance": 0.0,
                    "escaped": False,
                    "anytime_auc": incumbent,
                    "replaced_incumbent": False,
                    "breakthrough": False,
                    "operator_seconds": 0.01,
                    "evaluator_seconds": 0.02,
                },
                "treatment": {
                    "valid": True,
                    "score": treatment_score,
                    "functional_distance": 0.3,
                    "escaped": True,
                    "anytime_auc": incumbent + max(utility_delta, 0.0) / 2,
                    "replaced_incumbent": utility_delta > resolution,
                    "breakthrough": False,
                    "operator_seconds": 0.01,
                    "evaluator_seconds": 0.02,
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
