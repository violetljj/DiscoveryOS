from __future__ import annotations

import concurrent.futures
import ctypes
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from discoveryos.benchmarks.executable_mechanism_contract import (
    CONDITION_DIRECT,
    CONDITION_REPAIR,
    ImplementationDraw,
    _draw_from_json,
    _evaluate_descendant,
    _generate_implementation,
    _load_json,
    _profile_probe_source,
    _provider_binding,
    _repository_snapshot,
    _usage,
    _validate_provider,
    compile_executable_contract,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.provider_invocations import assert_no_orphaned_invocations
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "EMC_OPERATOR_CAUSAL_VALUE_R1"
MANIFEST_RECORD = "emc-operator-causal-r1-manifest.json"
CALIBRATION_RECORD = "emc-operator-causal-r1-calibration.json"
REPORT_RECORD = "emc-operator-causal-r1-report.json"
SOURCE_EMC_R3_RECORD = "emc-r3-implementation-validation.json"
CALIBRATION_NULL_PAIRS_PER_CONDITION = 2
VALIDATION_NULL_PAIRS_PER_CONDITION = 2
VALIDATION_INTERVENTION_PAIRS = 3
EXACT_SIGN_ALPHA = 0.10
MAX_POSITIVE_CONTRIBUTION_SHARE = 0.75
MAX_WORKERS = 2


def seal_operator_causal_value_protocol(
    workspace: Path,
    *,
    emc_r3_workspace: Path,
    emc_r3_validation_record_sha256: str,
    implementation_provider: PatchProvider,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    if max_workers < 1 or max_workers > 2:
        raise ValueError("Operator causal-value max_workers must be one or two")
    _validate_provider(implementation_provider)
    authority = _load_emc_r3_authority(
        emc_r3_workspace.resolve(), emc_r3_validation_record_sha256, implementation_provider
    )
    resource = _load_bound_resource_authority(
        Path(authority["manifest"]["resource_authority"]["workspace"]),
        authority["manifest"]["resource_authority"]["record_sha256"],
        authority["manifest"]["resource_authority"]["manifest_digest"],
        implementation_provider,
    )
    token_ceiling = int(resource["record"]["derived_scientific_per_call_token_ceiling"])
    workspace = workspace.resolve()
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_task(store, role, task) for role, task in _development_tasks()]
    applicability = [_applicability_witness(store, state) for state in states]
    if not all(item["passed"] for item in applicability):
        raise RuntimeError("Operator causal-value seal blocked: a state lacks frozen repair applicability")
    pairs = _pair_schedule(states)
    schedule = [branch for pair in pairs for branch in pair["branches"]]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_SCIENTIFIC_MODEL_CALL",
        "scope": "DIRECT_VS_REPAIR_CAUSAL_VALUE_ON_FOUR_PREDECLARED_DEVELOPMENT_STATES",
        "scientific_question": (
            "When Direct Construction and Post-Construction Repair both satisfy their already-confirmed executable "
            "contracts, does Repair improve downstream utility beyond Direct/Direct and Repair/Repair stochastic nulls?"
        ),
        "claim_ceiling": "DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_ON_TWO_INDEPENDENT_VALIDATION_DEV_STATES_ONLY",
        "scientific_model_calls_before_seal": 0,
        "fresh_search_value_tasks_consumed": 0,
        "provider": _provider_binding(implementation_provider),
        "source_emc_r3": {
            "workspace": str(emc_r3_workspace.resolve()),
            "validation_record_sha256": emc_r3_validation_record_sha256,
            "manifest_digest": authority["manifest"]["manifest_digest"],
            "verdict": authority["record"]["verdict"],
        },
        "resource_authority": {
            "workspace": authority["manifest"]["resource_authority"]["workspace"],
            "record_sha256": authority["manifest"]["resource_authority"]["record_sha256"],
            "derived_per_call_token_ceiling": token_ceiling,
        },
        "states": states,
        "repair_applicability": applicability,
        "pairs": pairs,
        "implementation_schedule": schedule,
        "endpoints": {
            "final_utility": "frozen evaluator score for one independently generated implementation",
            "anytime_auc": "mean cumulative-best score over replicate-ordered draws at matched call allocations",
            "validity_rate": "fraction of generated implementations passing public and frozen evaluator validity",
            "replacement_rate": "fraction exceeding the frozen baseline by more than score resolution",
            "breakthrough_probability": "fraction reaching the frozen reference score minus score resolution",
            "runtime_signature": "manipulation check only; never a utility endpoint",
        },
        "margin_rule": {
            "utility": "max(max score resolution, maximum absolute calibration same-condition pair delta)",
            "anytime_auc": "max(max score resolution, maximum absolute calibration same-condition trajectory AUC delta)",
            "validation_state_envelope": "max(frozen calibration margin, same-state validation null absolute effect)",
        },
        "primary_gate": {
            "all_branches_evaluable_and_within_resource_ceiling": True,
            "all_static_runtime_and_invariant_contract_checks_pass": True,
            "direct_and_repair_runtime_signatures_separated": True,
            "beneficial_validation_states_minimum": 2,
            "one_sided_exact_sign_alpha": EXACT_SIGN_ALPHA,
            "median_final_delta_exceeds_registered_envelope": True,
            "both_state_anytime_auc_deltas_exceed_registered_envelopes": True,
            "median_validity_replacement_and_breakthrough_rates_not_worse": True,
            "maximum_single_state_positive_contribution_share": MAX_POSITIVE_CONTRIBUTION_SHARE,
        },
        "result_semantics": {
            "runtime_separated_utility_positive": "OPERATOR_CAUSAL_VALUE_DETECTED_ON_DEV",
            "runtime_separated_utility_not_positive": "DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV",
            "runtime_not_separated": "EMC_OCV_R1_CONTRACT_PORTABILITY_FAILED_UTILITY_NOT_INTERPRETABLE",
            "resource_or_provider_failure": "EMC_OCV_R1_NOT_EVALUABLE_RESOURCE_OR_PROVIDER",
        },
        "isolation": {
            "implementation_forbidden_context": [
                "condition_id",
                "pair_kind",
                "control_or_treatment_role",
                "hidden_evaluator",
                "other_branch_outputs",
            ],
            "independent_provider_requests": True,
            "runtime_evidence_collected_by": "independent_profile_harness",
            "provider_invocation_accounting": "durable_at_most_once_fail_closed",
        },
        "repository": _repository_snapshot(),
        "environment": _environment_snapshot(workspace, max_workers),
        "implementation_bindings": _bindings(),
        "not_authorized": [
            "EMC-R3 root mutation or reinterpretation",
            "post-result task, endpoint, margin, pair-count, or gate changes",
            "fresh search-value execution",
            "system superiority or production claim",
        ],
        "fresh_search_value_budget_authorized": False,
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_sha256": digest_bytes(path.read_bytes()),
        "calibration_model_calls": sum(item["phase"] == "CALIBRATION" for item in schedule),
        "validation_model_calls": sum(item["phase"] == "VALIDATION" for item in schedule),
        "token_ceiling": token_ceiling,
    }


