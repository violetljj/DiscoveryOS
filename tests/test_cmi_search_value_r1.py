from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.cmi_search_value_r1 import (
    _aggregate,
    _bounded_observations,
    _load_r7_authority,
    _run_task,
)
from discoveryos.benchmarks.search_policy_admission import SearchObservation
from discoveryos.benchmarks.cmi_search_value_r1_tasks import cmi_search_value_r1_tasks
from tests.test_strategy_integration_si1 import _CommentProvider


BRIEF = {
    "causal_target": "functional_output_basin",
    "required_context": [
        "frozen_task_contract_and_public_api",
        "frozen_state_local_functional_probe",
        "incumbent_functional_signature",
        "matched_resource_ceiling",
    ],
    "intervention_contract": {
        "required_change": "change algorithmic decomposition before source generation",
        "admission_fingerprint": "functional distance greater than 0.10",
        "source_difference_is_sufficient": False,
    },
}


class CmiSearchValueR1Tests(unittest.TestCase):
    def test_over_budget_observation_is_excluded_instead_of_crashing_aggregation(self) -> None:
        observations = (
            SearchObservation("within", None, 100, 1.0, 0.2, True, True, "basin"),
            SearchObservation("over", "within", 120_001, 2.0, 0.3, True, True, "basin"),
        )
        self.assertEqual((observations[0],), _bounded_observations(observations))

    def test_checked_in_r7_authority_uses_the_frozen_success_gate(self) -> None:
        workspace = Path(__file__).resolve().parents[2] / "DiscoveryOS" / "runs" / "cmi-r7-fresh-causal-replication"
        if not workspace.is_dir():
            self.skipTest("ignored CMI-R7 authority is not present in this checkout")
        authority = _load_r7_authority(
            workspace,
            "3072e74c1a0114920f98c7930097a5488dd8a50763709a073513a1ef4dca763f",
        )
        self.assertTrue(authority["report"]["success_gate"]["passed"])

    def test_population_is_fixed_balanced_and_unique(self) -> None:
        tasks = cmi_search_value_r1_tasks()
        self.assertEqual(6, len(tasks))
        self.assertEqual(6, len({item.task.task_id for item in tasks}))
        self.assertEqual(6, len({item.payload_digest for item in tasks}))
        categories = [item.task.category for item in tasks]
        self.assertEqual(3, categories.count("capacitated_cost_assignment"))
        self.assertEqual(3, categories.count("budgeted_weighted_coverage"))

    def test_common_prefix_detects_eligibility_and_cmi_contributes_downstream(self) -> None:
        item = cmi_search_value_r1_tasks()[0]
        provider = _CommentProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit = item.task.initialize_repository(root / "task")
            report = asyncio.run(
                _run_task(
                    root / "run",
                    item,
                    repository,
                    commit,
                    {"manifest_digest": "test", "frozen_brief": BRIEF},
                    provider,
                )
            )
        self.assertTrue(report["causal_trace"]["opportunity"])
        self.assertTrue(report["causal_trace"]["eligible"])
        self.assertTrue(report["causal_trace"]["invoked"])
        self.assertTrue(report["causal_trace"]["accepted_descendant"])
        self.assertTrue(report["causal_trace"]["retained_after_intervention"])
        self.assertTrue(report["causal_trace"]["downstream_parent_was_cmi"])
        self.assertTrue(report["causal_trace"]["downstream_retained_contribution"])
        self.assertEqual("WIN", report["paired"]["outcome"])

    def test_aggregate_requires_search_transmission_and_cost_gates(self) -> None:
        tasks = cmi_search_value_r1_tasks()
        rows = [self._row(item.task.task_id, item.task.category) for item in tasks]
        report = _aggregate(
            {
                "manifest_digest": "sealed",
                "experiment_code_sha": "commit",
                "claim_ceiling": "bounded",
            },
            rows,
        )
        self.assertEqual(
            "CMI_SEARCH_VALUE_ESTABLISHED_ON_FROZEN_ASSIGNMENT_COVERAGE_REGIME",
            report["verdict"],
        )
        rows[0]["causal_trace"]["invoked"] = False
        rows[0]["causal_trace"]["eligible"] = True
        report = _aggregate(
            {
                "manifest_digest": "sealed",
                "experiment_code_sha": "commit",
                "claim_ceiling": "bounded",
            },
            rows,
        )
        self.assertEqual("SEARCH_ADVANTAGE_OBSERVED_BUT_NOT_ATTRIBUTABLE_TO_CMI", report["verdict"])

    @staticmethod
    def _row(task_id: str, category: str) -> dict:
        arm = {
            "CMI_DISABLED": {
                "metrics": {"best_improvement": 0.1, "auc_over_token_budget": 0.05},
                "actual_usage": {"tokens": 100},
                "evaluator_calls": 5,
                "elapsed_seconds": 1.0,
                "resource_checks": {"token_ceiling_respected": True, "wall_ceiling_respected": True},
            },
            "CMI_ENABLED": {
                "metrics": {"best_improvement": 0.2, "auc_over_token_budget": 0.1},
                "actual_usage": {"tokens": 90},
                "evaluator_calls": 5,
                "elapsed_seconds": 1.1,
                "resource_checks": {"token_ceiling_respected": True, "wall_ceiling_respected": True},
            },
        }
        return {
            "task_id": task_id,
            "task_category": category,
            "arms": arm,
            "paired": {"outcome": "WIN", "final_delta": 0.1, "anytime_auc_delta": 0.05},
            "causal_trace": {
                "opportunity": True,
                "eligible": True,
                "invoked": True,
                "accepted_descendant": True,
                "retained_after_intervention": True,
                "downstream_retained_contribution": True,
            },
        }


if __name__ == "__main__":
    unittest.main()
