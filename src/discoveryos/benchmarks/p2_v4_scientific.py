from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.p2_factorial_protocol import (
    ARM_IDS,
    CPU_SECONDS_CEILING,
    GENERATION_CALL_CEILING,
    P2_CONTRACT_CREATED_AT,
    PROVIDER_TIMEOUT_SECONDS,
    SEARCH_STEP_CEILING,
    TOKEN_CEILING,
    WALL_SECONDS_CEILING,
    _aggregate_p2_factorial,
    _evaluate_at,
    _git_tree_digest,
    _one_sided_sign_p,
    _p2_arm_terminal,
    _p2_block_terminal,
    _p2_harness_run_manifest,
    _p2_search_spec,
    inspect_provider,
)
from discoveryos.benchmarks.p2_v4_fast_close import (
    PROTOCOL_ID,
    _materialize_and_probe,
)
from discoveryos.benchmarks.real_code_tasks import RealCodeTask
from discoveryos.benchmarks.search_value_mvp0 import (
    STRUCTURAL_PATCH_SCHEMA,
    mvp0_controller_config,
)
from discoveryos.benchmarks.task_types import SearchValueTask
from discoveryos.contracts.models import EvidenceValidity, Fidelity
from discoveryos.harness import (
    HarnessSearchRuntime,
    P2ZeroModelRuntimeSurface,
    audit_p2_factorial_profiles,
    audit_p2_zero_model_runtime_fairness,
    capture_git_source_snapshot,
    harness_code_bundle_digest,
    static_composition_profiles,
)
from discoveryos.operators.action_controller import DeterministicActionController
from discoveryos.providers.codex_exec import CodexExecProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.executability_gate import (
    ExecutabilityFailure,
    ExecutabilityGate,
    ScientificBlockResult,
    TimingBreakdown,
    WindowsPowerEventSource,
    WindowsPowerInhibitionLease,
)
from discoveryos.util import digest_bytes, digest_json, jsonable


MANIFEST_RECORD = "p2-factorial-development-v4-manifest.json"
REPORT_RECORD = "p2-factorial-development-v4-report.json"
RECOVERABLE_INFRA = {
    ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value,
    ExecutabilityFailure.POWER_INHIBITION_UNAVAILABLE.value,
    ExecutabilityFailure.POWER_INHIBITION_RELEASE.value,
}


def _source_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def _task_from_gate(gate_root: Path, unit: dict[str, Any]) -> SearchValueTask:
    root = gate_root / "materialized" / unit["block_id"] / "primary"
    contract = json.loads((root / "task-contract.json").read_text(encoding="utf-8"))
    task = RealCodeTask(
        task_id=unit["instance_id"],
        category=unit["family_id"],
        question=(
            f"Optimize {unit['family_id']} solve(problem) for fewer deterministic CPython 3.11 "
            "opcodes while preserving every public test and evaluator validity constraint."
        ),
        algorithm_source=(root / "algorithm.py").read_text(encoding="utf-8"),
        public_tests_source=(root / "public_tests.py").read_text(encoding="utf-8"),
        evaluator_source=(root / "evaluate.py").read_text(encoding="utf-8"),
    )
    return SearchValueTask(
        task=task,
        reference_source=task.algorithm_source,
        intermediate_sources=(),
        score_resolution=float(contract["score_resolution"]),
        baseline_basin_id=f"bank:{unit['family_id']}",
        trajectory_classes=("LOCAL_REFINEMENT", "STRUCTURAL_ESCAPE"),
    )