def calibrate_operator_causal_value(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "CALIBRATION"]
    draws = _execute(workspace, manifest, schedule, implementation_provider, progress)
    portability = _portability(draws.values(), manifest, expected=len(schedule))
    pair_effects = _pair_effects(manifest, draws, phase="CALIBRATION")
    utility_margin = max(
        max(float(state["score_resolution"]) for state in manifest["states"]),
        max((abs(item["final_utility_delta"]) for item in pair_effects), default=0.0),
    )
    auc_nulls = _null_auc_effects(manifest, draws, phase="CALIBRATION")
    auc_margin = max(
        max(float(state["score_resolution"]) for state in manifest["states"]),
        max((abs(item["anytime_auc_delta"]) for item in auc_nulls), default=0.0),
    )
    passed = portability["passed"]
    if not portability["resource_and_provider_ok"]:
        verdict = "EMC_OCV_R1_CALIBRATION_NOT_EVALUABLE_RESOURCE_OR_PROVIDER"
    elif not portability["manipulation_ok"]:
        verdict = "EMC_OCV_R1_CALIBRATION_CONTRACT_PORTABILITY_FAILED"
    else:
        verdict = "EMC_OCV_R1_STOCHASTIC_NULL_CALIBRATION_PASSED"
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": verdict,
        "passed": passed,
        "portability": portability,
        "pair_effects": pair_effects,
        "auc_null_effects": auc_nulls,
        "frozen_margins": {"utility": utility_margin, "anytime_auc": auc_margin},
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _usage(draws.values()),
        "validation_authorized": passed,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(CALIBRATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_operator_causal_value_validation(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    calibration_path = workspace / "result-artifacts" / "records" / CALIBRATION_RECORD
    calibration = _load_json(calibration_path)
    if calibration.get("manifest_digest") != manifest_digest or not calibration.get("passed"):
        raise RuntimeError("Operator causal-value validation blocked because calibration did not pass")
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "VALIDATION"]
    draws = _execute(workspace, manifest, schedule, implementation_provider, progress)
    portability = _portability(draws.values(), manifest, expected=len(schedule))
    pair_effects = _pair_effects(manifest, draws, phase="VALIDATION")
    analysis, gate = _validation_analysis(manifest, calibration, draws, pair_effects, portability)
    if not portability["resource_and_provider_ok"]:
        verdict = "EMC_OCV_R1_NOT_EVALUABLE_RESOURCE_OR_PROVIDER"
    elif not portability["manipulation_ok"]:
        verdict = "EMC_OCV_R1_CONTRACT_PORTABILITY_FAILED_UTILITY_NOT_INTERPRETABLE"
    elif gate["passed"]:
        verdict = "OPERATOR_CAUSAL_VALUE_DETECTED_ON_DEV"
    else:
        verdict = "DIRECT_REPAIR_OPERATOR_CAUSAL_VALUE_NOT_ESTABLISHED_ON_DEV"
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "EMC_OCV_R1_COMPLETE",
        "verdict": verdict,
        "portability": portability,
        "utility_interpretable": portability["passed"],
        "analysis": analysis,
        "primary_gate": gate,
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _combine_usage(calibration["usage"], _usage(draws.values())),
        "claim_ceiling": manifest["claim_ceiling"],
        "search_value_established": False,
        "fresh_search_value_budget_authorized": False,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def _development_tasks():
    return (
        ("CALIBRATION", _assignment_task("ocv_r1_assignment_calibration", (17107, 17123, 17159, 17189, 17207, 17231))),
        ("CALIBRATION", _coverage_task("ocv_r1_coverage_calibration", (18109, 18127, 18149, 18181, 18211, 18223))),
        ("VALIDATION", _assignment_task("ocv_r1_assignment_validation", (19121, 19139, 19163, 19181, 19213, 19231))),
        ("VALIDATION", _coverage_task("ocv_r1_coverage_validation", (20107, 20129, 20147, 20173, 20201, 20231))),
    )


def _freeze_task(store: ArtifactStore, role: str, task: Any) -> dict[str, Any]:
    entrypoint = "assign_clients" if task.task.category == "capacitated_cost_assignment" else "choose_sets"
    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
        "profile_probe.py": store.put_bytes(_profile_probe_source(entrypoint, task.task.category).encode("utf-8"), media_type="text/x-python"),
    }
    base_source = normalized_source(task.task.algorithm_source)
    reference_source = normalized_source(task.reference_source)
    state = {
        "state_id": f"emc-ocv-r1-{task.task.task_id}",
        "role": role,
        "task_id": task.task.task_id,
        "task_category": task.task.category,
        "task_payload_digest": task.payload_digest,
        "entrypoint": entrypoint,
        "base_source_digest": store.put_bytes(base_source.encode("utf-8"), media_type="text/x-python"),
        "reference_source_digest": store.put_bytes(reference_source.encode("utf-8"), media_type="text/x-python"),
        "task_files": files,
        "score_resolution": task.score_resolution,
    }
    return {**state, "state_digest": digest_json(state)}


