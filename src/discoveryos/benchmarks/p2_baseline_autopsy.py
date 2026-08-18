from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.p2_factorial_protocol import (
    CPU_SECONDS_CEILING,
    P2_CONTRACT_CREATED_AT,
    TOKEN_CEILING,
    WALL_SECONDS_CEILING,
    _evaluate_at,
    _initialize_arm,
    _task_suite,
)
from discoveryos.contracts.models import Fidelity


ALPHA_BLOCKS = (
    "load_balance_alpha-seed-17082601",
    "load_balance_alpha-seed-17082602",
)
BETA_BLOCKS = (
    "load_balance_beta-seed-17082601",
    "load_balance_beta-seed-17082602",
)
TASK_FILES = ("algorithm.py", "public_tests.py", "evaluate.py", "requirements.lock")


def analyze_load_balance_baseline(workspace: Path, *, replay: bool = False) -> dict[str, Any]:
    """Autopsy the consumed V3 baseline without modifying its create-once root."""

    workspace = workspace.resolve()
    manifest = json.loads(
        (workspace / "protocol-artifacts" / "records" / "p2-factorial-development-v3-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    task_records = {item["task_id"]: item for item in manifest["tasks"]}
    alpha = [_inspect_block(workspace, block_id) for block_id in ALPHA_BLOCKS]
    beta = [_inspect_block(workspace, block_id) for block_id in BETA_BLOCKS]
    report: dict[str, Any] = {
        "analysis_version": "P2_LOAD_BALANCE_BASELINE_AUTOPSY_V1",
        "source_root": str(workspace),
        "generation_calls_executed": 0,
        "alpha_failures": alpha,
        "alpha_beta_differential": {
            "manifest": {
                task_id: {
                    key: task_records[task_id][key]
                    for key in (
                        "task_payload_digest",
                        "initial_state_digest",
                        "baseline_source_digest",
                        "evaluator_digest",
                        "reference_digest",
                        "intermediate_digests",
                        "baseline_replays",
                        "task_repository_tree_digest",
                    )
                }
                for task_id in ("load_balance_alpha", "load_balance_beta")
            },
            "file_digests": {
                "alpha": alpha[0]["materialized_file_digests"],
                "beta": beta[0]["materialized_file_digests"],
            },
            "identical_files": [
                name
                for name in TASK_FILES
                if alpha[0]["materialized_file_digests"][name]
                == beta[0]["materialized_file_digests"][name]
            ],
            "different_files": [
                name
                for name in TASK_FILES
                if alpha[0]["materialized_file_digests"][name]
                != beta[0]["materialized_file_digests"][name]
            ],
            "beta_baseline_receipts": [item["receipt"] for item in beta],
        },
    }
    if replay:
        report["exact_replays"] = [_replay_materialized_baseline(workspace, block_id) for block_id in ALPHA_BLOCKS]
    return report


def _inspect_block(workspace: Path, block_id: str) -> dict[str, Any]:
    arm_root = workspace / "arms" / block_id / "neither"
    ledger_path = arm_root / "ledger.sqlite3"
    connection = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
    try:
        receipt = json.loads(connection.execute("SELECT payload FROM evidence ORDER BY created_at LIMIT 1").fetchone()[0])
        candidate = json.loads(connection.execute("SELECT payload FROM candidates ORDER BY created_at LIMIT 1").fetchone()[0])
    finally:
        connection.close()
    bundle = _artifact_json(arm_root / "artifacts", candidate["artifact_digest"])
    repository = Path(bundle["candidate_manifest"]["base_repository"])
    command_logs = []
    for digest in receipt["artifacts"]:
        artifact = _artifact_json(arm_root / "artifacts", digest)
        if "step" in artifact:
            command_logs.append(artifact)
    return {
        "block_id": block_id,
        "receipt": {
            "validity": receipt["validity"],
            "failure_kind": receipt["failure_kind"],
            "failure_signature": receipt["failure_signature"],
            "metrics": receipt["metrics"],
            "resource_usage": receipt["resource_usage"],
        },
        "baseline_bundle": bundle["candidate_manifest"],
        "command_logs": command_logs,
        "materialized_file_digests": {
            name: hashlib.sha256((repository / name).read_bytes()).hexdigest() for name in TASK_FILES
        },
    }


def _replay_materialized_baseline(workspace: Path, block_id: str) -> dict[str, Any]:
    task_id = "load_balance_alpha"
    seed = int(block_id.rsplit("-seed-", 1)[1])
    source = (workspace / "task-materialization" / block_id / task_id / "repo").resolve()
    commit = _git(source, "rev-parse", "HEAD")
    item = next(item for item in _task_suite() if item.task.task_id == task_id)
    with tempfile.TemporaryDirectory(prefix="p2-baseline-autopsy-") as temporary:
        root = Path(temporary)
        repository = root / "source"
        subprocess.run(
            (
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "-c",
                "core.autocrlf=false",
                str(source),
                str(repository),
            ),
            check=True,
            timeout=30,
        )
        subprocess.run(("git", "-C", str(repository), "checkout", "--quiet", commit), check=True, timeout=30)
        arm = _initialize_arm(
            root / "arm",
            item.task,
            repository,
            commit,
            TOKEN_CEILING,
            cpu_ceiling=CPU_SECONDS_CEILING,
            wall_ceiling=WALL_SECONDS_CEILING,
            contract_created_at=P2_CONTRACT_CREATED_AT,
        )
        receipt = asyncio.run(
            _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=seed, attempt="baseline-autopsy-replay")
        )
        return {
            "block_id": block_id,
            "source_commit": commit,
            "validity": receipt.validity.value,
            "failure_kind": receipt.failure_kind.value if receipt.failure_kind else None,
            "failure_signature": receipt.failure_signature,
            "metrics": dict(receipt.metrics),
            "resource_usage": {
                "wall_seconds": receipt.resource_usage.wall_seconds,
                "cpu_seconds": receipt.resource_usage.cpu_seconds,
                "exit_code": receipt.resource_usage.exit_code,
            },
        }


def _artifact_json(root: Path, digest: str) -> dict[str, Any]:
    return json.loads((root / "objects" / digest[:2] / digest / "payload").read_text(encoding="utf-8"))


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repository), *arguments),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    ).stdout.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2 V3 load-balance baseline autopsy")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--replay", action="store_true", help="replay the untouched alpha baseline in temp roots")
    arguments = parser.parse_args()
    print(json.dumps(analyze_load_balance_baseline(arguments.workspace, replay=arguments.replay), indent=2))
