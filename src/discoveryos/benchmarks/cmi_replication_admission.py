from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.cmi_causal_value import MANIFEST_RECORD as R5_MANIFEST_RECORD
from discoveryos.benchmarks.cmi_causal_value import REPORT_RECORD as R5_REPORT_RECORD
from discoveryos.benchmarks.cmi_probe_calibration import _behavior_probe_source, _behavior_signature, _mean_absolute_distance
from discoveryos.benchmarks.executable_mechanism_contract import _evaluate_descendant, _load_json, _repository_snapshot
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2 import CONFIRMATION_REPORT_RECORD, DISCOVERY_REPORT_RECORD, MANIFEST_RECORD as SI2_MANIFEST_RECORD, PROTOCOL_ID as SI2_PROTOCOL_ID
from discoveryos.benchmarks.si2_tasks import si2_confirmation_tasks, si2_discovery_tasks
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator
from discoveryos.operators.local_behavior_control import LocalBehaviorControlOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION"
MANIFEST_RECORD = "cmi-r6-replication-manifest.json"
REPORT_RECORD = "cmi-r6-replication-report.json"
ELIGIBLE_CATEGORIES = {"capacitated_cost_assignment", "budgeted_weighted_coverage"}
EXPECTED_STATES = 8
FUNCTIONAL_ESCAPE_THRESHOLD = 0.10


def seal_cmi_replication_admission(
    workspace: Path,
    *,
    cmi_r5_workspace: Path,
    cmi_r5_report_sha256: str,
    si2_workspace: Path,
    si2_discovery_report_sha256: str,
    si2_confirmation_report_sha256: str,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R6 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R6 must be sealed from a clean worktree")

    r5 = _load_r5_authority(cmi_r5_workspace.resolve(), cmi_r5_report_sha256)
    si2 = _load_si2_authority(
        si2_workspace.resolve(), si2_discovery_report_sha256, si2_confirmation_report_sha256
    )
    _verify_frozen_operator_bindings(r5["manifest"])
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = _freeze_population(store, si2["manifest"])
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_REPLICATION_EVALUATION",
        "scope": "ALL_ELIGIBLE_SI2_CONSUMED_ASSIGNMENT_AND_COVERAGE_STATES",
        "scientific_question": "Does the frozen R5 paired causal-value effect retain its sign across all compatible consumed SI-2 states not used in CMI-R3/R4/R5?",
        "claim_ceiling": "CMI_CAUSAL_VALUE_REPLICATION_ON_CONSUMED_SI2_ASSIGNMENT_COVERAGE_DISTRIBUTION_ONLY",
        "repository": repository,
        "cmi_r5_authority": r5["binding"],
        "si2_consumed_authority": si2["binding"],
        "brief": r5["manifest"]["brief"],
        "population_rule": {
            "source": "all SI-2 discovery and confirmation cohort states",
            "eligible_categories": sorted(ELIGIBLE_CATEGORIES),
            "excluded_category": "balanced_graph_cut because the frozen R5 Operator has no implementation",
            "selection_after_utility_observation": False,
            "expected_states": EXPECTED_STATES,
            "expected_states_per_category": 4,
        },
        "contamination_disclosure": {
            "exact_state_ids_and_evaluator_seeds_used_in_cmi_r3_r4_r5": False,
            "task_families_available_before_r6": True,
            "si2_intermediate_heuristic_evidence_available_before_r6": True,
            "blind_mechanism_formation_independent_replication": False,
            "interpretation": "all-population consumed-distribution robustness only",
        },
        "states": states,
        "matched_conditions": r5["manifest"]["matched_conditions"],
        "endpoints": r5["manifest"]["endpoints"],
        "replication_gate": {
            "all_states_technically_evaluable": True,
            "control_escape_states_maximum": 0,
            "treatment_escape_states_minimum": 7,
            "positive_utility_states_beyond_resolution_minimum": 7,
            "negative_utility_states_beyond_resolution_maximum": 0,
            "both_category_median_utility_delta_exceeds_resolution": True,
            "both_category_median_auc_delta_exceeds_half_resolution": True,
            "treatment_validity_rate_not_worse": True,
            "treatment_replacement_rate_strictly_higher": True,
            "treatment_breakthrough_rate_not_worse": True,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
            "matched_zero_model_and_zero_token_resources": True,
        },
        "result_semantics": {
            "gate_passed": "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED",
            "gate_failed": "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_NOT_ESTABLISHED",
            "not_evaluable": "CMI_R6_NOT_EVALUABLE_PROBE_OR_EVALUATOR",
            "next_authority_if_passed": "CMI_FRESH_CAUSAL_VALIDATION_ADMISSION_READY",
        },
        "probability_or_significance_claim_authorized": False,
        "cross_task_family_generalization_claim_authorized": False,
        "blind_independent_replication_claim_authorized": False,
        "fresh_search_value_execution_authorized": False,
        "model_calls": 0,
        "tokens": 0,
        "fresh_search_value_tasks_consumed": 0,
        "consumed_states_reused_if_run": EXPECTED_STATES,
        "implementation_bindings": _implementation_bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "states": len(states),
        "model_calls": 0,
        "tokens": 0,
        "fresh_search_value_tasks_consumed": 0,
    }


