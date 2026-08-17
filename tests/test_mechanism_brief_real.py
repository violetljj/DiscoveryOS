from __future__ import annotations

import ast
import unittest

from discoveryos.benchmarks.mechanism_brief_real import (
    CALIBRATION_INTERVENTION_REPLICATES,
    CONDITION_A,
    CONDITION_B,
    MECHANISM_BRIEFS,
    NULL_REPLICATES,
    STAGED_GENERATION_SCHEMA,
    STAGES,
    VALIDATION_INTERVENTION_REPLICATES,
    _loop_depth,
    _schedule,
    _source_signature,
    _text_signature,
    _verdict,
)


class MechanismBriefRealProtocolTests(unittest.TestCase):
    def test_briefs_are_mutually_exclusive_and_schema_is_staged(self) -> None:
        self.assertIn("Do not perform", MECHANISM_BRIEFS[CONDITION_A])
        self.assertIn("post-construction improvement loop is required", MECHANISM_BRIEFS[CONDITION_B])
        self.assertEqual(
            {"proposal", "implementation_source", "repair_source", "final_source"},
            set(STAGED_GENERATION_SCHEMA["required"]),
        )

    def test_schedule_freezes_66_independent_model_calls(self) -> None:
        rows = [
            {"state_id": "cal-a", "role": "CALIBRATION"},
            {"state_id": "cal-b", "role": "CALIBRATION"},
            {"state_id": "val-a", "role": "VALIDATION"},
            {"state_id": "val-b", "role": "VALIDATION"},
            {"state_id": "val-c", "role": "VALIDATION"},
        ]
        schedule = _schedule(rows)
        self.assertEqual(66, len(schedule) * 2)
        calibration_pairs = 2 * (2 * NULL_REPLICATES + CALIBRATION_INTERVENTION_REPLICATES)
        validation_pairs = 3 * (2 * NULL_REPLICATES + VALIDATION_INTERVENTION_REPLICATES)
        self.assertEqual(calibration_pairs + validation_pairs, len(schedule))
        self.assertEqual(len(schedule) * 2, len({item[f"{side}_draw_id"] for item in schedule for side in ("control", "treatment")}))

    def test_deterministic_features_distinguish_constructive_and_local_shapes(self) -> None:
        proposal_a = _text_signature("constructive greedy marginal priority single pass")
        proposal_b = _text_signature("iterative local neighborhood improving move swap")
        self.assertGreater(proposal_a[0], proposal_a[1])
        self.assertGreater(proposal_b[1], proposal_b[0])
        greedy = _source_signature("def solve(x):\n    for item in x:\n        pass\n    return []\n")
        local = _source_signature("def solve(x):\n    while True:\n        for a in x:\n            for b in x:\n                pass\n        break\n    return []\n")
        self.assertGreater(local[1], greedy[1])
        self.assertGreater(_loop_depth(ast.parse("while True:\n for x in []:\n  pass")), 1)

    def test_verdict_keeps_transmission_separate_from_value(self) -> None:
        full = {stage: 2 for stage in STAGES}
        self.assertEqual(
            "MECHANISM_BRIEF_SEMANTIC_TRANSMISSION_DETECTED",
            _verdict(full, 2, True, True, True),
        )
        self.assertEqual(
            "MECHANISM_BRIEF_STRUCTURAL_RESPONSE_WITHOUT_BEHAVIOR_TRANSMISSION",
            _verdict(full, 1, True, True, True),
        )
        self.assertEqual(
            "MECHANISM_BRIEF_RESPONSE_NOT_SEMANTICALLY_VALID",
            _verdict(full, 2, True, False, True),
        )


if __name__ == "__main__":
    unittest.main()
