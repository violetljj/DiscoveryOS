from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.search_causality_autopsy import (
    _compare_arm_traces,
    _structural_digest,
    audit_si2_search_causality,
)


class SearchCausalityAutopsyTests(unittest.TestCase):
    def test_structural_digest_erases_names_and_literals_but_preserves_control_flow(self) -> None:
        first = "def f(xs):\n    return [x + 1 for x in xs]\n"
        renamed = "def g(values):\n    return [item + 9 for item in values]\n"
        branched = "def g(values):\n    if values:\n        return [item + 9 for item in values]\n    return []\n"
        self.assertEqual(_structural_digest(first), _structural_digest(renamed))
        self.assertNotEqual(_structural_digest(first), _structural_digest(branched))

    def test_arm_comparison_keeps_candidate_and_evaluation_surfaces_separate(self) -> None:
        left = {
            "exact_candidate_signatures": ["a", "b"],
            "structural_candidate_signatures": ["s"],
            "evaluation_trajectory": [{"score": 1.0}],
        }
        right = {
            "exact_candidate_signatures": ["b", "c"],
            "structural_candidate_signatures": ["s"],
            "evaluation_trajectory": [{"score": 1.0}],
        }
        comparison = _compare_arm_traces(left, right)
        self.assertEqual(1, comparison["exact_candidate_overlap_count"])
        self.assertAlmostEqual(1 / 3, comparison["exact_candidate_jaccard"])
        self.assertEqual(1.0, comparison["structural_candidate_jaccard"])
        self.assertTrue(comparison["evaluation_trajectory_equal"])

    def test_autopsy_refuses_to_write_inside_consumed_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            with self.assertRaisesRegex(ValueError, "outside the consumed"):
                audit_si2_search_causality(
                    source,
                    manifest_digest="unused",
                    output_workspace=source / "autopsy",
                )


if __name__ == "__main__":
    unittest.main()
