from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_replication_admission import _analyze_replication


class CmiReplicationAdmissionTests(unittest.TestCase):
    def test_consistent_replication_passes_and_one_family_failure_rejects(self) -> None:
        thresholds = {
            "control_escape_states_maximum": 0,
            "treatment_escape_states_minimum": 7,
            "positive_utility_states_beyond_resolution_minimum": 7,
            "negative_utility_states_beyond_resolution_maximum": 0,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
        }
        states = [
            self._state(index, "capacitated_cost_assignment" if index < 4 else "budgeted_weighted_coverage", 0.10)
            for index in range(8)
        ]
        _, gate = _analyze_replication(states, thresholds)
        self.assertTrue(gate["passed"])
        for state in states[4:]:
            state["arms"]["treatment"]["score"] = state["arms"]["control"]["score"]
            state["arms"]["treatment"]["anytime_auc"] = state["arms"]["control"]["anytime_auc"]
        _, failed = _analyze_replication(states, thresholds)
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["checks"]["both_category_median_utility_delta_exceeds_resolution"])

    def test_runtime_guardrail_is_hard_gate(self) -> None:
        thresholds = {
            "control_escape_states_maximum": 0,
            "treatment_escape_states_minimum": 7,
            "positive_utility_states_beyond_resolution_minimum": 7,
            "negative_utility_states_beyond_resolution_maximum": 0,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
        }
        states = [self._state(index, "capacitated_cost_assignment" if index < 4 else "budgeted_weighted_coverage", 0.10) for index in range(8)]
        states[0]["arms"]["treatment"]["evaluator_seconds"] = 4.0
        _, gate = _analyze_replication(states, thresholds)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["checks"]["maximum_state_evaluator_runtime_ratio"])

    @staticmethod
    def _state(index: int, category: str, effect: float) -> dict:
        control_score = 0.4
        return {
            "state_id": f"state-{index}",
            "task_category": category,
            "score_resolution": 0.005,
            "technically_evaluable": True,
            "manipulation_passed": True,
            "arms": {
                "control": {"valid": True, "score": control_score, "escaped": False, "anytime_auc": control_score, "replaced_incumbent": False, "breakthrough": False, "evaluator_seconds": 1.0},
                "treatment": {"valid": True, "score": control_score + effect, "escaped": True, "anytime_auc": control_score + effect / 2, "replaced_incumbent": True, "breakthrough": False, "evaluator_seconds": 1.5},
            },
        }


if __name__ == "__main__":
    unittest.main()
