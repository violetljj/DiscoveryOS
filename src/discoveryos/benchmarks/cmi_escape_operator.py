from __future__ import annotations

import ast
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.cmi_escape_brief import MANIFEST_RECORD as R3_MANIFEST_RECORD
from discoveryos.benchmarks.cmi_escape_brief import REPORT_RECORD as R3_REPORT_RECORD
from discoveryos.benchmarks.cmi_probe_calibration import (
    _behavior_probe_source,
    _behavior_signature,
    _mean_absolute_distance,
    _run_python,
)
from discoveryos.benchmarks.executable_mechanism_contract import _load_json, _repository_snapshot
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import CONFIRMATION_TASK_IDS, DISCOVERY_TASK_IDS, _assignment_task, _coverage_task
from discoveryos.operators.functional_basin_escape import FunctionalBasinEscapeOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS"
MANIFEST_RECORD = "cmi-r4-escape-operator-manifest.json"
REPORT_RECORD = "cmi-r4-escape-operator-report.json"
TASK_IDS = ("cmi_r4_assignment_mechanics_alpha", "cmi_r4_coverage_mechanics_alpha")
FUNCTIONAL_DISTANCE_MINIMUM_EXCLUSIVE = 0.10


def seal_cmi_escape_operator(
    workspace: Path,
    *,
    cmi_r3_workspace: Path,
    cmi_r3_report_sha256: str,
    require_clean_repository: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R4 workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R4 must be sealed from a clean worktree")

    authority_root = cmi_r3_workspace.resolve()
    report_path = authority_root / "result-artifacts" / "records" / R3_REPORT_RECORD
    manifest_path = authority_root / "protocol-artifacts" / "records" / R3_MANIFEST_RECORD
    report = _load_authority(report_path, cmi_r3_report_sha256, "CMI-R3 report")
    r3_manifest = _load_json(manifest_path, report["manifest_digest"])
    _validate_r3_authority(r3_manifest, report)

    known_ids = set(DISCOVERY_TASK_IDS) | set(CONFIRMATION_TASK_IDS)
    if any(task_id in known_ids for task_id in TASK_IDS):
        raise RuntimeError("CMI-R4 task identity overlaps a consumed search-value task")
    tasks = (
        _assignment_task(TASK_IDS[0], (31103, 31123, 31139, 31159, 31181, 31219)),
        _coverage_task(TASK_IDS[1], (32117, 32141, 32159, 32183, 32203, 32233)),
    )
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_state(store, task, index) for index, task in enumerate(tasks)]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_OPERATOR_EXECUTION",
        "scope": "TWO_NEW_DEVELOPMENT_STATE_OPERATOR_MECHANICS_ONLY",
        "claim_ceiling": "DEVELOPMENT_OPERATOR_MECHANICS_ONLY",
        "repository": repository,
        "cmi_r3_authority": {
            "workspace": str(authority_root),
            "manifest_path": str(manifest_path),
            "manifest_digest": report["manifest_digest"],
            "report_path": str(report_path),
            "report_sha256": cmi_r3_report_sha256,
        },
        "brief": r3_manifest["brief"],
        "states": states,
        "thresholds": {
            "null_functional_distance_maximum": 0.0,
            "positive_functional_distance_minimum_exclusive": FUNCTIONAL_DISTANCE_MINIMUM_EXCLUSIVE,
            "treatment_functional_distance_minimum_exclusive": FUNCTIONAL_DISTANCE_MINIMUM_EXCLUSIVE,
            "minimum_states_with_treatment_fingerprint": 2,
        },
        "pass_question": "Structured Functional-Basin-Escape Brief -> Real Operator -> Measurable Functional Basin Escape",
        "utility_comparison_authorized": False,
        "operator_value_trial_authorized": False,
        "fresh_search_value_budget_authorized": False,
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_search_value_tasks_consumed": 0,
        "development_states_consumed_if_run": 2,
        "implementation_bindings": _implementation_bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "model_calls": 0,
        "evaluator_calls": 0,
    }


