from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.local_patch_admission import _initialize_arm, _run_arm
from discoveryos.benchmarks.real_code_tasks import admission_tasks
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import ProviderGeneration
from discoveryos.providers.codex_exec import _usage_from_jsonl


class CorrectAdaptiveStepProvider:
    provider_name = "fixture_provider"
    model = "fixture_model"

    def generate(self, request):
        patch = (
            "diff --git a/algorithm.py b/algorithm.py\n"
            "--- a/algorithm.py\n"
            "+++ b/algorithm.py\n"
            "@@ -1,3 +1,9 @@\n"
            " # DiscoveryOS frozen baseline marker; no algorithm change.\n"
            " def choose_step(error):\n"
            "-    return 1\n"
            "+    if error == 0:\n"
            "+        return 0\n"
            "+    if error <= 1:\n"
            "+        return 1\n"
            "+    if error <= 5:\n"
            "+        return 2\n"
            "+    return 4\n"
        )
        return ProviderGeneration(
            raw_response=json.dumps(
                {
                    "hypothesis": "A monotone bounded step schedule matches the development objective.",
                    "expected_effects": {"score": "increase"},
                    "target_files": ["algorithm.py"],
                    "patch": patch,
                    "risks": ["Thresholds are specific to the bounded contract."],
                    "estimated_cost": {
                        "tokens": 100,
                        "cpu_seconds": 0,
                        "gpu_seconds": 0,
                        "device_seconds": 0,
                        "wall_seconds": 1,
                    },
                }
            ),
            usage=ResourceUsage(llm_input_tokens=70, llm_output_tokens=30, llm_cache_tokens=10, wall_seconds=0.1),
            latency_seconds=0.1,
            provider_version="fixture-1",
            provider_request_id="fixture-request",
            transport_log='{"type":"turn.completed","usage":{"input_tokens":70,"output_tokens":30,"cached_input_tokens":10}}',
        )


class RealCodeAdmissionTests(unittest.TestCase):
    def test_corpus_has_six_real_code_categories_and_runnable_baselines(self) -> None:
        tasks = admission_tasks()
        self.assertGreaterEqual(len(tasks), 6)
        self.assertEqual(len(tasks), len({task.category for task in tasks}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for task in tasks:
                repository, commit = task.initialize_repository(root)
                self.assertEqual(40, len(commit))
                public = subprocess.run(
                    ("python", "public_tests.py"),
                    cwd=repository,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(0, public.returncode, f"{task.task_id}: {public.stderr}")
                environment = os.environ.copy()
                environment["DISCOVERYOS_FIDELITY"] = "G2_DEVELOPMENT"
                evaluated = subprocess.run(
                    ("python", "evaluate.py"),
                    cwd=repository,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(0, evaluated.returncode, f"{task.task_id}: {evaluated.stderr}")
                payload = json.loads(evaluated.stdout)
                self.assertEqual(1.0, payload["metrics"]["valid"])
                self.assertLess(payload["metrics"]["score"], 1.0)

    def test_one_task_freezes_and_replays_a_real_generated_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = admission_tasks()[0]
            repository, commit = task.initialize_repository(root / "protocol")
            arm = _initialize_arm(root / "arm", task, repository, commit, token_ceiling=1000)
            report = asyncio.run(
                _run_arm(
                    arm,
                    task,
                    provider=CorrectAdaptiveStepProvider(),
                    iterations=1,
                    token_ceiling=1000,
                )
            )
            self.assertEqual(1.0, report["best_score"])
            self.assertTrue(report["improved"])
            self.assertEqual(100, report["tokens_to_first_improvement"])
            self.assertTrue(all(report["checks"].values()))

    def test_codex_jsonl_usage_is_accounted_separately(self) -> None:
        usage, request_id = _usage_from_jsonl(
            '\n'.join(
                (
                    '{"type":"thread.started","thread_id":"thread-1"}',
                    '{"type":"turn.completed","usage":{"input_tokens":120,"cached_input_tokens":20,"output_tokens":30}}',
                )
            )
        )
        self.assertEqual((120, 30, 20), usage)
        self.assertEqual("thread-1", request_id)


if __name__ == "__main__":
    unittest.main()
