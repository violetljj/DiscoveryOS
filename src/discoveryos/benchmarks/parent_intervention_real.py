from __future__ import annotations

import ast
import concurrent.futures
import json
import math
import statistics
import subprocess
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from discoveryos.benchmarks.causal_intervention_bench import (
    BranchTrace,
    FrozenDecisionState,
    InterventionPair,
    InterventionThresholds,
    _pair_receipt,
    evaluate_intervention_pairs,
)
from discoveryos.benchmarks.local_patch_admission import _materialize_files
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import si2_discovery_tasks
from discoveryos.contracts.executable import ExecutableCandidateBundle
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import (
    GenerationKind,
    GenerationProviderError,
    GenerationRequest,
)
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CIB_R1_REAL_DOWNSTREAM_PARENT_V1"
MANIFEST_RECORD = "cib-r1-parent-real-manifest.json"
CALIBRATION_RECORD = "cib-r1-parent-real-calibration.json"
REPORT_RECORD = "cib-r1-parent-real-report.json"
SOURCE_MANIFEST_RECORD = "si2-sealed-pre-model-manifest.json"

# These are the actual SI-2 CURRENT receipts where Parent selected a
# non-incumbent.  The split is frozen by receipt identity, before CIB-R1 calls.
CALIBRATION_STATES = (
    ("capacitated_assignment_delta", 2, "parent_7d121011546fad854de8178a"),
    ("capacitated_assignment_eta", 1, "parent_ac9643bb247f143930e77d0e"),
)
VALIDATION_STATES = (
    ("balanced_cut_delta", 2, "parent_bf40812e096ca1a9690fcb1b"),
    ("budgeted_coverage_epsilon", 2, "parent_fa22c48b1d36cd075a5bd72f"),
    ("capacitated_assignment_epsilon", 2, "parent_d255e41ed55ee73c09b56b95"),
)
CALIBRATION_NULL_REPLICATES = 2
CALIBRATION_POSITIVE_REPLICATES = 2
VALIDATION_THRESHOLDS = InterventionThresholds(
    null_replicates=2,
    intervention_replicates=3,
    positive_replicates=2,
    minimum_validation_states=3,
    minimum_reproducible_states=2,
    behavioral_margin=0.01,  # replaced by the frozen calibration result
    utility_margin=0.005,  # replaced by the frozen calibration result
    efficiency_margin_tokens=500,
)
DESCENDANT_STEPS = 3
BRANCH_TOKEN_CEILING = 60_000
BRANCH_EVALUATOR_CALL_CEILING = DESCENDANT_STEPS
EXACT_SIGN_ALPHA = 0.10
MAX_POSITIVE_CONTRIBUTION_SHARE = 0.75

DESCENDANT_CHAIN_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["descendants"],
    "properties": {
        "descendants": {
            "type": "array",
            "minItems": DESCENDANT_STEPS,
            "maxItems": DESCENDANT_STEPS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hypothesis", "source"],
                "properties": {
                    "hypothesis": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "minLength": 1},
                },
            },
        }
    },
}


@dataclass(frozen=True, slots=True)
class GeneratedBranch:
    trace: BranchTrace
    evaluable: bool
    validity_rate: float
    replacement_rate: float
    wall_seconds: float
    generation: dict[str, Any]
    descendants: tuple[dict[str, Any], ...]


