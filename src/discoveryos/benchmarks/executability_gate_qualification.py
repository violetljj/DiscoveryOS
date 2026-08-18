from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from datetime import datetime, timedelta
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
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.executability_gate import (
    BaselineProbeResult,
    ExecutabilityFailure,
    ExecutabilityGate,
    ExecutabilityPolicy,
    PowerEvent,
    PowerLeaseError,
    PowerLeaseReceipt,
    TimingBreakdown,
    WindowsPowerEventSource,
    WindowsPowerInhibitionLease,
)
from discoveryos.util import digest_bytes, digest_json


QUALIFICATION_VERSION = "DISCOVERYOS_EXECUTABILITY_GATE_QUALIFICATION_V1"
RECORD_NAME = "executability-gate-qualification-v1.json"
SOURCE_BLOCK_SEED = 17082601


def qualify_executability_gate(workspace: Path, v3_workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    v3_workspace = v3_workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError(f"qualification workspace is not empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        v3_workspace
        / "protocol-artifacts"
        / "records"
        / "p2-factorial-development-v3-manifest.json"
    )
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    task_records = {record["task_id"]: record for record in manifest["tasks"]}
    tasks = {item.task.task_id: item for item in _task_suite()}
    policy = ExecutabilityPolicy()
    live_receipts = []
    for task_id in sorted(tasks):
        source = (
            v3_workspace
            / "task-materialization"
            / f"{task_id}-seed-{SOURCE_BLOCK_SEED}"
            / task_id
            / "repo"
        )
        expected_tree = str(task_records[task_id]["task_repository_tree_digest"])
        gate = ExecutabilityGate(
            lease_factory=lambda reason: WindowsPowerInhibitionLease(reason),
            event_source=WindowsPowerEventSource(),
            policy=policy,
        )
        receipt = gate.execute(
            f"qualification-{task_id}",
            lambda item=tasks[task_id], source=source, expected_tree=expected_tree: _probe_baseline(
                item, source, expected_tree
            ),
        )
        live_receipts.append(asdict(receipt))

    adversarial = _adversarial_qualification()
    live_pass = all(receipt["admitted"] for receipt in live_receipts)
    adversarial_pass = all(case["matched_expected"] for case in adversarial)
    report_payload = {
        "qualification_version": QUALIFICATION_VERSION,
        "status": "EXECUTABILITY_GATE_QUALIFIED_ON_CONSUMED_L0_L2" if live_pass and adversarial_pass else "EXECUTABILITY_GATE_QUALIFICATION_FAILED",
        "claim_ceiling": "MECHANICS_AND_CONSUMED_DEVELOPMENT_ONLY",
        "source_v3_manifest_sha256": digest_bytes(manifest_bytes),
        "source_v3_protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "source_asset_level": "L2_CONSUMED_DEVELOPMENT_TASK",
        "task_count": len(live_receipts),
        "baseline_replays_per_task": 2,
        "generation_calls_executed": 0,
        "provider_calls_executed": 0,
        "fresh_or_sealed_assets_opened": 0,
        "policy": asdict(policy),
        "implementation_digests": {
            "executability_gate_source": digest_bytes(
                Path(__file__).parents[1].joinpath("runtime", "executability_gate.py").read_bytes()
            ),
            "qualification_source": digest_bytes(Path(__file__).read_bytes()),
        },
        "environment": {
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
        },
        "live_awake_receipts": live_receipts,
        "adversarial_fixtures": adversarial,
        "limits": {
            "new_p2_designed_or_sealed": False,
            "p2_v3_modified_or_reaggregated": False,
            "recovery_or_backfill_policy_decided": False,
            "p3_authorized": False,
        },
    }
    report = {**report_payload, "qualification_digest": digest_json(report_payload)}
    ArtifactStore(workspace / "artifacts").write_record(RECORD_NAME, report)
    return report


def _probe_baseline(item, source: Path, expected_tree: str) -> BaselineProbeResult:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="executability-gate-") as temporary:
        root = Path(temporary)
        repository = root / "source"
        source_commit = _git(source, "rev-parse", "HEAD")
        source_tree = _git(source, "rev-parse", "HEAD^{tree}")
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
        subprocess.run(
            ("git", "-C", str(repository), "checkout", "--quiet", source_commit),
            check=True,
            timeout=30,
        )
        clone_tree = _git(repository, "rev-parse", "HEAD^{tree}")
        arm = _initialize_arm(
            root / "arm",
            item.task,
            repository,
            source_commit,
            TOKEN_CEILING,
            cpu_ceiling=CPU_SECONDS_CEILING,
            wall_ceiling=WALL_SECONDS_CEILING,
            contract_created_at=P2_CONTRACT_CREATED_AT,
        )
        setup_seconds = time.monotonic() - started
        receipts = []
        outer_evaluation_seconds = []
        command_logs: list[dict[str, Any]] = []
        for replay_index in range(2):
            evaluation_started = time.monotonic()
            receipt = asyncio.run(
                _evaluate_at(
                    arm,
                    arm.baseline,
                    Fidelity.G1,
                    seed=SOURCE_BLOCK_SEED,
                    attempt=f"executability-gate-replay-{replay_index + 1}",
                )
            )
            outer_evaluation_seconds.append(time.monotonic() - evaluation_started)
            receipts.append(receipt)
            for digest in receipt.artifacts:
                artifact = json.loads(arm.artifacts.get_bytes(digest))
                if "step" in artifact:
                    command_logs.append(artifact)

        build_test_seconds = sum(
            float(log["wall_seconds"]) for log in command_logs if log["step"] in {"build", "test"}
        )
        evaluator_seconds = sum(
            float(log["wall_seconds"]) for log in command_logs if log["step"] == "evaluation"
        )
        patch_seconds = sum(
            float(log["wall_seconds"]) for log in command_logs if log["step"].startswith("patch_")
        )
        receipt_wall = sum(receipt.resource_usage.wall_seconds for receipt in receipts)
        harness_overhead = max(0.0, sum(outer_evaluation_seconds) - receipt_wall)
        total_wall = time.monotonic() - started
        scores = tuple(receipt.metric_dict().get("score", float("nan")) for receipt in receipts)
        valid_metrics = tuple(receipt.metric_dict().get("valid", float("nan")) for receipt in receipts)
        return BaselineProbeResult(
            materialization_replayed=source_tree == clone_tree == expected_tree,
            task_tree_digest_match=source_tree == clone_tree == expected_tree,
            evaluator_validities=tuple(receipt.validity.value for receipt in receipts),
            scores=scores,
            parser_contract_satisfied=all(value == 1.0 for value in valid_metrics),
            failure_signatures=tuple(receipt.failure_signature for receipt in receipts),
            timing=TimingBreakdown(
                repository_setup_seconds=setup_seconds + patch_seconds,
                build_test_seconds=build_test_seconds,
                evaluator_seconds=evaluator_seconds,
                harness_overhead_seconds=harness_overhead,
                cpu_seconds=sum(receipt.resource_usage.cpu_seconds for receipt in receipts),
                total_wall_seconds=total_wall,
            ),
            provenance={
                "task_id": item.task.task_id,
                "source_repository": str(source),
                "source_commit": source_commit,
                "source_tree": source_tree,
                "clone_tree": clone_tree,
                "expected_tree": expected_tree,
                "command_terminal_count": len(command_logs),
                "command_timed_out_count": sum(bool(log["timed_out"]) for log in command_logs),
                "score_finite": all(math.isfinite(score) for score in scores),
            },
        )