def _applicability_witness(store: ArtifactStore, state: dict[str, Any]) -> dict[str, Any]:
    base = _evaluate_descendant(store, state, store.get_bytes(state["base_source_digest"]).decode("utf-8"))
    reference = _evaluate_descendant(store, state, store.get_bytes(state["reference_source_digest"]).decode("utf-8"))
    delta = float(reference["score"]) - float(base["score"])
    improved_probes = sum(
        right > left + 1e-12 for left, right in zip(base["probe_scores"], reference["probe_scores"], strict=True)
    )
    passed = bool(base["valid"] and reference["valid"] and delta >= float(state["score_resolution"]) and improved_probes > 0)
    return {
        "state_id": state["state_id"],
        "passed": passed,
        "criterion": "valid reference improves valid baseline by score resolution and improves at least one frozen probe",
        "baseline_score": float(base["score"]),
        "reference_score": float(reference["score"]),
        "score_delta": delta,
        "improved_probe_count": improved_probes,
        "breakthrough_threshold": max(float(base["score"]) + float(state["score_resolution"]), float(reference["score"]) - float(state["score_resolution"])),
        "baseline_source_sha256": base["source_sha256"],
        "reference_source_sha256": reference["source_sha256"],
    }


def _pair_schedule(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for state in states:
        phase = state["role"]
        specifications = [
            ("DIRECT_NULL", CONDITION_DIRECT, CONDITION_DIRECT, CALIBRATION_NULL_PAIRS_PER_CONDITION if phase == "CALIBRATION" else VALIDATION_NULL_PAIRS_PER_CONDITION),
            ("REPAIR_NULL", CONDITION_REPAIR, CONDITION_REPAIR, CALIBRATION_NULL_PAIRS_PER_CONDITION if phase == "CALIBRATION" else VALIDATION_NULL_PAIRS_PER_CONDITION),
        ]
        if phase == "VALIDATION":
            specifications.append(("INTERVENTION", CONDITION_DIRECT, CONDITION_REPAIR, VALIDATION_INTERVENTION_PAIRS))
        for kind, control_condition, treatment_condition, count in specifications:
            for replicate in range(count):
                pair_id = f"{state['state_id']}:{kind.casefold()}:{replicate}"
                branches = []
                for side, condition in (("control", control_condition), ("treatment", treatment_condition)):
                    branches.append({
                        "state_id": state["state_id"],
                        "phase": phase,
                        "pair_id": pair_id,
                        "pair_kind": kind,
                        "replicate": replicate,
                        "side": side,
                        "condition_id": condition,
                        "draw_id": f"{pair_id}:{side}",
                        "contract": compile_executable_contract(condition, state["entrypoint"]),
                    })
                pairs.append({"pair_id": pair_id, "state_id": state["state_id"], "phase": phase, "kind": kind, "replicate": replicate, "branches": branches})
    return pairs


def _execute(
    workspace: Path,
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    provider: PatchProvider,
    progress: Callable[[str], None] | None,
) -> dict[str, ImplementationDraw]:
    assert_no_orphaned_invocations(workspace / "result-artifacts")
    states = {state["state_id"]: state for state in manifest["states"]}
    store = ArtifactStore(workspace / "result-artifacts")
    ceiling = int(manifest["resource_authority"]["derived_per_call_token_ceiling"])

    def execute(item: dict[str, Any]) -> ImplementationDraw:
        path = store.records / _draw_record_name(manifest, item["draw_id"])
        if path.is_file():
            saved = _load_json(path)
            _verify_checkpoint(saved, manifest, item)
            return _draw_from_json(saved["draw"])
        draw = _generate_implementation(
            workspace,
            states[item["state_id"]],
            item,
            provider,
            protocol_id=PROTOCOL_ID,
            token_ceiling=ceiling,
        )
        body = jsonable(draw)
        store.write_record(_draw_record_name(manifest, item["draw_id"]), {
            "manifest_digest": manifest["manifest_digest"],
            "draw_id": item["draw_id"],
            "condition_id": item["condition_id"],
            "draw": body,
            "draw_digest": digest_json(body),
        })
        return draw

    draws: dict[str, ImplementationDraw] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(manifest["environment"]["max_workers"])) as executor:
        future_map = {executor.submit(execute, item): item for item in schedule}
        for completed, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            draw = future.result()
            draws[draw.draw_id] = draw
            if progress:
                progress(f"EMC-OCV-R1 {schedule[0]['phase'].casefold()} draw {completed}/{len(schedule)} complete")
    return draws


