from __future__ import annotations

import asyncio
import json
import math
import os
import random
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.br_a_tasks import br_a_tasks
from discoveryos.benchmarks.local_patch_admission import AdmissionArm, _initialize_arm
from discoveryos.benchmarks.real_code_tasks import admission_tasks
from discoveryos.benchmarks.search_policy_admission import (
    ResidualHeadroomEvidence,
    SearchObservation,
    compute_policy_metrics,
    evaluate_task_admission,
)
from discoveryos.benchmarks.search_value_mvp0 import (
    _arm_report,
    _build_spec,
    _evaluate_at,
    _evidence_value,
    _extra_metrics,
    _materialize_files,
    _score_source,
    _search_observations,
    _sum_usage,
    canonical_evidence_summary,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask, search_value_mvp0_tasks
from discoveryos.benchmarks.si2_shinka_adapter import SHINKA_SOURCE_COMMIT
from discoveryos.benchmarks.si2_tasks import (
    normalized_source,
    si2_confirmation_tasks,
    si2_discovery_tasks,
)
from discoveryos.benchmarks.strategy_integration_si1 import (
    CPU_CEILING,
    EVALUATION_RESERVE,
    GENERATION_RESERVE,
    SETTLEMENT_RESERVE,
    _arm_diagnostics,
    _controller_config,
)
from discoveryos.contracts.models import (
    EvidenceRecord,
    Fidelity,
    MetricDirection,
    ResourceBudget,
    ResourceUsage,
    RunMode,
)
from discoveryos.operators.action_controller import (
    AnytimeTraceRecorder,
    DeterministicActionController,
    SearchAction,
)
from discoveryos.operators.asha import RungDefinition
from discoveryos.operators.local_patch import LocalPatchOperator, PatchProvider
from discoveryos.operators.novelty import NoveltyConfig, ShinkaStyleNoveltyPolicy
from discoveryos.operators.parent_selection import (
    ParentSelectionConfig,
    ShinkaWeightedParentSelectionPolicy,
)
from discoveryos.operators.structural_rewrite import StructuralRewriteOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.search_loop import (
    LedgerBackedSearchStateProjector,
    SearchActionResult,
    SearchLoopRunner,
    SearchRunSpec,
    UnifiedActionExecutor,
)
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "DISCOVERYOS_SI2_FRESH_SEARCH_VALUE_TRIAL_V1"
MANIFEST_RECORD = "si2-sealed-pre-model-manifest.json"
DISCOVERY_REPORT_RECORD = "si2-discovery-report.json"
WINNER_RECORD = "si2-frozen-system-winner.json"
CONFIRMATION_REPORT_RECORD = "si2-confirmation-report.json"
ARM_NAMES = ("CORE", "CURRENT_DISCOVERYOS", "VANILLA_STRONG_AGENT", "EXTERNAL_STRONG_BASELINE")
TOKEN_CEILING = 100_000
WALL_CEILING = 1_800.0
CPU_CEILING_SI2 = CPU_CEILING
GENERATION_LIMIT = 3
REPLICATE_COUNT = 1
EXECUTION_ORDER_SEED = 17081702
MODEL_SEED = 170817
MINIMUM_EVALUABLE_DISCOVERY_TASKS = 8
SIGN_TEST_ALPHA = 0.10
SHINKA_REPOSITORY = "https://github.com/SakanaAI/ShinkaEvolve"
SHINKA_LICENSE = "Apache-2.0"
HEADLESS_PACKAGE = "@roberttlange/headless@0.6.1"


def seal_si2_protocol(
    workspace: Path,
    *,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    shinka_checkout: Path,
    shinka_python: Path,
    headless_cli: Path,
    node_executable: Path,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("SI-2 sealing requires an empty create-once workspace")
    if _git(repository_root, "status", "--porcelain").strip():
        raise RuntimeError("SI-2 must seal from a clean committed worktree")
    if local_provider.model != structural_provider.model:
        raise ValueError("SI-2 requires one model across internal generation paths")
    if local_provider.reasoning_effort != structural_provider.reasoning_effort or not local_provider.reasoning_effort:
        raise ValueError("SI-2 requires one explicit reasoning effort")
    provider_version = local_provider.provider_version
    if provider_version == "unknown" or structural_provider.provider_version != provider_version:
        raise RuntimeError("SI-2 requires one executable reportable provider version")
    external = _external_preflight(
        shinka_checkout,
        shinka_python,
        headless_cli,
        node_executable,
        model=local_provider.model,
        reasoning_effort=local_provider.reasoning_effort,
    )
    workspace.mkdir(parents=True, exist_ok=True)

    discovery_records = _materialize_task_cohort(
        workspace / "protocol" / "discovery-tasks",
        si2_discovery_tasks(),
        cohort_role="FRESH_DISCOVERY",
    )
    confirmation_records = _materialize_task_cohort(
        workspace / "protocol" / "confirmation-vault",
        si2_confirmation_tasks(),
        cohort_role="CONFIRMATION_WITHHELD_UNTIL_WINNER_FREEZE",
    )
    contamination = _contamination_receipt(si2_discovery_tasks(), si2_confirmation_tasks())
    if not all(contamination["checks"].values()):
        raise RuntimeError(f"SI-2 task contamination check failed: {contamination}")

    source_root = Path(__file__).resolve().parents[1]
    implementation_paths = (
        source_root / "benchmarks" / "si2.py",
        source_root / "benchmarks" / "si2_tasks.py",
        source_root / "benchmarks" / "si2_shinka_adapter.py",
        source_root / "operators" / "action_controller.py",
        source_root / "operators" / "parent_selection.py",
        source_root / "operators" / "novelty.py",
        source_root / "runtime" / "search_loop.py",
        source_root / "runtime" / "ledger.py",
    )
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SI2_SEALED_PRE_MODEL",
        "claim_ceiling": "SI2_FROZEN_TASK_DISTRIBUTION_MODEL_AND_RESOURCE_SURFACE_ONLY",
        "model_calls_before_seal": 0,
        "experiment_code_sha": _git(repository_root, "rev-parse", "HEAD").strip(),
        "implementation_digests": {
            str(path.relative_to(source_root)).replace("\\", "/"): digest_bytes(path.read_bytes())
            for path in implementation_paths
        },
        "cohorts": {
            "discovery": discovery_records,
            "confirmation": confirmation_records,
        },
        "contamination_receipt": contamination,
        "arms": {
            "CORE": {
                "system": "DiscoveryOS minimal unified loop",
                "generation_limit": GENERATION_LIMIT,
                "parent_selection": False,
                "novelty": False,
            },
            "CURRENT_DISCOVERYOS": {
                "system": "DiscoveryOS SI-1R complete current stack",
                "generation_limit": GENERATION_LIMIT,
                "parent_selection": "shinka_weighted_dos_v2_probability_cap",
                "maximum_selection_probability": 0.8,
                "novelty": "shinka_novelty_dos_v2_cheap_first_affordable",
            },
            "VANILLA_STRONG_AGENT": {
                "system": "bounded sequential strong agent with evaluator feedback and incumbent replacement",
                "generation_limit": GENERATION_LIMIT,
                "research_graph_or_parent_archive": False,
            },
            "EXTERNAL_STRONG_BASELINE": {
                "system": "SakanaAI/ShinkaEvolve official runtime",
                "generation_limit": GENERATION_LIMIT,
                **external,
            },
        },
        "model": {
            "provider": local_provider.provider_name,
            "model": local_provider.model,
            "reasoning_effort": local_provider.reasoning_effort,
            "provider_version": provider_version,
            "local_settings_digest": local_provider.settings_digest,
            "structural_settings_digest": structural_provider.settings_digest,
        },
        "matched_resources_per_task_arm": {
            "tokens": TOKEN_CEILING,
            "generation_wall_seconds": WALL_CEILING,
            "total_wall_seconds": WALL_CEILING,
            "internal_evaluator_cpu_safety_ceiling": CPU_CEILING_SI2,
            "cross_arm_cpu_matching": False,
            "unused_budget_transfer": False,
            "cache_accounting": "internal exact; Shinka Headless cache-token field unavailable and reported null",
            "primary_budget_axis": "input_plus_output_tokens",
        },
        "replicates": {
            "per_task_arm": REPLICATE_COUNT,
            "model_seed": MODEL_SEED,
            "limitation": "single model replicate; task-level inference only",
        },
        "metrics": {
            "primary": ["matched_token_final_best", "anytime_auc", "fresh_task_win_rate"],
            "anytime_checkpoints": [0.25, 0.50, 0.75, 1.00],
            "secondary": [
                "evaluator_calls", "generation_tokens", "generation_wall", "total_wall",
                "valid_candidate_rate", "mechanics_failure_rate", "structural_diversity", "basin_diversity",
            ],
            "tie_tolerance": "per-task frozen score_resolution",
            "missingness": "no post-seal task replacement; protocol failures remain separate from scientific loss",
        },
        "search_value_gate": {
            "confirmatory_comparisons": ["CURRENT_DISCOVERYOS_vs_CORE", "CURRENT_DISCOVERYOS_vs_VANILLA_STRONG_AGENT"],
            "minimum_evaluable_tasks": MINIMUM_EVALUABLE_DISCOVERY_TASKS,
            "wins_strictly_greater_than_losses": True,
            "median_final_delta_strictly_positive": True,
            "median_anytime_auc_delta_strictly_positive": True,
            "one_sided_exact_sign_test_alpha": SIGN_TEST_ALPHA,
            "multiplicity": "Holm across the two confirmatory comparisons at family-wise alpha 0.10",
        },
        "external_competitiveness_gate": {
            "comparison": "CURRENT_DISCOVERYOS_vs_EXTERNAL_STRONG_BASELINE",
            "minimum_evaluable_tasks": MINIMUM_EVALUABLE_DISCOVERY_TASKS,
            "wins_strictly_greater_than_losses": True,
            "median_final_delta_not_negative": True,
            "median_anytime_auc_delta_not_negative": True,
            "one_sided_exact_sign_test_alpha": SIGN_TEST_ALPHA,
        },
        "winner_rule": [
            "highest median matched-token final improvement",
            "highest median anytime AUC",
            "highest valid candidate rate",
            "lexicographically smallest arm id",
        ],
        "confirmation_gate": {
            "winner_is_create_once_before_access": True,
            "minimum_tasks_with_resolvable_improvement": 2,
            "task_count": len(confirmation_records),
            "median_improvement_strictly_positive": True,
            "all_resource_checks_pass": True,
            "confirmation_cannot_change_winner": True,
        },
        "execution_order_seed": EXECUTION_ORDER_SEED,
        "final_blind_access_before_winner_freeze": 0,
        "network_policy": {
            "internal_arms": "Codex provider only; candidate workspaces read-only to model",
            "external_arm": "Shinka Headless Codex only; pricing catalog offline; evaluator local",
        },
        "post_seal_changes": "new protocol version and experiment root; affected partial results invalid",
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "model_calls": 0,
        "discovery_task_count": len(discovery_records),
        "confirmation_task_count": len(confirmation_records),
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "experiment_code_sha": manifest["experiment_code_sha"],
    }


def run_si2_discovery(
    workspace: Path,
    *,
    manifest_digest: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_and_verify_manifest(workspace, manifest_digest, local_provider, structural_provider)
    report_path = workspace / "result-artifacts" / "records" / DISCOVERY_REPORT_RECORD
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    task_map = {item.task.task_id: item for item in si2_discovery_tasks()}
    schedule = [(record["task_id"], arm) for record in manifest["cohorts"]["discovery"] for arm in ARM_NAMES]
    random.Random(manifest["execution_order_seed"]).shuffle(schedule)
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for index, (task_id, arm_name) in enumerate(schedule, start=1):
        result_record = f"tasks/{task_id}/{arm_name}.json"
        result_path = workspace / "result-artifacts" / "records" / result_record
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            arm_root = workspace / "arms" / "discovery" / task_id / arm_name
            if arm_root.exists() and any(arm_root.iterdir()):
                raise RuntimeError(f"partial SI-2 arm exists without sealed result: {task_id}:{arm_name}")
            if progress:
                progress(f"SI-2 discovery {index}/{len(schedule)} starting {task_id}:{arm_name}")
            item = task_map[task_id]
            task_record = _task_record(manifest, "discovery", task_id)
            try:
                result = _run_arm_dispatch(
                    workspace,
                    manifest,
                    item,
                    task_record,
                    arm_name,
                    arm_root,
                    local_provider,
                    structural_provider,
                )
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                if arm_name != "EXTERNAL_STRONG_BASELINE":
                    raise
                result = _external_not_evaluable_report(manifest, item, error)
            ArtifactStore(workspace / "result-artifacts").write_record(result_record, result)
        results[(task_id, arm_name)] = result
        if progress:
            progress(
                f"SI-2 completed {task_id}:{arm_name} improvement={result['metrics']['best_improvement']:.6f} "
                f"auc={result['metrics']['auc_over_token_budget']:.6f} tokens={result['actual_usage']['tokens']}"
            )
    report = _aggregate_discovery(manifest, results)
    ArtifactStore(workspace / "result-artifacts").write_record(DISCOVERY_REPORT_RECORD, report)
    winner = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "winner_arm": report["winner"]["arm"],
        "winner_rule": manifest["winner_rule"],
        "winner_metrics": report["winner"],
        "discovery_report_digest": digest_json(report),
        "frozen_before_confirmation_access": True,
    }
    ArtifactStore(workspace / "result-artifacts").write_record(WINNER_RECORD, winner)
    return report


def run_si2_confirmation(
    workspace: Path,
    *,
    manifest_digest: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_and_verify_manifest(workspace, manifest_digest, local_provider, structural_provider)
    winner_path = workspace / "result-artifacts" / "records" / WINNER_RECORD
    discovery_path = workspace / "result-artifacts" / "records" / DISCOVERY_REPORT_RECORD
    if not winner_path.is_file() or not discovery_path.is_file():
        raise RuntimeError("SI-2 confirmation requires a frozen system winner and discovery report")
    winner = json.loads(winner_path.read_text(encoding="utf-8"))
    if winner.get("manifest_digest") != manifest_digest or not winner.get("frozen_before_confirmation_access"):
        raise RuntimeError("SI-2 winner binding is invalid")
    report_path = workspace / "result-artifacts" / "records" / CONFIRMATION_REPORT_RECORD
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    winner_arm = winner["winner_arm"]
    task_map = {item.task.task_id: item for item in si2_confirmation_tasks()}
    results = []
    for index, record in enumerate(manifest["cohorts"]["confirmation"], start=1):
        task_id = record["task_id"]
        if progress:
            progress(f"SI-2 confirmation {index}/{len(task_map)} starting {task_id}:{winner_arm}")
        arm_root = workspace / "arms" / "confirmation" / task_id / winner_arm
        result_record = f"confirmation/{task_id}/{winner_arm}.json"
        result_path = workspace / "result-artifacts" / "records" / result_record
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            if arm_root.exists() and any(arm_root.iterdir()):
                raise RuntimeError(f"partial confirmation arm exists without sealed result: {task_id}:{winner_arm}")
            try:
                result = _run_arm_dispatch(
                    workspace,
                    manifest,
                    task_map[task_id],
                    record,
                    winner_arm,
                    arm_root,
                    local_provider,
                    structural_provider,
                )
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                if winner_arm != "EXTERNAL_STRONG_BASELINE":
                    raise
                result = _external_not_evaluable_report(manifest, task_map[task_id], error)
            ArtifactStore(workspace / "result-artifacts").write_record(result_record, result)
        results.append(result)
    improvements = [item["metrics"]["best_improvement"] for item in results]
    resolvable = sum(
        value >= task_map[result["task_id"]].score_resolution - 1e-12
        for value, result in zip(improvements, results)
    )
    resource_ok = all(all(item["resource_checks"].values()) for item in results)
    checks = {
        "at_least_two_tasks_with_resolvable_improvement": resolvable >= 2,
        "median_improvement_strictly_positive": statistics.median(improvements) > 0,
        "all_resource_checks_pass": resource_ok,
        "winner_unchanged": winner_arm == winner["winner_arm"],
    }
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "winner_arm": winner_arm,
        "confirmation_task_count": len(results),
        "resolvable_improvement_task_count": resolvable,
        "median_improvement": statistics.median(improvements),
        "checks": checks,
        "verdict": "SI2_WINNER_CONFIRMED_ON_WITHHELD_COHORT" if all(checks.values()) else "SI2_WINNER_NOT_CONFIRMED_ON_WITHHELD_COHORT",
        "winner_changed": False,
        "claim_ceiling": manifest["claim_ceiling"],
        "results": results,
    }
    ArtifactStore(workspace / "result-artifacts").write_record(CONFIRMATION_REPORT_RECORD, report)
    return report


def _materialize_task_cohort(
    root: Path,
    tasks: tuple[SearchValueTask, ...],
    *,
    cohort_role: str,
) -> list[dict[str, Any]]:
    records = []
    for item in tasks:
        repository, commit = item.task.initialize_repository(root)
        evidence, details = _si2_headroom_evidence(item, repository)
        admission = evaluate_task_admission(evidence)
        if not admission["admitted"]:
            failed = [name for name, passed in admission["checks"].items() if not passed]
            raise RuntimeError(f"SI-2 task admission failed: {item.task.task_id}:{failed}")
        records.append(
            {
                "task_id": item.task.task_id,
                "category": item.task.category,
                "cohort_role": cohort_role,
                "generator_lineage": "SI2_HIDDEN_DETERMINISTIC_CASE_GENERATOR_V1",
                "task_payload_digest": item.payload_digest,
                "repository": str(repository),
                "repository_commit": commit,
                "files": {
                    path: digest_bytes((repository / path).read_bytes())
                    for path in (item.task.entrypoint, "public_tests.py", "evaluate.py", "requirements.lock")
                },
                "headroom_evidence": jsonable(evidence),
                "admission": admission,
                "independent_scores": details,
            }
        )
    return records


def _si2_headroom_evidence(
    item: SearchValueTask,
    repository: Path,
) -> tuple[ResidualHeadroomEvidence, dict[str, Any]]:
    baseline_scores = tuple(_score_source(item, repository, item.task.algorithm_source) for _ in range(2))
    reference_score = _score_source(item, repository, item.reference_source)
    intermediate_scores = tuple(_score_source(item, repository, source) for source in item.intermediate_sources)
    distinct = []
    for score in (*intermediate_scores, reference_score):
        if score > baseline_scores[0] and score not in distinct:
            distinct.append(score)
    evidence = ResidualHeadroomEvidence(
        task_id=item.task.task_id,
        task_payload_digest=item.payload_digest,
        initial_state_digest=digest_json(
            {"question": item.task.question, "algorithm_source": normalized_source(item.task.algorithm_source)}
        ),
        evaluator_id=f"si2-executable-{item.task.task_id}",
        evaluator_digest=digest_bytes(normalized_source(item.task.evaluator_source).encode("utf-8")),
        baseline_candidate_digest=digest_bytes(normalized_source(item.task.algorithm_source).encode("utf-8")),
        baseline_receipt_digest=digest_json({"scores": baseline_scores, "fidelity": Fidelity.G2.value}),
        baseline_score=baseline_scores[0],
        score_direction=MetricDirection.MAXIMIZE,
        score_resolution=item.score_resolution,
        reference_score=reference_score,
        reference_kind="independent_difficulty_generator",
        reference_digest=digest_bytes(normalized_source(item.reference_source).encode("utf-8")),
        selection_provenance_digest=digest_json(
            {"generator": "SI2_HIDDEN_DETERMINISTIC_CASE_GENERATOR_V1", "pre_model": True}
        ),
        valid_intermediate_scores=tuple(distinct),
        trajectory_classes=item.trajectory_classes,
        baseline_basin_id=item.baseline_basin_id,
        basin_labeler_digest=digest_json(
            {"baseline": item.baseline_basin_id, "local": "inherit", "external": "system_generation"}
        ),
        baseline_executable=True,
        baseline_replay_count=2,
        baseline_replay_consistent=math.isclose(baseline_scores[0], baseline_scores[1]),
        source_independent_of_compared_policies=True,
        pre_admission_model_calls=0,
    )
    return evidence, {
        "baseline_replays": baseline_scores,
        "intermediate_scores": intermediate_scores,
        "reference_score": reference_score,
        "reference_is_optimality_oracle": False,
    }


def _contamination_receipt(
    discovery: tuple[SearchValueTask, ...],
    confirmation: tuple[SearchValueTask, ...],
) -> dict[str, Any]:
    consumed = tuple(admission_tasks()) + tuple(br_a_tasks()) + tuple(item.task for item in search_value_mvp0_tasks())
    fresh = tuple(item.task for item in (*discovery, *confirmation))
    consumed_ids = {item.task_id for item in consumed}
    consumed_categories = {item.category for item in consumed}
    consumed_sources = {digest_bytes(normalized_source(item.algorithm_source).encode("utf-8")) for item in consumed}
    fresh_ids = [item.task_id for item in fresh]
    fresh_sources = [digest_bytes(normalized_source(item.algorithm_source).encode("utf-8")) for item in fresh]
    fresh_payloads = [item.payload_digest for item in (*discovery, *confirmation)]
    discovery_sources = {item.payload_digest for item in discovery}
    confirmation_sources = {item.payload_digest for item in confirmation}
    checks = {
        "fresh_task_ids_unique": len(fresh_ids) == len(set(fresh_ids)),
        "fresh_task_payloads_unique": len(fresh_payloads) == len(set(fresh_payloads)),
        "zero_consumed_task_id_overlap": not (set(fresh_ids) & consumed_ids),
        "zero_consumed_category_overlap": not ({item.category for item in fresh} & consumed_categories),
        "zero_consumed_baseline_source_overlap": not (set(fresh_sources) & consumed_sources),
        "discovery_confirmation_payload_disjoint": not (discovery_sources & confirmation_sources),
    }
    return {
        "consumed_task_count": len(consumed),
        "fresh_discovery_task_count": len(discovery),
        "withheld_confirmation_task_count": len(confirmation),
        "checks": checks,
        "semantic_pretraining_contamination_ruled_out": False,
        "freshness_claim": "unconsumed by DiscoveryOS and unavailable to trial arms before seal",
    }


def _external_preflight(
    checkout: Path,
    python: Path,
    headless_cli: Path,
    node_executable: Path,
    *,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    checkout = checkout.resolve()
    python = python.resolve()
    headless_cli = headless_cli.resolve()
    node_executable = node_executable.resolve()
    for path in (checkout, python, headless_cli, node_executable):
        if not path.exists():
            raise RuntimeError(f"SI-2 external preflight path missing: {path}")
    commit = _git(checkout, "rev-parse", "HEAD").strip()
    if commit != SHINKA_SOURCE_COMMIT:
        raise RuntimeError(f"Shinka commit differs from frozen source: {commit}")
    if _git(checkout, "status", "--porcelain").strip():
        raise RuntimeError("Shinka checkout must be clean for SI-2 sealing")
    version = subprocess.run(
        (str(python), "-c", "import shinka; print(shinka.__version__)"),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.strip()
    codex_executable = Path.home() / ".codex" / ".sandbox-bin" / "codex.exe"
    codex_version = subprocess.run(
        (str(codex_executable), "--version"),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout.strip()
    if not codex_version or "unknown" in codex_version.casefold():
        raise RuntimeError("external Headless Codex executable version is unavailable")
    env = os.environ.copy()
    env["PATH"] = str(codex_executable.parent) + os.pathsep + env.get("PATH", "")
    rendered = subprocess.run(
        (
            str(node_executable),
            str(headless_cli),
            "codex",
            "--prompt",
            "SI-2 mechanics-only command rendering; do not execute",
            "--work-dir",
            str(checkout),
            "--allow",
            "read-only",
            "--model",
            model,
            "--reasoning-effort",
            reasoning_effort,
            "--print-command",
        ),
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    if "codex" not in rendered.casefold() or model not in rendered or "exec" not in rendered:
        raise RuntimeError(f"Headless Codex command rendering mismatch: {rendered}")
    return {
        "repository": SHINKA_REPOSITORY,
        "source_commit": commit,
        "license": SHINKA_LICENSE,
        "package_version": version,
        "checkout": str(checkout),
        "python": str(python),
        "headless_package": HEADLESS_PACKAGE,
        "headless_cli": str(headless_cli),
        "headless_cli_sha256": digest_bytes(headless_cli.read_bytes()),
        "node_executable": str(node_executable),
        "codex_executable": str(codex_executable),
        "codex_version": codex_version,
        "mechanics_preflight": "PASS_ZERO_MODEL_CALLS",
        "headless_command_render_digest": digest_bytes(rendered.encode("utf-8")),
        "model_compatibility": "Headless Codex exact model and reasoning effort forwarded",
    }


def _run_arm_dispatch(
    workspace: Path,
    manifest: dict[str, Any],
    item: SearchValueTask,
    task_record: dict[str, Any],
    arm_name: str,
    arm_root: Path,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
) -> dict[str, Any]:
    if arm_name == "EXTERNAL_STRONG_BASELINE":
        return _run_external_arm(workspace, manifest, item, arm_root)
    arm = _initialize_arm(
        arm_root,
        item.task,
        Path(task_record["repository"]),
        task_record["repository_commit"],
        TOKEN_CEILING,
    )
    if arm_name == "VANILLA_STRONG_AGENT":
        return asyncio.run(_run_vanilla_strong_agent(arm, item, local_provider))
    return asyncio.run(
        _run_discoveryos_system_arm(
            arm,
            item,
            arm_name,
            local_provider,
            structural_provider,
            current=arm_name == "CURRENT_DISCOVERYOS",
        )
    )


async def _run_vanilla_strong_agent(
    arm: AdmissionArm,
    item: SearchValueTask,
    provider: PatchProvider,
) -> dict[str, Any]:
    started = time.monotonic()
    baseline = await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="si2-baseline")
    evidence_history: list[EvidenceRecord] = [baseline]
    incumbent = arm.baseline
    incumbent_score = _evidence_value(arm, baseline)[2] or 0.0
    incumbent_observation_id: str | None = None
    observations: list[SearchObservation] = []
    usages: list[ResourceUsage] = []
    mechanics_failures = 0
    evaluator_calls = 1
    operator = LocalPatchOperator(
        provider=provider,
        artifacts=arm.artifacts,
        ledger=arm.ledger,
        contract=arm.contract,
        strategy_id="si2_vanilla_strong_agent",
    )
    for step in range(GENERATION_LIMIT):
        consumed = _sum_usage(usages)
        remaining = ResourceBudget(
            tokens=max(0, TOKEN_CEILING - consumed.tokens),
            wall_seconds=max(0.0, WALL_CEILING - consumed.wall_seconds),
            cpu_seconds=max(0.0, CPU_CEILING_SI2 - consumed.cpu_seconds),
        )
        bundle = __import__(
            "discoveryos.contracts.executable",
            fromlist=["ExecutableCandidateBundle"],
        ).ExecutableCandidateBundle.from_artifact(arm.artifacts, incumbent.artifact_digest)
        result = operator.propose(
            parent=incumbent,
            mutable_files=_materialize_files(bundle, arm.contract.mutable_paths),
            development_evidence_summary=canonical_evidence_summary(tuple(evidence_history)),
            failure_signature=evidence_history[-1].failure_signature,
            semantic_delta_memory=tuple(candidate.semantic_delta for candidate in (arm.baseline, incumbent)),
            remaining_budget=remaining,
            build=_build_spec(bundle),
        )
        usages.append(result.record.usage)
        evidence = None
        if result.candidate is not None:
            evidence = await _evaluate_at(
                arm,
                result.candidate,
                Fidelity.G2,
                seed=0,
                attempt=f"si2-vanilla-step-{step}",
            )
            evidence_history.append(evidence)
            usages.append(evidence.resource_usage)
            evaluator_calls += 1
        valid, feasible, score = _evidence_value(arm, evidence)
        if result.candidate is None or not valid:
            mechanics_failures += 1
        cumulative = _sum_usage(usages)
        observation_id = result.candidate.candidate_id if result.candidate else result.record.generation_id
        observations.append(
            SearchObservation(
                candidate_id=observation_id,
                parent_id=incumbent_observation_id,
                cumulative_tokens=cumulative.tokens,
                cumulative_wall_seconds=cumulative.wall_seconds,
                score=score,
                valid=valid,
                feasible=feasible,
                basin_id="vanilla_sequential_frontier" if valid and feasible else None,
            )
        )
        if result.candidate is not None and valid and feasible and score is not None and score > incumbent_score:
            incumbent = result.candidate
            incumbent_score = score
            incumbent_observation_id = observation_id
    headroom = _si2_headroom_for_arm(item, arm)
    observation_tuple = tuple(observations)
    metrics = compute_policy_metrics(
        headroom,
        observation_tuple,
        token_budget=TOKEN_CEILING,
        wall_budget=WALL_CEILING,
    )
    metrics.update(_extra_metrics(observation_tuple, TOKEN_CEILING, headroom))
    usage = _sum_usage(usages)
    report = _arm_report(
        arm_name="VANILLA_STRONG_AGENT",
        task_id=item.task.task_id,
        metrics=metrics,
        observations=observation_tuple,
        usage=usage,
        makespan=time.monotonic() - started,
        token_ceiling=TOKEN_CEILING,
        wall_ceiling=WALL_CEILING,
        action_counts={"SEQUENTIAL_AGENT_GENERATION": GENERATION_LIMIT},
        mechanics_failures=mechanics_failures,
    )
    report["evaluator_calls"] = evaluator_calls
    report["diagnostics"] = {"structural_diversity": None, "basin_diversity": None}
    return report


async def _run_discoveryos_system_arm(
    arm: AdmissionArm,
    item: SearchValueTask,
    arm_name: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    *,
    current: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="si2-baseline")
    parent_config = (
        ParentSelectionConfig(
            policy_version="shinka_weighted_dos_v2_probability_cap",
            selection_lambda=10.0,
            base_seed=MODEL_SEED + int(digest_json(item.task.task_id)[:6], 16),
            maximum_selection_probability=0.8,
        )
        if current
        else None
    )
    novelty_config = (
        NoveltyConfig(
            policy_version="shinka_novelty_dos_v2_cheap_first_affordable",
            max_novelty_attempts=2,
            affordability_gate=True,
        )
        if current
        else None
    )
    config = _controller_config(current, affordable_resampling=True)
    spec = SearchRunSpec(
        run_id=f"si2-{item.task.task_id}-{arm_name.casefold()}",
        contract_digest=arm.contract.digest,
        root_candidate_id=arm.baseline.candidate_id,
        branch_id="si2-active-frontier",
        initial_algorithm_family=item.baseline_basin_id,
        metric_name="score",
        metric_direction=MetricDirection.MAXIMIZE,
        initial_fidelity=Fidelity.G1,
        budget=ResourceBudget(tokens=TOKEN_CEILING, cpu_seconds=CPU_CEILING_SI2, wall_seconds=WALL_CEILING),
        rungs=(
            RungDefinition("si2-g1", Fidelity.G1, EVALUATION_RESERVE),
            RungDefinition("si2-g2", Fidelity.G2, ResourceBudget(cpu_seconds=10, wall_seconds=60)),
        ),
        eta=100,
        initial_trials=100,
        local_action_limit=GENERATION_LIMIT,
        structural_action_limit=0,
        max_steps=GENERATION_LIMIT,
        mutable_file_paths=(item.task.entrypoint,),
        seeds=tuple(range(10)),
        parent_selection=parent_config,
        novelty=novelty_config,
        mode=RunMode.BENCHMARK,
    )
    projector = LedgerBackedSearchStateProjector(
        spec=spec,
        contract=arm.contract,
        controller_config=config,
        ledger=arm.ledger,
        artifacts=arm.artifacts,
    )
    parent_policy = ShinkaWeightedParentSelectionPolicy(parent_config) if parent_config else None
    novelty_policy = ShinkaStyleNoveltyPolicy(novelty_config) if novelty_config else None
    executor = UnifiedActionExecutor(
        spec=spec,
        contract=arm.contract,
        ledger=arm.ledger,
        artifacts=arm.artifacts,
        projector=projector,
        local_operator=LocalPatchOperator(
            provider=local_provider,
            artifacts=arm.artifacts,
            ledger=arm.ledger,
            contract=arm.contract,
        ),
        structural_operator=StructuralRewriteOperator(
            provider=structural_provider,
            artifacts=arm.artifacts,
            ledger=arm.ledger,
            contract=arm.contract,
        ),
        experiment_executor=arm.executor,
        novelty_policy=novelty_policy,
    )
    loop = await SearchLoopRunner(
        controller=DeterministicActionController(config, parent_policy),
        projector=projector,
        executor=executor,
        trace=AnytimeTraceRecorder(arm.artifacts, arm.ledger),
    ).run()
    actions = tuple(
        SearchActionResult.from_dict(payload)
        for payload in arm.ledger.search_action_payloads(spec.run_id)
    )
    observations = _search_observations(arm, item, actions)
    headroom = _si2_headroom_for_arm(item, arm)
    metrics = compute_policy_metrics(
        headroom,
        observations,
        token_budget=TOKEN_CEILING,
        wall_budget=WALL_CEILING,
    )
    metrics.update(_extra_metrics(observations, TOKEN_CEILING, headroom))
    usage = _sum_usage(action.actual_usage for action in actions)
    report = _arm_report(
        arm_name=arm_name,
        task_id=item.task.task_id,
        metrics=metrics,
        observations=observations,
        usage=usage,
        makespan=time.monotonic() - started,
        token_ceiling=TOKEN_CEILING,
        wall_ceiling=WALL_CEILING,
        action_counts={
            action.value: sum(result.action is action for result in actions)
            for action in SearchAction
            if action is not SearchAction.STOP
        },
        mechanics_failures=sum(bool(action.failure_signature) for action in actions),
        stop_reason=loop.stop_decision.reason_codes,
    )
    report["evaluator_calls"] = 1 + sum(action.evidence_receipt_id is not None for action in actions)
    report["diagnostics"] = _arm_diagnostics(arm, spec, actions, observations, headroom.baseline_score)
    return report


def _run_external_arm(
    workspace: Path,
    manifest: dict[str, Any],
    item: SearchValueTask,
    arm_root: Path,
) -> dict[str, Any]:
    external = manifest["arms"]["EXTERNAL_STRONG_BASELINE"]
    model = manifest["model"]
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "SHINKA_PRICING_MODE": "offline",
            "SHINKA_HEADLESS_COMMAND": (
                f"{Path(external['node_executable']).as_posix()} {Path(external['headless_cli']).as_posix()}"
            ),
        }
    )
    codex_dir = str(Path(external["codex_executable"]).parent)
    env["PATH"] = codex_dir + os.pathsep + env.get("PATH", "")
    command = (
        external["python"],
        "-m",
        "discoveryos.benchmarks.si2_shinka_adapter",
        "--task-id",
        item.task.task_id,
        "--results-dir",
        str(arm_root),
        "--model",
        model["model"],
        "--reasoning-effort",
        model["reasoning_effort"],
        "--generations",
        str(GENERATION_LIMIT),
        "--token-ceiling",
        str(TOKEN_CEILING),
        "--seed",
        str(MODEL_SEED),
    )
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=workspace,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=WALL_CEILING,
        check=False,
    )
    makespan = time.monotonic() - started
    output_path = arm_root / "si2-shinka-arm-result.json"
    if completed.returncode != 0 or not output_path.is_file():
        raise RuntimeError(
            f"SI-2 external arm failed {item.task.task_id}: rc={completed.returncode} "
            f"stderr={completed.stderr[-2000:]} stdout={completed.stdout[-2000:]}"
        )
    raw = json.loads(output_path.read_text(encoding="utf-8"))
    headroom = _headroom_from_record(item, manifest, item.task.task_id)
    observations = tuple(
        SearchObservation(
            candidate_id=str(entry["candidate_id"]),
            parent_id=entry.get("parent_id"),
            cumulative_tokens=int(entry["cumulative_tokens"]),
            cumulative_wall_seconds=makespan * index / max(1, len(raw["observations"])),
            score=float(entry["score"]) if entry.get("valid") else None,
            valid=bool(entry.get("valid")),
            feasible=bool(entry.get("valid")),
            basin_id="shinka_official_population" if entry.get("valid") else None,
        )
        for index, entry in enumerate(raw["observations"], start=1)
    )
    metrics = compute_policy_metrics(
        headroom,
        observations,
        token_budget=TOKEN_CEILING,
        wall_budget=WALL_CEILING,
    )
    metrics.update(_extra_metrics(observations, TOKEN_CEILING, headroom))
    usage = raw["actual_usage"]
    materialized = max(1, len(observations))
    return {
        "task_id": item.task.task_id,
        "arm": "EXTERNAL_STRONG_BASELINE",
        "metrics": metrics,
        "observations": [jsonable(entry) for entry in observations],
        "action_counts": {"SHINKA_GENERATION": GENERATION_LIMIT},
        "stop_reason": (),
        "actual_usage": {
            "tokens": int(usage["tokens"]),
            "llm_input_tokens": int(usage["llm_input_tokens"]),
            "llm_output_tokens": int(usage["llm_output_tokens"]),
            "llm_cache_tokens": None,
            "end_to_end_makespan": makespan,
        },
        "invalid_generation_rate": sum(not item.valid for item in observations) / materialized,
        "mechanics_failure_rate": 0.0,
        "evaluator_calls": int(raw["evaluator_calls"]),
        "resource_checks": {
            "token_ceiling_respected": int(usage["tokens"]) <= TOKEN_CEILING,
            "wall_ceiling_with_tolerance_respected": makespan <= WALL_CEILING * 1.05,
        },
        "diagnostics": {
            "structural_diversity": len({entry["source_digest"] for entry in raw["observations"]}),
            "basin_diversity": None,
            "external_source_commit": external["source_commit"],
        },
    }


def _external_not_evaluable_report(
    manifest: dict[str, Any],
    item: SearchValueTask,
    error: BaseException,
) -> dict[str, Any]:
    headroom = _headroom_from_record(item, manifest, item.task.task_id)
    observations: tuple[SearchObservation, ...] = ()
    metrics = compute_policy_metrics(
        headroom,
        observations,
        token_budget=TOKEN_CEILING,
        wall_budget=WALL_CEILING,
    )
    metrics.update(_extra_metrics(observations, TOKEN_CEILING, headroom))
    return {
        "task_id": item.task.task_id,
        "arm": "EXTERNAL_STRONG_BASELINE",
        "status": "EXTERNAL_BASELINE_NOT_EVALUABLE",
        "failure_signature": f"{type(error).__name__}:{error}",
        "metrics": metrics,
        "observations": [],
        "action_counts": {"SHINKA_GENERATION": 0},
        "stop_reason": ("external_runtime_failure",),
        "actual_usage": {
            "tokens": None,
            "llm_input_tokens": None,
            "llm_output_tokens": None,
            "llm_cache_tokens": None,
            "end_to_end_makespan": None,
            "accounting_status": "UNAVAILABLE_AFTER_EXTERNAL_RUNTIME_FAILURE",
        },
        "invalid_generation_rate": 1.0,
        "mechanics_failure_rate": 1.0,
        "evaluator_calls": 0,
        "resource_checks": {
            "token_ceiling_respected": False,
            "wall_ceiling_with_tolerance_respected": False,
        },
        "diagnostics": {
            "structural_diversity": None,
            "basin_diversity": None,
            "external_source_commit": manifest["arms"]["EXTERNAL_STRONG_BASELINE"]["source_commit"],
        },
    }


def _aggregate_discovery(
    manifest: dict[str, Any],
    results: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    tasks = manifest["cohorts"]["discovery"]
    by_arm = {
        arm: {
            "median_final_improvement": statistics.median(
                results[(task["task_id"], arm)]["metrics"]["best_improvement"] for task in tasks
            ),
            "median_anytime_auc": statistics.median(
                results[(task["task_id"], arm)]["metrics"]["auc_over_token_budget"] for task in tasks
            ),
            "valid_candidate_rate": statistics.mean(
                1.0 - results[(task["task_id"], arm)]["invalid_generation_rate"] for task in tasks
            ),
            "total_tokens": sum(
                value
                for task in tasks
                if isinstance(
                    value := results[(task["task_id"], arm)]["actual_usage"]["tokens"],
                    int,
                )
            ),
            "usage_accounting_complete_tasks": sum(
                isinstance(results[(task["task_id"], arm)]["actual_usage"]["tokens"], int)
                for task in tasks
            ),
            "total_evaluator_calls": sum(results[(task["task_id"], arm)].get("evaluator_calls", 0) for task in tasks),
        }
        for arm in ARM_NAMES
    }
    comparisons = {
        baseline: _paired_comparison(manifest, results, baseline)
        for baseline in ("CORE", "VANILLA_STRONG_AGENT", "EXTERNAL_STRONG_BASELINE")
    }
    pvalues = {
        name: comparisons[name]["one_sided_exact_sign_p"]
        for name in ("CORE", "VANILLA_STRONG_AGENT")
    }
    holm = _holm_two(pvalues, SIGN_TEST_ALPHA)
    internal_checks = {
        baseline: {
            "minimum_evaluable_tasks": comparisons[baseline]["evaluable_tasks"] >= MINIMUM_EVALUABLE_DISCOVERY_TASKS,
            "wins_greater_than_losses": comparisons[baseline]["wins"] > comparisons[baseline]["losses"],
            "median_final_delta_positive": comparisons[baseline]["median_final_delta"] > 0,
            "median_auc_delta_positive": comparisons[baseline]["median_auc_delta"] > 0,
            "holm_sign_test_pass": holm[baseline],
        }
        for baseline in ("CORE", "VANILLA_STRONG_AGENT")
    }
    internal_resource_ok = all(
        all(results[(task["task_id"], arm)]["resource_checks"].values())
        for task in tasks
        for arm in ("CORE", "CURRENT_DISCOVERYOS", "VANILLA_STRONG_AGENT")
    )
    external_resource_ok = all(
        all(results[(task["task_id"], "EXTERNAL_STRONG_BASELINE")]["resource_checks"].values())
        for task in tasks
    )
    search_value_pass = internal_resource_ok and all(all(checks.values()) for checks in internal_checks.values())
    external = comparisons["EXTERNAL_STRONG_BASELINE"]
    external_checks = {
        "minimum_evaluable_tasks": external["evaluable_tasks"] >= MINIMUM_EVALUABLE_DISCOVERY_TASKS,
        "wins_greater_than_losses": external["wins"] > external["losses"],
        "median_final_delta_not_negative": external["median_final_delta"] >= 0,
        "median_auc_delta_not_negative": external["median_auc_delta"] >= 0,
        "sign_test_pass": external["one_sided_exact_sign_p"] <= SIGN_TEST_ALPHA,
        "resource_protection": external_resource_ok,
    }
    eligible_arms = [
        arm
        for arm in ARM_NAMES
        if all(all(results[(task["task_id"], arm)]["resource_checks"].values()) for task in tasks)
    ]
    ranked = sorted(
        eligible_arms,
        key=lambda arm: (
            -by_arm[arm]["median_final_improvement"],
            -by_arm[arm]["median_anytime_auc"],
            -by_arm[arm]["valid_candidate_rate"],
            arm,
        ),
    )
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest["manifest_digest"],
        "experiment_code_sha": manifest["experiment_code_sha"],
        "task_count": len(tasks),
        "replicates_per_task_arm": REPLICATE_COUNT,
        "arm_summaries": by_arm,
        "comparisons": comparisons,
        "holm_sign_test": {"alpha": SIGN_TEST_ALPHA, "passes": holm, "pvalues": pvalues},
        "search_value_checks": internal_checks,
        "internal_resource_protection": internal_resource_ok,
        "external_resource_protection": external_resource_ok,
        "search_value_verdict": (
            "DISCOVERYOS_SEARCH_VALUE_ESTABLISHED_ON_SI2_DISTRIBUTION"
            if search_value_pass
            else "SI2_SEARCH_VALUE_NOT_ESTABLISHED"
        ),
        "external_competitiveness_checks": external_checks,
        "external_competitiveness_verdict": (
            "DISCOVERYOS_EXTERNAL_COMPETITIVENESS_ESTABLISHED_ON_SI2_DISTRIBUTION"
            if all(external_checks.values())
            else "DISCOVERYOS_EXTERNAL_COMPETITIVENESS_NOT_ESTABLISHED"
        ),
        "winner": {"arm": ranked[0], **by_arm[ranked[0]]} if ranked else {"arm": None},
        "winner_ranking": ranked,
        "claim_ceiling": manifest["claim_ceiling"],
        "results": {
            f"{task_id}:{arm}": result
            for (task_id, arm), result in sorted(results.items())
        },
    }
    return report


def _paired_comparison(
    manifest: dict[str, Any],
    results: dict[tuple[str, str], dict[str, Any]],
    baseline_arm: str,
) -> dict[str, Any]:
    rows = []
    wins = ties = losses = 0
    for task in manifest["cohorts"]["discovery"]:
        task_id = task["task_id"]
        current = results[(task_id, "CURRENT_DISCOVERYOS")]
        baseline = results[(task_id, baseline_arm)]
        resolution = float(task["headroom_evidence"]["score_resolution"])
        final_delta = current["metrics"]["best_improvement"] - baseline["metrics"]["best_improvement"]
        auc_delta = current["metrics"]["auc_over_token_budget"] - baseline["metrics"]["auc_over_token_budget"]
        evaluable = all(current["resource_checks"].values()) and all(baseline["resource_checks"].values())
        if not evaluable:
            outcome = "NOT_EVALUABLE"
        elif final_delta >= resolution - 1e-12:
            outcome = "WIN"; wins += 1
        elif final_delta <= -resolution + 1e-12:
            outcome = "LOSS"; losses += 1
        else:
            outcome = "TIE"; ties += 1
        rows.append(
            {
                "task_id": task_id,
                "outcome": outcome,
                "score_resolution": resolution,
                "final_delta": final_delta,
                "auc_delta": auc_delta,
            }
        )
    evaluable_rows = [row for row in rows if row["outcome"] != "NOT_EVALUABLE"]
    return {
        "baseline_arm": baseline_arm,
        "evaluable_tasks": len(evaluable_rows),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "fresh_task_win_rate": wins / max(1, len(evaluable_rows)),
        "median_final_delta": statistics.median(row["final_delta"] for row in evaluable_rows) if evaluable_rows else 0.0,
        "median_auc_delta": statistics.median(row["auc_delta"] for row in evaluable_rows) if evaluable_rows else 0.0,
        "one_sided_exact_sign_p": _one_sided_sign_p(wins, losses),
        "rows": rows,
    }


def _one_sided_sign_p(wins: int, losses: int) -> float:
    count = wins + losses
    if count == 0:
        return 1.0
    return sum(math.comb(count, value) for value in range(wins, count + 1)) / (2**count)


def _holm_two(pvalues: dict[str, float], alpha: float) -> dict[str, bool]:
    ordered = sorted(pvalues, key=lambda name: (pvalues[name], name))
    passes = {name: False for name in pvalues}
    if pvalues[ordered[0]] <= alpha / 2:
        passes[ordered[0]] = True
        if pvalues[ordered[1]] <= alpha:
            passes[ordered[1]] = True
    return passes


def _load_and_verify_manifest(
    workspace: Path,
    expected_digest: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
) -> dict[str, Any]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    if not path.is_file():
        raise RuntimeError("SI-2 sealed manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("SI-2 manifest digest mismatch")
    if manifest.get("status") != "SI2_SEALED_PRE_MODEL" or manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("SI-2 manifest was not sealed before model execution")
    repository_root = Path(__file__).resolve().parents[3]
    if _git(repository_root, "rev-parse", "HEAD").strip() != manifest["experiment_code_sha"]:
        raise RuntimeError("SI-2 experiment code SHA drifted after sealing")
    source_root = Path(__file__).resolve().parents[1]
    for relative, expected in manifest["implementation_digests"].items():
        candidate = source_root / relative
        if not candidate.is_file() or digest_bytes(candidate.read_bytes()) != expected:
            raise RuntimeError(f"SI-2 implementation drift: {relative}")
    model = manifest["model"]
    if (
        local_provider.provider_name != model["provider"]
        or local_provider.model != model["model"]
        or local_provider.reasoning_effort != model["reasoning_effort"]
        or local_provider.provider_version != model["provider_version"]
        or local_provider.settings_digest != model["local_settings_digest"]
        or structural_provider.settings_digest != model["structural_settings_digest"]
    ):
        raise RuntimeError("SI-2 provider/model/settings differ from sealed manifest")
    task_map = {
        item.task.task_id: item
        for item in (*si2_discovery_tasks(), *si2_confirmation_tasks())
    }
    for cohort in ("discovery", "confirmation"):
        for record in manifest["cohorts"][cohort]:
            item = task_map.get(record["task_id"])
            repository = Path(record["repository"])
            if item is None or item.payload_digest != record["task_payload_digest"]:
                raise RuntimeError(f"SI-2 task definition drift: {record['task_id']}")
            if _git(repository, "status", "--porcelain").strip() or _git(repository, "rev-parse", "HEAD").strip() != record["repository_commit"]:
                raise RuntimeError(f"SI-2 task repository drift: {record['task_id']}")
            for relative, expected in record["files"].items():
                if digest_bytes((repository / relative).read_bytes()) != expected:
                    raise RuntimeError(f"SI-2 task file drift: {record['task_id']}:{relative}")
    external = manifest["arms"]["EXTERNAL_STRONG_BASELINE"]
    if _git(Path(external["checkout"]), "rev-parse", "HEAD").strip() != external["source_commit"]:
        raise RuntimeError("SI-2 external source commit drift")
    if digest_bytes(Path(external["headless_cli"]).read_bytes()) != external["headless_cli_sha256"]:
        raise RuntimeError("SI-2 Headless CLI drift")
    return manifest


def _si2_headroom_for_arm(item: SearchValueTask, arm: AdmissionArm) -> ResidualHeadroomEvidence:
    bundle = __import__(
        "discoveryos.contracts.executable",
        fromlist=["ExecutableCandidateBundle"],
    ).ExecutableCandidateBundle.from_artifact(arm.artifacts, arm.baseline.artifact_digest)
    return _si2_headroom_evidence(item, Path(bundle.base_repository))[0]


def _headroom_from_record(
    item: SearchValueTask,
    manifest: dict[str, Any],
    task_id: str,
) -> ResidualHeadroomEvidence:
    for cohort in ("discovery", "confirmation"):
        for record in manifest["cohorts"][cohort]:
            if record["task_id"] == task_id:
                return _si2_headroom_evidence(item, Path(record["repository"]))[0]
    raise KeyError(task_id)


def _task_record(manifest: dict[str, Any], cohort: str, task_id: str) -> dict[str, Any]:
    matches = [record for record in manifest["cohorts"][cohort] if record["task_id"] == task_id]
    if len(matches) != 1:
        raise KeyError(f"SI-2 task record not unique: {cohort}:{task_id}")
    return matches[0]


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout
