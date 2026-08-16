from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget, ResourceUsage
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    AnytimeTraceRecorder,
    BranchSearchState,
    CandidateSearchState,
    DeterministicActionController,
    SearchAction,
    SearchState,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger


class DeterministicActionControllerTests(unittest.TestCase):
    def test_mechanics_trajectory_is_local_local_structural_replicate_promote(self) -> None:
        controller = self._controller()
        states = self._trajectory()
        decisions = tuple(controller.decide(state) for state in states)
        self.assertEqual(
            (
                SearchAction.LOCAL_PATCH,
                SearchAction.LOCAL_PATCH,
                SearchAction.STRUCTURAL_ESCAPE,
                SearchAction.REPLICATE,
                SearchAction.PROMOTE_FIDELITY,
            ),
            tuple(decision.action for decision in decisions),
        )
        self.assertEqual(
            ("component-abs-transform",),
            decisions[2].reusable_component_ids,
        )
        self.assertEqual(Fidelity.G2, decisions[-1].fidelity)
        for decision, state in zip(decisions, states):
            replayed, issues = controller.replay(decision, state)
            self.assertTrue(replayed, issues)
            self.assertEqual(state.digest, decision.state_digest)

    def test_anytime_trace_binds_action_budget_and_incumbent_refresh(self) -> None:
        controller = self._controller()
        before = self._trajectory()[-1]
        decision = controller.decide(before)
        actual = ResourceUsage(cpu_seconds=2, wall_seconds=2)
        promoted = replace(
            before.candidates[0],
            fidelity=Fidelity.G2,
            score=0.25,
            promotion_eligible=False,
            promotion_target=None,
        )
        after = replace(
            before,
            step=before.step + 1,
            candidates=(promoted,),
            incumbent_score=0.25,
            remaining_budget=ResourceBudget(tokens=70, cpu_seconds=8, wall_seconds=15),
            elapsed_usage=actual,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            ledger = EvidenceLedger(root / "ledger.sqlite3")
            record = AnytimeTraceRecorder(artifacts, ledger).record(
                decision=decision,
                state_before=before,
                state_after=after,
                actual_usage=actual,
            )
            self.assertEqual(SearchAction.PROMOTE_FIDELITY, record.selected_action)
            self.assertEqual(0.05, record.best_metric_before)
            self.assertEqual(0.25, record.best_metric_after)
            self.assertEqual(ResourceBudget(tokens=70, cpu_seconds=8, wall_seconds=15), record.budget_after)
            trace_path = next((artifacts.records / "search" / before.run_id / "anytime").glob("*.json"))
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual(decision.decision_id, payload["decision_id"])
            self.assertEqual("PROMOTE_FIDELITY", payload["selected_action"])
            with ledger.connect() as connection:
                event = connection.execute(
                    "SELECT event_type, payload FROM events ORDER BY sequence"
                ).fetchone()
            self.assertEqual("SEARCH_ACTION_SETTLED", event["event_type"])
            self.assertEqual(record.trace_id, json.loads(event["payload"])["trace_id"])

    def test_stagnation_without_lineage_evidence_fails_closed(self) -> None:
        controller = self._controller()
        state = self._trajectory()[2]
        branch = replace(state.branches[0], lineage_receipt_ids=())
        decision = controller.decide(replace(state, branches=(branch,)))
        self.assertEqual(SearchAction.STOP, decision.action)
        self.assertEqual(("STRUCTURAL_EVIDENCE_REQUIRED",), decision.reason_codes)

    @staticmethod
    def _controller() -> DeterministicActionController:
        return DeterministicActionController(
            ActionControllerConfig(
                stagnation_generations=2,
                improvement_epsilon=0.01,
                uncertainty_threshold=0.05,
                incumbent_proximity=0.05,
                minimum_replicates=2,
                structural_similarity_threshold=0.8,
                costs=(
                    ActionCost(SearchAction.LOCAL_PATCH, ResourceBudget(tokens=10, wall_seconds=1)),
                    ActionCost(SearchAction.STRUCTURAL_ESCAPE, ResourceBudget(tokens=20, wall_seconds=2)),
                    ActionCost(SearchAction.REPLICATE, ResourceBudget(cpu_seconds=1, wall_seconds=1)),
                    ActionCost(SearchAction.PROMOTE_FIDELITY, ResourceBudget(cpu_seconds=2, wall_seconds=2)),
                ),
            )
        )

    @staticmethod
    def _trajectory() -> tuple[SearchState, ...]:
        budget = ResourceBudget(tokens=70, cpu_seconds=10, wall_seconds=17)
        local_candidate = CandidateSearchState(
            candidate_id="candidate-local",
            branch_id="branch-1",
            fidelity=Fidelity.G1,
            latest_evidence_receipt_id="receipt-local",
            score=0.05,
            uncertainty=0.01,
            replicate_count=2,
        )
        branch = BranchSearchState(
            branch_id="branch-1",
            lineage_root_id="candidate-baseline",
            parent_candidate_id=local_candidate.candidate_id,
            algorithm_family="linear-offset",
            generations_since_improvement=0,
            recent_improvements=(0.10,),
            recent_delta_similarity=0.2,
            lineage_receipt_ids=("receipt-local", "receipt-baseline"),
            failure_signatures=(),
            local_actions_remaining=2,
            structural_actions_remaining=1,
        )

        def state(step: int, candidate: CandidateSearchState, current_branch: BranchSearchState) -> SearchState:
            return SearchState(
                run_id="search-value-mechanics",
                step=step,
                incumbent_candidate_id=candidate.candidate_id,
                incumbent_score=candidate.score or 0.0,
                metric_direction=MetricDirection.MAXIMIZE,
                candidates=(candidate,),
                branches=(current_branch,),
                reusable_component_ids=("component-abs-transform",),
                remaining_budget=budget,
            )

        first = state(0, local_candidate, branch)
        second_branch = replace(
            branch,
            generations_since_improvement=1,
            recent_improvements=(0.10, 0.02),
            local_actions_remaining=1,
        )
        second = state(1, local_candidate, second_branch)
        stagnant_branch = replace(
            second_branch,
            generations_since_improvement=2,
            recent_improvements=(0.10, 0.02, 0.0),
            recent_delta_similarity=0.9,
            failure_signatures=("LOCAL_BASIN_PLATEAU",),
        )
        third = state(2, local_candidate, stagnant_branch)
        structural_candidate = CandidateSearchState(
            candidate_id="candidate-structural",
            branch_id="branch-1",
            fidelity=Fidelity.G1,
            latest_evidence_receipt_id="receipt-structural",
            score=0.05,
            uncertainty=0.10,
            replicate_count=1,
        )
        structural_branch = replace(
            stagnant_branch,
            parent_candidate_id=structural_candidate.candidate_id,
            algorithm_family="piecewise-memoized",
            generations_since_improvement=0,
            recent_improvements=(0.0,),
            recent_delta_similarity=0.0,
            structural_actions_remaining=0,
        )
        fourth = state(3, structural_candidate, structural_branch)
        replicated_candidate = replace(
            structural_candidate,
            uncertainty=0.01,
            replicate_count=2,
            promotion_eligible=True,
            promotion_target=Fidelity.G2,
        )
        fifth = state(4, replicated_candidate, structural_branch)
        return first, second, third, fourth, fifth


if __name__ == "__main__":
    unittest.main()