class _FixtureLease:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.acquired = False
        self.released = False

    def acquire(self) -> None:
        if self.fail:
            raise PowerLeaseError("injected lease failure")
        self.acquired = True

    def release(self) -> None:
        self.released = True

    @property
    def receipt(self) -> PowerLeaseReceipt:
        return PowerLeaseReceipt(
            acquired=self.acquired,
            provider="INJECTED_FIXTURE",
            request_types=("SYSTEM_REQUIRED",) if self.acquired else (),
            acquired_at_utc="fixture" if self.acquired else None,
            released_at_utc="fixture" if self.released else None,
            failure="injected lease failure" if self.fail else None,
        )


class _FixtureEvents:
    def __init__(self, kind: str | None = None) -> None:
        self.kind = kind

    def query(self, _start_utc: datetime, end_utc: datetime) -> tuple[PowerEvent, ...]:
        if self.kind is None:
            return ()
        event_id = 506 if self.kind == "ENTER_MODERN_STANDBY" else 42
        return (
            PowerEvent(
                record_id=event_id,
                provider="Microsoft-Windows-Kernel-Power",
                event_id=event_id,
                timestamp_utc=(end_utc - timedelta(microseconds=1)).isoformat(),
                kind=self.kind,
                message_sha256="0" * 64,
            ),
        )


