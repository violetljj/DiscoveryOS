from __future__ import annotations

from pathlib import Path
from typing import Any

from discoveryos.benchmarks.executable_mechanism_contract import _load_json, _repository_snapshot
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF"
MANIFEST_RECORD = "cmi-r3-functional-basin-escape-manifest.json"
REPORT_RECORD = "cmi-r3-functional-basin-escape-admission.json"
R2_REPORT_RECORD = "cmi-r2-real-diagnosis-report.json"
R2_CONTROLS_RECORD = "cmi-r2-real-diagnosis-controls.json"


def seal_cmi_escape_brief(
    workspace: Path,
    *,
    cmi_r2_workspace: Path,
    cmi_r2_report_sha256: str,
    cmi_r2_controls_sha256: str,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R3 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R3 must be sealed from a clean worktree")

    report_path = cmi_r2_workspace.resolve() / "result-artifacts" / "records" / R2_REPORT_RECORD
    controls_path = cmi_r2_workspace.resolve() / "result-artifacts" / "records" / R2_CONTROLS_RECORD
    report = _load_authority(report_path, cmi_r2_report_sha256, "CMI-R2 report")
    controls = _load_authority(controls_path, cmi_r2_controls_sha256, "CMI-R2 controls")
    _validate_r2_authority(report, controls)

    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_ZERO_MODEL",
        "scope": "TWO_STATE_DEVELOPMENT_MECHANISM_BRIEF",
        "claim_ceiling": "DEVELOPMENT_MECHANISM_BRIEF_ONLY",
        "repository": repository,
        "cmi_r2_authority": {
            "workspace": str(cmi_r2_workspace.resolve()),
            "report_path": str(report_path),
            "report_sha256": cmi_r2_report_sha256,
            "controls_path": str(controls_path),
            "controls_sha256": cmi_r2_controls_sha256,
            "manifest_digest": report["manifest_digest"],
        },
        "brief": _brief(),
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_tasks_consumed": 0,
        "operator_implementation_authorized": False,
        "operator_value_trial_authorized": False,
        "fresh_search_value_budget_authorized": False,
        "implementation_binding": {
            "path": str(Path(__file__).resolve()),
            "sha256": digest_bytes(Path(__file__).read_bytes()),
        },
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {"status": manifest["status"], "manifest_digest": manifest["manifest_digest"], "manifest_path": str(path), "model_calls": 0}


def admit_cmi_escape_brief(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, manifest_digest)
    if manifest.get("status") != "SEALED_ZERO_MODEL":
        raise RuntimeError("CMI-R3 manifest status mismatch")
    binding = manifest["implementation_binding"]
    binding_path = Path(binding["path"])
    if not binding_path.is_file() or digest_bytes(binding_path.read_bytes()) != binding["sha256"]:
        raise RuntimeError("CMI-R3 implementation binding drift")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R3 repository drift")

    authority = manifest["cmi_r2_authority"]
    report = _load_authority(Path(authority["report_path"]), authority["report_sha256"], "CMI-R2 report")
    controls = _load_authority(Path(authority["controls_path"]), authority["controls_sha256"], "CMI-R2 controls")
    _validate_r2_authority(report, controls)
    checks = _admission_checks(manifest["brief"], report, controls)
    passed = all(checks.values())
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF_ADMITTED" if passed else "CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF_REJECTED",
        "passed": passed,
        "checks": checks,
        "bound_hypothesis": "H5_STRUCTURAL_BASIN_LOCK",
        "causal_target": manifest["brief"]["causal_target"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_tasks_consumed": 0,
        "operator_implementation_authorized": False,
        "operator_value_trial_authorized": False,
        "fresh_search_value_budget_authorized": False,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, record)
    return {**record, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _brief() -> dict[str, Any]:
    return {
        "brief_id": "functional-basin-escape-v1",
        "source_hypothesis": "H5_STRUCTURAL_BASIN_LOCK",
        "causal_target": "functional_output_basin",
        "applicability_preconditions": {
            "minimum_independent_states": 2,
            "minimum_evaluator_ranked_control_recovery": 6 / 7,
            "minimum_valid_source_rate": 5 / 6,
            "maximum_within_state_functional_distance": 0.10,
            "minimum_reference_headroom": 0.0,
        },
        "required_context": ["frozen_task_contract_and_public_api", "frozen_state_local_functional_probe", "incumbent_functional_signature", "matched_resource_ceiling"],
        "intervention_contract": {
            "required_change": "change algorithmic decomposition before source generation",
            "admission_fingerprint": "valid candidate with state-local functional distance greater than 0.10 from the incumbent envelope",
            "minimum_states_with_fingerprint": 2,
            "source_difference_is_sufficient": False,
        },
        "causal_path": ["functional_output_basin_escape", "evaluator_relevant_behavior_change", "replacement_opportunity", "utility_or_auc_difference"],
        "null_control": "same mechanism and same source must have functional distance 0",
        "positive_control": "known alternative implementation must have functional distance greater than 0.10",
        "forbidden_substitutions": ["syntax_repair", "generic_critique_or_reflection", "source_only_diversity", "evaluator_or_threshold_modification", "reference_implementation_leakage", "prompt_length_or_token_count_as_fingerprint"],
        "failure_modes": ["source_differs_but_functional_signature_is_unchanged", "candidate_is_invalid_or_ineligible", "functional_probe_is_insensitive", "positive_control_or_reference_leaks_into_generation", "resource_ceiling_is_exceeded", "effect_is_observed_on_only_one_state", "behavior_changes_but_utility_remains_equivalent"],
        "next_gate_if_admitted": "separate create-once operator protocol with new development states and pre-utility fingerprint checks",
    }


def _load_authority(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file() or digest_bytes(path.read_bytes()) != expected_sha256:
        raise RuntimeError(f"{label} hash mismatch")
    return _load_json(path)


def _validate_r2_authority(report: dict[str, Any], controls: dict[str, Any]) -> None:
    assessments = {item["hypothesis_id"]: item["verdict"] for item in report.get("diagnosis", {}).get("assessments", [])}
    expected = {"H3_EVALUATOR_INSENSITIVITY": "REFUTED", "H4_IMPLEMENTATION_BOTTLENECK": "REFUTED", "H5_STRUCTURAL_BASIN_LOCK": "SUPPORTED"}
    if (report.get("status") != "CMI_R2_REAL_DIAGNOSIS_COMPLETE" or report.get("diagnosis", {}).get("mechanism_brief_hypothesis_id") != "H5_STRUCTURAL_BASIN_LOCK" or report.get("diagnosis", {}).get("terminal_phase") != "MECHANISM_BRIEF_ALLOWED" or assessments != expected or not report.get("development_mechanism_brief_authorized") or report.get("new_operator_authorized") or report.get("fresh_search_value_budget_authorized") or controls.get("status") != "CMI_R2_CONTROLS_PASSED" or controls.get("manifest_digest") != report.get("manifest_digest") or not controls.get("passed")):
        raise RuntimeError("CMI-R2 did not authorize the bounded development Mechanism Brief")


def _admission_checks(brief: dict[str, Any], report: dict[str, Any], controls: dict[str, Any]) -> dict[str, bool]:
    probes = {item["probe_id"]: item for item in report["probe_results"]}
    states = controls.get("states", [])
    forbidden = set(brief.get("forbidden_substitutions", []))
    path = brief.get("causal_path", [])
    contract = brief.get("intervention_contract", {})
    return {
        "authorized_hypothesis_bound": brief.get("source_hypothesis") == "H5_STRUCTURAL_BASIN_LOCK",
        "two_independent_states_bound": len(states) >= int(brief["applicability_preconditions"]["minimum_independent_states"]),
        "evaluator_sensitivity_precondition_met": float(probes["P3_RANKED_CONTROL_RECOVERY"]["observed_value"]) >= 6 / 7,
        "implementation_precondition_met": float(probes["P4_DIRECT_VALID_RATE"]["observed_value"]) >= 5 / 6,
        "basin_lock_precondition_met": float(probes["P5_FUNCTIONAL_DIVERSITY"]["observed_value"]) <= 0.10,
        "state_local_null_control_bound": bool(states) and all(float(item["same_source_functional_distance"]) == 0.0 for item in states),
        "state_local_positive_control_bound": bool(states) and all(float(item["baseline_reference_functional_distance"]) > 0.10 for item in states),
        "reference_headroom_bound": bool(states) and all(float(item["reference_headroom"]) > 0.0 for item in states),
        "nontrivial_intervention_required": contract.get("source_difference_is_sufficient") is False and "greater than 0.10" in contract.get("admission_fingerprint", ""),
        "causal_reachability_explicit": path == ["functional_output_basin_escape", "evaluator_relevant_behavior_change", "replacement_opportunity", "utility_or_auc_difference"],
        "source_only_and_leakage_forbidden": {"source_only_diversity", "reference_implementation_leakage", "evaluator_or_threshold_modification"}.issubset(forbidden),
        "failure_semantics_explicit": len(brief.get("failure_modes", [])) >= 6,
    }
