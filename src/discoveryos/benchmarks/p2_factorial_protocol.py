from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.local_patch_admission import AdmissionArm, _initialize_arm
from discoveryos.benchmarks.search_value_mvp0 import STRUCTURAL_PATCH_SCHEMA
from discoveryos.benchmarks.search_value_mvp0 import (
    _evaluate_at,
    _search_observations,
    _sum_usage,
    mvp0_controller_config,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import search_value_mvp0_tasks
from discoveryos.benchmarks.task_types import SearchValueTask, normalized_source
from discoveryos.contracts.models import EvidenceValidity, Fidelity, MetricDirection, ResourceBudget, RunMode
from discoveryos.harness import (
    HarnessRunManifest,
    ProviderBinding,
    P2ZeroModelRuntimeSurface,
    HarnessSearchRuntime,
    audit_p2_factorial_profiles,
    audit_p2_zero_model_runtime_fairness,
    capture_git_source_snapshot,
    harness_code_bundle_digest,
    static_composition_profiles,
)
from discoveryos.operators.action_controller import DeterministicActionController, SearchAction
from discoveryos.operators.asha import RungDefinition
from discoveryos.providers.codex_exec import CodexExecProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.search_loop import SearchActionResult, SearchRunSpec
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "DISCOVERYOS_P2_ADA_EVOX_FACTORIAL_DEVELOPMENT_V3"
MANIFEST_RECORD = "p2-factorial-development-v3-manifest.json"
REPORT_RECORD = "p2-factorial-development-v3-report.json"
ARM_IDS = ("neither", "ada_only", "evox_only", "ada_evox")
TASK_IDS = (
    "bounded_knapsack_alpha",
    "bounded_knapsack_beta",
    "conflict_coloring_alpha",
    "conflict_coloring_beta",
    "load_balance_alpha",
    "load_balance_beta",
)
REPLICATE_SEEDS = (17082601, 17082602)
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
PROVIDER_TIMEOUT_SECONDS = 300.0
GENERATION_CALL_CEILING = 7
EVALUATOR_CALL_CEILING = 7
TOKEN_CEILING = 140_000
WALL_SECONDS_CEILING = 2_100.0
CPU_SECONDS_CEILING = 420.0
SEARCH_STEP_CEILING = 6
P2_CONTRACT_CREATED_AT = "2026-08-18T00:00:00+00:00"


def _normalized_file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
INTERACTION_MINIMUM_EFFECT_STEPS = 1.0
MAIN_EFFECT_MINIMUM_EFFECT_STEPS = 1.0


@dataclass(frozen=True, slots=True)
class FrozenProviderBinding:
    executable_path: str
    executable_sha256: str
    provider_version: str
    provider_name: str
    model: str
    reasoning_effort: str
    timeout_seconds: float
    local_settings_digest: str
    structural_settings_digest: str


def _task_suite() -> tuple[SearchValueTask, ...]:
    by_id = {item.task.task_id: item for item in search_value_mvp0_tasks()}
    if set(TASK_IDS) - set(by_id):
        raise RuntimeError("P2 factorial task definitions are missing")
    return tuple(by_id[task_id] for task_id in TASK_IDS)


def preflight_p2_factorial_tasks() -> tuple[dict[str, Any], ...]:
    records = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for item in _task_suite():
            repository, commit = item.task.initialize_repository(root)
            baseline = tuple(_score_source(item, repository, item.task.algorithm_source) for _ in range(2))
            reference = _score_source(item, repository, item.reference_source)
            intermediates = tuple(
                _score_source(item, repository, source) for source in item.intermediate_sources
            )
            if baseline[0] != baseline[1]:
                raise RuntimeError(f"P2 baseline replay drift: {item.task.task_id}")
            headroom_steps = (reference - baseline[0]) / item.score_resolution
            distinct_steps = {
                round((score - baseline[0]) / item.score_resolution, 8)
                for score in (*intermediates, reference)
                if score - baseline[0] >= item.score_resolution - 1e-12
            }
            if headroom_steps < 4.0 or len(distinct_steps) < 2:
                raise RuntimeError(f"P2 task lacks resolvable development headroom: {item.task.task_id}")
            records.append(
                {
                    "task_id": item.task.task_id,
                    "family": item.task.category,
                    "asset_level": "L2_CONSUMED_DEVELOPMENT_TASK",
                    "consumption_source": "DISCOVERYOS_SEARCH_VALUE_MVP0_V1",
                    "task_payload_digest": item.payload_digest,
                    "preflight_task_repository_commit_non_authoritative": commit,
                    "task_repository_tree_digest": _git_tree_digest(repository),
                    "initial_state_digest": digest_json(
                        {
                            "question": item.task.question,
                            "algorithm_source": normalized_source(item.task.algorithm_source),
                        }
                    ),
                    "baseline_source_digest": digest_bytes(
                        normalized_source(item.task.algorithm_source).encode("utf-8")
                    ),
                    "evaluator_id": f"p2-factorial-{item.task.task_id}-g2-development",
                    "evaluator_digest": digest_bytes(
                        normalized_source(item.task.evaluator_source).encode("utf-8")
                    ),
                    "reference_digest": digest_bytes(
                        normalized_source(item.reference_source).encode("utf-8")
                    ),
                    "intermediate_digests": tuple(
                        digest_bytes(normalized_source(source).encode("utf-8"))
                        for source in item.intermediate_sources
                    ),
                    "score_direction": "maximize",
                    "score_resolution": item.score_resolution,
                    "baseline_replays": baseline,
                    "reference_score": reference,
                    "intermediate_scores": intermediates,
                    "headroom_steps": round(headroom_steps, 8),
                    "trajectory_classes": item.trajectory_classes,
                    "preflight_model_calls": 0,
                }
            )
    return tuple(records)


def _score_source(item: SearchValueTask, repository: Path, source: str) -> float:
    algorithm_path = repository / item.task.entrypoint
    original = algorithm_path.read_text(encoding="utf-8")
    algorithm_path.write_text(normalized_source(source), encoding="utf-8")
    environment = os.environ.copy()
    environment["DISCOVERYOS_FIDELITY"] = "G2_DEVELOPMENT"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        for command in ((sys.executable, "public_tests.py"), (sys.executable, "evaluate.py")):
            result = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60.0,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"P2 task preflight failed: {item.task.task_id}:{result.stderr.strip()}"
                )
        payload = json.loads(result.stdout.splitlines()[-1])
        if float(payload["metrics"]["valid"]) != 1.0:
            raise RuntimeError(f"P2 task preflight returned invalid: {item.task.task_id}")
        return float(payload["metrics"]["score"])
    finally:
        algorithm_path.write_text(original, encoding="utf-8")