def run_cmi_replication_admission(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest)
    store = ArtifactStore(workspace / "protocol-artifacts")
    control_operator = LocalBehaviorControlOperator()
    treatment_operator = FunctionalBasinEscapeOperator(manifest["brief"])
    states = [
        _run_replication_pair(store, state, control_operator, treatment_operator)
        for state in manifest["states"]
    ]
    technically_evaluable = all(item["technically_evaluable"] for item in states)
    analysis, gate = _analyze_replication(states, manifest["replication_gate"])
    if not technically_evaluable:
        verdict = "CMI_R6_NOT_EVALUABLE_PROBE_OR_EVALUATOR"
    elif gate["passed"]:
        verdict = "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED"
    else:
        verdict = "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_NOT_ESTABLISHED"
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "CMI_R6_COMPLETE",
        "verdict": verdict,
        "technically_evaluable": technically_evaluable,
        "states": states,
        "analysis": analysis,
        "replication_gate": gate,
        "claim_ceiling": manifest["claim_ceiling"],
        "fresh_causal_validation_preregistration_authorized": verdict == "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED",
        "fresh_search_value_execution_authorized": False,
        "probability_or_significance_established": False,
        "cross_task_family_generalization_established": False,
        "blind_independent_replication_established": False,
        "search_value_established": False,
        "model_calls": 0,
        "tokens": 0,
        "operator_invocations": {"control": len(states), "treatment": len(states)},
        "evaluator_calls": len(states) * 4,
        "functional_probe_calls": len(states) * 4,
        "fresh_search_value_tasks_consumed": 0,
        "consumed_states_reused": len(states),
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_population(store: ArtifactStore, si2_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = {
        entry["task_id"]: entry
        for cohort in ("discovery", "confirmation")
        for entry in si2_manifest["cohorts"][cohort]
        if entry["category"] in ELIGIBLE_CATEGORIES
    }
    tasks = [
        task
        for task in (*si2_discovery_tasks(), *si2_confirmation_tasks())
        if task.task.category in ELIGIBLE_CATEGORIES
    ]
    if len(tasks) != EXPECTED_STATES or set(entries) != {task.task.task_id for task in tasks}:
        raise RuntimeError("CMI-R6 eligible SI-2 population is incomplete")
    if any(task.payload_digest != entries[task.task.task_id]["task_payload_digest"] for task in tasks):
        raise RuntimeError("CMI-R6 reconstructed task differs from SI-2 authority")
    states = []
    for index, task in enumerate(tasks):
        entry = entries[task.task.task_id]
        probe_seeds = (41011 + index * 101, 41031 + index * 101, 41057 + index * 101)
        state = {
            "state_id": f"cmi-r6-{index}-{task.task.task_id}",
            "task_id": task.task.task_id,
            "task_category": task.task.category,
            "cohort_role": entry["cohort_role"],
            "task_payload_digest": task.payload_digest,
            "si2_repository_commit": entry["repository_commit"],
            "score_resolution": task.score_resolution,
            "base_source_digest": store.put_bytes(normalized_source(task.task.algorithm_source).encode("utf-8"), media_type="text/x-python"),
            "reference_source_digest": store.put_bytes(normalized_source(task.reference_source).encode("utf-8"), media_type="text/x-python"),
            "task_files": {
                "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
                "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
                "functional_probe.py": store.put_bytes(_behavior_probe_source(task.task.category, probe_seeds).encode("utf-8"), media_type="text/x-python"),
            },
            "functional_probe_seeds": list(probe_seeds),
            "breakthrough_rule": "reference_score_minus_score_resolution",
            "consumed_basis": "bound SI-2 discovery or confirmation cohort entry",
        }
        states.append({**state, "state_digest": digest_json(state)})
    category_counts = {
        category: sum(state["task_category"] == category for state in states)
        for category in ELIGIBLE_CATEGORIES
    }
    if set(category_counts.values()) != {4}:
        raise RuntimeError("CMI-R6 population is not balanced across eligible categories")
    return states


def _run_replication_pair(
    store: ArtifactStore,
    state: dict[str, Any],
    control_operator: LocalBehaviorControlOperator,
    treatment_operator: FunctionalBasinEscapeOperator,
) -> dict[str, Any]:
    base = store.get_bytes(state["base_source_digest"]).decode("utf-8")
    reference = store.get_bytes(state["reference_source_digest"]).decode("utf-8")
    started = time.perf_counter()
    control = control_operator.propose(task_category=state["task_category"], base_source=base)
    control_operator_seconds = time.perf_counter() - started
    started = time.perf_counter()
    treatment = treatment_operator.propose(task_category=state["task_category"], base_source=base)
    treatment_operator_seconds = time.perf_counter() - started
    sources = {"incumbent": base, "reference": reference, "control": control.source, "treatment": treatment.source}
    signatures = {label: _functional_signature(store, state, source) for label, source in sources.items()}
    evaluations, evaluator_seconds = {}, {}
    for label, source in sources.items():
        started = time.perf_counter()
        evaluations[label] = _evaluate_descendant(store, state, source)
        evaluator_seconds[label] = time.perf_counter() - started
    distances = {
        label: _mean_absolute_distance(signatures["incumbent"], signatures[label])
        for label in ("reference", "control", "treatment")
    }
    technically_evaluable = all(signatures.values()) and all(bool(item.get("valid")) for item in evaluations.values())
    manipulation_passed = (
        technically_evaluable
        and distances["reference"] > FUNCTIONAL_ESCAPE_THRESHOLD
        and distances["control"] == 0.0
        and distances["treatment"] > FUNCTIONAL_ESCAPE_THRESHOLD
        and control.trace["positive_control_received"] is False
        and treatment.trace["positive_control_received"] is False
        and control.trace["evaluator_feedback_received"] is False
        and treatment.trace["evaluator_feedback_received"] is False
    )
    incumbent_score = float(evaluations["incumbent"].get("score", 0.0))
    reference_score = float(evaluations["reference"].get("score", 0.0))
    breakthrough_threshold = reference_score - float(state["score_resolution"])
    arms = {}
    for arm, result, operator_seconds in (
        ("control", control, control_operator_seconds),
        ("treatment", treatment, treatment_operator_seconds),
    ):
        score = float(evaluations[arm].get("score", 0.0))
        valid = bool(evaluations[arm].get("valid"))
        arms[arm] = {
            "valid": valid,
            "score": score,
            "functional_distance": distances[arm],
            "escaped": valid and distances[arm] > FUNCTIONAL_ESCAPE_THRESHOLD,
            "anytime_auc": statistics.fmean((incumbent_score, max(incumbent_score, score))),
            "replaced_incumbent": valid and score > incumbent_score + float(state["score_resolution"]),
            "breakthrough": valid and score >= breakthrough_threshold,
            "operator_seconds": operator_seconds,
            "evaluator_seconds": evaluator_seconds[arm],
            "source_sha256": evaluations[arm].get("source_sha256"),
            "trace": result.trace,
        }
    return {
        "state_id": state["state_id"],
        "task_id": state["task_id"],
        "task_category": state["task_category"],
        "cohort_role": state["cohort_role"],
        "score_resolution": state["score_resolution"],
        "technically_evaluable": technically_evaluable,
        "manipulation_passed": manipulation_passed,
        "functional_distances": distances,
        "incumbent": {"valid": evaluations["incumbent"]["valid"], "score": incumbent_score},
        "reference": {"valid": evaluations["reference"]["valid"], "score": reference_score},
        "breakthrough_threshold": breakthrough_threshold,
        "arms": arms,
        "evaluator_seconds": evaluator_seconds,
    }


def _analyze_replication(states: list[dict[str, Any]], thresholds: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    effects = []
    for state in states:
        control, treatment = state["arms"]["control"], state["arms"]["treatment"]
        effects.append({
            "state_id": state["state_id"],
            "task_category": state["task_category"],
            "score_resolution": state["score_resolution"],
            "final_utility_delta": treatment["score"] - control["score"],
            "anytime_auc_delta": treatment["anytime_auc"] - control["anytime_auc"],
            "validity_delta": float(treatment["valid"]) - float(control["valid"]),
            "replacement_delta": float(treatment["replaced_incumbent"]) - float(control["replaced_incumbent"]),
            "breakthrough_delta": float(treatment["breakthrough"]) - float(control["breakthrough"]),
            "evaluator_runtime_ratio": treatment["evaluator_seconds"] / control["evaluator_seconds"] if control["evaluator_seconds"] > 0 else float("inf"),
        })
    control = [state["arms"]["control"] for state in states]
    treatment = [state["arms"]["treatment"] for state in states]
    categories = {}
    for category in sorted(ELIGIBLE_CATEGORIES):
        category_effects = [effect for effect in effects if effect["task_category"] == category]
        categories[category] = {
            "states": len(category_effects),
            "median_final_utility_delta": statistics.median(effect["final_utility_delta"] for effect in category_effects),
            "median_score_resolution": statistics.median(effect["score_resolution"] for effect in category_effects),
            "median_anytime_auc_delta": statistics.median(effect["anytime_auc_delta"] for effect in category_effects),
        }
    positive = sum(effect["final_utility_delta"] > effect["score_resolution"] for effect in effects)
    negative = sum(effect["final_utility_delta"] < -effect["score_resolution"] for effect in effects)
    control_runtime = sum(item["evaluator_seconds"] for item in control)
    treatment_runtime = sum(item["evaluator_seconds"] for item in treatment)
    summary = {
        "states": len(states),
        "manipulation_passed_states": sum(state["manipulation_passed"] for state in states),
        "functional_escape_rate": {"control": statistics.fmean(float(item["escaped"]) for item in control), "treatment": statistics.fmean(float(item["escaped"]) for item in treatment)},
        "positive_utility_states_beyond_resolution": positive,
        "negative_utility_states_beyond_resolution": negative,
        "ties_within_resolution": len(states) - positive - negative,
        "replacement_rate": {"control": statistics.fmean(float(item["replaced_incumbent"]) for item in control), "treatment": statistics.fmean(float(item["replaced_incumbent"]) for item in treatment)},
        "breakthrough_rate": {"control": statistics.fmean(float(item["breakthrough"]) for item in control), "treatment": statistics.fmean(float(item["breakthrough"]) for item in treatment)},
        "valid_candidate_rate": {"control": statistics.fmean(float(item["valid"]) for item in control), "treatment": statistics.fmean(float(item["valid"]) for item in treatment)},
        "evaluator_runtime_seconds": {"control": control_runtime, "treatment": treatment_runtime},
        "aggregate_evaluator_runtime_ratio": treatment_runtime / control_runtime if control_runtime > 0 else float("inf"),
        "maximum_state_evaluator_runtime_ratio": max(effect["evaluator_runtime_ratio"] for effect in effects),
        "category_summaries": categories,
    }
    checks = {
        "all_states_technically_evaluable": all(state["technically_evaluable"] for state in states),
        "control_escape_states_maximum": sum(item["escaped"] for item in control) <= int(thresholds["control_escape_states_maximum"]),
        "treatment_escape_states_minimum": sum(item["escaped"] for item in treatment) >= int(thresholds["treatment_escape_states_minimum"]),
        "positive_utility_states_beyond_resolution_minimum": positive >= int(thresholds["positive_utility_states_beyond_resolution_minimum"]),
        "negative_utility_states_beyond_resolution_maximum": negative <= int(thresholds["negative_utility_states_beyond_resolution_maximum"]),
        "both_category_median_utility_delta_exceeds_resolution": all(item["median_final_utility_delta"] > item["median_score_resolution"] for item in categories.values()),
        "both_category_median_auc_delta_exceeds_half_resolution": all(item["median_anytime_auc_delta"] > item["median_score_resolution"] / 2 for item in categories.values()),
        "treatment_validity_rate_not_worse": summary["valid_candidate_rate"]["treatment"] >= summary["valid_candidate_rate"]["control"],
        "treatment_replacement_rate_strictly_higher": summary["replacement_rate"]["treatment"] > summary["replacement_rate"]["control"],
        "treatment_breakthrough_rate_not_worse": summary["breakthrough_rate"]["treatment"] >= summary["breakthrough_rate"]["control"],
        "aggregate_evaluator_runtime_ratio_maximum": summary["aggregate_evaluator_runtime_ratio"] <= float(thresholds["aggregate_evaluator_runtime_ratio_maximum"]),
        "maximum_state_evaluator_runtime_ratio": summary["maximum_state_evaluator_runtime_ratio"] <= float(thresholds["maximum_state_evaluator_runtime_ratio"]),
        "matched_zero_model_and_zero_token_resources": True,
    }
    return {"paired_effects": effects, "summary": summary}, {"passed": all(checks.values()), "checks": checks}


def _functional_signature(store: ArtifactStore, state: dict[str, Any], source: str) -> list[float]:
    proxy = {**state, "task_files": {**state["task_files"], "behavior_probe.py": state["task_files"]["functional_probe.py"]}}
    return _behavior_signature(store, proxy, source)


def _load_r5_authority(workspace: Path, expected_report_sha256: str) -> dict[str, Any]:
    report_path = workspace / "result-artifacts" / "records" / R5_REPORT_RECORD
    manifest_path = workspace / "protocol-artifacts" / "records" / R5_MANIFEST_RECORD
    report = _load_authority(report_path, expected_report_sha256, "CMI-R5 report")
    manifest = _load_json(manifest_path, report["manifest_digest"])
    if (
        report.get("verdict") != "CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES"
        or not report.get("primary_gate", {}).get("passed")
        or report.get("search_value_established")
        or report.get("fresh_search_value_budget_authorized")
        or manifest.get("protocol_id") != "CMI_R5_CONSUMED_DEV_CAUSAL_VALUE"
    ):
        raise RuntimeError("CMI-R5 did not authorize a bounded consumed-state replication protocol")
    return {
        "manifest": manifest,
        "report": report,
        "binding": {
            "workspace": str(workspace),
            "manifest_path": str(manifest_path),
            "manifest_digest": report["manifest_digest"],
            "report_path": str(report_path),
            "report_sha256": expected_report_sha256,
            "verdict": report["verdict"],
        },
    }


def _load_si2_authority(workspace: Path, discovery_sha256: str, confirmation_sha256: str) -> dict[str, Any]:
    manifest_path = workspace / "protocol-artifacts" / "records" / SI2_MANIFEST_RECORD
    discovery_path = workspace / "result-artifacts" / "records" / DISCOVERY_REPORT_RECORD
    confirmation_path = workspace / "result-artifacts" / "records" / CONFIRMATION_REPORT_RECORD
    discovery = _load_authority(discovery_path, discovery_sha256, "SI-2 discovery report")
    confirmation = _load_authority(confirmation_path, confirmation_sha256, "SI-2 confirmation report")
    manifest = _load_json(manifest_path, discovery["manifest_digest"])
    if (
        manifest.get("protocol_id") != SI2_PROTOCOL_ID
        or manifest.get("status") != "SI2_SEALED_PRE_MODEL"
        or discovery.get("protocol_id") != SI2_PROTOCOL_ID
        or discovery.get("task_count") != 9
        or confirmation.get("protocol_id") != SI2_PROTOCOL_ID
        or confirmation.get("confirmation_task_count") != 3
        or confirmation.get("verdict") != "SI2_WINNER_CONFIRMED_ON_WITHHELD_COHORT"
        or confirmation.get("manifest_digest") != manifest.get("manifest_digest")
    ):
        raise RuntimeError("SI-2 authority does not establish the complete consumed population")
    return {
        "manifest": manifest,
        "binding": {
            "workspace": str(workspace),
            "manifest_path": str(manifest_path),
            "manifest_digest": manifest["manifest_digest"],
            "discovery_report_path": str(discovery_path),
            "discovery_report_sha256": discovery_sha256,
            "confirmation_report_path": str(confirmation_path),
            "confirmation_report_sha256": confirmation_sha256,
        },
    }


def _verify_frozen_operator_bindings(r5_manifest: dict[str, Any]) -> None:
    required = {
        "functional_basin_escape.py",
        "local_behavior_control.py",
    }
    bindings = {
        Path(binding["path"]).name: binding
        for binding in r5_manifest["implementation_bindings"]
        if Path(binding["path"]).name in required
    }
    if set(bindings) != required:
        raise RuntimeError("CMI-R5 Operator bindings are incomplete")
    for binding in bindings.values():
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R5 frozen Operator binding drift")


def _load_manifest(workspace: Path, expected_digest: str) -> dict[str, Any]:
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("status") != "SEALED_PRE_REPLICATION_EVALUATION":
        raise RuntimeError("CMI-R6 manifest identity mismatch")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R6 repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R6 implementation binding drift")
    r5 = manifest["cmi_r5_authority"]
    _load_r5_authority(Path(r5["workspace"]), r5["report_sha256"])
    si2 = manifest["si2_consumed_authority"]
    _load_si2_authority(Path(si2["workspace"]), si2["discovery_report_sha256"], si2["confirmation_report_sha256"])
    return manifest


def _load_authority(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file() or digest_bytes(path.read_bytes()) != expected_sha256:
        raise RuntimeError(f"{label} hash mismatch")
    return _load_json(path)


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("cmi_causal_value.py"),
        Path(__file__).with_name("cmi_probe_calibration.py"),
        Path(__file__).with_name("si2.py"),
        Path(__file__).with_name("si2_tasks.py"),
        Path(__file__).with_name("parent_intervention_real.py"),
        Path(__file__).parents[1] / "operators" / "functional_basin_escape.py",
        Path(__file__).parents[1] / "operators" / "local_behavior_control.py",
    )
    return [{"path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())} for path in paths]
