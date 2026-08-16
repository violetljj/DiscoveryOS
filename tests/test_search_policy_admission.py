from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.benchmarks.search_policy_admission import (
    METRIC_DEFINITIONS,
    REQUIRED_ARM_IDS,
    FrozenModelConfig,
    PolicyImplementation,
    ResidualHeadroomEvidence,
    SearchObservation,
    compute_policy_metrics,
    evaluate_task_admission,
    seal_search_policy_protocol,
    verify_search_policy_manifest,
)
from discoveryos.contracts.models import MetricDirection, ResourceBudget
from discoveryos.util import digest_json


def _digest(label: str) -> str:
    return digest_json({"fixture": label})


def _task(index: int = 0) -> ResidualHeadroomEvidence:
    return ResidualHeadroomEvidence(
        task_id=f"headroom-task-{index}",
        task_payload_digest=_digest(f"task-{index}"),
        initial_state_digest=_digest(f"initial-{index}"),
        evaluator_id="frozen-evaluator-v1",
        evaluator_digest=_digest("evaluator"),
        baseline_candidate_digest=_digest(f"baseline-{index}"),
        baseline_receipt_digest=_digest(f"receipt-{index}"),
        baseline_score=0.20,
        score_direction=MetricDirection.MAXIMIZE,
        score_resolution=0.05,
        reference_score=0.80,
        reference_kind="exact_oracle",
        reference_digest=_digest(f"oracle-{index}"),
        selection_provenance_digest=_digest(f"selection-provenance-{index}"),
        valid_intermediate_scores=(0.35, 0.55),
        trajectory_classes=("local-refinement", "structural-rewrite"),
        baseline_basin_id="baseline-basin",
        basin_labeler_digest=_digest(f"basin-labeler-{index}"),
        baseline_executable=True,
        baseline_replay_count=2,
        baseline_replay_consistent=True,
        source_independent_of_compared_policies=True,
        pre_admission_model_calls=0,
    )


def _policies() -> tuple[PolicyImplementation, ...]:
    return tuple(
        PolicyImplementation(
            arm_id=arm_id,
            controller_digest=_digest(f"controller-{arm_id}"),
            prompt_template_digest=_digest(f"prompt-{arm_id}"),
        )
        for arm_id in REQUIRED_ARM_IDS
    )


class SearchPolicyAdmissionTests(unittest.TestCase):
    def test_task_admission_rejects_candidate_feedback_and_ceiling_tasks(self) -> None:
        admitted = evaluate_task_admission(_task())
        self.assertTrue(admitted["admitted"])
        contaminated = evaluate_task_admission(replace(_task(), pre_admission_model_calls=1))
        self.assertFalse(contaminated["admitted"])
        self.assertFalse(contaminated["checks"]["no_pre_admission_model_calls"])
        ceiling = evaluate_task_admission(
            replace(_task(), reference_score=0.30, valid_intermediate_scores=(0.25,))
        )
        self.assertFalse(ceiling["admitted"])
        self.assertFalse(ceiling["checks"]["baseline_not_near_reference"])
        self.assertFalse(ceiling["checks"]["multiple_valid_improvement_magnitudes"])

    def test_protocol_seal_freezes_shared_surface_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = seal_search_policy_protocol(
                Path(directory),
                tasks=tuple(_task(index) for index in range(8)),
                model_config=FrozenModelConfig(
                    provider="fixture-provider",
                    model="fixture-model",
                    provider_version="fixture-1",
                    settings_digest=_digest("settings"),
                ),
                policies=_policies(),
                shared_budget=ResourceBudget(tokens=1000, wall_seconds=120),
                replicates_per_task=2,
                execution_order_seed=1701,
            )
            self.assertEqual("SEALED_PRE_MODEL", result["status"])
            self.assertEqual("SEARCH_POLICY_PROTOCOL_ONLY", result["claim_ceiling"])
            self.assertEqual(0, result["model_calls"])
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertFalse(
                manifest["task_admission_policy"]["one_shot_or_other_candidate_policy_probe_used_for_selection"]
            )
            self.assertEqual(set(REQUIRED_ARM_IDS), {arm["arm_id"] for arm in manifest["arms"]})
            self.assertEqual(set(METRIC_DEFINITIONS), set(manifest["metric_definitions"]))
            self.assertFalse(
                manifest["architecture_boundary"]["official_external_systems_used_as_internal_arms"]
            )
            self.assertFalse(
                manifest["architecture_boundary"]["full_unified_search_kernel_admitted_by_this_protocol"]
            )
            verify_search_policy_manifest(manifest, result["protocol_manifest_digest"])
            manifest["fairness_invariants"]["replicates_per_task"] = 3
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                verify_search_policy_manifest(manifest, result["protocol_manifest_digest"])

    def test_protocol_seal_fails_closed_when_any_task_is_contaminated(self) -> None:
        tasks = tuple(_task(index) for index in range(7)) + (
            replace(_task(7), source_independent_of_compared_policies=False),
        )
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
            ValueError, "policy_independent_headroom_source"
        ):
            seal_search_policy_protocol(
                Path(directory),
                tasks=tasks,
                model_config=FrozenModelConfig(
                    provider="fixture-provider",
                    model="fixture-model",
                    provider_version="fixture-1",
                    settings_digest=_digest("settings"),
                ),
                policies=_policies(),
                shared_budget=ResourceBudget(tokens=1000, wall_seconds=120),
                replicates_per_task=1,
                execution_order_seed=17,
            )

    def test_trace_metrics_use_frozen_budget_and_basin_labels(self) -> None:
        task = _task()
        observations = (
            SearchObservation("candidate-a", None, 100, 1.0, 0.30, True, True, "local-basin"),
            SearchObservation("candidate-b", "candidate-a", 200, 2.0, 0.50, True, True, "structural-basin"),
            SearchObservation("candidate-c", "candidate-b", 300, 3.0, None, False, False, None),
        )
        metrics = compute_policy_metrics(task, observations, token_budget=400, wall_budget=4.0)
        self.assertEqual(0.30, metrics["best_improvement"])
        self.assertEqual(0.175, metrics["auc_over_token_budget"])
        self.assertTrue(metrics["success"])
        self.assertEqual(0.66666667, metrics["valid_candidate_rate"])
        self.assertEqual(1.0, metrics["basin_jump_rate"])
        self.assertEqual(100, metrics["tokens_to_improvement"])
        self.assertEqual(1.0, metrics["wall_time_to_improvement"])

    def test_minimization_tasks_are_direction_normalized(self) -> None:
        task = replace(
            _task(),
            baseline_score=10.0,
            score_direction=MetricDirection.MINIMIZE,
            score_resolution=1.0,
            reference_score=5.0,
            valid_intermediate_scores=(9.0, 7.0),
        )
        self.assertTrue(evaluate_task_admission(task)["admitted"])
        metrics = compute_policy_metrics(
            task,
            (
                SearchObservation("candidate-a", None, 100, 1.0, 9.0, True, True, "local-basin"),
                SearchObservation("candidate-b", "candidate-a", 200, 2.0, 7.0, True, True, "structural-basin"),
            ),
            token_budget=300,
            wall_budget=3.0,
        )
        self.assertEqual(3.0, metrics["best_improvement"])
        self.assertEqual(3.0, metrics["best_improvement_steps"])


if __name__ == "__main__":
    unittest.main()
