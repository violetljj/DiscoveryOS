from __future__ import annotations

import unittest

from discoveryos.benchmarks.cmi_escape_brief import _admission_checks, _brief


class CmiEscapeBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "probe_results": [
                {"probe_id": "P3_RANKED_CONTROL_RECOVERY", "observed_value": 1.0},
                {"probe_id": "P4_DIRECT_VALID_RATE", "observed_value": 1.0},
                {"probe_id": "P5_FUNCTIONAL_DIVERSITY", "observed_value": 0.0},
            ]
        }
        self.states = [
            {"same_source_functional_distance": 0.0, "baseline_reference_functional_distance": 0.42, "reference_headroom": 0.20},
            {"same_source_functional_distance": 0.0, "baseline_reference_functional_distance": 0.28, "reference_headroom": 0.10},
        ]

    def test_brief_requires_behavioral_not_source_only_intervention(self) -> None:
        brief = _brief()
        self.assertFalse(brief["intervention_contract"]["source_difference_is_sufficient"])
        self.assertIn("source_only_diversity", brief["forbidden_substitutions"])
        self.assertEqual("utility_or_auc_difference", brief["causal_path"][-1])

    def test_bound_null_and_positive_controls_admit_brief(self) -> None:
        checks = _admission_checks(_brief(), self.report, {"states": self.states})
        self.assertTrue(all(checks.values()))

    def test_failed_positive_control_rejects_brief(self) -> None:
        self.states[0]["baseline_reference_functional_distance"] = 0.0
        checks = _admission_checks(_brief(), self.report, {"states": self.states})
        self.assertFalse(checks["state_local_positive_control_bound"])


if __name__ == "__main__":
    unittest.main()
