from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_fresh_causal_validation import _analyze_fresh_replication
from discoveryos.benchmarks.cmi_r7_fresh_tasks import cmi_r7_fresh_tasks


class CmiFreshCausalValidationTests(unittest.TestCase):
    def test_fresh_population_is_fixed_balanced_and_identity_unique(self) -> None:
        tasks = cmi_r7_fresh_tasks()
        self.assertEqual(6, len(tasks))
        self.assertEqual(6, len({task.task.task_id for task in tasks}))
        self.assertEqual(6, len({task.payload_digest for task in tasks}))
        categories = [task.task.category for task in tasks]
        self.assertEqual(3, categories.count("capacitated_cost_assignment"))
        self.assertEqual(3, categories.count("budgeted_weighted_coverage"))

    def test_only_six_of_six_primary_effect_passes(self) -> None:
        thresholds = {
            "valid_states_required": 6,
            "positive_primary_endpoint_states_required": 6,
            "negative_utility_states_maximum": 0,
            "positive_primary_endpoint_states_per_family_required": 3,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
        }
        states = [
            self._state(index, "capacitated_cost_assignment" if index < 3 else "budgeted_weighted_coverage")
            for index in range(6)
        ]
        _, passed = _analyze_fresh_replication(states, thresholds)
        self.assertTrue(passed["passed"])

        states[-1]["arms"]["treatment"]["score"] = states[-1]["arms"]["control"]["score"]
        _, failed = _analyze_fresh_replication(states, thresholds)
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["checks"]["positive_primary_endpoint_states_required"])
        self.assertFalse(failed["checks"]["positive_primary_endpoint_states_per_family_required"])

    def test_validity_and_cost_are_hard_guardrails(self) -> None:
        thresholds = {
            "valid_states_required": 6,
            "positive_primary_endpoint_states_required": 6,
            "negative_utility_states_maximum": 0,
            "positive_primary_endpoint_states_per_family_required": 3,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
        }
        states = [
            self._state(index, "capacitated_cost_assignment" if index < 3 else "budgeted_weighted_coverage")
            for index in range(6)
        ]
        states[0]["technically_evaluable"] = False
        states[1]["arms"]["treatment"]["evaluator_seconds"] = 3.5
        _, gate = _analyze_fresh_replication(states, thresholds)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["checks"]["valid_states_required"])
        self.assertFalse(gate["checks"]["maximum_state_evaluator_runtime_ratio"])

    @staticmethod
    def _state(index: int, category: str) -> dict:
        return {
            "state_id": f"state-{index}",
            "task_category": category,
            "score_resolution": 0.005,
            "technically_evaluable": True,
            "arms": {
                "control": {"valid": True, "score": 0.4, "escaped": False, "anytime_auc": 0.4, "replaced_incumbent": False, "breakthrough": False, "evaluator_seconds": 1.0},
                "treatment": {"valid": True, "score": 0.5, "escaped": True, "anytime_auc": 0.45, "replaced_incumbent": True, "breakthrough": False, "evaluator_seconds": 1.0},
            },
        }


if __name__ == "__main__":
    unittest.main()
