from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.benchmark_bank import (
    ClaimPurpose,
    IntegrationStatus,
    ShardRole,
    assess_shard_access,
    load_benchmark_bank,
)
from discoveryos.benchmarks.cmi_r7_fresh_tasks import PROTOCOL_SALT, cmi_r7_fresh_tasks
from discoveryos.benchmarks.cmi_replication_admission import (
    MANIFEST_RECORD as R6_MANIFEST_RECORD,
    REPORT_RECORD as R6_REPORT_RECORD,
    _run_replication_pair,
)
from discoveryos.benchmarks.executable_mechanism_contract import _load_json, _repository_snapshot
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator
from discoveryos.operators.local_behavior_control import LocalBehaviorControlOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R7_FRESH_CAUSAL_REPLICATION"
MANIFEST_RECORD = "cmi-r7-fresh-causal-manifest.json"
REPORT_RECORD = "cmi-r7-fresh-causal-report.json"
EXPECTED_STATES = 6
EXPECTED_STATES_PER_FAMILY = 3
ELIGIBLE_CATEGORIES = {"capacitated_cost_assignment", "budgeted_weighted_coverage"}
DEFAULT_BANK_REGISTRY = Path(__file__).parents[3] / "benchmarks" / "bank" / "v1" / "registry.json"


def seal_cmi_fresh_causal_validation(
    workspace: Path,
    *,
    cmi_r6_workspace: Path,
    cmi_r6_report_sha256: str,
    bank_registry_path: Path = DEFAULT_BANK_REGISTRY,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R7 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R7 must be sealed from a clean worktree")

    r6 = _load_r6_authority(cmi_r6_workspace.resolve(), cmi_r6_report_sha256)
    _verify_frozen_operator_bindings(r6["manifest"])
    registry_path = bank_registry_path.resolve()
    registry = load_benchmark_bank(registry_path)
    family_bindings = _protocol_specific_family_bindings(registry)
    access = assess_shard_access(
        role=ShardRole.SEALED,
        purpose=ClaimPurpose.FRESH_ADMISSION,
        integration_status=IntegrationStatus.ADMITTED,
        claim_upgrade_gate_passed=True,
    )
    if not access["authorized"]:
        raise RuntimeError("CMI-R7 protocol-specific SEALED shard access was denied")

    store = ArtifactStore(workspace / "protocol-artifacts")
    states = _freeze_fresh_population(store)
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_FRESH_EVALUATION",
        "scientific_question": "Does the frozen CMI treatment produce a resolution-exceeding paired utility gain on every one of six preregistered fresh states?",
        "claim_ceiling": "FRESH_STATE_CAUSAL_REPLICATION_WITHIN_FROZEN_ASSIGNMENT_COVERAGE_DISTRIBUTIONS_ONLY",
        "repository": repository,
        "cmi_r6_authority": r6["binding"],
        "frozen_brief": r6["manifest"]["brief"],
        "benchmark_bank": {
            "path": str(registry_path),
            "bank_id": registry["bank_id"],
            "registry_digest": digest_json(registry),
            "family_bindings": family_bindings,
            "access_decision": access,
            "admission_scope": "these six protocol-specific neighboring-hidden SEALED instances only",
        },
        "freshness": {
            "instance_fresh": True,
            "distribution_fresh": False,
            "task_family_fresh": False,
            "evaluator_regime_fresh": False,
            "exact_instance_mechanism_formation_independent": True,
            "task_family_mechanism_formation_independent": False,
            "exact_instances_used_before_seal": False,
            "prospective_utility_observed_before_seal": False,
            "seed_selection_rule": "SHA256 derivation from frozen protocol salt, family, state index, and case index; no screening or replacement",
            "protocol_salt": PROTOCOL_SALT,
        },
        "population_rule": {
            "states": EXPECTED_STATES,
            "states_per_family": EXPECTED_STATES_PER_FAMILY,
            "eligible_categories": sorted(ELIGIBLE_CATEGORIES),
            "all_states_frozen_together": True,
            "post_outcome_replacement": False,
        },
        "states": states,
        "matched_conditions": {
            "same_state": True,
            "same_incumbent": True,
            "same_evaluator": True,
            "same_score_resolution": True,
            "same_deterministic_randomness_rule": True,
            "one_control_and_one_treatment_invocation_per_state": True,
            "control": "frozen R6 LocalBehaviorControlOperator",
            "treatment": "frozen R6 FunctionalBasinEscapeOperator",
            "post_fresh_parameter_change": False,
        },
        "primary_endpoint": {
            "name": "paired_final_utility_delta_exceeds_state_resolution",
            "formula": "treatment_score - control_score > score_resolution",
            "co_primary_endpoints": 0,
        },
        "supporting_mechanism_metrics": [
            "functional_escape",
            "incumbent_replacement",
            "anytime_auc_delta",
            "breakthrough_delta",
        ],
        "success_gate": {
            "valid_states_required": 6,
            "positive_primary_endpoint_states_required": 6,
            "negative_utility_states_maximum": 0,
            "positive_primary_endpoint_states_per_family_required": 3,
            "aggregate_evaluator_runtime_ratio_maximum": 2.0,
            "maximum_state_evaluator_runtime_ratio": 3.0,
        },
        "result_semantics": {
            "passed": "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED",
            "operator_admission_if_passed": "CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES",
            "failed": "CMI_R7_FRESH_CAUSAL_REPLICATION_NOT_ESTABLISHED",
            "not_evaluable": "CMI_R7_NOT_EVALUABLE_PROBE_OR_EVALUATOR",
            "next_authority_if_passed": "CMI_ENABLED_SEARCH_VS_IDENTICAL_SEARCH_WITHOUT_CMI_PREREGISTRATION_AUTHORIZED",
        },
        "search_value_established": False,
        "cross_task_family_generalization_authorized": False,
        "probability_or_significance_claim_authorized": False,
        "model_calls": 0,
        "tokens": 0,
        "fresh_states_consumed_before_run": 0,
        "implementation_bindings": _implementation_bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "states": len(states),
        "fresh_states_consumed": 0,
        "model_calls": 0,
        "tokens": 0,
    }


