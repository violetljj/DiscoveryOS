from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.br_a_tasks import br_a_tasks
from discoveryos.benchmarks.local_patch_readmission import seal_local_patch_readmission
from discoveryos.benchmarks.real_code_tasks import admission_tasks
from discoveryos.util import digest_json


class FrozenFixtureProvider:
    provider_name = "fixture_provider"
    model = "fixture_model"
    provider_version = "fixture-1"
    settings_digest = digest_json(
        {"provider": provider_name, "model": model, "reasoning_effort": "medium"}
    )


class LocalPatchReadmissionTests(unittest.TestCase):
    def test_fresh_corpus_is_disjoint_runnable_and_has_headroom(self) -> None:
        fresh = br_a_tasks()
        consumed = admission_tasks()
        self.assertEqual(8, len(fresh))
        self.assertFalse({task.task_id for task in fresh} & {task.task_id for task in consumed})
        self.assertFalse({task.category for task in fresh} & {task.category for task in consumed})
        self.assertFalse({task.entrypoint for task in fresh} & {task.entrypoint for task in consumed})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for task in fresh:
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
                self.assertLess(payload["metrics"]["score"], 1.0, task.task_id)

    def test_seal_freezes_required_manifest_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = seal_local_patch_readmission(Path(directory), provider=FrozenFixtureProvider())
            self.assertEqual("SEALED", result["status"])
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(8, result["task_count"])
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual("executable-candidate-v3", manifest["candidate_bundle_version"])
            self.assertEqual("recount_hunks", manifest["repair_policy"])
            self.assertEqual(90_000, manifest["token_budget"]["per_task_per_llm_arm"])
            self.assertEqual(result["admission_manifest_digest"], manifest["admission_manifest_digest"])


if __name__ == "__main__":
    unittest.main()
