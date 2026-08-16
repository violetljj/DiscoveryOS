from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.benchmarks.mvp0_br import (
    BR_ARM_BUDGET,
    FrozenMvp0Autopsy,
    derive_budget_aware_stagnation_horizon,
    mvp0_br_controller_config,
)
from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget, ResourceUsage
from discoveryos.operators.action_controller import (
    AnytimeTraceRecorder,
    BranchSearchState,
    CandidateSearchState,
    DeterministicActionController,
    SearchAction,
    SearchState,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.search_loop import SearchLoopRunner


class Mvp0BudgetReachabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = mvp0_br_controller_config()
        self.controller = DeterministicActionController(self.config)

    def test_budget_aware_horizon_is_derived_from_the_frozen_envelope(self) -> None:
        local = self.config.cost_for(SearchAction.LOCAL_PATCH)
        structural = self.config.cost_for(SearchAction.STRUCTURAL_ESCAPE)
        assert local is not None and structural is not None
        self.assertEqual(
            1,
            derive_budget_aware_stagnation_horizon(
                BR_ARM_BUDGET,
                local.resource_floor,
                structural.resource_floor,
            ),
        )
        self.assertEqual(1, self.config.stagnation_generations)

    def test_all_frozen_actions_are_reachable_and_replay_deterministically(self) -> None:
        initial = self._state()
        local = self.controller.decide(initial)
        self.assertEqual(SearchAction.LOCAL_PATCH, local.action)
        self.assertEqual(50_000, local.budget_reserved.tokens)
        self.assertTrue(local.preflight_affordable)

        stop_state = self._state(step=1, local_remaining=0, structural_remaining=0)
        structural_state = self._state(step=1, stagnation=1, local_remaining=1, structural_remaining=1)
        replicate_state = self._state(step=1, replicates=1, uncertainty=0.1)
        promotion_state = self._state(step=1, promotion=True)
        second_local_state = self._state(step=1, structural_remaining=0)
        expected = {
            SearchAction.STOP: stop_state,
            SearchAction.STRUCTURAL_ESCAPE: structural_state,
            SearchAction.REPLICATE: replicate_state,
            SearchAction.PROMOTE_FIDELITY: promotion_state,
            SearchAction.LOCAL_PATCH: second_local_state,
        }
        for action, state in expected.items():
            with self.subTest(action=action.value):
                decision = self.controller.decide(state)
                self.assertEqual(action, decision.action)
                replayed, issues = self.controller.replay(decision, state)
                self.assertTrue(replayed, issues)

    def test_unaffordable_local_is_rejected_before_selection_without_candidate(self) -> None:
        state = self._state(remaining=ResourceBudget(tokens=49_999, cpu_seconds=300, wall_seconds=1_200))
        decision = self.controller.decide(state)
        self.assertEqual(SearchAction.STOP, decision.action)
        self.assertEqual(SearchAction.LOCAL_PATCH, decision.rejected_action)
        self.assertFalse(decision.preflight_affordable)
        self.assertIn("STOP_BUDGET_INSUFFICIENT", decision.reason_codes)
        self.assertIn("ACTION_REJECTED_PREFLIGHT_BUDGET:LOCAL_PATCH", decision.reason_codes)
        self.assertIsNone(decision.candidate_id)

    def test_reservation_reconciliation_is_trace_replayable(self) -> None:
        before = self._state()
        decision = self.controller.decide(before)
        usage = ResourceUsage(llm_input_tokens=10_000, llm_output_tokens=1_000, cpu_seconds=1, wall_seconds=20)
        after = replace(
            before,
            step=1,
            remaining_budget=ResourceBudget(tokens=49_000, cpu_seconds=299, wall_seconds=1_180),
            elapsed_usage=usage,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            ledger = EvidenceLedger(root / "ledger.sqlite3")
            record = AnytimeTraceRecorder(artifacts, ledger).record(
                decision=decision,
                state_before=before,
                state_after=after,
                actual_usage=usage,
            )
            payload = json.loads(next((artifacts.records / "search" / before.run_id / "anytime").glob("*.json")).read_text())
        self.assertEqual(decision.budget_reserved, record.budget_reserved)
        self.assertEqual(50_000, payload["budget_reserved"]["tokens"])
        self.assertEqual(25_000, payload["reserved_downstream_budget"]["tokens"])
        self.assertEqual(49_000, payload["budget_after"]["tokens"])

    def test_incumbent_monotonicity_rejects_every_regression_path(self) -> None:
        before = self._state()
        decision = self.controller.decide(before)
        usage = ResourceUsage(llm_input_tokens=1, wall_seconds=1)
        regressed = replace(
            before,
            step=1,
            incumbent_utility=0.5,
            remaining_budget=ResourceBudget(tokens=59_999, cpu_seconds=300, wall_seconds=1_199),
            elapsed_usage=usage,
        )
        for scenario in (
            "worse_candidate",
            "invalid_candidate",
            "budget_rejected_action",
            "failed_evaluation",
            "structural_candidate_failure",
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaisesRegex(ValueError, "cannot regress"):
                    AnytimeTraceRecorder(
                        ArtifactStore(root / "artifacts"),
                        EvidenceLedger(root / "ledger.sqlite3"),
                    ).record(
                        decision=decision,
                        state_before=before,
                        state_after=regressed,
                        actual_usage=usage,
                    )

    @staticmethod
    def _state(
        *,
        step: int = 0,
        stagnation: int = 0,
        local_remaining: int = 2,
        structural_remaining: int = 1,
        replicates: int = 2,
        uncertainty: float = 0.0,
        promotion: bool = False,
        remaining: ResourceBudget = BR_ARM_BUDGET,
    ) -> SearchState:
        candidate = CandidateSearchState(
            candidate_id="candidate-incumbent",
            branch_id="branch",
            fidelity=Fidelity.G1,
            latest_evidence_receipt_id="receipt",
            scheduling_utility=1.0,
            uncertainty=uncertainty,
            replicate_count=replicates,
            promotion_eligible=promotion,
            promotion_target=Fidelity.G2 if promotion else None,
        )
        branch = BranchSearchState(
            branch_id="branch",
            lineage_root_id="candidate-root",
            parent_candidate_id=candidate.candidate_id,
            algorithm_family="frozen-family",
            generations_since_improvement=stagnation,
            recent_improvements=(0.0,) if stagnation else (0.1,),
            recent_delta_similarity=1.0,
            lineage_receipt_ids=("receipt-root", "receipt"),
            failure_signatures=("LOCAL_BASIN_PLATEAU",) if stagnation else (),
            local_actions_remaining=local_remaining,
            structural_actions_remaining=structural_remaining,
        )
        return SearchState(
            run_id="mvp0-br-deterministic",
            step=step,
            incumbent_candidate_id=candidate.candidate_id,
            incumbent_utility=1.0,
            utility_metric_name="score",
            metric_direction=MetricDirection.MAXIMIZE,
            candidates=(candidate,),
            branches=(branch,),
            reusable_component_ids=(),
            remaining_budget=remaining,
        )


class FrozenMvp0AutopsyTests(unittest.TestCase):
    def test_local_frozen_records_reconstruct_without_mutation(self) -> None:
        workspace = Path("runs/search-value-mvp0-r1")
        manifest_path = workspace / "protocol-artifacts/records/search-value-mvp0-manifest.json"
        report_path = workspace / "result-artifacts/records/search-value-mvp0-report.json"
        if not manifest_path.exists() or not report_path.exists():
            self.skipTest("ignored frozen MVP-0 records are not present in this checkout")
        before = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (manifest_path, report_path))
        report = FrozenMvp0Autopsy(workspace).build()
        after = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (manifest_path, report_path))
        self.assertEqual(before, after)
        self.assertEqual([8, 8, 1], [row["attempted"] for row in report["action_marginal_value"]])
        self.assertEqual([8, 2, 0], [row["candidate_emitted"] for row in report["action_marginal_value"]])
        self.assertTrue(all(
            item["full_final_improvement"] == item["first_local_final_improvement"]
            for item in report["first_local_only"]["tasks"]
        ))


class BudgetRejectionEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_rejection_stops_before_executor_and_emits_no_candidate(self) -> None:
        state = Mvp0BudgetReachabilityTests._state(
            remaining=ResourceBudget(tokens=49_999, cpu_seconds=300, wall_seconds=1_200)
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = EvidenceLedger(Path(directory) / "ledger.sqlite3")

            class Projector:
                def build(self) -> SearchState:
                    return state

            class Executor:
                def __init__(self) -> None:
                    self.ledger = ledger
                    self.called = False

                async def execute(self, decision, before):
                    del decision, before
                    self.called = True
                    raise AssertionError("budget-rejected action reached executor")

            executor = Executor()
            result = await SearchLoopRunner(
                controller=DeterministicActionController(mvp0_br_controller_config()),
                projector=Projector(),
                executor=executor,
                trace=object(),
            ).run()
            with ledger.connect() as connection:
                events = [
                    row["event_type"]
                    for row in connection.execute("SELECT event_type FROM events ORDER BY sequence")
                ]
        self.assertFalse(executor.called)
        self.assertEqual(SearchAction.LOCAL_PATCH, result.stop_decision.rejected_action)
        self.assertEqual(
            ["ACTION_PLANNED", "ACTION_REJECTED_PREFLIGHT_BUDGET", "SEARCH_LOOP_STOPPED"],
            events,
        )
        self.assertFalse(any(event.startswith("CANDIDATE_") for event in events))


if __name__ == "__main__":
    unittest.main()
