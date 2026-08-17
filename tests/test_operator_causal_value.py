from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.executable_mechanism_contract import (
    CONDITION_DIRECT,
    CONDITION_REPAIR,
    ImplementationDraw,
)
from discoveryos.benchmarks.operator_causal_value import (
    _applicability_witness,
    _development_tasks,
    _freeze_task,
    _load_bound_resource_authority,
    _one_sided_sign_p,
    _pair_effects,
    _pair_schedule,
    _portability,
    _validation_analysis,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


class OperatorCausalValueTests(unittest.TestCase):
    def test_predeclared_states_have_repair_headroom_and_expected_call_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            states = [_freeze_task(store, role, task) for role, task in _development_tasks()]
            witnesses = [_applicability_witness(store, state) for state in states]
        self.assertTrue(all(item["passed"] for item in witnesses))
        self.assertTrue(all(item["improved_probe_count"] > 0 for item in witnesses))
        schedule = [branch for pair in _pair_schedule(states) for branch in pair["branches"]]
        self.assertEqual(16, sum(item["phase"] == "CALIBRATION" for item in schedule))
        self.assertEqual(28, sum(item["phase"] == "VALIDATION" for item in schedule))

    def test_portability_requires_the_confirmed_runtime_signatures(self) -> None:
        manifest = {"resource_authority": {"derived_per_call_token_ceiling": 78_000}}
        separated = [self._draw("d", CONDITION_DIRECT, 0.5), self._draw("r", CONDITION_REPAIR, 0.6)]
        self.assertTrue(_portability(separated, manifest, expected=2)["passed"])
        unseparated = [self._draw("d", CONDITION_DIRECT, 0.5), self._draw("r", CONDITION_REPAIR, 0.6, separated=False)]
        result = _portability(unseparated, manifest, expected=2)
        self.assertFalse(result["passed"])
        self.assertFalse(result["runtime_signatures_separated"])

    def test_positive_operator_effect_passes_registered_gate_and_tie_fails(self) -> None:
        manifest, draws = self._validation_fixture(repair_advantage=True)
        portability = _portability(draws.values(), manifest, expected=28)
        effects = _pair_effects(manifest, draws, phase="VALIDATION")
        analysis, gate = _validation_analysis(
            manifest,
            {"frozen_margins": {"utility": 0.01, "anytime_auc": 0.01}},
            draws,
            effects,
            portability,
        )
        self.assertTrue(gate["passed"])
        self.assertEqual(6, analysis["positive_pairs_beyond_envelope"])
        tied_manifest, tied_draws = self._validation_fixture(repair_advantage=False)
        tied_portability = _portability(tied_draws.values(), tied_manifest, expected=28)
        tied_effects = _pair_effects(tied_manifest, tied_draws, phase="VALIDATION")
        _, tied_gate = _validation_analysis(
            tied_manifest,
            {"frozen_margins": {"utility": 0.01, "anytime_auc": 0.01}},
            tied_draws,
            tied_effects,
            tied_portability,
        )
        self.assertFalse(tied_gate["passed"])

    def test_one_sided_sign_test_is_exact(self) -> None:
        self.assertEqual(1.0 / 64.0, _one_sided_sign_p(6, 6))
        self.assertGreater(_one_sided_sign_p(4, 6), 0.10)

    def test_historical_resource_authority_does_not_require_current_head(self) -> None:
        class Provider:
            provider_name = "fixture"
            model = "fixture-model"
            provider_version = "fixture-version"
            settings_digest = "fixture-settings"
            output_schema = {"type": "object"}

        provider = Provider()
        provider_binding = {
            "name": provider.provider_name,
            "model": provider.model,
            "version": provider.provider_version,
            "settings_digest": provider.settings_digest,
            "output_schema_digest": digest_json(provider.output_schema),
        }
        payload = {
            "status": "SEALED_PRE_PROVIDER_CALL",
            "provider": provider_binding,
            "repository": {"head_commit": "historical-seal-commit"},
        }
        manifest = {**payload, "manifest_digest": digest_json(payload)}
        record = {
            "manifest_digest": manifest["manifest_digest"],
            "passed": True,
            "status": "EMC_RESOURCE_CALIBRATION_PASSED",
            "derived_scientific_per_call_token_ceiling": 78_000,
            "ceiling_rule": {"maximum_scientific_ceiling": 100_000},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = ArtifactStore(root / "protocol-artifacts").write_record(
                "emc-resource-calibration-r1-manifest.json", manifest
            )
            record_path = ArtifactStore(root / "result-artifacts").write_record(
                "emc-resource-calibration-r1-result.json", record
            )
            loaded = _load_bound_resource_authority(
                root,
                digest_bytes(record_path.read_bytes()),
                manifest["manifest_digest"],
                provider,
            )
        self.assertEqual(78_000, loaded["record"]["derived_scientific_per_call_token_ceiling"])

    def _validation_fixture(self, *, repair_advantage: bool):
        states = [
            {"state_id": "assignment", "role": "VALIDATION", "entrypoint": "assign_clients", "score_resolution": 0.003},
            {"state_id": "coverage", "role": "VALIDATION", "entrypoint": "choose_sets", "score_resolution": 0.005},
        ]
        witnesses = [
            {"state_id": "assignment", "baseline_score": 0.30, "reference_score": 0.80, "breakthrough_threshold": 0.75},
            {"state_id": "coverage", "baseline_score": 0.60, "reference_score": 0.95, "breakthrough_threshold": 0.90},
        ]
        pairs = _pair_schedule(states)
        manifest = {
            "states": states,
            "repair_applicability": witnesses,
            "pairs": pairs,
            "resource_authority": {"derived_per_call_token_ceiling": 78_000},
        }
        draws = {}
        for pair in pairs:
            if pair["kind"] == "INTERVENTION":
                if pair["state_id"] == "assignment":
                    direct = 0.50 + 0.01 * pair["replicate"]
                    repair = direct + (0.20 if repair_advantage else 0.0)
                else:
                    direct = 0.72 + 0.01 * pair["replicate"]
                    repair = direct + (0.15 if repair_advantage else 0.0)
            else:
                direct = repair = 0.50 if pair["state_id"] == "assignment" else 0.72
            for branch in pair["branches"]:
                score = direct if branch["side"] == "control" else repair
                draws[branch["draw_id"]] = self._draw(branch["draw_id"], branch["condition_id"], score)
        return manifest, draws

    @staticmethod
    def _draw(draw_id: str, condition: str, score: float, *, separated: bool = True) -> ImplementationDraw:
        if condition == CONDITION_DIRECT:
            signature = (1.0, 0.0, 0.0)
        else:
            signature = (1.0, 1.0, 0.0) if separated else (1.0, 0.0, 0.0)
        return ImplementationDraw(
            state_id="fixture",
            condition_id=condition,
            draw_id=draw_id,
            contract_digest="contract",
            evaluable=True,
            source_valid=True,
            static_contract_passed=True,
            runtime_contract_passed=True,
            invariant_canary_passed=True,
            counter_signature=signature,
            counters={},
            token_cost=1_000,
            wall_seconds=1.0,
            source_sha256=draw_id,
            source_artifact_digest=None,
            generation={},
            evaluation={"score": score, "valid": True},
            contract_evidence={},
        )


if __name__ == "__main__":
    unittest.main()
