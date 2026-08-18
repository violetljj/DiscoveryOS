from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.benchmark_bank import (
    IntegrationStatus,
    load_benchmark_bank,
    materialize_bank_instance,
)
from discoveryos.runtime.executability_gate import (
    BaselineProbeResult,
    ExecutabilityFailure,
    ExecutabilityGate,
    TimingBreakdown,
    WindowsPowerEventSource,
    WindowsPowerInhibitionLease,
    _overlapping_power_events,
)
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "DISCOVERYOS_P2_ADA_EVOX_FACTORIAL_DEVELOPMENT_V4"
REGISTRY_DIGEST = "8428268400f6c23c13e58b0476b08c25e0870980feb081c7481063efd7b97a0a"
QUOTAS = {"R0": 6, "R1": 6, "R2": 12}
ARM_IDS = ("neither", "ada_only", "evox_only", "ada_evox")
V41_ADAPTER_ID = "discoveryos.algotune_p2v41_deterministic_dev.v1"


def _rank(registry_digest: str, family_id: str, instance_id: str) -> str:
    return hashlib.sha256(
        f"{PROTOCOL_ID}|{registry_digest}|{family_id}|{instance_id}".encode("utf-8")
    ).hexdigest()


def select_cohort(registry_path: Path) -> dict[str, Any]:
    registry = load_benchmark_bank(registry_path.resolve())
    registry_digest = digest_json(registry)
    if registry_digest != REGISTRY_DIGEST:
        raise RuntimeError("P2 V4 registry digest differs from the frozen V4.1 revision")
    eligible = [
        family
        for family in registry["families"]
        if family.get("integration_status") == IntegrationStatus.DEVELOPMENT_READY.value
        and family.get("source_id") == "algotune"
        and family.get("evidence_role") == "CONTRACT_DERIVED_DEVELOPMENT"
        and family.get("adapter_id") == V41_ADAPTER_ID
        and family.get("difficulty_tier") in QUOTAS
    ]
    selected = []
    for family in eligible:
        ranked_instances = sorted(
            (
                (_rank(registry_digest, family["family_id"], instance_id), instance_id)
                for instance_id in family["instance_ids"]
            )
        )
        instance_rank, instance_id = ranked_instances[0]
        selected.append(
            {
                "family_id": family["family_id"],
                "difficulty_tier": family["difficulty_tier"],
                "instance_id": instance_id,
                "selection_rank": instance_rank,
                "adapter_id": family["adapter_id"],
                "evaluator_regime": family["development_binding"]["evaluator_regime"],
            }
        )
    selected.sort(key=lambda item: (item["difficulty_tier"], item["selection_rank"]))
    counts = {
        tier: sum(item["difficulty_tier"] == tier for item in selected) for tier in QUOTAS
    }
    if counts != QUOTAS or len({item["family_id"] for item in selected}) != 24:
        raise RuntimeError(f"P2 V4 cohort quota mismatch: {counts}")
    schedule = []
    for index, unit in enumerate(selected, start=1):
        attempt_orders = []
        for attempt in (0, 1):
            order = sorted(
                ARM_IDS,
                key=lambda arm: hashlib.sha256(
                    f"{unit['selection_rank']}|attempt={attempt}|{arm}".encode("utf-8")
                ).hexdigest(),
            )
            attempt_orders.append(tuple(order))
        schedule.append(
            {
                **unit,
                "block_index": index,
                "block_id": f"p2v4-{index:02d}-{unit['family_id']}",
                "primary_arm_order": attempt_orders[0],
                "infra_retry_arm_order": attempt_orders[1],
            }
        )
    payload = {
        "protocol_id": PROTOCOL_ID,
        "registry_digest": registry_digest,
        "selection_rule": "minimum SHA256(protocol|registry|family|instance) per family",
        "quotas": QUOTAS,
        "units": tuple(schedule),
        "generation_calls": 0,
        "fresh_or_sealed_assets_opened": 0,
    }
    return {**payload, "cohort_plan_digest": digest_json(payload)}


def _tree_digest(root: Path) -> str:
    return digest_json(
        tuple(
            (path.relative_to(root).as_posix(), digest_bytes(path.read_bytes()))
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        )
    )


