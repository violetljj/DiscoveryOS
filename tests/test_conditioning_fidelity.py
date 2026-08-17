from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.benchmarks.conditioning_fidelity import (
    CHANNELS,
    ConditioningPair,
    ConditioningThresholds,
    _synthetic_pairs,
    evaluate_conditioning_pairs,
    parent_cib_r1_settlement,
    run_synthetic_gcf,
    seal_synthetic_gcf_protocol,
    synthetic_conditioning_states,
)
from discoveryos.util import digest_json


class ConditioningFidelityTests(unittest.TestCase):
    def test_parent_settlement_is_narrow_digest_bound_and_budget_closed(self) -> None:
        settlement = parent_cib_r1_settlement()
        payload = {key: value for key, value in settlement.items() if key != "settlement_digest"}
        self.assertEqual(digest_json(payload), settlement["settlement_digest"])
        self.assertEqual("CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME", settlement["status"])
        self.assertEqual("CLOSED", settlement["budget_decision"])
        self.assertIn("NOT_A_UNIVERSAL_ZERO_EFFECT_CLAIM", settlement["claim_ceiling"])
        self.assertEqual(4, len(settlement["reopen_condition"]["all_required"]))

    def test_synthetic_fixture_calibrates_stage_semantic_and_value_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sealed = seal_synthetic_gcf_protocol(workspace)
            result = run_synthetic_gcf(workspace, manifest_digest=sealed["manifest_digest"])
            self.assertEqual("GENERATOR_CONDITIONING_FIDELITY_BENCH_MECHANICS_READY", result["status"])
            self.assertTrue(result["analysis"]["gcf_0_calibration_passed"])
            self.assertEqual([], result["real_channels_admitted"])
            self.assertFalse(result["fresh_downstream_trial_authorized"])
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["fresh_task_budget_consumed"])
            self.assertEqual(36, len(result["pair_receipts"]))

            channels = {item["channel"]: item for item in result["analysis"]["channels"]}
            self.assertEqual(set(CHANNELS), set(channels))
            self.assertFalse(channels["PARENT_SOURCE"]["gcf_2_semantic_transmission_admitted"])
            self.assertTrue(channels["FAILURE_EVIDENCE"]["gcf_2_semantic_transmission_admitted"])
            self.assertFalse(channels["FAILURE_EVIDENCE"]["gcf_3_downstream_value_trial_eligible"])
            self.assertTrue(channels["MECHANISM_BRIEF"]["gcf_3_downstream_value_trial_eligible"])

    def test_manifest_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            seal_synthetic_gcf_protocol(workspace)
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                run_synthetic_gcf(workspace, manifest_digest="0" * 64)

    def test_pair_requires_independent_draws(self) -> None:
        thresholds = ConditioningThresholds()
        pair = next(iter(_synthetic_pairs(synthetic_conditioning_states(), thresholds)))
        with self.assertRaisesRegex(ValueError, "independent stochastic draws"):
            ConditioningPair(
                pair_id="invalid",
                kind=pair.kind,
                state=pair.state,
                control=pair.control,
                treatment=replace(pair.treatment, draw_id=pair.control.draw_id),
            )

    def test_failed_positive_controls_block_calibration(self) -> None:
        thresholds = ConditioningThresholds()
        pairs = []
        for pair in _synthetic_pairs(synthetic_conditioning_states(), thresholds):
            if pair.kind == "POSITIVE":
                pair = replace(
                    pair,
                    treatment=replace(
                        pair.treatment,
                        stage_signatures=pair.control.stage_signatures,
                        behavior_signature=pair.control.behavior_signature,
                        utility=pair.control.utility,
                    ),
                )
            pairs.append(pair)
        result = evaluate_conditioning_pairs(pairs, thresholds=thresholds)
        self.assertFalse(result["gcf_0_calibration_passed"])
        self.assertTrue(all(not item["gcf_2_semantic_transmission_admitted"] for item in result["channels"]))


if __name__ == "__main__":
    unittest.main()
