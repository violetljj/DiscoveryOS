from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget
from discoveryos.domains.clearance_demo import initialize_demo
from discoveryos.harness import (
    ACTION_CONTROLLER,
    OPERATOR_REGISTRY,
    AuthorityOverrideError,
    HarnessEventSink,
    PluginActivation,
    PluginManifest,
    PluginSelection,
    ResearchContext,
    ResearchHarness,
    ResearchProfile,
    ServiceKey,
    algorithm_discovery_v0_profile,
    build_root_research_context,
    standard_research_plugins,
)
from discoveryos.harness.strategies import CONTRACT
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    BranchSearchState,
    CandidateSearchState,
    DeterministicActionController,
    SearchAction,
    SearchState,
)
from discoveryos.runtime.ledger import EvidenceLedger


class _Provider:
    provider_name = "test-provider"
    model = "test-model"
    settings_digest = "0" * 64

    def generate(self, request):
        raise AssertionError(f"provider must not be called while composing the harness: {request}")


class ResearchContextTests(unittest.TestCase):
    def test_authority_services_cannot_be_replaced_or_intercepted(self) -> None:
        authority = ServiceKey("authority", dict, authority=True)
        policy = ServiceKey("policy", str)
        value: dict[str, str] = {"owner": "kernel"}
        root = ResearchContext.root({authority: value, policy: "base"})
        child = root.extend({policy: "plugin"}, scope_id="child", owner="plugin")
        self.assertEqual("plugin", child.get(policy))
        self.assertIs(value, child.get(authority))
        with self.assertRaises(AuthorityOverrideError):
            child.extend({authority: {}}, scope_id="bad", owner="plugin")
        with self.assertRaises(AuthorityOverrideError):
            child.intercept(authority, lambda item: item, scope_id="bad", owner="plugin")

    def test_isolation_keeps_authority_and_only_explicit_exports(self) -> None:
        authority = ServiceKey("authority", str, authority=True)
        visible = ServiceKey("visible", str)
        hidden = ServiceKey("hidden", str)
        root = ResearchContext.root({authority: "frozen", visible: "yes", hidden: "no"})
        isolated = root.isolate(scope_id="isolated", exported=(visible,))
        self.assertEqual("frozen", isolated.get(authority))
        self.assertEqual("yes", isolated.get(visible))
        self.assertFalse(isolated.has(hidden))


class ResearchHarnessLifecycleTests(unittest.TestCase):
    def test_failed_boot_rolls_back_activated_plugins_in_reverse(self) -> None:
        service = ServiceKey("temporary", str)
        disposed: list[str] = []

        class First:
            manifest = PluginManifest("first", "1", provides=(service,))

            def activate(self, context, config):
                del context, config
                return PluginActivation({service: "ready"}, lambda: disposed.append("first"))

        class Broken:
            manifest = PluginManifest("broken", "1", requires=(service,))

            def activate(self, context, config):
                del context, config
                raise RuntimeError("boot failed")

        with tempfile.TemporaryDirectory() as directory:
            ledger = EvidenceLedger(Path(directory) / "ledger.sqlite3")
            profile = ResearchProfile(
                "rollback",
                (PluginSelection.create("first"), PluginSelection.create("broken")),
            )
            with self.assertRaisesRegex(RuntimeError, "boot failed"):
                ResearchHarness((First(), Broken())).boot(
                    profile,
                    ResearchContext.root({}),
                    HarnessEventSink(ledger),
                )
            self.assertEqual(["first"], disposed)
            with ledger.connect() as connection:
                event_types = tuple(
                    row["event_type"]
                    for row in connection.execute("SELECT event_type FROM events ORDER BY sequence")
                )
            self.assertEqual(
                (
                    "HARNESS_PROFILE_BOOTING",
                    "HARNESS_PLUGIN_ACTIVATED",
                    "HARNESS_PLUGIN_DISPOSED",
                    "HARNESS_PROFILE_FAILED",
                ),
                event_types,
            )


