from __future__ import annotations

import json
import asyncio
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from dataclasses import replace

from discoveryos.contracts.executable import CommandSpec, EnvironmentLock, ExecutableCandidateBundle
from discoveryos.contracts.models import (
    CandidateSpec,
    ExperimentSpec,
    FailureKind,
    Fidelity,
    MetricDefinition,
    MetricDirection,
    ResourceBudget,
    RunMode,
    WinnerRule,
)
from discoveryos.domains.clearance_demo import initialize_demo
from discoveryos.evaluation import EvaluatorRegistry, ReplayEngine
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.repository_runner import ExecutableCandidateEvaluator, IsolatedRepositoryRunner
from discoveryos.runtime.scheduler import ComputeFabric, ExperimentExecutor
from discoveryos.util import digest_bytes


class RepositoryRunnerTests(unittest.TestCase):
    def test_bundle_runs_in_clean_worktree_and_emits_usage_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit, patch = _make_repository(root)
            artifacts = ArtifactStore(root / "artifacts")
            bundle = _bundle(repository, commit, patch)
            artifact_digest = bundle.store(artifacts)
            experiment = _experiment(artifact_digest, wall_seconds=10)
            output = IsolatedRepositoryRunner(artifacts).run(
                bundle,
                candidate_artifact_digest=artifact_digest,
                experiment=experiment,
                data=b"demo-data",
            )
            self.assertIsNone(output.failure_kind)
            self.assertEqual({"score": 2.0}, dict(output.metrics))
            self.assertEqual(5, output.reported_usage.llm_input_tokens)
            self.assertGreater(output.reported_usage.wall_seconds, 0)
            self.assertGreater(output.reported_usage.peak_rss_bytes, 0)
            self.assertEqual(4, len(output.artifacts))
            self.assertIn("return 1", (repository / "algorithm.py").read_text(encoding="utf-8"))
            worktrees = _git(repository, "worktree", "list", "--porcelain").stdout
            self.assertEqual(1, worktrees.count("worktree "))

    def test_hard_timeout_kills_the_evaluation_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit, patch = _make_repository(root)
            artifacts = ArtifactStore(root / "artifacts")
            bundle = _bundle(
                repository,
                commit,
                patch,
                evaluation=CommandSpec((sys.executable, "-c", "import time; time.sleep(30)")),
            )
            artifact_digest = bundle.store(artifacts)
            started = time.monotonic()
            output = IsolatedRepositoryRunner(artifacts).run(
                bundle,
                candidate_artifact_digest=artifact_digest,
                experiment=_experiment(artifact_digest, wall_seconds=2),
                data=None,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(FailureKind.TIMEOUT, output.failure_kind)
            self.assertIn("TIMEOUT", output.failure_signature or "")
            self.assertLess(elapsed, 8)

    def test_bundle_rejects_a_declared_forbidden_touch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit, patch = _make_repository(root)
            with self.assertRaises(ValueError):
                _bundle(repository, commit, patch, forbidden_paths=("algorithm.py",))

    def test_executor_records_and_replays_a_real_code_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = initialize_demo(root / "workspace")
            repository, commit, patch = _make_repository(root)
            bundle = _bundle(repository, commit, patch)
            artifact_digest = bundle.store(context.artifacts)
            candidate = CandidateSpec.create(
                artifact_digest=artifact_digest,
                operator_id="test_local_patch_v1",
                strategy_id="test",
                parameters={},
                semantic_delta="Return the stronger score in a one-file local patch.",
                environment_digest=bundle.environment_lock.sha256,
            )
            provisional = ExecutableCandidateEvaluator(context.artifacts)
            registry = EvaluatorRegistry()
            registry.register(provisional)
            bindings = tuple(
                (fidelity.value, provisional.evaluator_id, registry.digest(provisional.evaluator_id))
                for fidelity in context.contract.fidelities
            )
            contract = replace(
                context.contract,
                baseline_candidate_id=candidate.candidate_id,
                mutable_paths=("algorithm.py",),
                forbidden_paths=("tests",),
                metrics=(MetricDefinition("score", MetricDirection.MAXIMIZE, available_from=Fidelity.G0),),
                hard_constraints=(),
                winner_rule=WinnerRule(metric_order=("score",), require_fidelity=Fidelity.G2),
                evaluator_bindings=bindings,
            )
            registry = EvaluatorRegistry()
            evaluator = ExecutableCandidateEvaluator(context.artifacts, contract=contract)
            registry.register(evaluator)
            self.assertEqual(contract.evaluator_digest_for(Fidelity.G1), registry.digest(evaluator.evaluator_id))
            context.ledger.add_candidate(candidate)
            context.ledger.add_contract(contract)
            executor = ExperimentExecutor(
                contract=contract,
                ledger=context.ledger,
                artifacts=context.artifacts,
                vault=context.vault,
                registry=registry,
                fabric=ComputeFabric(cpu_workers=1),
            )
            experiment = ExperimentSpec.create(
                candidate_id=candidate.candidate_id,
                evaluator_id=contract.evaluator_id_for(Fidelity.G1),
                fidelity=Fidelity.G1,
                split_id=next(split.split_id for split in contract.data_splits if split.role.value == "development"),
                split_role=next(split.role for split in contract.data_splits if split.role.value == "development"),
                seed=31,
                resources=ResourceBudget(tokens=20, cpu_seconds=20, wall_seconds=10),
                contract_digest=contract.digest,
                mode=RunMode.DISCOVERY,
                rung_id="rung-low",
            )
            evidence = asyncio.run(executor.execute(candidate, experiment))
            self.assertEqual({"score": 2.0}, evidence.metric_dict())
            self.assertEqual(8, evidence.resource_usage.tokens)
            replay = ReplayEngine(
                contract=contract,
                ledger=context.ledger,
                artifacts=context.artifacts,
                vault=context.vault,
                registry=registry,
            ).replay(evidence)
            self.assertTrue(replay.bindings_valid)
            self.assertTrue(replay.evaluator_reproduced)


def _make_repository(root: Path) -> tuple[Path, str, str]:
    repository = root / "base"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "DiscoveryOS Tests")
    (repository / "algorithm.py").write_text("def score():\n    return 1\n", encoding="utf-8")
    (repository / "requirements.lock").write_text("stdlib-only\n", encoding="utf-8")
    _git(repository, "add", "algorithm.py", "requirements.lock")
    _git(repository, "commit", "-m", "baseline")
    commit = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "algorithm.py").write_text("def score():\n    return 2\n", encoding="utf-8")
    patch = _git(repository, "diff", "--", "algorithm.py").stdout
    _git(repository, "restore", "algorithm.py")
    return repository.resolve(), commit, patch


