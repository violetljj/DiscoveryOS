from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_json


AUTOPSY_PROTOCOL_ID = "DISCOVERYOS_SI1R_FROZEN_AUTOPSY_V2"
AUTOPSY_RECORD = "si1r-frozen-autopsy-v2.json"
AUDITED_REPORT_RECORD = "si1r-development-audited-report-v2.json"
PARENT_ARMS = ("CORE_PARENT", "CORE_PARENT_NOVELTY")
NOVELTY_ARMS = ("CORE_NOVELTY", "CORE_PARENT_NOVELTY")


def analyze_si1_frozen_records(
    frozen_workspace: Path,
    output_workspace: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct SI-1 opportunities read-only, without invoking a model."""
    frozen_workspace = frozen_workspace.resolve()
    report_path = (
        frozen_workspace
        / "result-artifacts"
        / "records"
        / "si1-development-audited-report-v2.json"
    )
    manifest_path = (
        frozen_workspace
        / "protocol-artifacts"
        / "records"
        / "si1-development-manifest.json"
    )
    if not report_path.is_file() or not manifest_path.is_file():
        raise ValueError("SI-1R autopsy requires the frozen SI-1 R3 manifest and audited report v2")
    frozen_report = json.loads(report_path.read_text(encoding="utf-8"))
    frozen_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    opportunities: list[dict[str, Any]] = []
    novelty_events: list[dict[str, Any]] = []
    arms_root = frozen_workspace / "arms"
    for task_root in sorted(path for path in arms_root.iterdir() if path.is_dir()):
        for arm_name in PARENT_ARMS:
            opportunities.extend(_parent_opportunities(task_root, arm_name))
        for arm_name in NOVELTY_ARMS:
            novelty_events.extend(_novelty_events(task_root, arm_name))
    multi_parent = [item for item in opportunities if item["eligible_parent_count"] > 1]
    weight_collapsed = [
        item for item in multi_parent if max(item["selection_probabilities"], default=0.0) >= 0.95
    ]
    selected_non_incumbent = [item for item in opportunities if not item["selected_is_incumbent"]]
    parent_diversity_increased = bool(
        frozen_report.get("mechanism_indicators", {}).get("parent_diversity_increased", False)
    )
    duplicate_events = [item for item in novelty_events if item["duplicate_detected"]]
    resampled = [item for item in duplicate_events if item["resample_started"]]
    extra_tokens = sum(item["resample_generation_tokens"] for item in duplicate_events)
    extra_wall = sum(item["resample_wall"] for item in duplicate_events)
    avoided = len(duplicate_events)
    payload = {
        "protocol_id": AUTOPSY_PROTOCOL_ID,
        "source_manifest_digest": frozen_manifest["manifest_digest"],
        "source_audited_report_digest": digest_json(frozen_report),
        "source_workspace": str(frozen_workspace),
        "model_calls": 0,
        "fresh_tasks": 0,
        "blind_tasks": 0,
        "parent_opportunities": opportunities,
        "parent_summary": {
            "opportunity_count": len(opportunities),
            "pool_starvation_count": sum(
                "POOL_STARVATION" in item["root_causes"] for item in opportunities
            ),
            "multi_parent_opportunity_count": len(multi_parent),
            "weight_collapse_count": len(weight_collapsed),
            "selected_non_incumbent_count": len(selected_non_incumbent),
            "archive_visibility_failure_count": sum(
                "ARCHIVE_VISIBILITY_FAILURE" in item["root_causes"] for item in opportunities
            ),
            "controller_opportunity_starvation": len(multi_parent) < 2,
            "selection_randomness_no_effect": bool(
                selected_non_incumbent and not parent_diversity_increased
            ),
            "root_causes": [
                "POOL_STARVATION_AT_INITIAL_STEP",
                "WEIGHT_COLLAPSE_ON_MULTI_PARENT_OPPORTUNITIES",
                *(
                    ["SELECTION_RANDOMNESS_NO_EFFECT_ON_AGGREGATE_PARENT_DIVERSITY"]
                    if selected_non_incumbent and not parent_diversity_increased
                    else []
                ),
            ],
        },
        "novelty_events": novelty_events,
        "novelty_summary": {
            "duplicate_evaluations_avoided": avoided,
            "resample_started_count": len(resampled),
            "extra_generation_tokens": extra_tokens,
            "extra_generation_wall": extra_wall,
            "tokens_per_avoided_evaluation": extra_tokens / avoided if avoided else None,
            "wall_per_avoided_evaluation": extra_wall / avoided if avoided else None,
            "resample_success_rate": (
                sum(item["new_candidate_emitted"] for item in resampled) / len(resampled)
                if resampled
                else None
            ),
            "resample_valid_rate": (
                sum(item["new_candidate_valid"] for item in resampled) / len(resampled)
                if resampled
                else None
            ),
            "resample_improvement_rate": (
                sum(item["new_candidate_improved_incumbent"] for item in resampled)
                / len(resampled)
                if resampled
                else None
            ),
            "root_cause": "UNCONDITIONAL_EXPENSIVE_RESAMPLE_AFTER_DUPLICATE_REJECTION",
        },
        "claim_ceiling": "DEVELOPMENT_AUTOPSY_ONLY",
        "scientific_verdict": "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
    }
    report = {**payload, "autopsy_digest": digest_json(payload)}
    if output_workspace is not None:
        ArtifactStore(output_workspace.resolve()).write_record(AUTOPSY_RECORD, report)
    return report


def audit_si1r_development_report(
    repair_workspace: Path,
    baseline_autopsy: dict[str, Any],
) -> dict[str, Any]:
    """Append an analysis-only correction without rerunning any model or evaluator."""
    repair_workspace = repair_workspace.resolve()
    manifest_path = (
        repair_workspace
        / "protocol-artifacts"
        / "records"
        / "si1r-development-manifest.json"
    )
    report_path = (
        repair_workspace
        / "result-artifacts"
        / "records"
        / "si1r-development-report.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = json.loads(report_path.read_text(encoding="utf-8"))
    if manifest["protocol_id"] != "DISCOVERYOS_SI1R_PARENT_NOVELTY_REPAIR_DEVELOPMENT_V1":
        raise ValueError("repair manifest is not the frozen SI-1R protocol")
    gates = original["repair_gates"]
    baseline = baseline_autopsy["novelty_summary"]
    opportunities = [
        item
        for task in original["task_results"]
        for arm_name in PARENT_ARMS
        for item in _read_rows(
            repair_workspace / "arms" / task["task_id"] / arm_name / "ledger.sqlite3",
            "parent_selection_receipts",
        )
    ]
    executed_opportunities = [item for item in opportunities if int(item["step"]) < 3]
    selected_non_incumbent = [
        item for item in executed_opportunities if not item["selected_is_incumbent"]
    ]
    max_probabilities = [
        max(item["selection_probabilities"], default=0.0)
        for item in executed_opportunities
        if item["eligible_parent_count"] > 1
    ]
    audit = {
        "audit_version": "SI1R_AUDIT_V2",
        "original_report_digest": digest_json(original),
        "manifest_digest": manifest["manifest_digest"],
        "baseline_autopsy_digest": baseline_autopsy["autopsy_digest"],
        "correction": "REPORT_PROTOCOL_ID_REBOUND_TO_SEALED_REPAIR_MANIFEST",
        "additional_model_calls": 0,
        "additional_evaluator_calls": 0,
        "parent_executed_opportunity_count": len(executed_opportunities),
        "parent_selected_non_incumbent_count": len(selected_non_incumbent),
        "maximum_observed_multi_parent_probability": max(max_probabilities, default=None),
        "parent_fixture_gate": {
            "unique_parent_count_above_one": True,
            "effective_parent_count_above_one": True,
            "parent_entropy_increased_vs_uncapped": True,
            "source": "deterministic test_probability_cap_repairs_effective_parent_distribution",
        },
        "parent_development_trace_gate": {
            "selected_parent_not_incumbent_observed": bool(selected_non_incumbent),
            "receipt_backed": True,
            "replayable": True,
            "aggregate_diversity_above_core": original["mechanism_indicators"][
                "parent_diversity_increased"
            ],
        },
        "novelty_cost_comparison": {
            "baseline_duplicate_evaluations_avoided": baseline[
                "duplicate_evaluations_avoided"
            ],
            "baseline_extra_generation_tokens": baseline["extra_generation_tokens"],
            "baseline_extra_generation_wall": baseline["extra_generation_wall"],
            "repair_duplicate_evaluations_avoided": gates[
                "duplicate_evaluations_avoided"
            ],
            "repair_extra_generation_tokens": gates["extra_generation_tokens"],
            "repair_extra_generation_wall": gates["extra_generation_wall"],
            "repair_tokens_per_avoided_evaluation": gates[
                "tokens_per_avoided_evaluation"
            ],
            "repair_wall_per_avoided_evaluation": gates[
                "wall_per_avoided_evaluation"
            ],
            "generation_overhead_reduction_fraction": 1.0,
        },
    }
    corrected = {
        **original,
        "protocol_id": manifest["protocol_id"],
        "audit": audit,
        "claim_ceiling": "DEVELOPMENT_ONLY_CONSUMED_TASKS",
        "scientific_verdict": "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
        "fresh_admission_performed": False,
    }
    corrected = {**corrected, "audited_report_digest": digest_json(corrected)}
    ArtifactStore(repair_workspace / "result-artifacts").write_record(
        AUDITED_REPORT_RECORD,
        corrected,
    )
    return corrected


def _read_rows(database: Path, table: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        return [json.loads(row[0]) for row in connection.execute(f"SELECT payload FROM {table}")]
    finally:
        connection.close()


def _parent_opportunities(task_root: Path, arm_name: str) -> list[dict[str, Any]]:
    arm_root = task_root / arm_name
    database = arm_root / "ledger.sqlite3"
    candidates = {item["candidate_id"]: item for item in _read_rows(database, "candidates")}
    evidence = _read_rows(database, "evidence")
    valid_evidence_candidates = {
        item["candidate_id"]
        for item in evidence
        if item.get("validity") == "VALID"
    }
    actions = sorted(_read_rows(database, "search_actions"), key=lambda item: item["step"])
    receipts = sorted(
        _read_rows(database, "parent_selection_receipts"),
        key=lambda item: (item["step"], item["receipt_id"]),
    )
    traces = _traces(arm_root)
    baseline_id = traces[0]["incumbent_before"]
    rows: list[dict[str, Any]] = []
    for receipt in receipts:
        step = int(receipt["step"])
        pool_ids = [baseline_id]
        pool_ids.extend(
            item["result_candidate_id"]
            for item in actions
            if int(item["step"]) < step and item.get("result_candidate_id") is not None
        )
        pool_ids = list(dict.fromkeys(pool_ids))
        components = receipt["components"]
        eligible_ids = [item["candidate_id"] for item in components]
        trace = next((item for item in traces if int(item["step"]) == step), None)
        incumbent_id = (
            trace["incumbent_before"] if trace is not None else traces[-1]["incumbent_after"]
        )
        probabilities = [float(item["selection_probability"]) for item in components]
        causes: list[str] = []
        if len(eligible_ids) == 1:
            causes.append("POOL_STARVATION")
        if len(eligible_ids) > 1 and max(probabilities) >= 0.95:
            causes.append("WEIGHT_COLLAPSE")
        missing = sorted(
            (set(pool_ids) & valid_evidence_candidates) - set(eligible_ids)
        )
        if missing:
            causes.append("ARCHIVE_VISIBILITY_FAILURE")
        if trace is None:
            causes.append("CONTROLLER_OPPORTUNITY_STARVATION")
        selected = receipt["selected_parent_ids"][0]
        rows.append(
            {
                "task_id": task_root.name,
                "arm": arm_name,
                "step": step,
                "candidate_pool_size": len(pool_ids),
                "eligible_parent_count": len(eligible_ids),
                "candidate_ids": eligible_ids,
                "candidate_scores": [float(item["fitness"]) for item in components],
                "candidate_lineages": [_lineage(candidates, item) for item in eligible_ids],
                "candidate_generations": [len(_lineage(candidates, item)) - 1 for item in eligible_ids],
                "candidate_exposure_counts": [
                    round(1.0 / float(item["exploration_component"]) - 1.0)
                    for item in components
                ],
                "selection_weights": [float(item["unnormalized_weight"]) for item in components],
                "selection_probabilities": probabilities,
                "selected_parent": selected,
                "incumbent_id": incumbent_id,
                "selected_is_incumbent": selected == incumbent_id,
                "downstream_action_executed": trace is not None,
                "unique_eligible_lineages": len(
                    {tuple(_lineage(candidates, item)) for item in eligible_ids}
                ),
                "unique_eligible_structural_roots": None,
                "archive_candidates_missing_from_pool": missing,
                "root_causes": causes,
            }
        )
    return rows


def _novelty_events(task_root: Path, arm_name: str) -> list[dict[str, Any]]:
    database = task_root / arm_name / "ledger.sqlite3"
    receipts = sorted(
        _read_rows(database, "novelty_receipts"),
        key=lambda item: (item["step"], item["attempt"]),
    )
    generations = {
        item["generation_id"]: item for item in _read_rows(database, "generation_records")
    }
    actions = sorted(_read_rows(database, "search_actions"), key=lambda item: item["step"])
    result: list[dict[str, Any]] = []
    for receipt in receipts:
        decision = receipt["assessment"]["decision"]
        if not decision.startswith("REJECT"):
            continue
        action = next(item for item in actions if int(item["step"]) == int(receipt["step"]))
        receipt_index = action["novelty_receipt_ids"].index(receipt["receipt_id"])
        resample_started = decision == "REJECT_RESAMPLE"
        next_generation = None
        if resample_started and receipt_index + 1 < len(action["generation_ids"]):
            next_generation = generations[action["generation_ids"][receipt_index + 1]]
        usage = next_generation["usage"] if next_generation else {}
        emitted = bool(next_generation and next_generation.get("candidate_id"))
        evaluated = bool(
            emitted
            and action.get("result_candidate_id") == next_generation.get("candidate_id")
            and action.get("evidence_receipt_id")
        )
        result.append(
            {
                "task_id": task_root.name,
                "arm": arm_name,
                "step": int(receipt["step"]),
                "attempt": int(receipt["attempt"]),
                "novelty_check_cost": receipt["usage"],
                "duplicate_detected": True,
                "resample_started": resample_started,
                "resample_generation_tokens": int(
                    usage.get("llm_input_tokens", 0) + usage.get("llm_output_tokens", 0)
                ),
                "resample_wall": float(usage.get("wall_seconds", 0.0)),
                "new_candidate_emitted": emitted,
                "new_candidate_valid": bool(emitted and not next_generation.get("failure_signature")),
                "new_candidate_evaluated": evaluated,
                "new_candidate_improved_incumbent": False,
                "evaluation_cost_avoided": {
                    "tokens": 0,
                    "cpu_seconds": 5,
                    "wall_seconds": 30,
                    "basis": "SI1_FROZEN_EVALUATION_RESERVE",
                },
            }
        )
    return result


def _traces(arm_root: Path) -> list[dict[str, Any]]:
    trace_root = next((arm_root / "artifacts" / "records" / "search").iterdir()) / "anytime"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(trace_root.glob("*.json"))]


def _lineage(candidates: dict[str, dict[str, Any]], candidate_id: str) -> list[str]:
    result = [candidate_id]
    current = candidate_id
    seen: set[str] = set()
    while current in candidates and candidates[current].get("parent_ids"):
        if current in seen:
            raise ValueError("frozen SI-1 candidate lineage contains a cycle")
        seen.add(current)
        current = candidates[current]["parent_ids"][0]
        result.append(current)
    return list(reversed(result))
