from __future__ import annotations

import concurrent.futures
import json
import platform
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.emc_resource_calibration import load_resource_authority
from discoveryos.benchmarks.executable_mechanism_contract import (
    CONDITION_DIRECT,
    CONDITION_REPAIR,
    IMPLEMENTATION_SCHEMA,
    MECHANISM_OBJECTS,
    ImplementationDraw,
    _analyze_draws,
    _draw_bindings,
    _draw_from_json,
    _draw_record_name,
    _evaluate_contract,
    _gate_verdict,
    _generate_implementation,
    _load_json,
    _provider_binding,
    _repository_snapshot,
    _sensitivity_sources,
    _usage,
    _validate_provider,
    _verify_checkpoint,
    compile_executable_contract,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.provider_invocations import assert_no_orphaned_invocations
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "EMC_R3_RESOURCE_CALIBRATED_CONFIRMATION"
MANIFEST_RECORD = "emc-r3-manifest.json"
SENSITIVITY_RECORD = "emc-r3-instrumentation-sensitivity.json"
CALIBRATION_RECORD = "emc-r3-implementation-calibration.json"
VALIDATION_RECORD = "emc-r3-implementation-validation.json"
REPLICATES_PER_CONDITION = 3
MAX_WORKERS = 2


def seal_emc_r3_protocol(
    workspace: Path,
    *,
    resource_workspace: Path,
    resource_record_sha256: str,
    implementation_provider: PatchProvider,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    if max_workers < 1 or max_workers > 2:
        raise ValueError("EMC-R3 max_workers must be one or two")
    _validate_provider(implementation_provider)
    authority = load_resource_authority(resource_workspace, resource_record_sha256, implementation_provider)
    token_ceiling = int(authority["record"]["derived_scientific_per_call_token_ceiling"])
    workspace = workspace.resolve()
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_task(store, role, task) for role, task in _development_tasks()]
    schedule = [
        {
            "state_id": state["state_id"],
            "condition_id": condition,
            "phase": state["role"],
            "replicate": replicate,
            "draw_id": f"{state['state_id']}:{condition.casefold()}:{replicate}",
            "contract": compile_executable_contract(condition, state["entrypoint"]),
        }
        for state in states
        for condition in (CONDITION_DIRECT, CONDITION_REPAIR)
        for replicate in range(REPLICATES_PER_CONDITION)
    ]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_SCIENTIFIC_MODEL_CALL",
        "scope": "RESOURCE_CALIBRATED_CONFIRMATION_ON_TWO_NEVER_CONSUMED_DEV_STATES",
        "scientific_question": (
            "Under an independently calibrated token ceiling and crash-safe at-most-once provider accounting, "
            "does the frozen executable contract reproducibly actuate its mutually exclusive runtime paths on "
            "two never-consumed development states?"
        ),
        "claim_ceiling": "RESOURCE_CALIBRATED_EXECUTABLE_CONTRACT_TRANSMISSION_ON_TWO_NEW_DEV_STATES_ONLY",
        "scientific_model_calls_before_seal": 0,
        "fresh_search_value_tasks_consumed": 0,
        "provider": _provider_binding(implementation_provider),
        "resource_authority": {
            "workspace": str(resource_workspace.resolve()),
            "record_sha256": resource_record_sha256,
            "manifest_digest": authority["record"]["manifest_digest"],
            "derived_per_call_token_ceiling": token_ceiling,
            "calibration_distribution": authority["record"]["distribution"],
            "ceiling_rule": authority["record"]["ceiling_rule"],
        },
        "mechanism_objects": MECHANISM_OBJECTS,
        "isolation": {
            "implementation_sees": ["task_question", "base_source", "canonical_mechanism_object", "executable_contract"],
            "implementation_forbidden_context": ["condition_id", "instrumentation_source", "hidden_evaluator"],
            "runtime_evidence_collected_by": "independent_profile_harness",
            "candidate_self_reported_counters_authoritative": False,
            "provider_invocation_accounting": "durable_at_most_once_fail_closed",
        },
        "cheap_first_gates": [
            "E0_INSTRUMENTATION_SENSITIVITY_NO_MODEL",
            "E1_RESOURCE_AUTHORITY_BOUND_AT_SEAL",
            "E2_IMPLEMENTATION_CALIBRATION_SIX_CALLS",
            "E3_INDEPENDENT_IMPLEMENTATION_VALIDATION_SIX_CALLS",
        ],
        "gates": {
            "E0": {"positive_controls_required": 2, "negative_controls_required": 2, "model_calls": 0},
            "E1": {"resource_record_sha256": resource_record_sha256, "model_calls": 0},
            "E2": {"model_calls": 6, "all_contract_layers_required": True, "zero_within_signature_variation": True},
            "E3": {"model_calls": 6, "same_requirements_as_E2": True, "independent_state": True},
        },
        "states": states,
        "implementation_schedule": schedule,
        "repository": _repository_snapshot(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "max_workers": max_workers,
        },
        "implementation_bindings": _bindings(),
        "not_authorized": [
            "R1 or R2 root mutation or replay",
            "resource ceiling changes after seal",
            "utility or superiority claim",
            "fresh search-value trial",
            "post-result task, contract, threshold, or replicate changes",
        ],
        "fresh_budget_authorized": False,
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_sha256": digest_bytes(path.read_bytes()),
        "scientific_model_calls": 12,
        "token_ceiling": token_ceiling,
    }


def run_emc_r3_instrumentation(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    state = manifest["states"][0]
    results = []
    for fixture_id, condition_id, expected, source in _sensitivity_sources(state["entrypoint"]):
        evidence = _evaluate_contract(
            workspace / "protocol-artifacts",
            state,
            source,
            compile_executable_contract(condition_id, state["entrypoint"]),
        )
        observed = bool(evidence["passed"])
        results.append({
            "fixture_id": fixture_id,
            "condition_id": condition_id,
            "expected_pass": expected,
            "observed_pass": observed,
            "matched": observed == expected,
            "evidence": evidence,
        })
    passed = len(results) == 4 and all(item["matched"] for item in results)
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "EMC_R3_INSTRUMENTATION_SENSITIVITY_PASSED" if passed else "EMC_R3_INSTRUMENTATION_SENSITIVITY_FAILED",
        "passed": passed,
        "results": results,
        "model_calls": 0,
        "calibration_authorized": passed,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(SENSITIVITY_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_emc_r3_calibration(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    sensitivity_path = workspace / "result-artifacts" / "records" / SENSITIVITY_RECORD
    sensitivity = _load_json(sensitivity_path)
    if sensitivity.get("manifest_digest") != manifest_digest or not sensitivity.get("passed"):
        raise RuntimeError("EMC-R3 calibration blocked because instrumentation sensitivity did not pass")
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "CALIBRATION"]
    draws = _execute(workspace, manifest, schedule, implementation_provider, progress)
    token_ceiling = int(manifest["resource_authority"]["derived_per_call_token_ceiling"])
    analysis = _analyze_draws(draws.values(), token_ceiling=token_ceiling)
    passed, verdict = _gate_verdict(draws.values(), analysis, "CALIBRATION", verdict_prefix="EMC_R3")
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": verdict,
        "passed": passed,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _usage(draws.values()),
        "validation_authorized": passed,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(CALIBRATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_emc_r3_validation(
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
        raise RuntimeError("EMC-R3 validation blocked because calibration did not pass")
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "VALIDATION"]
    draws = _execute(workspace, manifest, schedule, implementation_provider, progress)
    token_ceiling = int(manifest["resource_authority"]["derived_per_call_token_ceiling"])
    analysis = _analyze_draws(draws.values(), token_ceiling=token_ceiling)
    passed, gate_verdict = _gate_verdict(draws.values(), analysis, "VALIDATION", verdict_prefix="EMC_R3")
    verdict = "EMC_R3_EXECUTABLE_CONTRACT_TRANSMISSION_CONFIRMED_ON_TWO_NEW_DEV_STATES" if passed else gate_verdict
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "EMC_R3_COMPLETE",
        "passed": passed,
        "verdict": verdict,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _combine_usage(calibration["usage"], _usage(draws.values())),
        "claim_ceiling": manifest["claim_ceiling"],
        "search_value_established": False,
        "operator_causal_value_trial_protocol_authorized": passed,
        "fresh_value_trial_authorized": False,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(VALIDATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


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
                progress(f"EMC-R3 {schedule[0]['phase'].casefold()} draw {completed}/{len(schedule)} complete")
    return draws


def _freeze_task(store: ArtifactStore, role: str, task: Any) -> dict[str, Any]:
    entrypoint = "assign_clients" if task.task.category == "capacitated_cost_assignment" else "choose_sets"
    from discoveryos.benchmarks.executable_mechanism_contract import _profile_probe_source

    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
        "profile_probe.py": store.put_bytes(_profile_probe_source(entrypoint, task.task.category).encode("utf-8"), media_type="text/x-python"),
    }
    base_source = normalized_source(task.task.algorithm_source)
    state = {
        "state_id": f"emc-r3-{task.task.task_id}",
        "role": role,
        "task_id": task.task.task_id,
        "task_category": task.task.category,
        "task_payload_digest": task.payload_digest,
        "entrypoint": entrypoint,
        "base_source_digest": store.put_bytes(base_source.encode("utf-8"), media_type="text/x-python"),
        "task_files": files,
        "score_resolution": task.score_resolution,
    }
    return {**state, "state_digest": digest_json(state)}


def _development_tasks():
    return (
        ("CALIBRATION", _assignment_task("emc_r3_assignment_beta", (15101, 15121, 15139, 15161, 15187, 15217))),
        ("VALIDATION", _coverage_task("emc_r3_coverage_beta", (16111, 16127, 16139, 16183, 16217, 16223))),
    )


def _load_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("status") != "SEALED_PRE_SCIENTIFIC_MODEL_CALL":
        raise RuntimeError("EMC-R3 manifest was not sealed before scientific calls")
    if manifest.get("provider") != _provider_binding(provider):
        raise RuntimeError("EMC-R3 provider drift")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("EMC-R3 repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("EMC-R3 implementation binding drift")
    authority = load_resource_authority(
        Path(manifest["resource_authority"]["workspace"]),
        manifest["resource_authority"]["record_sha256"],
        provider,
    )
    if authority["record"]["derived_scientific_per_call_token_ceiling"] != manifest["resource_authority"]["derived_per_call_token_ceiling"]:
        raise RuntimeError("EMC-R3 resource ceiling authority drift")
    return manifest


def _bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("executable_mechanism_contract.py").resolve(),
        Path(__file__).with_name("emc_resource_calibration.py").resolve(),
        Path(__file__).with_name("si2_tasks.py").resolve(),
        Path(__file__).with_name("parent_intervention_real.py").resolve(),
        (Path(__file__).resolve().parents[1] / "runtime" / "provider_invocations.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]


def _combine_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_calls": int(first["model_calls"]) + int(second["model_calls"]),
        "tokens": int(first["tokens"]) + int(second["tokens"]),
        "wall_seconds_sum": float(first["wall_seconds_sum"]) + float(second["wall_seconds_sum"]),
    }
