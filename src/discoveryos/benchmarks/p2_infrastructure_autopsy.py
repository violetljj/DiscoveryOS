from __future__ import annotations

import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Iterable


def analyze_p2_infrastructure(workspace: Path) -> dict[str, Any]:
    """Read an existing P2 factorial root without executing tasks or providers."""

    workspace = workspace.resolve()
    block_root = workspace / "result-artifacts" / "records" / "blocks"
    arm_records: list[dict[str, Any]] = []
    provider_calls: list[dict[str, Any]] = []
    transport_error_items: list[dict[str, str]] = []
    transport_timeout_mentions = 0
    transport_retry_mentions = 0

    for arm_path in sorted(block_root.glob("*/arms/*.json")):
        block_id = arm_path.parents[1].name
        arm = arm_path.stem
        record = json.loads(arm_path.read_text(encoding="utf-8"))
        ledger_path = workspace / "arms" / block_id / arm / "ledger.sqlite3"
        generations, evidence = _read_ledger(ledger_path)
        provider_seconds = sum(_usage(item).get("wall_seconds", 0.0) for item in generations)
        evaluator_seconds = sum(_usage(item).get("wall_seconds", 0.0) for item in evidence)
        evaluator_cpu_seconds = sum(_usage(item).get("cpu_seconds", 0.0) for item in evidence)
        command_seconds: dict[str, float] = {}
        runner_reported_seconds = 0.0
        artifact_root = workspace / "arms" / block_id / arm / "artifacts"
        for receipt in evidence:
            for digest in receipt.get("artifacts", ()):
                try:
                    artifact = _artifact_json(artifact_root, digest)
                except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                step = artifact.get("step")
                if step:
                    command_seconds[str(step)] = command_seconds.get(str(step), 0.0) + float(
                        artifact.get("wall_seconds", 0.0)
                    )
                elif "command_log_artifacts" in artifact:
                    runner_reported_seconds += float(
                        artifact.get("resource_usage", {}).get("wall_seconds", 0.0)
                    )
        actual = record.get("actual_usage", {})
        actual_wall = float(actual.get("wall_seconds", 0.0))
        actual_cpu = float(actual.get("cpu_seconds", 0.0))
        end_to_end = float(actual.get("end_to_end_makespan", actual_wall))
        accounted = provider_seconds + evaluator_seconds

        for generation in generations:
            usage = _usage(generation)
            call = {
                "block_id": block_id,
                "arm": arm,
                "generation_id": generation.get("generation_id"),
                "status": generation.get("status"),
                "failure_signature": generation.get("failure_signature"),
                "wall_seconds": float(usage.get("wall_seconds", 0.0)),
            }
            provider_calls.append(call)
            digest = generation.get("provenance_artifact_digest")
            if digest:
                provenance = _artifact_json(artifact_root, digest)
                transport_digest = provenance.get("transport_log_digest")
                if transport_digest:
                    raw = _artifact_bytes(artifact_root, transport_digest).decode("utf-8", errors="replace")
                    folded = raw.casefold()
                    transport_timeout_mentions += folded.count("timeout")
                    transport_retry_mentions += folded.count("retry")
                    for item in _transport_errors(raw):
                        transport_error_items.append({**call, **item})

        arm_records.append(
            {
                "block_id": block_id,
                "arm": arm,
                "status": record.get("status"),
                "failure": record.get("failure"),
                "generation_calls": int(record.get("generation_calls", len(generations))),
                "evaluator_calls": int(record.get("evaluator_calls", len(evidence))),
                "actual_wall_seconds": actual_wall,
                "actual_cpu_seconds": actual_cpu,
                "wall_cpu_ratio": actual_wall / actual_cpu if actual_cpu > 0 else None,
                "provider_wall_seconds": provider_seconds,
                "evaluator_wall_seconds": evaluator_seconds,
                "evaluator_cpu_seconds": evaluator_cpu_seconds,
                "evaluator_non_cpu_seconds": max(0.0, evaluator_seconds - evaluator_cpu_seconds),
                "recorded_git_patch_seconds": sum(
                    value for step, value in command_seconds.items() if step.startswith("patch_")
                ),
                "recorded_local_build_test_seconds": sum(
                    command_seconds.get(step, 0.0) for step in ("build", "test")
                ),
                "recorded_evaluator_command_seconds": command_seconds.get("evaluation", 0.0),
                "other_recorded_command_seconds": sum(
                    value
                    for step, value in command_seconds.items()
                    if not step.startswith("patch_") and step not in {"build", "test", "evaluation"}
                ),
                "runner_uninstrumented_seconds": max(
                    0.0, runner_reported_seconds - sum(command_seconds.values())
                ),
                "scheduler_evidence_overhead_seconds": evaluator_seconds - runner_reported_seconds,
                "end_to_end_seconds": end_to_end,
                "harness_git_io_residual_seconds": end_to_end - accounted,
                "accounting_delta_vs_actual_wall_seconds": actual_wall - accounted,
                "evaluator_failures": tuple(
                    item.get("failure_signature") for item in evidence if item.get("failure_signature")
                ),
            }
        )

    normal = [item for item in arm_records if item["status"] == "EVALUABLE"]
    durations = [float(item["wall_seconds"]) for item in provider_calls]
    generation_failures = [item for item in provider_calls if item["status"] != "SUCCEEDED"]
    failure_signatures: dict[str, int] = {}
    for item in generation_failures:
        signature = str(item.get("failure_signature"))
        failure_signatures[signature] = failure_signatures.get(signature, 0) + 1
    return {
        "analysis_version": "P2_INFRASTRUCTURE_AUTOPSY_V1",
        "source_root": str(workspace),
        "generation_calls_executed": 0,
        "arm_count": len(arm_records),
        "normal_evaluable_arm_count": len(normal),
        "arm_records": arm_records,
        "normal_arm_summary": {
            "actual_wall_seconds": _distribution(item["actual_wall_seconds"] for item in normal),
            "actual_cpu_seconds": _distribution(item["actual_cpu_seconds"] for item in normal),
            "wall_cpu_ratio": _distribution(
                item["wall_cpu_ratio"] for item in normal if item["wall_cpu_ratio"] is not None
            ),
            "harness_git_io_residual_seconds": _distribution(
                item["harness_git_io_residual_seconds"] for item in normal
            ),
        },
        "provider_summary": {
            "call_count": len(provider_calls),
            "duration_seconds": _distribution(durations),
            "generation_failure_count": len(generation_failures),
            "generation_failure_signatures": failure_signatures,
            "timeout_mention_count": transport_timeout_mentions,
            "retry_mention_count": transport_retry_mentions,
            "transport_error_item_count": len(transport_error_items),
            "transport_error_messages": sorted({item["message"] for item in transport_error_items}),
        },
        "provider_calls": provider_calls,
    }


def _read_ledger(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.is_file():
        return [], []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        generations = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM generation_records")]
        evidence = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM evidence")]
    finally:
        connection.close()
    return generations, evidence


def _usage(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("usage", payload.get("resource_usage", {}))
    return value if isinstance(value, dict) else {}


def _artifact_bytes(root: Path, digest: str) -> bytes:
    return (root / "objects" / digest[:2] / digest / "payload").read_bytes()


def _artifact_json(root: Path, digest: str) -> dict[str, Any]:
    return json.loads(_artifact_bytes(root, digest).decode("utf-8"))


def _transport_errors(raw: str) -> Iterable[dict[str, str]]:
    for line in raw.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = payload.get("item", {}) if isinstance(payload, dict) else {}
        if payload.get("type") == "item.completed" and item.get("type") == "error":
            yield {"message": str(item.get("message", ""))}


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    p95_index = max(0, int(0.95 * len(ordered) + 0.999999999) - 1)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read-only P2 factorial infrastructure autopsy")
    parser.add_argument("workspace", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(analyze_p2_infrastructure(arguments.workspace), indent=2, sort_keys=True))