def seal_parent_real_cib_protocol(
    workspace: Path,
    *,
    source_workspace: Path,
    source_manifest_digest: str,
    provider: PatchProvider,
    max_workers: int = 2,
) -> dict[str, Any]:
    """Freeze actual consumed SI-2 interventions before any CIB-R1 call."""

    if max_workers < 1 or max_workers > 3:
        raise ValueError("CIB-R1 max_workers must be between one and three")
    version = getattr(provider, "provider_version", "unknown")
    if not version or version == "unknown":
        raise RuntimeError("CIB-R1 requires an executable provider with a reportable version")
    if getattr(provider, "output_schema", None) != DESCENDANT_CHAIN_SCHEMA:
        raise RuntimeError("CIB-R1 provider must use the frozen descendant-chain schema")

    workspace = workspace.resolve()
    source_workspace = source_workspace.resolve()
    source_manifest_path = (
        source_workspace / "protocol-artifacts" / "records" / SOURCE_MANIFEST_RECORD
    )
    source_manifest = _load_bound_json(source_manifest_path, source_manifest_digest)
    if source_manifest.get("status") != "SI2_SEALED_PRE_MODEL":
        raise RuntimeError("CIB-R1 source SI-2 manifest is not sealed pre-model")

    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    state_rows = []
    for role, specs in (("CALIBRATION", CALIBRATION_STATES), ("VALIDATION", VALIDATION_STATES)):
        for task_id, step, receipt_id in specs:
            state_rows.append(
                _freeze_actual_state(
                    protocol_store,
                    source_workspace,
                    task_id=task_id,
                    step=step,
                    receipt_id=receipt_id,
                    role=role,
                )
            )

    validation_categories = {
        row["task_category"] for row in state_rows if row["role"] == "VALIDATION"
    }
    if len(validation_categories) != 3:
        raise RuntimeError("CIB-R1 validation must span three task families")
    environment = _environment_snapshot(provider, max_workers=max_workers)
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_CALIBRATION",
        "scope": "CONSUMED_SI2_ACTUAL_PARENT_INTERVENTIONS_REAL_STOCHASTIC_DOWNSTREAM",
        "scientific_question": (
            "Holding state, budget, model, operator contract, randomness distribution, and evaluator fixed, "
            "does the parent-policy intervention causally improve the distribution of generated descendants?"
        ),
        "claim_ceiling": "REAL_PARENT_MECHANISM_CAUSAL_VALUE_ON_CONSUMED_DEV_STATES_ONLY",
        "model_calls_before_seal": 0,
        "fresh_task_budget_consumed": 0,
        "source_si2": {
            "workspace": str(source_workspace),
            "manifest_digest": source_manifest_digest,
            "manifest_file_sha256": digest_bytes(source_manifest_path.read_bytes()),
            "consumed_only": True,
        },
        "provider": {
            "name": provider.provider_name,
            "model": provider.model,
            "version": version,
            "settings_digest": getattr(provider, "settings_digest", ""),
            "output_schema_digest": digest_json(DESCENDANT_CHAIN_SCHEMA),
        },
        "operator_contract": {
            "id": "STRONG_AGENT_THREE_DESCENDANT_CHAIN_V1",
            "description": (
                "One isolated stochastic strong-model call emits three ordered full-source descendants; "
                "each descendant is executed by the original frozen task evaluator without feedback to the call."
            ),
            "descendant_steps": DESCENDANT_STEPS,
            "branch_token_ceiling": BRANCH_TOKEN_CEILING,
            "branch_evaluator_call_ceiling": BRANCH_EVALUATOR_CALL_CEILING,
            "prompt_template_digest": digest_json({"template": _prompt_template()}),
            "positive_control_prompt_template_digest": digest_json(
                {"template": _positive_prompt_template()}
            ),
            "positive_control_is_excluded_from_mechanism_value": True,
        },
        "calibration": {
            "state_count": len(CALIBRATION_STATES),
            "null_replicates": CALIBRATION_NULL_REPLICATES,
            "positive_replicates": CALIBRATION_POSITIVE_REPLICATES,
            "threshold_rule": {
                "behavioral_margin": "max(0.01, max calibration null behavior distance)",
                "utility_margin": "max(0.005, max validation task score resolution, max calibration null final abs delta)",
                "validation_blocked_unless_positive_detected_in_both_calibration_states": True,
            },
        },
        "validation_threshold_template": jsonable(VALIDATION_THRESHOLDS),
        "primary_paired_gate": {
            "one_sided_exact_sign_alpha": EXACT_SIGN_ALPHA,
            "minimum_beneficial_states": 2,
            "minimum_task_families": 2,
            "maximum_single_state_positive_contribution_share": MAX_POSITIVE_CONTRIBUTION_SHARE,
            "median_validity_rate_delta_minimum": 0.0,
            "median_replacement_rate_delta_minimum": 0.0,
            "all_branches_evaluable": True,
            "all_branch_resource_ceilings_respected": True,
        },
        "endpoints": [
            "descendant_validity_rate",
            "descendant_fitness_delta",
            "incumbent_replacement_rate",
            "one_to_three_step_descendant_best",
            "anytime_auc",
            "token_cost",
            "wall_cost",
        ],
        "states": state_rows,
        "execution_schedule": _execution_schedule(state_rows),
        "environment": environment,
        "implementation_bindings": _implementation_bindings(),
        "not_authorized": [
            "fresh-task search-value claim",
            "DiscoveryOS superiority claim",
            "production readiness claim",
            "SI-3 execution before this gate passes",
        ],
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = protocol_store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "calibration_states": len(CALIBRATION_STATES),
        "validation_states": len(VALIDATION_STATES),
        "planned_model_calls": _planned_model_calls(),
        "model_calls": 0,
        "fresh_task_budget_consumed": 0,
    }


