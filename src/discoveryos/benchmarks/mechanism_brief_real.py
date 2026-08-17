from __future__ import annotations

import ast
import concurrent.futures
import json
import math
import os
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from discoveryos.benchmarks.parent_intervention_real import _evaluate_descendant
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "GCF_R1_REAL_MECHANISM_BRIEF_V1"
SOURCE_PROTOCOL_ID = "CIB_R1_REAL_DOWNSTREAM_PARENT_V1"
SOURCE_MANIFEST_RECORD = "cib-r1-parent-real-manifest.json"
MANIFEST_RECORD = "gcf-r1-mechanism-brief-manifest.json"
CALIBRATION_RECORD = "gcf-r1-mechanism-brief-calibration.json"
REPORT_RECORD = "gcf-r1-mechanism-brief-report.json"
STAGES = ("PROPOSAL", "IMPLEMENTATION", "REPAIR", "FINAL")
CONDITION_A = "CONSTRUCTIVE_GREEDY"
CONDITION_B = "ITERATIVE_LOCAL_IMPROVEMENT"
NULL_REPLICATES = 2
CALIBRATION_INTERVENTION_REPLICATES = 2
VALIDATION_INTERVENTION_REPLICATES = 3
MINIMUM_VALIDATION_STATES = 2
STAGE_MARGIN = 0.05
BEHAVIOR_MARGIN = 0.02
BRANCH_TOKEN_CEILING = 50_000
MAX_WORKERS = 2


MECHANISM_BRIEFS = {
    CONDITION_A: (
        "Use a constructive greedy mechanism. Build the complete feasible solution in one forward "
        "selection pass using a deterministic marginal-gain or marginal-cost priority. Do not perform "
        "post-construction swaps, local-improvement iterations, backtracking, dynamic programming, or "
        "exhaustive enumeration. Repair may restore feasibility but must not become an optimization loop."
    ),
    CONDITION_B: (
        "Use iterative local improvement. Start from a feasible seed, then repeatedly evaluate a bounded "
        "neighborhood and apply an improving swap, add-remove, reassignment, or partition move until no "
        "improving move remains or a deterministic iteration bound is reached. A real post-construction "
        "improvement loop is required; do not stop after a single constructive greedy pass."
    ),
}


STAGED_GENERATION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["proposal", "implementation_source", "repair_source", "final_source"],
    "properties": {
        "proposal": {"type": "string", "minLength": 1},
        "implementation_source": {"type": "string", "minLength": 1},
        "repair_source": {"type": "string", "minLength": 1},
        "final_source": {"type": "string", "minLength": 1},
    },
}


@dataclass(frozen=True, slots=True)
class GeneratedConditionBranch:
    state_id: str
    condition_id: str
    draw_id: str
    stage_signatures: tuple[tuple[str, tuple[float, ...]], ...]
    behavior_signature: tuple[float, ...]
    utility: float
    valid: bool
    evaluable: bool
    token_cost: int
    wall_seconds: float
    generation: dict[str, Any]
    stages: tuple[dict[str, Any], ...]


