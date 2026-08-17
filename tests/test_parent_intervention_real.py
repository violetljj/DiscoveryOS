from __future__ import annotations

import unittest

from discoveryos.benchmarks.parent_intervention_real import (
    CALIBRATION_STATES,
    DESCENDANT_CHAIN_SCHEMA,
    VALIDATION_STATES,
    _one_sided_sign_p,
    _planned_model_calls,
)


class ParentInterventionRealProtocolTests(unittest.TestCase):
    def test_state_split_is_disjoint_and_validation_spans_tasks(self) -> None:
        calibration = {(task, step, receipt) for task, step, receipt in CALIBRATION_STATES}
        validation = {(task, step, receipt) for task, step, receipt in VALIDATION_STATES}
        self.assertTrue(calibration.isdisjoint(validation))
        self.assertEqual(3, len({task for task, _, _ in VALIDATION_STATES}))

    def test_call_budget_and_chain_shape_are_frozen(self) -> None:
        self.assertEqual(58, _planned_model_calls())
        descendants = DESCENDANT_CHAIN_SCHEMA["properties"]["descendants"]
        self.assertEqual(3, descendants["minItems"])
        self.assertEqual(3, descendants["maxItems"])

    def test_exact_sign_gate_requires_seven_of_nine(self) -> None:
        self.assertLessEqual(_one_sided_sign_p(7, 9), 0.10)
        self.assertGreater(_one_sided_sign_p(6, 9), 0.10)


if __name__ == "__main__":
    unittest.main()
