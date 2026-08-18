import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.p2_baseline_autopsy import _replay_materialized_baseline
from discoveryos.benchmarks.p2_factorial_protocol import _task_suite


class P2BaselineAutopsyTests(unittest.TestCase):
    def test_replay_preserves_materialized_bytes_and_produces_valid_finite_baseline(self) -> None:
        item = next(item for item in _task_suite() if item.task.task_id == "load_balance_alpha")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            block_id = "load_balance_alpha-seed-17082601"
            item.task.initialize_repository(root / "task-materialization" / block_id)

            replay = _replay_materialized_baseline(root, block_id)

            self.assertEqual("VALID", replay["validity"])
            self.assertIsNone(replay["failure_signature"])
            self.assertEqual(1.0, replay["metrics"]["valid"])
            self.assertAlmostEqual(0.3565120065120065, replay["metrics"]["score"])


if __name__ == "__main__":
    unittest.main()