class ResearchHarnessStrategyTests(unittest.TestCase):
    def test_standard_profile_composes_three_strategies_without_replacing_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            demo = initialize_demo(Path(directory))
            base = self._controller()
            root, sink = build_root_research_context(
                contract=demo.contract,
                ledger=demo.ledger,
                artifacts=demo.artifacts,
                evaluator=object(),
                patch_provider=_Provider(),
                base_controller=base,
            )
            session = ResearchHarness(standard_research_plugins()).boot(
                algorithm_discovery_v0_profile(),
                root,
                sink,
            )
            try:
                registry = session.context.get(OPERATOR_REGISTRY)
                self.assertEqual(
                    {
                        "direct_llm_research_v1",
                        "ada_lineage_refinement_v1",
                        "evox_meta_strategy_rewrite_v1",
                    },
                    {operator_id for operator_id, _ in registry.operators},
                )
                self.assertIs(demo.contract, session.context.get(CONTRACT))
                self.assertIsInstance(session.context.get(ACTION_CONTROLLER), DeterministicActionController)
            finally:
                session.close()

    def test_router_bootstraps_direct_then_cross_seeds_evox_to_ada(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            demo = initialize_demo(Path(directory))
            root, sink = build_root_research_context(
                contract=demo.contract,
                ledger=demo.ledger,
                artifacts=demo.artifacts,
                evaluator=object(),
                patch_provider=_Provider(),
                base_controller=self._controller(),
            )
            with ResearchHarness(standard_research_plugins()).boot(
                algorithm_discovery_v0_profile(), root, sink
            ) as session:
                controller = session.context.get(ACTION_CONTROLLER)
                first = controller.decide(self._state(step=0, strategy_id="baseline"))
                self.assertEqual("direct_llm_strategy_v1", first.strategy_id)
                self.assertEqual("direct_llm_research_v1", first.operator_id)

                second_state = self._state(step=1, strategy_id="evox_meta_strategy_v1")
                second = controller.decide(second_state)
                self.assertEqual(SearchAction.LOCAL_PATCH, second.action)
                self.assertEqual("ada_lineage_strategy_v1", second.strategy_id)
                self.assertIn("CROSS_SEED_EVOX_TO_ADA", second.reason_codes)
                self.assertTrue(controller.replay(second, second_state)[0])

    def test_router_sends_stagnant_ada_lineage_to_evox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            demo = initialize_demo(Path(directory))
            root, sink = build_root_research_context(
                contract=demo.contract,
                ledger=demo.ledger,
                artifacts=demo.artifacts,
                evaluator=object(),
                patch_provider=_Provider(),
                base_controller=self._controller(),
            )
            with ResearchHarness(standard_research_plugins()).boot(
                algorithm_discovery_v0_profile(), root, sink
            ) as session:
                controller = session.context.get(ACTION_CONTROLLER)
                state = self._state(step=3, strategy_id="ada_lineage_strategy_v1", stagnant=True)
                decision = controller.decide(state)
                self.assertEqual(SearchAction.STRUCTURAL_ESCAPE, decision.action)
                self.assertEqual("evox_meta_strategy_v1", decision.strategy_id)
                self.assertIn("CROSS_SEED_LINEAGE_TO_EVOX", decision.reason_codes)
                self.assertTrue(controller.replay(decision, state)[0])

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
    def _state(*, step: int, strategy_id: str, stagnant: bool = False) -> SearchState:
        candidate = CandidateSearchState(
            candidate_id="candidate-current",
            branch_id="branch-1",
            fidelity=Fidelity.G1,
            latest_evidence_receipt_id="receipt-current",
            scheduling_utility=1.0,
            uncertainty=0.0,
            replicate_count=2,
            strategy_id=strategy_id,
        )
        branch = BranchSearchState(
            branch_id="branch-1",
            lineage_root_id="candidate-root",
            parent_candidate_id=candidate.candidate_id,
            algorithm_family="current-family",
            generations_since_improvement=2 if stagnant else 0,
            recent_improvements=(0.0, 0.0) if stagnant else (0.1,),
            recent_delta_similarity=0.9 if stagnant else 0.1,
            lineage_receipt_ids=("receipt-root", "receipt-current"),
            failure_signatures=("LOCAL_BASIN_PLATEAU",) if stagnant else (),
            local_actions_remaining=3,
            structural_actions_remaining=2,
        )
        return SearchState(
            run_id="harness-routing",
            step=step,
            incumbent_candidate_id=candidate.candidate_id,
            incumbent_utility=1.0,
            utility_metric_name="score",
            metric_direction=MetricDirection.MAXIMIZE,
            candidates=(candidate,),
            branches=(branch,),
            reusable_component_ids=(),
            remaining_budget=ResourceBudget(tokens=100, cpu_seconds=10, wall_seconds=20),
        )


if __name__ == "__main__":
    unittest.main()
