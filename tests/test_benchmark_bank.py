from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.benchmark_bank import (
    ClaimPurpose,
    IntegrationStatus,
    ShardRole,
    assess_shard_access,
    load_benchmark_bank,
    materialize_bank_instance,
    validate_benchmark_bank,
)


REGISTRY = Path(__file__).parents[1] / "benchmarks" / "bank" / "v1" / "registry.json"


class BenchmarkBankTests(unittest.TestCase):
    def test_v1_registry_has_frozen_ladder_and_executable_dev_slice(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        report = validate_benchmark_bank(registry)
        self.assertEqual(49, report["family_count"])
        self.assertEqual({"R0": 8, "R1": 8, "R2": 12, "R3": 6, "R4": 5, "R5": 10}, report["tier_counts"])
        self.assertEqual(26, report["development_ready_families"])
        self.assertEqual(23, report["catalogued_families"])
        self.assertEqual(0, report["fresh_instances_consumed"])

        external = [
            family
            for family in registry["families"]
            if family.get("evidence_role") == "CONTRACT_DERIVED_DEVELOPMENT"
        ]
        self.assertEqual(24, len(external))
        self.assertEqual(
            {"R0": 6, "R1": 6, "R2": 12},
            {
                tier: sum(family["difficulty_tier"] == tier for family in external)
                for tier in ("R0", "R1", "R2")
            },
        )

    def test_catalogued_external_family_cannot_execute_or_open_sealed_shard(self) -> None:
        decision = assess_shard_access(
            role=ShardRole.SEALED,
            purpose=ClaimPurpose.FRESH_ADMISSION,
            integration_status=IntegrationStatus.CATALOGUED,
            claim_upgrade_gate_passed=True,
        )
        self.assertFalse(decision["authorized"])
        self.assertIn("BENCHMARK_FAMILY_NOT_EXECUTION_ADMITTED", decision["failures"])

        development_only = assess_shard_access(
            role=ShardRole.SEALED,
            purpose=ClaimPurpose.FRESH_ADMISSION,
            integration_status=IntegrationStatus.DEVELOPMENT_READY,
            claim_upgrade_gate_passed=True,
        )
        self.assertFalse(development_only["authorized"])
        self.assertIn("BENCHMARK_FAMILY_NOT_SCIENTIFICALLY_ADMITTED", development_only["failures"])

    def test_fresh_shard_is_rejected_for_debugging_and_blind_requires_freeze(self) -> None:
        debugging = assess_shard_access(
            role=ShardRole.SEALED,
            purpose=ClaimPurpose.DEVELOPMENT,
            integration_status=IntegrationStatus.ADMITTED,
            claim_upgrade_gate_passed=True,
        )
        self.assertFalse(debugging["authorized"])
        self.assertIn("NO_FRESH_TASK_FOR_DEBUGGING", debugging["failures"])
        blind = assess_shard_access(
            role=ShardRole.SEALED,
            purpose=ClaimPurpose.BLIND_CONFIRMATION,
            integration_status=IntegrationStatus.ADMITTED,
            claim_upgrade_gate_passed=True,
        )
        self.assertFalse(blind["authorized"])
        self.assertIn("WINNER_NOT_FROZEN", blind["failures"])
        self.assertIn("BLIND_SELECTION_ISOLATION_NOT_ESTABLISHED", blind["failures"])

    def test_internal_consumed_families_materialize_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for family_id, instance_id in (
                ("assignment_consumed_dev", "capacitated_assignment_delta"),
                ("set_cover_consumed_dev", "budgeted_coverage_delta"),
            ):
                output = Path(temp_dir) / family_id
                report = materialize_bank_instance(
                    REGISTRY,
                    family_id=family_id,
                    instance_id=instance_id,
                    output_dir=output,
                )
                self.assertEqual("CONSUMED_DEVELOPMENT_ONLY", report["resolution"]["claim_ceiling"])
                self.assertEqual(0, report["fresh_instances_consumed"])
                public = subprocess.run(
                    [sys.executable, "public_tests.py"], cwd=output, text=True, capture_output=True, check=False
                )
                self.assertEqual(0, public.returncode, public.stderr)
                evaluation = subprocess.run(
                    [sys.executable, "evaluate.py"], cwd=output, text=True, capture_output=True, check=False
                )
                self.assertEqual(0, evaluation.returncode, evaluation.stderr)
                self.assertIn('"metrics"', evaluation.stdout)

    def test_six_algotune_contract_families_materialize_and_execute_every_dev_instance(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        families = [
            family
            for family in registry["families"]
            if family.get("adapter_id") == "discoveryos.algotune_contract_dev.v1"
        ]
        self.assertEqual(6, len(families))
        with tempfile.TemporaryDirectory() as temp_dir:
            for family in families:
                self.assertEqual(2, len(family["instance_ids"]))
                for instance_id in family["instance_ids"]:
                    output = Path(temp_dir) / instance_id
                    report = materialize_bank_instance(
                        REGISTRY,
                        family_id=family["family_id"],
                        instance_id=instance_id,
                        output_dir=output,
                    )
                    resolution = report["resolution"]
                    self.assertEqual(
                        "EXTERNAL_CONTRACT_DERIVED_DEVELOPMENT_ONLY",
                        resolution["claim_ceiling"],
                    )
                    self.assertEqual(
                        "DISCOVERYOS_STDLIB_ALGOTUNE_CONTRACT_DEV_V1",
                        resolution["evaluator_regime"],
                    )
                    contract = json.loads((output / "task-contract.json").read_text(encoding="utf-8"))
                    self.assertFalse(contract["upstream_evaluator_reused"])
                    self.assertEqual("DEV", contract["partition_role"])
                    public = subprocess.run(
                        [sys.executable, "public_tests.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, public.returncode, f"{instance_id}: {public.stderr}")
                    evaluation = subprocess.run(
                        [sys.executable, "evaluate.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, evaluation.returncode, f"{instance_id}: {evaluation.stderr}")
                    payload = json.loads(evaluation.stdout)
                    self.assertEqual(1.0, payload["metrics"]["valid"], instance_id)
                    self.assertGreater(payload["metrics"]["score"], 0.0, instance_id)
                    self.assertGreater(payload["metrics"]["median_runtime_ms"], 0.0, instance_id)

    def test_algotune_dev_binding_is_fail_closed(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        family = next(item for item in registry["families"] if item["family_id"] == "dijkstra")
        family["development_binding"]["upstream_task_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "DEVELOPMENT_DIGEST_INVALID:dijkstra"):
            validate_benchmark_bank(registry)
        registry = load_benchmark_bank(REGISTRY)
        family = next(item for item in registry["families"] if item["family_id"] == "dijkstra")
        family["development_binding"]["upstream_task_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "DEVELOPMENT_DIGEST_BINDING_MISMATCH:dijkstra"):
            validate_benchmark_bank(registry)

    def test_algotune_dev_materialization_replays_and_invalid_candidate_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            report_a = materialize_bank_instance(
                REGISTRY,
                family_id="convolution_1d",
                instance_id="convolution_1d_dev_alpha",
                output_dir=first,
            )
            report_b = materialize_bank_instance(
                REGISTRY,
                family_id="convolution_1d",
                instance_id="convolution_1d_dev_alpha",
                output_dir=second,
            )
            self.assertEqual(
                report_a["resolution"]["instance_digest"],
                report_b["resolution"]["instance_digest"],
            )
            self.assertEqual(
                report_a["resolution"]["evaluator_digest"],
                report_b["resolution"]["evaluator_digest"],
            )
            (second / "algorithm.py").write_text(
                "def solve(problem):\n    return []\n",
                encoding="utf-8",
            )
            evaluation = subprocess.run(
                [sys.executable, "evaluate.py"],
                cwd=second,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, evaluation.returncode, evaluation.stderr)
            payload = json.loads(evaluation.stdout)
            self.assertEqual(0.0, payload["metrics"]["valid"])
            self.assertEqual(0.0, payload["metrics"]["score"])

    def test_p2_v4_expansion_selection_and_all_instances_are_zero_model_executable(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        audit = registry["p2_v4_expansion_audit"]
        self.assertEqual(0, audit["model_calls"])
        self.assertEqual(0, audit["fresh_or_sealed_assets_opened"])
        self.assertEqual(
            ["least_squares", "fft_convolution", "min_weight_assignment", "kd_tree", "kmeans"],
            audit["r1_sha256_rank"],
        )
        families = [
            family
            for family in registry["families"]
            if family.get("adapter_id") == "discoveryos.algotune_p2v4_contract_dev.v1"
        ]
        self.assertEqual(8, len(families))
        with tempfile.TemporaryDirectory() as temp_dir:
            for family in families:
                self.assertEqual(2, len(family["instance_ids"]))
                for instance_id in family["instance_ids"]:
                    output = Path(temp_dir) / instance_id
                    report = materialize_bank_instance(
                        REGISTRY,
                        family_id=family["family_id"],
                        instance_id=instance_id,
                        output_dir=output,
                    )
                    resolution = report["resolution"]
                    self.assertEqual(
                        "EXTERNAL_CONTRACT_DERIVED_DEVELOPMENT_ONLY",
                        resolution["claim_ceiling"],
                    )
                    self.assertEqual(
                        "DISCOVERYOS_STDLIB_ALGOTUNE_P2V4_CONTRACT_DEV_V1",
                        resolution["evaluator_regime"],
                    )
                    contract = json.loads((output / "task-contract.json").read_text(encoding="utf-8"))
                    self.assertFalse(contract["upstream_evaluator_reused"])
                    self.assertEqual("DEV", contract["partition_role"])
                    public = subprocess.run(
                        [sys.executable, "public_tests.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, public.returncode, f"{instance_id}: {public.stderr}")
                    evaluation = subprocess.run(
                        [sys.executable, "evaluate.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, evaluation.returncode, f"{instance_id}: {evaluation.stderr}")
                    payload = json.loads(evaluation.stdout)
                    self.assertEqual(1.0, payload["metrics"]["valid"], instance_id)
                    self.assertGreater(payload["metrics"]["score"], 0.0, instance_id)

    def test_p2_v4_expansion_digest_binding_and_invalid_candidate_fail_closed(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        family = next(item for item in registry["families"] if item["family_id"] == "tsp")
        family["development_binding"]["upstream_task_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "DEVELOPMENT_DIGEST_BINDING_MISMATCH:tsp"):
            validate_benchmark_bank(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            replay = Path(temp_dir) / "replay"
            output = Path(temp_dir) / "invalid"
            first = materialize_bank_instance(
                REGISTRY,
                family_id="vertex_cover",
                instance_id="vertex_cover_dev_alpha",
                output_dir=output,
            )
            second = materialize_bank_instance(
                REGISTRY,
                family_id="vertex_cover",
                instance_id="vertex_cover_dev_alpha",
                output_dir=replay,
            )
            self.assertEqual(
                first["resolution"]["instance_digest"],
                second["resolution"]["instance_digest"],
            )
            self.assertEqual(
                first["resolution"]["evaluator_digest"],
                second["resolution"]["evaluator_digest"],
            )
            (output / "algorithm.py").write_text("def solve(problem):\n    return []\n", encoding="utf-8")
            evaluation = subprocess.run(
                [sys.executable, "evaluate.py"],
                cwd=output,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, evaluation.returncode, evaluation.stderr)
            payload = json.loads(evaluation.stdout)
            self.assertEqual(0.0, payload["metrics"]["valid"])
            self.assertEqual(0.0, payload["metrics"]["score"])

    def test_ten_algotune_r2_families_materialize_and_execute_every_dev_instance(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        families = [
            family
            for family in registry["families"]
            if family.get("adapter_id") == "discoveryos.algotune_r2_contract_dev.v1"
        ]
        self.assertEqual(10, len(families))
        with tempfile.TemporaryDirectory() as temp_dir:
            for family in families:
                self.assertEqual(2, len(family["instance_ids"]))
                for instance_id in family["instance_ids"]:
                    output = Path(temp_dir) / instance_id
                    report = materialize_bank_instance(
                        REGISTRY,
                        family_id=family["family_id"],
                        instance_id=instance_id,
                        output_dir=output,
                    )
                    resolution = report["resolution"]
                    self.assertEqual(
                        "EXTERNAL_R2_CONTRACT_DERIVED_DEVELOPMENT_ONLY",
                        resolution["claim_ceiling"],
                    )
                    self.assertEqual(
                        "DISCOVERYOS_STDLIB_ALGOTUNE_R2_CONTRACT_DEV_V1",
                        resolution["evaluator_regime"],
                    )
                    contract = json.loads((output / "task-contract.json").read_text(encoding="utf-8"))
                    self.assertFalse(contract["upstream_evaluator_reused"])
                    self.assertEqual("DEV", contract["partition_role"])
                    public = subprocess.run(
                        [sys.executable, "public_tests.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, public.returncode, f"{instance_id}: {public.stderr}")
                    evaluation = subprocess.run(
                        [sys.executable, "evaluate.py"],
                        cwd=output,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0, evaluation.returncode, f"{instance_id}: {evaluation.stderr}")
                    payload = json.loads(evaluation.stdout)
                    self.assertEqual(1.0, payload["metrics"]["valid"], instance_id)
                    self.assertGreater(payload["metrics"]["score"], 0.0, instance_id)

    def test_algotune_r2_digest_binding_and_candidate_failure_are_fail_closed(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        family = next(item for item in registry["families"] if item["family_id"] == "max_clique")
        family["development_binding"]["upstream_description_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "DEVELOPMENT_DIGEST_BINDING_MISMATCH:max_clique"):
            validate_benchmark_bank(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            output = Path(temp_dir) / "invalid"
            replay_a = materialize_bank_instance(
                REGISTRY,
                family_id="max_clique",
                instance_id="max_clique_dev_alpha",
                output_dir=first,
            )
            replay_b = materialize_bank_instance(
                REGISTRY,
                family_id="max_clique",
                instance_id="max_clique_dev_alpha",
                output_dir=output,
            )
            self.assertEqual(
                replay_a["resolution"]["instance_digest"],
                replay_b["resolution"]["instance_digest"],
            )
            self.assertEqual(
                replay_a["resolution"]["evaluator_digest"],
                replay_b["resolution"]["evaluator_digest"],
            )
            (output / "algorithm.py").write_text("def solve(problem):\n    return []\n", encoding="utf-8")
            evaluation = subprocess.run(
                [sys.executable, "evaluate.py"],
                cwd=output,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, evaluation.returncode, evaluation.stderr)
            payload = json.loads(evaluation.stdout)
            self.assertEqual(0.0, payload["metrics"]["valid"])
            self.assertEqual(0.0, payload["metrics"]["score"])

    def test_ale_r3_catalog_is_pinned_and_cannot_pretend_to_be_execution_ready(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        source = registry["sources"]["ale_bench"]
        self.assertEqual("0f426173b4e4e73b09b2b3631ae0490f66b75f99", source["dataset_revision"])
        families = [family for family in registry["families"] if family["source_id"] == "ale_bench"]
        self.assertEqual(6, len(families))
        for family in families:
            audit = family["catalog_audit"]
            self.assertEqual(64, len(audit["dataset_lfs_sha256"]))
            self.assertGreater(audit["dataset_size_bytes"], 0)
            self.assertTrue(audit["private_content_cobundled"])
        tampered = copy.deepcopy(registry)
        ahc008 = next(family for family in tampered["families"] if family["family_id"] == "ahc008")
        ahc008["catalog_audit"]["execution_blockers"] = []
        with self.assertRaisesRegex(ValueError, "ALE_CATALOG_BLOCKERS_INCOMPLETE:ahc008"):
            validate_benchmark_bank(tampered)
        pretend = copy.deepcopy(registry)
        ahc008 = next(family for family in pretend["families"] if family["family_id"] == "ahc008")
        ahc008["integration_status"] = "DEVELOPMENT_READY"
        ahc008["adapter_id"] = "discoveryos.algotune_r2_contract_dev.v1"
        ahc008["instance_ids"] = ["pretend"]
        with self.assertRaisesRegex(ValueError, "ALE_EXECUTION_ADMISSION_INCOMPLETE:ahc008"):
            validate_benchmark_bank(pretend)

    def test_skydiscover_r4_catalog_binds_source_dependencies_and_data_boundary(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        families = [family for family in registry["families"] if family["difficulty_tier"] == "R4"]
        self.assertEqual(5, len(families))
        self.assertEqual(
            {"EXTERNAL_DATASET_UNBOUND", "SELF_CONTAINED_GENERATED_PUBLIC_CASES", "SELF_CONTAINED_PUBLIC_WORKLOADS"},
            {family["catalog_audit"]["data_boundary"] for family in families},
        )
        for family in families:
            audit = family["catalog_audit"]
            self.assertEqual(64, len(audit["upstream_tree_sha256"]))
            self.assertTrue(audit["syntax_preflight_passed"])
            self.assertTrue(audit["dependency_profile"])
            self.assertTrue(audit["execution_blockers"])
        tampered = copy.deepcopy(registry)
        next(f for f in tampered["families"] if f["family_id"] == "prism")["catalog_audit"]["data_boundary"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "SKYDISCOVER_SYSTEM_DATA_BOUNDARY_MISSING:prism"):
            validate_benchmark_bank(tampered)

    def test_skydiscover_r5_public_frontier_exposure_is_fail_closed(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        families = [family for family in registry["families"] if family["difficulty_tier"] == "R5"]
        self.assertEqual(10, len(families))
        for family in families:
            exposure = family["catalog_audit"]["public_exposure"]
            self.assertTrue(all(exposure.values()))
            self.assertIn(
                "NEIGHBORING_HIDDEN_DISTRIBUTION_NOT_FROZEN",
                family["catalog_audit"]["execution_blockers"],
            )
        tampered = copy.deepcopy(registry)
        next(f for f in tampered["families"] if f["family_id"] == "circle_packing")["catalog_audit"]["public_exposure"]["target_value"] = False
        with self.assertRaisesRegex(ValueError, "SKYDISCOVER_FRONTIER_EXPOSURE_INCOMPLETE:circle_packing"):
            validate_benchmark_bank(tampered)

    def test_registry_rejects_duplicate_or_pretend_admitted_family(self) -> None:
        registry = load_benchmark_bank(REGISTRY)
        duplicate = copy.deepcopy(registry)
        duplicate["families"][1]["family_id"] = duplicate["families"][0]["family_id"]
        with self.assertRaisesRegex(ValueError, "FAMILY_ID_INVALID_OR_DUPLICATE"):
            validate_benchmark_bank(duplicate)
        pretend = copy.deepcopy(registry)
        pretend["families"][2]["integration_status"] = "ADMITTED"
        with self.assertRaisesRegex(ValueError, "ADMISSION_BINDING_INCOMPLETE"):
            validate_benchmark_bank(pretend)


if __name__ == "__main__":
    unittest.main()
