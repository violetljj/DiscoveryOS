from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.cmi_probe_calibration import (
    run_cmi_probe_calibration,
    seal_cmi_probe_calibration,
)


class CmiProbeCalibrationTests(unittest.TestCase):
    def test_real_dev_probe_controls_are_create_once_zero_call_and_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "fresh-root"
            sealed = seal_cmi_probe_calibration(workspace, require_clean_repository=False)
            result = run_cmi_probe_calibration(workspace, manifest_digest=sealed["manifest_digest"])
            replayed = run_cmi_probe_calibration(workspace, manifest_digest=sealed["manifest_digest"])
            self.assertEqual("CMI_R1_REAL_PROBE_CALIBRATION_PASSED", result["status"])
            self.assertEqual(2, len(result["state_results"]))
            self.assertTrue(all(item["passed"] for item in result["state_results"]))
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["provider_calls"])
            self.assertEqual(0, result["fresh_search_value_tasks_consumed"])
            self.assertFalse(result["real_bottleneck_established"])
            self.assertFalse(result["real_mechanism_brief_authorized"])
            self.assertTrue(result["bounded_real_diagnosis_preregistration_authorized"])
            self.assertEqual(result["report_sha256"], replayed["report_sha256"])

    def test_wrong_manifest_digest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "fresh-root"
            seal_cmi_probe_calibration(workspace, require_clean_repository=False)
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                run_cmi_probe_calibration(workspace, manifest_digest="0" * 64)

    def test_nonempty_root_cannot_be_resealed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "fresh-root"
            seal_cmi_probe_calibration(workspace, require_clean_repository=False)
            with self.assertRaisesRegex(RuntimeError, "create-once"):
                seal_cmi_probe_calibration(workspace, require_clean_repository=False)


if __name__ == "__main__":
    unittest.main()
