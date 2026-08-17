from __future__ import annotations

import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


AUTOPSY_RECORD = "cmi-search-transmission-autopsy-r1.json"
SOURCE_MANIFEST_RECORD = "cmi-search-value-r1-v3-manifest.json"
SOURCE_REPORT_RECORD = "cmi-search-value-r1-v3-report.json"
SOURCE_VERDICT = "CMI_SEARCH_VALUE_NOT_ESTABLISHED"
R7_VERDICT = "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED"


def audit_cmi_search_transmission(
    source_workspace: Path,
    *,
    manifest_digest: str,
    source_report_sha256: str,
    r7_report_path: Path,
    r7_report_sha256: str,
    output_workspace: Path,
) -> dict[str, Any]:
    """Diagnose the closed V3 transmission trace without model or evaluator calls."""

    source_workspace = source_workspace.resolve()
    output_workspace = output_workspace.resolve()
    r7_report_path = r7_report_path.resolve()
    if output_workspace == source_workspace or source_workspace in output_workspace.parents:
        raise ValueError("autopsy output must remain outside the consumed CMI search workspace")

    manifest_path = source_workspace / "protocol-artifacts" / "records" / SOURCE_MANIFEST_RECORD
    report_path = source_workspace / "result-artifacts" / "records" / SOURCE_REPORT_RECORD
    manifest = _load_json(manifest_path)
    report = _load_json(report_path)
    r7_report = _load_json(r7_report_path)
    _verify_source_authority(
        manifest,
        report,
        manifest_path=manifest_path,
        report_path=report_path,
        manifest_digest=manifest_digest,
        report_sha256=source_report_sha256,
    )
    if digest_bytes(r7_report_path.read_bytes()) != r7_report_sha256:
        raise RuntimeError("CMI-R7 report SHA-256 mismatch")
    if (
        r7_report.get("verdict") != R7_VERDICT
        or r7_report.get("operator_admission")
        != "CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES"
    ):
        raise RuntimeError("autopsy requires the admitted and completed CMI-R7 authority")

    r7_by_category = _r7_category_authority(r7_report)
    task_ids = [str(task["task_id"]) for task in manifest.get("tasks", [])]
    if len(task_ids) != 6 or len(set(task_ids)) != 6:
        raise RuntimeError("CMI Search Value R1 autopsy requires the exact six-task V3 cohort")

    bindings = [
        _binding("autopsy_implementation", Path(__file__)),
        _binding("source_manifest", manifest_path),
        _binding("source_report", report_path),
        _binding("cmi_r7_report", r7_report_path),
    ]
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        task_path = source_workspace / "result-artifacts" / "records" / "tasks" / f"{task_id}.json"
        task = _load_json(task_path)
        if task.get("task_id") != task_id or task.get("manifest_digest") != manifest_digest:
            raise RuntimeError(f"V3 task identity or manifest binding mismatch: {task_id}")
        ledger_arm = "treatment" if task["causal_trace"]["eligible"] else "shared-prefix"
        ledger_path = source_workspace / "search" / task_id / ledger_arm / "ledger.sqlite3"
        bindings.extend(
            (
                _binding(f"task_receipt:{task_id}", task_path),
                _binding(f"{ledger_arm}_ledger:{task_id}", ledger_path),
            )
        )
        rows.append(_analyze_task(task, ledger_path, r7_by_category))

    eligible = [row for row in rows if row["eligible"]]
    if len(eligible) != 5:
        raise RuntimeError("closed V3 authority must contain exactly five eligible CMI invocations")
    if not all(row["invoked"] and row["accepted_descendant"] for row in eligible):
        raise RuntimeError("closed V3 authority requires five invoked and accepted CMI descendants")

    category_summary: dict[str, Any] = {}
    for category in sorted({row["task_category"] for row in eligible}):
        family_rows = [row for row in eligible if row["task_category"] == category]
        category_summary[category] = {
            "eligible_tasks": len(family_rows),
            "cmi_above_incumbent": sum(row["cmi_score_delta_vs_incumbent"] > 0 for row in family_rows),
            "cmi_above_simultaneous_control": sum(
                row["cmi_score_delta_vs_control_intervention"] > 0 for row in family_rows
            ),
            "median_cmi_score_delta_vs_incumbent": statistics.median(
                row["cmi_score_delta_vs_incumbent"] for row in family_rows
            ),
            "median_retention_threshold_gap": statistics.median(
                row["retention_threshold_gap"] for row in family_rows
            ),
        }

    score_threshold_failures = sum(row["retention_reason"] == "SCORE_THRESHOLD_NOT_MET" for row in eligible)
    true_parent_checks = sum(row["authoritative_downstream_parent_is_cmi"] for row in eligible)
    sequence_proxy_mismatches = sum(row["reported_parent_id_disagrees_with_authoritative_ledger"] for row in eligible)
    aligned_categories = all(row["r7_operator_output_digest_matches"] for row in eligible)
    objective_alignment = all(row["r7_score_resolution_matches"] for row in eligible) and aligned_categories

    result = {
        "status": "CMI_SEARCH_TRANSMISSION_AUTOPSY_R1_COMPLETE",
        "source_protocol": report["protocol_id"],
        "source_manifest_digest": manifest_digest,
        "source_report_sha256": source_report_sha256,
        "source_search_value_verdict": report["verdict"],
        "cmi_r7_report_sha256": r7_report_sha256,
        "claim_ceiling": "CONSUMED_V3_TRACE_DIAGNOSTIC_ONLY_NO_SEARCH_VALUE_OR_SUPERIORITY_CLAIM",
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
        "source_workspace_modified": False,
        "transmission_funnel": {
            "opportunities": sum(row["opportunity"] for row in rows),
            "eligible": len(eligible),
            "invoked": sum(row["invoked"] for row in rows),
            "accepted_descendants": sum(row["accepted_descendant"] for row in rows),
            "retained": sum(row["retained_after_intervention"] for row in rows),
            "authoritative_downstream_parent_was_cmi": true_parent_checks,
            "downstream_retained_contributions": sum(row["downstream_retained_contribution"] for row in rows),
        },
        "candidate_competition": {
            "eligible_tasks": len(eligible),
            "score_threshold_failures": score_threshold_failures,
            "cmi_above_incumbent": sum(row["cmi_score_delta_vs_incumbent"] > 0 for row in eligible),
            "cmi_above_simultaneous_control": sum(
                row["cmi_score_delta_vs_control_intervention"] > 0 for row in eligible
            ),
            "all_cmi_descendants_valid_but_below_retention_threshold": score_threshold_failures == len(eligible),
            "by_category": category_summary,
        },
        "objective_alignment": {
            "declared_score_level_aligned": objective_alignment,
            "same_supported_categories": sorted(r7_by_category) == sorted({row["task_category"] for row in rows}),
            "same_cmi_operator_output_digest_by_category": aligned_categories,
            "same_score_resolution_by_category": all(row["r7_score_resolution_matches"] for row in rows),
            "exact_cross_protocol_evaluator_binary_identity": "NOT_CLAIMED_TASK_SPECIFIC_EVALUATOR_DIGESTS",
        },
        "timing": {
            "downstream_steps_after_intervention": int(manifest["paired_execution"]["downstream_steps"]),
            "eligible_tasks_with_only_one_remaining_step": len(eligible)
            if int(manifest["paired_execution"]["downstream_steps"]) == 1
            else 0,
            "interpretation": "SHORT_PROPAGATION_WINDOW_SECONDARY_TO_IMMEDIATE_SCORE_DEFICIT",
        },
        "lineage_authority": {
            "authoritative_source": "treatment ledger CandidateSpec.parent_ids plus causal_trace",
            "reported_observation_parent_id_is_sequence_proxy": True,
            "eligible_tasks_with_sequence_proxy_mismatch": sequence_proxy_mismatches,
            "cached_downstream_candidates_conditioned_on_cmi_parent": true_parent_checks,
        },
        "forced_retention_counterfactual": {
            "immediate_score_effect_identifiable": True,
            "immediate_effect_positive_tasks": sum(row["cmi_score_delta_vs_incumbent"] > 0 for row in eligible),
            "downstream_compounding_effect": "NOT_IDENTIFIABLE_FROM_FROZEN_OFFLINE_TRACE",
            "reason": (
                "No cached downstream generation was conditioned on a CMI parent; reusing the sequential "
                "observations parent_id would contradict the authoritative CandidateSpec lineage."
            ),
            "new_model_or_evaluator_execution_performed": False,
        },
        "diagnostic_verdicts": [
            "CMI_DESCENDANT_COMPETITION_FAILURE_DETECTED_ON_CONSUMED_V3_TRACES",
            "CMI_SELECTION_INTEGRATION_DEFECT_NOT_ESTABLISHED",
            "FORCED_RETENTION_DOWNSTREAM_VALUE_NOT_IDENTIFIABLE_OFFLINE",
            "CMI_COMPOUNDING_SEARCH_VALUE_NOT_ESTABLISHED",
        ],
        "admission_decision": "DO_NOT_OPEN_FRESH_CMI_SEARCH_BUDGET",
        "next_allowed_question": (
            "A separately frozen consumed-task protocol may test an incumbent-conditioned or monotonic CMI "
            "operator before any selection-policy change; forced retention alone is not supported by these traces."
        ),
        "tasks": rows,
        "source_bindings": bindings,
    }
    record_path = ArtifactStore(output_workspace / "artifacts").write_record(AUTOPSY_RECORD, result)
    return {**result, "record_path": str(record_path), "record_sha256": digest_bytes(record_path.read_bytes())}


