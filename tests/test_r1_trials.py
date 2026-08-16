from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.contracts.models import (
    EvaluationOutput,
    ExperimentSpec,
    FailureKind,
    Fidelity,
    GateDecision,
    ResourceBudget,
    ResourceUsage,
    RunMode,
)
from discoveryos.domains.clearance_demo import initialize_demo
from discoveryos.evaluation import EvaluatorRegistry, GateEngine, ReplayEngine
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ComputeFabric, DiscoveryRunner, ExperimentExecutor


class TrialIdentityTests(unittest.TestCase):
    def test_rung_replicate_resource_and_attempt_are_part_of_experiment_identity(self) -> None:
        from discoveryos.contracts.models import ExperimentSpec

        common = {
            "candidate_id": "cand_example",
            "evaluator_id": "eval",
            "fidelity": Fidelity.G1,
            "split_id": "development",
            "split_role": None,
            "seed": 7,
            "resources": ResourceBudget(cpu_seconds=1, wall_seconds=2),
            "contract_digest": "a" * 64,
            "mode": RunMode.DISCOVERY,
            "replicate_id": "replicate-7",
            "rung_id": "rung-low",
            "attempt_id": "attempt-0",
        }
        first = ExperimentSpec.create(**common)
        same = ExperimentSpec.create(**common)
        promoted = ExperimentSpec.create(**{**common, "rung_id": "rung-medium", "resources": ResourceBudget(cpu_seconds=2, wall_seconds=4)})
        retry = ExperimentSpec.create(**{**common, "attempt_id": "attempt-1"})
        replicate = ExperimentSpec.create(**{**common, "replicate_id": "replicate-8"})
        self.assertEqual(first.experiment_id, same.experiment_id)
        self.assertEqual(first.trial_id, promoted.trial_id)
        self.assertNotEqual(first.experiment_id, promoted.experiment_id)
        self.assertNotEqual(first.experiment_id, retry.experiment_id)
        self.assertNotEqual(first.trial_id, replicate.trial_id)
        self.assertNotEqual(first.resource_fingerprint, promoted.resource_fingerprint)


class ResourceAccountingTests(unittest.TestCase):
    def test_reconciled_actual_usage_releases_unused_reservation_and_marks_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = EvidenceLedger(Path(directory) / "ledger.sqlite3")
            limit = ResourceBudget(cpu_seconds=20, wall_seconds=20)
            first, added = ledger.reserve_resources(
                reservation_id="r1",
                experiment_id="e1",
                requested=ResourceBudget(cpu_seconds=10, wall_seconds=10),
                limit=limit,
            )
            self.assertTrue(added)
            reconciliation = ledger.reconcile_resources(
                first,
                ResourceUsage(cpu_seconds=2, wall_seconds=2, peak_rss_bytes=1024, exit_code=0),
                limit,
            )
            self.assertFalse(reconciliation.budget_exhausted)
            second, _ = ledger.reserve_resources(
                reservation_id="r2",
                experiment_id="e2",
                requested=ResourceBudget(cpu_seconds=18, wall_seconds=18),
                limit=limit,
            )
            overrun = ledger.reconcile_resources(
                second,
                ResourceUsage(cpu_seconds=19, wall_seconds=18, exit_code=0),
                limit,
            )
            self.assertTrue(overrun.budget_exhausted)
            self.assertIn("cpu_seconds", overrun.exceeded_dimensions)
            self.assertEqual(overrun, ledger.resource_reconciliation("r2"))

    def test_reservation_rejection_is_not_evaluable_and_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = initialize_demo(Path(directory))
            experiment = ExperimentSpec.create(
                candidate_id=context.baseline.candidate_id,
                evaluator_id=context.contract.evaluator_id_for(Fidelity.G0),
                fidelity=Fidelity.G0,
                split_id=None,
                split_role=None,
                seed=9,
                resources=ResourceBudget(cpu_seconds=999, wall_seconds=1),
                contract_digest=context.contract.digest,
                mode=RunMode.DISCOVERY,
            )
            evidence = asyncio.run(context.runner.executor.execute(context.baseline, experiment))
            self.assertEqual(FailureKind.BUDGET_EXHAUSTED, evidence.failure_kind)
            self.assertEqual(GateDecision.NOT_EVALUABLE, GateEngine().evaluate(context.contract, evidence).decision)
            replay = ReplayEngine(
                contract=context.contract,
                ledger=context.ledger,
                artifacts=context.artifacts,
                vault=context.vault,
                registry=context.registry,
            ).replay(evidence)
            self.assertTrue(replay.bindings_valid)
            self.assertTrue(replay.evaluator_reproduced)