def run_cmi_fresh_causal_validation(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    report_path = workspace / "result-artifacts" / "records" / REPORT_RECORD
    if report_path.exists():
        raise RuntimeError("CMI-R7 fresh shard is create-once and already consumed")
    manifest = _load_manifest(workspace, manifest_digest)
    store = ArtifactStore(workspace / "protocol-artifacts")
    control = LocalBehaviorControlOperator()
    treatment = FunctionalBasinEscapeOperator(manifest["frozen_brief"])
    states = [_run_replication_pair(store, state, control, treatment) for state in manifest["states"]]
    analysis, gate = _analyze_fresh_replication(states, manifest["success_gate"])
    technically_evaluable = all(state["technically_evaluable"] for state in states)
    if not technically_evaluable:
        verdict = "CMI_R7_NOT_EVALUABLE_PROBE_OR_EVALUATOR"
    elif gate["passed"]:
        verdict = "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED"
    else:
        verdict = "CMI_R7_FRESH_CAUSAL_REPLICATION_NOT_ESTABLISHED"
    passed = verdict == "CMI_R7_FRESH_CAUSAL_REPLICATION_PASSED"
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "CMI_R7_COMPLETE",
        "verdict": verdict,
        "operator_admission": "CMI_OPERATOR_ADMITTED_ON_FRESH_ASSIGNMENT_COVERAGE_STATES" if passed else "CMI_OPERATOR_NOT_ADMITTED_BY_R7",
        "technically_evaluable": technically_evaluable,
        "states": states,
        "analysis": analysis,
        "success_gate": gate,
        "claim_ceiling": manifest["claim_ceiling"],
        "cmi_enabled_search_comparison_preregistration_authorized": passed,
        "search_value_established": False,
        "cross_task_family_generalization_established": False,
        "probability_or_significance_established": False,
        "model_calls": 0,
        "tokens": 0,
        "operator_invocations": {"control": len(states), "treatment": len(states)},
        "evaluator_calls": len(states) * 4,
        "functional_probe_calls": len(states) * 4,
        "fresh_states_consumed": len(states),
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_fresh_population(store: ArtifactStore) -> list[dict[str, Any]]:
    tasks = cmi_r7_fresh_tasks()
    if len(tasks) != EXPECTED_STATES:
        raise RuntimeError("CMI-R7 fresh population size drift")
    states = []
    for index, task in enumerate(tasks):
        probe_seeds = (71011 + index * 101, 71031 + index * 101, 71057 + index * 101)
        state = {
            "state_id": f"cmi-r7-{index}-{task.task.task_id}",
            "task_id": task.task.task_id,
            "task_category": task.task.category,
            "cohort_role": "FRESH_ADMISSION",
            "task_payload_digest": task.payload_digest,
            "score_resolution": task.score_resolution,
            "base_source_digest": store.put_bytes(normalized_source(task.task.algorithm_source).encode("utf-8"), media_type="text/x-python"),
            "reference_source_digest": store.put_bytes(normalized_source(task.reference_source).encode("utf-8"), media_type="text/x-python"),
            "task_files": {
                "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
                "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
                "functional_probe.py": store.put_bytes(_probe_source(task.task.category, probe_seeds).encode("utf-8"), media_type="text/x-python"),
            },
            "functional_probe_seeds": list(probe_seeds),
            "breakthrough_rule": "reference_score_minus_score_resolution",
            "freshness_role": "SEALED_NEIGHBORING_HIDDEN_INSTANCE",
        }
        states.append({**state, "state_digest": digest_json(state)})
    counts = {category: sum(state["task_category"] == category for state in states) for category in ELIGIBLE_CATEGORIES}
    if set(counts.values()) != {EXPECTED_STATES_PER_FAMILY}:
        raise RuntimeError("CMI-R7 population is not balanced 3+3")
    return states


def _analyze_fresh_replication(states: list[dict[str, Any]], thresholds: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    effects = []
    for state in states:
        control, treatment = state["arms"]["control"], state["arms"]["treatment"]
        delta = treatment["score"] - control["score"]
        effects.append({
            "state_id": state["state_id"],
            "task_category": state["task_category"],
            "score_resolution": state["score_resolution"],
            "final_utility_delta": delta,
            "primary_endpoint_positive": delta > state["score_resolution"],
            "anytime_auc_delta": treatment["anytime_auc"] - control["anytime_auc"],
            "replacement_delta": float(treatment["replaced_incumbent"]) - float(control["replaced_incumbent"]),
            "breakthrough_delta": float(treatment["breakthrough"]) - float(control["breakthrough"]),
            "evaluator_runtime_ratio": treatment["evaluator_seconds"] / control["evaluator_seconds"] if control["evaluator_seconds"] > 0 else float("inf"),
        })
    control = [state["arms"]["control"] for state in states]
    treatment = [state["arms"]["treatment"] for state in states]
    positive = sum(effect["primary_endpoint_positive"] for effect in effects)
    negative = sum(effect["final_utility_delta"] < -effect["score_resolution"] for effect in effects)
    family_positive = {
        category: sum(effect["primary_endpoint_positive"] for effect in effects if effect["task_category"] == category)
        for category in sorted(ELIGIBLE_CATEGORIES)
    }
    control_runtime = sum(arm["evaluator_seconds"] for arm in control)
    treatment_runtime = sum(arm["evaluator_seconds"] for arm in treatment)
    summary = {
        "states": len(states),
        "valid_states": sum(state["technically_evaluable"] and all(arm["valid"] for arm in state["arms"].values()) for state in states),
        "positive_primary_endpoint_states": positive,
        "negative_utility_states": negative,
        "ties_within_resolution": len(states) - positive - negative,
        "positive_primary_endpoint_states_by_family": family_positive,
        "functional_escape_rate": {"control": statistics.fmean(float(arm["escaped"]) for arm in control), "treatment": statistics.fmean(float(arm["escaped"]) for arm in treatment)},
        "replacement_rate": {"control": statistics.fmean(float(arm["replaced_incumbent"]) for arm in control), "treatment": statistics.fmean(float(arm["replaced_incumbent"]) for arm in treatment)},
        "breakthrough_rate": {"control": statistics.fmean(float(arm["breakthrough"]) for arm in control), "treatment": statistics.fmean(float(arm["breakthrough"]) for arm in treatment)},
        "aggregate_evaluator_runtime_ratio": treatment_runtime / control_runtime if control_runtime > 0 else float("inf"),
        "maximum_state_evaluator_runtime_ratio": max(effect["evaluator_runtime_ratio"] for effect in effects),
    }
    checks = {
        "valid_states_required": summary["valid_states"] == int(thresholds["valid_states_required"]),
        "positive_primary_endpoint_states_required": positive == int(thresholds["positive_primary_endpoint_states_required"]),
        "negative_utility_states_maximum": negative <= int(thresholds["negative_utility_states_maximum"]),
        "positive_primary_endpoint_states_per_family_required": all(value == int(thresholds["positive_primary_endpoint_states_per_family_required"]) for value in family_positive.values()),
        "aggregate_evaluator_runtime_ratio_maximum": summary["aggregate_evaluator_runtime_ratio"] <= float(thresholds["aggregate_evaluator_runtime_ratio_maximum"]),
        "maximum_state_evaluator_runtime_ratio": summary["maximum_state_evaluator_runtime_ratio"] <= float(thresholds["maximum_state_evaluator_runtime_ratio"]),
    }
    return {"paired_effects": effects, "summary": summary}, {"passed": all(checks.values()), "checks": checks}


def _protocol_specific_family_bindings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = []
    by_category = {family.get("upstream_task"): family for family in registry["families"]}
    for category in sorted(ELIGIBLE_CATEGORIES):
        family = by_category.get(category)
        if family is None or family.get("integration_status") != "DEVELOPMENT_READY":
            raise RuntimeError(f"CMI-R7 bank family binding unavailable: {category}")
        bindings.append({
            "family_id": family["family_id"],
            "upstream_task": category,
            "registry_integration_status": family["integration_status"],
            "protocol_specific_scientific_admission": True,
            "admission_basis": "R6 claim-upgrade gate plus hash-bound internal adapter/evaluator and zero-model deterministic local runtime",
            "generic_family_or_external_adapter_admission": False,
        })
    return bindings


def _load_r6_authority(workspace: Path, expected_report_sha256: str) -> dict[str, Any]:
    report_path = workspace / "result-artifacts" / "records" / R6_REPORT_RECORD
    manifest_path = workspace / "protocol-artifacts" / "records" / R6_MANIFEST_RECORD
    if not report_path.is_file() or digest_bytes(report_path.read_bytes()) != expected_report_sha256:
        raise RuntimeError("CMI-R6 report hash mismatch")
    report = _load_json(report_path)
    manifest = _load_json(manifest_path, report["manifest_digest"])
    if (
        report.get("verdict") != "CMI_R6_CONSUMED_DISTRIBUTION_REPLICATION_PASSED"
        or not report.get("replication_gate", {}).get("passed")
        or not report.get("fresh_causal_validation_preregistration_authorized")
        or report.get("search_value_established")
    ):
        raise RuntimeError("CMI-R6 did not authorize R7 preregistration")
    return {"manifest": manifest, "report": report, "binding": {"workspace": str(workspace), "manifest_path": str(manifest_path), "manifest_digest": report["manifest_digest"], "report_path": str(report_path), "report_sha256": expected_report_sha256, "verdict": report["verdict"]}}


def _verify_frozen_operator_bindings(r6_manifest: dict[str, Any]) -> None:
    required = {"functional_basin_escape.py", "local_behavior_control.py"}
    bindings = {Path(item["path"]).name: item for item in r6_manifest["implementation_bindings"] if Path(item["path"]).name in required}
    if set(bindings) != required:
        raise RuntimeError("CMI-R6 frozen Operator bindings are incomplete")
    for binding in bindings.values():
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R6 frozen Operator binding drift")


def _load_manifest(workspace: Path, expected_digest: str) -> dict[str, Any]:
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("status") != "SEALED_PRE_FRESH_EVALUATION":
        raise RuntimeError("CMI-R7 manifest identity mismatch")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R7 repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R7 implementation binding drift")
    r6 = manifest["cmi_r6_authority"]
    _load_r6_authority(Path(r6["workspace"]), r6["report_sha256"])
    registry = load_benchmark_bank(Path(manifest["benchmark_bank"]["path"]))
    if digest_json(registry) != manifest["benchmark_bank"]["registry_digest"]:
        raise RuntimeError("CMI-R7 benchmark bank registry drift")
    return manifest


def _probe_source(category: str, seeds: tuple[int, ...]) -> str:
    from discoveryos.benchmarks.cmi_probe_calibration import _behavior_probe_source

    return _behavior_probe_source(category, seeds)


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("cmi_r7_fresh_tasks.py"),
        Path(__file__).with_name("cmi_replication_admission.py"),
        Path(__file__).with_name("si2_tasks.py"),
        Path(__file__).with_name("benchmark_bank.py"),
        Path(__file__).parents[1] / "operators" / "functional_basin_escape.py",
        Path(__file__).parents[1] / "operators" / "local_behavior_control.py",
    )
    return [{"path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())} for path in paths]
