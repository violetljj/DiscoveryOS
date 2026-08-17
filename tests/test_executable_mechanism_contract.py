from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.executable_mechanism_contract import (
    CONDITION_DIRECT,
    CONDITION_REPAIR,
    IMPLEMENTATION_SCHEMA,
    MANIFEST_RECORD,
    PREFLIGHT_RECORD,
    SENSITIVITY_RECORD,
    ImplementationDraw,
    _analyze_draws,
    _evaluate_contract,
    _freeze_task,
    _gate_verdict,
    _implementation_prompt_template,
    _sensitivity_sources,
    compile_executable_contract,
    run_implementation_calibration,
    run_provider_preflight,
    seal_emc_protocol,
)
from discoveryos.benchmarks.si2_tasks import _assignment_task
from discoveryos.runtime.artifacts import ArtifactStore


class _Provider:
    provider_name = "fixture"
    model = "fixture-model"
    provider_version = "fixture-1"
    output_schema = IMPLEMENTATION_SCHEMA
    settings_digest = "fixture-settings"

    def generate(self, request):  # pragma: no cover - blocked-path guard
        raise AssertionError(f"unexpected provider call: {request.generation_id}")


def _draw(condition: str, replicate: int, **overrides) -> ImplementationDraw:
    counters = {"emc_construct": 2, "emc_improve": int(condition == CONDITION_REPAIR) * 2, "inherited_solver": 0}
    values = {
        "state_id": "state",
        "condition_id": condition,
        "draw_id": f"{condition}:{replicate}",
        "contract_digest": "contract",
        "evaluable": True,
        "source_valid": True,
        "static_contract_passed": True,
        "runtime_contract_passed": True,
        "invariant_canary_passed": True,
        "counter_signature": (1.0, float(condition == CONDITION_REPAIR), 0.0),
        "counters": counters,
        "token_cost": 10,
        "wall_seconds": 0.1,
        "source_sha256": "source",
        "source_artifact_digest": "artifact",
        "generation": {},
        "evaluation": {"score": 0.5, "valid": True},
        "contract_evidence": {},
    }
    values.update(overrides)
    return ImplementationDraw(**values)


class ExecutableMechanismContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = _Provider()

    def test_compiler_is_deterministic_and_conditions_have_different_obligations(self) -> None:
        direct = compile_executable_contract(CONDITION_DIRECT, "assign_clients")
        repair = compile_executable_contract(CONDITION_REPAIR, "assign_clients")
        self.assertEqual(direct, compile_executable_contract(CONDITION_DIRECT, "assign_clients"))
        self.assertIn("emc_improve", direct["forbidden_functions"])
        self.assertIn("emc_improve", repair["required_functions"])
        self.assertNotEqual(direct["contract_digest"], repair["contract_digest"])

    def test_independent_harness_accepts_positive_and_rejects_negative_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            task = _assignment_task("emc_fixture", (1, 2, 3, 4, 5, 6))
            state = _freeze_task(store, "CALIBRATION", task)
            for fixture_id, condition, expected, source in _sensitivity_sources(state["entrypoint"]):
                with self.subTest(fixture_id=fixture_id):
                    evidence = _evaluate_contract(Path(temporary), state, source, compile_executable_contract(condition, state["entrypoint"]))
                    self.assertEqual(expected, evidence["passed"])

    def test_seal_freezes_cheap_first_order_and_candidate_counter_non_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = seal_emc_protocol(Path(temporary), implementation_provider=self.provider)
            manifest = json.loads((Path(temporary) / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8"))
            self.assertEqual(13, sealed["maximum_model_calls"])
            self.assertEqual("E0_INSTRUMENTATION_SENSITIVITY_NO_MODEL", manifest["cheap_first_gates"][0])
            self.assertFalse(manifest["isolation"]["candidate_self_reported_counters_authoritative"])
            self.assertEqual(0, manifest["model_calls_before_seal"])

    def test_failed_sensitivity_blocks_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            sealed = seal_emc_protocol(workspace, implementation_provider=self.provider)
            ArtifactStore(workspace / "result-artifacts").write_record(
                SENSITIVITY_RECORD, {"manifest_digest": sealed["manifest_digest"], "passed": False}
            )
            with self.assertRaisesRegex(RuntimeError, "instrumentation sensitivity"):
                run_provider_preflight(workspace, manifest_digest=sealed["manifest_digest"], implementation_provider=self.provider)

    def test_failed_preflight_blocks_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            sealed = seal_emc_protocol(workspace, implementation_provider=self.provider)
            ArtifactStore(workspace / "result-artifacts").write_record(
                PREFLIGHT_RECORD, {"manifest_digest": sealed["manifest_digest"], "passed": False}
            )
            with self.assertRaisesRegex(RuntimeError, "provider preflight"):
                run_implementation_calibration(workspace, manifest_digest=sealed["manifest_digest"], implementation_provider=self.provider)

    def test_gate_requires_all_contract_layers_and_separated_signatures(self) -> None:
        draws = [_draw(condition, replicate) for condition in (CONDITION_DIRECT, CONDITION_REPAIR) for replicate in range(3)]
        analysis = _analyze_draws(draws)
        self.assertTrue(analysis["between_condition_counter_signatures_separated"])
        self.assertEqual((True, "EMC_R1_CALIBRATION_PASSED"), _gate_verdict(draws, analysis, "CALIBRATION"))
        broken = [*draws[:-1], _draw(CONDITION_REPAIR, 2, runtime_contract_passed=False)]
        broken_analysis = _analyze_draws(broken)
        self.assertEqual("EMC_R1_CALIBRATION_RUNTIME_CONTRACT_FAILED", _gate_verdict(broken, broken_analysis, "CALIBRATION")[1])

    def test_prompt_hides_condition_and_instrumentation(self) -> None:
        template = _implementation_prompt_template()
        self.assertIn("{mechanism_object}", template)
        self.assertIn("{executable_contract}", template)
        self.assertNotIn("condition_id", template)
        self.assertNotIn("profile_probe", template)


if __name__ == "__main__":
    unittest.main()
