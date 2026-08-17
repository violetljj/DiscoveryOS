from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.contracts.models import (
    DataRole,
    EvidenceRecord,
    EvidenceValidity,
    Fidelity,
    MetricDirection,
    ResourceBudget,
    ResourceUsage,
)
from discoveryos.harness.evox_strategy import (
    EvoXParentMode,
    EvoXStrategyStateMachine,
    EvoXTerminalTransition,
    EvoXVariationMode,
)
from discoveryos.operators.action_controller import (
    BranchSearchState,
    CandidateSearchState,
    SearchAction,
    SearchDecision,
    SearchState,
)
from discoveryos.runtime.ledger import EvidenceLedger


class EvoXStrategyStateMachineTests(unittest.TestCase):
    def test_deploy_score_switch_and_rollback_change_search_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = EvidenceLedger(Path(directory) / "ledger.sqlite3")
            machine = EvoXStrategyStateMachine(ledger)
            state = self._state(step=0)

            first_plan = machine.plan(state, "candidate-current")
            self.assertEqual(EvoXParentMode.CURRENT_PARENT, first_plan.strategy.parent_mode)
            self.assertEqual(
                EvoXVariationMode.COMPONENT_TRANSFER,
                first_plan.strategy.variation_mode,
            )
            first_decision = self._decision(state, first_plan)
            machine.deploy(state, first_decision)
            guidance = machine.generation_guidance(state, first_decision)
            self.assertIn("EVOX_STRATEGY_DEPLOYMENT_V1", guidance[0])
            self.assertIn("EVOX_VARIATION_MODE:COMPONENT_TRANSFER", guidance[1])
            with self.assertRaisesRegex(ValueError, "lacks terminal settlement"):
                machine.plan(state, "candidate-current")

            switched = machine.settle(
                state=state,
                decision=first_decision,
                result_candidate_id="candidate-result",
                evidence=self._evidence("candidate-result", score=1.0),
                metric_name="score",
                metric_direction=MetricDirection.MAXIMIZE,
            )
            self.assertEqual(EvoXTerminalTransition.SWITCH, switched.transition)

            next_state = self._state(step=1)
            second_plan = machine.plan(next_state, "candidate-current")
            self.assertEqual(EvoXParentMode.INCUMBENT, second_plan.strategy.parent_mode)
            self.assertEqual("candidate-incumbent", second_plan.selected_parent_id)
            self.assertEqual(
                EvoXVariationMode.CROSS_LINEAGE_RECOMBINE,
                second_plan.strategy.variation_mode,
            )
            second_decision = self._decision(next_state, second_plan)
            machine.deploy(next_state, second_decision)
            rolled_back = machine.settle(
                state=next_state,
                decision=second_decision,
                result_candidate_id=None,
                evidence=None,
                metric_name="score",
                metric_direction=MetricDirection.MAXIMIZE,
            )
            self.assertEqual(EvoXTerminalTransition.ROLLBACK, rolled_back.transition)

            third_plan = machine.plan(self._state(step=2), "candidate-current")
            self.assertEqual(first_plan.strategy.strategy_spec_id, third_plan.strategy.strategy_spec_id)
            self.assertEqual("candidate-current", third_plan.selected_parent_id)

            with ledger.connect() as connection:
                edge_types = {
                    row["edge_type"]
                    for row in connection.execute("SELECT edge_type FROM graph_edges")
                }
            self.assertTrue(
                {
                    "EVOX_STRATEGY_DEPLOYED",
                    "EVOX_STRATEGY_OBSERVED",
                    "EVOX_STRATEGY_SCORED",
                    "EVOX_STRATEGY_SWITCH",
                    "EVOX_STRATEGY_ROLLBACK",
                    "EVOX_ACTIVE_STRATEGY",
                }.issubset(edge_types)
            )

    def test_positive_observation_retains_deployed_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            machine = EvoXStrategyStateMachine(
                EvidenceLedger(Path(directory) / "ledger.sqlite3")
            )
            state = self._state(step=0)
            plan = machine.plan(state, "candidate-current")
            decision = self._decision(state, plan)
            machine.deploy(state, decision)
            retained = machine.settle(
                state=state,
                decision=decision,
                result_candidate_id="candidate-result",
                evidence=self._evidence("candidate-result", score=1.25),
                metric_name="score",
                metric_direction=MetricDirection.MAXIMIZE,
            )
            self.assertEqual(EvoXTerminalTransition.RETAIN, retained.transition)
            self.assertEqual(plan.strategy.strategy_spec_id, retained.active_strategy_spec_id)

    def test_generation_rejects_tampered_strategy_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            machine = EvoXStrategyStateMachine(
                EvidenceLedger(Path(directory) / "ledger.sqlite3")
            )
            state = self._state(step=0)
            plan = machine.plan(state, "candidate-current")
            decision = self._decision(state, plan)
            machine.deploy(state, decision)
            tampered = replace(
                decision,
                reason_codes=tuple(
                    code
                    for code in decision.reason_codes
                    if not code.startswith("EVOX_VARIATION_MODE:")
                ),
            )
            with self.assertRaisesRegex(ValueError, "not bound"):
                machine.generation_guidance(state, tampered)

    @staticmethod
    def _decision(state: SearchState, plan) -> SearchDecision:
        return SearchDecision.create(
            state=state,
            controller_digest="controller-v1",
            action=SearchAction.STRUCTURAL_ESCAPE,
            candidate_id=plan.selected_parent_id,
            branch_id="branch-1",
            operator_id="structural_rewrite_basin_jump_v1",
            strategy_id="evox_meta_strategy_v1",
            fidelity=Fidelity.G1,
            reason_codes=plan.reason_codes,
            resource_floor=ResourceBudget(tokens=1),
        )

    @staticmethod
    def _state(*, step: int) -> SearchState:
        candidates = (
            CandidateSearchState(
                candidate_id="candidate-current",
                branch_id="branch-1",
                fidelity=Fidelity.G1,
                latest_evidence_receipt_id="receipt-current",
                scheduling_utility=0.9,
                replicate_count=2,
                strategy_id="ada_lineage_strategy_v1",
            ),
            CandidateSearchState(
                candidate_id="candidate-incumbent",
                branch_id="branch-1",
                fidelity=Fidelity.G1,
                latest_evidence_receipt_id="receipt-incumbent",
                scheduling_utility=1.0,
                replicate_count=2,
                strategy_id="evox_meta_strategy_v1",
            ),
        )
        return SearchState(
            run_id="evox-state-machine",
            step=step,
            incumbent_candidate_id="candidate-incumbent",
            incumbent_utility=1.0,
            utility_metric_name="score",
            metric_direction=MetricDirection.MAXIMIZE,
            candidates=candidates,
            branches=(
                BranchSearchState(
                    branch_id="branch-1",
                    lineage_root_id="candidate-root",
                    parent_candidate_id="candidate-current",
                    algorithm_family="current-family",
                    generations_since_improvement=2,
                    recent_improvements=(0.0, 0.0),
                    recent_delta_similarity=0.9,
                    lineage_receipt_ids=("receipt-root", "receipt-current"),
                    failure_signatures=("LOCAL_BASIN_PLATEAU",),
                    local_actions_remaining=1,
                    structural_actions_remaining=2,
                ),
            ),
            reusable_component_ids=("component-1",),
            remaining_budget=ResourceBudget(tokens=100, cpu_seconds=10, wall_seconds=20),
        )

    @staticmethod
    def _evidence(candidate_id: str, *, score: float) -> EvidenceRecord:
        return EvidenceRecord(
            receipt_id=f"receipt-{candidate_id}-{score}",
            experiment_id=f"experiment-{candidate_id}",
            candidate_id=candidate_id,
            contract_digest="contract-v1",
            evaluator_id="evaluator-v1",
            evaluator_digest="evaluator-digest-v1",
            data_digest=None,
            fidelity=Fidelity.G1,
            split_id="dev",
            split_role=DataRole.DEVELOPMENT,
            metrics=(("score", score),),
            validity=EvidenceValidity.VALID,
            failure_signature=None,
            failure_kind=None,
            artifacts=(),
            resource_usage=ResourceUsage(),
            evaluation_output_digest="output-digest-v1",
            created_at="2026-08-18T00:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