def _portability(draws: Iterable[ImplementationDraw], manifest: dict[str, Any], *, expected: int) -> dict[str, Any]:
    values = list(draws)
    ceiling = int(manifest["resource_authority"]["derived_per_call_token_ceiling"])
    resource_and_provider_ok = len(values) == expected and all(draw.evaluable and draw.token_cost <= ceiling for draw in values)
    direct_signatures = {draw.counter_signature for draw in values if draw.condition_id == CONDITION_DIRECT}
    repair_signatures = {draw.counter_signature for draw in values if draw.condition_id == CONDITION_REPAIR}
    contract_ok = all(
        draw.source_valid and draw.static_contract_passed and draw.runtime_contract_passed and draw.invariant_canary_passed
        for draw in values
    )
    signatures_separated = (
        direct_signatures == {(1.0, 0.0, 0.0)} and repair_signatures == {(1.0, 1.0, 0.0)}
    )
    manipulation_ok = len(values) == expected and contract_ok and signatures_separated
    return {
        "passed": resource_and_provider_ok and manipulation_ok,
        "draws": len(values),
        "expected_draws": expected,
        "resource_and_provider_ok": resource_and_provider_ok,
        "all_contract_layers_passed": contract_ok,
        "runtime_signatures_separated": signatures_separated,
        "manipulation_ok": manipulation_ok,
        "within_condition_signatures": {
            CONDITION_DIRECT: [list(value) for value in sorted(direct_signatures)],
            CONDITION_REPAIR: [list(value) for value in sorted(repair_signatures)],
        },
    }


