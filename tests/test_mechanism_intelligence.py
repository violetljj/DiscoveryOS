from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.mechanism_intelligence import (
    DiagnosisPhase,
    DiagnosticProbeResult,
    MechanismDiagnosisSession,
    ProbeValidity,
    run_cmi_r0_synthetic,
    seal_cmi_r0_protocol,
    synthetic_fixture,
)
from discoveryos.cli import build_parser


class MechanismIntelligenceTests(unittest.TestCase):
    def test_synthetic_controls_establish_diagnostic_sensitivity_without_real_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sealed = seal_cmi_r0_protocol(workspace)
            result = run_cmi_r0_synthetic(workspace, manifest_digest=sealed["manifest_digest"])
            replayed = run_cmi_r0_synthetic(workspace, manifest_digest=sealed["manifest_digest"])
            self.assertEqual("CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_PASSED", result["status"])
            self.assertTrue(result["synthetic_sensitivity_passed"])
            self.assertFalse(result["real_bottleneck_established"])
            self.assertFalse(result["real_mechanism_brief_authorized"])
            self.assertFalse(result["fresh_search_value_budget_authorized"])
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["evaluator_calls"])
            self.assertEqual(0, result["fresh_task_budget_consumed"])
            self.assertEqual(result["report_sha256"], replayed["report_sha256"])
            self.assertEqual(
                "NO_ACTIONABLE_BOTTLENECK",
                result["scenarios"]["null_control"]["diagnosis"]["terminal_phase"],
            )
            positive = result["scenarios"]["positive_control"]["diagnosis"]
            self.assertEqual("MECHANISM_BRIEF_ALLOWED", positive["terminal_phase"])
            self.assertEqual("H5_STRUCTURAL_BASIN_LOCK", positive["mechanism_brief_hypothesis_id"])

    def test_cli_exposes_separate_seal_and_run_commands(self) -> None:
        parser = build_parser()
        sealed = parser.parse_args(["cmi-r0-seal", "--workspace", "runs/test-cmi"])
        executed = parser.parse_args(
            [
                "cmi-r0-run-synthetic",
                "--workspace",
                "runs/test-cmi",
                "--manifest-digest",
                "a" * 64,
            ]
        )
        self.assertEqual("cmi-r0-seal", sealed.command)
        self.assertEqual("cmi-r0-run-synthetic", executed.command)

    def test_phase_order_is_fail_closed(self) -> None:
        phenotype, hypotheses, probes, _ = synthetic_fixture()
        session = MechanismDiagnosisSession(phenotype)
        with self.assertRaisesRegex(RuntimeError, "HYPOTHESES_FROZEN"):
            session.freeze_probes(probes)
        session.freeze_hypotheses(hypotheses)
        session.freeze_probes(probes)
        with self.assertRaisesRegex(RuntimeError, "PROBES_FROZEN"):
            session.freeze_hypotheses(hypotheses)

    def test_probe_result_must_bind_frozen_spec_and_budget(self) -> None:
        phenotype, hypotheses, probes, _ = synthetic_fixture()
        session = MechanismDiagnosisSession(phenotype)
        session.freeze_hypotheses(hypotheses)
        session.freeze_probes(probes)
        results = [
            DiagnosticProbeResult(
                probe_id=probe.probe_id,
                probe_spec_digest=probe.spec_digest,
                phenotype_receipt_id=phenotype.receipt_id,
                observed_value=0.5,
                validity=ProbeValidity.VALID,
                reason="test",
            )
            for probe in probes
        ]
        results[0] = DiagnosticProbeResult(
            probe_id=probes[0].probe_id,
            probe_spec_digest=probes[0].spec_digest,
            phenotype_receipt_id=phenotype.receipt_id,
            observed_value=0.5,
            validity=ProbeValidity.VALID,
            reason="over budget",
            model_calls=1,
        )
        with self.assertRaisesRegex(ValueError, "call budget"):
            session.diagnose(results)

    def test_not_evaluable_probe_cannot_authorize_mechanism_brief(self) -> None:
        phenotype, hypotheses, probes, _ = synthetic_fixture()
        session = MechanismDiagnosisSession(phenotype)
        session.freeze_hypotheses(hypotheses)
        session.freeze_probes(probes)
        results = []
        for index, probe in enumerate(probes):
            results.append(
                DiagnosticProbeResult(
                    probe_id=probe.probe_id,
                    probe_spec_digest=probe.spec_digest,
                    phenotype_receipt_id=phenotype.receipt_id,
                    observed_value=None if index == 0 else 0.5,
                    validity=ProbeValidity.NOT_EVALUABLE if index == 0 else ProbeValidity.VALID,
                    reason="synthetic unavailable" if index == 0 else "synthetic",
                )
            )
        session.diagnose(results)
        report = session.finalize()
        self.assertEqual(DiagnosisPhase.NO_ACTIONABLE_BOTTLENECK, report.terminal_phase)
        self.assertIsNone(report.mechanism_brief_hypothesis_id)

    def test_manifest_digest_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            seal_cmi_r0_protocol(workspace)
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                run_cmi_r0_synthetic(workspace, manifest_digest="0" * 64)


if __name__ == "__main__":
    unittest.main()