def _run_command(root: Path, script: str, timeout: float = 180.0) -> tuple[subprocess.CompletedProcess[str], float]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    result = subprocess.run(
        (sys.executable, script),
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return result, time.monotonic() - started


def _materialize_and_probe(
    registry_path: Path, unit: dict[str, Any], unit_root: Path
) -> tuple[BaselineProbeResult, dict[str, Any]]:
    started = time.monotonic()
    copies = []
    setup_seconds = 0.0
    for name in ("primary", "replay"):
        copy_root = unit_root / name
        setup_started = time.monotonic()
        report = materialize_bank_instance(
            registry_path,
            family_id=unit["family_id"],
            instance_id=unit["instance_id"],
            output_dir=copy_root,
        )
        setup_seconds += time.monotonic() - setup_started
        copies.append((copy_root, report, _tree_digest(copy_root)))
    replayed = (
        copies[0][1]["resolution"]["instance_digest"]
        == copies[1][1]["resolution"]["instance_digest"]
    )
    tree_match = copies[0][2] == copies[1][2]
    scores: list[float] = []
    validities: list[str] = []
    signatures: list[str | None] = []
    evaluator_seconds = 0.0
    build_seconds = 0.0
    payloads = []
    initial_trees = tuple(item[2] for item in copies)
    for copy_root, _report, _tree in copies:
        public, elapsed = _run_command(copy_root, "public_tests.py")
        build_seconds += elapsed
        if public.returncode != 0:
            validities.append("NOT_EVALUABLE")
            scores.append(0.0)
            signatures.append(f"PUBLIC_TEST:{public.returncode}")
            payloads.append(None)
            continue
        evaluated, elapsed = _run_command(copy_root, "evaluate.py")
        evaluator_seconds += elapsed
        if evaluated.returncode != 0:
            validities.append("NOT_EVALUABLE")
            scores.append(0.0)
            signatures.append(f"EVALUATOR:{evaluated.returncode}")
            payloads.append(None)
            continue
        try:
            payload = json.loads(evaluated.stdout.splitlines()[-1])
            score = float(payload["metrics"]["score"])
            valid = float(payload["metrics"]["valid"]) == 1.0
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            payload = None
            score = 0.0
            valid = False
            signatures.append(f"PARSER:{type(error).__name__}")
        else:
            signatures.append(None if valid else "EVALUATOR_INVALID")
        validities.append("VALID" if valid else "INVALID")
        scores.append(score)
        payloads.append(payload)
    final_trees = tuple(_tree_digest(item[0]) for item in copies)
    tree_match = tree_match and initial_trees == final_trees
    total = time.monotonic() - started
    timing = TimingBreakdown(
        repository_setup_seconds=setup_seconds,
        build_test_seconds=build_seconds,
        evaluator_seconds=evaluator_seconds,
        harness_overhead_seconds=max(0.0, total - setup_seconds - build_seconds - evaluator_seconds),
        total_wall_seconds=total,
    )
    probe = BaselineProbeResult(
        materialization_replayed=replayed,
        task_tree_digest_match=tree_match,
        evaluator_validities=tuple(validities),
        scores=tuple(scores),
        parser_contract_satisfied=all(payload is not None for payload in payloads),
        failure_signatures=tuple(signatures),
        timing=timing,
        provenance={
            "instance_digests": tuple(item[1]["resolution"]["instance_digest"] for item in copies),
            "tree_digests": initial_trees,
            "final_tree_digests": final_trees,
            "evaluator_payloads": tuple(payloads),
        },
    )
    validator = ExecutabilityGate(
        lease_factory=lambda _reason: WindowsPowerInhibitionLease(_reason),
        event_source=WindowsPowerEventSource(),
    )
    failure, detail = validator._validate_baseline(probe)
    return probe, {
        "status": "EXECUTABILITY_GATE_PASS" if failure is None else "EXECUTABILITY_GATE_FAIL_CLOSED",
        "admitted": failure is None,
        "failure_class": failure.value if failure else None,
        "failure_detail": detail,
        "probe": jsonable(probe),
    }


def run_full_cohort_gate(
    workspace: Path,
    *,
    registry_path: Path,
    lease_factory: Callable[[str], Any] = WindowsPowerInhibitionLease,
    event_source: Any | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    plan = select_cohort(registry_path)
    (workspace / "cohort-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source = event_source or WindowsPowerEventSource()
    lease = lease_factory("DiscoveryOS P2 V4 full-cohort Executability Gate")
    session_start = datetime.now(timezone.utc)
    failure_class = None
    failure_detail = None
    events = ()
    unit_receipts = []
    try:
        try:
            lease.acquire()
        except BaseException as error:
            failure_class = ExecutabilityFailure.POWER_INHIBITION_UNAVAILABLE.value
            failure_detail = f"{type(error).__name__}:{error}"
        if failure_class is not None:
            raise RuntimeError(failure_detail)
        queried = source.query(session_start - timedelta(days=1), datetime.now(timezone.utc))
        events = _overlapping_power_events(queried, session_start, datetime.now(timezone.utc))
        if events:
            failure_class = ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value
            failure_detail = "host was already in a low-power state at cohort Gate start"
        if failure_class is None:
            materialized = workspace / "materialized"
            materialized.mkdir()
            for unit in plan["units"]:
                probe, receipt = _materialize_and_probe(
                    registry_path.resolve(), unit, materialized / unit["block_id"]
                )
                unit_receipts.append({**unit, **receipt})
                if not receipt["admitted"]:
                    failure_class = receipt["failure_class"]
                    failure_detail = f"{unit['block_id']}:{receipt['failure_detail']}"
                    break
        queried = source.query(session_start - timedelta(days=1), datetime.now(timezone.utc))
        overlap = _overlapping_power_events(queried, session_start, datetime.now(timezone.utc))
        events = tuple(dict.fromkeys((*events, *overlap)))
        if overlap:
            failure_class = ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value
            failure_detail = "host low-power state overlaps the full-cohort Gate"
    except BaseException as error:
        if failure_class is None:
            failure_class = (
                ExecutabilityFailure.POWER_PROVENANCE.value
                if unit_receipts == []
                else ExecutabilityFailure.BASELINE_EXECUTION.value
            )
            failure_detail = f"{type(error).__name__}:{error}"
    finally:
        try:
            lease.release()
        except BaseException as error:
            failure_class = ExecutabilityFailure.POWER_INHIBITION_RELEASE.value
            failure_detail = f"{type(error).__name__}:{error}"
    admitted = failure_class is None and len(unit_receipts) == 24
    receipt_payload = {
        "version": "DISCOVERYOS_P2_V4_FULL_COHORT_GATE_V1",
        "protocol_id": PROTOCOL_ID,
        "cohort_plan_digest": plan["cohort_plan_digest"],
        "status": "P2_V4_FULL_COHORT_GATE_PASS" if admitted else "P2_V4_FULL_COHORT_GATE_FAIL_CLOSED",
        "admitted": admitted,
        "failure_class": failure_class,
        "failure_detail": failure_detail,
        "session_started_utc": session_start.isoformat(),
        "session_finished_utc": datetime.now(timezone.utc).isoformat(),
        "power_lease": jsonable(lease.receipt),
        "power_events": jsonable(events),
        "unit_receipts": tuple(unit_receipts),
        "passed_units": sum(item["admitted"] for item in unit_receipts),
        "required_units": 24,
        "generation_calls": 0,
        "provider_calls": 0,
        "fresh_or_sealed_assets_opened": 0,
    }
    receipt = {**receipt_payload, "receipt_digest": digest_json(receipt_payload)}
    (workspace / "gate-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _main() -> int:
    parser = argparse.ArgumentParser(description="P2 V4 fast-close cohort selector and zero-model Gate")
    parser.add_argument("action", choices=("plan", "gate"))
    parser.add_argument("--registry", type=Path, default=Path("benchmarks/bank/v1/registry.json"))
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        result = select_cohort(args.registry)
    else:
        if args.workspace is None:
            parser.error("gate requires --workspace")
        result = run_full_cohort_gate(args.workspace, registry_path=args.registry)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("admitted", True) else 2


if __name__ == "__main__":
    raise SystemExit(_main())