def _pair_effects(
    manifest: dict[str, Any], draws: dict[str, ImplementationDraw], *, phase: str
) -> list[dict[str, Any]]:
    states = {state["state_id"]: state for state in manifest["states"]}
    applicability = {item["state_id"]: item for item in manifest["repair_applicability"]}
    result = []
    for pair in manifest["pairs"]:
        if pair["phase"] != phase:
            continue
        control = draws[f"{pair['pair_id']}:control"]
        treatment = draws[f"{pair['pair_id']}:treatment"]
        state = states[pair["state_id"]]
        witness = applicability[pair["state_id"]]
        baseline = float(witness["baseline_score"])
        resolution = float(state["score_resolution"])
        breakthrough = float(witness["breakthrough_threshold"])
        control_score = float(control.evaluation.get("score", 0.0)) if control.source_valid else 0.0
        treatment_score = float(treatment.evaluation.get("score", 0.0)) if treatment.source_valid else 0.0
        result.append({
            "pair_id": pair["pair_id"],
            "state_id": pair["state_id"],
            "kind": pair["kind"],
            "replicate": pair["replicate"],
            "control_condition": control.condition_id,
            "treatment_condition": treatment.condition_id,
            "control_score": control_score,
            "treatment_score": treatment_score,
            "final_utility_delta": treatment_score - control_score,
            "validity_delta": float(treatment.source_valid) - float(control.source_valid),
            "replacement_delta": float(treatment.source_valid and treatment_score > baseline + resolution) - float(control.source_valid and control_score > baseline + resolution),
            "breakthrough_delta": float(treatment.source_valid and treatment_score >= breakthrough) - float(control.source_valid and control_score >= breakthrough),
        })
    return result


def _null_auc_effects(
    manifest: dict[str, Any], draws: dict[str, ImplementationDraw], *, phase: str
) -> list[dict[str, Any]]:
    effects = []
    for state in (item for item in manifest["states"] if item["role"] == phase):
        witness = next(item for item in manifest["repair_applicability"] if item["state_id"] == state["state_id"])
        for kind in ("DIRECT_NULL", "REPAIR_NULL"):
            pairs = sorted(
                (item for item in manifest["pairs"] if item["state_id"] == state["state_id"] and item["kind"] == kind),
                key=lambda item: int(item["replicate"]),
            )
            control_scores = [_draw_score(draws[f"{item['pair_id']}:control"]) for item in pairs]
            treatment_scores = [_draw_score(draws[f"{item['pair_id']}:treatment"]) for item in pairs]
            control_auc = _trajectory_auc(control_scores, float(witness["baseline_score"]))
            treatment_auc = _trajectory_auc(treatment_scores, float(witness["baseline_score"]))
            effects.append({
                "state_id": state["state_id"],
                "kind": kind,
                "control_anytime_auc": control_auc,
                "treatment_anytime_auc": treatment_auc,
                "anytime_auc_delta": treatment_auc - control_auc,
            })
    return effects


