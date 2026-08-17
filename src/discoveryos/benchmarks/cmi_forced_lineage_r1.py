from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.cmi_search_transmission_autopsy import (
    SOURCE_MANIFEST_RECORD,
    SOURCE_REPORT_RECORD,
    _candidate_payloads,
    _exact_candidate,
    _verify_source_authority,
)
from discoveryos.benchmarks.cmi_search_value_r1 import (
    _add_usage,
    _implementation_paths as _search_value_implementation_paths,
    _load_real_provider_preflight,
    _local_operator,
    _local_step,
    _remaining_budget as _search_value_remaining_budget,
    _source_candidate,
)
from discoveryos.benchmarks.cmi_search_value_r1_tasks import cmi_search_value_r1_tasks
from discoveryos.benchmarks.executable_mechanism_contract import _repository_snapshot
from discoveryos.benchmarks.local_patch_admission import _initialize_arm
from discoveryos.benchmarks.search_policy_admission import SearchObservation, compute_policy_metrics
from discoveryos.benchmarks.search_value_mvp0 import _evaluate_at, _evidence_value, _extra_metrics, _materialize_files
from discoveryos.benchmarks.si2 import _si2_headroom_evidence
from discoveryos.contracts.executable import ExecutableCandidateBundle
from discoveryos.contracts.models import Fidelity, ResourceBudget, ResourceUsage
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CMI_FORCED_LINEAGE_TRANSMISSION_R1_CONSUMED_V3"
MANIFEST_RECORD = "cmi-forced-lineage-transmission-r1-manifest.json"
REPORT_RECORD = "cmi-forced-lineage-transmission-r1-report.json"
SOURCE_MANIFEST_DIGEST = "5c1395d78efc1b102896471655cc9cf83b7d61585592172712b92a4191233d3b"
SOURCE_REPORT_SHA256 = "de4850ae8c75bec35455e197356bd0dc608d47c7e6983a9a9025617ccea2a39b"
ARM_NAMES = ("INCUMBENT_LINEAGE", "CONTROL_DESCENDANT_LINEAGE", "CMI_DESCENDANT_LINEAGE")
DOWNSTREAM_GENERATIONS = 2
TOKEN_CEILING = 80_000
WALL_CEILING = 1_200.0


