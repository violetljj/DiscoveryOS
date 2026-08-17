from __future__ import annotations

import asyncio
import difflib
import json
import math
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.cmi_fresh_causal_validation import (
    MANIFEST_RECORD as R7_MANIFEST_RECORD,
    REPORT_RECORD as R7_REPORT_RECORD,
)
from discoveryos.benchmarks.cmi_probe_calibration import (
    _behavior_probe_source,
    _mean_absolute_distance,
    _run_python,
)
from discoveryos.benchmarks.cmi_r7_fresh_tasks import cmi_r7_fresh_tasks
from discoveryos.benchmarks.cmi_search_value_r1_tasks import (
    PROTOCOL_SALT,
    cmi_search_value_r1_tasks,
    probe_seeds,
)
from discoveryos.benchmarks.executable_mechanism_contract import _repository_snapshot
from discoveryos.benchmarks.local_patch_admission import AdmissionArm, _initialize_arm
from discoveryos.benchmarks.search_policy_admission import SearchObservation, compute_policy_metrics
from discoveryos.benchmarks.search_value_mvp0 import (
    _build_spec,
    _evaluate_at,
    _evidence_value,
    _extra_metrics,
    _materialize_files,
    _sum_usage,
    canonical_evidence_summary,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask, normalized_source
from discoveryos.benchmarks.si2 import (
    _materialize_task_cohort,
    _one_sided_sign_p,
    _si2_headroom_evidence,
)
from discoveryos.benchmarks.si2_tasks import si2_confirmation_tasks, si2_discovery_tasks
from discoveryos.contracts.executable import ExecutableCandidateBundle
from discoveryos.contracts.models import CandidateSpec, EvidenceRecord, Fidelity, ResourceBudget, ResourceUsage
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator
from discoveryos.operators.local_patch import LocalPatchOperator, PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CMI_SEARCH_VALUE_R1_V1"
MANIFEST_RECORD = "cmi-search-value-r1-manifest.json"
REPORT_RECORD = "cmi-search-value-r1-report.json"
ARM_NAMES = ("CMI_DISABLED", "CMI_ENABLED")
TASK_COUNT = 6
COMMON_PREFIX_STEPS = 2
DOWNSTREAM_STEPS = 1
TOKEN_CEILING = 80_000
WALL_CEILING = 1_800.0
FUNCTIONAL_DISTANCE_MAXIMUM = 0.10
SIGN_TEST_ALPHA = 0.10


def seal_cmi_search_value_r1(
    workspace: Path,
    *,
    cmi_r7_workspace: Path,
    cmi_r7_report_sha256: str,
    provider: PatchProvider,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI Search Value R1 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI Search Value R1 must be sealed from a clean worktree")
    provider_version = str(getattr(provider, "provider_version", "unknown"))
    if not provider_version or provider_version == "unknown":
        raise RuntimeError("CMI Search Value R1 requires a reportable provider version")
    if not getattr(provider, "reasoning_effort", None):
        raise RuntimeError("CMI Search Value R1 requires explicit reasoning effort")

    authority = _load_r7_authority(cmi_r7_workspace.resolve(), cmi_r7_report_sha256)
    tasks = cmi_search_value_r1_tasks()
    _validate_fresh_population(tasks, authority["manifest"])
    workspace.mkdir(parents=True, exist_ok=True)
    task_records = _materialize_task_cohort(
        workspace / "protocol" / "fresh-tasks",
        tasks,
        cohort_role="CMI_SEARCH_VALUE_R1_FRESH_SEARCH",
    )
    source_root = Path(__file__).resolve().parents[1]
    implementation_paths = _implementation_paths()
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "CMI_SEARCH_VALUE_R1_SEALED_PRE_MODEL",
        "scientific_question": "Does the same bounded search produce greater final value when the only available extra action is the frozen admitted CMI operator?",
        "claim_ceiling": "CMI_SEARCH_VALUE_ON_FRESH_INSTANCES_WITHIN_FROZEN_ASSIGNMENT_COVERAGE_FAMILIES_AND_EVALUATOR_REGIME_ONLY",
        "model_calls_before_seal": 0,
        "repository": repository,
        "experiment_code_sha": repository["head_commit"],
        "implementation_digests": {
            str(path.relative_to(source_root)).replace("\\", "/"): digest_bytes(path.read_bytes())
            for path in implementation_paths
        },
        "cmi_r7_authority": authority["binding"],
        "frozen_brief": authority["manifest"]["frozen_brief"],
        "freshness": {
            "instance_fresh": True,
            "distribution_fresh": False,
            "task_family_fresh": False,
            "evaluator_regime_fresh": False,
            "selection_rule": "all six instances derived from protocol salt without screening or replacement",
            "protocol_salt": PROTOCOL_SALT,
        },
        "tasks": task_records,
        "arms": {
            "CMI_DISABLED": "two-step common Local Patch prefix, default Local Patch intervention, one downstream Local Patch",
            "CMI_ENABLED": "same prefix; frozen CMI replaces only the intervention action when eligible; same downstream Local Patch",
        },
        "paired_execution": {
            "common_random_prefix": True,
            "common_prefix_steps": COMMON_PREFIX_STEPS,
            "ineligible_fallback_shared_exactly": True,
            "downstream_steps": DOWNSTREAM_STEPS,
            "physical shared calls are credited independently and identically to both scientific arms": True,
        },
        "model": {
            "provider": provider.provider_name,
            "model": provider.model,
            "reasoning_effort": provider.reasoning_effort,
            "provider_version": provider_version,
            "settings_digest": provider.settings_digest,
        },
        "matched_resources_per_task_arm": {
            "tokens": TOKEN_CEILING,
            "wall_seconds": WALL_CEILING,
            "unused_budget_transfer": False,
            "primary_budget_axis": "input_plus_output_tokens",
            "max_parallel_tasks": 1,
        },
        "opportunity_and_eligibility": {
            "opportunity": "two technically valid common-prefix Local Patch descendants and sufficient remaining action budget",
            "eligibility": {
                "two_distinct_source_digests": True,
                "pairwise_functional_distance_maximum": FUNCTIONAL_DISTANCE_MAXIMUM,
                "pairwise_score_spread_at_most_task_resolution": True,
                "supported_categories": ["budgeted_weighted_coverage", "capacitated_cost_assignment"],
            },
            "no_task_replacement_if_ineligible": True,
        },
        "primary_metrics": ["paired_final_utility", "paired_anytime_auc", "win_tie_loss"],
        "search_value_gate": {
            "minimum_evaluable_tasks": TASK_COUNT,
            "wins_strictly_greater_than_losses": True,
            "losses_maximum": 0,
            "median_final_delta_strictly_positive": True,
            "median_anytime_auc_delta_strictly_positive": True,
            "one_sided_exact_sign_test_alpha": SIGN_TEST_ALPHA,
        },
        "causal_transmission_gate": {
            "minimum_eligible_and_invoked_tasks": 4,
            "minimum_invoked_tasks_per_family": 1,
            "accepted_descendants_equal_invocations": True,
            "minimum_downstream_retained_contributions": 2,
            "minimum_downstream_retained_contributions_per_family": 1,
        },
        "cost_gate": {
            "enabled_model_tokens_not_above_disabled": True,
            "enabled_evaluator_calls_equal_disabled": True,
            "enabled_total_wall_ratio_maximum": 2.0,
        },
        "verdict_rules": {
            "positive": "search advantage AND causal transmission AND cost gates all pass",
            "unattributed": "search advantage without causal transmission cannot count as CMI search value",
            "scientific_negative": "valid matched comparison fails the positive gate",
            "invalid_or_not_evaluable_remain_separate": True,
        },
        "fresh_tasks_consumed_if_run": TASK_COUNT,
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "model_calls_before_seal": 0,
    }


def run_cmi_search_value_r1(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_and_verify_manifest(workspace, manifest_digest, provider)
    report_path = workspace / "result-artifacts" / "records" / REPORT_RECORD
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    task_map = {item.task.task_id: item for item in cmi_search_value_r1_tasks()}
    results: list[dict[str, Any]] = []
    for index, record in enumerate(manifest["tasks"], start=1):
        task_id = record["task_id"]
        result_record = f"tasks/{task_id}.json"
        result_path = workspace / "result-artifacts" / "records" / result_record
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            task_root = workspace / "search" / task_id
            if task_root.exists() and any(task_root.iterdir()):
                raise RuntimeError(f"partial CMI Search Value R1 task exists without terminal receipt: {task_id}")
            if progress:
                progress(f"CMI Search Value R1 {index}/{len(manifest['tasks'])} starting {task_id}")
            result = asyncio.run(
                _run_task(
                    task_root,
                    task_map[task_id],
                    Path(record["repository"]),
                    record["repository_commit"],
                    manifest,
                    provider,
                )
            )
            ArtifactStore(workspace / "result-artifacts").write_record(result_record, result)
        results.append(result)
        if progress:
            progress(
                f"CMI Search Value R1 completed {task_id} eligible={result['causal_trace']['eligible']} "
                f"invoked={result['causal_trace']['invoked']} delta={result['paired']['final_delta']:.8f}"
            )
    report = _aggregate(manifest, results)
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


async def _run_task(
    task_root: Path,
    item: SearchValueTask,
    repository: Path,
    repository_commit: str,
    manifest: dict[str, Any],
    provider: PatchProvider,
) -> dict[str, Any]:
    started = time.monotonic()
    shared = _initialize_arm(task_root / "shared-prefix", item.task, repository, repository_commit, TOKEN_CEILING)
    baseline = await _evaluate_at(shared, shared.baseline, Fidelity.G1, seed=0, attempt="cmi-svr1-baseline")
    evidence_history: list[EvidenceRecord] = [baseline]
    incumbent = shared.baseline
    incumbent_source = _candidate_source(shared, incumbent, item.task.entrypoint)
    _, _, incumbent_score_value = _evidence_value(shared, baseline)
    incumbent_score = float(incumbent_score_value or 0.0)
    shared_usage = ResourceUsage()
    prefix_steps: list[dict[str, Any]] = []
    shared_operator = _local_operator(shared, provider, "cmi_svr1_shared_prefix")
    for step in range(COMMON_PREFIX_STEPS):
        generated = await _local_step(
            shared,
            item,
            shared_operator,
            incumbent,
            evidence_history,
            _remaining_budget(shared_usage),
            attempt=f"cmi-svr1-prefix-{step}",
        )
        shared_usage = _add_usage(shared_usage, generated["usage"])
        prefix_steps.append(generated)
        if generated["evidence"] is not None:
            evidence_history.append(generated["evidence"])
        if generated["valid"] and generated["score"] is not None and generated["score"] > incumbent_score:
            incumbent = generated["candidate"]
            incumbent_source = generated["source"]
            incumbent_score = float(generated["score"])

    opportunity = len(prefix_steps) == COMMON_PREFIX_STEPS and all(step["valid"] for step in prefix_steps)
    eligibility = _eligibility(item, prefix_steps, opportunity)
    if not eligibility["eligible"]:
        shared_tail: list[dict[str, Any]] = []
        for step in range(2):
            generated = await _local_step(
                shared,
                item,
                shared_operator,
                incumbent,
                evidence_history,
                _remaining_budget(shared_usage),
                attempt=f"cmi-svr1-shared-fallback-{step}",
            )
            shared_usage = _add_usage(shared_usage, generated["usage"])
            shared_tail.append(generated)
            if generated["evidence"] is not None:
                evidence_history.append(generated["evidence"])
            if generated["valid"] and generated["score"] is not None and generated["score"] > incumbent_score:
                incumbent = generated["candidate"]
                incumbent_source = generated["source"]
                incumbent_score = float(generated["score"])
        observations = _observations(prefix_steps + shared_tail)
        arm = _arm_summary(item, repository, observations, shared_usage, time.monotonic() - started, 1 + len(prefix_steps) + len(shared_tail))
        arms = {name: {**arm, "arm": name} for name in ARM_NAMES}
        causal = {
            "opportunity": opportunity,
            **eligibility,
            "invoked": False,
            "accepted_descendant": False,
            "retained_after_intervention": False,
            "downstream_parent_was_cmi": False,
            "downstream_retained_contribution": False,
            "operator_trace": None,
        }
    else:
        control = await _run_branch(
            task_root / "control",
            item,
            repository,
            repository_commit,
            provider,
            incumbent_source,
            incumbent_score,
            shared_usage,
            prefix_steps,
            cmi_enabled=False,
            frozen_brief=manifest["frozen_brief"],
        )
        treatment = await _run_branch(
            task_root / "treatment",
            item,
            repository,
            repository_commit,
            provider,
            incumbent_source,
            incumbent_score,
            shared_usage,
            prefix_steps,
            cmi_enabled=True,
            frozen_brief=manifest["frozen_brief"],
        )
        arms = {"CMI_DISABLED": control["arm"], "CMI_ENABLED": treatment["arm"]}
        causal = {
            "opportunity": opportunity,
            **eligibility,
            "invoked": True,
            "accepted_descendant": treatment["intervention_valid"],
            "retained_after_intervention": treatment["intervention_retained"],
            "downstream_parent_was_cmi": treatment["downstream_parent_was_intervention"],
            "downstream_retained_contribution": False,
            "operator_trace": treatment["operator_trace"],
        }

    resolution = item.score_resolution
    final_delta = arms["CMI_ENABLED"]["metrics"]["best_improvement"] - arms["CMI_DISABLED"]["metrics"]["best_improvement"]
    auc_delta = arms["CMI_ENABLED"]["metrics"]["auc_over_token_budget"] - arms["CMI_DISABLED"]["metrics"]["auc_over_token_budget"]
    if causal["invoked"]:
        causal["downstream_retained_contribution"] = bool(
            causal["retained_after_intervention"]
            and causal["downstream_parent_was_cmi"]
            and final_delta >= resolution - 1e-12
        )
    outcome = "WIN" if final_delta >= resolution - 1e-12 else "LOSS" if final_delta <= -resolution + 1e-12 else "TIE"
    return {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest["manifest_digest"],
        "task_id": item.task.task_id,
        "task_category": item.task.category,
        "score_resolution": resolution,
        "arms": arms,
        "paired": {"outcome": outcome, "final_delta": final_delta, "anytime_auc_delta": auc_delta},
        "causal_trace": causal,
        "physical_execution": {
            "common_prefix_model_calls": COMMON_PREFIX_STEPS,
            "shared_fallback": not eligibility["eligible"],
            "elapsed_seconds": time.monotonic() - started,
        },
    }


async def _run_branch(
    root: Path,
    item: SearchValueTask,
    repository: Path,
    repository_commit: str,
    provider: PatchProvider,
    prefix_incumbent_source: str,
    prefix_incumbent_score: float,
    shared_usage: ResourceUsage,
    prefix_steps: list[dict[str, Any]],
    *,
    cmi_enabled: bool,
    frozen_brief: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    arm = _initialize_arm(root, item.task, repository, repository_commit, TOKEN_CEILING)
    baseline = await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="cmi-svr1-branch-baseline")
    incumbent = _source_candidate(arm, arm.baseline, item.task.entrypoint, prefix_incumbent_source, "paired_prefix_replay")
    incumbent_evidence = await _evaluate_at(arm, incumbent, Fidelity.G2, seed=0, attempt="cmi-svr1-prefix-incumbent")
    evidence_history = [baseline, incumbent_evidence]
    incumbent_score = prefix_incumbent_score
    branch_usage = ResourceUsage()
    intervention_trace = None
    intervention_valid = False
    intervention_retained = False
    if cmi_enabled:
        generated = FunctionalBasinEscapeOperator(frozen_brief).propose(
            task_category=item.task.category,
            base_source=prefix_incumbent_source,
        )
        intervention_trace = generated.trace
        intervention = _source_candidate(
            arm,
            incumbent,
            item.task.entrypoint,
            generated.source,
            "cmi_functional_basin_escape_v1",
        )
        intervention_evidence = await _evaluate_at(
            arm, intervention, Fidelity.G2, seed=0, attempt="cmi-svr1-intervention-cmi"
        )
        valid, feasible, score = _evidence_value(arm, intervention_evidence)
        intervention_usage = intervention_evidence.resource_usage
        intervention_source = generated.source
        intervention_valid = valid and feasible and score is not None
        branch_usage = _add_usage(branch_usage, intervention_usage)
    else:
        operator = _local_operator(arm, provider, "cmi_svr1_control_intervention")
        local = await _local_step(
            arm,
            item,
            operator,
            incumbent,
            evidence_history,
            _remaining_budget(_add_usage(shared_usage, branch_usage)),
            attempt="cmi-svr1-intervention-control",
        )
        intervention = local["candidate"]
        intervention_evidence = local["evidence"]
        valid, feasible, score = local["valid"], local["feasible"], local["score"]
        intervention_usage = local["usage"]
        intervention_source = local["source"]
        intervention_valid = valid and feasible and score is not None
        branch_usage = _add_usage(branch_usage, intervention_usage)
    if intervention_evidence is not None:
        evidence_history.append(intervention_evidence)
    if intervention_valid and float(score) > incumbent_score + item.score_resolution:
        incumbent = intervention
        incumbent_score = float(score)
        intervention_retained = True
    downstream_parent_was_intervention = intervention_retained
    operator = _local_operator(arm, provider, "cmi_svr1_downstream_local")
    downstream = await _local_step(
        arm,
        item,
        operator,
        incumbent,
        evidence_history,
        _remaining_budget(_add_usage(shared_usage, branch_usage)),
        attempt="cmi-svr1-downstream",
    )
    branch_usage = _add_usage(branch_usage, downstream["usage"])
    steps = prefix_steps + [
        {
            "candidate": intervention,
            "candidate_id": intervention.candidate_id if intervention is not None else "intervention-failed",
            "source": intervention_source,
            "valid": intervention_valid,
            "feasible": bool(feasible),
            "score": float(score) if score is not None else None,
            "usage": intervention_usage,
            "evidence": intervention_evidence,
        },
        downstream,
    ]
    total_usage = _add_usage(shared_usage, branch_usage)
    observations = _observations(steps)
    summary = _arm_summary(
        item,
        repository,
        observations,
        total_usage,
        time.monotonic() - started,
        1 + len(steps),
    )
    return {
        "arm": summary,
        "intervention_valid": intervention_valid,
        "intervention_retained": intervention_retained,
        "downstream_parent_was_intervention": downstream_parent_was_intervention,
        "operator_trace": intervention_trace,
    }


async def _local_step(
    arm: AdmissionArm,
    item: SearchValueTask,
    operator: LocalPatchOperator,
    parent: CandidateSpec,
    evidence_history: list[EvidenceRecord],
    remaining: ResourceBudget,
    *,
    attempt: str,
) -> dict[str, Any]:
    bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, parent.artifact_digest)
    result = operator.propose(
        parent=parent,
        mutable_files=_materialize_files(bundle, arm.contract.mutable_paths),
        development_evidence_summary=canonical_evidence_summary(tuple(evidence_history)),
        failure_signature=evidence_history[-1].failure_signature,
        semantic_delta_memory=tuple(candidate.semantic_delta for candidate in (arm.baseline, parent)),
        remaining_budget=remaining,
        build=_build_spec(bundle),
    )
    evidence = None
    if result.candidate is not None:
        evidence = await _evaluate_at(arm, result.candidate, Fidelity.G2, seed=0, attempt=attempt)
    valid, feasible, score = _evidence_value(arm, evidence)
    usage = _sum_usage(
        item for item in (result.record.usage, evidence.resource_usage if evidence is not None else None) if item is not None
    )
    source = _candidate_source(arm, result.candidate, item.task.entrypoint) if result.candidate is not None else ""
    return {
        "candidate": result.candidate,
        "candidate_id": result.candidate.candidate_id if result.candidate is not None else result.record.generation_id,
        "source": source,
        "valid": valid,
        "feasible": feasible,
        "score": score,
        "usage": usage,
        "evidence": evidence,
        "failure_signature": result.record.failure_signature,
    }


def _eligibility(item: SearchValueTask, prefix_steps: list[dict[str, Any]], opportunity: bool) -> dict[str, Any]:
    supported = item.task.category in {"capacitated_cost_assignment", "budgeted_weighted_coverage"}
    sources = [step["source"] for step in prefix_steps]
    distinct = len(sources) == 2 and all(sources) and digest_bytes(sources[0].encode()) != digest_bytes(sources[1].encode())
    signatures = [_functional_signature(item.task.category, source, probe_seeds(item.task.task_id)) for source in sources]
    functional_distance = _mean_absolute_distance(*signatures) if len(signatures) == 2 else math.inf
    scores = [float(step["score"]) for step in prefix_steps if step["score"] is not None]
    score_spread = max(scores) - min(scores) if len(scores) == 2 else math.inf
    checks = {
        "natural_opportunity": opportunity,
        "supported_category": supported,
        "distinct_sources": distinct,
        "functional_distance_within_basin": functional_distance <= FUNCTIONAL_DISTANCE_MAXIMUM,
        "utility_plateau_within_resolution": score_spread <= item.score_resolution + 1e-12,
    }
    return {
        "eligible": all(checks.values()),
        "eligibility_checks": checks,
        "functional_distance": functional_distance,
        "score_spread": score_spread,
        "probe_seeds": list(probe_seeds(item.task.task_id)),
    }


def _functional_signature(category: str, source: str, seeds: tuple[int, ...]) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="discoveryos-cmi-svr1-probe-") as temporary:
        root = Path(temporary)
        (root / "algorithm.py").write_text(normalized_source(source), encoding="utf-8")
        (root / "behavior_probe.py").write_text(_behavior_probe_source(category, seeds), encoding="utf-8")
        result = _run_python(root, "behavior_probe.py")
    if result.returncode != 0:
        return []
    try:
        return [float(value) for value in json.loads(result.stdout)["signature"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return []


def _local_operator(arm: AdmissionArm, provider: PatchProvider, strategy_id: str) -> LocalPatchOperator:
    return LocalPatchOperator(
        provider=provider,
        artifacts=arm.artifacts,
        ledger=arm.ledger,
        contract=arm.contract,
        strategy_id=strategy_id,
    )


def _candidate_source(arm: AdmissionArm, candidate: CandidateSpec | None, entrypoint: str) -> str:
    if candidate is None:
        return ""
    bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, candidate.artifact_digest)
    return normalized_source(_materialize_files(bundle, (entrypoint,))[entrypoint])


def _source_candidate(
    arm: AdmissionArm,
    parent: CandidateSpec,
    entrypoint: str,
    source: str,
    operator_id: str,
) -> CandidateSpec:
    parent_bundle = ExecutableCandidateBundle.from_artifact(arm.artifacts, parent.artifact_digest)
    base_repository = Path(parent_bundle.base_repository)
    original = (base_repository / entrypoint).read_text(encoding="utf-8")
    patch = _full_file_patch(entrypoint, original, normalized_source(source))
    bundle = ExecutableCandidateBundle(
        base_repository=str(base_repository),
        base_commit=parent_bundle.base_commit,
        patch_diff=patch,
        mutable_paths=parent_bundle.mutable_paths,
        forbidden_paths=parent_bundle.forbidden_paths,
        touched_paths=(entrypoint,),
        entrypoint=entrypoint,
        environment_lock=parent_bundle.environment_lock,
        build_command=parent_bundle.build_command,
        test_command=parent_bundle.test_command,
        evaluation_command=parent_bundle.evaluation_command,
        patch_stack=(patch,),
        patch_apply_policy="recount_hunks",
        format_version="executable-candidate-v3",
    )
    candidate = CandidateSpec.create(
        artifact_digest=bundle.store(arm.artifacts),
        parent_ids=(parent.candidate_id,),
        operator_id=operator_id,
        strategy_id="cmi_search_value_r1",
        parameters={"task_id": arm.contract.contract_id, "source_sha256": digest_bytes(source.encode())},
        semantic_delta=f"CMI Search Value R1 source materialization by {operator_id}",
        environment_digest=parent.environment_digest,
    )
    arm.ledger.add_candidate(candidate)
    return candidate


def _full_file_patch(path: str, before: str, after: str) -> str:
    body = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if not body:
        raise RuntimeError("source candidate must differ from the base repository")
    return f"diff --git a/{path} b/{path}\n{body}"


def _observations(steps: list[dict[str, Any]]) -> tuple[SearchObservation, ...]:
    observations: list[SearchObservation] = []
    cumulative = ResourceUsage()
    for step in steps:
        cumulative = _add_usage(cumulative, step["usage"])
        observations.append(
            SearchObservation(
                candidate_id=step["candidate_id"],
                parent_id=observations[-1].candidate_id if observations else None,
                cumulative_tokens=cumulative.tokens,
                cumulative_wall_seconds=cumulative.wall_seconds,
                score=step["score"],
                valid=bool(step["valid"]),
                feasible=bool(step["feasible"]),
                basin_id="cmi_search_value_r1" if step["valid"] and step["feasible"] else None,
            )
        )
    return tuple(observations)


def _arm_summary(
    item: SearchValueTask,
    repository: Path,
    observations: tuple[SearchObservation, ...],
    usage: ResourceUsage,
    elapsed: float,
    evaluator_calls: int,
) -> dict[str, Any]:
    headroom = _si2_headroom_evidence(item, repository)[0]
    metrics = compute_policy_metrics(headroom, observations, token_budget=TOKEN_CEILING, wall_budget=WALL_CEILING)
    metrics.update(_extra_metrics(observations, TOKEN_CEILING, headroom))
    return {
        "metrics": metrics,
        "observations": [jsonable(item) for item in observations],
        "actual_usage": {**usage.as_budget_dict(), "llm_input_tokens": usage.llm_input_tokens, "llm_output_tokens": usage.llm_output_tokens, "llm_cache_tokens": usage.llm_cache_tokens},
        "evaluator_calls": evaluator_calls,
        "elapsed_seconds": elapsed,
        "resource_checks": {
            "token_ceiling_respected": usage.tokens <= TOKEN_CEILING,
            "wall_ceiling_respected": usage.wall_seconds <= WALL_CEILING,
        },
    }


def _aggregate(manifest: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluable = [
        item for item in results
        if all(all(item["arms"][arm]["resource_checks"].values()) for arm in ARM_NAMES)
    ]
    wins = sum(item["paired"]["outcome"] == "WIN" for item in evaluable)
    ties = sum(item["paired"]["outcome"] == "TIE" for item in evaluable)
    losses = sum(item["paired"]["outcome"] == "LOSS" for item in evaluable)
    final_deltas = [item["paired"]["final_delta"] for item in evaluable]
    auc_deltas = [item["paired"]["anytime_auc_delta"] for item in evaluable]
    search_checks = {
        "minimum_evaluable_tasks": len(evaluable) >= TASK_COUNT,
        "wins_greater_than_losses": wins > losses,
        "losses_maximum": losses == 0,
        "median_final_delta_positive": bool(final_deltas) and statistics.median(final_deltas) > 0,
        "median_anytime_auc_delta_positive": bool(auc_deltas) and statistics.median(auc_deltas) > 0,
        "exact_sign_test_pass": _one_sided_sign_p(wins, losses) <= SIGN_TEST_ALPHA,
    }
    invoked = [item for item in results if item["causal_trace"]["invoked"]]
    contributions = [item for item in invoked if item["causal_trace"]["downstream_retained_contribution"]]
    categories = {item.task.category for item in cmi_search_value_r1_tasks()}
    transmission_checks = {
        "minimum_eligible_and_invoked_tasks": len(invoked) >= 4,
        "invocation_equals_eligibility": all(item["causal_trace"]["invoked"] == item["causal_trace"]["eligible"] for item in results),
        "minimum_invoked_tasks_per_family": all(sum(item["task_category"] == category for item in invoked) >= 1 for category in categories),
        "accepted_descendants_equal_invocations": all(item["causal_trace"]["accepted_descendant"] for item in invoked),
        "minimum_downstream_retained_contributions": len(contributions) >= 2,
        "minimum_downstream_retained_contributions_per_family": all(sum(item["task_category"] == category for item in contributions) >= 1 for category in categories),
    }
    usage = {
        arm: {
            "tokens": sum(item["arms"][arm]["actual_usage"]["tokens"] for item in results),
            "evaluator_calls": sum(item["arms"][arm]["evaluator_calls"] for item in results),
            "elapsed_seconds": sum(item["arms"][arm]["elapsed_seconds"] for item in results),
        }
        for arm in ARM_NAMES
    }
    disabled, enabled = usage["CMI_DISABLED"], usage["CMI_ENABLED"]
    cost_checks = {
        "enabled_model_tokens_not_above_disabled": enabled["tokens"] <= disabled["tokens"],
        "enabled_evaluator_calls_equal_disabled": enabled["evaluator_calls"] == disabled["evaluator_calls"],
        "enabled_total_wall_ratio_maximum": enabled["elapsed_seconds"] / disabled["elapsed_seconds"] <= 2.0 if disabled["elapsed_seconds"] > 0 else False,
    }
    search_pass = all(search_checks.values())
    transmission_pass = all(transmission_checks.values())
    cost_pass = all(cost_checks.values())
    if search_pass and transmission_pass and cost_pass:
        verdict = "CMI_SEARCH_VALUE_ESTABLISHED_ON_FROZEN_ASSIGNMENT_COVERAGE_REGIME"
    elif search_pass and not transmission_pass:
        verdict = "SEARCH_ADVANTAGE_OBSERVED_BUT_NOT_ATTRIBUTABLE_TO_CMI"
    else:
        verdict = "CMI_SEARCH_VALUE_NOT_ESTABLISHED"
    return {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest["manifest_digest"],
        "experiment_code_sha": manifest["experiment_code_sha"],
        "task_count": len(results),
        "paired": {
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "median_final_delta": statistics.median(final_deltas) if final_deltas else 0.0,
            "median_anytime_auc_delta": statistics.median(auc_deltas) if auc_deltas else 0.0,
            "one_sided_exact_sign_p": _one_sided_sign_p(wins, losses),
        },
        "causal_transmission": {
            "opportunities": sum(item["causal_trace"]["opportunity"] for item in results),
            "eligible": sum(item["causal_trace"]["eligible"] for item in results),
            "invocations": len(invoked),
            "accepted_descendants": sum(item["causal_trace"]["accepted_descendant"] for item in results),
            "retained_after_intervention": sum(item["causal_trace"]["retained_after_intervention"] for item in results),
            "downstream_retained_contributions": len(contributions),
        },
        "usage": usage,
        "gates": {
            "search_advantage": {"passed": search_pass, "checks": search_checks},
            "causal_transmission": {"passed": transmission_pass, "checks": transmission_checks},
            "cost": {"passed": cost_pass, "checks": cost_checks},
        },
        "verdict": verdict,
        "claim_ceiling": manifest["claim_ceiling"],
        "fresh_tasks_consumed": len(results),
        "results": results,
    }


def _load_r7_authority(workspace: Path, expected_report_sha256: str) -> dict[str, Any]:
    report_path = workspace / "result-artifacts" / "records" / R7_REPORT_RECORD
    manifest_path = workspace / "protocol-artifacts" / "records" / R7_MANIFEST_RECORD
    if not report_path.is_file() or digest_bytes(report_path.read_bytes()) != expected_report_sha256:
        raise RuntimeError("CMI-R7 report hash mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        report.get("verdict") != "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED"
        or not report.get("success_gate", {}).get("passed")
        or not report.get("cmi_enabled_search_comparison_preregistration_authorized")
        or report.get("manifest_digest") != manifest.get("manifest_digest")
    ):
        raise RuntimeError("CMI-R7 did not authorize CMI Search Value R1 preregistration")
    return {
        "manifest": manifest,
        "report": report,
        "binding": {
            "workspace": str(workspace),
            "manifest_path": str(manifest_path),
            "manifest_digest": manifest["manifest_digest"],
            "report_path": str(report_path),
            "report_sha256": expected_report_sha256,
            "verdict": report["verdict"],
        },
    }


def _validate_fresh_population(tasks: tuple[SearchValueTask, ...], r7_manifest: dict[str, Any]) -> None:
    if len(tasks) != TASK_COUNT or len({item.task.task_id for item in tasks}) != TASK_COUNT:
        raise RuntimeError("CMI Search Value R1 requires exactly six unique tasks")
    prior = (*si2_discovery_tasks(), *si2_confirmation_tasks(), *cmi_r7_fresh_tasks())
    prior_ids = {item.task.task_id for item in prior}
    prior_payloads = {item.payload_digest for item in prior}
    if any(item.task.task_id in prior_ids or item.payload_digest in prior_payloads for item in tasks):
        raise RuntimeError("CMI Search Value R1 overlaps a consumed task identity or payload")
    r7_ids = {state["task_id"] for state in r7_manifest.get("states", [])}
    if any(item.task.task_id in r7_ids for item in tasks):
        raise RuntimeError("CMI Search Value R1 overlaps the consumed R7 sealed shard")


def _load_and_verify_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    if not path.is_file():
        raise RuntimeError("CMI Search Value R1 manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("CMI Search Value R1 manifest digest mismatch")
    if manifest.get("status") != "CMI_SEARCH_VALUE_R1_SEALED_PRE_MODEL" or manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("CMI Search Value R1 was not sealed before model execution")
    repository = _repository_snapshot()
    if repository["head_commit"] != manifest["experiment_code_sha"]:
        raise RuntimeError("CMI Search Value R1 repository drift")
    source_root = Path(__file__).resolve().parents[1]
    for relative, expected in manifest["implementation_digests"].items():
        candidate = source_root / relative
        if not candidate.is_file() or digest_bytes(candidate.read_bytes()) != expected:
            raise RuntimeError(f"CMI Search Value R1 implementation drift: {relative}")
    model = manifest["model"]
    if (
        provider.provider_name != model["provider"]
        or provider.model != model["model"]
        or provider.reasoning_effort != model["reasoning_effort"]
        or provider.provider_version != model["provider_version"]
        or provider.settings_digest != model["settings_digest"]
    ):
        raise RuntimeError("CMI Search Value R1 provider/model/settings drift")
    task_map = {item.task.task_id: item for item in cmi_search_value_r1_tasks()}
    for record in manifest["tasks"]:
        item = task_map.get(record["task_id"])
        repository_path = Path(record["repository"])
        if item is None or item.payload_digest != record["task_payload_digest"]:
            raise RuntimeError(f"CMI Search Value R1 task definition drift: {record['task_id']}")
        if _git(repository_path, "status", "--porcelain").strip() or _git(repository_path, "rev-parse", "HEAD").strip() != record["repository_commit"]:
            raise RuntimeError(f"CMI Search Value R1 task repository drift: {record['task_id']}")
        for relative, expected in record["files"].items():
            if digest_bytes((repository_path / relative).read_bytes()) != expected:
                raise RuntimeError(f"CMI Search Value R1 task file drift: {record['task_id']}:{relative}")
    _load_r7_authority(Path(manifest["cmi_r7_authority"]["workspace"]), manifest["cmi_r7_authority"]["report_sha256"])
    return manifest


def _implementation_paths() -> tuple[Path, ...]:
    source_root = Path(__file__).resolve().parents[1]
    return (
        Path(__file__).resolve(),
        Path(__file__).with_name("cmi_search_value_r1_tasks.py").resolve(),
        source_root / "operators" / "functional_basin_escape.py",
        source_root / "operators" / "local_patch.py",
        source_root / "benchmarks" / "cmi_probe_calibration.py",
        source_root / "benchmarks" / "si2_tasks.py",
    )


def _remaining_budget(usage: ResourceUsage) -> ResourceBudget:
    return ResourceBudget(
        tokens=max(0, TOKEN_CEILING - usage.tokens),
        cpu_seconds=max(0.0, 300.0 - usage.cpu_seconds),
        wall_seconds=max(0.0, WALL_CEILING - usage.wall_seconds),
    )


def _add_usage(left: ResourceUsage, right: ResourceUsage) -> ResourceUsage:
    return _sum_usage((left, right))


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=root,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout
