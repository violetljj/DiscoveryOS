from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discoveryos.contracts.executable import CommandSpec, EnvironmentLock, ExecutableCandidateBundle
from discoveryos.contracts.models import (
    CandidateSpec,
    ClaimCeiling,
    ConstraintOperator,
    DataRole,
    DataSplit,
    EvaluationOutput,
    EvidenceRecord,
    EvidenceValidity,
    ExperimentSpec,
    FailureKind,
    Fidelity,
    HardConstraint,
    MetricDefinition,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    ResourceUsage,
    RunMode,
    WinnerRule,
)
from discoveryos.contracts.patch import (
    GenerationProviderError,
    GenerationStatus,
    MechanicalDiagnostic,
    ProviderGeneration,
)
from discoveryos.operators.local_patch import CandidateBuildSpec, LocalPatchOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_bytes


class FakeProvider:
    provider_name = "fake_provider"
    model = "frozen-test-model"

    def __init__(self, responses: list[ProviderGeneration | Exception]) -> None:
        self.responses = responses
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class LocalPatchOperatorTest(unittest.TestCase):
    def test_success_freezes_generation_provenance_and_candidate_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), [self._response(self._patch("return value + 1"))])
            result = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="baseline score is development-only",
                failure_signature=None,
                semantic_delta_memory=("bounded local changes have been stable",),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
            )

            self.assertEqual(GenerationStatus.SUCCEEDED, result.record.status)
            self.assertIsNotNone(result.candidate)
            self.assertEqual(11, result.record.usage.tokens)
            stored = context["ledger"].get_generation(result.record.generation_id)
            self.assertEqual(result.record, stored)
            bundle = ExecutableCandidateBundle.from_artifact(context["artifacts"], result.candidate.artifact_digest)
            self.assertEqual((result.proposal.patch,), bundle.patch_stack)
            self.assertEqual("recount_hunks", bundle.patch_apply_policy)
            self.assertEqual("executable-candidate-v3", bundle.format_version)
            self.assertEqual(result.record.provenance_artifact_digest, bundle.generation_provenance_digest)
            self.assertEqual(1, context["ledger"].counts()["generation_records"])

    def test_invalid_or_failed_generation_is_not_an_algorithmic_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = self._context(root / "invalid", [self._response("not json")])
            result = invalid["operator"].propose(
                parent=invalid["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="",
                failure_signature=None,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=invalid["build"],
            )
            self.assertEqual(GenerationStatus.INVALID_RESPONSE, result.record.status)
            self.assertIsNone(result.candidate)

            failed = self._context(root / "failed", [GenerationProviderError("MODEL_UNAVAILABLE")])
            result = failed["operator"].propose(
                parent=failed["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="",
                failure_signature=None,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=failed["build"],
            )
            self.assertEqual(GenerationStatus.PROVIDER_FAILURE, result.record.status)
            self.assertIsNone(result.candidate)

    def test_forbidden_diff_mechanics_are_rejected_before_candidate_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deletion = (
                "diff --git a/algorithm.py b/algorithm.py\n"
                "deleted file mode 100644\n"
                "--- a/algorithm.py\n"
                "+++ /dev/null\n"
                "@@ -1,2 +0,0 @@\n"
                "-def improve(value):\n"
                "-    return value\n"
            )
            context = self._context(Path(directory), [self._response(deletion)])
            result = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="",
                failure_signature=None,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
            )
            self.assertEqual(GenerationStatus.INVALID_RESPONSE, result.record.status)
            self.assertIn("forbidden", result.record.failure_signature)
            self.assertIsNone(result.candidate)

    def test_repair_is_mechanical_only_and_allowed_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(
                Path(directory),
                [
                    self._response(self._patch("return missing_name")),
                    self._response(self._patch("return value + 1")),
                ],
            )
            first = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="development score marker 0.123456",
                failure_signature=None,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
            )
            diagnostic = MechanicalDiagnostic(
                failure_kind=FailureKind.TEST_FAILED,
                failure_signature="TEST_FAILED:test:exit=1",
                diagnostic_excerpt="NameError: missing_name",
            )
            parent_bundle = ExecutableCandidateBundle.from_artifact(context["artifacts"], first.candidate.artifact_digest)
            repair_build = CandidateBuildSpec(
                base_repository=context["build"].base_repository,
                base_commit=context["build"].base_commit,
                entrypoint=context["build"].entrypoint,
                environment_lock=context["build"].environment_lock,
                build_command=context["build"].build_command,
                test_command=context["build"].test_command,
                evaluation_command=context["build"].evaluation_command,
                parent_patch_stack=parent_bundle.effective_patch_stack,
                parent_touched_paths=parent_bundle.touched_paths,
            )
            repaired = context["operator"].repair(
                generation_id=first.record.generation_id,
                parent=first.candidate,
                mutable_files={"algorithm.py": "def improve(value):\n    return missing_name\n"},
                diagnostic=diagnostic,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=89, wall_seconds=30),
                build=repair_build,
            )
            self.assertEqual(GenerationStatus.SUCCEEDED, repaired.record.status)
            self.assertNotIn("0.123456", context["provider"].requests[1].prompt)
            repaired_bundle = ExecutableCandidateBundle.from_artifact(context["artifacts"], repaired.candidate.artifact_digest)
            self.assertEqual(2, len(repaired_bundle.patch_stack))
            with self.assertRaisesRegex(ValueError, "only one mechanical repair"):
                context["operator"].repair(
                    generation_id=first.record.generation_id,
                    parent=first.candidate,
                    mutable_files={"algorithm.py": "def improve(value):\n    return missing_name\n"},
                    diagnostic=diagnostic,
                    semantic_delta_memory=(),
                    remaining_budget=ResourceBudget(tokens=70, wall_seconds=30),
                    build=repair_build,
                )

    def test_valid_worse_evidence_cannot_enter_repair_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), [])
            experiment = ExperimentSpec.create(
                candidate_id=context["parent"].candidate_id,
                evaluator_id="eval",
                fidelity=Fidelity.G2,
                split_id="dev",
                split_role=DataRole.DEVELOPMENT,
                seed=0,
                resources=ResourceBudget(cpu_seconds=1, wall_seconds=1),
                contract_digest=context["contract"].digest,
                mode=RunMode.BENCHMARK,
            )
            evidence = EvidenceRecord.create(
                experiment=experiment,
                evaluator_digest="0" * 64,
                data_digest="1" * 64,
                output=EvaluationOutput.from_metrics({"score": -1.0}),
                resource_usage=ResourceUsage(),
            )
            with self.assertRaisesRegex(ValueError, "only mechanical execution failures"):
                MechanicalDiagnostic.from_evidence(evidence, "score regressed")

    def test_actual_tokens_over_ceiling_are_not_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = ProviderGeneration(
                raw_response=self._proposal_json(self._patch("return value + 1")),
                usage=ResourceUsage(llm_input_tokens=90, llm_output_tokens=20, wall_seconds=1),
                latency_seconds=1,
                provider_version="test",
            )
            context = self._context(Path(directory), [generated])
            result = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value\n"},
                development_evidence_summary="",
                failure_signature=None,
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
            )
            self.assertEqual(GenerationStatus.BUDGET_EXHAUSTED, result.record.status)
            self.assertIsNone(result.candidate)

    def _context(self, root: Path, responses: list[ProviderGeneration | Exception]):
        root.mkdir(parents=True, exist_ok=True)
        artifacts = ArtifactStore(root / "artifacts")
        ledger = EvidenceLedger(root / "ledger.sqlite3")
        contract = self._contract()
        parent = CandidateSpec.create(
            artifact_digest=artifacts.put_json({"baseline": True}),
            operator_id="baseline",
            strategy_id="baseline",
            parameters={},
            semantic_delta="frozen baseline",
            environment_digest="e" * 64,
        )
        ledger.add_contract(contract)
        ledger.add_candidate(parent)
        provider = FakeProvider(responses)
        operator = LocalPatchOperator(provider=provider, artifacts=artifacts, ledger=ledger, contract=contract)
        environment_lock = EnvironmentLock("requirements.lock", digest_bytes(b"locked\n"))
        build = CandidateBuildSpec(
            base_repository=root.resolve(),
            base_commit="base-commit",
            entrypoint="algorithm.py",
            environment_lock=environment_lock,
            build_command=CommandSpec(("python", "-m", "py_compile", "algorithm.py")),
            test_command=CommandSpec(("python", "public_tests.py")),
            evaluation_command=CommandSpec(("python", "evaluate.py")),
        )
        return {
            "artifacts": artifacts,
            "ledger": ledger,
            "contract": contract,
            "parent": parent,
            "provider": provider,
            "operator": operator,
            "build": build,
        }

    @staticmethod
    def _contract() -> ProblemContract:
        return ProblemContract(
            contract_id="local-patch-test",
            version="1",
            question="Improve the real implementation under frozen tests.",
            baseline_candidate_id="baseline",
            mutable_paths=("algorithm.py",),
            forbidden_paths=("public_tests.py", "evaluate.py"),
            data_splits=(
                DataSplit("dev", DataRole.DEVELOPMENT, "dev.bin", "1" * 64),
                DataSplit("blind", DataRole.FINAL_BLIND, "blind.bin", "2" * 64),
            ),
            fidelities=(Fidelity.G0, Fidelity.G1, Fidelity.G2),
            metrics=(MetricDefinition("score", MetricDirection.MAXIMIZE),),
            hard_constraints=(HardConstraint("score", ConstraintOperator.GE, -10, Fidelity.G1),),
            budget=ResourceBudget(tokens=1000, cpu_seconds=100, wall_seconds=1000),
            winner_rule=WinnerRule(metric_order=("score",)),
            evaluator_bindings=tuple((fidelity.value, "eval", "0" * 64) for fidelity in (Fidelity.G0, Fidelity.G1, Fidelity.G2)),
            claim_ceiling=ClaimCeiling.DEVELOPMENT_ONLY,
        )

    @staticmethod
    def _patch(expression: str) -> str:
        return (
            "diff --git a/algorithm.py b/algorithm.py\n"
            "--- a/algorithm.py\n"
            "+++ b/algorithm.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def improve(value):\n"
            "-    return value\n"
            f"+    {expression}\n"
        )

    def _response(self, patch: str) -> ProviderGeneration:
        return ProviderGeneration(
            raw_response=self._proposal_json(patch),
            usage=ResourceUsage(llm_input_tokens=7, llm_output_tokens=4, llm_cache_tokens=2, wall_seconds=1),
            latency_seconds=1,
            provider_version="test-provider-1",
            provider_request_id="request-1",
            transport_log='{"type":"turn.completed"}',
        )

    @staticmethod
    def _proposal_json(patch: str) -> str:
        return json.dumps(
            {
                "hypothesis": "Incrementing the result improves the development objective.",
                "expected_effects": {"score": "increase"},
                "target_files": ["algorithm.py"],
                "patch": patch,
                "risks": ["May not generalize beyond the bounded task."],
                "estimated_cost": {
                    "tokens": 11,
                    "cpu_seconds": 0,
                    "gpu_seconds": 0,
                    "device_seconds": 0,
                    "wall_seconds": 1,
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