def seal_cmi_forced_lineage_r1(
    workspace: Path,
    *,
    source_workspace: Path,
    provider_preflight_path: Path,
    provider_preflight_sha256: str,
    provider: PatchProvider,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    source_workspace = source_workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI forced-lineage workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI forced-lineage protocol must be sealed from a clean worktree")
    provider_version = str(getattr(provider, "provider_version", "unknown"))
    if not provider_version or provider_version == "unknown":
        raise RuntimeError("CMI forced-lineage protocol requires a reportable provider version")
    if not getattr(provider, "reasoning_effort", None):
        raise RuntimeError("CMI forced-lineage protocol requires explicit reasoning effort")

    manifest_path = source_workspace / "protocol-artifacts" / "records" / SOURCE_MANIFEST_RECORD
    report_path = source_workspace / "result-artifacts" / "records" / SOURCE_REPORT_RECORD
    source_manifest = _load_json(manifest_path)
    source_report = _load_json(report_path)
    _verify_source_authority(
        source_manifest,
        source_report,
        manifest_path=manifest_path,
        report_path=report_path,
        manifest_digest=SOURCE_MANIFEST_DIGEST,
        report_sha256=SOURCE_REPORT_SHA256,
    )
    preflight_path = provider_preflight_path.resolve()
    if digest_bytes(preflight_path.read_bytes()) != provider_preflight_sha256:
        raise RuntimeError("real-provider preflight SHA-256 mismatch")
    preflight = _load_real_provider_preflight(preflight_path, provider_preflight_sha256)

    task_map = {item.task.task_id: item for item in cmi_search_value_r1_tasks()}
    states = []
    for task_record in source_manifest["tasks"]:
        task_id = str(task_record["task_id"])
        task_receipt_path = source_workspace / "result-artifacts" / "records" / "tasks" / f"{task_id}.json"
        receipt = _load_json(task_receipt_path)
        if not receipt["causal_trace"]["eligible"]:
            continue
        item = task_map[task_id]
        if item.payload_digest != task_record["task_payload_digest"]:
            raise RuntimeError(f"current task definition differs from consumed V3 authority: {task_id}")
        state = _extract_state(
                source_workspace,
                item.task.entrypoint,
                receipt,
                task_receipt_path,
            )
        state["task_payload_digest"] = task_record["task_payload_digest"]
        state["task_files"] = task_record["files"]
        states.append(state)
    if len(states) != 5:
        raise RuntimeError("forced-lineage R1 requires the complete five-state eligible V3 population")

    workspace.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[1]
    implementation_paths = _implementation_paths()
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "CMI_FORCED_LINEAGE_TRANSMISSION_R1_SEALED_PRE_MODEL",
        "scientific_question": "Can a weaker CMI descendant produce better downstream descendants than matched control and incumbent starting parents?",
        "claim_ceiling": "CONSUMED_V3_FORCED_LINEAGE_DEVELOPMENT_SIGNAL_ONLY_NO_SEARCH_VALUE_OR_SUPERIORITY_CLAIM",
        "fresh_task_budget": 0,
        "selection_policy_changes": 0,
        "generation_zero_counts_as_success": False,
        "source_authority": {
            "workspace": str(source_workspace),
            "manifest_digest": SOURCE_MANIFEST_DIGEST,
            "manifest_sha256": digest_bytes(manifest_path.read_bytes()),
            "report_sha256": SOURCE_REPORT_SHA256,
        },
        "repository": repository,
        "experiment_code_sha": repository["head_commit"],
        "implementation_digests": {
            str(path.relative_to(source_root)).replace("\\", "/"): digest_bytes(path.read_bytes())
            for path in implementation_paths
        },
        "provider": {
            "name": provider.provider_name,
            "model": provider.model,
            "version": provider_version,
            "reasoning_effort": provider.reasoning_effort,
            "settings_digest": provider.settings_digest,
        },
        "provider_preflight": {
            "path": str(preflight_path),
            "sha256": provider_preflight_sha256,
            "terminal": bool(preflight["terminal"]),
            "valid": True,
        },
        "matched_execution": {
            "arms": ARM_NAMES,
            "downstream_generations": DOWNSTREAM_GENERATIONS,
            "generator": "bounded_llm_local_patch_v1",
            "token_ceiling_per_arm": TOKEN_CEILING,
            "wall_ceiling_per_arm": WALL_CEILING,
            "forced_generation_zero_parent": True,
            "within_lineage_parent_rule": "FORCE_EACH_VALID_CHILD_AS_NEXT_PARENT_WITHOUT_FITNESS_SELECTION",
            "arm_order": "FIXED_LATIN_ROTATION_BY_STATE_INDEX",
        },
        "primary_endpoint": "best downstream utility after forced parent: CMI_DESCENDANT_LINEAGE minus CONTROL_DESCENDANT_LINEAGE",
        "secondary_endpoint": "anytime AUC from the forced generation-zero parent over the matched downstream token ceiling; CMI vs control, with incumbent lineage diagnostic",
        "success_gate": {
            "all_five_states_evaluable": True,
            "cmi_vs_control_primary_wins_required": 5,
            "cmi_vs_control_losses_allowed": 0,
            "each_family_all_primary_positive": True,
            "median_primary_delta_strictly_positive": True,
            "median_anytime_auc_delta_strictly_positive": True,
            "all_arms_exactly_two_provider_calls": True,
        },
        "kill_gate": "Any failure of the success gate closes further CMI Search integration, fresh CMI budget, selection tuning, quota, and bonus work under the current Operator.",
        "states": states,
        "model_calls_before_seal": 0,
    }
    manifest_digest = digest_json(payload)
    manifest = {**payload, "manifest_digest": manifest_digest}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {**manifest, "manifest_path": str(path), "manifest_sha256": digest_bytes(path.read_bytes())}


