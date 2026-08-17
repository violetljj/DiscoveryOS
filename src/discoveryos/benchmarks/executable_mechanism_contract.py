from __future__ import annotations

import ast
import concurrent.futures
import json
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from discoveryos.benchmarks.parent_intervention_real import _evaluate_descendant, _run_python
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.provider_invocations import DurableProviderInvoker, assert_no_orphaned_invocations
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "EMC_R2_EXECUTABLE_MECHANISM_CONTRACT"
MANIFEST_RECORD = "emc-r2-manifest.json"
SENSITIVITY_RECORD = "emc-r2-instrumentation-sensitivity.json"
PREFLIGHT_RECORD = "emc-r2-provider-preflight.json"
CALIBRATION_RECORD = "emc-r2-implementation-calibration.json"
VALIDATION_RECORD = "emc-r2-implementation-validation.json"
CONDITION_DIRECT = "DIRECT_CONSTRUCTION"
CONDITION_REPAIR = "POST_CONSTRUCTION_REPAIR"
REPLICATES_PER_CONDITION = 3
PREFLIGHT_TOKEN_CEILING = 60_000
IMPLEMENTATION_TOKEN_CEILING = 60_000
MAX_WORKERS = 2


IMPLEMENTATION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["implementation_source"],
    "properties": {"implementation_source": {"type": "string", "minLength": 1}},
}


MECHANISM_OBJECTS: dict[str, dict[str, Any]] = {
    CONDITION_DIRECT: {
        "mechanism_family": "direct_constructive_selection",
        "hypothesis": "a single constructive path is sufficient and no post-construction repair should execute",
        "required_intervention": "construct a feasible answer through emc_construct and return it directly",
        "forbidden_fallbacks": ["emc_improve", "inherited_solver"],
        "invariants": ["api_preserved", "feasibility_preserved", "inputs_immutable", "standard_library_only"],
        "expected_behavioral_signature": "construct_calls_positive_and_improve_calls_zero",
        "failure_semantics": "fail closed when required construction is not observed",
    },
    CONDITION_REPAIR: {
        "mechanism_family": "post_construction_repair",
        "hypothesis": "a real post-construction repair path should execute after the constructive seed",
        "required_intervention": "call emc_construct, then call emc_improve on the seed before returning",
        "forbidden_fallbacks": ["inherited_solver"],
        "invariants": ["api_preserved", "feasibility_preserved", "inputs_immutable", "standard_library_only"],
        "expected_behavioral_signature": "construct_calls_positive_and_improve_calls_positive",
        "failure_semantics": "fail closed when either required runtime path is not observed",
    },
}


def compile_executable_contract(condition_id: str, entrypoint: str) -> dict[str, Any]:
    if condition_id not in MECHANISM_OBJECTS:
        raise ValueError(f"unknown EMC condition: {condition_id}")
    required = ["emc_construct"]
    forbidden = ["inherited_solver"]
    counters: dict[str, dict[str, int | None]] = {
        "emc_construct": {"minimum": 1, "maximum": None},
        "emc_improve": {"minimum": 0, "maximum": 0},
        "inherited_solver": {"minimum": 0, "maximum": 0},
    }
    required_edges = [[entrypoint, "emc_construct"]]
    if condition_id == CONDITION_REPAIR:
        required.append("emc_improve")
        counters["emc_improve"] = {"minimum": 1, "maximum": None}
        required_edges.append([entrypoint, "emc_improve"])
    else:
        forbidden.append("emc_improve")
    payload = {
        "contract_version": "EMC_CONTRACT_V1",
        "entrypoint": entrypoint,
        "required_functions": required,
        "forbidden_functions": forbidden,
        "required_call_edges": required_edges,
        "runtime_counters": counters,
        "invariants": MECHANISM_OBJECTS[condition_id]["invariants"],
        "evidence_source": "independent_profile_harness",
        "candidate_self_reported_counters_authoritative": False,
    }
    return {**payload, "contract_digest": digest_json(payload)}