def seal_mechanism_brief_protocol(
    workspace: Path,
    *,
    source_workspace: Path,
    source_manifest_digest: str,
    provider: PatchProvider,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    """Freeze the first real GCF diagnosis before any model output is observed."""

    if max_workers < 1 or max_workers > 3:
        raise ValueError("GCF-R1 max_workers must be between one and three")
    provider_version = getattr(provider, "provider_version", "unknown")
    if not provider_version or provider_version == "unknown":
        raise RuntimeError("GCF-R1 requires a provider with a reportable version")
    if getattr(provider, "output_schema", None) != STAGED_GENERATION_SCHEMA:
        raise RuntimeError("GCF-R1 provider must use the frozen staged-generation schema")

    workspace = workspace.resolve()
    source_workspace = source_workspace.resolve()
    source_manifest_path = source_workspace / "protocol-artifacts" / "records" / SOURCE_MANIFEST_RECORD
    source_manifest = _load_json(source_manifest_path, source_manifest_digest)
    if source_manifest.get("protocol_id") != SOURCE_PROTOCOL_ID:
        raise RuntimeError("GCF-R1 source is not the frozen CIB-R1 protocol")
    source_report_path = source_workspace / "result-artifacts" / "records" / "cib-r1-parent-real-report.json"
    if not source_report_path.is_file():
        raise RuntimeError("GCF-R1 requires the completed CIB-R1 report")
    source_report = _load_json(source_report_path)
    if source_report.get("verdict") != "PARENT_INTERVENTION_VALUE_NOT_ESTABLISHED_UNDER_STRONG_STOCHASTIC_GENERATOR":
        raise RuntimeError("GCF-R1 source Parent settlement is not complete")

    source_store = ArtifactStore(source_workspace / "protocol-artifacts")
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    rows = [_freeze_state(protocol_store, source_store, row) for row in source_manifest["states"]]
    if sum(row["role"] == "CALIBRATION" for row in rows) != 2:
        raise RuntimeError("GCF-R1 requires two outcome-blind calibration states")
    validation = [row for row in rows if row["role"] == "VALIDATION"]
    if len(validation) != 3 or len({row["task_category"] for row in validation}) != 3:
        raise RuntimeError("GCF-R1 validation must span three task families")

    schedule = _schedule(rows)
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_CALIBRATION",
        "scope": "CONSUMED_CIB_R1_STATES_REAL_MECHANISM_BRIEF_TRANSMISSION_ONLY",
        "scientific_question": (
            "Holding task, base source, model, prompt, budget, evaluator, and stochastic distribution fixed, "
            "does changing only the mechanism brief produce stagewise structural and hidden-behavior "
            "separation beyond same-condition stochastic null?"
        ),
        "claim_ceiling": "REAL_MECHANISM_BRIEF_SEMANTIC_TRANSMISSION_ON_CONSUMED_DEV_STATES_ONLY",
        "model_calls_before_seal": 0,
        "fresh_task_budget_consumed": 0,
        "source_cib_r1": {
            "workspace": str(source_workspace),
            "manifest_digest": source_manifest_digest,
            "manifest_file_sha256": digest_bytes(source_manifest_path.read_bytes()),
            "report_sha256": digest_bytes(source_report_path.read_bytes()),
            "consumed_only": True,
        },
        "provider": {
            "name": provider.provider_name,
            "model": provider.model,
            "version": provider_version,
            "settings_digest": getattr(provider, "settings_digest", ""),
            "output_schema_digest": digest_json(STAGED_GENERATION_SCHEMA),
        },
        "generation_contract": {
            "id": "STAGED_PROPOSAL_IMPLEMENTATION_REPAIR_FINAL_V1",
            "prompt_template_digest": digest_json({"template": _prompt_template()}),
            "branch_token_ceiling": BRANCH_TOKEN_CEILING,
            "separate_provider_request_per_branch": True,
            "no_evaluator_feedback_inside_branch": True,
        },
        "conditions": MECHANISM_BRIEFS,
        "single_variable_intervention": {
            "changed": "mechanism_brief",
            "held_fixed": [
                "task_question",
                "base_parent_source",
                "failure_context",
                "model_and_settings",
                "prompt_template",
                "token_ceiling",
                "evaluator",
            ],
        },
        "measurement": {
            "stages": list(STAGES),
            "stage_signature": "deterministic lexical-plus-Python-AST mechanism feature vector",
            "behavior_signature": "frozen six-instance task probe scores plus validity",
            "utility_recorded_but_not_used_for_gcf2": True,
            "stage_margin": STAGE_MARGIN,
            "behavior_margin": BEHAVIOR_MARGIN,
            "null_envelope": "maximum absolute A/A or B/B pair distance within state",
            "state_effect": "median A/B pair distance",
        },
        "calibration_gate": {
            "states": 2,
            "null_replicates_per_condition": NULL_REPLICATES,
            "intervention_replicates": CALIBRATION_INTERVENTION_REPLICATES,
            "minimum_proposal_detectable_states": 2,
            "validation_blocked_if_failed": True,
            "margins_are_predeclared_not_fit_to_intervention": True,
        },
        "validation_gate": {
            "states": 3,
            "minimum_reproducible_states": MINIMUM_VALIDATION_STATES,
            "null_replicates_per_condition": NULL_REPLICATES,
            "intervention_replicates": VALIDATION_INTERVENTION_REPLICATES,
            "gcf2_requires": [
                "final_stage_separation_in_at_least_two_states",
                "hidden_behavior_separation_in_at_least_two_states",
                "all_branches_evaluable_and_within_resource_ceiling",
            ],
        },
        "states": rows,
        "execution_schedule": schedule,
        "planned_model_calls": sum(2 for _ in schedule),
        "environment": _environment_snapshot(provider_version, max_workers),
        "implementation_bindings": _implementation_bindings(),
        "not_authorized": [
            "fresh task access",
            "search-value or superiority claim",
            "mechanism utility admission",
            "SI-3 execution",
            "post-result prompt, margin, state, or brief tuning",
        ],
        "fresh_budget_authorized": False,
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = protocol_store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "planned_model_calls": manifest["planned_model_calls"],
        "fresh_task_budget_consumed": 0,
    }


