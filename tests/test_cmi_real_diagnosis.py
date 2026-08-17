from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_real_diagnosis import REPLICATES_PER_STATE, _hypotheses_and_probes


class CmiRealDiagnosisTests(unittest.TestCase):
    def test_protocol_is_six_calls_and_hypotheses_are_competing(self) -> None:
        hypotheses, probes = _hypotheses_and_probes()
        self.assertEqual(3, REPLICATES_PER_STATE)
        self.assertEqual(3, len(hypotheses))
        self.assertEqual({item.hypothesis_id for item in hypotheses}, {item.target_hypothesis_id for item in probes})
        self.assertTrue(all(item.fresh_task_budget == 0 for item in probes))


if __name__ == "__main__":
    unittest.main()
