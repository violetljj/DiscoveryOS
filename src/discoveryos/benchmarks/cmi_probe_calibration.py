from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.executable_mechanism_contract import _evaluate_descendant, _load_json, _repository_snapshot
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import (
    CONFIRMATION_TASK_IDS,
    DISCOVERY_TASK_IDS,
    _assignment_task,
    _coverage_task,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "CMI_R1_REAL_PROBE_CALIBRATION"
MANIFEST_RECORD = "cmi-r1-probe-calibration-manifest.json"
REPORT_RECORD = "cmi-r1-probe-calibration-report.json"
TASK_IDS = ("cmi_r1_assignment_probe_alpha", "cmi_r1_coverage_probe_alpha")
EVALUATOR_RECOVERY_MINIMUM = 6 / 7
FUNCTIONAL_DISTANCE_MINIMUM = 0.10


def seal_cmi_probe_calibration(
    workspace: Path, *, require_clean_repository: bool = True
) -> dict[str, Any]:
    """Freeze two never-consumed dev episodes before observing any probe output."""

    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R1 calibration workspace must be create-once and empty")
    repository = _repository_snapshot()
    if require_clean_repository and not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R1 calibration must be sealed from a clean worktree")
    known_ids = set(DISCOVERY_TASK_IDS) | set(CONFIRMATION_TASK_IDS)
    if any(task_id in known_ids for task_id in TASK_IDS):
        raise RuntimeError("CMI-R1 task identity overlaps a consumed SI-2 task")

    tasks = (
        _assignment_task(TASK_IDS[0], (21101, 21121, 21139, 21157, 21179, 21211)),
        _coverage_task(TASK_IDS[1], (22109, 22123, 22147, 22171, 22193, 22229)),
    )
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_state(store, task, index) for index, task in enumerate(tasks)]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_PROBE_OBSERVATION",
        "scope": "REAL_DEV_PROBE_CALIBRATION_ONLY",
        "claim_ceiling": "PROBE_SENSITIVITY_NOT_REAL_BOTTLENECK_DIAGNOSIS",
        "repository": repository,
        "states": states,
        "thresholds": {
            "evaluator_ranked_control_recovery_minimum": EVALUATOR_RECOVERY_MINIMUM,
            "same_source_functional_distance_maximum": 0.0,
            "baseline_reference_functional_distance_minimum": FUNCTIONAL_DISTANCE_MINIMUM,
            "reference_headroom_minimum": "state.score_resolution",
        },
        "required_checks": [
            "all baseline and reference controls valid",
            "reference exceeds baseline by frozen score resolution",
            "ranked evaluator controls recover at least 6 of 7 expected pairs per state",
            "same-source functional probe is exactly deterministic",
            "baseline/reference functional signatures exceed frozen distance",
        ],
        "next_stage_authority_if_passed": "MAY_PREREGISTER_BOUNDED_CMI_REAL_DIAGNOSIS",
        "model_calls": 0,
        "provider_calls": 0,
        "fresh_search_value_tasks_consumed": 0,
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
        "provider_calls": 0,
    }


