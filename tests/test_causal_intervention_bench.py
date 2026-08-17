from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.benchmarks.causal_intervention_bench import (
    BranchTrace,
    FrozenDecisionState,
    InterventionPair,
    InterventionThresholds,
    _synthetic_pairs,
    evaluate_intervention_pairs,
    run_synthetic_cib,
    seal_synthetic_cib_protocol,
    synthetic_states,
)
from discoveryos.util import digest_json


class CausalInterventionBenchTests(unittest.TestCase):
    def test_pair_requires_independent_draws_and_frozen_actions(self) -> None:
        state = synthetic_states()[0]
        branch = BranchTrace(
            state_id=state.state_id,
            action_id=state.default_action_id,
            draw_id="same",
            proposal_semantics_digest=digest_json({"proposal": "a"}),
            behavioral_signature=(0.0,),
            immediate_fitness=0.0,
            descendant_best=(0.0, 0.0, 0.0),
            anytime_auc=0.0,
            token_cost=1,
            evaluator_cost=1,
        )
        with self.assertRaisesRegex(ValueError, "independent stochastic draws"):
            InterventionPair("pair", "NULL", state, branch, branch)

    def test_synthetic_fixture_establishes_sensitivity_without_opening_fresh_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sealed = seal_synthetic_cib_protocol(workspace)
            result = run_synthetic_cib(
                workspace, manifest_digest=sealed["manifest_digest"]
            )
            self.assertEqual("CAUSAL_INTERVENTION_BENCH_MECHANICS_READY", result["status"])
            self.assertTrue(result["analysis"]["bench_sensitivity_established"])
            self.assertEqual(
                "INTERVENTION_VALUE_ADMITTED",
                result["synthetic_fixture_intervention_verdict"],
            )
            self.assertFalse(result["real_mechanism_admitted"])
            self.assertEqual(
                "DO_NOT_OPEN_SI3_FRESH_BUDGET", result["si3_fresh_budget_decision"]
            )
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["evaluator_calls"])
            self.assertEqual(27, len(result["pair_receipts"]))

    def test_manifest_fails_closed_after_digest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sealed = seal_synthetic_cib_protocol(workspace)
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                run_synthetic_cib(workspace, manifest_digest="0" * 64)
            self.assertTrue(Path(sealed["manifest_path"]).is_file())

    def test_behavior_change_without_utility_is_not_admitted(self) -> None:
        thresholds = InterventionThresholds()
        pairs = list(_synthetic_pairs(synthetic_states(), thresholds))
        changed = []
        for pair in pairs:
            if pair.kind != "INTERVENTION":
                changed.append(pair)
                continue
            treatment = replace(
                pair.treatment,
                immediate_fitness=pair.control.immediate_fitness,
                descendant_best=pair.control.descendant_best,
                anytime_auc=pair.control.anytime_auc,
            )
            changed.append(replace(pair, treatment=treatment))
        result = evaluate_intervention_pairs(changed, thresholds=thresholds)
        self.assertGreaterEqual(
            result["intervention_behavior_changed_states"],
            thresholds.minimum_reproducible_states,
        )
        self.assertEqual(
            "BEHAVIOR_CHANGED_UTILITY_EQUIVALENT", result["intervention_verdict"]
        )

    def test_positive_control_failure_blocks_mechanism_admission(self) -> None:
        thresholds = InterventionThresholds()
        pairs = list(_synthetic_pairs(synthetic_states(), thresholds))
        changed = []
        for pair in pairs:
            if pair.kind != "POSITIVE":
                changed.append(pair)
                continue
            treatment = replace(
                pair.treatment,
                behavioral_signature=pair.control.behavioral_signature,
                immediate_fitness=pair.control.immediate_fitness,
                descendant_best=pair.control.descendant_best,
                anytime_auc=pair.control.anytime_auc,
            )
            changed.append(replace(pair, treatment=treatment))
        result = evaluate_intervention_pairs(changed, thresholds=thresholds)
        self.assertFalse(result["bench_sensitivity_established"])
        self.assertEqual("BENCH_SENSITIVITY_NOT_ESTABLISHED", result["intervention_verdict"])

    def test_state_contract_rejects_single_step_horizon(self) -> None:
        state = synthetic_states()[0]
        with self.assertRaisesRegex(ValueError, "beyond the immediate child"):
            FrozenDecisionState(**{**state.__dict__, "downstream_steps": 1})


if __name__ == "__main__":
    unittest.main()
