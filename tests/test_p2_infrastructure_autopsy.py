import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.p2_infrastructure_autopsy import analyze_p2_infrastructure


class P2InfrastructureAutopsyTests(unittest.TestCase):
    def test_read_only_accounting_separates_provider_commands_and_residual(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arm_root = root / "arms" / "task-seed-1" / "neither"
            records = root / "result-artifacts" / "records" / "blocks" / "task-seed-1" / "arms"
            records.mkdir(parents=True)
            (records / "neither.json").write_text(
                json.dumps(
                    {
                        "status": "EVALUABLE",
                        "generation_calls": 1,
                        "evaluator_calls": 1,
                        "actual_usage": {
                            "wall_seconds": 12.0,
                            "cpu_seconds": 1.0,
                            "end_to_end_makespan": 13.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            arm_root.mkdir(parents=True)
            connection = sqlite3.connect(arm_root / "ledger.sqlite3")
            connection.execute("CREATE TABLE generation_records(payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE evidence(payload TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO generation_records VALUES (?)",
                (json.dumps({"generation_id": "g1", "status": "SUCCEEDED", "usage": {"wall_seconds": 4}}),),
            )
            connection.execute(
                "INSERT INTO evidence VALUES (?)",
                (json.dumps({"resource_usage": {"wall_seconds": 8, "cpu_seconds": 1}, "artifacts": []}),),
            )
            connection.commit()
            connection.close()

            report = analyze_p2_infrastructure(root)

            arm = report["arm_records"][0]
            self.assertEqual(0, report["generation_calls_executed"])
            self.assertEqual(4.0, arm["provider_wall_seconds"])
            self.assertEqual(8.0, arm["evaluator_wall_seconds"])
            self.assertEqual(1.0, arm["harness_git_io_residual_seconds"])
            self.assertEqual(0.0, arm["accounting_delta_vs_actual_wall_seconds"])


if __name__ == "__main__":
    unittest.main()
