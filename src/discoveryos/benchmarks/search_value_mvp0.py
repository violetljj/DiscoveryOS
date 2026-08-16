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

from discoveryos.benchmarks.local_patch_admission import (
    AdmissionArm,
    _build_spec,
    _initialize_arm,
    _materialize_files,
)
from discoveryos.benchmarks.search_policy_admission import (
    ResidualHeadroomEvidence,
    SearchObservation,
    compute_policy_metrics,
    evaluate_task_admission,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import (
    SearchValueTask,
    normalized_source,
    search_value_mvp0_tasks,
)
from discoveryos.contracts.models import (
    DataRole,
    EvidenceRecord,
    EvidenceValidity,
    ExperimentSpec,
    Fidelity,
    GateDecision,
    MetricDirection,
    ResourceBudget,
    ResourceUsage,
    RunMode,
)
from discoveryos.evaluation.gates import GateEngine
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    AnytimeTraceRecorder,
    DeterministicActionController,
    SearchAction,
)
from discoveryos.operators.asha import RungDefinition
from discoveryos.operators.local_patch import LOCAL_PATCH_PROMPT_TEMPLATE, LocalPatchOperator, PatchProvider
from discoveryos.operators.structural_rewrite import STRUCTURAL_REWRITE_PROMPT_TEMPLATE, StructuralRewriteOperator
from discoveryos.providers.codex_exec import PATCH_PROPOSAL_SCHEMA
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.search_loop import (
    LedgerBackedSearchStateProjector,
    SearchActionResult,
    SearchLoopRunner,
    SearchRunSpec,
    UnifiedActionExecutor,
)
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "DISCOVERYOS_SEARCH_VALUE_MVP0_V1"
MANIFEST_RECORD = "search-value-mvp0-manifest.json"
REPORT_RECORD = "search-value-mvp0-report.json"
MECHANICS_ANCHOR = "ec301a18f6543e8c07d62b49bc8cf784f90b137d"
DEFAULT_TOKEN_CEILING = 60_000
DEFAULT_WALL_CEILING = 1_200.0
DEFAULT_CPU_CEILING = 300.0
GENERATION_FLOOR = 20_000
EXECUTION_ORDER_SEED = 17082601


STRUCTURAL_PATCH_SCHEMA: dict[str, Any] = json.loads(json.dumps(PATCH_PROPOSAL_SCHEMA))
STRUCTURAL_PATCH_SCHEMA["required"] = [
    *STRUCTURAL_PATCH_SCHEMA["required"],
    "algorithm_family",
    "escape_rationale",
    "reused_component_ids",
]
STRUCTURAL_PATCH_SCHEMA["properties"].update(
    {
        "algorithm_family": {"type": "string", "minLength": 1},
        "escape_rationale": {"type": "string", "minLength": 1},
        "reused_component_ids": {"type": "array", "items": {"type": "string"}},
    }
)


def mvp0_controller_config() -> ActionControllerConfig:
    return ActionControllerConfig(
        stagnation_generations=2,
        improvement_epsilon=0.01,
        uncertainty_threshold=0.05,
        incumbent_proximity=0.025,
        minimum_replicates=1,
        structural_similarity_threshold=0.0,
        costs=(
            ActionCost(SearchAction.LOCAL_PATCH, ResourceBudget(tokens=GENERATION_FLOOR, wall_seconds=300)),
            ActionCost(SearchAction.STRUCTURAL_ESCAPE, ResourceBudget(tokens=GENERATION_FLOOR, wall_seconds=300)),
            ActionCost(SearchAction.REPLICATE, ResourceBudget(cpu_seconds=5, wall_seconds=30)),
            ActionCost(SearchAction.PROMOTE_FIDELITY, ResourceBudget(cpu_seconds=10, wall_seconds=60)),
        ),
    )


