from __future__ import annotations

import copy
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
        self.assertEqual(47, report["family_count"])
        self.assertEqual({"R0": 8, "R1": 8, "R2": 10, "R3": 6, "R4": 5, "R5": 10}, report["tier_counts"])
        self.assertEqual(2, report["development_ready_families"])
        self.assertEqual(45, report["catalogued_families"])
        self.assertEqual(0, report["fresh_instances_consumed"])

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
