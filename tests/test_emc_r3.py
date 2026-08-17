from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.emc_resource_calibration import (
    run_emc_resource_calibration,
    seal_emc_resource_calibration,
)
from discoveryos.benchmarks.executable_mechanism_contract import IMPLEMENTATION_SCHEMA
from discoveryos.benchmarks.executable_mechanism_contract_r3 import (
    MANIFEST_RECORD,
    SENSITIVITY_RECORD,
    run_emc_r3_calibration,
    run_emc_r3_instrumentation,
    seal_emc_r3_protocol,
)
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import ProviderGeneration
from discoveryos.runtime.artifacts import ArtifactStore


class _Provider:
    provider_name = "fixture"
    model = "fixture-model"
    provider_version = "fixture-1"
    settings_digest = "fixture-settings"
    output_schema = IMPLEMENTATION_SCHEMA

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return ProviderGeneration(
            raw_response='{"implementation_source":"pass"}',
            usage=ResourceUsage(llm_input_tokens=1000, llm_output_tokens=100, wall_seconds=1.0),
            latency_seconds=1.0,
            provider_version=self.provider_version,
            provider_request_id=f"fixture-{self.calls}",
        )


class EmcR3ProtocolTests(unittest.TestCase):
    def _resource_authority(self, root: Path, provider: _Provider) -> tuple[Path, dict]:
        workspace = root / "resource"
        sealed = seal_emc_resource_calibration(workspace, provider=provider)
        result = run_emc_resource_calibration(
            workspace,
            manifest_digest=sealed["manifest_digest"],
            provider=provider,
        )
        return workspace, result

    def test_resource_calibration_derives_ceiling_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            provider = _Provider()
            workspace, result = self._resource_authority(Path(temporary), provider)
            self.assertTrue(result["passed"])
            self.assertEqual(78_000, result["derived_scientific_per_call_token_ceiling"])
            self.assertEqual(4, provider.calls)
            rerun = run_emc_resource_calibration(
                workspace,
                manifest_digest=result["manifest_digest"],
                provider=provider,
            )
            self.assertEqual(result["record_sha256"], rerun["record_sha256"])
            self.assertEqual(4, provider.calls)

    def test_r3_seal_binds_resource_authority_and_fresh_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            resource_workspace, result = self._resource_authority(root, provider)
            sealed = seal_emc_r3_protocol(
                root / "r3",
                resource_workspace=resource_workspace,
                resource_record_sha256=result["record_sha256"],
                implementation_provider=provider,
            )
            manifest = json.loads((root / "r3" / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8"))
            self.assertEqual(78_000, sealed["token_ceiling"])
            self.assertEqual(12, sealed["scientific_model_calls"])
            self.assertEqual(
                {"emc-r3-emc_r3_assignment_beta", "emc-r3-emc_r3_coverage_beta"},
                {state["state_id"] for state in manifest["states"]},
            )
            self.assertEqual(result["record_sha256"], manifest["resource_authority"]["record_sha256"])

    def test_instrumentation_passes_without_scientific_provider_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            resource_workspace, result = self._resource_authority(root, provider)
            sealed = seal_emc_r3_protocol(
                root / "r3",
                resource_workspace=resource_workspace,
                resource_record_sha256=result["record_sha256"],
                implementation_provider=provider,
            )
            calls_before = provider.calls
            sensitivity = run_emc_r3_instrumentation(
                root / "r3",
                manifest_digest=sealed["manifest_digest"],
                implementation_provider=provider,
            )
            self.assertTrue(sensitivity["passed"])
            self.assertEqual(calls_before, provider.calls)

    def test_failed_instrumentation_blocks_scientific_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            resource_workspace, result = self._resource_authority(root, provider)
            sealed = seal_emc_r3_protocol(
                root / "r3",
                resource_workspace=resource_workspace,
                resource_record_sha256=result["record_sha256"],
                implementation_provider=provider,
            )
            ArtifactStore(root / "r3" / "result-artifacts").write_record(
                SENSITIVITY_RECORD,
                {"manifest_digest": sealed["manifest_digest"], "passed": False},
            )
            calls_before = provider.calls
            with self.assertRaisesRegex(RuntimeError, "instrumentation sensitivity"):
                run_emc_r3_calibration(
                    root / "r3",
                    manifest_digest=sealed["manifest_digest"],
                    implementation_provider=provider,
                )
            self.assertEqual(calls_before, provider.calls)

    def test_orphaned_invocation_blocks_entire_scientific_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            resource_workspace, result = self._resource_authority(root, provider)
            sealed = seal_emc_r3_protocol(
                root / "r3",
                resource_workspace=resource_workspace,
                resource_record_sha256=result["record_sha256"],
                implementation_provider=provider,
            )
            run_emc_r3_instrumentation(
                root / "r3",
                manifest_digest=sealed["manifest_digest"],
                implementation_provider=provider,
            )
            ArtifactStore(root / "r3" / "result-artifacts").write_record(
                "provider-invocations/orphan/claim.json",
                {"invocation_id": "orphan"},
            )
            calls_before = provider.calls
            with self.assertRaisesRegex(RuntimeError, "new calls forbidden"):
                run_emc_r3_calibration(
                    root / "r3",
                    manifest_digest=sealed["manifest_digest"],
                    implementation_provider=provider,
                )
            self.assertEqual(calls_before, provider.calls)


if __name__ == "__main__":
    unittest.main()