def calibrate_mechanism_brief(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, provider)
    schedule = [item for item in manifest["execution_schedule"] if item["phase"] == "CALIBRATION"]
    branches = _execute_schedule(workspace, manifest, schedule, provider, progress=progress)
    analysis = _analyze(manifest, schedule, branches)
    all_evaluable = all(branch.evaluable for branch in branches.values())
    all_final_valid = all(branch.valid for branch in branches.values())
    resource_ok = all(branch.token_cost <= BRANCH_TOKEN_CEILING for branch in branches.values())
    proposal_states = int(analysis["detectable_states_by_stage"]["PROPOSAL"])
    passed = all_evaluable and resource_ok and proposal_states == 2
    record = {
        "status": "GCF_R1_CALIBRATION_PASSED" if passed else "GCF_R1_CALIBRATION_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "passed": passed,
        "all_branches_evaluable": all_evaluable,
        "all_final_sources_valid": all_final_valid,
        "resource_ceilings_respected": resource_ok,
        "proposal_detectable_states": proposal_states,
        "analysis": analysis,
        "branch_bindings": _branch_bindings(workspace, schedule),
        "model_calls": len(branches),
        "usage": _usage(branches.values()),
        "fresh_task_budget_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(CALIBRATION_RECORD, record)
    return {**record, "calibration_path": str(path), "calibration_sha256": digest_bytes(path.read_bytes())}


def run_mechanism_brief_validation(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, provider)
    calibration_path = workspace / "result-artifacts" / "records" / CALIBRATION_RECORD
    calibration = _load_json(calibration_path)
    if calibration.get("manifest_digest") != manifest_digest or not calibration.get("passed"):
        raise RuntimeError("GCF-R1 validation blocked because frozen calibration did not pass")
    schedule = [item for item in manifest["execution_schedule"] if item["phase"] == "VALIDATION"]
    branches = _execute_schedule(workspace, manifest, schedule, provider, progress=progress)
    analysis = _analyze(manifest, schedule, branches)
    all_evaluable = all(branch.evaluable for branch in branches.values())
    all_final_valid = all(branch.valid for branch in branches.values())
    resource_ok = all(branch.token_cost <= BRANCH_TOKEN_CEILING for branch in branches.values())
    counts = analysis["detectable_states_by_stage"]
    behavior_count = int(analysis["behavior_changed_states"])
    semantic = (
        all_evaluable
        and all_final_valid
        and resource_ok
        and int(counts["FINAL"]) >= MINIMUM_VALIDATION_STATES
        and behavior_count >= MINIMUM_VALIDATION_STATES
    )
    verdict = _verdict(counts, behavior_count, all_evaluable, all_final_valid, resource_ok)
    total_model_calls = int(calibration["model_calls"]) + len(branches)
    report = {
        "status": "GCF_R1_REAL_MECHANISM_BRIEF_COMPLETE",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "calibration_sha256": digest_bytes(calibration_path.read_bytes()),
        "verdict": verdict,
        "mechanism_brief_semantic_transmission_detected": semantic,
        "real_channel_admitted": "MECHANISM_BRIEF" if semantic else None,
        "search_value_established": False,
        "fresh_value_trial_authorized": False,
        "all_branches_evaluable": all_evaluable,
        "all_final_sources_valid": all_final_valid,
        "resource_ceilings_respected": resource_ok,
        "analysis": analysis,
        "branch_bindings": _branch_bindings(workspace, schedule),
        "model_calls": total_model_calls,
        "validation_model_calls": len(branches),
        "usage": _combine_usage(calibration["usage"], _usage(branches.values())),
        "fresh_task_budget_consumed": 0,
        "claim_ceiling": manifest["claim_ceiling"],
        "next_budget_decision": (
            "ELIGIBLE_TO_PREREGISTER_INDEPENDENT_GCF3_VALUE_TRIAL"
            if semantic
            else "DO_NOT_OPEN_FRESH_VALUE_TRIAL"
        ),
        "source_bindings": [
            {
                "role": "sealed_manifest",
                "path": str(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD),
                "sha256": digest_bytes((workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_bytes()),
            },
            {"role": "implementation", "path": str(Path(__file__).resolve()), "sha256": digest_bytes(Path(__file__).read_bytes())},
        ],
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_state(
    target: ArtifactStore, source: ArtifactStore, row: dict[str, Any]
) -> dict[str, Any]:
    incumbent_id = row["state"]["default_action_id"]
    copied_files = {}
    for name, digest in row["task_files"].items():
        copied_files[name] = target.put_bytes(source.get_bytes(digest), media_type="text/plain")
    base_digest = target.put_bytes(
        source.get_bytes(row["actions"][incumbent_id]["source_artifact_digest"]),
        media_type="text/x-python",
    )
    return {
        "state_id": f"gcf-r1-{row['task_id']}",
        "role": row["role"],
        "task_id": row["task_id"],
        "task_category": row["task_category"],
        "state_digest": digest_json(
            {
                "source_state": row["state"]["state_digest"],
                "base_source": base_digest,
                "conditions": MECHANISM_BRIEFS,
            }
        ),
        "source_state_digest": row["state"]["state_digest"],
        "base_source_digest": base_digest,
        "task_files": copied_files,
        "incumbent_score": row["incumbent_score"],
        "score_resolution": row["score_resolution"],
        "probe_bindings": {
            "stage_signature": digest_json({"function": "_stage_signature", "version": 1}),
            "behavior": row["state"]["behavioral_probe_digest"],
            "utility_evaluator": row["task_files"]["evaluate.py"],
        },
    }


def _schedule(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedule = []
    for row in rows:
        intervention_count = (
            CALIBRATION_INTERVENTION_REPLICATES
            if row["role"] == "CALIBRATION"
            else VALIDATION_INTERVENTION_REPLICATES
        )
        kinds = (("NULL_A", NULL_REPLICATES), ("NULL_B", NULL_REPLICATES), ("INTERVENTION", intervention_count))
        for kind, count in kinds:
            for replicate in range(count):
                control_condition, treatment_condition = {
                    "NULL_A": (CONDITION_A, CONDITION_A),
                    "NULL_B": (CONDITION_B, CONDITION_B),
                    "INTERVENTION": (CONDITION_A, CONDITION_B),
                }[kind]
                pair_id = f"{row['state_id']}-{kind.casefold().replace('_', '-')}-{replicate}"
                order = ["control", "treatment"]
                if int(digest_json({"pair": pair_id, "order": 1})[:8], 16) % 2:
                    order.reverse()
                schedule.append(
                    {
                        "phase": row["role"],
                        "state_id": row["state_id"],
                        "pair_id": pair_id,
                        "kind": kind,
                        "replicate": replicate,
                        "control_condition": control_condition,
                        "treatment_condition": treatment_condition,
                        "control_draw_id": f"{pair_id}:control",
                        "treatment_draw_id": f"{pair_id}:treatment",
                        "branch_order": order,
                    }
                )
    return schedule


def _execute_schedule(
    workspace: Path,
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    provider: PatchProvider,
    *,
    progress: Callable[[str], None] | None,
) -> dict[str, GeneratedConditionBranch]:
    rows = {row["state_id"]: row for row in manifest["states"]}
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    result_store = ArtifactStore(workspace / "result-artifacts")

    def run_pair(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, GeneratedConditionBranch]]:
        local = {}
        row = rows[item["state_id"]]
        for side in item["branch_order"]:
            condition = item[f"{side}_condition"]
            draw_id = item[f"{side}_draw_id"]
            record = f"branches/{item['phase'].casefold()}/{digest_json({'manifest': manifest['manifest_digest'], 'draw': draw_id})}.json"
            path = result_store.records / record
            if path.is_file():
                saved = _load_json(path)
                if (
                    saved.get("manifest_digest") != manifest["manifest_digest"]
                    or saved.get("draw_id") != draw_id
                    or saved.get("condition_id") != condition
                    or saved.get("branch_digest") != digest_json(saved.get("branch"))
                ):
                    raise RuntimeError("GCF-R1 branch checkpoint binding mismatch")
                local[side] = _branch_from_json(saved["branch"])
            else:
                branch = _generate_branch(protocol_store, row, condition, draw_id, provider)
                body = jsonable(branch)
                result_store.write_record(
                    record,
                    {
                        "manifest_digest": manifest["manifest_digest"],
                        "draw_id": draw_id,
                        "condition_id": condition,
                        "branch": body,
                        "branch_digest": digest_json(body),
                    },
                )
                local[side] = branch
        return item, local

    branches: dict[str, GeneratedConditionBranch] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(manifest["environment"]["max_workers"])) as executor:
        futures = [executor.submit(run_pair, item) for item in schedule]
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            item, local = future.result()
            for side, branch in local.items():
                branches[f"{item['pair_id']}:{side}"] = branch
            completed += 1
            if progress:
                progress(f"GCF-R1 {item['phase'].casefold()} pair {completed}/{len(schedule)} complete")
    return branches


def _generate_branch(
    store: ArtifactStore,
    row: dict[str, Any],
    condition: str,
    draw_id: str,
    provider: PatchProvider,
) -> GeneratedConditionBranch:
    question = store.get_bytes(row["task_files"]["question"]).decode("utf-8")
    base_source = store.get_bytes(row["base_source_digest"]).decode("utf-8")
    prompt = _prompt_template().format(
        question=question,
        base_source=base_source,
        mechanism_brief=MECHANISM_BRIEFS[condition],
    )
    request = GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider=provider.provider_name,
        model=provider.model,
        provider_settings_digest=getattr(provider, "settings_digest", ""),
        prompt_template_digest=digest_json({"template": _prompt_template()}),
        context_digest=digest_json({"state": row["state_digest"], "condition": condition, "draw": draw_id}),
        prompt=prompt,
        token_ceiling=BRANCH_TOKEN_CEILING,
    )
    started = time.monotonic()
    try:
        generated = provider.generate(request)
        payload = json.loads(generated.raw_response)
        proposal = str(payload["proposal"])
        sources = [str(payload[name]) for name in ("implementation_source", "repair_source", "final_source")]
        evaluations = [_evaluate_descendant(store, row, source) for source in sources]
        evaluable = not generated.refused
        usage = generated.usage
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
        proposal = ""
        sources = ["", "", ""]
        evaluations = [
            {"score": 0.0, "valid": False, "probe_scores": [0.0] * 6, "ast_features": [0.0] * 6, "failure": type(error).__name__}
            for _ in sources
        ]
        evaluable = False
        generation = {
            "status": "PROVIDER_OR_SCHEMA_FAILURE",
            "generation_id": request.generation_id,
            "failure_signature": getattr(error, "signature", type(error).__name__),
            "usage": jsonable(usage),
            "latency_seconds": time.monotonic() - started,
        }
    stage_signatures = (
        ("PROPOSAL", tuple(_text_signature(proposal))),
        ("IMPLEMENTATION", tuple(_source_signature(sources[0]))),
        ("REPAIR", tuple(_source_signature(sources[1]))),
        ("FINAL", tuple(_source_signature(sources[2]))),
    )
    final = evaluations[-1]
    behavior = tuple([float(value) for value in final["probe_scores"]] + [float(final["valid"])])
    stages = (
        {"stage": "PROPOSAL", "text_sha256": digest_bytes(proposal.encode("utf-8")), "signature": list(stage_signatures[0][1])},
        *(
            {
                "stage": stage,
                "source_sha256": digest_bytes(source.encode("utf-8")),
                "source_artifact_digest": store.put_bytes(source.encode("utf-8"), media_type="text/x-python") if source else None,
                "signature": list(signature),
                "evaluation": evaluation,
            }
            for stage, source, (_, signature), evaluation in zip(
                STAGES[1:], sources, stage_signatures[1:], evaluations, strict=True
            )
        ),
    )
    return GeneratedConditionBranch(
        state_id=row["state_id"],
        condition_id=condition,
        draw_id=draw_id,
        stage_signatures=stage_signatures,
        behavior_signature=behavior,
        utility=float(final["score"]),
        valid=bool(final["valid"]),
        evaluable=evaluable,
        token_cost=int(usage.tokens),
        wall_seconds=float(usage.wall_seconds),
        generation=generation,
        stages=tuple(stages),
    )


def _analyze(
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    branches: dict[str, GeneratedConditionBranch],
) -> dict[str, Any]:
    rows = {row["state_id"]: row for row in manifest["states"]}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    pair_rows = []
    for item in schedule:
        control = branches[f"{item['pair_id']}:control"]
        treatment = branches[f"{item['pair_id']}:treatment"]
        effect = _effect(control, treatment)
        grouped.setdefault(item["state_id"], {}).setdefault(item["kind"], []).append(effect)
        pair_rows.append({"pair_id": item["pair_id"], "state_id": item["state_id"], "kind": item["kind"], "effect": effect})
    state_results = []
    for state_id, by_kind in sorted(grouped.items()):
        nulls = by_kind["NULL_A"] + by_kind["NULL_B"]
        interventions = by_kind["INTERVENTION"]
        null_stage = {stage: max(effect["stage_distance"][stage] for effect in nulls) for stage in STAGES}
        null_behavior = max(effect["behavior_distance"] for effect in nulls)
        intervention_stage = {
            stage: statistics.median(effect["stage_distance"][stage] for effect in interventions)
            for stage in STAGES
        }
        intervention_behavior = statistics.median(effect["behavior_distance"] for effect in interventions)
        utility_delta = statistics.median(effect["utility_delta"] for effect in interventions)
        stage_detectable = {
            stage: intervention_stage[stage] > null_stage[stage] + STAGE_MARGIN for stage in STAGES
        }
        behavior_changed = intervention_behavior > null_behavior + BEHAVIOR_MARGIN
        state_results.append(
            {
                "state_id": state_id,
                "task_id": rows[state_id]["task_id"],
                "task_category": rows[state_id]["task_category"],
                "null_envelope": {"stage_distance": null_stage, "behavior_distance": null_behavior},
                "intervention_effect": {
                    "stage_distance": intervention_stage,
                    "behavior_distance": intervention_behavior,
                    "utility_delta_record_only": utility_delta,
                },
                "stage_detectable": stage_detectable,
                "behavior_changed": behavior_changed,
            }
        )
    counts = {stage: sum(state["stage_detectable"][stage] for state in state_results) for stage in STAGES}
    return {
        "detectable_states_by_stage": counts,
        "behavior_changed_states": sum(state["behavior_changed"] for state in state_results),
        "condition_survival_curve": [counts[stage] for stage in STAGES],
        "states": state_results,
        "pairs": pair_rows,
    }


def _effect(control: GeneratedConditionBranch, treatment: GeneratedConditionBranch) -> dict[str, Any]:
    return {
        "stage_distance": {
            stage: math.dist(control_signature, treatment_signature)
            for (stage, control_signature), (_, treatment_signature) in zip(
                control.stage_signatures, treatment.stage_signatures, strict=True
            )
        },
        "behavior_distance": math.dist(control.behavior_signature, treatment.behavior_signature),
        "utility_delta": treatment.utility - control.utility,
        "validity_delta": float(treatment.valid) - float(control.valid),
    }


def _text_signature(text: str) -> list[float]:
    lowered = text.casefold()
    greedy = ("greedy", "constructive", "marginal", "single pass", "priority")
    local = ("local", "swap", "neighborhood", "improving move", "iteration")
    return [
        min(1.0, sum(lowered.count(token) for token in greedy) / 5.0),
        min(1.0, sum(lowered.count(token) for token in local) / 5.0),
        min(1.0, len(text) / 2000.0),
    ]


def _source_signature(source: str) -> list[float]:
    lowered = source.casefold()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [0.0] * 9
    nodes = list(ast.walk(tree))
    loops = [node for node in nodes if isinstance(node, (ast.For, ast.While))]
    while_count = sum(isinstance(node, ast.While) for node in nodes)
    break_count = sum(isinstance(node, ast.Break) for node in nodes)
    max_depth = _loop_depth(tree)
    greedy_words = sum(lowered.count(token) for token in ("greedy", "marginal", "priority", "ratio"))
    local_words = sum(lowered.count(token) for token in ("swap", "local", "improv", "neighbor", "delta"))
    return [
        min(1.0, len(loops) / 12.0),
        min(1.0, while_count / 3.0),
        min(1.0, break_count / 3.0),
        min(1.0, max_depth / 4.0),
        min(1.0, greedy_words / 8.0),
        min(1.0, local_words / 8.0),
        min(1.0, sum(isinstance(node, ast.If) for node in nodes) / 20.0),
        min(1.0, sum(isinstance(node, ast.FunctionDef) for node in nodes) / 8.0),
        min(1.0, len(source) / 12_000.0),
    ]


def _loop_depth(tree: ast.AST) -> int:
    maximum = 0

    def visit(node: ast.AST, depth: int) -> None:
        nonlocal maximum
        next_depth = depth + 1 if isinstance(node, (ast.For, ast.While)) else depth
        maximum = max(maximum, next_depth)
        for child in ast.iter_child_nodes(node):
            visit(child, next_depth)

    visit(tree, 0)
    return maximum


def _verdict(
    counts: dict[str, int],
    behavior_count: int,
    all_evaluable: bool,
    all_final_valid: bool,
    resource_ok: bool,
) -> str:
    if not all_evaluable or not resource_ok:
        return "GCF_R1_NOT_EVALUABLE"
    if not all_final_valid:
        return "MECHANISM_BRIEF_RESPONSE_NOT_SEMANTICALLY_VALID"
    if counts["PROPOSAL"] < MINIMUM_VALIDATION_STATES:
        return "MECHANISM_BRIEF_NOT_DETECTABLE_AT_PROPOSAL"
    if counts["IMPLEMENTATION"] < MINIMUM_VALIDATION_STATES:
        return "MECHANISM_BRIEF_PROPOSAL_TO_IMPLEMENTATION_FAILED"
    if counts["REPAIR"] < MINIMUM_VALIDATION_STATES:
        return "MECHANISM_BRIEF_REPAIR_HOMOGENIZATION_DETECTED"
    if counts["FINAL"] < MINIMUM_VALIDATION_STATES:
        return "MECHANISM_BRIEF_FINAL_SURVIVAL_NOT_ESTABLISHED"
    if behavior_count < MINIMUM_VALIDATION_STATES:
        return "MECHANISM_BRIEF_STRUCTURAL_RESPONSE_WITHOUT_BEHAVIOR_TRANSMISSION"
    return "MECHANISM_BRIEF_SEMANTIC_TRANSMISSION_DETECTED"


def _prompt_template() -> str:
    return (
        "You are executing a frozen generator-conditioning diagnostic. Only the MECHANISM BRIEF changes "
        "between experimental branches. Follow it materially, not just in prose.\n\n"
        "TASK:\n{question}\n\n"
        "FIXED BASE algorithm.py:\n```python\n{base_source}\n```\n\n"
        "MECHANISM BRIEF:\n{mechanism_brief}\n\n"
        "Return four fields. proposal is a concrete plan. implementation_source is the first complete "
        "algorithm.py implementing that plan. repair_source is a complete corrected version after checking "
        "the task constraints and likely edge cases. final_source is the complete normalized final version. "
        "All sources must preserve the required API, use only the Python standard library, and contain no "
        "markdown fences. Do not mention this experiment or add inert marker code."
    )


def _load_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_json(path, expected_digest)
    if manifest.get("status") != "SEALED_PRE_CALIBRATION":
        raise RuntimeError("GCF-R1 manifest was not sealed before model calls")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("GCF-R1 implementation binding drift")
    expected_provider = manifest["provider"]
    actual = {
        "name": provider.provider_name,
        "model": provider.model,
        "version": getattr(provider, "provider_version", "unknown"),
        "settings_digest": getattr(provider, "settings_digest", ""),
        "output_schema_digest": digest_json(getattr(provider, "output_schema", None)),
    }
    if actual != expected_provider:
        raise RuntimeError("GCF-R1 provider/model/settings differ from sealed manifest")
    return manifest


def _load_json(path: Path, expected_digest: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required GCF-R1 artifact missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if expected_digest is not None:
        payload = {key: item for key, item in value.items() if key != "manifest_digest"}
        if value.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
            raise RuntimeError("sealed GCF-R1 manifest digest mismatch")
    return value


def _branch_from_json(value: dict[str, Any]) -> GeneratedConditionBranch:
    return GeneratedConditionBranch(
        **{
            **value,
            "stage_signatures": tuple((stage, tuple(signature)) for stage, signature in value["stage_signatures"]),
            "behavior_signature": tuple(value["behavior_signature"]),
            "stages": tuple(value["stages"]),
        }
    )


def _branch_bindings(workspace: Path, schedule: list[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    root = workspace / "result-artifacts" / "records" / "branches"
    for item in schedule:
        for side in ("control", "treatment"):
            draw = item[f"{side}_draw_id"]
            path = root / item["phase"].casefold() / f"{digest_json({'manifest': _manifest_digest(workspace), 'draw': draw})}.json"
            result.append({"draw_id": draw, "path": str(path), "sha256": digest_bytes(path.read_bytes())})
    return result


def _manifest_digest(workspace: Path) -> str:
    return json.loads((workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_text(encoding="utf-8"))["manifest_digest"]


def _usage(branches: Iterable[GeneratedConditionBranch]) -> dict[str, Any]:
    values = list(branches)
    return {
        "model_calls": len(values),
        "tokens": sum(branch.token_cost for branch in values),
        "wall_seconds_sum": sum(branch.wall_seconds for branch in values),
    }


def _combine_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {key: first[key] + second[key] for key in ("model_calls", "tokens", "wall_seconds_sum")}


def _environment_snapshot(provider_version: str, max_workers: int) -> dict[str, Any]:
    import shutil

    usage = shutil.disk_usage(Path.cwd().anchor)
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "free_disk_bytes_at_seal": usage.free,
        "provider_version": provider_version,
        "max_workers": max_workers,
    }


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (Path(__file__).resolve(), Path(__file__).with_name("parent_intervention_real.py").resolve())
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
