from __future__ import annotations

import difflib
import json
import tempfile
import threading
import unittest
from pathlib import Path

from discoveryos.benchmarks.strategy_integration_si1 import (
    ARM_NAMES,
    run_strategy_integration_si1_pilot,
)
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import ProviderGeneration
from discoveryos.util import digest_json


class _CommentProvider:
    provider_name = "si1_fake_provider"
    model = "si1_fake_model"
    reasoning_effort = "medium"
    provider_version = "si1-fake-1"
    settings_digest = digest_json({"provider": provider_name, "model": model})

    def __init__(self) -> None:
        self._counter = 0
        self._lock = threading.Lock()

    def generate(self, request):
        context = json.loads(request.prompt.split("FROZEN_CONTEXT_JSON\n", 1)[1])
        path, source = context["mutable_files"][0]
        with self._lock:
            self._counter += 1
            counter = self._counter
        updated = source.rstrip("\n") + f"\n# deterministic SI-1 mechanics comment {counter}\n"
        patch = "".join(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return ProviderGeneration(
            raw_response=json.dumps(
                {
                    "hypothesis": "exercise deterministic SI-1 mechanics",
                    "expected_effects": [{"metric": "score", "effect": "unchanged"}],
                    "target_files": [path],
                    "patch": patch,
                    "risks": ["Comment-only change has no algorithmic value."],
                    "estimated_cost": {
                        "tokens": 2,
                        "cpu_seconds": 0,
                        "gpu_seconds": 0,
                        "device_seconds": 0,
                        "wall_seconds": 0.01,
                    },
                }
            ),
            usage=ResourceUsage(llm_input_tokens=1, llm_output_tokens=1, wall_seconds=0.01),
            latency_seconds=0.01,
            provider_version=self.provider_version,
        )


class StrategyIntegrationPilotTests(unittest.TestCase):
    def test_four_arm_consumed_task_runner_and_diagnostics(self) -> None:
        provider = _CommentProvider()
        with tempfile.TemporaryDirectory() as directory:
            report = run_strategy_integration_si1_pilot(
                Path(directory) / "pilot",
                local_provider=provider,
                structural_provider=provider,
                task_ids=("bounded_knapsack_alpha",),
                max_workers=1,
            )
        self.assertEqual("DEVELOPMENT_ONLY_CONSUMED_TASKS", report["claim_ceiling"])
        self.assertFalse(report["fresh_admission_performed"])
        self.assertEqual(set(ARM_NAMES), set(report["arm_summaries"]))
        self.assertTrue(report["controller_budget_reachability_preserved"])
        self.assertEqual(
            "SHINKA_PARENT_NOVELTY_MECHANICS_READY",
            report["mechanics_verdict"],
        )
        self.assertTrue(all(report["mechanics_checks"].values()))
        self.assertEqual(
            [0, 1, 2],
            report["task_results"][0]["arms"]["CORE_PARENT"]["diagnostics"][
                "parent_selection_receipt_steps"
            ],
        )
        self.assertEqual(
            0,
            sum(
                item["selected_but_unaffordable_action_count"]
                for item in report["arm_summaries"].values()
            ),
        )
        self.assertGreater(
            report["arm_summaries"]["CORE_NOVELTY"]["avoided_evaluations"],
            0,
        )
        self.assertGreater(
            report["arm_summaries"]["CORE_NOVELTY"]["resample_cost_tokens"],
            0,
        )
        self.assertEqual(
            report["arm_summaries"]["CORE_NOVELTY"]["resample_cost_tokens"],
            report["arm_summaries"]["CORE_NOVELTY"]["novelty_tokens"],
        )
        self.assertGreater(
            report["arm_summaries"]["CORE_NOVELTY"]["novelty_llm_calls"],
            0,
        )
        self.assertEqual(
            0,
            report["arm_summaries"]["CORE_NOVELTY"]["novelty_check_cost_tokens"],
        )
        self.assertEqual(
            "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
            report["scientific_verdict"],
        )

    def test_repair_mode_changes_parent_distribution_and_stops_unaffordable_resampling(self) -> None:
        provider = _CommentProvider()
        with tempfile.TemporaryDirectory() as directory:
            report = run_strategy_integration_si1_pilot(
                Path(directory) / "repair-pilot",
                local_provider=provider,
                structural_provider=provider,
                task_ids=("bounded_knapsack_alpha",),
                max_workers=1,
                repair_mode=True,
            )
        self.assertEqual(
            "SI1_PARENT_EFFECTIVENESS_REPAIRED",
            report["parent_repair_verdict"],
        )
        self.assertEqual("SI1_NOVELTY_COST_REPAIRED", report["novelty_repair_verdict"])
        self.assertTrue(report["repair_gates"]["parent_selected_non_incumbent"])
        self.assertGreater(report["repair_gates"]["duplicate_evaluations_avoided"], 0)
        self.assertEqual(0, report["repair_gates"]["extra_generation_tokens"])
        self.assertEqual(0, report["repair_gates"]["selected_but_unaffordable_action_count"])
        self.assertEqual(0, report["repair_gates"]["generation_budget_exceeded_count"])


if __name__ == "__main__":
    unittest.main()
