from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from discoveryos.benchmarks.cmi_search_transmission_autopsy import audit_cmi_search_transmission
from discoveryos.util import digest_bytes, digest_json


class CmiSearchTransmissionAutopsyTests(unittest.TestCase):
    def test_consumed_trace_attributes_retention_and_refuses_false_lineage_counterfactual(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manifest_digest, report_sha, r7_path, r7_sha = self._fixture(root)

            result = audit_cmi_search_transmission(
                source,
                manifest_digest=manifest_digest,
                source_report_sha256=report_sha,
                r7_report_path=r7_path,
                r7_report_sha256=r7_sha,
                output_workspace=root / "autopsy",
            )

            self.assertEqual("CMI_SEARCH_TRANSMISSION_AUTOPSY_R1_COMPLETE", result["status"])
            self.assertEqual(
                {
                    "opportunities": 6,
                    "eligible": 5,
                    "invoked": 5,
                    "accepted_descendants": 5,
                    "retained": 0,
                    "authoritative_downstream_parent_was_cmi": 0,
                    "downstream_retained_contributions": 0,
                },
                result["transmission_funnel"],
            )
            self.assertEqual(5, result["candidate_competition"]["score_threshold_failures"])
            self.assertTrue(
                result["candidate_competition"]["all_cmi_descendants_valid_but_below_retention_threshold"]
            )
            self.assertEqual(5, result["lineage_authority"]["eligible_tasks_with_sequence_proxy_mismatch"])
            self.assertEqual(
                "NOT_IDENTIFIABLE_FROM_FROZEN_OFFLINE_TRACE",
                result["forced_retention_counterfactual"]["downstream_compounding_effect"],
            )
            self.assertEqual(0, result["model_calls"])
            self.assertEqual(0, result["evaluator_calls"])
            self.assertTrue(Path(result["record_path"]).is_file())

    def test_report_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manifest_digest, _, r7_path, r7_sha = self._fixture(root)
            with self.assertRaisesRegex(RuntimeError, "report SHA-256 mismatch"):
                audit_cmi_search_transmission(
                    source,
                    manifest_digest=manifest_digest,
                    source_report_sha256="0" * 64,
                    r7_report_path=r7_path,
                    r7_report_sha256=r7_sha,
                    output_workspace=root / "autopsy",
                )

    def _fixture(self, root: Path) -> tuple[Path, str, str, Path, str]:
        source = root / "source"
        manifest_dir = source / "protocol-artifacts" / "records"
        report_dir = source / "result-artifacts" / "records"
        task_dir = report_dir / "tasks"
        manifest_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)

        task_ids = [
            "assignment_01",
            "assignment_02",
            "assignment_03",
            "coverage_01",
            "coverage_02",
            "coverage_03",
        ]
        manifest_payload = {
            "protocol_id": "CMI_SEARCH_VALUE_R1_V3_INVALID_DESCENDANT_TERMINALIZATION",
            "experiment_code_sha": "fixture-code-sha",
            "paired_execution": {"downstream_steps": 1},
            "tasks": [{"task_id": task_id} for task_id in task_ids],
        }
        manifest_digest = digest_json(manifest_payload)
        manifest = {**manifest_payload, "manifest_digest": manifest_digest}
        manifest_path = manifest_dir / "cmi-search-value-r1-v3-manifest.json"
        self._write_json(manifest_path, manifest)

        report = {
            "protocol_id": manifest["protocol_id"],
            "manifest_digest": manifest_digest,
            "experiment_code_sha": manifest["experiment_code_sha"],
            "verdict": "CMI_SEARCH_VALUE_NOT_ESTABLISHED",
        }
        report_path = report_dir / "cmi-search-value-r1-v3-report.json"
        self._write_json(report_path, report)

        for index, task_id in enumerate(task_ids):
            category = "capacitated_cost_assignment" if task_id.startswith("assignment") else "budgeted_weighted_coverage"
            resolution = 0.003 if category.startswith("capacitated") else 0.005
            eligible = task_id != "coverage_02"
            prefix_score = 0.60 if category.startswith("capacitated") else 0.95
            cmi_score = prefix_score - (0.04 if category.startswith("capacitated") else 0.01)
            trace_digest = "r7-assignment-output" if category.startswith("capacitated") else "r7-coverage-output"
            task = {
                "protocol_id": manifest["protocol_id"],
                "manifest_digest": manifest_digest,
                "task_id": task_id,
                "task_category": category,
                "score_resolution": resolution,
                "causal_trace": {
                    "opportunity": True,
                    "eligible": eligible,
                    "invoked": eligible,
                    "accepted_descendant": eligible,
                    "retained_after_intervention": False,
                    "downstream_retained_contribution": False,
                    "operator_trace": {"candidate_source_digest": trace_digest} if eligible else None,
                },
                "arms": {
                    "CMI_ENABLED": {
                        "observations": self._observations(task_id, prefix_score, cmi_score, reported_parent="cmi")
                    },
                    "CMI_DISABLED": {
                        "observations": self._observations(task_id, prefix_score, prefix_score, reported_parent="control")
                    },
                },
            }
            self._write_json(task_dir / f"{task_id}.json", task)
            ledger_arm = "treatment" if eligible else "shared-prefix"
            self._ledger(source / "search" / task_id / ledger_arm / "ledger.sqlite3", task_id, eligible)

        r7 = {
            "verdict": "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED",
            "operator_admission": "CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES",
            "states": [],
        }
        for category, resolution, trace_digest in (
            ("capacitated_cost_assignment", 0.003, "r7-assignment-output"),
            ("budgeted_weighted_coverage", 0.005, "r7-coverage-output"),
        ):
            for index in range(3):
                r7["states"].append(
                    {
                        "task_category": category,
                        "score_resolution": resolution,
                        "arms": {"treatment": {"trace": {"candidate_source_digest": trace_digest}}},
                    }
                )
        r7_path = root / "r7-report.json"
        self._write_json(r7_path, r7)
        return (
            source,
            manifest_digest,
            digest_bytes(report_path.read_bytes()),
            r7_path,
            digest_bytes(r7_path.read_bytes()),
        )

    @staticmethod
    def _observations(task_id: str, prefix_score: float, intervention_score: float, *, reported_parent: str) -> list[dict]:
        return [
            {"candidate_id": f"{task_id}-prefix-1", "parent_id": None, "score": prefix_score},
            {"candidate_id": f"{task_id}-prefix", "parent_id": f"{task_id}-prefix-1", "score": prefix_score},
            {"candidate_id": f"{task_id}-cmi", "parent_id": f"{task_id}-prefix", "score": intervention_score},
            {"candidate_id": f"{task_id}-downstream", "parent_id": f"{task_id}-{reported_parent}", "score": prefix_score},
        ]

    @staticmethod
    def _ledger(path: Path, task_id: str, eligible: bool) -> None:
        path.parent.mkdir(parents=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE candidates(candidate_id TEXT, payload TEXT, created_at TEXT)")
            if eligible:
                candidates = [
                    {
                        "candidate_id": f"{task_id}-prefix",
                        "operator_id": "paired_prefix_replay",
                        "strategy_id": "cmi_search_value_r1",
                        "parent_ids": [f"{task_id}-baseline"],
                    },
                    {
                        "candidate_id": f"{task_id}-cmi",
                        "operator_id": "cmi_functional_basin_escape_v1",
                        "strategy_id": "cmi_search_value_r1",
                        "parent_ids": [f"{task_id}-prefix"],
                    },
                    {
                        "candidate_id": f"{task_id}-downstream",
                        "operator_id": "bounded_llm_local_patch_v1",
                        "strategy_id": "cmi_svr1_downstream_local",
                        "parent_ids": [f"{task_id}-prefix"],
                    },
                ]
                for index, candidate in enumerate(candidates):
                    connection.execute(
                        "INSERT INTO candidates VALUES (?, ?, ?)",
                        (candidate["candidate_id"], json.dumps(candidate), f"2026-01-01T00:00:0{index}Z"),
                    )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