def build_manifest(
    *,
    repository: Path,
    gate_root: Path,
    provider_executable: Path,
) -> dict[str, Any]:
    gate_root = gate_root.resolve()
    gate_path = gate_root / "gate-receipt.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("admitted") or gate.get("passed_units") != 24:
        raise RuntimeError("P2 V4 scientific seal requires a 24/24 admitted cohort Gate")
    if gate.get("generation_calls") != 0 or gate.get("provider_calls") != 0:
        raise RuntimeError("P2 V4 cohort Gate was not zero-model")
    snapshot = capture_git_source_snapshot(repository.resolve())
    if not snapshot.worktree_clean:
        raise RuntimeError("P2 V4 seal requires a clean worktree")
    provider = inspect_provider(provider_executable)
    profile_audit = audit_p2_factorial_profiles()
    task_records = []
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        for unit in gate["unit_receipts"]:
            item = _task_from_gate(gate_root, unit)
            task_repository, _commit = item.task.initialize_repository(temp / unit["block_id"])
            materialized = gate_root / "materialized" / unit["block_id"] / "primary"
            contract = json.loads((materialized / "task-contract.json").read_text(encoding="utf-8"))
            task_records.append(
                {
                    "block_id": unit["block_id"],
                    "family_id": unit["family_id"],
                    "instance_id": unit["instance_id"],
                    "difficulty_tier": unit["difficulty_tier"],
                    "selection_rank": unit["selection_rank"],
                    "primary_arm_order": tuple(unit["primary_arm_order"]),
                    "infra_retry_arm_order": tuple(unit["infra_retry_arm_order"]),
                    "task_payload_digest": item.payload_digest,
                    "task_repository_tree_digest": _git_tree_digest(task_repository),
                    "initial_program_sha256": digest_bytes((materialized / "algorithm.py").read_bytes()),
                    "public_tests_sha256": digest_bytes((materialized / "public_tests.py").read_bytes()),
                    "evaluator_sha256": digest_bytes((materialized / "evaluate.py").read_bytes()),
                    "task_contract_sha256": digest_bytes((materialized / "task-contract.json").read_bytes()),
                    "score_resolution": item.score_resolution,
                    "headroom_steps": contract["headroom_steps"],
                    "evaluator_regime": contract["evaluator_regime"],
                }
            )
    estimands = {
        "response": "final feasible improvement divided by task score_resolution",
        "ada_main_effect": "0.5 * ((Y10 - Y00) + (Y11 - Y01))",
        "evox_main_effect": "0.5 * ((Y01 - Y00) + (Y11 - Y10))",
        "ada_evox_interaction": "Y11 - Y10 - Y01 + Y00",
        "minimum_effect_steps": {
            "ada_main_effect": 1.0,
            "evox_main_effect": 1.0,
            "ada_evox_interaction": 1.0,
        },
        "primary_test": "one-sided exact paired sign test with Holm FWER 0.05",
    }
    payload = {
        "protocol_id": PROTOCOL_ID,
        "protocol_revision": "4.1",
        "status": "SEALED_PRE_MODEL",
        "claim_ceiling": "P2_FACTORIAL_DEVELOPMENT_SIGNAL_ON_EXTERNAL_CONTRACT_DERIVED_DEV_ONLY",
        "model_calls_before_seal": 0,
        "fresh_or_sealed_assets_opened": 0,
        "repository": jsonable(snapshot),
        "gate_binding": {
            "receipt_digest": gate["receipt_digest"],
            "receipt_file_sha256": digest_bytes(gate_path.read_bytes()),
            "cohort_plan_digest": gate["cohort_plan_digest"],
        },
        "implementation_digests": {
            "scientific_runner": _source_digest(Path(__file__)),
            "v4_gate": _source_digest(Path(__file__).with_name("p2_v4_fast_close.py")),
            "v4_seal": _source_digest(Path(__file__).parents[3] / "docs" / "P2_FACTORIAL_V4_PREMODEL_STATISTICAL_SEAL.md"),
            "harness_code_bundle": harness_code_bundle_digest(),
        },
        "provider": jsonable(provider),
        "profile_fairness_binding": {
            "audit_digest": profile_audit.digest,
            "arm_profile_ids": profile_audit.arm_profile_ids,
        },
        "arms": ARM_IDS,
        "tasks": tuple(task_records),
        "execution_schedule": tuple(
            {
                "block_index": index,
                "block_id": task["block_id"],
                "task_id": task["instance_id"],
                "replicate_seed": int(task["selection_rank"][:8], 16),
                "arm_order": task["primary_arm_order"],
                "infra_retry_arm_order": task["infra_retry_arm_order"],
            }
            for index, task in enumerate(task_records, start=1)
        ),
        "matched_resource_envelope_per_arm": {
            "generation_call_ceiling": GENERATION_CALL_CEILING,
            "evaluator_call_ceiling": GENERATION_CALL_CEILING,
            "token_ceiling": TOKEN_CEILING,
            "wall_seconds_ceiling": WALL_SECONDS_CEILING,
            "cpu_seconds_ceiling": CPU_SECONDS_CEILING,
            "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
            "search_step_ceiling": SEARCH_STEP_CEILING,
        },
        "failure_and_stop_rules": {
            "required_evaluable_blocks": 24,
            "max_infra_retries_per_block": 1,
            "max_infra_retries_global": 2,
            "recoverable_failure_classes": tuple(sorted(RECOVERABLE_INFRA)),
            "whole_block_retry_only": True,
            "efficacy_stop": False,
            "machine_futility_only": True,
        },
        "cost_accounting": (
            "scientific_generation_calls",
            "scientific_tokens",
            "infra_censored_generation_calls",
            "infra_censored_tokens",
            "total_paid_generation_calls",
            "total_paid_tokens",
        ),
        "estimands": estimands,
        "decision_rules": {
            "y11_noninferiority_margin_steps": 0.0,
            "p3_requires_positive_interaction_and_y11_noninferiority": True,
        },
    }
    return {**payload, "protocol_manifest_digest": digest_json(payload)}


