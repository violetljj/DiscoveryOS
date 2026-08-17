from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.search_value_mvp0 import STRUCTURAL_PATCH_SCHEMA
from discoveryos.benchmarks.search_value_mvp0_tasks import search_value_mvp0_tasks
from discoveryos.benchmarks.task_types import SearchValueTask, normalized_source
from discoveryos.harness import audit_p2_factorial_profiles, capture_git_source_snapshot
from discoveryos.providers.codex_exec import CodexExecProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "DISCOVERYOS_P2_ADA_EVOX_FACTORIAL_DEVELOPMENT_V1"
MANIFEST_RECORD = "p2-factorial-development-v1-manifest.json"
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
                    "task_repository_commit": commit,
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
            "same_max_steps": GENERATION_CALL_CEILING,
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