def inspect_provider(executable: Path) -> FrozenProviderBinding:
    resolved = executable.resolve(strict=True)
    local = CodexExecProvider(
        command=(str(resolved),),
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        timeout_seconds=PROVIDER_TIMEOUT_SECONDS,
    )
    structural = CodexExecProvider(
        command=(str(resolved),),
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        timeout_seconds=PROVIDER_TIMEOUT_SECONDS,
        output_schema=STRUCTURAL_PATCH_SCHEMA,
    )
    version = local.provider_version
    if not version.startswith("codex-cli ") or "unknown" in version.lower():
        raise RuntimeError(f"unusable Codex provider version: {version}")
    return FrozenProviderBinding(
        executable_path=str(resolved),
        executable_sha256=digest_bytes(resolved.read_bytes()),
        provider_version=version,
        provider_name=local.provider_name,
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        timeout_seconds=PROVIDER_TIMEOUT_SECONDS,
        local_settings_digest=local.settings_digest,
        structural_settings_digest=structural.settings_digest,
    )


def build_p2_factorial_manifest(
    *,
    repository_commit: str,
    tracked_source_tree_digest: str,
    provider: FrozenProviderBinding,
    tasks: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if tuple(record["task_id"] for record in tasks) != TASK_IDS:
        raise ValueError("P2 factorial task set or order differs from the frozen suite")
    if any(record.get("asset_level") != "L2_CONSUMED_DEVELOPMENT_TASK" for record in tasks):
        raise ValueError("P2 protocol may use only the frozen L2 consumed development suite")
    if any(record.get("preflight_model_calls") != 0 for record in tasks):
        raise ValueError("P2 task preflight must remain zero-model")
    family_counts: dict[str, int] = {}
    for record in tasks:
        family = str(record["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
    if sorted(family_counts.values()) != [2, 2, 2]:
        raise ValueError("P2 suite must contain two tasks from each of three families")
    profile_audit = audit_p2_factorial_profiles()
    schedule = []
    randomizer = random.Random(18082601)
    block_keys = [(task_id, seed) for task_id in TASK_IDS for seed in REPLICATE_SEEDS]
    randomizer.shuffle(block_keys)
    for block_index, (task_id, seed) in enumerate(block_keys, start=1):
        arm_order = list(ARM_IDS)
        randomizer.shuffle(arm_order)
        schedule.append(
            {
                "block_index": block_index,
                "block_id": f"{task_id}-seed-{seed}",
                "task_id": task_id,
                "replicate_seed": seed,
                "arm_order": tuple(arm_order),
            }
        )
    estimands = {
        "response_unit": "task_replicate paired four-arm block",
        "response": "final feasible improvement divided by task score_resolution",
        "ada_main_effect": "0.5 * ((Y10 - Y00) + (Y11 - Y01))",
        "evox_main_effect": "0.5 * ((Y01 - Y00) + (Y11 - Y10))",
        "ada_evox_interaction": "Y11 - Y10 - Y01 + Y00",
        "directions": {
            "ada_main_effect": "positive",
            "evox_main_effect": "positive",
            "ada_evox_interaction": "positive_synergy_only",
        },
        "minimum_effect_steps": {
            "ada_main_effect": MAIN_EFFECT_MINIMUM_EFFECT_STEPS,
            "evox_main_effect": MAIN_EFFECT_MINIMUM_EFFECT_STEPS,
            "ada_evox_interaction": INTERACTION_MINIMUM_EFFECT_STEPS,
        },
        "aggregation": "compute contrasts within each paired block, then aggregate; never subtract arm-level medians",
        "primary_test": "one-sided exact paired sign test per estimand with Holm family-wise alpha 0.05",
        "effect_gate": "median paired contrast must meet its frozen minimum_effect_steps",
        "synergy_prohibition": "Y11-vs-Y00 alone can never establish interaction or synergy",
    }
    payload = {
        "protocol_id": PROTOCOL_ID,
        "protocol_revision": 3,
        "status": "SEALED_PRE_MODEL",
        "claim_ceiling": "P2_FACTORIAL_DEVELOPMENT_SIGNAL_ON_CONSUMED_TASKS_ONLY",
        "model_calls_before_seal": 0,
        "fresh_or_sealed_assets_opened": 0,
        "repository": {
            "commit": repository_commit,
            "tracked_source_tree_digest": tracked_source_tree_digest,
            "worktree_clean_at_seal": True,
        },
        "implementation_digests": {
            "protocol_source": _normalized_file_digest(Path(__file__)),
            "task_suite_source": _normalized_file_digest(
                Path(__file__).with_name("search_value_mvp0_tasks.py")
            ),
            "harness_code_bundle": harness_code_bundle_digest(),
        },
        "profile_fairness_binding": {
            "status": profile_audit.status,
            "audit_digest": profile_audit.digest,
            "arm_profile_ids": profile_audit.arm_profile_ids,
            "factor_flags": profile_audit.factor_flags,
        },
        "arms": ARM_IDS,
        "tasks": tasks,
        "task_selection": {
            "rule": "two lexicographically first task ids per existing MVP0 family; no P2 outcome inspection",
            "task_count": len(tasks),
            "families": tuple(sorted(family_counts.items())),
            "asset_level": "L2_CONSUMED_DEVELOPMENT_TASK",
            "task_replacement": False,
        },
        "replicates": {
            "count_per_task_arm": len(REPLICATE_SEEDS),
            "seeds": REPLICATE_SEEDS,
            "paired_across_all_four_arms": True,
            "execution_order_seed": 18082601,
            "arm_order_randomized_within_task_replicate_block": True,
        },
        "execution_schedule": tuple(schedule),
        "provider": jsonable(provider),
        "matched_resource_envelope_per_task_replicate_arm": {
            "generation_call_ceiling": GENERATION_CALL_CEILING,
            "evaluator_call_ceiling": EVALUATOR_CALL_CEILING,
            "token_ceiling_input_plus_output": TOKEN_CEILING,
            "wall_seconds_ceiling": WALL_SECONDS_CEILING,
            "cpu_seconds_ceiling": CPU_SECONDS_CEILING,
            "provider_timeout_seconds_per_call": PROVIDER_TIMEOUT_SECONDS,
            "unused_budget_transfer": False,
            "cross_arm_budget_transfer": False,
            "repair_or_resample_calls": 0,
            "every_provider_attempt_consumes_one_generation_slot": True,
            "every_candidate_evaluation_consumes_one_evaluator_slot": True,
        },
        "execution_semantics": {
            "runtime": "HarnessSearchRuntime",
            "one_runtime_per_arm": True,
            "separate_job_scoped_ledger_per_arm": True,
            "same_task_initial_state_and_evaluator": True,
            "same_model_provider_settings": True,
            "same_controller_cost_and_reservation_policy": True,
            "same_max_steps": SEARCH_STEP_CEILING,
            "baseline_evaluator_calls_per_arm": 1,
            "novelty_resampling": False,
            "final_blind_access": False,
        },
        "estimands": estimands,
        "secondary_metrics": {
            "token_anytime_auc": "paired contrasts using the same three factorial formulas",
            "valid_candidate_rate": "guardrail; maximum arm regression 0.10",
            "resource_usage": "guardrail only; efficiency cannot compensate for a failed primary effect",
        },
        "failure_and_stop_rules": {
            "controller_stop": "terminal for that arm; unused calls and budget are not transferred or filled",
            "invalid_candidate": "consumes generation and evaluator slots; incumbent remains unchanged",
            "provider_failure": "consumes its generation slot; no free retry or replacement",
            "evaluator_failure": "mark the complete four-arm paired block NOT_EVALUABLE; no backfill",
            "budget_or_timeout": "stop the arm and mark the complete paired block NOT_EVALUABLE_RESOURCE",
            "system_failure_before_first_model_call": "repair only through a new protocol revision after zero-model preflight",
            "system_failure_after_any_model_call": "preserve receipts; no task replacement, threshold change, or same-revision rerun",
            "required_evaluable_blocks": len(TASK_IDS) * len(REPLICATE_SEEDS),
            "early_global_stop": False,
        },
        "decision_rules": {
            "individual_estimand_verdicts": True,
            "interaction_label_requires_positive_direction_effect_and_multiplicity_gates": True,
            "p3_authorization": (
                "requires positive replayable interaction plus Y11 noninferiority to Y10, Y01, and Y00; "
                "otherwise diagnose on consumed traces"
            ),
            "no_single_contrast_story": "Ada+EvoX versus neither is descriptive only",
            "y11_noninferiority_margin_steps": 0.0,
        },
        "not_authorized": (
            "fresh or SEALED tasks",
            "official AdaEvolve or EvoX parity claims",
            "generalization or superiority claims",
            "P3 adaptive profile design before a positive replayable P2 result",
            "mechanism, threshold, task, evaluator, budget, or gate changes after the first model call",
        ),
    }
    return {**payload, "protocol_manifest_digest": digest_json(payload)}


def verify_p2_factorial_manifest(manifest: dict[str, Any], expected_digest: str) -> None:
    recorded = manifest.get("protocol_manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "protocol_manifest_digest"}
    if recorded != expected_digest or recorded != digest_json(payload):
        raise RuntimeError("P2 factorial manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_MODEL" or manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("P2 factorial protocol was not sealed before model execution")
    if manifest.get("fresh_or_sealed_assets_opened") != 0:
        raise RuntimeError("P2 factorial protocol opened a protected asset")
    if manifest["implementation_digests"]["protocol_source"] != _normalized_file_digest(
        Path(__file__)
    ):
        raise RuntimeError("P2 factorial protocol implementation drift")
    if manifest["implementation_digests"]["task_suite_source"] != _normalized_file_digest(
        Path(__file__).with_name("search_value_mvp0_tasks.py")
    ):
        raise RuntimeError("P2 factorial task suite implementation drift")
    if manifest["implementation_digests"]["harness_code_bundle"] != harness_code_bundle_digest():
        raise RuntimeError("P2 factorial Harness implementation drift")
    current_tasks = tuple(item.payload_digest for item in _task_suite())
    frozen_tasks = tuple(record["task_payload_digest"] for record in manifest["tasks"])
    if frozen_tasks != current_tasks:
        raise RuntimeError("P2 factorial task suite drift")
    profile_audit = audit_p2_factorial_profiles()
    if (
        manifest["profile_fairness_binding"]["audit_digest"] != profile_audit.digest
        or tuple(tuple(item) for item in manifest["profile_fairness_binding"]["arm_profile_ids"])
        != profile_audit.arm_profile_ids
    ):
        raise RuntimeError("P2 factorial Profile/fairness binding drift")


def verify_p2_factorial_execution_authority(
    manifest: dict[str, Any],
    *,
    repository: Path,
    provider_executable: Path,
) -> None:
    verify_p2_factorial_manifest(manifest, manifest.get("protocol_manifest_digest", ""))
    snapshot = capture_git_source_snapshot(repository.resolve())
    frozen_repository = manifest["repository"]
    if not snapshot.worktree_clean:
        raise RuntimeError("P2 factorial execution requires a clean worktree")
    if (
        snapshot.repository_commit != frozen_repository["commit"]
        or snapshot.tracked_source_tree_digest != frozen_repository["tracked_source_tree_digest"]
    ):
        raise RuntimeError("P2 factorial execution source binding drift")
    if jsonable(inspect_provider(provider_executable)) != manifest["provider"]:
        raise RuntimeError("P2 factorial execution provider binding drift")


def seal_p2_factorial_protocol(
    workspace: Path,
    *,
    repository: Path,
    provider_executable: Path,
) -> dict[str, Any]:
    snapshot = capture_git_source_snapshot(repository.resolve())
    if not snapshot.worktree_clean:
        raise RuntimeError("P2 factorial protocol requires a clean worktree")
    provider = inspect_provider(provider_executable)
    tasks = preflight_p2_factorial_tasks()
    manifest = build_p2_factorial_manifest(
        repository_commit=snapshot.repository_commit,
        tracked_source_tree_digest=snapshot.tracked_source_tree_digest,
        provider=provider,
        tasks=tasks,
    )
    store = ArtifactStore(workspace.resolve() / "protocol-artifacts")
    path = store.write_record(MANIFEST_RECORD, manifest)
    verify_p2_factorial_manifest(manifest, manifest["protocol_manifest_digest"])
    verify_p2_factorial_execution_authority(
        manifest,
        repository=repository,
        provider_executable=provider_executable,
    )
    return {
        "status": manifest["status"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "task_count": len(tasks),
        "replicates_per_task_arm": len(REPLICATE_SEEDS),
        "maximum_generation_calls": (
            len(tasks) * len(REPLICATE_SEEDS) * len(ARM_IDS) * GENERATION_CALL_CEILING
        ),
        "protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "manifest_path": str(path),
        "repository_commit": snapshot.repository_commit,
        "provider_version": provider.provider_version,
    }


def run_p2_factorial_protocol(
    workspace: Path,
    *,
    repository: Path,
    provider_executable: Path,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute the sealed V2 schedule exactly once and persist every terminal."""

    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_p2_factorial_execution_authority(
        manifest,
        repository=repository,
        provider_executable=provider_executable,
    )
    report_path = workspace / "result-artifacts" / "records" / REPORT_RECORD
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        replay_p2_factorial_report(workspace, repository=repository, provider_executable=provider_executable)
        return report
    result_root = workspace / "result-artifacts"
    if result_root.exists() and any(result_root.rglob("*.json")):
        raise RuntimeError("P2 V3 has partial result receipts; same-revision resume is forbidden")

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
    source_snapshot = capture_git_source_snapshot(repository.resolve())
    profiles = {arm_id: profiles[0] for arm_id, profiles in static_composition_profiles().items()}
    task_map = {item.task.task_id: item for item in _task_suite()}
    task_records = {item["task_id"]: item for item in manifest["tasks"]}
    store = ArtifactStore(result_root)
    block_results: list[dict[str, Any]] = []

    for scheduled in manifest["execution_schedule"]:
        block_id = str(scheduled["block_id"])
        task_id = str(scheduled["task_id"])
        seed = int(scheduled["replicate_seed"])
        item = task_map[task_id]
        task_record = task_records[task_id]
        if progress:
            progress(
                f"P2 V3 block {scheduled['block_index']}/12 preparing {block_id} "
                f"order={','.join(scheduled['arm_order'])}"
            )
        store.write_record(
            f"blocks/{block_id}/block-start.json",
            {
                "protocol_manifest_digest": manifest["protocol_manifest_digest"],
                "block_id": block_id,
                "task_id": task_id,
                "replicate_seed": seed,
                "arm_order": scheduled["arm_order"],
                "status": "STARTED",
            },
        )
        repository_root = workspace / "task-materialization" / block_id
        task_repository, task_commit = item.task.initialize_repository(repository_root)
        if _git_tree_digest(task_repository) != task_record["task_repository_tree_digest"]:
            raise RuntimeError(f"P2 task repository tree drift: {block_id}")

        prepared: dict[str, dict[str, Any]] = {}
        runtimes: dict[str, HarnessSearchRuntime] = {}
        surfaces: list[P2ZeroModelRuntimeSurface] = []
        preparation_failure: str | None = None
        for arm_id in ARM_IDS:
            arm_started = time.monotonic()
            arm = _initialize_arm(
                workspace / "arms" / block_id / arm_id,
                item.task,
                task_repository,
                task_commit,
                TOKEN_CEILING,
                cpu_ceiling=CPU_SECONDS_CEILING,
                wall_ceiling=WALL_SECONDS_CEILING,
                contract_created_at=P2_CONTRACT_CREATED_AT,
            )
            baseline = asyncio.run(
                _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=seed, attempt="p2-baseline")
            )
            baseline_elapsed = time.monotonic() - arm_started
            if baseline.validity is EvidenceValidity.NOT_EVALUABLE:
                preparation_failure = f"BASELINE_EVALUATOR_NOT_EVALUABLE:{arm_id}"
                prepared[arm_id] = {
                    "arm": arm,
                    "baseline": baseline,
                    "baseline_elapsed": baseline_elapsed,
                }
                break
            spec = _p2_search_spec(arm, item, block_id=block_id, seed=seed)
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
                "baseline_elapsed": baseline_elapsed,
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

        if preparation_failure is None:
            try:
                fairness = audit_p2_zero_model_runtime_fairness(tuple(surfaces))
                if fairness.profile_audit_digest != manifest["profile_fairness_binding"]["audit_digest"]:
                    raise RuntimeError("P2 block fairness digest differs from the sealed manifest")
                store.write_record(
                    f"blocks/{block_id}/fairness.json",
                    {
                        "status": fairness.status,
                        "digest": fairness.digest,
                        "profile_audit_digest": fairness.profile_audit_digest,
                        "common_runtime_surface_digest": fairness.common_runtime_surface_digest,
                        "ledger_paths": fairness.ledger_paths,
                    },
                )
            except Exception as error:
                preparation_failure = f"FAIRNESS_PREFLIGHT_FAILED:{type(error).__name__}:{error}"

        arm_results: dict[str, dict[str, Any]] = {}
        try:
            if preparation_failure is None:
                for arm_id in scheduled["arm_order"]:
                    if progress:
                        progress(f"P2 V3 starting {block_id}:{arm_id}")
                    runtime_started = time.monotonic()
                    failure: str | None = None
                    try:
                        loop_result = asyncio.run(runtimes[arm_id].run())
                        stop_reason = loop_result.stop_decision.reason_codes
                    except Exception as error:
                        failure = f"{type(error).__name__}:{error}"
                        stop_reason = ("RUNTIME_EXCEPTION",)
                    runtime_elapsed = time.monotonic() - runtime_started
                    terminal = _p2_arm_terminal(
                        arm_id=arm_id,
                        item=item,
                        prepared=prepared[arm_id],
                        runtime_elapsed=runtime_elapsed,
                        stop_reason=stop_reason,
                        failure=failure,
                    )
                    arm_results[arm_id] = terminal
                    store.write_record(f"blocks/{block_id}/arms/{arm_id}.json", terminal)
                    if progress:
                        progress(
                            f"P2 V3 completed {block_id}:{arm_id} "
                            f"status={terminal['status']} steps={terminal['response_steps']:.4f} "
                            f"calls={terminal['generation_calls']}/{terminal['evaluator_calls']} "
                            f"tokens={terminal['actual_usage']['tokens']}"
                        )
            else:
                for arm_id in ARM_IDS:
                    terminal = {
                        "block_id": block_id,
                        "task_id": task_id,
                        "replicate_seed": seed,
                        "arm": arm_id,
                        "status": "NOT_EVALUABLE_PREFLIGHT",
                        "failure": preparation_failure,
                        "response_steps": 0.0,
                        "generation_calls": len(
                            prepared[arm_id]["arm"].ledger.generation_records()
                        ) if arm_id in prepared else 0,
                        "evaluator_calls": len(
                            prepared[arm_id]["arm"].ledger.evidence_records()
                        ) if arm_id in prepared else 0,
                        "actual_usage": {"tokens": 0, "cpu_seconds": 0.0, "wall_seconds": 0.0},
                    }
                    arm_results[arm_id] = terminal
                    store.write_record(f"blocks/{block_id}/arms/{arm_id}.json", terminal)
        finally:
            for runtime in runtimes.values():
                runtime.close()

        block = _p2_block_terminal(scheduled, arm_results)
        store.write_record(f"blocks/{block_id}/block-terminal.json", block)
        block_results.append(block)
        if progress:
            progress(f"P2 V3 terminal {block_id} status={block['status']}")

    report = _aggregate_p2_factorial(manifest, tuple(block_results))
    store.write_record(REPORT_RECORD, report)
    replay_p2_factorial_report(workspace, repository=repository, provider_executable=provider_executable)
    return report


def _p2_search_spec(
    arm: AdmissionArm,
    item: SearchValueTask,
    *,
    block_id: str,
    seed: int,
) -> SearchRunSpec:
    return SearchRunSpec(
        run_id=f"p2-v3-{block_id}-{arm.name}",
        contract_digest=arm.contract.digest,
        root_candidate_id=arm.baseline.candidate_id,
        branch_id="single-active-branch",
        initial_algorithm_family=item.baseline_basin_id,
        metric_name="score",
        metric_direction=MetricDirection.MAXIMIZE,
        initial_fidelity=Fidelity.G1,
        budget=ResourceBudget(
            tokens=TOKEN_CEILING,
            cpu_seconds=CPU_SECONDS_CEILING,
            wall_seconds=WALL_SECONDS_CEILING,
        ),
        rungs=(
            RungDefinition("p2-g1", Fidelity.G1, ResourceBudget(cpu_seconds=5, wall_seconds=30)),
            RungDefinition("p2-g2", Fidelity.G2, ResourceBudget(cpu_seconds=10, wall_seconds=60)),
        ),
        eta=2,
        initial_trials=2,
        local_action_limit=4,
        structural_action_limit=2,
        max_steps=SEARCH_STEP_CEILING,
        mutable_file_paths=(item.task.entrypoint,),
        seeds=(seed,),
        mode=RunMode.BENCHMARK,
    )


def _p2_harness_run_manifest(
    *,
    arm: AdmissionArm,
    item: SearchValueTask,
    profile,
    spec: SearchRunSpec,
    source_snapshot,
    local_provider: CodexExecProvider,
    structural_provider: CodexExecProvider,
) -> HarnessRunManifest:
    return HarnessRunManifest(
        run_id=spec.run_id,
        search_run_spec_digest=spec.digest,
        profile_id=profile.profile_id,
        plugin_manifest_digests=tuple(
            (selection.plugin_id, selection.manifest_digest) for selection in profile.plugins
        ),
        code_bundle_digest=harness_code_bundle_digest(),
        repository_commit=source_snapshot.repository_commit,
        tracked_source_tree_digest=source_snapshot.tracked_source_tree_digest,
        worktree_clean=source_snapshot.worktree_clean,
        local_provider=ProviderBinding(
            local_provider.provider_name,
            local_provider.model,
            local_provider.settings_digest,
            local_provider.provider_version,
        ),
        structural_provider=ProviderBinding(
            structural_provider.provider_name,
            structural_provider.model,
            structural_provider.settings_digest,
            structural_provider.provider_version,
        ),
        task_instance_digest=item.payload_digest,
        contract_digest=arm.contract.digest,
        evaluator_bindings=arm.contract.evaluator_bindings,
        environment_digest=arm.baseline.environment_digest,
        seeds=spec.seeds,
        budget=spec.budget,
        winner_rule_digest=digest_json(arm.contract.winner_rule),
        claim_ceiling=arm.contract.claim_ceiling.value,
    )


def _p2_arm_terminal(
    *,
    arm_id: str,
    item: SearchValueTask,
    prepared: dict[str, Any],
    runtime_elapsed: float,
    stop_reason: tuple[str, ...],
    failure: str | None,
) -> dict[str, Any]:
    arm: AdmissionArm = prepared["arm"]
    actions = tuple(
        SearchActionResult.from_dict(payload)
        for payload in arm.ledger.search_action_payloads(prepared["run_manifest"].run_id)
    )
    observations = _search_observations(arm, item, actions)
    evidence = arm.ledger.evidence_records()
    usage = _sum_usage((prepared["baseline"].resource_usage, *(action.actual_usage for action in actions)))
    generation_calls = len(arm.ledger.generation_records())
    evaluator_calls = len(evidence)
    baseline_score = _score_from_evidence(prepared["baseline"])
    best_score = baseline_score
    for observation in observations:
        if observation.valid and observation.feasible and observation.score is not None:
            best_score = max(best_score, float(observation.score))
    improvement = max(0.0, best_score - baseline_score)
    response_steps = improvement / item.score_resolution
    makespan = float(prepared["baseline_elapsed"]) + runtime_elapsed
    evaluator_failed = any(record.validity is EvidenceValidity.NOT_EVALUABLE for record in evidence)
    resource_checks = {
        "generation_call_ceiling": generation_calls <= GENERATION_CALL_CEILING,
        "evaluator_call_ceiling": evaluator_calls <= EVALUATOR_CALL_CEILING,
        "token_ceiling": usage.tokens <= TOKEN_CEILING,
        "cpu_ceiling": usage.cpu_seconds <= CPU_SECONDS_CEILING,
        "wall_ceiling": makespan <= WALL_SECONDS_CEILING,
    }
    if failure is not None:
        status = "NOT_EVALUABLE_SYSTEM"
    elif evaluator_failed:
        status = "NOT_EVALUABLE_EVALUATOR"
    elif not all(resource_checks.values()):
        status = "NOT_EVALUABLE_RESOURCE"
    else:
        status = "EVALUABLE"
    action_counts = {
        action.value: sum(result.action is action for result in actions)
        for action in SearchAction
        if action is not SearchAction.STOP
    }
    return {
        "task_id": item.task.task_id,
        "replicate_seed": prepared["run_manifest"].seeds[0],
        "arm": arm_id,
        "status": status,
        "failure": failure,
        "run_manifest": jsonable(prepared["run_manifest"]),
        "baseline_score": baseline_score,
        "best_score": best_score,
        "best_improvement": improvement,
        "score_resolution": item.score_resolution,
        "response_steps": response_steps,
        "token_anytime_auc_steps": _token_anytime_auc_steps(
            observations,
            baseline_score=baseline_score,
            score_resolution=item.score_resolution,
            token_ceiling=TOKEN_CEILING,
        ),
        "observations": tuple(jsonable(observation) for observation in observations),
        "action_counts": action_counts,
        "stop_reason": stop_reason,
        "generation_calls": generation_calls,
        "evaluator_calls": evaluator_calls,
        "valid_candidate_rate": (
            sum(observation.valid and observation.feasible for observation in observations)
            / max(1, len(observations))
        ),
        "actual_usage": {
            **usage.as_budget_dict(),
            "llm_input_tokens": usage.llm_input_tokens,
            "llm_output_tokens": usage.llm_output_tokens,
            "llm_cache_tokens": usage.llm_cache_tokens,
            "end_to_end_makespan": makespan,
        },
        "resource_checks": resource_checks,
    }


def _score_from_evidence(evidence) -> float:
    value = evidence.metric_dict().get("score")
    if evidence.validity is not EvidenceValidity.VALID or value is None:
        raise RuntimeError("P2 baseline evidence is not valid and scored")
    return float(value)


def _token_anytime_auc_steps(
    observations,
    *,
    baseline_score: float,
    score_resolution: float,
    token_ceiling: int,
) -> float:
    cursor = 0
    best = 0.0
    area = 0.0
    for observation in observations:
        token = min(token_ceiling, max(cursor, int(observation.cumulative_tokens)))
        area += best * (token - cursor)
        if observation.valid and observation.feasible and observation.score is not None:
            best = max(best, max(0.0, float(observation.score) - baseline_score) / score_resolution)
        cursor = token
    area += best * (token_ceiling - cursor)
    return area / token_ceiling


def _p2_block_terminal(scheduled: dict[str, Any], arms: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = tuple(arms[arm_id]["status"] for arm_id in ARM_IDS)
    if all(status == "EVALUABLE" for status in statuses):
        status = "EVALUABLE"
    elif any(status == "NOT_EVALUABLE_RESOURCE" for status in statuses):
        status = "NOT_EVALUABLE_RESOURCE"
    else:
        status = "NOT_EVALUABLE"
    responses = {arm_id: float(arms[arm_id]["response_steps"]) for arm_id in ARM_IDS}
    contrasts = None
    secondary = None
    if status == "EVALUABLE":
        y00, y10, y01, y11 = (
            responses["neither"],
            responses["ada_only"],
            responses["evox_only"],
            responses["ada_evox"],
        )
        contrasts = {
            "ada_main_effect": 0.5 * ((y10 - y00) + (y11 - y01)),
            "evox_main_effect": 0.5 * ((y01 - y00) + (y11 - y10)),
            "ada_evox_interaction": y11 - y10 - y01 + y00,
        }
        auc = {arm_id: float(arms[arm_id]["token_anytime_auc_steps"]) for arm_id in ARM_IDS}
        secondary = {
            "ada_main_effect": 0.5 * ((auc["ada_only"] - auc["neither"]) + (auc["ada_evox"] - auc["evox_only"])),
            "evox_main_effect": 0.5 * ((auc["evox_only"] - auc["neither"]) + (auc["ada_evox"] - auc["ada_only"])),
            "ada_evox_interaction": auc["ada_evox"] - auc["ada_only"] - auc["evox_only"] + auc["neither"],
        }
    return {
        "block_index": scheduled["block_index"],
        "block_id": scheduled["block_id"],
        "task_id": scheduled["task_id"],
        "replicate_seed": scheduled["replicate_seed"],
        "arm_order": scheduled["arm_order"],
        "status": status,
        "arm_statuses": tuple((arm_id, arms[arm_id]["status"]) for arm_id in ARM_IDS),
        "responses": responses,
        "contrasts": contrasts,
        "secondary_auc_contrasts": secondary,
        "arm_record_digests": tuple((arm_id, digest_json(arms[arm_id])) for arm_id in ARM_IDS),
    }


def _aggregate_p2_factorial(
    manifest: dict[str, Any],
    blocks: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    required = int(manifest["failure_and_stop_rules"]["required_evaluable_blocks"])
    evaluable = tuple(block for block in blocks if block["status"] == "EVALUABLE")
    if len(blocks) != required or len(evaluable) != required:
        return {
            "protocol_id": manifest["protocol_id"],
            "protocol_manifest_digest": manifest["protocol_manifest_digest"],
            "status": "NOT_EVALUABLE",
            "claim_ceiling": manifest["claim_ceiling"],
            "required_blocks": required,
            "completed_blocks": len(blocks),
            "evaluable_blocks": len(evaluable),
            "block_record_digests": tuple(
                (block["block_id"], digest_json(block)) for block in blocks
            ),
            "estimands": None,
            "p3_authorized": False,
        }
    names = ("ada_main_effect", "evox_main_effect", "ada_evox_interaction")
    raw = {}
    for name in names:
        effects = tuple(float(block["contrasts"][name]) for block in evaluable)
        positives = sum(effect > 0 for effect in effects)
        negatives = sum(effect < 0 for effect in effects)
        raw[name] = {
            "effects": effects,
            "median_effect_steps": statistics.median(effects),
            "positive_blocks": positives,
            "tie_blocks": len(effects) - positives - negatives,
            "negative_blocks": negatives,
            "one_sided_exact_sign_p": _one_sided_sign_p(positives, negatives),
        }
    holm = _holm_one_sided({name: raw[name]["one_sided_exact_sign_p"] for name in names})
    estimands = {}
    for name in names:
        minimum = float(manifest["estimands"]["minimum_effect_steps"][name])
        estimands[name] = {
            **raw[name],
            "minimum_effect_steps": minimum,
            "holm_threshold": holm[name]["threshold"],
            "holm_rejected": holm[name]["rejected"],
            "verdict": (
                "POSITIVE_DEVELOPMENT_SIGNAL"
                if raw[name]["median_effect_steps"] >= minimum and holm[name]["rejected"]
                else "NOT_ESTABLISHED"
            ),
        }
    y11_noninferiority = {
        comparison: statistics.median(
            float(block["responses"]["ada_evox"]) - float(block["responses"][comparison])
            for block in evaluable
        )
        >= float(manifest["decision_rules"]["y11_noninferiority_margin_steps"])
        for comparison in ("neither", "ada_only", "evox_only")
    }
    p3 = (
        estimands["ada_evox_interaction"]["verdict"] == "POSITIVE_DEVELOPMENT_SIGNAL"
        and all(y11_noninferiority.values())
    )
    return {
        "protocol_id": manifest["protocol_id"],
        "protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "status": "P2_FACTORIAL_DEVELOPMENT_COMPLETE",
        "claim_ceiling": manifest["claim_ceiling"],
        "required_blocks": required,
        "completed_blocks": len(blocks),
        "evaluable_blocks": len(evaluable),
        "block_record_digests": tuple((block["block_id"], digest_json(block)) for block in blocks),
        "estimands": estimands,
        "y11_noninferiority": y11_noninferiority,
        "p3_authorized": p3,
    }


def _one_sided_sign_p(positives: int, negatives: int) -> float:
    n = positives + negatives
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(positives, n + 1)) / (2**n)


def _git_tree_digest(repository: Path) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD^{tree}"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tree = completed.stdout.strip()
    if len(tree) != 40:
        raise RuntimeError("P2 task repository did not produce a Git tree identity")
    return tree


def _holm_one_sided(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    result: dict[str, dict[str, Any]] = {}
    still_rejecting = True
    total = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        threshold = alpha / (total - index)
        rejected = still_rejecting and p_value <= threshold
        if not rejected:
            still_rejecting = False
        result[name] = {"threshold": threshold, "rejected": rejected}
    return result


def replay_p2_factorial_report(
    workspace: Path,
    *,
    repository: Path,
    provider_executable: Path,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = json.loads(
        (workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8")
    )
    verify_p2_factorial_execution_authority(
        manifest,
        repository=repository,
        provider_executable=provider_executable,
    )
    report = json.loads(
        (workspace / "result-artifacts" / "records" / REPORT_RECORD).read_text(encoding="utf-8")
    )
    blocks = tuple(
        json.loads(
            (
                workspace
                / "result-artifacts"
                / "records"
                / "blocks"
                / scheduled["block_id"]
                / "block-terminal.json"
            ).read_text(encoding="utf-8")
        )
        for scheduled in manifest["execution_schedule"]
    )
    recomputed = _aggregate_p2_factorial(manifest, blocks)
    issues = []
    if digest_json(report) != digest_json(recomputed):
        issues.append("REPORT_RECOMPUTATION_MISMATCH")
    return {
        "status": "REPLAY_PASS" if not issues else "REPLAY_INVALID",
        "issues": tuple(issues),
        "protocol_manifest_digest": manifest["protocol_manifest_digest"],
        "report_digest": digest_json(report),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Seal, run, or replay the P2 factorial V3 protocol")
    parser.add_argument("action", choices=("seal", "run", "replay"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--provider-executable", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.action == "seal":
        result = seal_p2_factorial_protocol(
            arguments.workspace,
            repository=arguments.repository,
            provider_executable=arguments.provider_executable,
        )
    elif arguments.action == "run":
        result = run_p2_factorial_protocol(
            arguments.workspace,
            repository=arguments.repository,
            provider_executable=arguments.provider_executable,
            progress=lambda message: print(message, flush=True),
        )
    else:
        result = replay_p2_factorial_report(
            arguments.workspace,
            repository=arguments.repository,
            provider_executable=arguments.provider_executable,
        )
    print(json.dumps(result, sort_keys=True, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