def _bundle(
    repository: Path,
    commit: str,
    patch: str,
    *,
    forbidden_paths: tuple[str, ...] = ("tests",),
    evaluation: CommandSpec | None = None,
) -> ExecutableCandidateBundle:
    lock = repository / "requirements.lock"
    return ExecutableCandidateBundle(
        base_repository=str(repository),
        base_commit=commit,
        patch_diff=patch,
        mutable_paths=("algorithm.py",),
        forbidden_paths=forbidden_paths,
        touched_paths=("algorithm.py",),
        entrypoint="algorithm.py",
        environment_lock=EnvironmentLock("requirements.lock", digest_bytes(lock.read_bytes())),
        build_command=CommandSpec((sys.executable, "-m", "py_compile", "algorithm.py")),
        test_command=CommandSpec((sys.executable, "-c", "import algorithm; assert algorithm.score() == 2")),
        evaluation_command=evaluation
        or CommandSpec(
            (
                sys.executable,
                "-c",
                "import algorithm,json; print(json.dumps({'metrics': {'score': algorithm.score()}, 'usage': {'llm_input_tokens': 5, 'llm_output_tokens': 3, 'llm_cache_tokens': 2}}))",
            )
        ),
    )


def _experiment(candidate_digest: str, *, wall_seconds: float) -> ExperimentSpec:
    return ExperimentSpec.create(
        candidate_id="cand_" + candidate_digest[:20],
        evaluator_id="executable_candidate_v1",
        fidelity=Fidelity.G1,
        split_id="development",
        split_role=None,
        seed=17,
        resources=ResourceBudget(tokens=20, cpu_seconds=20, wall_seconds=wall_seconds),
        contract_digest="c" * 64,
        mode=RunMode.DISCOVERY,
        replicate_id="replicate-17",
        rung_id="rung-low",
    )


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