def run_cmi_probe_calibration(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest)
    store = ArtifactStore(workspace / "protocol-artifacts")
    state_results = [_calibrate_state(store, state, manifest["thresholds"]) for state in manifest["states"]]
    passed = len(state_results) == 2 and all(item["passed"] for item in state_results)
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "CMI_R1_REAL_PROBE_CALIBRATION_PASSED" if passed else "CMI_R1_REAL_PROBE_CALIBRATION_FAILED",
        "passed": passed,
        "state_results": state_results,
        "claim_ceiling": manifest["claim_ceiling"],
        "real_bottleneck_established": False,
        "real_mechanism_brief_authorized": False,
        "bounded_real_diagnosis_preregistration_authorized": passed,
        "model_calls": 0,
        "provider_calls": 0,
        "fresh_search_value_tasks_consumed": 0,
        "fresh_search_value_budget_authorized": False,
        "source_bindings": [
            {
                "role": "manifest",
                "path": str(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD),
                "sha256": digest_bytes((workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD).read_bytes()),
            }
        ],
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _freeze_state(store: ArtifactStore, task: Any, index: int) -> dict[str, Any]:
    category = task.task.category
    if category == "capacitated_cost_assignment":
        behavior_seeds = (23117, 23131, 23159)
    elif category == "budgeted_weighted_coverage":
        behavior_seeds = (24109, 24133, 24151)
    else:
        raise ValueError(f"unsupported CMI-R1 category: {category}")
    sources = [normalized_source(task.task.algorithm_source)]
    sources.extend(normalized_source(value) for value in task.intermediate_sources)
    sources.append(normalized_source(task.reference_source))
    labels = ("baseline", "intermediate_1", "intermediate_2", "intermediate_3", "reference")
    source_entries = [
        {"label": label, "digest": store.put_bytes(source.encode("utf-8"), media_type="text/x-python")}
        for label, source in zip(labels, sources, strict=True)
    ]
    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
        "behavior_probe.py": store.put_bytes(
            _behavior_probe_source(category, behavior_seeds).encode("utf-8"), media_type="text/x-python"
        ),
    }
    state = {
        "state_id": f"cmi-r1-probe-{index}-{task.task.task_id}",
        "task_id": task.task.task_id,
        "task_category": category,
        "task_payload_digest": task.payload_digest,
        "score_resolution": task.score_resolution,
        "behavior_probe_seeds": list(behavior_seeds),
        "task_files": files,
        "ranked_sources": source_entries,
        "expected_order_pairs": [
            ["baseline", "intermediate_1"],
            ["baseline", "intermediate_2"],
            ["baseline", "intermediate_3"],
            ["baseline", "reference"],
            ["intermediate_1", "reference"],
            ["intermediate_2", "reference"],
            ["intermediate_3", "reference"],
        ],
        "freshness_basis": "new task id and evaluator seeds absent from all prior shipped protocols",
    }
    return {**state, "state_digest": digest_json(state)}


