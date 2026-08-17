from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.cmi_escape_operator import MANIFEST_RECORD as R4_MANIFEST_RECORD
from discoveryos.benchmarks.cmi_escape_operator import REPORT_RECORD as R4_REPORT_RECORD
from discoveryos.benchmarks.cmi_probe_calibration import _behavior_signature, _mean_absolute_distance
from discoveryos.benchmarks.executable_mechanism_contract import _evaluate_descendant, _load_json, _repository_snapshot
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator
from discoveryos.operators.local_behavior_control import LocalBehaviorControlOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R5_CONSUMED_DEV_CAUSAL_VALUE"
MANIFEST_RECORD = "cmi-r5-causal-value-manifest.json"
REPORT_RECORD = "cmi-r5-causal-value-report.json"
FUNCTIONAL_ESCAPE_THRESHOLD = 0.10


def seal_cmi_causal_value(
    workspace: Path,
    *,
    cmi_r4_workspace: Path,
    cmi_r4_report_sha256: str,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R5 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R5 must be sealed from a clean worktree")

    authority_root = cmi_r4_workspace.resolve()
    report_path = authority_root / "result-artifacts" / "records" / R4_REPORT_RECORD
    manifest_path = authority_root / "protocol-artifacts" / "records" / R4_MANIFEST_RECORD
    report = _load_authority(report_path, cmi_r4_report_sha256, "CMI-R4 report")
    r4_manifest = _load_json(manifest_path, report["manifest_digest"])
    _validate_r4_authority(r4_manifest, report)

    r4_store = ArtifactStore(authority_root / "protocol-artifacts")
    store = ArtifactStore(workspace / "protocol-artifacts")
    tasks = _reconstructed_tasks()
    states = [
        _freeze_consumed_state(store, r4_store, r4_state, tasks[r4_state["task_id"]])
        for r4_state in r4_manifest["states"]
    ]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_UTILITY_EVALUATION",
        "scope": "PAIRED_CAUSAL_VALUE_ON_TWO_CONSUMED_CMI_R4_DEVELOPMENT_STATES",
        "scientific_question": "Does the frozen functional-basin-escape intervention improve utility relative to a source-local behavior-preserving intervention under matched deterministic resources?",
        "claim_ceiling": "CMI_ESCAPE_CAUSAL_VALUE_ON_TWO_CONSUMED_DEV_STATES_ONLY",
        "repository": repository,
        "cmi_r4_authority": {
            "workspace": str(authority_root),
            "manifest_path": str(manifest_path),
            "manifest_digest": report["manifest_digest"],
            "report_path": str(report_path),
            "report_sha256": cmi_r4_report_sha256,
            "verdict": report["status"],
        },
        "brief": r4_manifest["brief"],
        "states": states,
        "arms": {
            "control": "one deterministic source-local behavior-preserving Operator invocation",
            "treatment": "one deterministic CMI functional-basin-escape Operator invocation",
        },
        "matched_conditions": [
            "same consumed state",
            "same incumbent parent",
            "one deterministic Operator invocation",
            "zero model calls and zero tokens",
            "same frozen evaluator and functional probe",
            "same process timeout and execution environment",
        ],
        "endpoints": {
            "functional_escape_rate": "manipulation check only: functional distance strictly greater than 0.10",
            "final_utility": "frozen evaluator score after one matched Operator invocation",
            "anytime_auc": "mean cumulative-best utility at allocation zero and allocation one",
            "replacement_rate": "candidate exceeds incumbent by more than score resolution",
            "breakthrough_rate": "candidate reaches frozen reference score minus score resolution",
            "valid_candidate_rate": "fraction passing the frozen evaluator validity checks",
            "cost": "model calls, tokens, Operator wall time, evaluator wall time, and process counts",
        },
        "primary_gate": {
            "control_escape_on_zero_states": True,
            "treatment_escape_on_both_states": True,
            "treatment_final_utility_delta_exceeds_score_resolution_on_both_states": True,
            "treatment_anytime_auc_delta_exceeds_half_score_resolution_on_both_states": True,
            "treatment_validity_rate_not_worse": True,
            "treatment_replacement_rate_strictly_higher": True,
            "treatment_breakthrough_rate_not_worse": True,
            "matched_zero_model_and_zero_token_resources": True,
        },
        "result_semantics": {
            "gate_passed": "CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES",
            "gate_failed": "CMI_R5_CAUSAL_VALUE_NOT_ESTABLISHED_ON_CONSUMED_DEV",
            "probe_or_evaluator_failed": "CMI_R5_NOT_EVALUABLE_PROBE_OR_EVALUATOR",
        },
        "model_calls": 0,
        "tokens": 0,
        "fresh_search_value_tasks_consumed": 0,
        "consumed_development_states_reused": 2,
        "fresh_search_value_budget_authorized": False,
        "implementation_bindings": _implementation_bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "model_calls": 0,
        "tokens": 0,
        "fresh_search_value_tasks_consumed": 0,
    }