def seal(
    workspace: Path,
    *,
    repository: Path,
    gate_root: Path,
    provider_executable: Path,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists():
        raise RuntimeError("P2 V4 scientific workspace is create-once")
    manifest = build_manifest(
        repository=repository,
        gate_root=gate_root,
        provider_executable=provider_executable,
    )
    store = ArtifactStore(workspace / "protocol-artifacts")
    store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": "P2_V4_SCIENTIFIC_MANIFEST_SEALED",
        "protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "blocks": 24,
        "model_calls_before_seal": 0,
    }


def verify_manifest(
    manifest: dict[str, Any], *, repository: Path, gate_root: Path, provider_executable: Path
) -> None:
    recorded = manifest.get("protocol_manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "protocol_manifest_digest"}
    if recorded != digest_json(payload):
        raise RuntimeError("P2 V4 manifest digest mismatch")
    rebuilt = build_manifest(
        repository=repository,
        gate_root=gate_root,
        provider_executable=provider_executable,
    )
    if rebuilt["protocol_manifest_digest"] != recorded:
        raise RuntimeError("P2 V4 execution authority drift")


def _execute_block_attempt(
    *,
    workspace: Path,
    attempt_root: Path,
    scheduled: dict[str, Any],
    item: SearchValueTask,
    task_record: dict[str, Any],
    manifest: dict[str, Any],
    source_snapshot: Any,
    local_provider: CodexExecProvider,
    structural_provider: CodexExecProvider,
    arm_order: tuple[str, ...],
    progress: Callable[[str], None] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profiles = {arm: values[0] for arm, values in static_composition_profiles().items()}
    task_repository, task_commit = item.task.initialize_repository(attempt_root / "task")
    if _git_tree_digest(task_repository) != task_record["task_repository_tree_digest"]:
        raise RuntimeError("P2 V4 task repository tree drift")
    prepared: dict[str, dict[str, Any]] = {}
    runtimes: dict[str, HarnessSearchRuntime] = {}
    surfaces = []
    store = ArtifactStore(attempt_root / "records")
    for arm_id in ARM_IDS:
        started = time.monotonic()
        arm = __import__(
            "discoveryos.benchmarks.local_patch_admission", fromlist=["_initialize_arm"]
        )._initialize_arm(
            attempt_root / "arms" / arm_id,
            item.task,
            task_repository,
            task_commit,
            TOKEN_CEILING,
            cpu_ceiling=CPU_SECONDS_CEILING,
            wall_ceiling=WALL_SECONDS_CEILING,
            contract_created_at=P2_CONTRACT_CREATED_AT,
        )
        baseline = asyncio.run(
            _evaluate_at(
                arm,
                arm.baseline,
                Fidelity.G1,
                seed=int(scheduled["replicate_seed"]),
                attempt="p2-v4-baseline",
            )
        )
        if baseline.validity is EvidenceValidity.NOT_EVALUABLE:
            raise RuntimeError(f"BASELINE_EVALUATOR_NOT_EVALUABLE:{arm_id}")
        spec = _p2_search_spec(
            arm,
            item,
            block_id=scheduled["block_id"],
            seed=int(scheduled["replicate_seed"]),
        )
        run_manifest = _p2_harness_run_manifest(
            arm=arm,
            item=item,
            profile=profiles[arm_id],
            spec=spec,
            source_snapshot=source_snapshot,
            local_provider=local_provider,
            structural_provider=structural_provider,
        )
        runtime = HarnessSearchRuntime.build(
            profile=profiles[arm_id],
            spec=spec,
            contract=arm.contract,
            ledger=arm.ledger,
            artifacts=arm.artifacts,
            experiment_executor=arm.executor,
            base_controller=DeterministicActionController(mvp0_controller_config()),
            local_provider=local_provider,
            structural_provider=structural_provider,
            manifest=run_manifest,
            source_snapshot=source_snapshot,
        )
        prepared[arm_id] = {
            "arm": arm,
            "baseline": baseline,
            "baseline_elapsed": time.monotonic() - started,
            "run_manifest": run_manifest,
        }
        runtimes[arm_id] = runtime
        surfaces.append(
            P2ZeroModelRuntimeSurface.capture(
                arm_id=arm_id,
                runtime=runtime,
                initial_state=runtime.loop.projector.build(),
            )
        )
    fairness = audit_p2_zero_model_runtime_fairness(tuple(surfaces))
    if fairness.profile_audit_digest != manifest["profile_fairness_binding"]["audit_digest"]:
        raise RuntimeError("P2 V4 block fairness drift")
    arm_results = {}
    try:
        for arm_id in arm_order:
            if progress:
                progress(f"P2 V4 {scheduled['block_id']} starting {arm_id}")
            started = time.monotonic()
            failure = None
            try:
                result = asyncio.run(runtimes[arm_id].run())
                stop_reason = result.stop_decision.reason_codes
            except Exception as error:
                failure = f"{type(error).__name__}:{error}"
                stop_reason = ("RUNTIME_EXCEPTION",)
            terminal = _p2_arm_terminal(
                arm_id=arm_id,
                item=item,
                prepared=prepared[arm_id],
                runtime_elapsed=time.monotonic() - started,
                stop_reason=stop_reason,
                failure=failure,
            )
            arm_results[arm_id] = terminal
            store.write_record(f"arms/{arm_id}.json", terminal)
            if progress:
                progress(
                    f"P2 V4 {scheduled['block_id']} completed {arm_id} "
                    f"status={terminal['status']} calls={terminal['generation_calls']} "
                    f"tokens={terminal['actual_usage']['tokens']}"
                )
    finally:
        for runtime in runtimes.values():
            runtime.close()
    block = _p2_block_terminal({**scheduled, "arm_order": arm_order}, arm_results)
    store.write_record("block-terminal.json", block)
    cost = {
        "generation_calls": sum(item["generation_calls"] for item in arm_results.values()),
        "tokens": sum(item["actual_usage"]["tokens"] for item in arm_results.values()),
    }
    return block, cost


def _futility_unreachable(blocks: tuple[dict[str, Any], ...], total: int = 24) -> bool:
    evaluable = tuple(block for block in blocks if block["status"] == "EVALUABLE")
    remaining = total - len(blocks)
    if remaining < 0:
        return True
    for name in ("ada_main_effect", "evox_main_effect", "ada_evox_interaction"):
        effects = tuple(float(block["contrasts"][name]) for block in evaluable)
        positives = sum(effect > 0 for effect in effects) + remaining
        negatives = sum(effect < 0 for effect in effects)
        if _one_sided_sign_p(positives, negatives) <= 0.05:
            return False
    return True


def run(
    workspace: Path,
    *,
    repository: Path,
    gate_root: Path,
    provider_executable: Path,
    progress: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = json.loads(
        (workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8")
    )
    verify_manifest(
        manifest,
        repository=repository,
        gate_root=gate_root,
        provider_executable=provider_executable,
    )
    result_root = workspace / "result-artifacts"
    if result_root.exists():
        raise RuntimeError("P2 V4 scientific result root is create-once and cannot resume")
    provider = inspect_provider(provider_executable)
    local_provider = CodexExecProvider(
        command=(provider.executable_path,),
        model=provider.model,
        reasoning_effort=provider.reasoning_effort,
        timeout_seconds=provider.timeout_seconds,
    )
    structural_provider = CodexExecProvider(
        command=(provider.executable_path,),
        model=provider.model,
        reasoning_effort=provider.reasoning_effort,
        timeout_seconds=provider.timeout_seconds,
        output_schema=STRUCTURAL_PATCH_SCHEMA,
    )
    snapshot = capture_git_source_snapshot(repository.resolve())
    gate = json.loads((gate_root / "gate-receipt.json").read_text(encoding="utf-8"))
    unit_map = {unit["block_id"]: unit for unit in gate["unit_receipts"]}
    record_map = {record["block_id"]: record for record in manifest["tasks"]}
    store = ArtifactStore(result_root)
    blocks = []
    global_retries = 0
    ledger = {
        "scientific_generation_calls": 0,
        "scientific_tokens": 0,
        "infra_censored_generation_calls": 0,
        "infra_censored_tokens": 0,
    }
    for scheduled in manifest["execution_schedule"]:
        item = _task_from_gate(gate_root, unit_map[scheduled["block_id"]])
        accepted_block = None
        for attempt in (0, 1):
            arm_order = tuple(
                scheduled["arm_order"] if attempt == 0 else scheduled["infra_retry_arm_order"]
            )
            attempt_root = workspace / "attempts" / scheduled["block_id"] / f"attempt-{attempt}"
            baseline_root = attempt_root / "gate-baseline"
            block_holder: dict[str, Any] = {}
            cost_holder = {"generation_calls": 0, "tokens": 0}
            gate_runner = ExecutabilityGate(
                lease_factory=WindowsPowerInhibitionLease,
                event_source=WindowsPowerEventSource(),
            )

            def baseline_probe():
                probe, _receipt = _materialize_and_probe(
                    Path("benchmarks/bank/v1/registry.json"),
                    unit_map[scheduled["block_id"]],
                    baseline_root,
                )
                return probe

            def scientific():
                started = time.monotonic()
                block, cost = _execute_block_attempt(
                    workspace=workspace,
                    attempt_root=attempt_root / "scientific",
                    scheduled=scheduled,
                    item=item,
                    task_record=record_map[scheduled["block_id"]],
                    manifest=manifest,
                    source_snapshot=snapshot,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    arm_order=arm_order,
                    progress=progress,
                )
                block_holder["block"] = block
                cost_holder.update(cost)
                elapsed = time.monotonic() - started
                calls = cost["generation_calls"]
                return ScientificBlockResult(
                    timing=TimingBreakdown(
                        harness_overhead_seconds=elapsed,
                        total_wall_seconds=elapsed,
                        provider_call_count=calls,
                        provider_terminal_count=calls,
                        provider_timing_count=calls,
                    ),
                    generation_calls_executed=calls,
                )

            receipt = gate_runner.execute(
                f"{scheduled['block_id']}-attempt-{attempt}", baseline_probe, scientific
            )
            store.write_record(
                f"attempts/{scheduled['block_id']}/attempt-{attempt}-gate.json", jsonable(receipt)
            )
            if receipt.admitted:
                accepted_block = block_holder.get("block")
                ledger["scientific_generation_calls"] += cost_holder["generation_calls"]
                ledger["scientific_tokens"] += cost_holder["tokens"]
                break
            if receipt.failure_class in RECOVERABLE_INFRA and attempt == 0 and global_retries < 2:
                global_retries += 1
                ledger["infra_censored_generation_calls"] += cost_holder["generation_calls"]
                ledger["infra_censored_tokens"] += cost_holder["tokens"]
                continue
            ledger["scientific_generation_calls"] += cost_holder["generation_calls"]
            ledger["scientific_tokens"] += cost_holder["tokens"]
            status = (
                "PROTOCOL_NOT_EVALUABLE_INFRA"
                if receipt.failure_class in RECOVERABLE_INFRA
                else "NOT_EVALUABLE"
            )
            report = {
                "protocol_id": PROTOCOL_ID,
                "protocol_manifest_digest": manifest["protocol_manifest_digest"],
                "status": status,
                "failure_class": receipt.failure_class,
                "failure_detail": receipt.failure_detail,
                "completed_blocks": len(blocks),
                "estimands": None,
                "p3_authorized": False,
                "cost_ledger": _finalize_cost(ledger),
            }
            store.write_record(REPORT_RECORD, report)
            return report
        if accepted_block is None or accepted_block["status"] != "EVALUABLE":
            report = {
                "protocol_id": PROTOCOL_ID,
                "protocol_manifest_digest": manifest["protocol_manifest_digest"],
                "status": "NOT_EVALUABLE",
                "completed_blocks": len(blocks),
                "estimands": None,
                "p3_authorized": False,
                "cost_ledger": _finalize_cost(ledger),
            }
            store.write_record(REPORT_RECORD, report)
            return report
        blocks.append(accepted_block)
        store.write_record(f"blocks/{scheduled['block_id']}.json", accepted_block)
        if _futility_unreachable(tuple(blocks)):
            report = {
                "protocol_id": PROTOCOL_ID,
                "protocol_manifest_digest": manifest["protocol_manifest_digest"],
                "status": "FUTILITY_STOP_FINAL_GATE_MATHEMATICALLY_UNREACHABLE",
                "completed_blocks": len(blocks),
                "estimands": None,
                "p3_authorized": False,
                "cost_ledger": _finalize_cost(ledger),
            }
            store.write_record(REPORT_RECORD, report)
            return report
    report = {
        **_aggregate_p2_factorial(manifest, tuple(blocks)),
        "cost_ledger": _finalize_cost(ledger),
    }
    store.write_record(REPORT_RECORD, report)
    return report


def _finalize_cost(ledger: dict[str, int]) -> dict[str, int]:
    return {
        **ledger,
        "total_paid_generation_calls": (
            ledger["scientific_generation_calls"] + ledger["infra_censored_generation_calls"]
        ),
        "total_paid_tokens": ledger["scientific_tokens"] + ledger["infra_censored_tokens"],
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Seal or run P2 V4 scientific fast-close")
    parser.add_argument("action", choices=("seal", "run"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--gate-root", type=Path, required=True)
    parser.add_argument("--provider-executable", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "seal":
        result = seal(
            args.workspace,
            repository=args.repository,
            gate_root=args.gate_root,
            provider_executable=args.provider_executable,
        )
    else:
        result = run(
            args.workspace,
            repository=args.repository,
            gate_root=args.gate_root,
            provider_executable=args.provider_executable,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