def calibrate_parent_real_cib(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest, manifest_path = _load_manifest(workspace, manifest_digest, provider)
    calibration_path = workspace / "result-artifacts" / "records" / CALIBRATION_RECORD
    if calibration_path.exists():
        return _load_bound_json(calibration_path)
    rows = [row for row in manifest["states"] if row["role"] == "CALIBRATION"]
    schedule = [item for item in manifest["execution_schedule"] if item["phase"] == "CALIBRATION"]
    pairs, branches = _execute_schedule(
        workspace,
        manifest,
        rows,
        schedule,
        provider,
        progress=progress,
    )
    all_evaluable = all(branch.evaluable for branch in branches.values())
    null_behavior = []
    null_utility = []
    positive_by_state: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        effect = _pair_receipt(pair)["effect"]
        if pair.kind == "NULL":
            null_behavior.append(abs(float(effect["behavior_distance"])))
            null_utility.append(abs(float(effect["descendant_final_delta"])))
        else:
            positive_by_state.setdefault(pair.state.state_id, []).append(effect)
    task_map = {row["state"]["state_id"]: row for row in rows}
    sensitivity = {}
    for state_id, effects in positive_by_state.items():
        behavior = statistics.median(float(item["behavior_distance"]) for item in effects)
        utility = statistics.median(abs(float(item["descendant_final_delta"])) for item in effects)
        sensitivity[state_id] = {
            "behavior_distance": behavior,
            "absolute_descendant_final_delta": utility,
            "detected": behavior > max(null_behavior, default=0.0) + 0.01
            and utility
            > max(
                0.005,
                float(task_map[state_id]["score_resolution"]),
                max(null_utility, default=0.0),
            ),
        }
    calibration_passed = all_evaluable and len(sensitivity) == len(rows) and all(
        item["detected"] for item in sensitivity.values()
    )
    thresholds = {
        **jsonable(VALIDATION_THRESHOLDS),
        "behavioral_margin": max(0.01, max(null_behavior, default=0.0)),
        "utility_margin": max(
            0.005,
            max(float(row["score_resolution"]) for row in manifest["states"] if row["role"] == "VALIDATION"),
            max(null_utility, default=0.0),
        ),
    }
    result_store = ArtifactStore(workspace / "result-artifacts")
    pair_bindings = _write_pair_records(result_store, pairs, branches, "calibration-pairs")
    report_payload = {
        "status": "CIB_R1_CALIBRATION_PASSED" if calibration_passed else "CIB_R1_CALIBRATION_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "all_branches_evaluable": all_evaluable,
        "calibration_sensitivity": sensitivity,
        "frozen_validation_thresholds": thresholds,
        "model_calls": len(branches),
        "fresh_task_budget_consumed": 0,
        "validation_authorized": calibration_passed,
        "pair_receipts": pair_bindings,
        "manifest_file_sha256": digest_bytes(manifest_path.read_bytes()),
    }
    report = {**report_payload, "calibration_digest": digest_json(report_payload)}
    path = result_store.write_record(CALIBRATION_RECORD, report)
    return {**report, "calibration_path": str(path), "calibration_sha256": digest_bytes(path.read_bytes())}


def run_parent_real_cib(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest, manifest_path = _load_manifest(workspace, manifest_digest, provider)
    calibration_path = workspace / "result-artifacts" / "records" / CALIBRATION_RECORD
    calibration = _load_bound_json(calibration_path)
    calibration_payload = {
        key: value for key, value in calibration.items() if key != "calibration_digest"
    }
    if calibration.get("calibration_digest") != digest_json(calibration_payload):
        raise RuntimeError("CIB-R1 calibration digest mismatch")
    if calibration.get("manifest_digest") != manifest_digest:
        raise RuntimeError("CIB-R1 calibration is not bound to the sealed manifest")
    if not calibration.get("validation_authorized"):
        raise RuntimeError("CIB-R1 validation blocked because calibration did not establish sensitivity")
    thresholds = InterventionThresholds(**calibration["frozen_validation_thresholds"])
    rows = [row for row in manifest["states"] if row["role"] == "VALIDATION"]
    schedule = [item for item in manifest["execution_schedule"] if item["phase"] == "VALIDATION"]
    pairs, branches = _execute_schedule(
        workspace,
        manifest,
        rows,
        schedule,
        provider,
        progress=progress,
    )
    all_evaluable = all(branch.evaluable for branch in branches.values())
    resource_ok = all(
        branch.trace.token_cost <= BRANCH_TOKEN_CEILING
        and branch.trace.evaluator_cost <= BRANCH_EVALUATOR_CALL_CEILING
        for branch in branches.values()
    )
    analysis = evaluate_intervention_pairs(pairs, thresholds=thresholds)
    primary = _primary_gate(pairs, branches, analysis, all_evaluable, resource_ok)
    if not all_evaluable:
        verdict = "PARENT_REAL_DOWNSTREAM_NOT_EVALUABLE"
    elif not analysis["bench_sensitivity_established"]:
        verdict = "PARENT_REAL_DOWNSTREAM_BENCH_SENSITIVITY_NOT_ESTABLISHED"
    elif primary["passed"]:
        verdict = "REAL_PARENT_MECHANISM_CAUSAL_VALUE"
    else:
        verdict = "PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR"
    result_store = ArtifactStore(workspace / "result-artifacts")
    pair_bindings = _write_pair_records(result_store, pairs, branches, "validation-pairs")
    report = {
        "status": "CIB_R1_REAL_DOWNSTREAM_COMPLETE",
        "verdict": verdict,
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "calibration_sha256": digest_bytes(calibration_path.read_bytes()),
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": len(branches),
        "cumulative_model_calls_including_calibration": len(branches) + int(calibration["model_calls"]),
        "fresh_task_budget_consumed": 0,
        "all_branches_evaluable": all_evaluable,
        "resource_ceilings_respected": resource_ok,
        "paired_analysis": analysis,
        "primary_paired_causal_gate": primary,
        "real_parent_mechanism_admitted": verdict == "REAL_PARENT_MECHANISM_CAUSAL_VALUE",
        "si3_fresh_budget_decision": (
            "SI3_FRESH_BUDGET_ELIGIBLE_FOR_SEPARATE_PROTOCOL"
            if verdict == "REAL_PARENT_MECHANISM_CAUSAL_VALUE"
            else "DO_NOT_OPEN_SI3_FRESH_BUDGET"
        ),
        "pair_receipts": pair_bindings,
        "source_bindings": [
            {"role": "sealed_manifest", "path": str(manifest_path), "sha256": digest_bytes(manifest_path.read_bytes())},
            {"role": "calibration", "path": str(calibration_path), "sha256": digest_bytes(calibration_path.read_bytes())},
            *manifest["implementation_bindings"],
        ],
    }
    path = result_store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_actual_state(
    store: ArtifactStore,
    source_workspace: Path,
    *,
    task_id: str,
    step: int,
    receipt_id: str,
    role: str,
) -> dict[str, Any]:
    task_map = {item.task.task_id: item for item in si2_discovery_tasks()}
    task = task_map[task_id]
    arm_root = source_workspace / "arms" / "discovery" / task_id / "CURRENT_DISCOVERYOS"
    ledger_path = arm_root / "ledger.sqlite3"
    run_id = f"si2-{task_id}-current_discoveryos"
    with sqlite3.connect(f"file:{ledger_path.resolve()}?mode=ro", uri=True) as connection:
        receipt_rows = connection.execute(
            "SELECT payload FROM parent_selection_receipts WHERE run_id=? AND step=? AND receipt_id=?",
            (run_id, step, receipt_id),
        ).fetchall()
        receipts = [json.loads(item[0]) for item in receipt_rows]
    if len(receipts) != 1 or receipts[0].get("selected_is_incumbent") is not False:
        raise RuntimeError(f"CIB-R1 source intervention receipt mismatch: {task_id}:{step}")
    receipt = receipts[0]
    incumbent_id = str(receipt["incumbent_id"])
    selected_id = str(receipt["selected_parent_ids"][0])
    if incumbent_id == selected_id:
        raise RuntimeError("CIB-R1 source receipt does not change parent")
    artifact_store = ArtifactStore(arm_root / "artifacts")
    actions = {}
    for action_id in (incumbent_id, selected_id):
        with sqlite3.connect(f"file:{ledger_path.resolve()}?mode=ro", uri=True) as connection:
            candidate_row = connection.execute(
                "SELECT payload FROM candidates WHERE candidate_id=?", (action_id,)
            ).fetchone()
        if candidate_row is None:
            raise RuntimeError(f"CIB-R1 source candidate missing: {action_id}")
        candidate = json.loads(candidate_row[0])
        artifact_digest = str(candidate["artifact_digest"])
        bundle = ExecutableCandidateBundle.from_artifact(artifact_store, artifact_digest)
        source = normalized_source(_materialize_files(bundle, (bundle.entrypoint,))[bundle.entrypoint])
        actions[action_id] = {
            "source_artifact_digest": store.put_bytes(source.encode("utf-8"), media_type="text/x-python"),
            "source_sha256": digest_bytes(source.encode("utf-8")),
            "candidate_artifact_digest": artifact_digest,
        }
    positive_id = f"{task_id}:frozen-reference-positive-control"
    # The positive control is intentionally far from the incumbent and uses a
    # copy-through prompt.  It validates the real model -> source -> evaluator
    # observation chain; it is never counted as Parent value.
    positive_source = normalized_source(task.task.algorithm_source)
    actions[positive_id] = {
        "source_artifact_digest": store.put_bytes(positive_source.encode("utf-8"), media_type="text/x-python"),
        "source_sha256": digest_bytes(positive_source.encode("utf-8")),
        "candidate_artifact_digest": None,
    }
    task_files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
    }
    score_by_id = dict(zip(receipt["candidate_ids"], receipt["candidate_scores"], strict=True))
    state_payload = {
        "source_receipt": receipt,
        "actions": actions,
        "task_payload_digest": task.payload_digest,
        "task_files": task_files,
        "operator": "STRONG_AGENT_THREE_DESCENDANT_CHAIN_V1",
    }
    state = FrozenDecisionState(
        state_id=f"cib-r1-{task_id}-step-{step}",
        state_digest=digest_json(state_payload),
        mechanism_id="SI2_ACTUAL_SHINKA_WEIGHTED_PARENT_SELECTION",
        policy_id=str(receipt["policy_version"]),
        default_action_id=incumbent_id,
        intervention_action_id=selected_id,
        positive_action_id=positive_id,
        behavioral_probe_digest=digest_json(
            {"probe": "per-case-evaluator-scores-plus-ast-features-v1", "task_files": task_files}
        ),
        downstream_steps=DESCENDANT_STEPS,
        token_budget=BRANCH_TOKEN_CEILING,
        evaluator_call_budget=BRANCH_EVALUATOR_CALL_CEILING,
    )
    return {
        "role": role,
        "state": jsonable(state),
        "task_id": task_id,
        "task_category": task.task.category,
        "task_payload_digest": task.payload_digest,
        "score_resolution": task.score_resolution,
        "source_receipt": receipt,
        "source_receipt_digest": digest_json(receipt),
        "source_ledger_sha256": digest_bytes(ledger_path.read_bytes()),
        "actions": actions,
        "action_parent_scores": {
            incumbent_id: float(score_by_id[incumbent_id]),
            selected_id: float(score_by_id[selected_id]),
            positive_id: None,
        },
        "incumbent_score": float(score_by_id[incumbent_id]),
        "task_files": task_files,
    }


def _execution_schedule(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedule = []
    for row in rows:
        state = FrozenDecisionState(**row["state"])
        kinds = (
            (("NULL", CALIBRATION_NULL_REPLICATES), ("POSITIVE", CALIBRATION_POSITIVE_REPLICATES))
            if row["role"] == "CALIBRATION"
            else (
                ("NULL", VALIDATION_THRESHOLDS.null_replicates),
                ("INTERVENTION", VALIDATION_THRESHOLDS.intervention_replicates),
                ("POSITIVE", VALIDATION_THRESHOLDS.positive_replicates),
            )
        )
        for kind, count in kinds:
            for replicate in range(count):
                pair_id = f"{state.state_id}-{kind.casefold()}-{replicate}"
                treatment_action = {
                    "NULL": state.default_action_id,
                    "INTERVENTION": state.intervention_action_id,
                    "POSITIVE": state.positive_action_id,
                }[kind]
                order = ["control", "treatment"]
                if int(digest_json({"pair_id": pair_id, "order": "frozen"})[:2], 16) % 2:
                    order.reverse()
                schedule.append(
                    {
                        "phase": row["role"],
                        "state_id": state.state_id,
                        "pair_id": pair_id,
                        "kind": kind,
                        "replicate": replicate,
                        "control_action_id": state.default_action_id,
                        "treatment_action_id": treatment_action,
                        "branch_order": order,
                        "control_draw_id": f"{pair_id}:control",
                        "treatment_draw_id": f"{pair_id}:treatment",
                    }
                )
    return schedule


def _execute_schedule(
    workspace: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
    provider: PatchProvider,
    *,
    progress: Callable[[str], None] | None,
) -> tuple[list[InterventionPair], dict[str, GeneratedBranch]]:
    row_map = {row["state"]["state_id"]: row for row in rows}
    store = ArtifactStore(workspace / "protocol-artifacts")
    checkpoint_store = ArtifactStore(workspace / "result-artifacts")
    max_workers = int(manifest["environment"]["max_workers"])
    branch_results: dict[str, GeneratedBranch] = {}

    def run_pair(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, GeneratedBranch]]:
        row = row_map[item["state_id"]]
        local: dict[str, GeneratedBranch] = {}
        for side in item["branch_order"]:
            action_id = item[f"{side}_action_id"]
            draw_id = item[f"{side}_draw_id"]
            checkpoint_name = (
                f"branches/{item['phase'].casefold()}/"
                f"{digest_json({'manifest': manifest['manifest_digest'], 'draw': draw_id})}.json"
            )
            checkpoint_path = checkpoint_store.records / checkpoint_name
            if checkpoint_path.is_file():
                payload = _load_bound_json(checkpoint_path)
                if (
                    payload.get("manifest_digest") != manifest["manifest_digest"]
                    or payload.get("draw_id") != draw_id
                    or payload.get("action_id") != action_id
                    or payload.get("branch_digest")
                    != digest_json(payload.get("branch_result"))
                ):
                    raise RuntimeError("CIB-R1 branch checkpoint binding mismatch")
                local[side] = _branch_from_json(payload["branch_result"])
            else:
                branch = _generate_branch(store, row, action_id, draw_id, provider)
                branch_payload = jsonable(branch)
                checkpoint_store.write_record(
                    checkpoint_name,
                    {
                        "manifest_digest": manifest["manifest_digest"],
                        "draw_id": draw_id,
                        "action_id": action_id,
                        "branch_result": branch_payload,
                        "branch_digest": digest_json(branch_payload),
                    },
                )
                local[side] = branch
        return item, local

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_pair, item) for item in schedule]
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            item, local = future.result()
            for side, branch in local.items():
                branch_results[f"{item['pair_id']}:{side}"] = branch
            completed += 1
            if progress:
                progress(f"CIB-R1 {item['phase'].casefold()} pair {completed}/{len(schedule)} complete")

    pairs = []
    for item in schedule:
        row = row_map[item["state_id"]]
        state = FrozenDecisionState(**row["state"])
        pairs.append(
            InterventionPair(
                pair_id=item["pair_id"],
                kind=item["kind"],
                state=state,
                control=branch_results[f"{item['pair_id']}:control"].trace,
                treatment=branch_results[f"{item['pair_id']}:treatment"].trace,
            )
        )
    return pairs, branch_results