def run_cmi_forced_lineage_r1(
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
        return _load_json(report_path)
    task_map = {item.task.task_id: item for item in cmi_search_value_r1_tasks()}
    rows = []
    for index, state in enumerate(manifest["states"]):
        task_id = state["task_id"]
        record = f"tasks/{task_id}.json"
        record_path = workspace / "result-artifacts" / "records" / record
        if record_path.is_file():
            row = _load_json(record_path)
        else:
            root = workspace / "lineages" / task_id
            if root.exists() and any(root.iterdir()):
                raise RuntimeError(f"partial forced-lineage task exists without terminal receipt: {task_id}")
            if progress:
                progress(f"CMI forced-lineage {index + 1}/{len(manifest['states'])} starting {task_id}")
            row = asyncio.run(_run_state(root, task_map[task_id], state, provider, index))
            ArtifactStore(workspace / "result-artifacts").write_record(record, row)
        rows.append(row)
        if progress:
            progress(f"CMI forced-lineage completed {task_id} outcome={row['paired']['outcome']}")
    report = _aggregate(manifest, rows)
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


async def _run_state(root: Path, item: Any, state: dict[str, Any], provider: PatchProvider, index: int) -> dict[str, Any]:
    repository, commit = item.task.initialize_repository(root / "task-repository")
    for relative, expected in state["task_files"].items():
        if digest_bytes((repository / relative).read_bytes()) != expected:
            raise RuntimeError(f"consumed V3 task materialization drift: {item.task.task_id}:{relative}")
    order = tuple(ARM_NAMES[(index + offset) % len(ARM_NAMES)] for offset in range(len(ARM_NAMES)))
    arms = {}
    for name in order:
        arms[name] = await _run_arm(
            root / name.lower(), item, repository, commit, provider, name, state["parents"][name]
        )
    resolution = float(state["score_resolution"])
    control = arms["CONTROL_DESCENDANT_LINEAGE"]
    cmi = arms["CMI_DESCENDANT_LINEAGE"]
    evaluable = all(arm["technically_evaluable"] for arm in arms.values())
    if evaluable:
        primary_delta = cmi["best_downstream_utility"] - control["best_downstream_utility"]
        auc_delta = cmi["metrics"]["auc_over_token_budget"] - control["metrics"]["auc_over_token_budget"]
        outcome = "WIN" if primary_delta > resolution else "LOSS" if primary_delta < -resolution else "TIE"
    else:
        primary_delta = None
        auc_delta = None
        outcome = "NOT_EVALUABLE"
    return {
        "protocol_id": PROTOCOL_ID,
        "task_id": item.task.task_id,
        "task_category": item.task.category,
        "score_resolution": resolution,
        "arm_execution_order": order,
        "arms": arms,
        "paired": {
            "evaluable": evaluable,
            "outcome": outcome,
            "cmi_minus_control_best_downstream_utility": primary_delta,
            "cmi_minus_control_anytime_auc": auc_delta,
            "generation_zero_excluded_from_primary": True,
        },
    }


async def _run_arm(
    root: Path,
    item: Any,
    repository: Path,
    commit: str,
    provider: PatchProvider,
    arm_name: str,
    parent_record: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    arm = _initialize_arm(root, item.task, repository, commit, TOKEN_CEILING)
    baseline = await _evaluate_at(arm, arm.baseline, Fidelity.G1, seed=0, attempt=f"forced-lineage-{arm_name}-baseline")
    forced_parent = _source_candidate(
        arm, arm.baseline, item.task.entrypoint, parent_record["source"], f"forced_parent_{arm_name.lower()}"
    )
    parent_evidence = await _evaluate_at(
        arm, forced_parent, Fidelity.G2, seed=0, attempt=f"forced-lineage-{arm_name}-generation-zero"
    )
    valid, feasible, parent_score = _evidence_value(arm, parent_evidence)
    generation_zero_replay_matches = bool(
        parent_score is not None and abs(float(parent_score) - float(parent_record["score"])) <= 1e-12
    )
    evidence_history = [baseline, parent_evidence]
    parent = forced_parent
    usage = ResourceUsage()
    steps = []
    operator = _local_operator(arm, provider, f"cmi_forced_lineage_{arm_name.lower()}")
    if valid and feasible and parent_score is not None and generation_zero_replay_matches:
        for generation in range(1, DOWNSTREAM_GENERATIONS + 1):
            generated = await _local_step(
                arm,
                item,
                operator,
                parent,
                evidence_history,
                _remaining_budget(usage),
                attempt=f"forced-lineage-{arm_name}-g{generation}",
            )
            usage = _add_usage(usage, generated["usage"])
            generated["generation"] = generation
            generated["authoritative_parent_id"] = parent.candidate_id
            steps.append(generated)
            if generated["evidence"] is not None:
                evidence_history.append(generated["evidence"])
            if not (generated["valid"] and generated["feasible"] and generated["candidate"] is not None):
                break
            parent = generated["candidate"]

    observations = [
        SearchObservation(
            candidate_id=forced_parent.candidate_id,
            parent_id=None,
            cumulative_tokens=0,
            cumulative_wall_seconds=0.0,
            score=float(parent_score) if parent_score is not None else None,
            valid=bool(valid),
            feasible=bool(feasible),
            basin_id=arm_name if valid and feasible else None,
        )
    ]
    cumulative = ResourceUsage()
    for step in steps:
        cumulative = _add_usage(cumulative, step["usage"])
        observations.append(
            SearchObservation(
                candidate_id=step["candidate_id"],
                parent_id=step["authoritative_parent_id"],
                cumulative_tokens=cumulative.tokens,
                cumulative_wall_seconds=cumulative.wall_seconds,
                score=step["score"],
                valid=bool(step["valid"]),
                feasible=bool(step["feasible"]),
                basin_id=arm_name if step["valid"] and step["feasible"] else None,
            )
        )
    headroom = _si2_headroom_evidence(item, repository)[0]
    metrics = compute_policy_metrics(headroom, tuple(observations), token_budget=TOKEN_CEILING, wall_budget=WALL_CEILING)
    metrics.update(_extra_metrics(tuple(observations), TOKEN_CEILING, headroom))
    downstream_scores = [float(step["score"]) for step in steps if step["valid"] and step["feasible"] and step["score"] is not None]
    technically_evaluable = (
        generation_zero_replay_matches
        and len(steps) == DOWNSTREAM_GENERATIONS
        and len(downstream_scores) == DOWNSTREAM_GENERATIONS
    )
    return {
        "arm": arm_name,
        "generation_zero": {
            "source_sha256": digest_bytes(parent_record["source"].encode("utf-8")),
            "source_candidate_id": parent_record["source_candidate_id"],
            "replayed_candidate_id": forced_parent.candidate_id,
            "source_v3_score": parent_record["score"],
            "replayed_score": float(parent_score) if parent_score is not None else None,
            "replay_matches_source_score": generation_zero_replay_matches,
            "valid": bool(valid and feasible),
            "counts_as_success": False,
        },
        "downstream": [
            {
                "generation": step["generation"],
                "candidate_id": step["candidate_id"],
                "authoritative_parent_id": step["authoritative_parent_id"],
                "valid": bool(step["valid"]),
                "feasible": bool(step["feasible"]),
                "score": step["score"],
                "failure_signature": step["failure_signature"],
                "usage": jsonable(step["usage"]),
            }
            for step in steps
        ],
        "best_downstream_utility": max(downstream_scores) if downstream_scores else None,
        "metrics": metrics,
        "actual_usage": jsonable(usage),
        "provider_calls": len(steps),
        "evaluator_calls": 2 + sum(step["evidence"] is not None for step in steps),
        "technically_evaluable": technically_evaluable,
        "resource_checks": {
            "token_ceiling_respected": usage.tokens <= TOKEN_CEILING,
            "wall_ceiling_respected": usage.wall_seconds <= WALL_CEILING,
        },
        "elapsed_seconds": time.monotonic() - started,
    }


def _extract_state(
    source_workspace: Path,
    entrypoint: str,
    receipt: dict[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    task_id = receipt["task_id"]
    root = source_workspace / "search" / task_id
    treatment_candidates = _candidate_payloads(root / "treatment" / "ledger.sqlite3")
    control_candidates = _candidate_payloads(root / "control" / "ledger.sqlite3")
    prefix = _exact_candidate(treatment_candidates, operator_id="paired_prefix_replay")
    cmi = _exact_candidate(treatment_candidates, operator_id="cmi_functional_basin_escape_v1")
    control = _exact_candidate(control_candidates, strategy_id="cmi_svr1_control_intervention")
    treatment_observations = receipt["arms"]["CMI_ENABLED"]["observations"]
    control_observations = receipt["arms"]["CMI_DISABLED"]["observations"]
    parents = {
        "INCUMBENT_LINEAGE": _parent_binding(root / "treatment", prefix, entrypoint, max(float(row["score"]) for row in treatment_observations[:2])),
        "CONTROL_DESCENDANT_LINEAGE": _parent_binding(root / "control", control, entrypoint, float(control_observations[2]["score"])),
        "CMI_DESCENDANT_LINEAGE": _parent_binding(root / "treatment", cmi, entrypoint, float(treatment_observations[2]["score"])),
    }
    return {
        "task_id": task_id,
        "task_category": receipt["task_category"],
        "score_resolution": receipt["score_resolution"],
        "source_task_receipt": {"path": str(receipt_path.resolve()), "sha256": digest_bytes(receipt_path.read_bytes())},
        "parents": parents,
    }


def _parent_binding(branch_root: Path, payload: dict[str, Any], entrypoint: str, score: float) -> dict[str, Any]:
    store = ArtifactStore(branch_root / "artifacts")
    bundle = ExecutableCandidateBundle.from_artifact(store, payload["artifact_digest"])
    source = _materialize_files(bundle, (entrypoint,))[entrypoint]
    return {
        "source_candidate_id": payload["candidate_id"],
        "source_artifact_digest": payload["artifact_digest"],
        "source": source,
        "source_sha256": digest_bytes(source.encode("utf-8")),
        "score": score,
        "source_ledger_sha256": digest_bytes((branch_root / "ledger.sqlite3").read_bytes()),
    }


def _aggregate(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluable = [row for row in rows if row["paired"]["evaluable"]]
    wins = sum(row["paired"]["outcome"] == "WIN" for row in evaluable)
    ties = sum(row["paired"]["outcome"] == "TIE" for row in evaluable)
    losses = sum(row["paired"]["outcome"] == "LOSS" for row in evaluable)
    primary = [row["paired"]["cmi_minus_control_best_downstream_utility"] for row in evaluable]
    auc = [row["paired"]["cmi_minus_control_anytime_auc"] for row in evaluable]
    family_positive = all(
        all(row["paired"]["outcome"] == "WIN" for row in evaluable if row["task_category"] == category)
        for category in {row["task_category"] for row in rows}
    )
    matched_calls = all(
        all(row["arms"][name]["provider_calls"] == DOWNSTREAM_GENERATIONS for name in ARM_NAMES)
        for row in rows
    )
    gate = {
        "all_five_states_evaluable": len(evaluable) == 5,
        "five_of_five_cmi_vs_control_primary_wins": wins == 5 and losses == 0,
        "each_family_all_primary_positive": family_positive and len(evaluable) == 5,
        "median_primary_delta_strictly_positive": bool(primary) and statistics.median(primary) > 0,
        "median_anytime_auc_delta_strictly_positive": bool(auc) and statistics.median(auc) > 0,
        "all_arms_exactly_two_provider_calls": matched_calls,
    }
    passed = all(gate.values())
    if len(evaluable) != 5 or not matched_calls:
        verdict = "CMI_FORCED_LINEAGE_R1_NOT_EVALUABLE"
        decision = "RETAIN_DIAGNOSTIC_EVIDENCE_AND_FIX_ONLY_VALIDITY_OR_EXECUTABILITY_BLOCKERS"
    elif passed:
        verdict = "CMI_STEPPING_STONE_SIGNAL_DETECTED_ON_CONSUMED_V3_STATES"
        decision = "NON_MYOPIC_ARCHIVE_PARENT_POLICY_DEV_HYPOTHESIS_AUTHORIZED_NO_FRESH_BUDGET"
    else:
        verdict = "CMI_FORCED_LINEAGE_VALUE_NOT_ESTABLISHED_ON_CONSUMED_V3_STATES"
        decision = "STOP_CMI_SEARCH_INTEGRATION_NO_FRESH_BUDGET_OR_SELECTION_TUNING"
    return {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest["manifest_digest"],
        "experiment_code_sha": manifest["experiment_code_sha"],
        "claim_ceiling": manifest["claim_ceiling"],
        "verdict": verdict,
        "decision": decision,
        "fresh_task_budget_consumed": 0,
        "selection_policy_changed": False,
        "generation_zero_counted_as_success": False,
        "paired_summary": {
            "evaluable": len(evaluable),
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "median_primary_delta": statistics.median(primary) if primary else None,
            "median_anytime_auc_delta": statistics.median(auc) if auc else None,
        },
        "success_gate": {**gate, "passed": passed},
        "tasks": rows,
    }


def _remaining_budget(usage: ResourceUsage) -> ResourceBudget:
    original = _search_value_remaining_budget(usage)
    return ResourceBudget(
        tokens=max(0, TOKEN_CEILING - usage.tokens),
        cpu_seconds=original.cpu_seconds,
        wall_seconds=max(0.0, WALL_CEILING - usage.wall_seconds),
    )


def _load_and_verify_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_json(path)
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("CMI forced-lineage manifest digest mismatch")
    repository = _repository_snapshot()
    if repository["head_commit"] != manifest["experiment_code_sha"] or not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI forced-lineage repository drift")
    source_root = Path(__file__).resolve().parents[1]
    for relative, expected in manifest["implementation_digests"].items():
        if digest_bytes((source_root / relative).read_bytes()) != expected:
            raise RuntimeError(f"CMI forced-lineage implementation drift: {relative}")
    frozen = manifest["provider"]
    if (
        provider.provider_name != frozen["name"]
        or provider.model != frozen["model"]
        or provider.provider_version != frozen["version"]
        or provider.reasoning_effort != frozen["reasoning_effort"]
        or provider.settings_digest != frozen["settings_digest"]
    ):
        raise RuntimeError("CMI forced-lineage provider/model/settings drift")
    return manifest


def _implementation_paths() -> tuple[Path, ...]:
    return (Path(__file__).resolve(), *_search_value_implementation_paths())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required JSON source missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON source is not an object: {path}")
    return value