def _calibrate_state(store: ArtifactStore, state: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    evaluations = {}
    signatures = {}
    for item in state["ranked_sources"]:
        source = store.get_bytes(item["digest"]).decode("utf-8")
        evaluations[item["label"]] = _evaluate_descendant(store, state, source)
        signatures[item["label"]] = _behavior_signature(store, state, source)
    baseline_repeat = _behavior_signature(
        store,
        state,
        store.get_bytes(next(item["digest"] for item in state["ranked_sources"] if item["label"] == "baseline")).decode("utf-8"),
    )
    expected_pairs = state["expected_order_pairs"]
    recovered = sum(
        evaluations[right]["score"] > evaluations[left]["score"]
        for left, right in expected_pairs
        if evaluations[left]["valid"] and evaluations[right]["valid"]
    )
    recovery_rate = recovered / len(expected_pairs)
    same_source_distance = _mean_absolute_distance(signatures["baseline"], baseline_repeat)
    cross_distance = _mean_absolute_distance(signatures["baseline"], signatures["reference"])
    headroom = evaluations["reference"]["score"] - evaluations["baseline"]["score"]
    checks = {
        "baseline_and_reference_valid": bool(evaluations["baseline"]["valid"] and evaluations["reference"]["valid"]),
        "reference_headroom": headroom >= float(state["score_resolution"]),
        "evaluator_ranked_control_recovery": recovery_rate >= float(thresholds["evaluator_ranked_control_recovery_minimum"]),
        "same_source_probe_deterministic": same_source_distance <= float(thresholds["same_source_functional_distance_maximum"]),
        "functional_positive_control_detected": cross_distance >= float(thresholds["baseline_reference_functional_distance_minimum"]),
    }
    return {
        "state_id": state["state_id"],
        "task_id": state["task_id"],
        "passed": all(checks.values()),
        "checks": checks,
        "baseline_score": evaluations["baseline"]["score"],
        "reference_score": evaluations["reference"]["score"],
        "reference_headroom": headroom,
        "ranked_control_pairs_recovered": recovered,
        "ranked_control_pairs_total": len(expected_pairs),
        "ranked_control_recovery_rate": recovery_rate,
        "same_source_functional_distance": same_source_distance,
        "baseline_reference_functional_distance": cross_distance,
        "evaluation_bindings": {
            label: {
                "source_sha256": value["source_sha256"],
                "score": value["score"],
                "valid": value["valid"],
            }
            for label, value in evaluations.items()
        },
    }


def _behavior_signature(store: ArtifactStore, state: dict[str, Any], source: str) -> list[float]:
    with tempfile.TemporaryDirectory(prefix="discoveryos-cmi-r1-probe-") as temporary:
        root = Path(temporary)
        (root / "algorithm.py").write_text(source, encoding="utf-8")
        (root / "behavior_probe.py").write_bytes(store.get_bytes(state["task_files"]["behavior_probe.py"]))
        result = _run_python(root, "behavior_probe.py")
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout.strip())
        values = [float(value) for value in payload["signature"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return []
    return values


def _mean_absolute_distance(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)


def _behavior_probe_source(category: str, seeds: tuple[int, ...]) -> str:
    if category == "capacitated_cost_assignment":
        body = f'''
import json, random
from algorithm import assign_clients

signature = []
for seed in {seeds!r}:
    rng = random.Random(seed)
    clients, facilities = 18, 4
    capacities = [5, 5, 4, 4]
    costs = []
    for client in range(clients):
        preferred = rng.randrange(facilities)
        costs.append([1 + rng.randrange(4) if facility == preferred else 9 + rng.randrange(9) for facility in range(facilities)])
    result = assign_clients(costs, capacities)
    valid = isinstance(result, list) and len(result) == clients and all(isinstance(value, int) and 0 <= value < facilities for value in result)
    valid = valid and all(result.count(facility) <= capacities[facility] for facility in range(facilities))
    if not valid:
        raise SystemExit(2)
    signature.extend(value / (facilities - 1) for value in result)
print(json.dumps({{"signature": signature}}))
'''
    elif category == "budgeted_weighted_coverage":
        body = f'''
import json, random
from algorithm import choose_sets

signature = []
for seed in {seeds!r}:
    rng = random.Random(seed)
    elements, count, limit = 30, 14, 4
    weights = [rng.randint(1, 9) for _ in range(elements)]
    sets = []
    for index in range(count):
        members = set(rng.sample(range(elements), 7 + index % 4))
        sets.append(tuple(sorted(members)))
    result = choose_sets(sets, weights, limit)
    valid = isinstance(result, list) and len(result) <= limit and len(result) == len(set(result))
    valid = valid and all(isinstance(value, int) and 0 <= value < count for value in result)
    if not valid:
        raise SystemExit(2)
    covered = set().union(*(sets[index] for index in result)) if result else set()
    signature.extend(float(index in covered) for index in range(elements))
print(json.dumps({{"signature": signature}}))
'''
    else:
        raise ValueError(f"unsupported behavior probe category: {category}")
    return normalized_source(body)


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
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(arguments, 124, stdout=error.stdout or "", stderr=error.stderr or "timeout")


def _load_manifest(workspace: Path, expected_digest: str) -> dict[str, Any]:
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_json(path, expected_digest)
    if manifest.get("protocol_id") != PROTOCOL_ID or manifest.get("status") != "SEALED_PRE_PROBE_OBSERVATION":
        raise RuntimeError("CMI-R1 probe calibration manifest identity mismatch")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R1 repository differs from the sealed manifest")
    for binding in manifest["implementation_bindings"]:
        bound = Path(binding["path"])
        if not bound.is_file() or digest_bytes(bound.read_bytes()) != binding["sha256"]:
            raise RuntimeError("CMI-R1 implementation binding drift")
    return manifest


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("si2_tasks.py").resolve(),
        Path(__file__).with_name("parent_intervention_real.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
