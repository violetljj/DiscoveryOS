from __future__ import annotations

import unittest

from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    BranchSearchState,
    CandidateSearchState,
    DeterministicActionController,
    SearchAction,
    SearchState,
)
from discoveryos.operators.novelty import (
    NoveltyComparison,
    NoveltyConfig,
    NoveltyDecision,
    NoveltyReceipt,
    ShinkaStyleNoveltyPolicy,
    novelty_diagnostics,
)


BASE = """def improve(value):
    total = value + 1
    return total
"""


class NoveltyMechanicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = NoveltyConfig(
            max_novelty_attempts=2,
            similarity_threshold=0.5,
            semantic_difference_threshold=0.2,
        )
        self.policy = ShinkaStyleNoveltyPolicy(self.config)
        self.comparisons = (
            NoveltyComparison(
                candidate_id="parent",
                scopes=("selected_parent", "archive"),
                code=BASE,
            ),
        )

    def test_exact_duplicate_rejected_before_evaluation(self) -> None:
        assessment = self.policy.assess(BASE + "# formatting only\n", self.comparisons, attempt=1)
        self.assertEqual(NoveltyDecision.REJECT_RESAMPLE, assessment.decision)
        self.assertTrue(assessment.exact_duplicate)
        self.assertIn("CHEAP_LEVEL_1_REJECT", assessment.reason_codes)
        self.assertEqual("L1_NORMALIZED_FINGERPRINT", assessment.cascade_level)
        self.assertTrue(all(not item.semantic_checked for item in assessment.similarities))

    def test_near_duplicate_takes_high_similarity_semantic_path(self) -> None:
        proposal = BASE.replace("value + 1", "value + 2")
        assessment = self.policy.assess(proposal, self.comparisons, attempt=1)
        self.assertTrue(assessment.high_similarity)
        self.assertIn(
            assessment.decision,
            {NoveltyDecision.REJECT_RESAMPLE, NoveltyDecision.ACCEPT},
        )
        self.assertTrue(any("SEMANTIC_JUDGE" in reason for reason in assessment.reason_codes))

    def test_genuinely_novel_candidate_is_accepted(self) -> None:
        proposal = """def improve(value):
    if value < 0:
        return value * value
    return sum(range(value + 1))
"""
        assessment = self.policy.assess(proposal, self.comparisons, attempt=1)
        self.assertEqual(NoveltyDecision.ACCEPT, assessment.decision)
        self.assertFalse(assessment.exact_duplicate)

    def test_resampling_is_bounded_and_exhaustion_is_deterministic(self) -> None:
        first = self.policy.assess(BASE, self.comparisons, attempt=1)
        last = self.policy.assess(BASE, self.comparisons, attempt=2)
        self.assertEqual(NoveltyDecision.REJECT_RESAMPLE, first.decision)
        self.assertEqual(NoveltyDecision.REJECT_EXHAUSTED, last.decision)
        with self.assertRaises(ValueError):
            self.policy.assess(BASE, self.comparisons, attempt=3)

    def test_receipt_replay_and_diagnostics(self) -> None:
        assessment = self.policy.assess(BASE, self.comparisons, attempt=1)
        receipt = NoveltyReceipt.create(
            run_id="novelty-mechanics",
            step=0,
            attempt=1,
            max_attempts=2,
            source_candidate_id="parent",
            proposal_candidate_id="proposal",
            proposal_code=BASE,
            comparisons=self.comparisons,
            assessment=assessment,
            policy_version=self.config.policy_version,
        )
        self.assertEqual((True, ()), self.policy.replay(receipt, BASE, self.comparisons))
        diagnostics = novelty_diagnostics((receipt,))
        self.assertEqual(1, diagnostics.duplicate_avoided_evaluations)
        self.assertEqual(1, diagnostics.novelty_resample_count)
        self.assertEqual(0, diagnostics.novelty_tokens)
        self.assertEqual(1.0, diagnostics.unique_candidate_rate)

    def test_worst_case_retry_budget_is_rejected_before_action_start(self) -> None:
        complete = ResourceBudget(tokens=30, wall_seconds=3)
        config = ActionControllerConfig(
            minimum_replicates=1,
            costs=(
                ActionCost(
                    SearchAction.LOCAL_PATCH,
                    complete,
                    generation_reserve=ResourceBudget(tokens=10, wall_seconds=1),
                    novelty_resample_reserve=ResourceBudget(tokens=20, wall_seconds=2),
                ),
                ActionCost(SearchAction.STRUCTURAL_ESCAPE, complete),
                ActionCost(SearchAction.REPLICATE, ResourceBudget(cpu_seconds=1)),
                ActionCost(SearchAction.PROMOTE_FIDELITY, ResourceBudget(cpu_seconds=1)),
            ),
        )
        candidate = CandidateSearchState(
            candidate_id="candidate",
            branch_id="branch",
            fidelity=Fidelity.G0,
            latest_evidence_receipt_id="evidence",
            scheduling_utility=1.0,
            replicate_count=1,
        )
        branch = BranchSearchState(
            branch_id="branch",
            lineage_root_id="candidate",
            parent_candidate_id="candidate",
            algorithm_family="family",
            generations_since_improvement=0,
            recent_improvements=(),
            recent_delta_similarity=0.0,
            lineage_receipt_ids=("evidence",),
            failure_signatures=(),
            local_actions_remaining=1,
            structural_actions_remaining=0,
        )
        state = SearchState(
            run_id="budget-preflight",
            step=0,
            incumbent_candidate_id="candidate",
            incumbent_utility=1.0,
            utility_metric_name="score",
            metric_direction=MetricDirection.MAXIMIZE,
            candidates=(candidate,),
            branches=(branch,),
            reusable_component_ids=(),
            remaining_budget=ResourceBudget(tokens=29, wall_seconds=3),
        )
        decision = DeterministicActionController(config).decide(state)
        self.assertEqual(SearchAction.STOP, decision.action)
        self.assertEqual(SearchAction.LOCAL_PATCH, decision.rejected_action)
        self.assertIn("STOP_BUDGET_INSUFFICIENT", decision.reason_codes)
        self.assertEqual(ResourceBudget(tokens=20, wall_seconds=2), decision.novelty_resample_reserve)

    def test_duplicate_rejection_stops_when_generation_is_costlier_than_evaluation(self) -> None:
        policy = ShinkaStyleNoveltyPolicy(
            NoveltyConfig(
                policy_version="shinka_novelty_dos_v2_cheap_first_affordable",
                max_novelty_attempts=2,
                affordability_gate=True,
            )
        )
        assessment = policy.assess(BASE, self.comparisons, attempt=1)
        resolved = policy.resolve_resampling(
            assessment,
            generation_reserve=ResourceBudget(tokens=100, wall_seconds=10),
            evaluation_reserve=ResourceBudget(cpu_seconds=1, wall_seconds=1),
            remaining_resample_budget=ResourceBudget(tokens=100, cpu_seconds=1, wall_seconds=11),
        )
        self.assertEqual(NoveltyDecision.REJECT_STOP, resolved.decision)
        self.assertIn("NOVELTY_REJECT_AND_STOP_UNAFFORDABLE", resolved.reason_codes)


if __name__ == "__main__":
    unittest.main()
