from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.p2_v4_scientific import (
    RECOVERABLE_INFRA,
    _finalize_cost,
    _futility_unreachable,
    _task_from_gate,
)


class P2V4ScientificFastCloseTests(unittest.TestCase):
    def test_task_adapter_preserves_frozen_resolution_and_family_identity(self) -> None:
        unit = {"block_id": "block", "instance_id": "instance", "family_id": "family"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "materialized" / "block" / "primary"
            task.mkdir(parents=True)
            (task / "algorithm.py").write_text("def solve(problem):\n    return problem\n", encoding="utf-8")
            (task / "public_tests.py").write_text("from algorithm import solve\n", encoding="utf-8")
            (task / "evaluate.py").write_text(
                'print("{\\"metrics\\":{\\"score\\":0,\\"valid\\":1}}")\n', encoding="utf-8"
            )
            (task / "task-contract.json").write_text(
                json.dumps({"score_resolution": 7}), encoding="utf-8"
            )
            adapted = _task_from_gate(root, unit)
        self.assertEqual("instance", adapted.task.task_id)
        self.assertEqual("family", adapted.task.category)
        self.assertEqual(7.0, adapted.score_resolution)

    def test_cost_ledger_keeps_scientific_and_infra_loss_separate(self) -> None:
        result = _finalize_cost(
            {
                "scientific_generation_calls": 10,
                "scientific_tokens": 100,
                "infra_censored_generation_calls": 2,
                "infra_censored_tokens": 30,
            }
        )
        self.assertEqual(12, result["total_paid_generation_calls"])
        self.assertEqual(130, result["total_paid_tokens"])

    def test_futility_is_machine_only_and_requires_all_estimands_unreachable(self) -> None:
        negative = {
            "status": "EVALUABLE",
            "contrasts": {
                "ada_main_effect": -1.0,
                "evox_main_effect": -1.0,
                "ada_evox_interaction": -1.0,
            },
        }
        self.assertFalse(_futility_unreachable((negative,)))
        self.assertTrue(_futility_unreachable(tuple(negative for _ in range(24))))
        positive = {
            "status": "EVALUABLE",
            "contrasts": {
                "ada_main_effect": 1.0,
                "evox_main_effect": 1.0,
                "ada_evox_interaction": 1.0,
            },
        }
        self.assertFalse(_futility_unreachable(tuple(positive for _ in range(18))))

    def test_recovery_whitelist_is_narrow(self) -> None:
        self.assertEqual(
            {
                "INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION",
                "INFRA_FAILURE_POWER_INHIBITION_UNAVAILABLE",
                "INFRA_FAILURE_POWER_INHIBITION_RELEASE_FAILED",
            },
            RECOVERABLE_INFRA,
        )


if __name__ == "__main__":
    unittest.main()