def _validation_analysis(
    manifest: dict[str, Any],
    calibration: dict[str, Any],
    draws: dict[str, ImplementationDraw],
    pair_effects: list[dict[str, Any]],
    portability: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    utility_margin = float(calibration["frozen_margins"]["utility"])
    auc_margin = float(calibration["frozen_margins"]["anytime_auc"])
    state_summaries = []
    adjusted_signs: list[int] = []
    positive_by_state: dict[str, float] = {}
    for state in (item for item in manifest["states"] if item["role"] == "VALIDATION"):
        state_id = state["state_id"]
        witness = next(item for item in manifest["repair_applicability"] if item["state_id"] == state_id)
        null_effects = [item for item in pair_effects if item["state_id"] == state_id and item["kind"] != "INTERVENTION"]
        interventions = sorted(
            (item for item in pair_effects if item["state_id"] == state_id and item["kind"] == "INTERVENTION"),
            key=lambda item: int(item["replicate"]),
        )
        state_utility_envelope = max(utility_margin, max((abs(item["final_utility_delta"]) for item in null_effects), default=0.0))
        null_auc = next(
            item for item in _null_auc_effects(manifest, draws, phase="VALIDATION")
            if item["state_id"] == state_id and item["kind"] == "DIRECT_NULL"
        )
        repair_null_auc = next(
            item for item in _null_auc_effects(manifest, draws, phase="VALIDATION")
            if item["state_id"] == state_id and item["kind"] == "REPAIR_NULL"
        )
        state_auc_envelope = max(auc_margin, abs(null_auc["anytime_auc_delta"]), abs(repair_null_auc["anytime_auc_delta"]))
        direct_scores = [float(item["control_score"]) for item in interventions]
        repair_scores = [float(item["treatment_score"]) for item in interventions]
        direct_auc = _trajectory_auc(direct_scores, float(witness["baseline_score"]))
        repair_auc = _trajectory_auc(repair_scores, float(witness["baseline_score"]))
        raw_deltas = [float(item["final_utility_delta"]) for item in interventions]
        for delta in raw_deltas:
            adjusted_signs.append(1 if delta > state_utility_envelope else -1 if delta < -state_utility_envelope else 0)
        positive_by_state[state_id] = sum(max(0.0, delta - state_utility_envelope) for delta in raw_deltas)
        state_summaries.append({
            "state_id": state_id,
            "utility_envelope": state_utility_envelope,
            "anytime_auc_envelope": state_auc_envelope,
            "intervention_final_deltas": raw_deltas,
            "median_final_delta": statistics.median(raw_deltas),
            "direct_anytime_auc": direct_auc,
            "repair_anytime_auc": repair_auc,
            "anytime_auc_delta": repair_auc - direct_auc,
            "validity_rate_delta": statistics.fmean(float(item["validity_delta"]) for item in interventions),
            "replacement_rate_delta": statistics.fmean(float(item["replacement_delta"]) for item in interventions),
            "breakthrough_probability_delta": statistics.fmean(float(item["breakthrough_delta"]) for item in interventions),
            "beneficial": statistics.median(raw_deltas) > state_utility_envelope and repair_auc - direct_auc > state_auc_envelope,
        })
    positives = sum(value > 0 for value in adjusted_signs)
    negatives = sum(value < 0 for value in adjusted_signs)
    nonzero = positives + negatives
    sign_p = _one_sided_sign_p(positives, nonzero)
    intervention_effects = [item for item in pair_effects if item["kind"] == "INTERVENTION"]
    all_final_deltas = [float(item["final_utility_delta"]) for item in intervention_effects]
    pair_envelopes = [
        next(state["utility_envelope"] for state in state_summaries if state["state_id"] == item["state_id"])
        for item in intervention_effects
    ]
    total_positive = sum(positive_by_state.values())
    contribution_share = max(positive_by_state.values(), default=0.0) / total_positive if total_positive else 1.0
    checks = {
        "utility_interpretable": portability["passed"],
        "minimum_beneficial_states": sum(bool(item["beneficial"]) for item in state_summaries) >= 2,
        "one_sided_exact_sign": nonzero > 0 and sign_p <= EXACT_SIGN_ALPHA,
        "median_final_delta_exceeds_registered_envelope": statistics.median(all_final_deltas) > statistics.median(pair_envelopes),
        "both_state_anytime_auc_positive": all(item["anytime_auc_delta"] > item["anytime_auc_envelope"] for item in state_summaries),
        "median_validity_rate_not_worse": statistics.median(item["validity_rate_delta"] for item in state_summaries) >= 0.0,
        "median_replacement_rate_not_worse": statistics.median(item["replacement_rate_delta"] for item in state_summaries) >= 0.0,
        "median_breakthrough_probability_not_worse": statistics.median(item["breakthrough_probability_delta"] for item in state_summaries) >= 0.0,
        "not_single_state_driven": contribution_share <= MAX_POSITIVE_CONTRIBUTION_SHARE,
    }
    analysis = {
        "frozen_calibration_margins": calibration["frozen_margins"],
        "state_summaries": state_summaries,
        "validation_pair_effects": pair_effects,
        "positive_pairs_beyond_envelope": positives,
        "negative_pairs_beyond_envelope": negatives,
        "ties_within_envelope": len(adjusted_signs) - nonzero,
        "one_sided_exact_sign_p": sign_p,
        "median_final_utility_delta": statistics.median(all_final_deltas),
        "maximum_single_state_positive_contribution_share": contribution_share,
    }
    return analysis, {"passed": all(checks.values()), "checks": checks}


def _draw_score(draw: ImplementationDraw) -> float:
    return float(draw.evaluation.get("score", 0.0)) if draw.source_valid else 0.0


def _trajectory_auc(scores: list[float], incumbent: float) -> float:
    best = incumbent
    values = []
    for score in scores:
        best = max(best, score)
        values.append(best)
    return statistics.fmean(values) if values else incumbent


def _one_sided_sign_p(positives: int, nonzero: int) -> float:
    if nonzero <= 0:
        return 1.0
    return sum(math.comb(nonzero, count) for count in range(positives, nonzero + 1)) / (2**nonzero)


def _load_emc_r3_authority(
    workspace: Path, expected_record_sha256: str, provider: PatchProvider
) -> dict[str, Any]:
    record_path = workspace / "result-artifacts" / "records" / SOURCE_EMC_R3_RECORD
    if not record_path.is_file() or digest_bytes(record_path.read_bytes()) != expected_record_sha256:
        raise RuntimeError("EMC-R3 validation authority hash mismatch")
    record = _load_json(record_path)
    if not record.get("passed") or record.get("verdict") != "EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES":
        raise RuntimeError("EMC-R3 did not authorize an Operator causal-value protocol")
    manifest_path = workspace / "protocol-artifacts" / "records" / "emc-r3-manifest.json"
    manifest = _load_json(manifest_path, record["manifest_digest"])
    if manifest.get("provider") != _provider_binding(provider):
        raise RuntimeError("Operator causal-value provider differs from EMC-R3 authority")
    return {"record": record, "manifest": manifest}


def _load_bound_resource_authority(
    workspace: Path,
    expected_record_sha256: str,
    expected_manifest_digest: str,
    provider: PatchProvider,
) -> dict[str, Any]:
    """Verify the historical authority without requiring the current HEAD to equal its seal commit."""
    record_path = workspace.resolve() / "result-artifacts" / "records" / "emc-resource-calibration-r1-result.json"
    manifest_path = workspace.resolve() / "protocol-artifacts" / "records" / "emc-resource-calibration-r1-manifest.json"
    if not record_path.is_file() or digest_bytes(record_path.read_bytes()) != expected_record_sha256:
        raise RuntimeError("EMC resource authority record hash mismatch")
    record = _load_json(record_path)
    manifest = _load_json(manifest_path, expected_manifest_digest)
    if (
        record.get("manifest_digest") != expected_manifest_digest
        or not record.get("passed")
        or record.get("status") != "EMC_RESOURCE_CALIBRATION_PASSED"
        or manifest.get("provider") != _provider_binding(provider)
    ):
        raise RuntimeError("EMC resource authority binding mismatch")
    derived = int(record.get("derived_scientific_per_call_token_ceiling", 0))
    if derived <= 0 or derived > int(record["ceiling_rule"]["maximum_scientific_ceiling"]):
        raise RuntimeError("EMC resource authority derived ceiling is invalid")
    return {"record": record, "manifest": manifest}


def _load_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("status") != "SEALED_PRE_SCIENTIFIC_MODEL_CALL":
        raise RuntimeError("Operator causal-value manifest was not sealed before scientific calls")
    if manifest.get("provider") != _provider_binding(provider):
        raise RuntimeError("Operator causal-value provider drift")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("Operator causal-value repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("Operator causal-value implementation binding drift")
    authority = _load_emc_r3_authority(
        Path(manifest["source_emc_r3"]["workspace"]),
        manifest["source_emc_r3"]["validation_record_sha256"],
        provider,
    )
    resource = _load_bound_resource_authority(
        Path(manifest["resource_authority"]["workspace"]),
        manifest["resource_authority"]["record_sha256"],
        authority["manifest"]["resource_authority"]["manifest_digest"],
        provider,
    )
    if int(resource["record"]["derived_scientific_per_call_token_ceiling"]) != int(
        manifest["resource_authority"]["derived_per_call_token_ceiling"]
    ):
        raise RuntimeError("Operator causal-value resource ceiling authority drift")
    return manifest


def _draw_record_name(manifest: dict[str, Any], draw_id: str) -> str:
    digest = digest_json({"manifest": manifest["manifest_digest"], "stage": "operator-causal-value", "draw": draw_id})
    return f"draws/operator-causal-value/{digest}.json"


def _verify_checkpoint(saved: dict[str, Any], manifest: dict[str, Any], item: dict[str, Any]) -> None:
    if (
        saved.get("manifest_digest") != manifest["manifest_digest"]
        or saved.get("draw_id") != item["draw_id"]
        or saved.get("condition_id") != item["condition_id"]
        or saved.get("draw_digest") != digest_json(saved.get("draw"))
    ):
        raise RuntimeError("Operator causal-value draw checkpoint binding mismatch")


def _draw_bindings(
    workspace: Path, manifest: dict[str, Any], schedule: list[dict[str, Any]]
) -> list[dict[str, str]]:
    root = workspace / "result-artifacts" / "records"
    return [
        {
            "draw_id": item["draw_id"],
            "path": str(root / _draw_record_name(manifest, item["draw_id"])),
            "sha256": digest_bytes((root / _draw_record_name(manifest, item["draw_id"])).read_bytes()),
        }
        for item in schedule
    ]


def _bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("executable_mechanism_contract.py").resolve(),
        Path(__file__).with_name("executable_mechanism_contract_r3.py").resolve(),
        Path(__file__).with_name("emc_resource_calibration.py").resolve(),
        Path(__file__).with_name("si2_tasks.py").resolve(),
        Path(__file__).with_name("parent_intervention_real.py").resolve(),
        (Path(__file__).resolve().parents[1] / "runtime" / "provider_invocations.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]


def _environment_snapshot(workspace: Path, max_workers: int) -> dict[str, Any]:
    disk = shutil.disk_usage(workspace.anchor)
    memory: dict[str, int | None] = {"total_bytes": None, "available_bytes": None}
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load_percent", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            memory = {"total_bytes": int(status.total_physical), "available_bytes": int(status.available_physical)}
    gpu: dict[str, Any] = {"available": False}
    nvidia_smi = Path("C:/Windows/System32/nvidia-smi.exe")
    if nvidia_smi.is_file():
        completed = subprocess.run(
            (
                str(nvidia_smi),
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        if completed.returncode == 0:
            gpu = {"available": True, "query": [line.strip() for line in completed.stdout.splitlines() if line.strip()]}
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "memory": memory,
        "disk": {"root": workspace.anchor, "total_bytes": disk.total, "free_bytes": disk.free},
        "gpu": gpu,
        "max_workers": max_workers,
        "concurrency_policy": "bounded independent provider requests; shared create-once store guarded by unique draw identity",
    }


def _combine_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_calls": int(first["model_calls"]) + int(second["model_calls"]),
        "tokens": int(first["tokens"]) + int(second["tokens"]),
        "wall_seconds_sum": float(first["wall_seconds_sum"]) + float(second["wall_seconds_sum"]),
    }