class _StaticEvaluator:
    evaluator_id = "static_eval_v1"
    version = "1"

    def evaluate(self, candidate, experiment, data):
        return EvaluationOutput.from_metrics({"latency_ms": 1.0, "parameter_count": 4.0})


class _DevelopmentEvaluator:
    evaluator_id = "development_eval_v1"
    version = "1"

    def evaluate(self, candidate, experiment, data):
        return EvaluationOutput.from_metrics(
            {"false_clear": 0.0, "false_block": 0.1, "clearance_mae": 0.1, "temporal_jitter": 0.1, "latency_ms": 1.0}
        )


class _ExplodingEvaluator:
    evaluator_id = "exploding_eval_v1"
    version = "1"

    def evaluate(self, candidate, experiment, data):
        raise RuntimeError("boom")


class FidelityBindingAndFailureTests(unittest.TestCase):
    def test_scheduler_selects_the_frozen_evaluator_for_each_fidelity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = initialize_demo(Path(directory))
            registry = EvaluatorRegistry()
            registry.register(_StaticEvaluator())
            registry.register(_DevelopmentEvaluator())
            bindings = []
            for fidelity in context.contract.fidelities:
                evaluator_id = _StaticEvaluator.evaluator_id if fidelity is Fidelity.G0 else _DevelopmentEvaluator.evaluator_id
                bindings.append((fidelity.value, evaluator_id, registry.digest(evaluator_id)))
            contract = replace(context.contract, evaluator_bindings=tuple(bindings))
            self.assertEqual((), contract.validate())
            context.ledger.add_contract(contract)
            executor = ExperimentExecutor(
                contract=contract,
                ledger=context.ledger,
                artifacts=context.artifacts,
                vault=context.vault,
                registry=registry,
                fabric=ComputeFabric(cpu_workers=1),
            )
            runner = DiscoveryRunner(executor)
            g0 = asyncio.run(runner._run_stage([context.baseline], Fidelity.G0, 11))[0]
            g1 = asyncio.run(runner._run_stage([context.baseline], Fidelity.G1, 11))[0]
            self.assertEqual(_StaticEvaluator.evaluator_id, g0.evaluator_id)
            self.assertEqual(_DevelopmentEvaluator.evaluator_id, g1.evaluator_id)

    def test_evaluator_exception_has_an_independent_failure_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = initialize_demo(Path(directory))
            registry = EvaluatorRegistry()
            registry.register(_ExplodingEvaluator())
            bindings = tuple(
                (fidelity.value, _ExplodingEvaluator.evaluator_id, registry.digest(_ExplodingEvaluator.evaluator_id))
                for fidelity in context.contract.fidelities
            )
            contract = replace(context.contract, evaluator_bindings=bindings)
            executor = ExperimentExecutor(
                contract=contract,
                ledger=context.ledger,
                artifacts=context.artifacts,
                vault=context.vault,
                registry=registry,
                fabric=ComputeFabric(cpu_workers=1),
            )
            evidence = asyncio.run(DiscoveryRunner(executor)._run_stage([context.baseline], Fidelity.G0, 22))[0]
            self.assertEqual(FailureKind.EVALUATOR_EXCEPTION, evidence.failure_kind)
            self.assertEqual("EVALUATOR_EXCEPTION:RuntimeError", evidence.failure_signature)
            self.assertIsNotNone(evidence.resource_usage.exit_code)


if __name__ == "__main__":
    unittest.main()