def _verify_source_authority(
    manifest: dict[str, Any],
    report: dict[str, Any],
    *,
    manifest_path: Path,
    report_path: Path,
    manifest_digest: str,
    report_sha256: str,
) -> None:
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != manifest_digest or digest_json(payload) != manifest_digest:
        raise RuntimeError("CMI Search Value R1 V3 manifest digest mismatch")
    if digest_bytes(report_path.read_bytes()) != report_sha256:
        raise RuntimeError("CMI Search Value R1 V3 report SHA-256 mismatch")
    if report.get("manifest_digest") != manifest_digest or report.get("verdict") != SOURCE_VERDICT:
        raise RuntimeError("autopsy requires the closed V3 non-establishment result")
    expected_code_sha = manifest.get("experiment_code_sha")
    if report.get("experiment_code_sha") != expected_code_sha:
        raise RuntimeError("V3 report experiment commit does not match its manifest")
    if not manifest_path.is_file():
        raise RuntimeError("CMI Search Value R1 V3 manifest is missing")


def _r7_category_authority(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for state in report.get("states", []):
        category = str(state["task_category"])
        digest = str(state["arms"]["treatment"]["trace"]["candidate_source_digest"])
        resolution = float(state["score_resolution"])
        entry = result.setdefault(category, {"operator_output_digests": set(), "score_resolutions": set()})
        entry["operator_output_digests"].add(digest)
        entry["score_resolutions"].add(resolution)
    for category, entry in result.items():
        if len(entry["operator_output_digests"]) != 1 or len(entry["score_resolutions"]) != 1:
            raise RuntimeError(f"CMI-R7 category authority is not stable: {category}")
    return result


def _analyze_task(
    task: dict[str, Any],
    ledger_path: Path,
    r7_by_category: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    category = str(task["task_category"])
    eligible = bool(task["causal_trace"]["eligible"])
    treatment = task["arms"]["CMI_ENABLED"]
    control = task["arms"]["CMI_DISABLED"]
    treatment_observations = treatment.get("observations", [])
    control_observations = control.get("observations", [])
    if len(treatment_observations) != 4 or len(control_observations) != 4:
        raise RuntimeError(f"unexpected V3 observation schedule: {task['task_id']}")

    r7 = r7_by_category.get(category)
    if r7 is None:
        raise RuntimeError(f"CMI-R7 authority has no category: {category}")
    resolution = float(task["score_resolution"])
    base = {
        "task_id": task["task_id"],
        "task_category": category,
        "opportunity": bool(task["causal_trace"]["opportunity"]),
        "eligible": eligible,
        "invoked": bool(task["causal_trace"]["invoked"]),
        "accepted_descendant": bool(task["causal_trace"]["accepted_descendant"]),
        "retained_after_intervention": bool(task["causal_trace"]["retained_after_intervention"]),
        "downstream_retained_contribution": bool(task["causal_trace"]["downstream_retained_contribution"]),
        "score_resolution": resolution,
        "r7_score_resolution_matches": resolution in r7["score_resolutions"],
    }
    if not eligible:
        return {
            **base,
            "retention_reason": "NOT_APPLICABLE_INELIGIBLE_SHARED_FALLBACK",
            "authoritative_downstream_parent_is_cmi": False,
            "reported_parent_id_disagrees_with_authoritative_ledger": False,
            "r7_operator_output_digest_matches": True,
        }

    candidates = _candidate_payloads(ledger_path)
    prefix = _exact_candidate(candidates, operator_id="paired_prefix_replay")
    cmi = _exact_candidate(candidates, operator_id="cmi_functional_basin_escape_v1")
    downstream = _exact_candidate(candidates, strategy_id="cmi_svr1_downstream_local")
    cmi_observation = treatment_observations[2]
    downstream_observation = treatment_observations[3]
    if cmi_observation["candidate_id"] != cmi["candidate_id"]:
        raise RuntimeError(f"CMI observation/candidate mismatch: {task['task_id']}")
    if downstream_observation["candidate_id"] != downstream["candidate_id"]:
        raise RuntimeError(f"downstream observation/candidate mismatch: {task['task_id']}")
    if cmi.get("parent_ids") != [prefix["candidate_id"]]:
        raise RuntimeError(f"CMI CandidateSpec parent mismatch: {task['task_id']}")

    incumbent_score = max(float(item["score"]) for item in treatment_observations[:2])
    cmi_score = float(cmi_observation["score"])
    control_score = float(control_observations[2]["score"])
    threshold = incumbent_score + resolution
    actual_parent_is_cmi = downstream.get("parent_ids") == [cmi["candidate_id"]]
    actual_parent_is_prefix = downstream.get("parent_ids") == [prefix["candidate_id"]]
    if not actual_parent_is_cmi and not actual_parent_is_prefix:
        raise RuntimeError(f"downstream CandidateSpec has unexpected parent: {task['task_id']}")
    reported_parent = downstream_observation.get("parent_id")
    trace_digest = str(task["causal_trace"]["operator_trace"]["candidate_source_digest"])
    return {
        **base,
        "incumbent_score": incumbent_score,
        "cmi_score": cmi_score,
        "control_intervention_score": control_score,
        "cmi_score_delta_vs_incumbent": cmi_score - incumbent_score,
        "cmi_score_delta_vs_control_intervention": cmi_score - control_score,
        "retention_threshold": threshold,
        "retention_threshold_gap": threshold - cmi_score,
        "retention_reason": "SCORE_THRESHOLD_NOT_MET" if cmi_score <= threshold else "UNEXPLAINED",
        "cmi_candidate_id": cmi["candidate_id"],
        "prefix_incumbent_candidate_id": prefix["candidate_id"],
        "downstream_candidate_id": downstream["candidate_id"],
        "authoritative_downstream_parent_id": downstream["parent_ids"][0],
        "authoritative_downstream_parent_is_cmi": actual_parent_is_cmi,
        "reported_observation_downstream_parent_id": reported_parent,
        "reported_parent_id_disagrees_with_authoritative_ledger": reported_parent != downstream["parent_ids"][0],
        "r7_operator_output_digest_matches": trace_digest in r7["operator_output_digests"],
    }


def _candidate_payloads(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"required treatment ledger missing: {path}")
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute("SELECT payload FROM candidates ORDER BY created_at").fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def _exact_candidate(
    candidates: list[dict[str, Any]],
    *,
    operator_id: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    matches = [
        item
        for item in candidates
        if (operator_id is None or item.get("operator_id") == operator_id)
        and (strategy_id is None or item.get("strategy_id") == strategy_id)
    ]
    if len(matches) != 1:
        label = operator_id or strategy_id
        raise RuntimeError(f"expected exactly one candidate for {label}, found {len(matches)}")
    return matches[0]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required autopsy source missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"autopsy source is not a JSON object: {path}")
    return value


def _binding(role: str, path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"required autopsy binding missing: {path}")
    return {"role": role, "path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())}