@dataclass(frozen=True, slots=True)
class ImplementationDraw:
    state_id: str
    condition_id: str
    draw_id: str
    contract_digest: str
    evaluable: bool
    source_valid: bool
    static_contract_passed: bool
    runtime_contract_passed: bool
    invariant_canary_passed: bool
    counter_signature: tuple[float, ...]
    counters: dict[str, int]
    token_cost: int
    wall_seconds: float
    source_sha256: str
    source_artifact_digest: str | None
    generation: dict[str, Any]
    evaluation: dict[str, Any]
    contract_evidence: dict[str, Any]


def seal_emc_protocol(
    workspace: Path,
    *,
    implementation_provider: PatchProvider,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    if max_workers < 1 or max_workers > 3:
        raise ValueError("EMC max_workers must be between one and three")
    _validate_provider(implementation_provider)
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
        "status": "SEALED_PRE_MODEL_CALL",
        "scope": "NEW_DEVELOPMENT_STATES_EXECUTABLE_CONTRACT_TRANSMISSION_ONLY",
        "scientific_question": (
            "When an implementation generator receives a frozen structured Mechanism Object plus a "
            "deterministically compiled executable contract, does independently observed runtime execution "
            "satisfy the required and forbidden mechanism paths?"
        ),
        "claim_ceiling": "EXECUTABLE_MECHANISM_CONTRACT_TRANSMISSION_ON_TWO_NEW_DEV_STATES_ONLY",
        "model_calls_before_seal": 0,
        "fresh_search_value_tasks_consumed": 0,
        "provider": _provider_binding(implementation_provider),
        "mechanism_objects": MECHANISM_OBJECTS,
        "compiler": {
            "deterministic": True,
            "compiler_source_sha256": digest_bytes(Path(__file__).read_bytes()),
            "candidate_cannot_modify_contract": True,
        },
        "isolation": {
            "implementation_sees": ["task_question", "base_source", "canonical_mechanism_object", "executable_contract"],
            "implementation_forbidden_context": ["condition_id", "instrumentation_source", "hidden_evaluator"],
            "runtime_evidence_collected_by": "independent_profile_harness",
            "candidate_self_reported_counters_authoritative": False,
        },
        "cheap_first_gates": [
            "E0_INSTRUMENTATION_SENSITIVITY_NO_MODEL",
            "E1_PROVIDER_AND_RESOURCE_PREFLIGHT_ONE_CALL",
            "E2_IMPLEMENTATION_CALIBRATION_SIX_CALLS",
            "E3_INDEPENDENT_IMPLEMENTATION_VALIDATION_SIX_CALLS",
        ],
        "gates": {
            "E0": {
                "positive_controls_required": 2,
                "negative_controls_required": 2,
                "model_calls": 0,
            },
            "E1": {"model_calls": 1, "per_call_token_ceiling": PREFLIGHT_TOKEN_CEILING},
            "E2": {
                "model_calls": 6,
                "all_draws_evaluable": True,
                "all_sources_valid": True,
                "all_static_contracts_pass": True,
                "all_runtime_contracts_pass": True,
                "all_invariant_canaries_pass": True,
                "between_condition_signature_must_differ": True,
            },
            "E3": {
                "model_calls": 6,
                "same_requirements_as_E2": True,
                "independent_state": True,
            },
        },
        "resource_policy": {
            "implementation_per_call_token_ceiling": IMPLEMENTATION_TOKEN_CEILING,
            "ceiling_basis": "new protocol bound exceeds the observed GCF-V2 R3 maximum 53655 without modifying R3",
            "resource_violation_semantics": "NOT_EVALUABLE_RESOURCE_CEILING",
            "provider_enforcement": "post_call_receipt_check",
        },
        "states": states,
        "implementation_schedule": schedule,
        "repository": _repository_snapshot(),
        "environment": _environment_snapshot(_provider_version(implementation_provider), max_workers),
        "implementation_bindings": _implementation_bindings(),
        "not_authorized": [
            "GCF-V2 root mutation or replay",
            "candidate self-reported runtime evidence",
            "utility or superiority claim",
            "fresh search-value trial",
            "post-result task, contract, threshold, replicate, or ceiling changes",
        ],
        "fresh_budget_authorized": False,
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "maximum_model_calls": 13,
        "fresh_search_value_tasks_consumed": 0,
    }


