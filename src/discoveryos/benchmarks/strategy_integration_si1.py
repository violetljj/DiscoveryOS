from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.local_patch_admission import AdmissionArm, _initialize_arm
from discoveryos.benchmarks.search_policy_admission import compute_policy_metrics
from discoveryos.benchmarks.search_value_mvp0 import (
    _arm_report,
    _evaluate_at,
    _extra_metrics,
    _headroom_from_item,
    _search_observations,
    _sum_usage,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask, search_value_mvp0_tasks
from discoveryos.contracts.models import Fidelity, MetricDirection, ResourceBudget, RunMode
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
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


PROTOCOL_ID = "DISCOVERYOS_STRATEGY_INTEGRATION_SI1_DEVELOPMENT_V1"
REPAIR_PROTOCOL_ID = "DISCOVERYOS_SI1R_PARENT_NOVELTY_REPAIR_DEVELOPMENT_V1"
MANIFEST_RECORD = "si1-development-manifest.json"
REPORT_RECORD = "si1-development-report.json"
REPAIR_MANIFEST_RECORD = "si1r-development-manifest.json"
REPAIR_REPORT_RECORD = "si1r-development-report.json"
SHINKA_PAPER = "arXiv:2509.19349v1"
SHINKA_SOURCE_COMMIT = "2bf8cfeb6fd39c79555cd94a8f395d64e740aae8"
DEFAULT_TASK_IDS = (
    "bounded_knapsack_alpha",
    "conflict_coloring_alpha",
    "load_balance_alpha",
)
ARM_NAMES = ("CORE", "CORE_PARENT", "CORE_NOVELTY", "CORE_PARENT_NOVELTY")
TOKEN_CEILING = 100_000
WALL_CEILING = 1_800.0
CPU_CEILING = 300.0
GENERATION_RESERVE = ResourceBudget(tokens=25_000, wall_seconds=300)
EVALUATION_RESERVE = ResourceBudget(cpu_seconds=5, wall_seconds=30)
SETTLEMENT_RESERVE = ResourceBudget(wall_seconds=1)


def run_strategy_integration_si1_pilot(
    workspace: Path,
    *,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    task_ids: tuple[str, ...] = DEFAULT_TASK_IDS,
    max_workers: int = 3,
    progress: Callable[[str], None] | None = None,
    repair_mode: bool = False,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    report_record = REPAIR_REPORT_RECORD if repair_mode else REPORT_RECORD
    manifest_record = REPAIR_MANIFEST_RECORD if repair_mode else MANIFEST_RECORD
    protocol_id = REPAIR_PROTOCOL_ID if repair_mode else PROTOCOL_ID
    if workspace.exists() and any(workspace.iterdir()):
        report_path = workspace / "result-artifacts" / "records" / report_record
        if report_path.is_file():
            return json.loads(report_path.read_text(encoding="utf-8"))
        raise RuntimeError("SI-1 development pilot requires an empty workspace")
    if local_provider.model != structural_provider.model:
        raise ValueError("SI-1 arms require one frozen model")
    if local_provider.reasoning_effort != structural_provider.reasoning_effort:
        raise ValueError("SI-1 arms require one frozen reasoning effort")
    if not local_provider.reasoning_effort:
        raise ValueError("SI-1 requires an explicit reasoning effort")
    provider_version = local_provider.provider_version
    if provider_version == "unknown" or structural_provider.provider_version != provider_version:
        raise RuntimeError("SI-1 requires one executable reportable provider version")
    workspace.mkdir(parents=True, exist_ok=True)
    task_map = {item.task.task_id: item for item in search_value_mvp0_tasks()}
    if any(task_id not in task_map for task_id in task_ids):
        raise ValueError("SI-1 task ids must come from the consumed MVP-0 task suite")
    selected = tuple(task_map[task_id] for task_id in task_ids)
    categories = [item.task.category for item in selected]
    if len(categories) != len(set(categories)):
        raise ValueError("SI-1 small pilot selects one consumed task per task family")
    task_records: list[dict[str, Any]] = []
    repositories: dict[str, tuple[Path, str]] = {}
    for item in selected:
        repository, commit = item.task.initialize_repository(workspace / "protocol" / "tasks")
        repositories[item.task.task_id] = (repository, commit)
        task_records.append(
            {
                "task_id": item.task.task_id,
                "category": item.task.category,
                "corpus_role": "CONSUMED_MVP0_DEVELOPMENT_ONLY",
                "task_payload_digest": item.payload_digest,
                "repository": str(repository),
                "repository_commit": commit,
            }
        )
    source_root = Path(__file__).resolve().parents[1]
    manifest_payload = {
        "protocol_id": protocol_id,
        "status": "SEALED_DEVELOPMENT_PRE_MODEL",
        "claim_ceiling": "DEVELOPMENT_ONLY_NO_FRESH_ADMISSION",
        "model_calls_before_seal": 0,
        "official_source": {
            "paper": SHINKA_PAPER,
            "repository": "SakanaAI/ShinkaEvolve",
            "source_commit": SHINKA_SOURCE_COMMIT,
        },
        "implementation_digests": {
            str(path.relative_to(source_root)).replace("\\", "/"): digest_bytes(path.read_bytes())
            for path in (
                source_root / "benchmarks" / "strategy_integration_si1.py",
                source_root / "operators" / "parent_selection.py",
                source_root / "operators" / "novelty.py",
                source_root / "operators" / "action_controller.py",
                source_root / "runtime" / "ledger.py",
                source_root / "runtime" / "search_loop.py",
            )
        },
        "tasks": task_records,
        "arms": {
            name: {
                "parent_selection": "PARENT" in name,
                "novelty_rejection": "NOVELTY" in name,
                "operator": "bounded_llm_local_patch_v1",
                "max_settled_steps": 3,
                "structural_actions": 0,
            }
            for name in ARM_NAMES
        },
        "matched_resources_per_task_arm": {
            "tokens": TOKEN_CEILING,
            "wall_seconds": WALL_CEILING,
            "cpu_seconds": CPU_CEILING,
            "unused_budget_transfer": False,
        },
        "model": {
            "provider": local_provider.provider_name,
            "model": local_provider.model,
            "reasoning_effort": local_provider.reasoning_effort,
            "provider_version": provider_version,
            "local_settings_digest": local_provider.settings_digest,
            "structural_settings_digest": structural_provider.settings_digest,
        },
        "novelty": jsonable(
            NoveltyConfig(
                policy_version="shinka_novelty_dos_v2_cheap_first_affordable",
                max_novelty_attempts=2,
                affordability_gate=True,
            )
            if repair_mode
            else NoveltyConfig(max_novelty_attempts=2)
        ),
        "parent": jsonable(
            ParentSelectionConfig(
                policy_version="shinka_weighted_dos_v2_probability_cap",
                selection_lambda=10.0,
                base_seed=170817,
                maximum_selection_probability=0.8,
            )
            if repair_mode
            else ParentSelectionConfig(selection_lambda=10.0, base_seed=170817)
        ),
        "repair_scope": (
            "SI1_PARENT_EFFECTIVENESS_AND_NOVELTY_COST_ONLY" if repair_mode else None
        ),
        "fresh_scientific_corpus_consumed": False,
        "forbidden_claims": ["SEARCH_VALUE_ESTABLISHED", "SHINKA_MECHANISM_ADMITTED"],
    }
    manifest = {**manifest_payload, "manifest_digest": digest_json(manifest_payload)}
    ArtifactStore(workspace / "protocol-artifacts").write_record(manifest_record, manifest)
    results: dict[tuple[str, str], dict[str, Any]] = {}
    worker_count = max(1, min(max_workers, len(selected)))
    # One arm wave at a time avoids concurrent worktree mutation against the same
    # task repository; tasks within a wave are independent and CPU-safe.
    for arm_name in ARM_NAMES:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {}
            for item in selected:
                repository, commit = repositories[item.task.task_id]
                arm = _initialize_arm(
                    workspace / "arms" / item.task.task_id / arm_name,
                    item.task,
                    repository,
                    commit,
                    TOKEN_CEILING,
                )
                future = pool.submit(
                    asyncio.run,
                    _run_arm(
                        arm,
                        item,
                        arm_name,
                        local_provider,
                        structural_provider,
                        repair_mode=repair_mode,
                    ),
                )
                futures[future] = item.task.task_id
            for future in as_completed(futures):
                task_id = futures[future]
                result = future.result()
                results[(task_id, arm_name)] = result
                ArtifactStore(workspace / "result-artifacts").write_record(
                    f"tasks/{task_id}/{arm_name}.json",
                    result,
                )
                if progress:
                    progress(
                        f"{'SI-1R' if repair_mode else 'SI-1'} completed {task_id}:{arm_name} "
                        f"improvement={result['metrics']['best_improvement']:.6f} "
                        f"tokens={result['actual_usage']['tokens']}"
                    )
    report = _aggregate(manifest, selected, results)
    if repair_mode:
        report = _repair_verdicts(report)
    ArtifactStore(workspace / "result-artifacts").write_record(report_record, report)
    return report


async def _run_arm(
    arm: AdmissionArm,
    item: SearchValueTask,
    arm_name: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    *,
    repair_mode: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="baseline")
    parent_enabled = "PARENT" in arm_name
    novelty_enabled = "NOVELTY" in arm_name
    parent_config = (
        ParentSelectionConfig(
            policy_version=(
                "shinka_weighted_dos_v2_probability_cap"
                if repair_mode
                else "shinka_weighted_dos_v1"
            ),
            selection_lambda=10.0,
            base_seed=170817 + int(digest_json(item.task.task_id)[:6], 16),
            maximum_selection_probability=0.8 if repair_mode else 1.0,
        )
        if parent_enabled
        else None
    )
    novelty_config = (
        NoveltyConfig(
            policy_version=(
                "shinka_novelty_dos_v2_cheap_first_affordable"
                if repair_mode
                else "shinka_novelty_dos_v1"
            ),
            max_novelty_attempts=2,
            affordability_gate=repair_mode,
        )
        if novelty_enabled
        else None
    )
    config = _controller_config(novelty_enabled, affordable_resampling=repair_mode)
    spec = SearchRunSpec(
        run_id=f"{'si1r' if repair_mode else 'si1'}-{item.task.task_id}-{arm_name.casefold()}",
        contract_digest=arm.contract.digest,
        root_candidate_id=arm.baseline.candidate_id,
        branch_id="si1-active-frontier",
        initial_algorithm_family=item.baseline_basin_id,
        metric_name="score",
        metric_direction=MetricDirection.MAXIMIZE,
        initial_fidelity=Fidelity.G1,
        budget=ResourceBudget(tokens=TOKEN_CEILING, cpu_seconds=CPU_CEILING, wall_seconds=WALL_CEILING),
        rungs=(
            RungDefinition("si1-g1", Fidelity.G1, EVALUATION_RESERVE),
            RungDefinition("si1-g2", Fidelity.G2, ResourceBudget(cpu_seconds=10, wall_seconds=60)),
        ),
        eta=100,
        initial_trials=100,
        local_action_limit=3,
        structural_action_limit=0,
        max_steps=3,
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
    headroom = _headroom_from_item(item, arm)
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
    report["diagnostics"] = _arm_diagnostics(arm, spec, actions, observations, headroom.baseline_score)
    return report


def _controller_config(
    novelty_enabled: bool,
    *,
    affordable_resampling: bool = False,
) -> ActionControllerConfig:
    retry = (
        GENERATION_RESERVE
        if novelty_enabled and not affordable_resampling
        else ResourceBudget()
    )
    complete = _sum_budgets(
        GENERATION_RESERVE,
        retry,
        EVALUATION_RESERVE,
        SETTLEMENT_RESERVE,
    )
    return ActionControllerConfig(
        stagnation_generations=99,
        improvement_epsilon=0.01,
        uncertainty_threshold=0.05,
        incumbent_proximity=0.0,
        minimum_replicates=1,
        structural_similarity_threshold=0.0,
        costs=(
            ActionCost(
                SearchAction.LOCAL_PATCH,
                complete,
                generation_reserve=GENERATION_RESERVE,
                evaluation_reserve=EVALUATION_RESERVE,
                settlement_reserve=SETTLEMENT_RESERVE,
                novelty_resample_reserve=retry,
            ),
            ActionCost(
                SearchAction.STRUCTURAL_ESCAPE,
                complete,
                generation_reserve=GENERATION_RESERVE,
                evaluation_reserve=EVALUATION_RESERVE,
                settlement_reserve=SETTLEMENT_RESERVE,
                novelty_resample_reserve=retry,
            ),
            ActionCost(
                SearchAction.REPLICATE,
                _sum_budgets(EVALUATION_RESERVE, SETTLEMENT_RESERVE),
                evaluation_reserve=EVALUATION_RESERVE,
                settlement_reserve=SETTLEMENT_RESERVE,
            ),
            ActionCost(
                SearchAction.PROMOTE_FIDELITY,
                _sum_budgets(ResourceBudget(cpu_seconds=10, wall_seconds=60), SETTLEMENT_RESERVE),
                evaluation_reserve=ResourceBudget(cpu_seconds=10, wall_seconds=60),
                settlement_reserve=SETTLEMENT_RESERVE,
            ),
        ),
    )


def _arm_diagnostics(
    arm: AdmissionArm,
    spec: SearchRunSpec,
    actions: tuple[SearchActionResult, ...],
    observations,
    baseline_score: float,
) -> dict[str, Any]:
    selected = [action.source_candidate_id for action in actions if action.action is SearchAction.LOCAL_PATCH]
    counts = {candidate_id: selected.count(candidate_id) for candidate_id in set(selected)}
    probabilities = [count / len(selected) for count in counts.values()] if selected else []
    entropy = -sum(value * math.log(value) for value in probabilities if value > 0)
    traces = []
    trace_root = arm.artifacts.records / "search" / spec.run_id / "anytime"
    for path in sorted(trace_root.glob("*.json")):
        traces.append(json.loads(path.read_text(encoding="utf-8")))
    incumbent_count = sum(
        action.source_candidate_id == trace["incumbent_before"]
        for action, trace in zip(actions, traces, strict=False)
        if action.action is SearchAction.LOCAL_PATCH
    )
    novelty = arm.ledger.novelty_receipt_payloads(spec.run_id)
    parent_receipts = arm.ledger.parent_selection_receipt_payloads(spec.run_id)
    novelty_by_id = {item["receipt_id"]: item for item in novelty}
    rejected = [item for item in novelty if item["assessment"]["decision"].startswith("REJECT")]
    accepted = [item for item in novelty if item["assessment"]["decision"] == "ACCEPT"]
    generations = [item for item in arm.ledger.generation_records() if item.candidate_id]
    generation_by_id = {item.generation_id: item for item in arm.ledger.generation_records()}
    resample_generations = []
    for action in actions:
        for index, receipt_id in enumerate(action.novelty_receipt_ids):
            receipt = novelty_by_id[receipt_id]
            if receipt["assessment"]["decision"] != "REJECT_RESAMPLE":
                continue
            next_index = index + 1
            if next_index >= len(action.generation_ids):
                raise RuntimeError("novelty resample receipt is missing its next generation")
            resample_generations.append(generation_by_id[action.generation_ids[next_index]])
    novelty_check_tokens = sum(
        item["usage"]["llm_input_tokens"] + item["usage"]["llm_output_tokens"]
        for item in novelty
    )
    novelty_check_wall = sum(item["usage"]["wall_seconds"] for item in novelty)
    resample_cost_tokens = sum(item.usage.tokens for item in resample_generations)
    resample_cost_wall = sum(item.usage.wall_seconds for item in resample_generations)
    generated_evidence = {
        action.result_candidate_id: action.evidence_receipt_id
        for action in actions
        if action.result_candidate_id is not None
    }
    evidence = {item.receipt_id: item for item in arm.ledger.evidence_records()}
    valid_count = sum(
        receipt_id in evidence and evidence[receipt_id].validity.value == "VALID"
        for receipt_id in generated_evidence.values()
        if receipt_id is not None
    )
    improvements = [
        max(0.0, float(item.score) - baseline_score)
        for item in observations
        if item.valid and item.feasible and item.score is not None
    ]
    first_success = next((value for value in improvements if value > 0), 0.0)
    final_best = max(improvements, default=0.0)
    budget_failures = sum(
        (item.failure_signature or "").startswith("GENERATION_BUDGET_EXCEEDED")
        for item in actions
    )
    return {
        "valid_candidate_rate": valid_count / len(generated_evidence) if generated_evidence else 0.0,
        "parent_selection_receipt_count": len(parent_receipts),
        "parent_selection_receipt_steps": sorted(
            {int(item["step"]) for item in parent_receipts}
        ),
        "novelty_receipt_count": len(novelty),
        "unique_parent_count": len(counts),
        "effective_parent_count": math.exp(entropy) if probabilities else 0.0,
        "parent_entropy": entropy,
        "parent_exposure_gini": _gini(tuple(counts.values())),
        "incumbent_parent_fraction": incumbent_count / len(selected) if selected else 0.0,
        "non_incumbent_parent_fraction": (1.0 - incumbent_count / len(selected)) if selected else 0.0,
        "unique_structural_root_parent_count": None,
        "proposal_novelty_rejection_rate": len(rejected) / len(novelty) if novelty else 0.0,
        "duplicate_avoided_evaluations": len(rejected),
        "novelty_resample_count": sum(
            item["assessment"]["decision"] == "REJECT_RESAMPLE" for item in novelty
        ),
        "novelty_tokens": novelty_check_tokens + resample_cost_tokens,
        "novelty_wall": novelty_check_wall + resample_cost_wall,
        "novelty_llm_calls": len(resample_generations),
        "novelty_check_tokens": novelty_check_tokens,
        "novelty_check_wall": novelty_check_wall,
        "resample_cost_tokens": resample_cost_tokens,
        "resample_cost_wall": resample_cost_wall,
        "accepted_candidate_similarity": (
            statistics.fmean(item["assessment"]["max_similarity"] for item in accepted)
            if accepted
            else None
        ),
        "unique_candidate_rate": (
            len({item.candidate_id for item in generations}) / len(generations) if generations else 0.0
        ),
        "unique_structural_root_rate": None,
        "novelty_false_reject_diagnostics": [
            item["assessment"]["false_reject_diagnostic"] for item in rejected
        ],
        "marginal_improvement_after_first_successful_candidate": max(0.0, final_best - first_success),
        "selected_but_unaffordable_action_count": budget_failures,
        "generation_budget_exceeded_count": budget_failures,
    }


def _aggregate(
    manifest: dict[str, Any],
    tasks: tuple[SearchValueTask, ...],
    results: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    arm_summaries: dict[str, dict[str, Any]] = {}
    for arm_name in ARM_NAMES:
        reports = [results[(item.task.task_id, arm_name)] for item in tasks]
        arm_summaries[arm_name] = {
            "median_final_improvement": statistics.median(item["metrics"]["best_improvement"] for item in reports),
            "median_anytime_auc": statistics.median(item["metrics"]["auc_over_token_budget"] for item in reports),
            "total_tokens": sum(item["actual_usage"]["tokens"] for item in reports),
            "median_tokens_to_best": statistics.median(item["metrics"]["tokens_to_best"] for item in reports),
            "median_wall_to_best": statistics.median(item["metrics"]["wall_to_best"] for item in reports),
            "valid_candidate_rate": statistics.fmean(
                item["metrics"]["valid_candidate_rate"] for item in reports
            ),
            "unique_parent_count": sum(item["diagnostics"]["unique_parent_count"] for item in reports),
            "effective_parent_count": statistics.fmean(item["diagnostics"]["effective_parent_count"] for item in reports),
            "parent_entropy": statistics.fmean(item["diagnostics"]["parent_entropy"] for item in reports),
            "parent_exposure_gini": statistics.fmean(item["diagnostics"]["parent_exposure_gini"] for item in reports),
            "novelty_rejection_rate": statistics.fmean(item["diagnostics"]["proposal_novelty_rejection_rate"] for item in reports),
            "avoided_evaluations": sum(item["diagnostics"]["duplicate_avoided_evaluations"] for item in reports),
            "novelty_tokens": sum(item["diagnostics"]["novelty_tokens"] for item in reports),
            "novelty_wall": sum(item["diagnostics"]["novelty_wall"] for item in reports),
            "novelty_llm_calls": sum(item["diagnostics"]["novelty_llm_calls"] for item in reports),
            "novelty_check_cost_tokens": sum(
                item["diagnostics"]["novelty_check_tokens"] for item in reports
            ),
            "novelty_check_cost_wall": sum(
                item["diagnostics"]["novelty_check_wall"] for item in reports
            ),
            "resample_cost_tokens": sum(
                item["diagnostics"]["resample_cost_tokens"] for item in reports
            ),
            "resample_cost_wall": sum(
                item["diagnostics"]["resample_cost_wall"] for item in reports
            ),
            "unique_candidate_rate": statistics.fmean(item["diagnostics"]["unique_candidate_rate"] for item in reports),
            "structural_root_diversity": None,
            "marginal_improvement_after_first_successful_candidate": statistics.fmean(
                item["diagnostics"]["marginal_improvement_after_first_successful_candidate"]
                for item in reports
            ),
            "selected_but_unaffordable_action_count": sum(
                item["diagnostics"]["selected_but_unaffordable_action_count"] for item in reports
            ),
            "resource_protection": all(all(item["resource_checks"].values()) for item in reports),
        }
    core = arm_summaries["CORE"]
    parent = arm_summaries["CORE_PARENT"]
    novelty = arm_summaries["CORE_NOVELTY"]
    combined = arm_summaries["CORE_PARENT_NOVELTY"]
    indicators = {
        "parent_diversity_increased": max(
            parent["effective_parent_count"], combined["effective_parent_count"]
        ) > core["effective_parent_count"] + 1e-12,
        "duplicate_evaluation_reduced": novelty["avoided_evaluations"] + combined["avoided_evaluations"] > 0,
        "later_marginal_search_value_observed": max(
            parent["marginal_improvement_after_first_successful_candidate"],
            novelty["marginal_improvement_after_first_successful_candidate"],
            combined["marginal_improvement_after_first_successful_candidate"],
        ) > core["marginal_improvement_after_first_successful_candidate"] + 1e-12,
    }
    resource_ok = all(item["resource_protection"] for item in arm_summaries.values())
    preflight_ok = all(item["selected_but_unaffordable_action_count"] == 0 for item in arm_summaries.values())
    parent_receipts_complete = all(
        set(
            range(
                results[(item.task.task_id, arm_name)]["action_counts"][
                    SearchAction.LOCAL_PATCH.value
                ]
            )
        ).issubset(
            set(
                results[(item.task.task_id, arm_name)]["diagnostics"][
                    "parent_selection_receipt_steps"
                ]
            )
        )
        for item in tasks
        for arm_name in ("CORE_PARENT", "CORE_PARENT_NOVELTY")
    )
    novelty_receipts_recorded = all(
        results[(item.task.task_id, arm_name)]["diagnostics"]["novelty_receipt_count"] > 0
        for item in tasks
        for arm_name in ("CORE_NOVELTY", "CORE_PARENT_NOVELTY")
    )
    mechanics_checks = {
        "matched_arm_matrix_complete": len(results) == len(tasks) * len(ARM_NAMES),
        "parent_selection_receipts_complete": parent_receipts_complete,
        "novelty_receipts_recorded": novelty_receipts_recorded,
        "resource_protection": resource_ok,
        "controller_budget_reachability_preserved": preflight_ok,
    }
    mechanics_ready = all(mechanics_checks.values())
    if any(indicators.values()) and resource_ok and preflight_ok:
        signal = "DEVELOPMENT_SIGNAL_POSITIVE"
    elif not any(indicators.values()) and all(
        arm_summaries[name]["median_final_improvement"] < core["median_final_improvement"]
        for name in ARM_NAMES[1:]
    ):
        signal = "DEVELOPMENT_SIGNAL_NEGATIVE"
    else:
        signal = "DEVELOPMENT_SIGNAL_NEUTRAL"
    return {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest["manifest_digest"],
        "claim_ceiling": "DEVELOPMENT_ONLY_CONSUMED_TASKS",
        "task_count": len(tasks),
        "arm_summaries": arm_summaries,
        "mechanism_indicators": indicators,
        "mechanics_checks": mechanics_checks,
        "mechanics_verdict": (
            "SHINKA_PARENT_NOVELTY_MECHANICS_READY"
            if mechanics_ready
            else "SHINKA_PARENT_NOVELTY_MECHANICS_NOT_READY"
        ),
        "resource_protection": resource_ok,
        "controller_budget_reachability_preserved": preflight_ok,
        "development_signal": signal,
        "scientific_verdict": "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
        "fresh_admission_performed": False,
        "task_results": [
            {
                "task_id": item.task.task_id,
                "category": item.task.category,
                "arms": {name: results[(item.task.task_id, name)] for name in ARM_NAMES},
            }
            for item in tasks
        ],
    }


def _repair_verdicts(report: dict[str, Any]) -> dict[str, Any]:
    parent_arms = (
        report["arm_summaries"]["CORE_PARENT"],
        report["arm_summaries"]["CORE_PARENT_NOVELTY"],
    )
    novelty_arms = (
        report["arm_summaries"]["CORE_NOVELTY"],
        report["arm_summaries"]["CORE_PARENT_NOVELTY"],
    )
    non_incumbent = sum(
        task["arms"][arm]["diagnostics"]["non_incumbent_parent_fraction"]
        for task in report["task_results"]
        for arm in ("CORE_PARENT", "CORE_PARENT_NOVELTY")
    )
    parent_repaired = (
        any(item["unique_parent_count"] > 1 and item["effective_parent_count"] > 1 for item in parent_arms)
        and non_incumbent > 0
    )
    avoided = sum(item["avoided_evaluations"] for item in novelty_arms)
    extra_tokens = sum(item["resample_cost_tokens"] for item in novelty_arms)
    extra_wall = sum(item["resample_cost_wall"] for item in novelty_arms)
    novelty_repaired = avoided > 0 and extra_tokens < 41_386 and extra_wall < 67.89
    return {
        **report,
        "repair_gates": {
            "parent_selected_non_incumbent": non_incumbent > 0,
            "parent_effective_count_above_one": any(
                item["effective_parent_count"] > 1 for item in parent_arms
            ),
            "duplicate_evaluations_avoided": avoided,
            "extra_generation_tokens": extra_tokens,
            "extra_generation_wall": extra_wall,
            "tokens_per_avoided_evaluation": extra_tokens / avoided if avoided else None,
            "wall_per_avoided_evaluation": extra_wall / avoided if avoided else None,
            "selected_but_unaffordable_action_count": sum(
                item["selected_but_unaffordable_action_count"]
                for item in report["arm_summaries"].values()
            ),
            "generation_budget_exceeded_count": sum(
                task["arms"][arm]["diagnostics"]["generation_budget_exceeded_count"]
                for task in report["task_results"]
                for arm in ARM_NAMES
            ),
        },
        "parent_repair_verdict": (
            "SI1_PARENT_EFFECTIVENESS_REPAIRED"
            if parent_repaired
            else "SI1_PARENT_EFFECTIVENESS_NOT_DEMONSTRATED"
        ),
        "novelty_repair_verdict": (
            "SI1_NOVELTY_COST_REPAIRED"
            if novelty_repaired
            else "SI1_NOVELTY_COST_NOT_REPAIRED"
        ),
        "scientific_verdict": "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
        "fresh_admission_performed": False,
    }


def _sum_budgets(*budgets: ResourceBudget) -> ResourceBudget:
    return ResourceBudget(
        tokens=sum(item.tokens for item in budgets),
        cpu_seconds=sum(item.cpu_seconds for item in budgets),
        gpu_seconds=sum(item.gpu_seconds for item in budgets),
        device_seconds=sum(item.device_seconds for item in budgets),
        wall_seconds=sum(item.wall_seconds for item in budgets),
    )


def _gini(values: tuple[int, ...]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    ordered = sorted(values)
    count = len(ordered)
    return (
        (2.0 * sum((index + 1) * value for index, value in enumerate(ordered)))
        / (count * sum(ordered))
        - (count + 1.0) / count
    )
