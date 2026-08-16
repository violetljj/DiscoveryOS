from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
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
    ExperimentSpec,
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
from discoveryos.contracts.patch import GenerationStatus, ProviderGeneration
from discoveryos.operators.local_patch import CandidateBuildSpec
from discoveryos.operators.structural_rewrite import (
    STRUCTURAL_REWRITE_PROMPT_TEMPLATE,
    BasinEscapeBrief,
    LineageSnapshot,
    ReusableComponentReference,
    StructuralRewriteOperator,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.repository_runner import IsolatedRepositoryRunner
from discoveryos.util import digest_bytes


class FakeProvider:
    provider_name = "fake_provider"
    model = "frozen-test-model"

    def __init__(self, responses: list[ProviderGeneration]) -> None:
        self.responses = responses
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


class StructuralRewriteOperatorTests(unittest.TestCase):
    def test_structural_rewrite_preserves_lineage_and_records_component_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), target_family="piecewise_memoized")
            result = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value + 1\n"},
                development_evidence_summary="Two local deltas tied at score 0.3.",
                semantic_delta_memory=("Local offsets repeatedly saturated.",),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
                brief=context["brief"],
            )
            self.assertEqual(GenerationStatus.SUCCEEDED, result.record.status)
            self.assertIsNotNone(result.candidate)
            candidate = result.candidate
            self.assertEqual("structural_rewrite_basin_jump_v1", candidate.operator_id)
            self.assertEqual("lineage_preserving_structural_escape", candidate.strategy_id)
            self.assertEqual(
                (context["parent"].candidate_id, context["baseline"].candidate_id),
                candidate.parent_ids,
            )
            parameters = candidate.parameter_dict()
            self.assertEqual("linear_offset", parameters["source_algorithm_family"])
            self.assertEqual("piecewise_memoized", parameters["target_algorithm_family"])
            self.assertEqual((context["component_id"],), tuple(parameters["reused_component_ids"]))
            self.assertEqual(context["brief"].digest, parameters["basin_escape_brief_digest"])

            bundle = ExecutableCandidateBundle.from_artifact(context["artifacts"], candidate.artifact_digest)
            self.assertEqual(2, len(bundle.patch_stack))
            self.assertEqual(context["parent_patch"], bundle.patch_stack[0])
            self.assertEqual(result.proposal.patch, bundle.patch_stack[1])
            experiment = ExperimentSpec.create(
                candidate_id=candidate.candidate_id,
                evaluator_id="eval",
                fidelity=Fidelity.G1,
                split_id="dev",
                split_role=DataRole.DEVELOPMENT,
                seed=7,
                resources=ResourceBudget(tokens=100, cpu_seconds=20, wall_seconds=20),
                contract_digest=context["contract"].digest,
                mode=RunMode.BENCHMARK,
            )
            output = IsolatedRepositoryRunner(
                context["artifacts"],
                contract=context["contract"],
            ).run(
                bundle,
                candidate_artifact_digest=candidate.artifact_digest,
                experiment=experiment,
                data=None,
            )
            self.assertIsNone(output.failure_kind, output.failure_signature)
            self.assertEqual({"score": 5.0}, dict(output.metrics))
            request = context["provider"].requests[0]
            self.assertIn("STRUCTURAL_REWRITE_BRIEF_JSON", request.prompt)
            self.assertEqual(
                digest_bytes(STRUCTURAL_REWRITE_PROMPT_TEMPLATE.encode("utf-8")),
                request.prompt_template_digest,
            )

            with context["ledger"].connect() as connection:
                edge_types = {
                    row["edge_type"]
                    for row in connection.execute(
                        "SELECT edge_type FROM graph_edges WHERE target_id=?",
                        (candidate.candidate_id,),
                    ).fetchall()
                }
            self.assertIn("DERIVED_FROM", edge_types)
            self.assertIn("BASIN_ESCAPE", edge_types)
            self.assertIn("REUSED_BY_STRUCTURAL_REWRITE", edge_types)

    def test_same_family_response_is_not_materialized_as_basin_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), target_family="linear_offset", reused_components=())
            result = context["operator"].propose(
                parent=context["parent"],
                mutable_files={"algorithm.py": "def improve(value):\n    return value + 1\n"},
                development_evidence_summary="The local branch is flat.",
                semantic_delta_memory=(),
                remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                build=context["build"],
                brief=context["brief"],
            )
            self.assertEqual(GenerationStatus.INVALID_RESPONSE, result.record.status)
            self.assertIn("must leave the current algorithm family", result.record.failure_signature)
            self.assertIsNone(result.candidate)

    def test_unbound_lineage_evidence_fails_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), target_family="piecewise_memoized")
            broken_parent = replace(
                context["brief"].lineage[0],
                evidence_receipt_ids=("rcpt_missing",),
            )
            brief = replace(context["brief"], lineage=(broken_parent, context["brief"].lineage[1]))
            with self.assertRaisesRegex(ValueError, "evidence receipt mismatch"):
                context["operator"].propose(
                    parent=context["parent"],
                    mutable_files={"algorithm.py": "def improve(value):\n    return value + 1\n"},
                    development_evidence_summary="The branch is flat.",
                    semantic_delta_memory=(),
                    remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                    build=context["build"],
                    brief=brief,
                )
            self.assertEqual([], context["provider"].requests)
            self.assertEqual([], context["ledger"].generation_records())

    def test_structural_rewrite_refuses_a_baseline_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self._context(Path(directory), target_family="piecewise_memoized")
            reset_build = replace(context["build"], parent_patch_stack=())
            with self.assertRaisesRegex(ValueError, "cannot be a baseline reset"):
                context["operator"].propose(
                    parent=context["parent"],
                    mutable_files={"algorithm.py": "def improve(value):\n    return value + 1\n"},
                    development_evidence_summary="The branch is flat.",
                    semantic_delta_memory=(),
                    remaining_budget=ResourceBudget(tokens=100, wall_seconds=30),
                    build=reset_build,
                    brief=context["brief"],
                )
            self.assertEqual([], context["provider"].requests)

    def _context(
        self,
        root: Path,
        *,
        target_family: str,
        reused_components: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        artifacts = ArtifactStore(root / "artifacts")
        ledger = EvidenceLedger(root / "ledger.sqlite3")
        contract = self._contract()
        repository = root / "repository"
        repository.mkdir()
        (repository / "algorithm.py").write_text(
            "def improve(value):\n    return value\n",
            encoding="utf-8",
        )
        (repository / "public_tests.py").write_text(
            "from algorithm import improve\nassert isinstance(improve(1), (int, float))\n",
            encoding="utf-8",
        )
        (repository / "evaluate.py").write_text(
            "import json\nfrom algorithm import improve\n"
            "print(json.dumps({'metrics': {'score': float(improve(-2) + improve(1))}}))\n",
            encoding="utf-8",
        )
        (repository / "requirements.lock").write_text("locked\n", encoding="utf-8")
        self._git(repository, "init", "-q")
        self._git(repository, "config", "user.email", "structural-test@example.invalid")
        self._git(repository, "config", "user.name", "Structural Rewrite Test")
        self._git(repository, "add", ".")
        self._git(repository, "commit", "-q", "-m", "baseline")
        base_commit = self._git(repository, "rev-parse", "HEAD").stdout.strip()
        ledger.add_contract(contract)
        baseline = CandidateSpec.create(
            artifact_digest=artifacts.put_json({"baseline": True}),
            operator_id="baseline",
            strategy_id="baseline",
            parameters={"algorithm_family": "identity"},
            semantic_delta="frozen identity baseline",
            environment_digest="e" * 64,
        )
        parent_patch = self._parent_patch()
        parent = CandidateSpec.create(
            artifact_digest=artifacts.put_json({"parent_patch": parent_patch}),
            parent_ids=(baseline.candidate_id,),
            operator_id="bounded_llm_local_patch_v1",
            strategy_id="iterative_local_patch",
            parameters={"algorithm_family": "linear_offset"},
            semantic_delta="add a fixed local offset",
            environment_digest="e" * 64,
        )
        ledger.add_candidate(baseline)
        ledger.add_candidate(parent)
        baseline_receipt = self._add_evidence(ledger, contract, baseline, 0.0, seed=0)
        parent_receipt = self._add_evidence(ledger, contract, parent, 0.3, seed=1)
        component_id = "cmp_reusable_abs_transform"
        component_digest = artifacts.put_json({"component": "absolute-value transform"})
        parent_family_digest = artifacts.put_json(
            {"candidate_id": parent.candidate_id, "algorithm_family": "linear_offset"}
        )
        baseline_family_digest = artifacts.put_json(
            {"candidate_id": baseline.candidate_id, "algorithm_family": "identity"}
        )
        component = ReusableComponentReference(
            component_id=component_id,
            source_candidate_id=baseline.candidate_id,
            artifact_digest=component_digest,
            interface="improve(value: float) -> float",
            effect_summary="Handles the negative-value region without changing the public interface.",
        )
        brief = BasinEscapeBrief(
            lineage=(
                LineageSnapshot(
                    parent.candidate_id,
                    "linear_offset",
                    parent_family_digest,
                    parent.semantic_delta,
                    (parent_receipt.receipt_id,),
                    "score=0.3; no gain from the last local offset",
                ),
                LineageSnapshot(
                    baseline.candidate_id,
                    "identity",
                    baseline_family_digest,
                    baseline.semantic_delta,
                    (baseline_receipt.receipt_id,),
                    "score=0.0 baseline",
                ),
            ),
            stagnation_reason="two consecutive local changes produced no additional improvement",
            failure_signatures=("LOCAL_BASIN_PLATEAU",),
            rejected_local_deltas=("increase the constant offset again",),
            reusable_components=(component,),
        )
        selected_components = reused_components if reused_components is not None else (component_id,)
        provider = FakeProvider([self._response(target_family, selected_components)])
        operator = StructuralRewriteOperator(
            provider=provider,
            artifacts=artifacts,
            ledger=ledger,
            contract=contract,
        )
        build = CandidateBuildSpec(
            base_repository=repository.resolve(),
            base_commit=base_commit,
            entrypoint="algorithm.py",
            environment_lock=EnvironmentLock(
                "requirements.lock",
                digest_bytes((repository / "requirements.lock").read_bytes()),
            ),
            build_command=CommandSpec((sys.executable, "-m", "py_compile", "algorithm.py")),
            test_command=CommandSpec((sys.executable, "public_tests.py")),
            evaluation_command=CommandSpec((sys.executable, "evaluate.py")),
            parent_patch_stack=(parent_patch,),
            parent_touched_paths=("algorithm.py",),
        )
        return {
            "artifacts": artifacts,
            "ledger": ledger,
            "contract": contract,
            "baseline": baseline,
            "parent": parent,
            "parent_patch": parent_patch,
            "component_id": component_id,
            "brief": brief,
            "provider": provider,
            "operator": operator,
            "build": build,
        }

    @staticmethod
    def _add_evidence(
        ledger: EvidenceLedger,
        contract: ProblemContract,
        candidate: CandidateSpec,
        score: float,
        *,
        seed: int,
    ) -> EvidenceRecord:
        experiment = ExperimentSpec.create(
            candidate_id=candidate.candidate_id,
            evaluator_id="eval",
            fidelity=Fidelity.G2,
            split_id="dev",
            split_role=DataRole.DEVELOPMENT,
            seed=seed,
            resources=ResourceBudget(cpu_seconds=1, wall_seconds=1),
            contract_digest=contract.digest,
            mode=RunMode.BENCHMARK,
        )
        evidence = EvidenceRecord.create(
            experiment=experiment,
            evaluator_digest="0" * 64,
            data_digest="1" * 64,
            output=EvaluationOutput.from_metrics({"score": score}),
            resource_usage=ResourceUsage(cpu_seconds=1, wall_seconds=1),
        )
        ledger.add_experiment(experiment)
        ledger.add_evidence(evidence)
        return evidence

    @staticmethod
    def _contract() -> ProblemContract:
        return ProblemContract(
            contract_id="structural-rewrite-test",
            version="1",
            question="Escape a saturated local algorithm family under frozen tests.",
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
            evaluator_bindings=tuple(
                (fidelity.value, "eval", "0" * 64)
                for fidelity in (Fidelity.G0, Fidelity.G1, Fidelity.G2)
            ),
            claim_ceiling=ClaimCeiling.DEVELOPMENT_ONLY,
        )

    @staticmethod
    def _parent_patch() -> str:
        return (
            "diff --git a/algorithm.py b/algorithm.py\n"
            "--- a/algorithm.py\n"
            "+++ b/algorithm.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def improve(value):\n"
            "-    return value\n"
            "+    return value + 1\n"
        )

    def _response(self, algorithm_family: str, reused_components: tuple[str, ...]) -> ProviderGeneration:
        patch = (
            "diff --git a/algorithm.py b/algorithm.py\n"
            "--- a/algorithm.py\n"
            "+++ b/algorithm.py\n"
            "@@ -1,2 +1,4 @@\n"
            " def improve(value):\n"
            "-    return value + 1\n"
            "+    if value < 0:\n"
            "+        return -value\n"
            "+    return value + 2\n"
        )
        return ProviderGeneration(
            raw_response=json.dumps(
                {
                    "hypothesis": "A piecewise transform escapes the saturated constant-offset basin.",
                    "expected_effects": {"score": "increase through a different functional family"},
                    "target_files": ["algorithm.py"],
                    "patch": patch,
                    "risks": ["The new branch may overfit the negative-value region."],
                    "estimated_cost": {
                        "tokens": 20,
                        "cpu_seconds": 0,
                        "gpu_seconds": 0,
                        "device_seconds": 0,
                        "wall_seconds": 1,
                    },
                    "algorithm_family": algorithm_family,
                    "escape_rationale": "Replace a scalar offset with input-dependent piecewise behavior.",
                    "reused_component_ids": list(reused_components),
                }
            ),
            usage=ResourceUsage(llm_input_tokens=12, llm_output_tokens=8, wall_seconds=1),
            latency_seconds=1,
            provider_version="test-provider-1",
        )

    @staticmethod
    def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", "-C", str(repository), *arguments),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
