from __future__ import annotations

import unittest
from copy import deepcopy

from discoveryos.benchmarks.p2_factorial_protocol import (
    ARM_IDS,
    GENERATION_CALL_CEILING,
    INTERACTION_MINIMUM_EFFECT_STEPS,
    REPLICATE_SEEDS,
    TASK_IDS,
    FrozenProviderBinding,
    build_p2_factorial_manifest,
    preflight_p2_factorial_tasks,
    verify_p2_factorial_manifest,
)


class P2FactorialProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = preflight_p2_factorial_tasks()
        cls.provider = FrozenProviderBinding(
            executable_path="C:/verified/codex.exe",
            executable_sha256="a" * 64,
            provider_version="codex-cli test",
            provider_name="codex_exec",
            model="gpt-5.6-sol",
            reasoning_effort="medium",
            timeout_seconds=300.0,
            local_settings_digest="b" * 64,
            structural_settings_digest="c" * 64,
        )

    def _manifest(self):
        return build_p2_factorial_manifest(
            repository_commit="d" * 40,
            tracked_source_tree_digest="e" * 64,
            provider=self.provider,
            tasks=self.tasks,
        )

    def test_seal_freezes_paired_estimands_and_matched_execution_surface(self) -> None:
        manifest = self._manifest()
        self.assertEqual("SEALED_PRE_MODEL", manifest["status"])
        self.assertEqual(0, manifest["model_calls_before_seal"])
        self.assertEqual(ARM_IDS, manifest["arms"])
        self.assertEqual(TASK_IDS, tuple(item["task_id"] for item in manifest["tasks"]))
        self.assertEqual(REPLICATE_SEEDS, manifest["replicates"]["seeds"])
        self.assertEqual(
            "Y11 - Y10 - Y01 + Y00",
            manifest["estimands"]["ada_evox_interaction"],
        )
        self.assertEqual(
            INTERACTION_MINIMUM_EFFECT_STEPS,
            manifest["estimands"]["minimum_effect_steps"]["ada_evox_interaction"],
        )
        envelope = manifest["matched_resource_envelope_per_task_replicate_arm"]
        self.assertEqual(GENERATION_CALL_CEILING, envelope["generation_call_ceiling"])
        self.assertEqual(0, envelope["repair_or_resample_calls"])
        self.assertFalse(envelope["unused_budget_transfer"])
        self.assertEqual(
            len(TASK_IDS) * len(REPLICATE_SEEDS),
            manifest["failure_and_stop_rules"]["required_evaluable_blocks"],
        )
        verify_p2_factorial_manifest(manifest, manifest["protocol_manifest_digest"])

    def test_tampering_and_task_replacement_fail_closed(self) -> None:
        manifest = self._manifest()
        tampered = deepcopy(manifest)
        tampered["estimands"]["ada_evox_interaction"] = "Y11 - Y00"
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            verify_p2_factorial_manifest(tampered, manifest["protocol_manifest_digest"])
        with self.assertRaisesRegex(ValueError, "task set or order"):
            build_p2_factorial_manifest(
                repository_commit="d" * 40,
                tracked_source_tree_digest="e" * 64,
                provider=self.provider,
                tasks=tuple(reversed(self.tasks)),
            )

    def test_preflight_uses_only_balanced_consumed_development_tasks(self) -> None:
        self.assertEqual(6, len(self.tasks))
        self.assertEqual(
            {"combinatorial_subset_optimization": 2, "graph_conflict_optimization": 2, "parallel_load_optimization": 2},
            {
                family: sum(record["family"] == family for record in self.tasks)
                for family in {record["family"] for record in self.tasks}
            },
        )
        self.assertTrue(
            all(record["asset_level"] == "L2_CONSUMED_DEVELOPMENT_TASK" for record in self.tasks)
        )
        self.assertTrue(all(record["preflight_model_calls"] == 0 for record in self.tasks))


if __name__ == "__main__":
    unittest.main()