def run_instrumentation_sensitivity(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    state = manifest["states"][0]
    fixtures = _sensitivity_sources(state["entrypoint"])
    results = []
    for fixture_id, condition_id, expected, source in fixtures:
        contract = compile_executable_contract(condition_id, state["entrypoint"])
        evidence = _evaluate_contract(workspace / "protocol-artifacts", state, source, contract)
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
        "status": "EMC_R2_INSTRUMENTATION_SENSITIVITY_PASSED" if passed else "EMC_R2_INSTRUMENTATION_SENSITIVITY_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "passed": passed,
        "results": results,
        "model_calls": 0,
        "scientific_evidence": False,
        "provider_preflight_authorized": passed,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(SENSITIVITY_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_provider_preflight(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    sensitivity_path = workspace / "result-artifacts" / "records" / SENSITIVITY_RECORD
    sensitivity = _load_json(sensitivity_path)
    if sensitivity.get("manifest_digest") != manifest_digest or not sensitivity.get("passed"):
        raise RuntimeError("EMC provider preflight blocked because instrumentation sensitivity did not pass")
    item = next(item for item in manifest["implementation_schedule"] if item["phase"] == "CALIBRATION")
    state = next(state for state in manifest["states"] if state["state_id"] == item["state_id"])
    draw = _generate_implementation(workspace, state, {**item, "draw_id": "emc-r2-provider-preflight"}, implementation_provider)
    resource_ok = draw.token_cost <= PREFLIGHT_TOKEN_CEILING
    passed = draw.evaluable and resource_ok
    record = {
        "status": "EMC_R2_PROVIDER_PREFLIGHT_PASSED" if passed else "EMC_R2_PROVIDER_PREFLIGHT_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "sensitivity_record_sha256": digest_bytes(sensitivity_path.read_bytes()),
        "passed": passed,
        "resource_ceiling_respected": resource_ok,
        "draw": jsonable(draw),
        "usage": _usage([draw]),
        "scientific_evidence": False,
        "calibration_authorized": passed,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(PREFLIGHT_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_implementation_calibration(
    workspace: Path,
    *,
    manifest_digest: str,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, implementation_provider)
    preflight_path = workspace / "result-artifacts" / "records" / PREFLIGHT_RECORD
    preflight = _load_json(preflight_path)
    if preflight.get("manifest_digest") != manifest_digest or not preflight.get("passed"):
        raise RuntimeError("EMC calibration blocked because provider preflight did not pass")
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "CALIBRATION"]
    draws = _execute_implementations(workspace, manifest, schedule, implementation_provider, progress)
    analysis = _analyze_draws(draws.values())
    passed, verdict = _gate_verdict(draws.values(), analysis, "CALIBRATION")
    record = {
        "status": verdict,
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "preflight_record_sha256": digest_bytes(preflight_path.read_bytes()),
        "passed": passed,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _combine_usage(preflight["usage"], _usage(draws.values())),
        "validation_authorized": passed,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(CALIBRATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_implementation_validation(
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
        raise RuntimeError("EMC validation blocked because implementation calibration did not pass")
    schedule = [item for item in manifest["implementation_schedule"] if item["phase"] == "VALIDATION"]
    draws = _execute_implementations(workspace, manifest, schedule, implementation_provider, progress)
    analysis = _analyze_draws(draws.values())
    passed, gate_verdict = _gate_verdict(draws.values(), analysis, "VALIDATION")
    verdict = (
        "EXECUTABLE_MECHANISM_CONTRACT_TRANSMISSION_DETECTED_ON_TWO_DEV_STATES"
        if passed
        else gate_verdict
    )
    record = {
        "status": "EMC_R2_COMPLETE",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "calibration_record_sha256": digest_bytes(calibration_path.read_bytes()),
        "passed": passed,
        "verdict": verdict,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, schedule),
        "usage": _combine_usage(calibration["usage"], _usage(draws.values())),
        "claim_ceiling": manifest["claim_ceiling"],
        "search_value_established": False,
        "fresh_value_trial_authorized": False,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(VALIDATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def _development_tasks():
    return (
        ("CALIBRATION", _assignment_task("emc_r1_assignment_alpha", (13103, 13127, 13159, 13177, 13217, 13241))),
        ("VALIDATION", _coverage_task("emc_r1_coverage_alpha", (14107, 14143, 14159, 14177, 14207, 14221))),
    )


def _freeze_task(store: ArtifactStore, role: str, task: Any) -> dict[str, Any]:
    entrypoint = "assign_clients" if task.task.category == "capacitated_cost_assignment" else "choose_sets"
    probe_source = _profile_probe_source(entrypoint, task.task.category)
    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"),
        "evaluate.py": store.put_bytes(normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"),
        "profile_probe.py": store.put_bytes(probe_source.encode("utf-8"), media_type="text/x-python"),
    }
    base_source = normalized_source(task.task.algorithm_source)
    state = {
        "state_id": f"emc-r2-{task.task.task_id}",
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


def _execute_implementations(
    workspace: Path,
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    provider: PatchProvider,
    progress: Callable[[str], None] | None,
) -> dict[str, ImplementationDraw]:
    assert_no_orphaned_invocations(workspace / "result-artifacts")
    states = {state["state_id"]: state for state in manifest["states"]}
    result_store = ArtifactStore(workspace / "result-artifacts")

    def execute(item: dict[str, Any]) -> ImplementationDraw:
        path = result_store.records / _draw_record_name(manifest, item["draw_id"])
        if path.is_file():
            saved = _load_json(path)
            _verify_checkpoint(saved, manifest, item)
            return _draw_from_json(saved["draw"])
        draw = _generate_implementation(workspace, states[item["state_id"]], item, provider)
        body = jsonable(draw)
        result_store.write_record(_draw_record_name(manifest, item["draw_id"]), {
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
                progress(f"EMC {schedule[0]['phase'].casefold()} draw {completed}/{len(schedule)} complete")
    return draws


def _generate_implementation(
    workspace: Path,
    state: dict[str, Any],
    item: dict[str, Any],
    provider: PatchProvider,
    *,
    protocol_id: str = PROTOCOL_ID,
    token_ceiling: int = IMPLEMENTATION_TOKEN_CEILING,
) -> ImplementationDraw:
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    result_store = ArtifactStore(workspace / "result-artifacts")
    question = protocol_store.get_bytes(state["task_files"]["question"]).decode("utf-8")
    base_source = protocol_store.get_bytes(state["base_source_digest"]).decode("utf-8")
    mechanism = MECHANISM_OBJECTS[item["condition_id"]]
    contract = item["contract"]
    prompt = _implementation_prompt_template().format(
        question=question,
        base_source=base_source,
        mechanism_object=json.dumps(mechanism, sort_keys=True, separators=(",", ":")),
        executable_contract=json.dumps(contract, sort_keys=True, separators=(",", ":")),
    )
    request = GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider=provider.provider_name,
        model=provider.model,
        provider_settings_digest=getattr(provider, "settings_digest", ""),
        prompt_template_digest=digest_json({"stage": "emc_implementation", "template": _implementation_prompt_template()}),
        context_digest=digest_json({"state": state["state_digest"], "draw": item}),
        prompt=prompt,
        token_ceiling=token_ceiling,
    )
    started = time.monotonic()
    source = ""
    evaluable = False
    evaluation = {"score": 0.0, "valid": False, "probe_scores": [], "failure": "NOT_RUN"}
    evidence = _empty_contract_evidence("NOT_RUN")
    usage = ResourceUsage()
    try:
        invocation = DurableProviderInvoker(
            workspace / "result-artifacts",
            namespace=f"{protocol_id}:{item['draw_id']}",
        ).invoke(provider, request)
        generated = invocation.generation
        payload = json.loads(generated.raw_response)
        if set(payload) != {"implementation_source"} or not isinstance(payload["implementation_source"], str):
            raise ValueError("implementation response does not match the frozen schema")
        source = payload["implementation_source"]
        evaluation = _evaluate_descendant(protocol_store, state, source)
        evidence = _evaluate_contract(workspace / "protocol-artifacts", state, source, contract)
        evaluable = not generated.refused
        usage = generated.usage
        generation = {
            **_generation_success(request, generated, evaluable),
            "durable_invocation_recovered": invocation.recovered,
        }
    except (GenerationProviderError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        usage = error.usage if isinstance(error, GenerationProviderError) and error.usage else ResourceUsage()
        generation = _generation_failure(request, error, usage, started)
    counters = evidence.get("runtime", {}).get("counters", {})
    signature = tuple(float(counters.get(name, 0) > 0) for name in ("emc_construct", "emc_improve", "inherited_solver"))
    return ImplementationDraw(
        state_id=state["state_id"],
        condition_id=item["condition_id"],
        draw_id=item["draw_id"],
        contract_digest=contract["contract_digest"],
        evaluable=evaluable,
        source_valid=bool(evaluation.get("valid")),
        static_contract_passed=bool(evidence.get("static", {}).get("passed")),
        runtime_contract_passed=bool(evidence.get("runtime", {}).get("passed")),
        invariant_canary_passed=bool(evidence.get("invariant_canary", {}).get("passed")),
        counter_signature=signature,
        counters={name: int(counters.get(name, 0)) for name in ("emc_construct", "emc_improve", "inherited_solver")},
        token_cost=int(usage.tokens),
        wall_seconds=float(usage.wall_seconds),
        source_sha256=digest_bytes(source.encode("utf-8")),
        source_artifact_digest=result_store.put_bytes(source.encode("utf-8"), media_type="text/x-python") if source else None,
        generation=generation,
        evaluation=evaluation,
        contract_evidence=evidence,
    )


def _evaluate_contract(protocol_root: Path, state: dict[str, Any], source: str, contract: dict[str, Any]) -> dict[str, Any]:
    static = _static_contract_evidence(source, contract)
    store = ArtifactStore(protocol_root)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "algorithm.py").write_text(source, encoding="utf-8")
        (root / "profile_probe.py").write_bytes(store.get_bytes(state["task_files"]["profile_probe.py"]))
        profile = _run_python(root, "profile_probe.py")
        public = None
        (root / "public_tests.py").write_bytes(store.get_bytes(state["task_files"]["public_tests.py"]))
        public = _run_python(root, "public_tests.py")
    runtime_payload: dict[str, Any] = {}
    try:
        runtime_payload = json.loads(profile.stdout.strip()) if profile.returncode == 0 else {}
    except json.JSONDecodeError:
        runtime_payload = {}
    counters = runtime_payload.get("counters", {}) if isinstance(runtime_payload, dict) else {}
    runtime_checks = []
    for name, bounds in contract["runtime_counters"].items():
        value = int(counters.get(name, 0))
        minimum = int(bounds["minimum"])
        maximum = bounds["maximum"]
        passed = value >= minimum and (maximum is None or value <= int(maximum))
        runtime_checks.append({"counter": name, "value": value, "minimum": minimum, "maximum": maximum, "passed": passed})
    runtime = {
        "passed": profile.returncode == 0 and len(runtime_checks) == 3 and all(item["passed"] for item in runtime_checks),
        "returncode": profile.returncode,
        "stdout_sha256": digest_bytes(profile.stdout.encode("utf-8")),
        "stderr_sha256": digest_bytes(profile.stderr.encode("utf-8")),
        "counters": {name: int(counters.get(name, 0)) for name in contract["runtime_counters"]},
        "checks": runtime_checks,
    }
    invariant = {
        "passed": public.returncode == 0,
        "returncode": public.returncode,
        "stdout_sha256": digest_bytes(public.stdout.encode("utf-8")),
        "stderr_sha256": digest_bytes(public.stderr.encode("utf-8")),
    }
    return {"passed": static["passed"] and runtime["passed"] and invariant["passed"], "static": static, "runtime": runtime, "invariant_canary": invariant}


def _static_contract_evidence(source: str, contract: dict[str, Any]) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return {"passed": False, "failure": f"SYNTAX_ERROR:{error.msg}", "defined_functions": [], "call_edges": []}
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    edges: set[tuple[str, str]] = set()
    for owner, node in functions.items():
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                edges.add((owner, child.func.id))
    required_functions = set(contract["required_functions"])
    forbidden_functions = set(contract["forbidden_functions"])
    required_edges = {tuple(edge) for edge in contract["required_call_edges"]}
    checks = {
        "entrypoint_defined": contract["entrypoint"] in functions,
        "required_functions_defined": required_functions.issubset(functions),
        "forbidden_functions_absent": forbidden_functions.isdisjoint(functions),
        "required_call_edges_present": required_edges.issubset(edges),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "defined_functions": sorted(functions),
        "call_edges": [list(edge) for edge in sorted(edges)],
    }


def _profile_probe_source(entrypoint: str, category: str) -> str:
    if category == "capacitated_cost_assignment":
        cases = "[([[4,1],[2,5],[3,2]],[2,2]), ([[8,2],[1,9],[3,4],[7,1]],[2,2])]"
    else:
        cases = "[([tuple([0,1]),tuple([1,2]),tuple([2,3])],[1,2,3,4],2), ([tuple([0,2]),tuple([1,3]),tuple([0,3])],[2,3,5,7],2)]"
    return normalized_source(f'''\
import json
import sys
import algorithm

NAMES = {{"emc_construct", "emc_improve", "inherited_solver"}}
counters = {{name: 0 for name in NAMES}}

def observe(frame, event, arg):
    if event == "call" and frame.f_code.co_name in NAMES and frame.f_code.co_filename.endswith("algorithm.py"):
        counters[frame.f_code.co_name] += 1
    return observe

sys.setprofile(observe)
try:
    for args in {cases}:
        algorithm.{entrypoint}(*args)
finally:
    sys.setprofile(None)
print(json.dumps({{"counters": counters}}, sort_keys=True))
''')


def _sensitivity_sources(entrypoint: str) -> list[tuple[str, str, bool, str]]:
    if entrypoint == "assign_clients":
        construct = "return [facility for facility, capacity in enumerate(capacities) for _ in range(capacity)][:len(costs)]"
        args = "costs, capacities"
    else:
        construct = "return list(range(min(limit, len(sets))))"
        args = "sets, weights, limit"
    direct = f"def emc_construct({args}):\n    {construct}\n\ndef {entrypoint}({args}):\n    return emc_construct({args})\n"
    repair = (
        f"def emc_construct({args}):\n    {construct}\n\ndef emc_improve(value, *unused):\n    return value\n\n"
        f"def {entrypoint}({args}):\n    seed = emc_construct({args})\n    return emc_improve(seed)\n"
    )
    inert = f"def {entrypoint}({args}):\n    {construct}\n"
    forbidden = direct + "\ndef inherited_solver():\n    return None\n"
    return [
        ("positive_direct", CONDITION_DIRECT, True, direct),
        ("positive_repair", CONDITION_REPAIR, True, repair),
        ("negative_missing_required", CONDITION_REPAIR, False, inert),
        ("negative_forbidden_fallback", CONDITION_DIRECT, False, forbidden),
    ]


def _implementation_prompt_template() -> str:
    return (
        "Implement the immutable Mechanism Object and its deterministic Executable Mechanism Contract. "
        "The exact required function names and entrypoint call edges are executable obligations, not suggestions. "
        "Do not add the forbidden functions or substitute self-reported counters. Preserve the public API, "
        "feasibility, input immutability, and standard-library-only constraint. Return a complete algorithm.py.\n\n"
        "TASK:\n{question}\n\nBASE algorithm.py:\n```python\n{base_source}```\n\n"
        "CANONICAL MECHANISM OBJECT:\n{mechanism_object}\n\nEXECUTABLE MECHANISM CONTRACT:\n{executable_contract}"
    )


def _analyze_draws(
    draws: Iterable[ImplementationDraw],
    *,
    token_ceiling: int = IMPLEMENTATION_TOKEN_CEILING,
) -> dict[str, Any]:
    values = list(draws)
    direct = [draw for draw in values if draw.condition_id == CONDITION_DIRECT]
    repair = [draw for draw in values if draw.condition_id == CONDITION_REPAIR]
    direct_signatures = {draw.counter_signature for draw in direct}
    repair_signatures = {draw.counter_signature for draw in repair}
    separated = len(direct_signatures) == 1 and len(repair_signatures) == 1 and direct_signatures.isdisjoint(repair_signatures)
    return {
        "draws": len(values),
        "all_evaluable": all(draw.evaluable for draw in values),
        "all_sources_valid": all(draw.source_valid for draw in values),
        "all_static_contracts_passed": all(draw.static_contract_passed for draw in values),
        "all_runtime_contracts_passed": all(draw.runtime_contract_passed for draw in values),
        "all_invariant_canaries_passed": all(draw.invariant_canary_passed for draw in values),
        "resource_ceilings_respected": all(draw.token_cost <= token_ceiling for draw in values),
        "between_condition_counter_signatures_separated": separated,
        "within_condition_signatures": {
            CONDITION_DIRECT: [list(value) for value in sorted(direct_signatures)],
            CONDITION_REPAIR: [list(value) for value in sorted(repair_signatures)],
        },
        "contract_pass_counts": {
            CONDITION_DIRECT: sum(draw.static_contract_passed and draw.runtime_contract_passed for draw in direct),
            CONDITION_REPAIR: sum(draw.static_contract_passed and draw.runtime_contract_passed for draw in repair),
        },
        "utility_record_only": {
            CONDITION_DIRECT: [draw.evaluation.get("score", 0.0) for draw in direct],
            CONDITION_REPAIR: [draw.evaluation.get("score", 0.0) for draw in repair],
        },
        "token_costs": [draw.token_cost for draw in values],
    }


def _gate_verdict(
    draws: Iterable[ImplementationDraw],
    analysis: dict[str, Any],
    phase: str,
    *,
    verdict_prefix: str = "EMC_R2",
    replicates_per_condition: int = REPLICATES_PER_CONDITION,
) -> tuple[bool, str]:
    values = list(draws)
    if not analysis["resource_ceilings_respected"] or not analysis["all_evaluable"]:
        return False, f"{verdict_prefix}_{phase}_NOT_EVALUABLE_RESOURCE_OR_PROVIDER"
    if not analysis["all_sources_valid"] or not analysis["all_invariant_canaries_passed"]:
        return False, f"{verdict_prefix}_{phase}_IMPLEMENTATION_INVALID"
    if not analysis["all_static_contracts_passed"]:
        return False, f"{verdict_prefix}_{phase}_STATIC_CONTRACT_FAILED"
    if not analysis["all_runtime_contracts_passed"]:
        return False, f"{verdict_prefix}_{phase}_RUNTIME_CONTRACT_FAILED"
    if not analysis["between_condition_counter_signatures_separated"]:
        return False, f"{verdict_prefix}_{phase}_RUNTIME_SIGNATURE_NOT_SEPARATED"
    if len(values) != 2 * replicates_per_condition:
        return False, f"{verdict_prefix}_{phase}_INCOMPLETE"
    return True, f"{verdict_prefix}_{phase}_PASSED"


def _provider_binding(provider: PatchProvider) -> dict[str, Any]:
    return {
        "name": provider.provider_name,
        "model": provider.model,
        "version": _provider_version(provider),
        "settings_digest": getattr(provider, "settings_digest", ""),
        "output_schema_digest": digest_json(getattr(provider, "output_schema", None)),
    }


def _provider_version(provider: PatchProvider) -> str:
    return str(getattr(provider, "provider_version", "unknown"))


def _validate_provider(provider: PatchProvider) -> None:
    if _provider_version(provider) in {"", "unknown"}:
        raise RuntimeError("EMC requires a reportable provider version")
    if getattr(provider, "output_schema", None) != IMPLEMENTATION_SCHEMA:
        raise RuntimeError("EMC implementation provider must use the frozen schema")


def _load_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("status") != "SEALED_PRE_MODEL_CALL":
        raise RuntimeError("EMC manifest was not sealed before model calls")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("EMC repository commit differs from the sealed manifest")
    if _provider_binding(provider) != manifest["provider"]:
        raise RuntimeError("EMC provider/model/settings differ from the sealed manifest")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("EMC implementation binding drift")
    return manifest


def _draw_record_name(manifest: dict[str, Any], draw_id: str) -> str:
    digest = digest_json({"manifest": manifest["manifest_digest"], "stage": "implementation", "draw": draw_id})
    return f"draws/implementations/{digest}.json"


def _verify_checkpoint(saved: dict[str, Any], manifest: dict[str, Any], item: dict[str, Any]) -> None:
    if (
        saved.get("manifest_digest") != manifest["manifest_digest"]
        or saved.get("draw_id") != item["draw_id"]
        or saved.get("condition_id") != item["condition_id"]
        or saved.get("draw_digest") != digest_json(saved.get("draw"))
    ):
        raise RuntimeError("EMC draw checkpoint binding mismatch")


def _draw_bindings(workspace: Path, manifest: dict[str, Any], schedule: list[dict[str, Any]]) -> list[dict[str, str]]:
    root = workspace / "result-artifacts" / "records"
    result = []
    for item in schedule:
        path = root / _draw_record_name(manifest, item["draw_id"])
        result.append({"draw_id": item["draw_id"], "path": str(path), "sha256": digest_bytes(path.read_bytes())})
    return result


def _draw_from_json(value: dict[str, Any]) -> ImplementationDraw:
    return ImplementationDraw(**{**value, "counter_signature": tuple(value["counter_signature"])})


def _generation_success(request: GenerationRequest, generated: Any, evaluable: bool) -> dict[str, Any]:
    return {
        "status": "SUCCEEDED" if evaluable else "REFUSED",
        "generation_id": request.generation_id,
        "provider_request_id": generated.provider_request_id,
        "provider_version": generated.provider_version,
        "raw_response_sha256": digest_bytes(generated.raw_response.encode("utf-8")),
        "transport_log_sha256": digest_bytes((generated.transport_log or "").encode("utf-8")),
        "usage": jsonable(generated.usage),
        "latency_seconds": generated.latency_seconds,
    }


def _generation_failure(request: GenerationRequest, error: Exception, usage: ResourceUsage, started: float) -> dict[str, Any]:
    record = {
        "status": "PROVIDER_OR_SCHEMA_FAILURE",
        "generation_id": request.generation_id,
        "failure_signature": getattr(error, "signature", type(error).__name__),
        "usage": jsonable(usage),
        "latency_seconds": time.monotonic() - started,
    }
    if isinstance(error, GenerationProviderError):
        record["transport_log_excerpt"] = (error.transport_log or "")[-2_000:]
    return record


def _empty_contract_evidence(failure: str) -> dict[str, Any]:
    return {
        "passed": False,
        "failure": failure,
        "static": {"passed": False},
        "runtime": {"passed": False, "counters": {}},
        "invariant_canary": {"passed": False},
    }


def _usage(draws: Iterable[ImplementationDraw]) -> dict[str, Any]:
    values = list(draws)
    return {"model_calls": len(values), "tokens": sum(draw.token_cost for draw in values), "wall_seconds_sum": sum(draw.wall_seconds for draw in values)}


def _combine_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {key: first[key] + second[key] for key in ("model_calls", "tokens", "wall_seconds_sum")}


def _load_json(path: Path, expected_digest: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required EMC artifact missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if expected_digest is not None:
        payload = {key: item for key, item in value.items() if key != "manifest_digest"}
        if value.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
            raise RuntimeError("sealed EMC manifest digest mismatch")
    return value


def _environment_snapshot(provider_version: str, max_workers: int) -> dict[str, Any]:
    import shutil

    usage = shutil.disk_usage(Path.cwd().anchor)
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "free_disk_bytes_at_seal": usage.free,
        "provider_version": provider_version,
        "max_workers": max_workers,
    }


def _repository_snapshot() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    status = subprocess.run(("git", "status", "--short"), cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if head.returncode != 0 or status.returncode != 0:
        raise RuntimeError("EMC requires a readable Git repository")
    return {"head_commit": head.stdout.strip(), "worktree_clean_at_observation": not bool(status.stdout.strip())}


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("si2_tasks.py").resolve(),
        Path(__file__).with_name("parent_intervention_real.py").resolve(),
        (Path(__file__).resolve().parents[1] / "runtime" / "provider_invocations.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