def _fixture_baseline() -> BaselineProbeResult:
    return BaselineProbeResult(
        materialization_replayed=True,
        task_tree_digest_match=True,
        evaluator_validities=("VALID", "VALID"),
        scores=(0.5, 0.5),
        parser_contract_satisfied=True,
        failure_signatures=(None, None),
        timing=TimingBreakdown(
            repository_setup_seconds=1.0,
            build_test_seconds=1.0,
            evaluator_seconds=1.0,
            harness_overhead_seconds=1.0,
            cpu_seconds=0.5,
            total_wall_seconds=4.0,
        ),
    )


def _adversarial_qualification() -> list[dict[str, Any]]:
    timeout = replace(
        _fixture_baseline(),
        evaluator_validities=("NOT_EVALUABLE", "NOT_EVALUABLE"),
        failure_signatures=("TIMEOUT:test", "TIMEOUT:repository_setup"),
    )
    unexplained = replace(
        _fixture_baseline(),
        timing=replace(_fixture_baseline().timing, total_wall_seconds=100.0),
    )
    materialization = replace(_fixture_baseline(), task_tree_digest_match=False)
    cases = (
        ("awake", _FixtureLease(), _FixtureEvents(), _fixture_baseline(), None),
        (
            "suspend",
            _FixtureLease(),
            _FixtureEvents("ENTER_MODERN_STANDBY"),
            _fixture_baseline(),
            ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value,
        ),
        (
            "hibernate",
            _FixtureLease(),
            _FixtureEvents("ENTER_SLEEP_OR_HIBERNATE"),
            _fixture_baseline(),
            ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value,
        ),
        ("timeout", _FixtureLease(), _FixtureEvents(), timeout, ExecutabilityFailure.EXECUTION_TIMEOUT.value),
        (
            "unexplained_wall",
            _FixtureLease(),
            _FixtureEvents(),
            unexplained,
            ExecutabilityFailure.TIMING_RECONCILIATION.value,
        ),
        (
            "lease_failure",
            _FixtureLease(fail=True),
            _FixtureEvents(),
            _fixture_baseline(),
            ExecutabilityFailure.POWER_INHIBITION_UNAVAILABLE.value,
        ),
        (
            "materialization_drift",
            _FixtureLease(),
            _FixtureEvents(),
            materialization,
            ExecutabilityFailure.MATERIALIZATION.value,
        ),
    )
    results = []
    for name, lease, events, baseline, expected_failure in cases:
        receipt = ExecutabilityGate(
            lease_factory=lambda _reason, lease=lease: lease,
            event_source=events,
        ).execute(f"fixture-{name}", lambda baseline=baseline: baseline)
        results.append(
            {
                "fixture": name,
                "expected_failure_class": expected_failure,
                "observed_failure_class": receipt.failure_class,
                "admitted": receipt.admitted,
                "matched_expected": receipt.failure_class == expected_failure,
                "generation_calls_executed": receipt.generation_calls_executed,
            }
        )
    return results


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
    parser = argparse.ArgumentParser(description="Qualify the zero-generation Executability Gate")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("v3_workspace", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(qualify_executability_gate(arguments.workspace, arguments.v3_workspace), indent=2))