def _generate_branch(
    store: ArtifactStore,
    row: dict[str, Any],
    action_id: str,
    draw_id: str,
    provider: PatchProvider,
) -> GeneratedBranch:
    state = FrozenDecisionState(**row["state"])
    source = store.get_bytes(row["actions"][action_id]["source_artifact_digest"]).decode("utf-8")
    question = store.get_bytes(row["task_files"]["question"]).decode("utf-8")
    positive_control = action_id == state.positive_action_id
    prompt = (
        _positive_prompt_template().format(question=question, parent_source=source)
        if positive_control
        else _render_prompt(question, source)
    )
    request = GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider=provider.provider_name,
        model=provider.model,
        provider_settings_digest=getattr(provider, "settings_digest", ""),
        prompt_template_digest=digest_json(
            {"template": _positive_prompt_template() if positive_control else _prompt_template()}
        ),
        context_digest=digest_json({"state": state.state_digest, "action": action_id, "draw": draw_id}),
        prompt=prompt,
        token_ceiling=BRANCH_TOKEN_CEILING,
    )
    started = time.monotonic()
    try:
        generated = provider.generate(request)
        payload = json.loads(generated.raw_response)
        descendants = payload["descendants"]
        if len(descendants) != DESCENDANT_STEPS:
            raise ValueError("descendant chain length mismatch")
        sources = tuple(normalized_source(str(item["source"])) for item in descendants)
        evaluations = tuple(_evaluate_descendant(store, row, item) for item in sources)
        usage = generated.usage
        evaluable = not generated.refused
        generation = {
            "status": "SUCCEEDED" if evaluable else "REFUSED",
            "generation_id": request.generation_id,
            "provider_request_id": generated.provider_request_id,
            "provider_version": generated.provider_version,
            "raw_response_sha256": digest_bytes(generated.raw_response.encode("utf-8")),
            "transport_log_sha256": digest_bytes((generated.transport_log or "").encode("utf-8")),
            "usage": jsonable(usage),
            "latency_seconds": generated.latency_seconds,
        }
    except (GenerationProviderError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        usage = error.usage if isinstance(error, GenerationProviderError) and error.usage else ResourceUsage()
        evaluations = tuple(
            {"source_sha256": digest_json({"failed": draw_id, "step": step}), "score": 0.0, "valid": False,
             "probe_scores": [0.0] * 6, "ast_features": [0.0] * 6, "failure": type(error).__name__}
            for step in range(DESCENDANT_STEPS)
        )
        sources = tuple("" for _ in range(DESCENDANT_STEPS))
        evaluable = False
        generation = {
            "status": "PROVIDER_OR_SCHEMA_FAILURE",
            "generation_id": request.generation_id,
            "failure_signature": getattr(error, "signature", type(error).__name__),
            "usage": jsonable(usage),
            "latency_seconds": time.monotonic() - started,
        }
    scores = [float(item["score"]) for item in evaluations]
    cumulative_best = []
    for score in scores:
        cumulative_best.append(max((*cumulative_best, score)))
    behavior = tuple(
        value
        for item in evaluations
        for value in (*[float(v) for v in item["probe_scores"]], float(item["valid"]), *[float(v) for v in item["ast_features"]])
    )
    incumbent_score = float(row["incumbent_score"])
    valid_rate = statistics.fmean(float(item["valid"]) for item in evaluations)
    replacement_rate = statistics.fmean(
        float(bool(item["valid"]) and float(item["score"]) > incumbent_score + float(row["score_resolution"]) - 1e-12)
        for item in evaluations
    )
    trace = BranchTrace(
        state_id=state.state_id,
        action_id=action_id,
        draw_id=draw_id,
        proposal_semantics_digest=digest_json({"descendant_sources": [item["source_sha256"] for item in evaluations]}),
        behavioral_signature=behavior,
        immediate_fitness=scores[0],
        descendant_best=tuple(cumulative_best),
        anytime_auc=statistics.fmean(cumulative_best),
        token_cost=int(usage.tokens),
        evaluator_cost=DESCENDANT_STEPS,
    )
    return GeneratedBranch(
        trace=trace,
        evaluable=evaluable,
        validity_rate=valid_rate,
        replacement_rate=replacement_rate,
        wall_seconds=float(usage.wall_seconds),
        generation=generation,
        descendants=tuple(
            {**item, "source_artifact_digest": store.put_bytes(source.encode("utf-8"), media_type="text/x-python") if source else None}
            for item, source in zip(evaluations, sources, strict=True)
        ),
    )


def _evaluate_descendant(store: ArtifactStore, row: dict[str, Any], source: str) -> dict[str, Any]:
    public_tests = store.get_bytes(row["task_files"]["public_tests.py"]).decode("utf-8")
    evaluator = store.get_bytes(row["task_files"]["evaluate.py"]).decode("utf-8")
    with tempfile.TemporaryDirectory(prefix="discoveryos-cib-r1-eval-") as temporary:
        root = Path(temporary)
        (root / "algorithm.py").write_text(source, encoding="utf-8")
        (root / "public_tests.py").write_text(public_tests, encoding="utf-8")
        probe_evaluator = evaluator + "\nprint(json.dumps({'probe_scores': scores, 'probe_valid': bool(valid)}))\n"
        (root / "evaluate.py").write_text(probe_evaluator, encoding="utf-8")
        public = _run_python(root, "public_tests.py")
        evaluation = _run_python(root, "evaluate.py") if public.returncode == 0 else None
    valid = False
    score = 0.0
    probe_scores = [0.0] * 6
    failure = None
    if public.returncode != 0:
        failure = "PUBLIC_TEST_FAILED"
    elif evaluation is None or evaluation.returncode != 0:
        failure = "EVALUATOR_REJECTED_CANDIDATE"
    else:
        try:
            lines = [json.loads(line) for line in evaluation.stdout.splitlines() if line.strip()]
            metrics = lines[-2]["metrics"]
            probe = lines[-1]
            score = float(metrics["score"])
            valid = float(metrics["valid"]) == 1.0 and bool(probe["probe_valid"])
            probe_scores = [float(value) for value in probe["probe_scores"]]
            if len(probe_scores) != 6:
                raise ValueError("probe score shape mismatch")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            failure = "EVALUATOR_OUTPUT_INVALID"
            valid = False
            score = 0.0
            probe_scores = [0.0] * 6
    return {
        "source_sha256": digest_bytes(source.encode("utf-8")),
        "score": score if valid else 0.0,
        "valid": valid,
        "probe_scores": probe_scores if valid else [0.0] * 6,
        "ast_features": _ast_features(source),
        "failure": failure,
    }


def _run_python(root: Path, script: str) -> subprocess.CompletedProcess[str]:
    arguments = (str(Path(__file__).resolve().parents[3] / ".venv" / "Scripts" / "python.exe"), script)
    try:
        return subprocess.run(
            arguments,
            cwd=root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            arguments,
            124,
            stdout=error.stdout or "",
            stderr=error.stderr or "candidate evaluation timeout",
        )


def _ast_features(source: str) -> list[float]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [0.0] * 6
    kinds = (ast.For, ast.While, ast.If, ast.Call, ast.FunctionDef, ast.comprehension)
    return [min(1.0, sum(isinstance(node, kind) for node in ast.walk(tree)) / 50.0) for kind in kinds]


def _write_pair_records(
    store: ArtifactStore,
    pairs: Iterable[InterventionPair],
    branches: dict[str, GeneratedBranch],
    prefix: str,
) -> list[dict[str, str]]:
    bindings = []
    for pair in pairs:
        control = branches[f"{pair.pair_id}:control"]
        treatment = branches[f"{pair.pair_id}:treatment"]
        receipt = {
            **_pair_receipt(pair),
            "branch_details": {
                "control": jsonable(control),
                "treatment": jsonable(treatment),
            },
            "extended_effect": {
                "validity_rate_delta": treatment.validity_rate - control.validity_rate,
                "replacement_rate_delta": treatment.replacement_rate - control.replacement_rate,
                "wall_seconds_delta": treatment.wall_seconds - control.wall_seconds,
            },
        }
        path = store.write_record(f"{prefix}/{pair.pair_id}.json", receipt)
        bindings.append({"pair_id": pair.pair_id, "path": str(path), "sha256": digest_bytes(path.read_bytes())})
    return bindings


def _primary_gate(
    pairs: list[InterventionPair],
    branches: dict[str, GeneratedBranch],
    analysis: dict[str, Any],
    all_evaluable: bool,
    resource_ok: bool,
) -> dict[str, Any]:
    intervention_pairs = [pair for pair in pairs if pair.kind == "INTERVENTION"]
    deltas = [pair.treatment.descendant_best[-1] - pair.control.descendant_best[-1] for pair in intervention_pairs]
    positives = sum(delta > 0 for delta in deltas)
    negatives = sum(delta < 0 for delta in deltas)
    nonzero = positives + negatives
    sign_p = _one_sided_sign_p(positives, nonzero)
    validity_deltas = []
    replacement_deltas = []
    state_positive: dict[str, float] = {}
    for pair in intervention_pairs:
        control = branches[f"{pair.pair_id}:control"]
        treatment = branches[f"{pair.pair_id}:treatment"]
        validity_deltas.append(treatment.validity_rate - control.validity_rate)
        replacement_deltas.append(treatment.replacement_rate - control.replacement_rate)
        state_positive[pair.state.state_id] = state_positive.get(pair.state.state_id, 0.0) + max(
            0.0, pair.treatment.descendant_best[-1] - pair.control.descendant_best[-1]
        )
    total_positive = sum(state_positive.values())
    contribution_share = max(state_positive.values(), default=0.0) / total_positive if total_positive else 1.0
    checks = {
        "all_branches_evaluable": all_evaluable,
        "resource_ceilings_respected": resource_ok,
        "bench_sensitivity_established": bool(analysis["bench_sensitivity_established"]),
        "minimum_beneficial_states": int(analysis["intervention_beneficial_states"]) >= 2,
        "one_sided_exact_sign": nonzero > 0 and sign_p <= EXACT_SIGN_ALPHA,
        "median_descendant_final_delta_positive": statistics.median(deltas) > 0.0,
        "median_validity_rate_not_worse": statistics.median(validity_deltas) >= 0.0,
        "median_replacement_rate_not_worse": statistics.median(replacement_deltas) >= 0.0,
        "not_single_state_driven": contribution_share <= MAX_POSITIVE_CONTRIBUTION_SHARE,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "intervention_pair_count": len(intervention_pairs),
        "positive_pairs": positives,
        "negative_pairs": negatives,
        "ties": len(deltas) - nonzero,
        "one_sided_exact_sign_p": sign_p,
        "median_descendant_final_delta": statistics.median(deltas),
        "median_validity_rate_delta": statistics.median(validity_deltas),
        "median_replacement_rate_delta": statistics.median(replacement_deltas),
        "maximum_single_state_positive_contribution_share": contribution_share,
    }


def _one_sided_sign_p(positives: int, nonzero: int) -> float:
    if nonzero <= 0:
        return 1.0
    return sum(math.comb(nonzero, count) for count in range(positives, nonzero + 1)) / (2**nonzero)


def _branch_from_json(value: dict[str, Any]) -> GeneratedBranch:
    return GeneratedBranch(
        trace=BranchTrace(
            **{
                **value["trace"],
                "behavioral_signature": tuple(value["trace"]["behavioral_signature"]),
                "descendant_best": tuple(value["trace"]["descendant_best"]),
            }
        ),
        evaluable=bool(value["evaluable"]),
        validity_rate=float(value["validity_rate"]),
        replacement_rate=float(value["replacement_rate"]),
        wall_seconds=float(value["wall_seconds"]),
        generation=dict(value["generation"]),
        descendants=tuple(value["descendants"]),
    )


def _render_prompt(question: str, parent_source: str) -> str:
    return _prompt_template().format(question=question, parent_source=parent_source)


def _prompt_template() -> str:
    return (
        "You are a strong algorithm engineer operating under a frozen contract.\n"
        "Task:\n{question}\n\n"
        "Current parent algorithm.py:\n```python\n{parent_source}\n```\n\n"
        "Produce exactly three ordered descendant implementations. Each must be a complete algorithm.py, "
        "preserve the required function signature and constraints, use only the Python standard library, and "
        "remain practical at the stated scale. Treat descendant 2 as a refinement of descendant 1 and "
        "descendant 3 as a refinement of descendant 2. Do not include markdown fences in source fields."
    )


def _positive_prompt_template() -> str:
    return (
        "This is a frozen CIB sensitivity control, not a mechanism arm.\n"
        "Task:\n{question}\n\n"
        "Parent algorithm.py:\n```python\n{parent_source}\n```\n\n"
        "Return exactly three descendants. In every source field, copy the parent algorithm.py exactly, "
        "without markdown fences or any code change. Use a short hypothesis explaining that this is an "
        "intentional copy-through sensitivity control."
    )


def _environment_snapshot(provider: PatchProvider, *, max_workers: int) -> dict[str, Any]:
    import os
    import platform
    import shutil

    usage = shutil.disk_usage(Path.cwd().anchor)
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "free_disk_bytes_at_seal": usage.free,
        "max_workers": max_workers,
        "provider_version": getattr(provider, "provider_version", "unknown"),
    }


