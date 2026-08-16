from __future__ import annotations

import unittest

from discoveryos.benchmarks.local_patch_reliability import evaluate_fresh_reliability_gate


class LocalPatchReliabilityTests(unittest.TestCase):
    def test_fresh_reliability_gate_is_frozen_before_readmission(self) -> None:
        passed = evaluate_fresh_reliability_gate(
            one_shot_invalid_rate=0.40,
            iterative_invalid_rate=0.40,
            final_blind_receipts=0,
            replay_complete=True,
        )
        self.assertTrue(passed["passed"])

        failed = evaluate_fresh_reliability_gate(
            one_shot_invalid_rate=0.20,
            iterative_invalid_rate=0.31,
            final_blind_receipts=0,
            replay_complete=True,
        )
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["checks"]["iterative_invalid_rate_gap"])


if __name__ == "__main__":
    unittest.main()
