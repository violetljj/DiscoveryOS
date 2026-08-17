from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.structured_mechanism_mediation import (
    CONDITION_A,
    CONDITION_B,
    IMPLEMENTATION_SCHEMA,
    MANIFEST_RECORD,
    MECHANISM_OBJECT_SCHEMA,
    PROPOSAL_RECORD,
    ImplementationDraw,
    MechanismObject,
    ProposalDraw,
    _analyze_implementations,
    _analyze_proposals,
    _implementation_prompt_template,
    run_structured_implementation_calibration,
    seal_structured_mediation_protocol,
)
from discoveryos.runtime.artifacts import ArtifactStore


class _Provider:
    provider_name = "fixture"
    model = "fixture-model"
    provider_version = "fixture-1"

    def __init__(self, schema):
        self.output_schema = schema
        self.settings_digest = f"settings-{len(json.dumps(schema))}"

    def generate(self, request):  # pragma: no cover - blocked-path guard
        raise AssertionError(f"unexpected provider call: {request.generation_id}")


def _payload(condition: str) -> dict:
    if condition == CONDITION_A:
        family, construction, loop, move, termination = (
            "constructive_greedy", "single_pass", "forbidden", "none", "construction_complete"
        )
    else:
        family, construction, loop, move, termination = (
            "iterative_local_improvement",
            "seed_then_improve",
            "required",
            "swap_or_reassign",
            "local_optimum_or_bound",
        )
    return {
        "mechanism": {
            "mechanism_family": family,
            "hypothesis": "the requested control flow changes the search trajectory",
            "algorithmic_change": {"replace": "the inherited policy", "with": family},
            "expected_control_flow": {
                "construction_mode": construction,
                "improvement_loop": loop,
                "neighborhood_move": move,
                "termination": termination,
            },
            "forbidden_fallbacks": ["inherited_solver"],
            "invariants": ["api_preserved", "feasibility_preserved", "inputs_immutable"],
            "expected_behavioral_signatures": ["changed decision sequence"],
            "failure_semantics": ["fail closed on infeasible output"],
        }
    }


class StructuredMechanismMediationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal_provider = _Provider(MECHANISM_OBJECT_SCHEMA)
        self.implementation_provider = _Provider(IMPLEMENTATION_SCHEMA)

    def test_mechanism_object_enforces_categorical_condition_contract(self) -> None:
        greedy = MechanismObject.from_payload(_payload(CONDITION_A), expected_condition=CONDITION_A)
        local = MechanismObject.from_payload(_payload(CONDITION_B), expected_condition=CONDITION_B)
        self.assertNotEqual(greedy.categorical_signature, local.categorical_signature)
        self.assertEqual(greedy.digest, MechanismObject.from_payload(_payload(CONDITION_A), expected_condition=CONDITION_A).digest)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            MechanismObject.from_payload(_payload(CONDITION_A), expected_condition=CONDITION_B)

    def test_seal_freezes_cheap_first_gate_and_mediation_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = seal_structured_mediation_protocol(
                Path(temporary),
                proposal_provider=self.proposal_provider,
                implementation_provider=self.implementation_provider,
            )
            self.assertEqual(12, result["proposal_calls_before_gate"])
            self.assertEqual(24, result["maximum_total_model_calls"])
            manifest = json.loads(
                (Path(temporary) / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["task_question", "base_source", "canonical_mechanism_object"],
                manifest["mediation_isolation"]["implementation_sees"],
            )
            self.assertIn("natural_language_mechanism_brief", manifest["mediation_isolation"]["implementation_forbidden_context"])
            self.assertEqual(0, manifest["model_calls_before_seal"])

    def test_proposal_analysis_compares_between_against_within_condition(self) -> None:
        states = [{"state_id": "s1", "task_category": "one"}, {"state_id": "s2", "task_category": "two"}]
        manifest = {"states": states}
        draws = {}
        signatures = {CONDITION_A: (0.0,) * 5, CONDITION_B: (1.0,) * 5}
        for state in states:
            for condition in (CONDITION_A, CONDITION_B):
                for replicate in range(3):
                    draw_id = f"{state['state_id']}:{condition}:{replicate}"
                    draws[draw_id] = ProposalDraw(
                        state_id=state["state_id"],
                        condition_id=condition,
                        draw_id=draw_id,
                        evaluable=True,
                        contract_compliant=True,
                        mechanism=_payload(condition)["mechanism"],
                        mechanism_digest="digest",
                        categorical_signature=signatures[condition],
                        token_cost=10,
                        wall_seconds=0.1,
                        generation={},
                    )
        analysis = _analyze_proposals(manifest, draws)
        self.assertEqual(2, analysis["detectable_states"])
        self.assertTrue(all(row["between_condition_median"] > row["within_condition_envelope"] for row in analysis["states"]))

    def test_implementation_analysis_keeps_structure_and_behavior_separate(self) -> None:
        manifest = {"states": [{"state_id": "s1", "task_category": "one"}, {"state_id": "s2", "task_category": "two"}]}
        draws = {}
        for state in manifest["states"]:
            for condition in (CONDITION_A, CONDITION_B):
                for replicate in range(3):
                    draw_id = f"{state['state_id']}:{condition}:{replicate}"
                    draws[draw_id] = ImplementationDraw(
                        state_id=state["state_id"],
                        condition_id=condition,
                        draw_id=draw_id,
                        mechanism_digest="digest",
                        evaluable=True,
                        valid=True,
                        source_signature=((0.0,) * 9 if condition == CONDITION_A else (1.0,) * 9),
                        behavior_signature=(0.0,) * 7,
                        utility=1.0,
                        token_cost=10,
                        wall_seconds=0.1,
                        generation={},
                        source_sha256="source",
                        source_artifact_digest="artifact",
                        evaluation={},
                    )
        analysis = _analyze_implementations(manifest, draws)
        self.assertEqual(2, analysis["source_detectable_states"])
        self.assertEqual(0, analysis["behavior_detectable_states"])

    def test_failed_proposal_record_blocks_implementation_without_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            sealed = seal_structured_mediation_protocol(
                workspace,
                proposal_provider=self.proposal_provider,
                implementation_provider=self.implementation_provider,
            )
            ArtifactStore(workspace / "result-artifacts").write_record(
                PROPOSAL_RECORD,
                {"manifest_digest": sealed["manifest_digest"], "passed": False},
            )
            with self.assertRaisesRegex(RuntimeError, "proposal gate did not pass"):
                run_structured_implementation_calibration(
                    workspace,
                    manifest_digest=sealed["manifest_digest"],
                    proposal_provider=self.proposal_provider,
                    implementation_provider=self.implementation_provider,
                )

    def test_implementation_template_has_no_raw_brief_slot(self) -> None:
        template = _implementation_prompt_template()
        self.assertIn("{mechanism_object}", template)
        self.assertNotIn("{mechanism_brief}", template)
        self.assertNotIn("condition_id", template)


if __name__ == "__main__":
    unittest.main()