def run_cmi_escape_operator(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest)
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    operator = FunctionalBasinEscapeOperator(manifest["brief"])
    states = [_run_state(protocol_store, state, operator, manifest["thresholds"]) for state in manifest["states"]]
    controls_evaluable = all(item["controls_evaluable"] for item in states)
    fingerprint_count = sum(item["treatment_fingerprint_passed"] for item in states)
    passed = controls_evaluable and fingerprint_count >= int(
        manifest["thresholds"]["minimum_states_with_treatment_fingerprint"]
    ) and all(item["causal_reachability_passed"] for item in states)
    if not controls_evaluable:
        status = "CMI_R4_NOT_EVALUABLE_CONTROL_OR_PROBE"
    elif passed:
        status = "CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_CONFIRMED_ON_TWO_DEV_STATES"
    else:
        status = "CMI_R4_FUNCTIONAL_BASIN_ESCAPE_OPERATOR_MECHANICS_NOT_ESTABLISHED_ON_DEV"
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": status,
        "passed": passed,
        "states": states,
        "treatment_fingerprint_states": fingerprint_count,
        "claim_ceiling": manifest["claim_ceiling"],
        "operator_mechanics_established": passed,
        "causal_value_established": False,
        "search_value_established": False,
        "utility_comparison_performed": False,
        "operator_value_trial_authorized": False,
        "fresh_search_value_budget_authorized": False,
        "model_calls": 0,
        "evaluator_calls": 0,
        "probe_process_calls": 24,
        "fresh_search_value_tasks_consumed": 0,
        "development_states_consumed": len(states),
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_state(store: ArtifactStore, task: Any, index: int) -> dict[str, Any]:
    category = task.task.category
    probe_seeds = (33107, 33149, 33179) if category == "capacitated_cost_assignment" else (34123, 34157, 34183)
    descendant_seeds = (35107, 35141, 35171) if category == "capacitated_cost_assignment" else (36109, 36137, 36187)
    base = normalized_source(task.task.algorithm_source)
    positive = normalized_source(task.reference_source)
    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "functional_probe.py": store.put_bytes(_behavior_probe_source(category, probe_seeds).encode("utf-8"), media_type="text/x-python"),
        "descendant_probe.py": store.put_bytes(_behavior_probe_source(category, descendant_seeds).encode("utf-8"), media_type="text/x-python"),
    }
    state = {
        "state_id": f"cmi-r4-{index}-{task.task.task_id}",
        "task_id": task.task.task_id,
        "task_category": category,
        "task_payload_digest": task.payload_digest,
        "task_files": files,
        "base_source_digest": store.put_bytes(base.encode("utf-8"), media_type="text/x-python"),
        "positive_control_source_digest": store.put_bytes(positive.encode("utf-8"), media_type="text/x-python"),
        "functional_probe_seeds": list(probe_seeds),
        "descendant_probe_seeds": list(descendant_seeds),
        "freshness_basis": "new development task id, task seeds, and probe seeds absent from shipped protocols",
    }
    return {**state, "state_digest": digest_json(state)}