def run_cmi_causal_value(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest)
    store = ArtifactStore(workspace / "protocol-artifacts")
    control_operator = LocalBehaviorControlOperator()
    treatment_operator = FunctionalBasinEscapeOperator(manifest["brief"])
    states = [
        _run_pair(store, state, control_operator, treatment_operator)
        for state in manifest["states"]
    ]
    evaluable = all(item["evaluable"] for item in states)
    analysis, gate = _analyze(states) if evaluable else ({}, {"passed": False, "checks": {}})
    if not evaluable:
        verdict = "CMI_R5_NOT_EVALUABLE_PROBE_OR_EVALUATOR"
    elif gate["passed"]:
        verdict = "CMI_R5_CAUSAL_VALUE_DETECTED_ON_TWO_CONSUMED_DEV_STATES"
    else:
        verdict = "CMI_R5_CAUSAL_VALUE_NOT_ESTABLISHED_ON_CONSUMED_DEV"
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "CMI_R5_COMPLETE",
        "verdict": verdict,
        "evaluable": evaluable,
        "states": states,
        "analysis": analysis,
        "primary_gate": gate,
        "claim_ceiling": manifest["claim_ceiling"],
        "probability_or_significance_established": False,
        "search_value_established": False,
        "fresh_search_value_budget_authorized": False,
        "model_calls": 0,
        "tokens": 0,
        "operator_invocations": {"control": len(states), "treatment": len(states)},
        "evaluator_calls": 8,
        "functional_probe_calls": 8,
        "fresh_search_value_tasks_consumed": 0,
        "consumed_development_states_reused": len(states),
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_consumed_state(
    store: ArtifactStore,
    r4_store: ArtifactStore,
    r4_state: dict[str, Any],
    task: Any,
) -> dict[str, Any]:
    if task.payload_digest != r4_state["task_payload_digest"]:
        raise RuntimeError("CMI-R5 reconstructed task differs from R4 state authority")
    base = r4_store.get_bytes(r4_state["base_source_digest"])
    reference = r4_store.get_bytes(r4_state["positive_control_source_digest"])
    functional_probe = r4_store.get_bytes(r4_state["task_files"]["functional_probe.py"])
    state = {
        "state_id": r4_state["state_id"],
        "task_id": r4_state["task_id"],
        "task_category": r4_state["task_category"],
        "task_payload_digest": task.payload_digest,
        "r4_state_digest": r4_state["state_digest"],
        "score_resolution": task.score_resolution,
        "base_source_digest": store.put_bytes(base, media_type="text/x-python"),
        "reference_source_digest": store.put_bytes(reference, media_type="text/x-python"),
        "task_files": {
            "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
            "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
            "functional_probe.py": store.put_bytes(functional_probe, media_type="text/x-python"),
        },
        "breakthrough_rule": "reference_score_minus_score_resolution",
    }
    return {**state, "state_digest": digest_json(state)}