def seal_search_value_mvp0(
    workspace: Path,
    *,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    token_ceiling: int = DEFAULT_TOKEN_CEILING,
    wall_ceiling: float = DEFAULT_WALL_CEILING,
    cpu_ceiling: float = DEFAULT_CPU_CEILING,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("MVP-0 sealing requires an empty workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    code_sha = _git(Path(__file__).resolve().parents[3], "rev-parse", "HEAD").strip()
    if _git(Path(__file__).resolve().parents[3], "status", "--porcelain").strip():
        raise RuntimeError("MVP-0 protocol must be sealed from a clean committed worktree")
    if token_ceiling < GENERATION_FLOOR or wall_ceiling <= 0 or cpu_ceiling <= 0:
        raise ValueError("MVP-0 requires positive matched resource ceilings")
    if local_provider.model != structural_provider.model:
        raise ValueError("local and structural providers must use the same frozen model")
    provider_version = getattr(local_provider, "provider_version", "unknown")
    if provider_version == "unknown" or getattr(structural_provider, "provider_version", "unknown") != provider_version:
        raise RuntimeError("MVP-0 requires one reportable provider version")

    task_items = search_value_mvp0_tasks()
    task_records: list[dict[str, Any]] = []
    evidence_records: list[ResidualHeadroomEvidence] = []
    for item in task_items:
        repository, commit = item.task.initialize_repository(workspace / "protocol" / "tasks")
        evidence, details = _headroom_evidence(item, repository, mechanics_anchor=MECHANICS_ANCHOR)
        admission = evaluate_task_admission(evidence)
        if not admission["admitted"]:
            failures = [name for name, passed in admission["checks"].items() if not passed]
            raise RuntimeError(f"MVP-0 task admission failed: {item.task.task_id}:{failures}")
        evidence_records.append(evidence)
        task_records.append(
            {
                "task_id": item.task.task_id,
                "category": item.task.category,
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

    controller = mvp0_controller_config()
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_MODEL",
        "claim_ceiling": "SEARCH_VALUE_MVP0_FROZEN_DISTRIBUTION_ONLY",
        "model_calls_before_seal": 0,
        "mechanics_anchor_sha": MECHANICS_ANCHOR,
        "experiment_code_sha": code_sha,
        "task_suite_source_digest": digest_bytes(
            Path(__file__).with_name("search_value_mvp0_tasks.py").read_bytes()
        ),
        "protocol_source_digest": digest_bytes(Path(__file__).read_bytes()),
        "tasks": task_records,
        "arms": {
            "vanilla_one_shot": {
                "scientific_generation_limit": 1,
                "controller": "one direct bounded proposal from the frozen baseline",
                "prompt_template_digest": digest_bytes(LOCAL_PATCH_PROMPT_TEMPLATE.encode("utf-8")),
            },
            "discoveryos_unified_loop": {
                "controller_digest": controller.digest,
                "local_prompt_template_digest": digest_bytes(LOCAL_PATCH_PROMPT_TEMPLATE.encode("utf-8")),
                "structural_prompt_template_digest": digest_bytes(STRUCTURAL_REWRITE_PROMPT_TEMPLATE.encode("utf-8")),
                "single_active_branch": True,
                "max_steps": 6,
                "local_action_limit_per_family": 2,
                "structural_action_limit": 1,
            },
        },
        "model": {
            "provider": local_provider.provider_name,
            "model": local_provider.model,
            "provider_version": provider_version,
            "local_settings_digest": local_provider.settings_digest,
            "structural_settings_digest": structural_provider.settings_digest,
        },
        "matched_resources_per_task_arm": {
            "tokens": token_ceiling,
            "wall_seconds": wall_ceiling,
            "cpu_seconds": cpu_ceiling,
            "wall_tolerance_fraction": 0.05,
            "unused_budget_transfer": False,
        },
        "fairness": {
            "same_model": True,
            "same_task_statement": True,
            "same_repository_snapshot": True,
            "same_mutable_files": True,
            "same_evaluator_and_development_data": True,
            "same_model_reasoning_settings": True,
            "same_starting_candidate": True,
            "vanilla_prompt_is_not_reduced": True,
            "final_blind_access": False,
        },
        "metrics": {
            "primary": ["task_win_tie_loss", "final_improvement", "success_rate", "anytime_auc"],
            "anytime_checkpoints": [0.25, 0.50, 0.75, 1.00],
            "efficiency": [
                "tokens_to_first_improvement",
                "tokens_to_best",
                "wall_to_first_improvement",
                "wall_to_best",
            ],
            "reliability": ["invalid_generation_rate", "mechanics_failure_rate"],
        },
        "pass_gate": {
            "task_wins_strictly_greater_than_losses": True,
            "median_final_improvement_not_below_vanilla": True,
            "median_anytime_auc_not_below_vanilla": True,
            "all_resource_protection_checks_pass": True,
            "paired_win_rate_60_percent_is_strong_positive_signal_not_required_for_minimum_pass": True,
        },
        "execution_order_seed": EXECUTION_ORDER_SEED,
        "task_replacement_after_model_feedback": False,
        "bugs_after_seal": "record INVALID_MECHANICS; do not modify or rerun this revision",
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {
        "status": "SEALED_PRE_MODEL",
        "task_count": len(task_records),
        "model_calls": 0,
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "experiment_code_sha": code_sha,
        "mechanics_anchor_sha": MECHANICS_ANCHOR,
    }


def run_search_value_mvp0(
    workspace: Path,
    *,
    manifest_digest: str,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_manifest(manifest, manifest_digest, workspace, local_provider, structural_provider)
    report_path = workspace / "result-artifacts" / "records" / REPORT_RECORD
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    task_map = {item.task.task_id: item for item in search_value_mvp0_tasks()}
    schedule = [
        (record["task_id"], arm)
        for record in manifest["tasks"]
        for arm in ("vanilla_one_shot", "discoveryos_unified_loop")
    ]
    random.Random(manifest["execution_order_seed"]).shuffle(schedule)
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for index, (task_id, arm_name) in enumerate(schedule, start=1):
        if progress:
            progress(f"MVP-0 {index}/{len(schedule)} starting {task_id}:{arm_name}")
        task_record = next(item for item in manifest["tasks"] if item["task_id"] == task_id)
        item = task_map[task_id]
        repository = Path(task_record["repository"])
        arm = _initialize_arm(
            workspace / "arms" / task_id / arm_name,
            item.task,
            repository,
            task_record["repository_commit"],
            int(manifest["matched_resources_per_task_arm"]["tokens"]),
        )
        if arm_name == "vanilla_one_shot":
            result = asyncio.run(
                _run_vanilla(
                    arm,
                    item,
                    local_provider,
                    token_ceiling=int(manifest["matched_resources_per_task_arm"]["tokens"]),
                    wall_ceiling=float(manifest["matched_resources_per_task_arm"]["wall_seconds"]),
                )
            )
        else:
            result = asyncio.run(
                _run_discoveryos(
                    arm,
                    item,
                    local_provider,
                    structural_provider,
                    token_ceiling=int(manifest["matched_resources_per_task_arm"]["tokens"]),
                    wall_ceiling=float(manifest["matched_resources_per_task_arm"]["wall_seconds"]),
                    cpu_ceiling=float(manifest["matched_resources_per_task_arm"]["cpu_seconds"]),
                )
            )
        results[(task_id, arm_name)] = result
        ArtifactStore(workspace / "result-artifacts").write_record(
            f"tasks/{task_id}/{arm_name}.json", result
        )
        if progress:
            progress(
                f"MVP-0 completed {task_id}:{arm_name} improvement={result['metrics']['best_improvement']:.6f} "
                f"auc={result['metrics']['auc_over_token_budget']:.6f} tokens={result['actual_usage']['tokens']}"
            )
    report = _aggregate(manifest, results)
    ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return report


async def _run_vanilla(
    arm: AdmissionArm,
    item: SearchValueTask,
    provider: PatchProvider,
    *,
    token_ceiling: int,
    wall_ceiling: float,
) -> dict[str, Any]:
    started = time.monotonic()
    baseline = await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="baseline")
    operator = LocalPatchOperator(
        provider=provider,
        artifacts=arm.artifacts,
        ledger=arm.ledger,
        contract=arm.contract,
        strategy_id="mvp0_vanilla_one_shot",
    )
    bundle = __import__("discoveryos.contracts.executable", fromlist=["ExecutableCandidateBundle"]).ExecutableCandidateBundle.from_artifact(
        arm.artifacts, arm.baseline.artifact_digest
    )
    result = operator.propose(
        parent=arm.baseline,
        mutable_files=_materialize_files(bundle, arm.contract.mutable_paths),
        development_evidence_summary=canonical_evidence_summary((baseline,)),
        failure_signature=baseline.failure_signature,
        semantic_delta_memory=(arm.baseline.semantic_delta,),
        remaining_budget=ResourceBudget(tokens=token_ceiling, wall_seconds=wall_ceiling),
        build=_build_spec(bundle),
    )
    evidence = None
    if result.candidate is not None:
        evidence = await _evaluate_at(arm, result.candidate, Fidelity.G2, seed=0, attempt="one-shot")
    usage = _sum_usage((result.record.usage, evidence.resource_usage if evidence else ResourceUsage()))
    valid, feasible, score = _evidence_value(arm, evidence)
    observation = SearchObservation(
        candidate_id=result.candidate.candidate_id if result.candidate else result.record.generation_id,
        parent_id=None,
        cumulative_tokens=usage.tokens,
        cumulative_wall_seconds=usage.wall_seconds,
        score=score,
        valid=valid,
        feasible=feasible,
        basin_id="one_shot_generated" if valid and feasible else None,
    )
    headroom = _headroom_from_item(item, arm)
    metrics = compute_policy_metrics(
        headroom,
        (observation,),
        token_budget=token_ceiling,
        wall_budget=wall_ceiling,
    )
    metrics.update(_extra_metrics((observation,), token_ceiling, headroom))
    makespan = time.monotonic() - started
    return _arm_report(
        arm_name="vanilla_one_shot",
        task_id=item.task.task_id,
        metrics=metrics,
        observations=(observation,),
        usage=usage,
        makespan=makespan,
        token_ceiling=token_ceiling,
        wall_ceiling=wall_ceiling,
        action_counts={"LOCAL_PATCH": 1},
        mechanics_failures=int(result.candidate is None or (evidence is not None and not valid)),
    )


async def _run_discoveryos(
    arm: AdmissionArm,
    item: SearchValueTask,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    *,
    token_ceiling: int,
    wall_ceiling: float,
    cpu_ceiling: float,
) -> dict[str, Any]:
    started = time.monotonic()
    await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt="baseline")
    config = mvp0_controller_config()
    spec = SearchRunSpec(
        run_id=f"mvp0-{item.task.task_id}",
        contract_digest=arm.contract.digest,
        root_candidate_id=arm.baseline.candidate_id,
        branch_id="single-active-branch",
        initial_algorithm_family=item.baseline_basin_id,
        metric_name="score",
        metric_direction=MetricDirection.MAXIMIZE,
        initial_fidelity=Fidelity.G1,
        budget=ResourceBudget(tokens=token_ceiling, cpu_seconds=cpu_ceiling, wall_seconds=wall_ceiling),
        rungs=(
            RungDefinition("mvp0-g1", Fidelity.G1, ResourceBudget(cpu_seconds=5, wall_seconds=30)),
            RungDefinition("mvp0-g2", Fidelity.G2, ResourceBudget(cpu_seconds=10, wall_seconds=60)),
        ),
        eta=2,
        initial_trials=2,
        local_action_limit=2,
        structural_action_limit=1,
        max_steps=6,
        mutable_file_paths=(item.task.entrypoint,),
        seeds=(0, 1, 2),
        mode=RunMode.BENCHMARK,
    )
    projector = LedgerBackedSearchStateProjector(
        spec=spec,
        contract=arm.contract,
        controller_config=config,
        ledger=arm.ledger,
        artifacts=arm.artifacts,
    )
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
    )
    loop_result = await SearchLoopRunner(
        controller=DeterministicActionController(config),
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
        token_budget=token_ceiling,
        wall_budget=wall_ceiling,
    )
    metrics.update(_extra_metrics(observations, token_ceiling, headroom))
    usage = _sum_usage(action.actual_usage for action in actions)
    action_counts = {
        action.value: sum(result.action is action for result in actions)
        for action in SearchAction
        if action is not SearchAction.STOP
    }
    makespan = time.monotonic() - started
    return _arm_report(
        arm_name="discoveryos_unified_loop",
        task_id=item.task.task_id,
        metrics=metrics,
        observations=observations,
        usage=usage,
        makespan=makespan,
        token_ceiling=token_ceiling,
        wall_ceiling=wall_ceiling,
        action_counts=action_counts,
        mechanics_failures=sum(bool(action.failure_signature) for action in actions),
        stop_reason=loop_result.stop_decision.reason_codes,
    )


async def _evaluate_at(
    arm: AdmissionArm,
    candidate,
    fidelity: Fidelity,
    *,
    seed: int,
    attempt: str,
) -> EvidenceRecord:
    split_id = "development" if fidelity is not Fidelity.G0 else None
    split_role = DataRole.DEVELOPMENT if split_id else None
    experiment = ExperimentSpec.create(
        candidate_id=candidate.candidate_id,
        evaluator_id=arm.contract.evaluator_id_for(fidelity),
        fidelity=fidelity,
        split_id=split_id,
        split_role=split_role,
        seed=seed,
        resources=ResourceBudget(cpu_seconds=10, wall_seconds=60),
        contract_digest=arm.contract.digest,
        mode=RunMode.BENCHMARK,
        replicate_id=f"seed-{seed}",
        rung_id=f"mvp0-{fidelity.value}",
        attempt_id=attempt,
    )
    return await arm.executor.execute(candidate, experiment)


def _headroom_evidence(
    item: SearchValueTask,
    repository: Path,
    *,
    mechanics_anchor: str,
) -> tuple[ResidualHeadroomEvidence, dict[str, Any]]:
    baseline_scores = tuple(_score_source(item, repository, item.task.algorithm_source) for _ in range(2))
    reference_score = _score_source(item, repository, item.reference_source)
    intermediate_scores = tuple(
        _score_source(item, repository, source) for source in item.intermediate_sources
    )
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
        evaluator_id=f"mvp0-executable-{item.task.task_id}",
        evaluator_digest=digest_bytes(normalized_source(item.task.evaluator_source).encode("utf-8")),
        baseline_candidate_digest=digest_bytes(normalized_source(item.task.algorithm_source).encode("utf-8")),
        baseline_receipt_digest=digest_json({"scores": baseline_scores, "fidelity": Fidelity.G2.value}),
        baseline_score=baseline_scores[0],
        score_direction=MetricDirection.MAXIMIZE,
        score_resolution=item.score_resolution,
        reference_score=reference_score,
        reference_kind="exact_oracle",
        reference_digest=digest_bytes(normalized_source(item.reference_source).encode("utf-8")),
        selection_provenance_digest=digest_json(
            {"generator": "independent_deterministic_mvp0_v1", "mechanics_anchor": mechanics_anchor}
        ),
        valid_intermediate_scores=tuple(distinct),
        trajectory_classes=item.trajectory_classes,
        baseline_basin_id=item.baseline_basin_id,
        basin_labeler_digest=digest_json(
            {"baseline": item.baseline_basin_id, "local": "inherit", "structural": "target_algorithm_family"}
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
    }


def _score_source(item: SearchValueTask, repository: Path, source: str) -> float:
    path = repository / item.task.entrypoint
    original = path.read_text(encoding="utf-8")
    path.write_text(normalized_source(source), encoding="utf-8")
    environment = os.environ.copy()
    environment["DISCOVERYOS_FIDELITY"] = Fidelity.G2.value
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        for command in (("python", "public_tests.py"), ("python", "evaluate.py")):
            result = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"independent task evidence failed: {item.task.task_id}:{result.stderr}")
        payload = json.loads(result.stdout.splitlines()[-1])
        if float(payload["metrics"]["valid"]) != 1.0:
            raise RuntimeError(f"independent source is invalid: {item.task.task_id}")
        return float(payload["metrics"]["score"])
    finally:
        path.write_text(original, encoding="utf-8")


def _headroom_from_item(item: SearchValueTask, arm: AdmissionArm) -> ResidualHeadroomEvidence:
    repository = Path(
        __import__("discoveryos.contracts.executable", fromlist=["ExecutableCandidateBundle"])
        .ExecutableCandidateBundle.from_artifact(arm.artifacts, arm.baseline.artifact_digest)
        .base_repository
    )
    return _headroom_evidence(item, repository, mechanics_anchor=MECHANICS_ANCHOR)[0]


def _search_observations(
    arm: AdmissionArm,
    item: SearchValueTask,
    actions: tuple[SearchActionResult, ...],
) -> tuple[SearchObservation, ...]:
    evidence_by_receipt = {item.receipt_id: item for item in arm.ledger.evidence_records()}
    observations: list[SearchObservation] = []
    cumulative_tokens = 0
    cumulative_wall = 0.0
    basin = item.baseline_basin_id
    for action in actions:
        cumulative_tokens += action.actual_usage.tokens
        cumulative_wall += action.actual_usage.wall_seconds
        evidence = evidence_by_receipt.get(action.evidence_receipt_id or "")
        valid, feasible, score = _evidence_value(arm, evidence)
        if action.action is SearchAction.STRUCTURAL_ESCAPE and action.result_candidate_id:
            candidate = arm.ledger.get_candidate(action.result_candidate_id)
            basin = str(candidate.parameter_dict().get("target_algorithm_family", "structural_escape"))
        observations.append(
            SearchObservation(
                candidate_id=action.decision_id,
                parent_id=observations[-1].candidate_id if observations else None,
                cumulative_tokens=cumulative_tokens,
                cumulative_wall_seconds=cumulative_wall,
                score=score,
                valid=valid,
                feasible=feasible,
                basin_id=basin if valid and feasible else None,
            )
        )
    return tuple(observations)


def _evidence_value(arm: AdmissionArm, evidence: EvidenceRecord | None) -> tuple[bool, bool, float | None]:
    if evidence is None:
        return False, False, None
    gate = GateEngine().evaluate(arm.contract, evidence).decision
    valid = evidence.validity is EvidenceValidity.VALID
    feasible = gate is GateDecision.FEASIBLE
    return valid, feasible, evidence.metric_dict().get("score") if valid and feasible else None


def canonical_evidence_summary(evidence: tuple[EvidenceRecord, ...]) -> str:
    return json.dumps(
        {
            "development_evidence": [
                {
                    "receipt_id": item.receipt_id,
                    "fidelity": item.fidelity.value,
                    "validity": item.validity.value,
                    "metrics": item.metric_dict(),
                    "failure_signature": item.failure_signature,
                }
                for item in evidence
            ]
        },
        sort_keys=True,
    )


def _extra_metrics(
    observations: tuple[SearchObservation, ...],
    token_ceiling: int,
    headroom: ResidualHeadroomEvidence,
) -> dict[str, Any]:
    best_improvement = 0.0
    first_tokens = None
    first_wall = None
    best_tokens = 0
    best_wall = 0.0
    checkpoint_values: dict[str, float] = {}
    for observation in observations:
        if observation.valid and observation.feasible and observation.score is not None:
            improvement = max(0.0, observation.score - headroom.baseline_score)
            if improvement > best_improvement:
                best_improvement = improvement
                best_tokens = observation.cumulative_tokens
                best_wall = observation.cumulative_wall_seconds
            if first_tokens is None and improvement >= headroom.score_resolution - 1e-12:
                first_tokens = observation.cumulative_tokens
                first_wall = observation.cumulative_wall_seconds
    for fraction in (0.25, 0.5, 0.75, 1.0):
        ceiling = token_ceiling * fraction
        values = [
            max(0.0, observation.score - headroom.baseline_score)
            for observation in observations
            if observation.cumulative_tokens <= ceiling
            and observation.valid
            and observation.feasible
            and observation.score is not None
        ]
        checkpoint_values[f"best_improvement_at_{int(fraction * 100)}pct"] = max(values, default=0.0)
    return {
        **checkpoint_values,
        "tokens_to_best": best_tokens,
        "wall_to_best": best_wall,
        "wall_to_first_improvement": first_wall,
        "observed_tokens_to_first_improvement": first_tokens,
    }


def _arm_report(
    *,
    arm_name: str,
    task_id: str,
    metrics: dict[str, Any],
    observations: tuple[SearchObservation, ...],
    usage: ResourceUsage,
    makespan: float,
    token_ceiling: int,
    wall_ceiling: float,
    action_counts: dict[str, int],
    mechanics_failures: int,
    stop_reason: tuple[str, ...] = (),
) -> dict[str, Any]:
    materialized = max(1, len(observations))
    return {
        "task_id": task_id,
        "arm": arm_name,
        "metrics": metrics,
        "observations": [jsonable(item) for item in observations],
        "action_counts": action_counts,
        "stop_reason": stop_reason,
        "actual_usage": {
            **usage.as_budget_dict(),
            "llm_input_tokens": usage.llm_input_tokens,
            "llm_output_tokens": usage.llm_output_tokens,
            "llm_cache_tokens": usage.llm_cache_tokens,
            "end_to_end_makespan": makespan,
        },
        "invalid_generation_rate": sum(not item.valid for item in observations) / materialized,
        "mechanics_failure_rate": mechanics_failures / materialized,
        "resource_checks": {
            "token_ceiling_respected": usage.tokens <= token_ceiling,
            "wall_ceiling_with_tolerance_respected": makespan <= wall_ceiling * 1.05,
        },
    }


def _aggregate(manifest: dict[str, Any], results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    comparisons = []
    wins = ties = losses = 0
    for task_record in manifest["tasks"]:
        task_id = task_record["task_id"]
        vanilla = results[(task_id, "vanilla_one_shot")]
        dos = results[(task_id, "discoveryos_unified_loop")]
        delta = dos["metrics"]["best_improvement"] - vanilla["metrics"]["best_improvement"]
        resolution = task_record["headroom_evidence"]["score_resolution"]
        if delta >= resolution - 1e-12:
            outcome = "WIN"; wins += 1
        elif delta <= -resolution + 1e-12:
            outcome = "LOSS"; losses += 1
        else:
            outcome = "TIE"; ties += 1
        comparisons.append(
            {
                "task_id": task_id,
                "outcome": outcome,
                "final_improvement_delta": delta,
                "auc_delta": dos["metrics"]["auc_over_token_budget"] - vanilla["metrics"]["auc_over_token_budget"],
                "vanilla": vanilla,
                "discoveryos": dos,
            }
        )
    vanilla_improvements = [item["vanilla"]["metrics"]["best_improvement"] for item in comparisons]
    dos_improvements = [item["discoveryos"]["metrics"]["best_improvement"] for item in comparisons]
    vanilla_auc = [item["vanilla"]["metrics"]["auc_over_token_budget"] for item in comparisons]
    dos_auc = [item["discoveryos"]["metrics"]["auc_over_token_budget"] for item in comparisons]
    resource_ok = all(
        all(report["resource_checks"].values())
        for item in comparisons
        for report in (item["vanilla"], item["discoveryos"])
    )
    checks = {
        "wins_greater_than_losses": wins > losses,
        "median_final_improvement_not_below_vanilla": statistics.median(dos_improvements) >= statistics.median(vanilla_improvements),
        "median_anytime_auc_not_below_vanilla": statistics.median(dos_auc) >= statistics.median(vanilla_auc),
        "resource_protection": resource_ok,
    }
    return {
        "protocol_id": manifest["protocol_id"],
        "manifest_digest": manifest["manifest_digest"],
        "experiment_code_sha": manifest["experiment_code_sha"],
        "mechanics_anchor_sha": manifest["mechanics_anchor_sha"],
        "task_count": len(comparisons),
        "paired": {"wins": wins, "ties": ties, "losses": losses, "win_rate": wins / len(comparisons)},
        "medians": {
            "vanilla_final_improvement": statistics.median(vanilla_improvements),
            "discoveryos_final_improvement": statistics.median(dos_improvements),
            "vanilla_anytime_auc": statistics.median(vanilla_auc),
            "discoveryos_anytime_auc": statistics.median(dos_auc),
        },
        "pass_checks": checks,
        "verdict": "SEARCH_VALUE_MVP0_PASS" if all(checks.values()) else "SEARCH_VALUE_MVP0_FAIL",
        "strong_positive_signal": wins / len(comparisons) >= 0.60 and losses < wins,
        "claim_ceiling": "FROZEN_MVP0_TASK_DISTRIBUTION_AND_MODEL_CONFIG_ONLY",
        "comparisons": comparisons,
    }


def _verify_manifest(
    manifest: dict[str, Any],
    expected_digest: str,
    workspace: Path,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
) -> None:
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("MVP-0 manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_MODEL" or manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("MVP-0 was not sealed before candidate-model execution")
    current_sha = _git(Path(__file__).resolve().parents[3], "rev-parse", "HEAD").strip()
    if current_sha != manifest["experiment_code_sha"]:
        raise RuntimeError("MVP-0 experiment code SHA drifted after sealing")
    if digest_bytes(Path(__file__).read_bytes()) != manifest["protocol_source_digest"]:
        raise RuntimeError("MVP-0 protocol source drifted after sealing")
    expected_model = manifest["model"]
    if (
        local_provider.provider_name != expected_model["provider"]
        or local_provider.model != expected_model["model"]
        or local_provider.settings_digest != expected_model["local_settings_digest"]
        or structural_provider.settings_digest != expected_model["structural_settings_digest"]
        or getattr(local_provider, "provider_version", "unknown") != expected_model["provider_version"]
    ):
        raise RuntimeError("MVP-0 provider/model/settings differ from the sealed manifest")
    task_map = {item.task.task_id: item for item in search_value_mvp0_tasks()}
    for record in manifest["tasks"]:
        item = task_map.get(record["task_id"])
        repository = Path(record["repository"])
        if item is None or item.payload_digest != record["task_payload_digest"]:
            raise RuntimeError(f"MVP-0 task definition drift: {record['task_id']}")
        if _git(repository, "status", "--porcelain").strip() or _git(repository, "rev-parse", "HEAD").strip() != record["repository_commit"]:
            raise RuntimeError(f"MVP-0 frozen repository drift: {record['task_id']}")
        for path, digest in record["files"].items():
            if digest_bytes((repository / path).read_bytes()) != digest:
                raise RuntimeError(f"MVP-0 frozen file drift: {record['task_id']}:{path}")


def _sum_usage(items) -> ResourceUsage:
    total = ResourceUsage()
    for item in items:
        exit_codes = [value for value in (total.exit_code, item.exit_code) if value is not None]
        total = ResourceUsage(
            llm_input_tokens=total.llm_input_tokens + item.llm_input_tokens,
            llm_output_tokens=total.llm_output_tokens + item.llm_output_tokens,
            llm_cache_tokens=total.llm_cache_tokens + item.llm_cache_tokens,
            cpu_seconds=total.cpu_seconds + item.cpu_seconds,
            gpu_seconds=total.gpu_seconds + item.gpu_seconds,
            device_seconds=total.device_seconds + item.device_seconds,
            wall_seconds=total.wall_seconds + item.wall_seconds,
            peak_rss_bytes=max(total.peak_rss_bytes, item.peak_rss_bytes),
            exit_code=max(exit_codes, default=None),
        )
    return total


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout
