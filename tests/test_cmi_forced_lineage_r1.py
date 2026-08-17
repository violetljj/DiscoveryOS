from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.cmi_forced_lineage_r1 import (
    ARM_NAMES,
    _aggregate,
    _run_arm,
)
from discoveryos.benchmarks.cmi_search_value_r1_tasks import cmi_search_value_r1_tasks
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2 import _si2_headroom_evidence
from tests.test_strategy_integration_si1 import _CommentProvider


class CmiForcedLineageR1Tests(unittest.TestCase):
    def test_forced_lineage_uses_each_valid_child_as_the_next_parent(self) -> None:
        item = cmi_search_value_r1_tasks()[0]
        provider = _CommentProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit = item.task.initialize_repository(root / "task")
            baseline_source = normalized_source((repository / item.task.entrypoint).read_text(encoding="utf-8"))
            baseline_score = _si2_headroom_evidence(item, repository)[0].baseline_score
            result = asyncio.run(
                _run_arm(
                    root / "arm",
                    item,
                    repository,
                    commit,
                    provider,
                    "CMI_DESCENDANT_LINEAGE",
                    {
                        "source": baseline_source + "\n# forced generation-zero fixture\n",
                        "source_candidate_id": "source-cmi",
                        "score": baseline_score,
                    },
                )
            )

        self.assertTrue(result["technically_evaluable"])
        self.assertEqual(2, result["provider_calls"])
        self.assertEqual(
            result["downstream"][0]["candidate_id"],
            result["downstream"][1]["authoritative_parent_id"],
        )
        self.assertFalse(result["generation_zero"]["counts_as_success"])

    def test_strict_five_state_gate_authorizes_only_consumed_dev_signal(self) -> None:
        rows = [
            self._row(f"assignment-{index}", "capacitated_cost_assignment")
            for index in range(3)
        ] + [
            self._row(f"coverage-{index}", "budgeted_weighted_coverage")
            for index in range(2)
        ]
        report = _aggregate(
            {
                "manifest_digest": "sealed",
                "experiment_code_sha": "commit",
                "claim_ceiling": "consumed-dev-only",
            },
            rows,
        )
        self.assertEqual(
            "CMI_STEPPING_STONE_SIGNAL_DETECTED_ON_CONSUMED_V3_STATES",
            report["verdict"],
        )
        self.assertIn("NO_FRESH_BUDGET", report["decision"])

        rows[0]["paired"].update(
            {
                "outcome": "TIE",
                "cmi_minus_control_best_downstream_utility": 0.0,
                "cmi_minus_control_anytime_auc": 0.0,
            }
        )
        report = _aggregate(
            {
                "manifest_digest": "sealed",
                "experiment_code_sha": "commit",
                "claim_ceiling": "consumed-dev-only",
            },
            rows,
        )
        self.assertEqual(
            "CMI_FORCED_LINEAGE_VALUE_NOT_ESTABLISHED_ON_CONSUMED_V3_STATES",
            report["verdict"],
        )
        self.assertEqual(
            "STOP_CMI_SEARCH_INTEGRATION_NO_FRESH_BUDGET_OR_SELECTION_TUNING",
            report["decision"],
        )

    @staticmethod
    def _row(task_id: str, category: str) -> dict:
        arms = {
            name: {
                "provider_calls": 2,
                "technically_evaluable": True,
                "best_downstream_utility": 0.9 if name == "CMI_DESCENDANT_LINEAGE" else 0.8,
                "metrics": {"auc_over_token_budget": 0.7 if name == "CMI_DESCENDANT_LINEAGE" else 0.6},
            }
            for name in ARM_NAMES
        }
        return {
            "task_id": task_id,
            "task_category": category,
            "arms": arms,
            "paired": {
                "evaluable": True,
                "outcome": "WIN",
                "cmi_minus_control_best_downstream_utility": 0.1,
                "cmi_minus_control_anytime_auc": 0.1,
            },
        }


if __name__ == "__main__":
    unittest.main()
