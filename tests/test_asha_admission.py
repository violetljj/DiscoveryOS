from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.asha_synthetic import run_asha_admission


class ASHAAdmissionTests(unittest.TestCase):
    def test_matched_budget_synthetic_admission_is_replayable_and_blind_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = run_asha_admission(Path(directory), seeds=3)
            self.assertTrue(report["summary"]["matched_actual_cpu"])
            self.assertTrue(report["summary"]["mechanics_passed"])
            self.assertEqual(0, report["summary"]["final_blind_receipts"])
            for seed_report in report["seed_reports"]:
                self.assertEqual(54.0, seed_report["asha"]["actual_usage"]["cpu_seconds"])
                self.assertEqual(54.0, seed_report["random"]["actual_usage"]["cpu_seconds"])
                self.assertEqual(8, seed_report["promotion_count"])
                self.assertEqual(1, seed_report["asha_retry_count"])
                self.assertTrue(seed_report["checks"]["asha"]["multi_rung_reordering"])
                self.assertTrue(all(seed_report["checks"]["asha"].values()))
                self.assertTrue(all(seed_report["checks"]["random"].values()))


if __name__ == "__main__":
    unittest.main()
