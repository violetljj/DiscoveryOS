from __future__ import annotations

import json
import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.search_policy_admission import evaluate_task_admission
from discoveryos.benchmarks.search_value_mvp0 import _score_source
from discoveryos.benchmarks.si2 import (
    _contamination_receipt,
    _holm_two,
    _one_sided_sign_p,
    _si2_headroom_evidence,
    _run_discoveryos_system_arm,
    _run_vanilla_strong_agent,
)
from discoveryos.benchmarks.local_patch_admission import _initialize_arm
from discoveryos.benchmarks.si2_shinka_adapter import shinka_evaluator_source
from discoveryos.benchmarks.si2_tasks import (
    normalized_source,
    si2_confirmation_tasks,
    si2_discovery_tasks,
)
from tests.test_strategy_integration_si1 import _CommentProvider


class Si2ProtocolTests(unittest.TestCase):
    def test_fresh_and_confirmation_tasks_are_disjoint_and_admitted(self) -> None:
        discovery = si2_discovery_tasks()
        confirmation = si2_confirmation_tasks()
        self.assertEqual(9, len(discovery))
        self.assertEqual(3, len(confirmation))
        receipt = _contamination_receipt(discovery, confirmation)
        self.assertTrue(all(receipt["checks"].values()), receipt)
        self.assertFalse(receipt["semantic_pretraining_contamination_ruled_out"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in (*discovery, *confirmation):
                repository, _ = item.task.initialize_repository(root)
                evidence, details = _si2_headroom_evidence(item, repository)
                admission = evaluate_task_admission(evidence)
                self.assertTrue(admission["admitted"], (item.task.task_id, admission, details))
                self.assertEqual("independent_difficulty_generator", evidence.reference_kind)
                self.assertGreaterEqual(admission["headroom_steps"], 4)

    def test_shinka_evaluator_wrapper_matches_native_frozen_evaluator(self) -> None:
        item = si2_discovery_tasks()[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, _ = item.task.initialize_repository(root / "native")
            expected = _score_source(item, repository, item.task.algorithm_source)
            program = root / "initial.py"
            program.write_text(normalized_source(item.task.algorithm_source), encoding="utf-8")
            evaluator = root / "evaluate_shinka.py"
            evaluator.write_text(
                shinka_evaluator_source(
                    normalized_source(item.task.public_tests_source),
                    normalized_source(item.task.evaluator_source),
                ),
                encoding="utf-8",
            )
            output = root / "result"
            env = os.environ.copy(); env["PYTHONUTF8"] = "1"
            completed = subprocess.run(
                (sys.executable, str(evaluator), "--program_path", str(program), "--results_dir", str(output)),
                env=env,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
            correct = json.loads((output / "correct.json").read_text(encoding="utf-8"))
            self.assertTrue(correct["correct"], correct)
            self.assertAlmostEqual(expected, metrics["combined_score"])

    def test_sign_test_and_holm_gate_are_exact_and_fail_closed(self) -> None:
        self.assertAlmostEqual(0.08984375, _one_sided_sign_p(7, 2))
        self.assertEqual(1.0, _one_sided_sign_p(0, 0))
        self.assertEqual({"core": True, "vanilla": True}, _holm_two({"core": 0.02, "vanilla": 0.08}, 0.10))
        self.assertEqual({"core": False, "vanilla": False}, _holm_two({"core": 0.06, "vanilla": 0.07}, 0.10))

    def test_three_internal_arm_paths_emit_matched_resource_reports(self) -> None:
        item = si2_discovery_tasks()[0]
        provider = _CommentProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, commit = item.task.initialize_repository(root / "tasks")
            core = _initialize_arm(root / "core", item.task, repository, commit, 100_000)
            current = _initialize_arm(root / "current", item.task, repository, commit, 100_000)
            vanilla = _initialize_arm(root / "vanilla", item.task, repository, commit, 100_000)
            core_report = asyncio.run(
                _run_discoveryos_system_arm(core, item, "CORE", provider, provider, current=False)
            )
            current_report = asyncio.run(
                _run_discoveryos_system_arm(
                    current, item, "CURRENT_DISCOVERYOS", provider, provider, current=True
                )
            )
            vanilla_report = asyncio.run(_run_vanilla_strong_agent(vanilla, item, provider))
        self.assertEqual(
            {"CORE", "CURRENT_DISCOVERYOS", "VANILLA_STRONG_AGENT"},
            {core_report["arm"], current_report["arm"], vanilla_report["arm"]},
        )
        for report in (core_report, current_report, vanilla_report):
            self.assertIn("best_improvement", report["metrics"])
            self.assertTrue(all(report["resource_checks"].values()), report)
            self.assertGreaterEqual(report["evaluator_calls"], 1)


if __name__ == "__main__":
    unittest.main()