def _implementation_bindings() -> list[dict[str, str]]:
    import discoveryos.benchmarks.causal_intervention_bench as cib
    import discoveryos.benchmarks.si2_tasks as tasks
    import discoveryos.providers.codex_exec as provider

    return [
        {"role": role, "path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())}
        for role, path in (
            ("cib_r1_adapter", Path(__file__)),
            ("cib_core", Path(cib.__file__)),
            ("consumed_si2_tasks", Path(tasks.__file__)),
            ("codex_provider", Path(provider.__file__)),
        )
    ]


def _load_manifest(
    workspace: Path, expected_digest: str, provider: PatchProvider
) -> tuple[dict[str, Any], Path]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_bound_json(path, expected_digest)
    if manifest.get("status") != "SEALED_PRE_CALIBRATION" or manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("CIB-R1 manifest was not sealed before model calls")
    current = {item["role"]: item["sha256"] for item in _implementation_bindings()}
    frozen = {item["role"]: item["sha256"] for item in manifest["implementation_bindings"]}
    if current != frozen:
        raise RuntimeError("CIB-R1 implementation binding drift")
    expected = manifest["provider"]
    if (
        provider.provider_name != expected["name"]
        or provider.model != expected["model"]
        or getattr(provider, "provider_version", "unknown") != expected["version"]
        or getattr(provider, "settings_digest", "") != expected["settings_digest"]
        or digest_json(getattr(provider, "output_schema", {})) != expected["output_schema_digest"]
    ):
        raise RuntimeError("CIB-R1 provider/model/settings differ from the sealed manifest")
    return manifest, path


def _load_bound_json(path: Path, expected_digest: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required CIB-R1 artifact missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if expected_digest is not None:
        payload = {key: item for key, item in value.items() if key != "manifest_digest"}
        if value.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
            raise RuntimeError("CIB-R1 bound artifact digest mismatch")
    return value


def _planned_model_calls() -> int:
    calibration_pairs = len(CALIBRATION_STATES) * (
        CALIBRATION_NULL_REPLICATES + CALIBRATION_POSITIVE_REPLICATES
    )
    validation_pairs = len(VALIDATION_STATES) * (
        VALIDATION_THRESHOLDS.null_replicates
        + VALIDATION_THRESHOLDS.intervention_replicates
        + VALIDATION_THRESHOLDS.positive_replicates
    )
    return 2 * (calibration_pairs + validation_pairs)
