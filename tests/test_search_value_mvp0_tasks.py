from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.br_a_tasks import br_a_tasks
from discoveryos.benchmarks.real_code_tasks import admission_tasks
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source, search_value_mvp0_tasks


class SearchValueMvp0TaskTests(unittest.TestCase):
    def test_tasks_are_fresh_executable_and_have_independent_residual_headroom(self) -> None:
        tasks = search_value_mvp0_tasks()
        consumed = {task.task_id for task in (*admission_tasks(), *br_a_tasks())}
        self.assertEqual(8, len(tasks))
        self.assertFalse({item.task.task_id for item in tasks} & consumed)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in tasks:
                repository, _ = item.task.initialize_repository(root)
                baseline = self._score(repository, item.task.entrypoint, item.task.algorithm_source)
                replay = self._score(repository, item.task.entrypoint, item.task.algorithm_source)
                reference = self._score(repository, item.task.entrypoint, item.reference_source)
                intermediates = tuple(
                    self._score(repository, item.task.entrypoint, source)
                    for source in item.intermediate_sources
                )
                self.assertAlmostEqual(baseline, replay, msg=item.task.task_id)
                self.assertAlmostEqual(1.0, reference, places=10, msg=item.task.task_id)
                self.assertGreaterEqual(
                    (reference - baseline) / item.score_resolution,
                    4.0,
                    item.task.task_id,
                )
                magnitudes = {
                    round((score - baseline) / item.score_resolution, 8)
                    for score in (*intermediates, reference)
                    if score - baseline >= item.score_resolution - 1e-12
                }
                self.assertGreaterEqual(len(magnitudes), 2, (item.task.task_id, baseline, intermediates))

    @staticmethod
    def _score(repository: Path, entrypoint: str, source: str) -> float:
        path = repository / entrypoint
        original = path.read_text(encoding="utf-8")
        path.write_text(normalized_source(source), encoding="utf-8")
        environment = os.environ.copy()
        environment["DISCOVERYOS_FIDELITY"] = "G2_DEVELOPMENT"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            public = subprocess.run(
                ("python", "public_tests.py"),
                cwd=repository,
                env=environment,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if public.returncode != 0:
                raise AssertionError(public.stderr)
            evaluated = subprocess.run(
                ("python", "evaluate.py"),
                cwd=repository,
                env=environment,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if evaluated.returncode != 0:
                raise AssertionError(evaluated.stderr)
            return float(json.loads(evaluated.stdout.splitlines()[-1])["metrics"]["score"])
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