def _run_state(
    store: ArtifactStore,
    state: dict[str, Any],
    operator: FunctionalBasinEscapeOperator,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    base = store.get_bytes(state["base_source_digest"]).decode("utf-8")
    positive = store.get_bytes(state["positive_control_source_digest"]).decode("utf-8")
    treatment = operator.propose(task_category=state["task_category"], base_source=base)
    sources = {"baseline": base, "null": base, "positive": positive, "treatment": treatment.source}
    public_validity = {label: _public_valid(store, state, source) for label, source in sources.items()}
    functional = {label: _signature(store, state, source, "functional_probe.py") for label, source in sources.items()}
    descendant = {label: _signature(store, state, source, "descendant_probe.py") for label, source in sources.items()}
    distances = {
        label: {
            "source_distance": _source_distance(base, source),
            "structural_distance": _structural_distance(base, source),
            "functional_distance": _mean_absolute_distance(functional["baseline"], functional[label]),
            "descendant_behavior_distance": _mean_absolute_distance(descendant["baseline"], descendant[label]),
        }
        for label, source in sources.items()
        if label != "baseline"
    }
    controls_evaluable = (
        all(public_validity.values())
        and all(functional.values())
        and all(descendant.values())
        and distances["null"]["functional_distance"] <= float(thresholds["null_functional_distance_maximum"])
        and distances["positive"]["functional_distance"] > float(thresholds["positive_functional_distance_minimum_exclusive"])
    )
    trace = treatment.trace
    required_paths = {
        "causal_target",
        "required_context",
        "intervention_contract.required_change",
        "intervention_contract.admission_fingerprint",
        "intervention_contract.source_difference_is_sufficient",
    }
    causal_reachability = (
        required_paths.issubset(set(trace["field_paths_read"]))
        and trace["positive_control_received"] is False
        and trace["evaluator_feedback_received"] is False
        and operator.brief_digest == trace["brief_digest"]
        and treatment.source != positive
    )
    fingerprint = (
        public_validity["treatment"]
        and distances["treatment"]["functional_distance"] > float(thresholds["treatment_functional_distance_minimum_exclusive"])
    )
    return {
        "state_id": state["state_id"],
        "task_id": state["task_id"],
        "task_category": state["task_category"],
        "controls_evaluable": controls_evaluable,
        "public_validity": public_validity,
        "distances_from_incumbent": distances,
        "treatment_fingerprint_passed": fingerprint,
        "causal_reachability_passed": causal_reachability,
        "operator_trace": trace,
        "source_sha256": {label: digest_bytes(source.encode("utf-8")) for label, source in sources.items()},
    }


def _public_valid(store: ArtifactStore, state: dict[str, Any], source: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="discoveryos-cmi-r4-public-") as temporary:
        root = Path(temporary)
        (root / "algorithm.py").write_text(source, encoding="utf-8")
        (root / "public_tests.py").write_bytes(store.get_bytes(state["task_files"]["public_tests.py"]))
        return _run_python(root, "public_tests.py").returncode == 0


def _signature(store: ArtifactStore, state: dict[str, Any], source: str, probe_name: str) -> list[float]:
    proxy = {**state, "task_files": {**state["task_files"], "behavior_probe.py": state["task_files"][probe_name]}}
    return _behavior_signature(store, proxy, source)


def _source_distance(left: str, right: str) -> float:
    return 1.0 - SequenceMatcher(None, normalized_source(left), normalized_source(right)).ratio()


def _structural_distance(left: str, right: str) -> float:
    def counts(source: str) -> Counter[str]:
        return Counter(type(node).__name__ for node in ast.walk(ast.parse(source)))
    left_counts, right_counts = counts(left), counts(right)
    union = sum((left_counts | right_counts).values())
    intersection = sum((left_counts & right_counts).values())
    return 0.0 if union == 0 else 1.0 - intersection / union


def _load_manifest(workspace: Path, expected_digest: str) -> dict[str, Any]:
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("status") != "SEALED_PRE_OPERATOR_EXECUTION":
        raise RuntimeError("CMI-R4 manifest identity mismatch")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R4 repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R4 implementation binding drift")
    authority = manifest["cmi_r3_authority"]
    report = _load_authority(Path(authority["report_path"]), authority["report_sha256"], "CMI-R3 report")
    r3_manifest = _load_json(Path(authority["manifest_path"]), authority["manifest_digest"])
    _validate_r3_authority(r3_manifest, report)
    if digest_json(r3_manifest["brief"]) != digest_json(manifest["brief"]):
        raise RuntimeError("CMI-R4 bound Brief drift")
    return manifest


def _validate_r3_authority(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    if (
        manifest.get("protocol_id") != "CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF"
        or report.get("status") != "CMI_R3_FUNCTIONAL_BASIN_ESCAPE_BRIEF_ADMITTED"
        or not report.get("passed")
        or report.get("manifest_digest") != manifest.get("manifest_digest")
        or report.get("claim_ceiling") != "DEVELOPMENT_MECHANISM_BRIEF_ONLY"
        or report.get("operator_value_trial_authorized")
        or report.get("fresh_search_value_budget_authorized")
    ):
        raise RuntimeError("CMI-R3 did not authorize the bounded R4 mechanics protocol")


def _load_authority(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file() or digest_bytes(path.read_bytes()) != expected_sha256:
        raise RuntimeError(f"{label} hash mismatch")
    return _load_json(path)


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).parents[1] / "operators" / "functional_basin_escape.py",
        Path(__file__).with_name("cmi_probe_calibration.py"),
        Path(__file__).with_name("si2_tasks.py"),
    )
    return [{"path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())} for path in paths]
