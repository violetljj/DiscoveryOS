from __future__ import annotations

import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from discoveryos.benchmarks.local_patch_admission import _initialize_arm
from discoveryos.benchmarks.p2_factorial_protocol import (
    ARM_IDS,
    GENERATION_CALL_CEILING,
    INTERACTION_MINIMUM_EFFECT_STEPS,
    REPLICATE_SEEDS,
    TASK_IDS,
    FrozenProviderBinding,
    _aggregate_p2_factorial,
    _evaluate_at,
    _git_tree_digest,
    _p2_harness_run_manifest,
    _p2_search_spec,
    _task_suite,
    build_p2_factorial_manifest,
    preflight_p2_factorial_tasks,
    verify_p2_factorial_manifest,
)
from discoveryos.contracts.models import Fidelity
from discoveryos.harness import (
    HarnessSearchRuntime,
    P2ZeroModelRuntimeSurface,
    SourceSnapshot,
    audit_p2_zero_model_runtime_fairness,
    static_composition_profiles,
)
from discoveryos.operators.action_controller import DeterministicActionController
from discoveryos.benchmarks.search_value_mvp0 import mvp0_controller_config


class _NoCallProvider:
    provider_name = "codex_exec"
    model = "gpt-5.6-sol"
    provider_version = "codex-cli test"

    def __init__(self, settings_digest: str) -> None:
        self.settings_digest = settings_digest

    def propose(self, *_args, **_kwargs):
        raise AssertionError("zero-model execution preflight invoked the provider")


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
        self.assertEqual(12, len(manifest["execution_schedule"]))
        self.assertEqual(
            {(task_id, seed) for task_id in TASK_IDS for seed in REPLICATE_SEEDS},
            {
                (item["task_id"], item["replicate_seed"])
                for item in manifest["execution_schedule"]
            },
        )
        self.assertTrue(
            all(set(item["arm_order"]) == set(ARM_IDS) for item in manifest["execution_schedule"])
        )
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
        self.assertTrue(
            all(len(record["task_repository_tree_digest"]) == 40 for record in self.tasks)
        )
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            item = _task_suite()[0]
            left_repository, _ = item.task.initialize_repository(Path(left))
            right_repository, _ = item.task.initialize_repository(Path(right))
            self.assertEqual(
                _git_tree_digest(left_repository),
                _git_tree_digest(right_repository),
            )

    def test_aggregate_computes_within_block_factorial_estimands(self) -> None:
        manifest = self._manifest()
        blocks = []
        for scheduled in manifest["execution_schedule"]:
            blocks.append(
                {
                    **scheduled,
                    "status": "EVALUABLE",
                    "responses": {
                        "neither": 0.0,
                        "ada_only": 2.0,
                        "evox_only": 3.0,
                        "ada_evox": 7.0,
                    },
                    "contrasts": {
                        "ada_main_effect": 3.0,
                        "evox_main_effect": 4.0,
                        "ada_evox_interaction": 2.0,
                    },
                }
            )
        report = _aggregate_p2_factorial(manifest, tuple(blocks))
        self.assertEqual("P2_FACTORIAL_DEVELOPMENT_COMPLETE", report["status"])
        self.assertEqual(
            "POSITIVE_DEVELOPMENT_SIGNAL",
            report["estimands"]["ada_evox_interaction"]["verdict"],
        )
        self.assertTrue(report["p3_authorized"])

    def test_aggregate_fails_closed_when_one_block_is_not_evaluable(self) -> None:
        manifest = self._manifest()
        blocks = [
            {
                **scheduled,
                "status": "NOT_EVALUABLE" if index == 0 else "EVALUABLE",
                "responses": {},
                "contrasts": None,
            }
            for index, scheduled in enumerate(manifest["execution_schedule"])
        ]
        report = _aggregate_p2_factorial(manifest, tuple(blocks))
        self.assertEqual("NOT_EVALUABLE", report["status"])
        self.assertIsNone(report["estimands"])
        self.assertFalse(report["p3_authorized"])

    def test_real_task_block_builds_four_isolated_runtime_surfaces_without_model_calls(self) -> None:
        item = _task_suite()[0]
        profiles = {name: values[0] for name, values in static_composition_profiles().items()}
        local = _NoCallProvider("1" * 64)
        structural = _NoCallProvider("2" * 64)
        snapshot = SourceSnapshot("d" * 40, "e" * 64, True)
        runtimes = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit = item.task.initialize_repository(root / "task")
            surfaces = []
            for arm_id in ARM_IDS:
                arm = _initialize_arm(
                    root / "arms" / arm_id,
                    item.task,
                    repository,
                    commit,
                    140_000,
                    cpu_ceiling=420,
                    wall_ceiling=2_100,
                    contract_created_at="2026-08-18T00:00:00+00:00",
                )
                asyncio.run(
                    _evaluate_at(
                        arm,
                        arm.baseline,
                        Fidelity.G1,
                        seed=REPLICATE_SEEDS[0],
                        attempt="zero-model-preflight",
                    )
                )
                spec = _p2_search_spec(
                    arm,
                    item,
                    block_id="zero-model-preflight",
                    seed=REPLICATE_SEEDS[0],
                )
                run_manifest = _p2_harness_run_manifest(
                    arm=arm,
                    item=item,
                    profile=profiles[arm_id],
                    spec=spec,
                    source_snapshot=snapshot,
                    local_provider=local,
                    structural_provider=structural,
                )
                runtime = HarnessSearchRuntime.build(
                    profile=profiles[arm_id],
                    spec=spec,
                    contract=arm.contract,
                    ledger=arm.ledger,
                    artifacts=arm.artifacts,
                    experiment_executor=arm.executor,
                    base_controller=DeterministicActionController(mvp0_controller_config()),
                    local_provider=local,
                    structural_provider=structural,
                    manifest=run_manifest,
                    source_snapshot=snapshot,
                )
                runtimes.append(runtime)
                surfaces.append(
                    P2ZeroModelRuntimeSurface.capture(
                        arm_id=arm_id,
                        runtime=runtime,
                        initial_state=runtime.loop.projector.build(),
                    )
                )
            try:
                audit = audit_p2_zero_model_runtime_fairness(tuple(surfaces))
                self.assertEqual("P2_ZERO_MODEL_FACTORIAL_FAIRNESS_GATE_PASS", audit.status)
            finally:
                for runtime in runtimes:
                    runtime.close()


if __name__ == "__main__":
    unittest.main()
