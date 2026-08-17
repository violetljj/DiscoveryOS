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
    DataRole,
    DataSplit,
    EvaluationOutput,
    EvidenceValidity,
    Fidelity,
    MetricDefinition,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    ResourceUsage,
    WinnerRule,
)
from discoveryos.contracts.patch import ProviderGeneration
from discoveryos.evaluation.base import EvaluatorRegistry
from discoveryos.harness import (
    HarnessRunManifest,
    HarnessSearchRuntime,
    ProviderBinding,
    SourceSnapshot,
    algorithm_discovery_v1_profile,
    harness_code_bundle_digest,
    replay_harness_run_binding,
)
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    AnytimeTraceRecorder,
    DeterministicActionController,
    SearchAction,
)
from discoveryos.operators.asha import RungDefinition
from discoveryos.operators.local_patch import LocalPatchOperator
from discoveryos.operators.novelty import NoveltyConfig, ShinkaStyleNoveltyPolicy
from discoveryos.operators.parent_selection import (
    ParentSelectionConfig,
    ShinkaWeightedParentSelectionPolicy,
)
from discoveryos.operators.structural_rewrite import StructuralRewriteOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ComputeFabric, ExperimentExecutor
from discoveryos.runtime.search_loop import (
    LedgerBackedSearchStateProjector,
    SearchLoopRunner,
    SearchRunSpec,
    UnifiedActionExecutor,
)
from discoveryos.runtime.vault import SplitVault
from discoveryos.util import digest_bytes, digest_json


class _Provider:
    provider_name = "frozen_fake_provider"
    model = "frozen_test_model"
    settings_digest = "0" * 64

    def __init__(self, responses: list[ProviderGeneration]) -> None:
        self.responses = responses

    def generate(self, request):
        del request
        return self.responses.pop(0)


class _LoopEvaluator:
    evaluator_id = "loop_eval"
    version = "1"

    def evaluate(self, candidate, experiment, data):
        del data
        if candidate.operator_id in {
            "bounded_llm_local_patch_v1",
            "direct_llm_research_v1",
            "ada_lineage_refinement_v1",
        }:
            return EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.NOT_EVALUABLE,
                failure_signature="LOCAL_BASIN_PLATEAU",
            )
        if candidate.operator_id == "asha_control":
            return EvaluationOutput.from_metrics({"score": 2.0})
        structural_ids = {"structural_rewrite_basin_jump_v1", "evox_meta_strategy_rewrite_v1"}
        score = 1.5 if experiment.fidelity is Fidelity.G1 else 1.0 if candidate.operator_id in structural_ids else 0.0
        return EvaluationOutput.from_metrics({"score": score})


class _PositiveEvaluator:
    evaluator_id = "positive_eval"
    version = "1"

    def evaluate(self, candidate, experiment, data):
        del experiment, data
        return EvaluationOutput.from_metrics(
            {"score": 2.0 if candidate.operator_id == "bounded_llm_local_patch_v1" else 1.0}
        )


class SearchLoopIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_operators_evaluator_projector_and_runner_close_the_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, base_commit = self._repository(root / "repository")
            artifacts = ArtifactStore(root / "artifacts")
            ledger = EvidenceLedger(root / "ledger.sqlite3")
            baseline_patch = self._patch("return value", "return value + 0")
            bundle = ExecutableCandidateBundle(
                base_repository=str(repository.resolve()),
                base_commit=base_commit,
                patch_diff=baseline_patch,
                mutable_paths=("algorithm.py",),
                forbidden_paths=("public_tests.py", "evaluate.py"),
                touched_paths=("algorithm.py",),
                entrypoint="algorithm.py",
                environment_lock=EnvironmentLock(
                    "requirements.lock",
                    digest_bytes((repository / "requirements.lock").read_bytes()),
                ),
                build_command=CommandSpec((sys.executable, "-m", "py_compile", "algorithm.py")),
                test_command=CommandSpec((sys.executable, "public_tests.py")),
                evaluation_command=CommandSpec((sys.executable, "evaluate.py")),
                patch_stack=(baseline_patch,),
                patch_apply_policy="recount_hunks",
                format_version="executable-candidate-v3",
            )
            baseline = CandidateSpec.create(
                artifact_digest=bundle.store(artifacts),
                operator_id="baseline",
                strategy_id="baseline",
                parameters={"algorithm_family": "linear_offset"},
                semantic_delta="frozen baseline offset",
                environment_digest=bundle.environment_lock.sha256,
            )
            asha_control = CandidateSpec.create(
                artifact_digest=baseline.artifact_digest,
                operator_id="asha_control",
                strategy_id="frozen_population_control",
                parameters={"algorithm_family": "control"},
                semantic_delta="frozen ASHA capacity control",
                environment_digest=bundle.environment_lock.sha256,
            )
            registry = EvaluatorRegistry()
            registry.register(_LoopEvaluator())
            evaluator_digest = registry.digest("loop_eval")
            development_data = b"frozen-development-data"
            contract = ProblemContract(
                contract_id="search-loop-test",
                version="1",
                question="Close the autonomous search mechanics loop.",
                baseline_candidate_id=baseline.candidate_id,
                mutable_paths=("algorithm.py",),
                forbidden_paths=("public_tests.py", "evaluate.py"),
                data_splits=(
                    DataSplit("dev", DataRole.DEVELOPMENT, "dev.bin", digest_bytes(development_data)),
                ),
                fidelities=(Fidelity.G0, Fidelity.G1),
                metrics=(MetricDefinition("score", MetricDirection.MAXIMIZE, available_from=Fidelity.G0),),
                hard_constraints=(),
                budget=ResourceBudget(tokens=1000, cpu_seconds=100, wall_seconds=500),
                winner_rule=WinnerRule(metric_order=("score",), require_fidelity=Fidelity.G1),
                evaluator_bindings=(
                    (Fidelity.G0.value, "loop_eval", evaluator_digest),
                    (Fidelity.G1.value, "loop_eval", evaluator_digest),
                ),
                claim_ceiling=ClaimCeiling.MECHANICS_ONLY,
            )
            ledger.add_contract(contract)
            ledger.add_candidate(baseline)
            ledger.add_candidate(asha_control)
            vault = SplitVault(root / "vault", ledger)
            vault.put_split(DataRole.DEVELOPMENT, "dev.bin", development_data)
            experiment_executor = ExperimentExecutor(
                contract=contract,
                ledger=ledger,
                artifacts=artifacts,
                vault=vault,
                registry=registry,
                fabric=ComputeFabric(cpu_workers=1),
            )
            from discoveryos.contracts.models import ExperimentSpec, RunMode

            for candidate, seed in ((asha_control, 0), (baseline, 0), (baseline, 1)):
                initial_experiment = ExperimentSpec.create(
                    candidate_id=candidate.candidate_id,
                    evaluator_id="loop_eval",
                    fidelity=Fidelity.G0,
                    split_id=None,
                    split_role=None,
                    seed=seed,
                    resources=ResourceBudget(cpu_seconds=1, wall_seconds=5),
                    contract_digest=contract.digest,
                    mode=RunMode.DISCOVERY,
                    rung_id="g0",
                )
                await experiment_executor.execute(candidate, initial_experiment)

            controller_config = ActionControllerConfig(
                stagnation_generations=2,
                improvement_epsilon=0.01,
                uncertainty_threshold=0.05,
                incumbent_proximity=0.05,
                minimum_replicates=2,
                structural_similarity_threshold=0.8,
                costs=(
                    ActionCost(SearchAction.LOCAL_PATCH, ResourceBudget(tokens=100, wall_seconds=30)),
                    ActionCost(SearchAction.STRUCTURAL_ESCAPE, ResourceBudget(tokens=100, wall_seconds=30)),
                    ActionCost(SearchAction.REPLICATE, ResourceBudget(cpu_seconds=1, wall_seconds=5)),
                    ActionCost(SearchAction.PROMOTE_FIDELITY, ResourceBudget(cpu_seconds=1, wall_seconds=5)),
                ),
            )
            spec = SearchRunSpec(
                run_id="autonomous-loop-test",
                contract_digest=contract.digest,
                root_candidate_id=baseline.candidate_id,
                branch_id="single-active-branch",
                initial_algorithm_family="linear_offset",
                metric_name="score",
                metric_direction=MetricDirection.MAXIMIZE,
                initial_fidelity=Fidelity.G0,
                budget=ResourceBudget(tokens=1000, cpu_seconds=100, wall_seconds=500),
                rungs=(
                    RungDefinition("g0", Fidelity.G0, ResourceBudget(cpu_seconds=1, wall_seconds=5)),
                    RungDefinition("g1", Fidelity.G1, ResourceBudget(cpu_seconds=1, wall_seconds=5)),
                ),
                eta=2,
                initial_trials=4,
                local_action_limit=2,
                structural_action_limit=1,
                max_steps=5,
                mutable_file_paths=("algorithm.py",),
                seeds=(0, 1, 2),
                initial_population_candidate_ids=(asha_control.candidate_id,),
            )
            local_provider = _Provider(
                [
                    self._local_response(self._patch("return value + 0", "return value + 1")),
                    self._local_response(self._patch("return value + 1", "return value + 2")),
                ]
            )
            structural_provider = _Provider(
                [self._structural_response(self._patch("return value + 2", "return abs(value)"))]
            )
            profile = algorithm_discovery_v1_profile()
            source_snapshot = SourceSnapshot("a" * 40, "b" * 64, True)
            manifest = HarnessRunManifest(
                run_id=spec.run_id,
                search_run_spec_digest=spec.digest,
                profile_id=profile.profile_id,
                plugin_manifest_digests=tuple(
                    (item.plugin_id, item.manifest_digest) for item in profile.plugins
                ),
                code_bundle_digest=harness_code_bundle_digest(),
                repository_commit=source_snapshot.repository_commit,
                tracked_source_tree_digest=source_snapshot.tracked_source_tree_digest,
                worktree_clean=True,
                local_provider=ProviderBinding(
                    local_provider.provider_name,
                    local_provider.model,
                    local_provider.settings_digest,
                    "test-provider-v1",
                ),
                structural_provider=ProviderBinding(
                    structural_provider.provider_name,
                    structural_provider.model,
                    structural_provider.settings_digest,
                    "test-provider-v1",
                ),
                task_instance_digest="c" * 64,
                contract_digest=contract.digest,
                evaluator_bindings=contract.evaluator_bindings,
                environment_digest=baseline.environment_digest,
                seeds=spec.seeds,
                budget=spec.budget,
                winner_rule_digest=digest_json(contract.winner_rule),
                claim_ceiling=contract.claim_ceiling.value,
            )
            runtime = HarnessSearchRuntime.build(
                profile=profile,
                spec=spec,
                contract=contract,
                ledger=ledger,
                artifacts=artifacts,
                experiment_executor=experiment_executor,
                base_controller=DeterministicActionController(controller_config),
                local_provider=local_provider,
                structural_provider=structural_provider,
                manifest=manifest,
                source_snapshot=source_snapshot,
            )
            projector = runtime.loop.projector
            self.assertEqual(spec, SearchRunSpec.from_dict(ledger.get_search_run(spec.run_id)))
            result = await runtime.run()
            replay = replay_harness_run_binding(
                ledger,
                manifest,
                profile=profile,
                spec=spec,
                contract=contract,
                environment_digest=baseline.environment_digest,
                local_provider=local_provider,
                structural_provider=structural_provider,
                source_snapshot=source_snapshot,
            )
            self.assertTrue(replay.bindings_valid, replay.issues)
            drifted = replace(manifest, code_bundle_digest="f" * 64)
            drift_replay = replay_harness_run_binding(
                ledger,
                drifted,
                profile=profile,
                spec=spec,
                contract=contract,
                environment_digest=baseline.environment_digest,
                local_provider=local_provider,
                structural_provider=structural_provider,
                source_snapshot=source_snapshot,
            )
            self.assertIn("CODE_BUNDLE_MISMATCH", drift_replay.issues)

            actions = [payload["action"] for payload in ledger.search_action_payloads(spec.run_id)]
            self.assertEqual(
                [
                    "LOCAL_PATCH",
                    "LOCAL_PATCH",
                    "STRUCTURAL_ESCAPE",
                    "REPLICATE",
                    "PROMOTE_FIDELITY",
                ],
                actions,
            )
            self.assertEqual(5, result.settled_steps)
            self.assertEqual(1.5, result.incumbent_utility, projector.build())
            self.assertEqual(("NO_ACTIVE_SEARCH_FRONTIER",), result.stop_decision.reason_codes)
            self.assertEqual(5, len(result.trace_ids))
            trace_files = sorted((artifacts.records / "search" / spec.run_id / "anytime").glob("*.json"))
            self.assertEqual(5, len(trace_files))
            trace_payload = json.loads(trace_files[0].read_text(encoding="utf-8"))
            self.assertIn("budget_floor", trace_payload)
            self.assertIn("budget_reserved", trace_payload)
            self.assertIn("reserved_downstream_budget", trace_payload)
            with ledger.connect() as connection:
                event_types = [
                    row["event_type"]
                    for row in connection.execute("SELECT event_type FROM events ORDER BY sequence")
                ]
            self.assertIn("ACTION_PLANNED", event_types)
            self.assertIn("ACTION_STARTED", event_types)
            self.assertIn("ACTION_EXECUTION_FAILED", event_types)
            self.assertIn("CANDIDATE_EMITTED", event_types)
            self.assertIn("CANDIDATE_VALID", event_types)
            self.assertIn("HARNESS_SEARCH_STARTED", event_types)
            self.assertIn("HARNESS_SEARCH_SETTLED", event_types)
            self.assertIn("HARNESS_PROFILE_DISPOSED", event_types)
            self.assertNotIn("CANDIDATE_INVALID", event_types)
            self.assertFalse(
                any(
                    (record.failure_signature or "").startswith("GENERATION_BUDGET_EXCEEDED")
                    for record in ledger.generation_records()
                )
            )
            state = projector.build()
            self.assertEqual("score", state.utility_metric_name)
            self.assertEqual(1, len(state.branches))

    async def test_parent_local_novelty_resample_evaluate_settle_closes_the_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, base_commit = self._repository(root / "repository")
            artifacts = ArtifactStore(root / "artifacts")
            ledger = EvidenceLedger(root / "ledger.sqlite3")
            baseline_patch = self._patch("return value", "return value + 0")
            bundle = ExecutableCandidateBundle(
                base_repository=str(repository.resolve()),
                base_commit=base_commit,
                patch_diff=baseline_patch,
                mutable_paths=("algorithm.py",),
                forbidden_paths=("public_tests.py", "evaluate.py"),
                touched_paths=("algorithm.py",),
                entrypoint="algorithm.py",
                environment_lock=EnvironmentLock(
                    "requirements.lock",
                    digest_bytes((repository / "requirements.lock").read_bytes()),
                ),
                build_command=CommandSpec((sys.executable, "-m", "py_compile", "algorithm.py")),
                test_command=CommandSpec((sys.executable, "public_tests.py")),
                evaluation_command=CommandSpec((sys.executable, "evaluate.py")),
                patch_stack=(baseline_patch,),
                patch_apply_policy="recount_hunks",
                format_version="executable-candidate-v3",
            )
            baseline = CandidateSpec.create(
                artifact_digest=bundle.store(artifacts),
                operator_id="baseline",
                strategy_id="baseline",
                parameters={"algorithm_family": "linear_offset"},
                semantic_delta="baseline",
                environment_digest=bundle.environment_lock.sha256,
            )
            registry = EvaluatorRegistry()
            registry.register(_PositiveEvaluator())
            evaluator_digest = registry.digest("positive_eval")
            development_data = b"development"
            contract = ProblemContract(
                contract_id="strategy-integration-test",
                version="1",
                question="Exercise parent and novelty integration.",
                baseline_candidate_id=baseline.candidate_id,
                mutable_paths=("algorithm.py",),
                forbidden_paths=("public_tests.py", "evaluate.py"),
                data_splits=(DataSplit("dev", DataRole.DEVELOPMENT, "dev.bin", digest_bytes(development_data)),),
                fidelities=(Fidelity.G0, Fidelity.G1),
                metrics=(MetricDefinition("score", MetricDirection.MAXIMIZE, available_from=Fidelity.G0),),
                hard_constraints=(),
                budget=ResourceBudget(tokens=100, cpu_seconds=20, wall_seconds=100),
                winner_rule=WinnerRule(metric_order=("score",), require_fidelity=Fidelity.G1),
                evaluator_bindings=(
                    (Fidelity.G0.value, "positive_eval", evaluator_digest),
                    (Fidelity.G1.value, "positive_eval", evaluator_digest),
                ),
                claim_ceiling=ClaimCeiling.MECHANICS_ONLY,
            )
            ledger.add_contract(contract)
            ledger.add_candidate(baseline)
            vault = SplitVault(root / "vault", ledger)
            vault.put_split(DataRole.DEVELOPMENT, "dev.bin", development_data)
            experiment_executor = ExperimentExecutor(
                contract=contract,
                ledger=ledger,
                artifacts=artifacts,
                vault=vault,
                registry=registry,
                fabric=ComputeFabric(cpu_workers=1),
            )
            from discoveryos.contracts.models import ExperimentSpec, RunMode

            initial_experiment = ExperimentSpec.create(
                candidate_id=baseline.candidate_id,
                evaluator_id="positive_eval",
                fidelity=Fidelity.G0,
                split_id=None,
                split_role=None,
                seed=0,
                resources=ResourceBudget(cpu_seconds=1, wall_seconds=5),
                contract_digest=contract.digest,
                mode=RunMode.DISCOVERY,
                rung_id="g0",
            )
            initial_evidence = await experiment_executor.execute(baseline, initial_experiment)
            frozen_initial_payload = next(
                payload for payload in ledger.evidence_payloads() if payload["receipt_id"] == initial_evidence.receipt_id
            )
            generation = ResourceBudget(tokens=10, wall_seconds=3)
            retry = ResourceBudget(tokens=10, wall_seconds=3)
            evaluation = ResourceBudget(cpu_seconds=1, wall_seconds=5)
            complete = ResourceBudget(tokens=20, cpu_seconds=1, wall_seconds=11)
            controller_config = ActionControllerConfig(
                stagnation_generations=2,
                minimum_replicates=1,
                structural_similarity_threshold=0.0,
                costs=(
                    ActionCost(
                        SearchAction.LOCAL_PATCH,
                        complete,
                        generation_reserve=generation,
                        evaluation_reserve=evaluation,
                        novelty_resample_reserve=retry,
                    ),
                    ActionCost(
                        SearchAction.STRUCTURAL_ESCAPE,
                        complete,
                        generation_reserve=generation,
                        evaluation_reserve=evaluation,
                        novelty_resample_reserve=retry,
                    ),
                    ActionCost(SearchAction.REPLICATE, evaluation),
                    ActionCost(SearchAction.PROMOTE_FIDELITY, evaluation),
                ),
            )
            parent_config = ParentSelectionConfig(base_seed=13, selection_lambda=2.0)
            novelty_config = NoveltyConfig(
                max_novelty_attempts=2,
                similarity_threshold=0.9,
                semantic_difference_threshold=0.2,
            )
            spec = SearchRunSpec(
                run_id="parent-novelty-integration",
                contract_digest=contract.digest,
                root_candidate_id=baseline.candidate_id,
                branch_id="branch",
                initial_algorithm_family="linear_offset",
                metric_name="score",
                metric_direction=MetricDirection.MAXIMIZE,
                initial_fidelity=Fidelity.G0,
                budget=ResourceBudget(tokens=40, cpu_seconds=3, wall_seconds=40),
                rungs=(
                    RungDefinition("g0", Fidelity.G0, evaluation),
                    RungDefinition("g1", Fidelity.G1, evaluation),
                ),
                eta=2,
                initial_trials=2,
                local_action_limit=2,
                structural_action_limit=0,
                max_steps=2,
                mutable_file_paths=("algorithm.py",),
                seeds=(0, 1),
                parent_selection=parent_config,
                novelty=novelty_config,
            )
            duplicate_patch = (
                "diff --git a/algorithm.py b/algorithm.py\n"
                "--- a/algorithm.py\n"
                "+++ b/algorithm.py\n"
                "@@ -1,2 +1,3 @@\n"
                " def improve(value):\n"
                "+    # duplicate formatting-only proposal\n"
                "     return value + 0\n"
            )
            local = LocalPatchOperator(
                provider=_Provider(
                    [
                        self._local_response(self._patch("return missing", "return value + 9")),
                        self._local_response(duplicate_patch),
                        self._local_response(self._patch("return value + 0", "return value + 1")),
                    ]
                ),
                artifacts=artifacts,
                ledger=ledger,
                contract=contract,
            )
            structural = StructuralRewriteOperator(
                provider=_Provider([]),
                artifacts=artifacts,
                ledger=ledger,
                contract=contract,
            )
            projector = LedgerBackedSearchStateProjector(
                spec=spec,
                contract=contract,
                controller_config=controller_config,
                ledger=ledger,
                artifacts=artifacts,
            )
            parent_policy = ShinkaWeightedParentSelectionPolicy(parent_config)
            novelty_policy = ShinkaStyleNoveltyPolicy(novelty_config)
            result = await SearchLoopRunner(
                controller=DeterministicActionController(controller_config, parent_policy),
                projector=projector,
                executor=UnifiedActionExecutor(
                    spec=spec,
                    contract=contract,
                    ledger=ledger,
                    artifacts=artifacts,
                    projector=projector,
                    local_operator=local,
                    structural_operator=structural,
                    experiment_executor=experiment_executor,
                    novelty_policy=novelty_policy,
                ),
                trace=AnytimeTraceRecorder(artifacts, ledger),
            ).run()
            actions = ledger.search_action_payloads(spec.run_id)
            failed_action, action = actions
            novelty_receipts = ledger.novelty_receipt_payloads(spec.run_id)
            self.assertIsNone(failed_action["result_candidate_id"])
            self.assertTrue(
                failed_action["failure_signature"].startswith(
                    "NOVELTY_PROPOSAL_MATERIALIZATION_FAILED"
                )
            )
            self.assertEqual(1, len(failed_action["generation_ids"]))
            self.assertEqual(
                2,
                failed_action["actual_usage"]["llm_input_tokens"]
                + failed_action["actual_usage"]["llm_output_tokens"],
            )
            self.assertEqual("LOCAL_PATCH", action["action"])
            self.assertEqual(2, len(action["generation_ids"]))
            self.assertEqual(4, action["actual_usage"]["llm_input_tokens"] + action["actual_usage"]["llm_output_tokens"])
            self.assertEqual(2, len(novelty_receipts))
            self.assertEqual("REJECT_RESAMPLE", novelty_receipts[0]["assessment"]["decision"])
            self.assertEqual("ACCEPT", novelty_receipts[1]["assessment"]["decision"])
            self.assertEqual(2, len(ledger.parent_selection_receipt_payloads(spec.run_id)))
            self.assertEqual(2, len(ledger.evidence_records()))
            self.assertEqual(2, result.settled_steps)
            self.assertEqual(2.0, result.incumbent_utility)
            self.assertEqual(
                frozen_initial_payload,
                next(
                    payload
                    for payload in ledger.evidence_payloads()
                    if payload["receipt_id"] == initial_evidence.receipt_id
                ),
            )

    @staticmethod
    def _repository(path: Path) -> tuple[Path, str]:
        path.mkdir()
        (path / "algorithm.py").write_text("def improve(value):\n    return value\n", encoding="utf-8")
        (path / "public_tests.py").write_text("from algorithm import improve\nassert improve(1) is not None\n", encoding="utf-8")
        (path / "evaluate.py").write_text("print('{\"metrics\": {\"score\": 0}}')\n", encoding="utf-8")
        (path / "requirements.lock").write_text("locked\n", encoding="utf-8")
        for args in (
            ("init", "-q"),
            ("config", "user.email", "search-loop@example.invalid"),
            ("config", "user.name", "Search Loop Test"),
            ("add", "."),
            ("commit", "-q", "-m", "baseline"),
        ):
            subprocess.run(("git", "-C", str(path), *args), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        commit = subprocess.run(
            ("git", "-C", str(path), "rev-parse", "HEAD"),
            check=True,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
        ).stdout.strip()
        return path, commit

    @staticmethod
    def _patch(before: str, after: str) -> str:
        return (
            "diff --git a/algorithm.py b/algorithm.py\n"
            "--- a/algorithm.py\n"
            "+++ b/algorithm.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def improve(value):\n"
            f"-    {before}\n"
            f"+    {after}\n"
        )

    @staticmethod
    def _local_response(patch: str) -> ProviderGeneration:
        return ProviderGeneration(
            raw_response=json.dumps(
                {
                    "hypothesis": "repeat local offset adjustment",
                    "expected_effects": {"score": "uncertain"},
                    "target_files": ["algorithm.py"],
                    "patch": patch,
                    "risks": ["May remain in the same local basin."],
                    "estimated_cost": {
                        "tokens": 2,
                        "cpu_seconds": 0,
                        "gpu_seconds": 0,
                        "device_seconds": 0,
                        "wall_seconds": 0.1,
                    },
                }
            ),
            usage=ResourceUsage(llm_input_tokens=1, llm_output_tokens=1, wall_seconds=0.1),
            latency_seconds=0.1,
            provider_version="test-1",
        )

    @staticmethod
    def _structural_response(patch: str) -> ProviderGeneration:
        return ProviderGeneration(
            raw_response=json.dumps(
                {
                    "hypothesis": "absolute value changes the algorithm family",
                    "expected_effects": {"score": "increase"},
                    "target_files": ["algorithm.py"],
                    "patch": patch,
                    "risks": ["The family shift may not generalize."],
                    "estimated_cost": {
                        "tokens": 2,
                        "cpu_seconds": 0,
                        "gpu_seconds": 0,
                        "device_seconds": 0,
                        "wall_seconds": 0.1,
                    },
                    "algorithm_family": "absolute_value",
                    "escape_rationale": "Replace additive offsets with an input-dependent transform.",
                    "reused_component_ids": [],
                }
            ),
            usage=ResourceUsage(llm_input_tokens=1, llm_output_tokens=1, wall_seconds=0.1),
            latency_seconds=0.1,
            provider_version="test-1",
        )


if __name__ == "__main__":
    unittest.main()
