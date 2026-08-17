from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.parent_intervention_dev import (
    run_parent_dev_cib,
    seal_parent_dev_cib_protocol,
)


class ParentInterventionDevelopmentTests(unittest.TestCase):
    def test_parent_policy_replays_and_transmits_value_on_consumed_dev_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sealed = seal_parent_dev_cib_protocol(workspace)
            result = run_parent_dev_cib(
                workspace, manifest_digest=sealed["manifest_digest"]
            )
            self.assertEqual("PARENT_CIB_DEVELOPMENT_TRACE_COMPLETE", result["status"])
            self.assertTrue(result["actual_parent_policy_invoked"])
            self.assertTrue(all(item["replay_valid"] for item in result["policy_replay"]))
            self.assertTrue(all(not item["selected_is_incumbent"] for item in result["policy_replay"]))
            self.assertEqual(
                "INTERVENTION_VALUE_ADMITTED",
                result["paired_analysis"]["intervention_verdict"],
            )
            self.assertEqual(
                "PARENT_VALUE_TRANSMISSION_DETECTED_ON_SEMANTICS_PRESERVING_DEV_REPLAY",
                result["development_signal"],
            )
            self.assertFalse(result["real_parent_mechanism_admitted"])
            self.assertFalse(result["representative_strong_agent_downstream"])
            self.assertEqual(
                "DO_NOT_OPEN_SI3_FRESH_BUDGET", result["si3_fresh_budget_decision"]
            )
            self.assertEqual(18, len(result["pair_receipts"]))

    def test_parent_protocol_fails_closed_on_wrong_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            seal_parent_dev_cib_protocol(workspace)
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                run_parent_dev_cib(workspace, manifest_digest="0" * 64)


if __name__ == "__main__":
    unittest.main()