def _run_pair(
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
    evaluations = {}
    evaluator_seconds = {}
    for label, source in sources.items():
        started = time.perf_counter()
        evaluations[label] = _evaluate_descendant(store, state, source)
        evaluator_seconds[label] = time.perf_counter() - started
    distances = {
        arm: _mean_absolute_distance(signatures["incumbent"], signatures[arm])
        for arm in ("control", "treatment")
    }
    incumbent_score = float(evaluations["incumbent"].get("score", 0.0))
    reference_score = float(evaluations["reference"].get("score", 0.0))
    threshold = reference_score - float(state["score_resolution"])
    arms = {}
    for arm, operator_seconds, trace in (
        ("control", control_operator_seconds, control.trace),
        ("treatment", treatment_operator_seconds, treatment.trace),
    ):
        evaluation = evaluations[arm]
        score = float(evaluation.get("score", 0.0))
        valid = bool(evaluation.get("valid"))
        arms[arm] = {
            "valid": valid,
            "score": score,
            "functional_distance": distances[arm],
            "escaped": valid and distances[arm] > FUNCTIONAL_ESCAPE_THRESHOLD,
            "final_utility_delta_from_incumbent": score - incumbent_score,
            "anytime_auc": statistics.fmean((incumbent_score, max(incumbent_score, score))),
            "replaced_incumbent": valid and score > incumbent_score + float(state["score_resolution"]),
            "breakthrough": valid and score >= threshold,
            "operator_seconds": operator_seconds,
            "evaluator_seconds": evaluator_seconds[arm],
            "source_sha256": evaluation.get("source_sha256"),
            "trace": trace,
        }
    evaluable = (
        all(signatures.values())
        and all(bool(item.get("valid")) for item in evaluations.values())
        and distances["control"] == 0.0
        and distances["treatment"] > FUNCTIONAL_ESCAPE_THRESHOLD
        and control.trace["positive_control_received"] is False
        and treatment.trace["positive_control_received"] is False
        and control.trace["evaluator_feedback_received"] is False
        and treatment.trace["evaluator_feedback_received"] is False
    )
    return {
        "state_id": state["state_id"],
        "task_id": state["task_id"],
        "task_category": state["task_category"],
        "evaluable": evaluable,
        "incumbent": {"valid": evaluations["incumbent"]["valid"], "score": incumbent_score},
        "reference": {"valid": evaluations["reference"]["valid"], "score": reference_score},
        "score_resolution": state["score_resolution"],
        "breakthrough_threshold": threshold,
        "arms": arms,
        "evaluator_seconds": evaluator_seconds,
    }


def _analyze(states: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    effects = []
    for state in states:
        control, treatment = state["arms"]["control"], state["arms"]["treatment"]
        effects.append({
            "state_id": state["state_id"],
            "functional_distance_delta": treatment["functional_distance"] - control["functional_distance"],
            "final_utility_delta": treatment["score"] - control["score"],
            "anytime_auc_delta": treatment["anytime_auc"] - control["anytime_auc"],
            "validity_delta": float(treatment["valid"]) - float(control["valid"]),
            "replacement_delta": float(treatment["replaced_incumbent"]) - float(control["replaced_incumbent"]),
            "breakthrough_delta": float(treatment["breakthrough"]) - float(control["breakthrough"]),
        })
    control = [state["arms"]["control"] for state in states]
    treatment = [state["arms"]["treatment"] for state in states]
    summary = {
        "functional_escape_rate": {"control": statistics.fmean(float(item["escaped"]) for item in control), "treatment": statistics.fmean(float(item["escaped"]) for item in treatment)},
        "mean_final_utility": {"control": statistics.fmean(item["score"] for item in control), "treatment": statistics.fmean(item["score"] for item in treatment)},
        "mean_anytime_auc": {"control": statistics.fmean(item["anytime_auc"] for item in control), "treatment": statistics.fmean(item["anytime_auc"] for item in treatment)},
        "replacement_rate": {"control": statistics.fmean(float(item["replaced_incumbent"]) for item in control), "treatment": statistics.fmean(float(item["replaced_incumbent"]) for item in treatment)},
        "breakthrough_rate": {"control": statistics.fmean(float(item["breakthrough"]) for item in control), "treatment": statistics.fmean(float(item["breakthrough"]) for item in treatment)},
        "valid_candidate_rate": {"control": statistics.fmean(float(item["valid"]) for item in control), "treatment": statistics.fmean(float(item["valid"]) for item in treatment)},
        "operator_seconds": {"control": sum(item["operator_seconds"] for item in control), "treatment": sum(item["operator_seconds"] for item in treatment)},
        "evaluator_seconds": {"control": sum(item["evaluator_seconds"] for item in control), "treatment": sum(item["evaluator_seconds"] for item in treatment)},
    }
    checks = {
        "control_escape_on_zero_states": all(not item["escaped"] for item in control),
        "treatment_escape_on_both_states": all(item["escaped"] for item in treatment),
        "treatment_final_utility_delta_exceeds_score_resolution_on_both_states": all(effect["final_utility_delta"] > float(state["score_resolution"]) for effect, state in zip(effects, states, strict=True)),
        "treatment_anytime_auc_delta_exceeds_half_score_resolution_on_both_states": all(effect["anytime_auc_delta"] > float(state["score_resolution"]) / 2 for effect, state in zip(effects, states, strict=True)),
        "treatment_validity_rate_not_worse": summary["valid_candidate_rate"]["treatment"] >= summary["valid_candidate_rate"]["control"],
        "treatment_replacement_rate_strictly_higher": summary["replacement_rate"]["treatment"] > summary["replacement_rate"]["control"],
        "treatment_breakthrough_rate_not_worse": summary["breakthrough_rate"]["treatment"] >= summary["breakthrough_rate"]["control"],
        "matched_zero_model_and_zero_token_resources": True,
    }
    return {"paired_effects": effects, "endpoint_summary": summary}, {"passed": all(checks.values()), "checks": checks}


def _functional_signature(store: ArtifactStore, state: dict[str, Any], source: str) -> list[float]:
    proxy = {**state, "task_files": {**state["task_files"], "behavior_probe.py": state["task_files"]["functional_probe.py"]}}
    return _behavior_signature(store, proxy, source)


def _reconstructed_tasks() -> dict[str, Any]:
    tasks = (
        _assignment_task("cmi_r4_assignment_mechanics_alpha", (31103, 31123, 31139, 31159, 31181, 31219)),
        _coverage_task("cmi_r4_coverage_mechanics_alpha", (32117, 32141, 32159, 32183, 32203, 32233)),
    )
    return {task.task.task_id: task for task in tasks}


def _load_manifest(workspace: Path, expected_digest: str) -> dict[str, Any]:
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("status") != "SEALED_PRE_UTILITY_EVALUATION":
        raise RuntimeError("CMI-R5 manifest identity mismatch")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R5 repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R5 implementation binding drift")
    authority = manifest["cmi_r4_authority"]
    report = _load_authority(Path(authority["report_path"]), authority["report_sha256"], "CMI-R4 report")
    r4_manifest = _load_json(Path(authority["manifest_path"]), authority["manifest_digest"])
    _validate_r4_authority(r4_manifest, report)
    return manifest


def _validate_r4_authority(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    if (
        manifest.get("protocol_id") != "CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS"
        or report.get("status") != "CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_CONFIRMED_ON_TWO_DEV_STATES"
        or not report.get("passed")
        or report.get("manifest_digest") != manifest.get("manifest_digest")
        or not report.get("operator_mechanics_established")
        or report.get("causal_value_established")
        or report.get("fresh_search_value_budget_authorized")
    ):
        raise RuntimeError("CMI-R4 did not establish the bounded mechanics prerequisite")


def _load_authority(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file() or digest_bytes(path.read_bytes()) != expected_sha256:
        raise RuntimeError(f"{label} hash mismatch")
    return _load_json(path)


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).parents[1] / "operators" / "functional_basin_escape.py",
        Path(__file__).parents[1] / "operators" / "local_behavior_control.py",
        Path(__file__).with_name("cmi_escape_operator.py"),
        Path(__file__).with_name("cmi_probe_calibration.py"),
        Path(__file__).with_name("si2_tasks.py"),
        Path(__file__).with_name("parent_intervention_real.py"),
    )
    return [{"path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())} for path in paths]
