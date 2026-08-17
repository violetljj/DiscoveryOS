from __future__ import annotations

import concurrent.futures
import itertools
import json
import math
import os
import platform
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from discoveryos.benchmarks.mechanism_brief_real import _source_signature
from discoveryos.benchmarks.parent_intervention_real import _evaluate_descendant
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import _balanced_cut_task, _coverage_task
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "GCF_V2_STRUCTURED_MECHANISM_MEDIATION_R3"
MANIFEST_RECORD = "gcf-v2-r3-structured-mediation-manifest.json"
PREFLIGHT_RECORD = "gcf-v2-r3-provider-preflight.json"
PROPOSAL_RECORD = "gcf-v2-r3-structured-proposal-calibration.json"
PROPOSAL_VALIDATION_RECORD = "gcf-v2-r3-structured-proposal-validation.json"
IMPLEMENTATION_RECORD = "gcf-v2-r3-structured-implementation-calibration.json"
CONDITION_A = "CONSTRUCTIVE_GREEDY"
CONDITION_B = "ITERATIVE_LOCAL_IMPROVEMENT"
REPLICATES_PER_CONDITION = 3
MINIMUM_CALIBRATION_STATES = 1
PREFLIGHT_TOKEN_CEILING = 25_000
PROPOSAL_TOKEN_CEILING = 25_000
IMPLEMENTATION_TOKEN_CEILING = 30_000
SOURCE_MARGIN = 0.05
BEHAVIOR_MARGIN = 0.02
MAX_WORKERS = 2


CONDITIONS: dict[str, dict[str, Any]] = {
    CONDITION_A: {
        "brief": (
            "Construct the complete feasible solution in one deterministic marginal-priority pass. "
            "Do not perform post-construction local improvement, swaps, or repeated optimization."
        ),
        "expected": {
            "mechanism_family": "constructive_greedy",
            "construction_mode": "single_pass",
            "improvement_loop": "forbidden",
            "neighborhood_move": "none",
            "termination": "construction_complete",
        },
    },
    CONDITION_B: {
        "brief": (
            "Start from a feasible seed, then repeatedly apply a bounded improving swap, reassignment, or "
            "add-remove move until a local optimum or deterministic iteration bound. A real post-construction "
            "improvement loop is required."
        ),
        "expected": {
            "mechanism_family": "iterative_local_improvement",
            "construction_mode": "seed_then_improve",
            "improvement_loop": "required",
            "neighborhood_move": "swap_or_reassign",
            "termination": "local_optimum_or_bound",
        },
    },
}


MECHANISM_OBJECT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["mechanism"],
    "properties": {
        "mechanism": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "mechanism_family",
                "hypothesis",
                "algorithmic_change",
                "expected_control_flow",
                "forbidden_fallbacks",
                "invariants",
                "expected_behavioral_signatures",
                "failure_semantics",
            ],
            "properties": {
                "mechanism_family": {
                    "type": "string",
                    "enum": ["constructive_greedy", "iterative_local_improvement"],
                },
                "hypothesis": {"type": "string", "minLength": 1},
                "algorithmic_change": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["replace", "with"],
                    "properties": {
                        "replace": {"type": "string", "minLength": 1},
                        "with": {"type": "string", "minLength": 1},
                    },
                },
                "expected_control_flow": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["construction_mode", "improvement_loop", "neighborhood_move", "termination"],
                    "properties": {
                        "construction_mode": {"enum": ["single_pass", "seed_then_improve"]},
                        "improvement_loop": {"enum": ["forbidden", "required"]},
                        "neighborhood_move": {"enum": ["none", "swap_or_reassign"]},
                        "termination": {"enum": ["construction_complete", "local_optimum_or_bound"]},
                    },
                },
                "forbidden_fallbacks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "invariants": {
                    "type": "array",
                    "minItems": 3,
                    "items": {
                        "type": "string",
                        "enum": ["api_preserved", "feasibility_preserved", "inputs_immutable", "standard_library_only"]
                    },
                },
                "expected_behavioral_signatures": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "failure_semantics": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        }
    },
}


IMPLEMENTATION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["implementation_source"],
    "properties": {"implementation_source": {"type": "string", "minLength": 1}},
}


@dataclass(frozen=True, slots=True)
class MechanismObject:
    mechanism_family: str
    hypothesis: str
    replace: str
    with_: str
    construction_mode: str
    improvement_loop: str
    neighborhood_move: str
    termination: str
    forbidden_fallbacks: tuple[str, ...]
    invariants: tuple[str, ...]
    expected_behavioral_signatures: tuple[str, ...]
    failure_semantics: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, expected_condition: str) -> "MechanismObject":
        if set(payload) != {"mechanism"} or not isinstance(payload["mechanism"], dict):
            raise ValueError("structured proposal must contain exactly one mechanism object")
        value = payload["mechanism"]
        required = {
            "mechanism_family",
            "hypothesis",
            "algorithmic_change",
            "expected_control_flow",
            "forbidden_fallbacks",
            "invariants",
            "expected_behavioral_signatures",
            "failure_semantics",
        }
        if set(value) != required:
            raise ValueError("mechanism object fields do not match the frozen schema")
        change = value["algorithmic_change"]
        flow = value["expected_control_flow"]
        if not isinstance(change, dict) or set(change) != {"replace", "with"}:
            raise ValueError("algorithmic_change must contain replace and with")
        if not isinstance(flow, dict) or set(flow) != {
            "construction_mode", "improvement_loop", "neighborhood_move", "termination"
        }:
            raise ValueError("expected_control_flow fields do not match the frozen schema")
        list_fields = ("forbidden_fallbacks", "invariants", "expected_behavioral_signatures", "failure_semantics")
        for field in list_fields:
            items = value[field]
            if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
                raise ValueError(f"{field} must be a non-empty string array")
            if len(items) != len(set(items)):
                raise ValueError(f"{field} must contain unique entries")
        expected = CONDITIONS[expected_condition]["expected"]
        actual = {"mechanism_family": value["mechanism_family"], **flow}
        if actual != expected:
            raise ValueError("mechanism object contradicts the frozen condition contract")
        invariants = set(value["invariants"])
        allowed_invariants = {"api_preserved", "feasibility_preserved", "inputs_immutable", "standard_library_only"}
        if not invariants.issubset(allowed_invariants):
            raise ValueError("mechanism object contains an unknown invariant")
        if not {"api_preserved", "feasibility_preserved", "inputs_immutable"}.issubset(invariants):
            raise ValueError("mechanism object omits required invariants")
        scalar_text = (value["hypothesis"], change["replace"], change["with"])
        if not all(isinstance(item, str) and item.strip() for item in scalar_text):
            raise ValueError("mechanism object text fields must be non-empty")
        return cls(
            mechanism_family=str(value["mechanism_family"]),
            hypothesis=str(value["hypothesis"]),
            replace=str(change["replace"]),
            with_=str(change["with"]),
            construction_mode=str(flow["construction_mode"]),
            improvement_loop=str(flow["improvement_loop"]),
            neighborhood_move=str(flow["neighborhood_move"]),
            termination=str(flow["termination"]),
            forbidden_fallbacks=tuple(value["forbidden_fallbacks"]),
            invariants=tuple(value["invariants"]),
            expected_behavioral_signatures=tuple(value["expected_behavioral_signatures"]),
            failure_semantics=tuple(value["failure_semantics"]),
        )

    @property
    def categorical_signature(self) -> tuple[float, ...]:
        return (
            float(self.mechanism_family == "iterative_local_improvement"),
            float(self.construction_mode == "seed_then_improve"),
            float(self.improvement_loop == "required"),
            float(self.neighborhood_move == "swap_or_reassign"),
            float(self.termination == "local_optimum_or_bound"),
        )

    @property
    def canonical_payload(self) -> dict[str, Any]:
        return {
            "mechanism_family": self.mechanism_family,
            "hypothesis": self.hypothesis,
            "algorithmic_change": {"replace": self.replace, "with": self.with_},
            "expected_control_flow": {
                "construction_mode": self.construction_mode,
                "improvement_loop": self.improvement_loop,
                "neighborhood_move": self.neighborhood_move,
                "termination": self.termination,
            },
            "forbidden_fallbacks": list(self.forbidden_fallbacks),
            "invariants": list(self.invariants),
            "expected_behavioral_signatures": list(self.expected_behavioral_signatures),
            "failure_semantics": list(self.failure_semantics),
        }

    @property
    def digest(self) -> str:
        return digest_json(self.canonical_payload)


@dataclass(frozen=True, slots=True)
class ProposalDraw:
    state_id: str
    condition_id: str
    draw_id: str
    evaluable: bool
    contract_compliant: bool
    mechanism: dict[str, Any] | None
    mechanism_digest: str | None
    categorical_signature: tuple[float, ...]
    token_cost: int
    wall_seconds: float
    generation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ImplementationDraw:
    state_id: str
    condition_id: str
    draw_id: str
    mechanism_digest: str
    evaluable: bool
    valid: bool
    source_signature: tuple[float, ...]
    behavior_signature: tuple[float, ...]
    utility: float
    token_cost: int
    wall_seconds: float
    generation: dict[str, Any]
    source_sha256: str
    source_artifact_digest: str | None
    evaluation: dict[str, Any]


def seal_structured_mediation_protocol(
    workspace: Path,
    *,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    if max_workers < 1 or max_workers > 3:
        raise ValueError("GCF-V2 max_workers must be between one and three")
    _validate_provider_pair(proposal_provider, implementation_provider)
    workspace = workspace.resolve()
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_task(store, role, task) for role, task in _calibration_tasks()]
    schedule = [
        {
            "state_id": state["state_id"],
            "condition_id": condition,
            "phase": state["role"],
            "draw_id": f"{state['state_id']}:{condition.casefold()}:{replicate}",
            "replicate": replicate,
        }
        for state in states
        for condition in (CONDITION_A, CONDITION_B)
        for replicate in range(REPLICATES_PER_CONDITION)
    ]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_MODEL_CALL",
        "scope": "NEW_DEVELOPMENT_CALIBRATION_STATES_STRUCTURED_MEDIATION_ONLY",
        "scientific_question": (
            "Does a natural-language mechanism condition reliably produce a frozen structured Mechanism Object, "
            "and does an implementation generator that sees only that object transmit it into source and behavior?"
        ),
        "claim_ceiling": "STRUCTURED_MECHANISM_MEDIATION_ON_NEW_DEVELOPMENT_CALIBRATION_STATES_ONLY",
        "model_calls_before_seal": 0,
        "fresh_search_value_tasks_consumed": 0,
        "providers": {
            "proposal": _provider_binding(proposal_provider),
            "implementation": _provider_binding(implementation_provider),
        },
        "conditions": CONDITIONS,
        "mediation_isolation": {
            "proposal_sees": ["task_question", "base_source", "natural_language_mechanism_brief"],
            "implementation_sees": ["task_question", "base_source", "canonical_mechanism_object"],
            "implementation_forbidden_context": ["natural_language_mechanism_brief", "condition_id", "proposal_raw_response"],
            "separate_provider_requests": True,
        },
        "cheap_first_gate": {
            "provider_schema_preflight_calls": 1,
            "proposal_blocked_if_preflight_fails": True,
            "calibration_proposal_calls": sum(item["phase"] == "CALIBRATION" for item in schedule),
            "validation_proposal_calls": sum(item["phase"] == "VALIDATION" for item in schedule),
            "proposal_token_ceiling": PROPOSAL_TOKEN_CEILING,
            "replicates_per_state_condition": REPLICATES_PER_CONDITION,
            "minimum_detectable_states_per_phase": MINIMUM_CALIBRATION_STATES,
            "validation_blocked_if_calibration_fails": True,
            "implementation_blocked_if_proposal_gate_fails": True,
            "between_condition_must_exceed_within_condition": True,
        },
        "implementation_gate": {
            "maximum_calls_after_proposal_pass": len(schedule),
            "implementation_token_ceiling": IMPLEMENTATION_TOKEN_CEILING,
            "source_margin": SOURCE_MARGIN,
            "behavior_margin": BEHAVIOR_MARGIN,
            "minimum_source_detectable_states": MINIMUM_CALIBRATION_STATES,
            "minimum_behavior_detectable_states": MINIMUM_CALIBRATION_STATES,
            "utility_record_only": True,
        },
        "states": states,
        "proposal_schedule": schedule,
        "repository": _repository_snapshot(),
        "environment": _environment_snapshot(_provider_version(proposal_provider), max_workers),
        "implementation_bindings": _implementation_bindings(),
        "not_authorized": [
            "GCF-R1 consumed-root mutation or replay",
            "fresh search-value trial",
            "mechanism utility or system superiority claim",
            "post-result schema, task, replicate, threshold, or prompt tuning",
            "remote execution without a separately frozen worker contract",
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
        "proposal_calls_before_gate": sum(item["phase"] == "CALIBRATION" for item in schedule),
        "maximum_total_model_calls": 1 + len(schedule) * 2,
        "fresh_search_value_tasks_consumed": 0,
    }


def run_structured_provider_preflight(
    workspace: Path,
    *,
    manifest_digest: str,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, proposal_provider, implementation_provider)
    state = manifest["states"][0]
    item = {
        "state_id": state["state_id"],
        "condition_id": CONDITION_A,
        "draw_id": "gcf-v2-r2-provider-schema-preflight",
        "replicate": -1,
    }
    draw = _generate_proposal(ArtifactStore(workspace / "protocol-artifacts"), state, item, proposal_provider)
    passed = draw.evaluable and draw.contract_compliant and draw.token_cost <= PREFLIGHT_TOKEN_CEILING
    record = {
        "status": "GCF_V2_R2_PROVIDER_PREFLIGHT_PASSED" if passed else "GCF_V2_R2_PROVIDER_PREFLIGHT_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "passed": passed,
        "draw": jsonable(draw),
        "draw_digest": digest_json(jsonable(draw)),
        "usage": _usage([draw]),
        "scientific_evidence": False,
        "proposal_calibration_authorized": passed,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(PREFLIGHT_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def calibrate_structured_proposals(
    workspace: Path,
    *,
    manifest_digest: str,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, proposal_provider, implementation_provider)
    preflight_path = workspace / "result-artifacts" / "records" / PREFLIGHT_RECORD
    preflight = _load_json(preflight_path)
    if preflight.get("manifest_digest") != manifest_digest or not preflight.get("passed"):
        raise RuntimeError("GCF-V2 proposal calibration blocked because provider/schema preflight did not pass")
    schedule = [item for item in manifest["proposal_schedule"] if item["phase"] == "CALIBRATION"]
    draws = _execute_proposals(workspace, manifest, schedule, proposal_provider, progress)
    analysis = _analyze_proposals(manifest, draws)
    resource_ok = all(draw.token_cost <= PROPOSAL_TOKEN_CEILING for draw in draws.values())
    all_evaluable = all(draw.evaluable for draw in draws.values())
    all_compliant = all(draw.contract_compliant for draw in draws.values())
    passed = (
        resource_ok
        and all_evaluable
        and all_compliant
        and analysis["detectable_states"] >= MINIMUM_CALIBRATION_STATES
    )
    record = {
        "status": "GCF_V2_PROPOSAL_CALIBRATION_PASSED" if passed else "GCF_V2_PROPOSAL_CALIBRATION_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "preflight_record_sha256": digest_bytes(preflight_path.read_bytes()),
        "passed": passed,
        "all_draws_evaluable": all_evaluable,
        "all_objects_contract_compliant": all_compliant,
        "resource_ceilings_respected": resource_ok,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, "proposals", schedule),
        "usage": _combine_usage(preflight["usage"], _usage(draws.values())),
        "preflight_model_calls": 1,
        "scientific_proposal_model_calls": len(draws),
        "proposal_validation_authorized": passed,
        "implementation_calls_authorized": False,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(PROPOSAL_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def validate_structured_proposals(
    workspace: Path,
    *,
    manifest_digest: str,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, proposal_provider, implementation_provider)
    calibration_path = workspace / "result-artifacts" / "records" / PROPOSAL_RECORD
    calibration = _load_json(calibration_path)
    if calibration.get("manifest_digest") != manifest_digest or not calibration.get("passed"):
        raise RuntimeError("GCF-V2 proposal validation blocked because proposal calibration did not pass")
    schedule = [item for item in manifest["proposal_schedule"] if item["phase"] == "VALIDATION"]
    draws = _execute_proposals(workspace, manifest, schedule, proposal_provider, progress)
    analysis = _analyze_proposals(manifest, draws)
    resource_ok = all(draw.token_cost <= PROPOSAL_TOKEN_CEILING for draw in draws.values())
    all_evaluable = all(draw.evaluable for draw in draws.values())
    all_compliant = all(draw.contract_compliant for draw in draws.values())
    passed = resource_ok and all_evaluable and all_compliant and analysis["detectable_states"] >= 1
    record = {
        "status": "GCF_V2_PROPOSAL_VALIDATION_PASSED" if passed else "GCF_V2_PROPOSAL_VALIDATION_FAILED",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "calibration_record_sha256": digest_bytes(calibration_path.read_bytes()),
        "passed": passed,
        "all_draws_evaluable": all_evaluable,
        "all_objects_contract_compliant": all_compliant,
        "resource_ceilings_respected": resource_ok,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, "proposals", schedule),
        "usage": _combine_usage(calibration["usage"], _usage(draws.values())),
        "validation_model_calls": len(draws),
        "implementation_calls_authorized": passed,
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(PROPOSAL_VALIDATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_structured_implementation_calibration(
    workspace: Path,
    *,
    manifest_digest: str,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, proposal_provider, implementation_provider)
    proposal_path = workspace / "result-artifacts" / "records" / PROPOSAL_VALIDATION_RECORD
    proposal_record = _load_json(proposal_path)
    if proposal_record.get("manifest_digest") != manifest_digest or not proposal_record.get("passed"):
        raise RuntimeError("GCF-V2 implementation blocked because frozen proposal validation did not pass")
    proposals = _load_proposal_draws(workspace, manifest)
    draws = _execute_implementations(workspace, manifest, proposals, implementation_provider, progress)
    analysis = _analyze_implementations(manifest, draws)
    resource_ok = all(draw.token_cost <= IMPLEMENTATION_TOKEN_CEILING for draw in draws.values())
    all_evaluable = all(draw.evaluable for draw in draws.values())
    all_valid = all(draw.valid for draw in draws.values())
    source_count = int(analysis["source_detectable_states"])
    behavior_count = int(analysis["behavior_detectable_states"])
    mediated = (
        resource_ok
        and all_evaluable
        and all_valid
        and source_count >= MINIMUM_CALIBRATION_STATES
        and behavior_count >= MINIMUM_CALIBRATION_STATES
    )
    if not all_evaluable or not resource_ok:
        verdict = "GCF_V2_NOT_EVALUABLE"
    elif not all_valid:
        verdict = "STRUCTURED_MECHANISM_IMPLEMENTATION_INVALID"
    elif source_count < MINIMUM_CALIBRATION_STATES:
        verdict = "STRUCTURED_OBJECT_TO_IMPLEMENTATION_NOT_DETECTABLE"
    elif behavior_count < MINIMUM_CALIBRATION_STATES:
        verdict = "STRUCTURED_IMPLEMENTATION_WITHOUT_BEHAVIOR_MEDIATION"
    else:
        verdict = "STRUCTURED_MECHANISM_MEDIATION_DETECTED_ON_CALIBRATION"
    record = {
        "status": "GCF_V2_STRUCTURED_MEDIATION_CALIBRATION_COMPLETE",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "proposal_record_sha256": digest_bytes(proposal_path.read_bytes()),
        "verdict": verdict,
        "structured_mechanism_mediation_detected": mediated,
        "all_draws_evaluable": all_evaluable,
        "all_sources_valid": all_valid,
        "resource_ceilings_respected": resource_ok,
        "analysis": analysis,
        "draw_bindings": _draw_bindings(workspace, manifest, "implementations"),
        "usage": _combine_usage(proposal_record["usage"], _usage(draws.values())),
        "search_value_established": False,
        "fresh_value_trial_authorized": False,
        "next_budget_decision": (
            "ELIGIBLE_TO_PREREGISTER_INDEPENDENT_GCF_V2_VALIDATION"
            if mediated
            else "DO_NOT_OPEN_GCF_V2_VALIDATION"
        ),
        "claim_ceiling": manifest["claim_ceiling"],
        "fresh_search_value_tasks_consumed": 0,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(IMPLEMENTATION_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def _calibration_tasks():
    return (
        ("CALIBRATION", _coverage_task("gcf_v2_coverage_calibration_alpha", (11113, 11131, 11149, 11171, 11197, 11213))),
        ("VALIDATION", _balanced_cut_task("gcf_v2_cut_calibration_alpha", (12109, 12143, 12161, 12197, 12211, 12239))),
    )


def _freeze_task(store: ArtifactStore, role: str, task: Any) -> dict[str, Any]:
    files = {
        "question": store.put_bytes(task.task.question.encode("utf-8"), media_type="text/plain"),
        "public_tests.py": store.put_bytes(
            normalized_source(task.task.public_tests_source).encode("utf-8"), media_type="text/x-python"
        ),
        "evaluate.py": store.put_bytes(
            normalized_source(task.task.evaluator_source).encode("utf-8"), media_type="text/x-python"
        ),
    }
    base_source = normalized_source(task.task.algorithm_source)
    base_digest = store.put_bytes(base_source.encode("utf-8"), media_type="text/x-python")
    state = {
        "state_id": f"gcf-v2-{task.task.task_id}",
        "role": role,
        "task_id": task.task.task_id,
        "task_category": task.task.category,
        "task_payload_digest": task.payload_digest,
        "base_source_digest": base_digest,
        "task_files": files,
        "score_resolution": task.score_resolution,
    }
    return {**state, "state_digest": digest_json(state)}


def _execute_proposals(
    workspace: Path,
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    provider: PatchProvider,
    progress: Callable[[str], None] | None,
) -> dict[str, ProposalDraw]:
    states = {state["state_id"]: state for state in manifest["states"]}
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    result_store = ArtifactStore(workspace / "result-artifacts")

    def execute(item: dict[str, Any]) -> ProposalDraw:
        record = _draw_record_path(manifest, "proposals", item["draw_id"])
        path = result_store.records / record
        if path.is_file():
            saved = _load_json(path)
            _verify_checkpoint(saved, manifest, item)
            return _proposal_from_json(saved["draw"])
        draw = _generate_proposal(protocol_store, states[item["state_id"]], item, provider)
        body = jsonable(draw)
        result_store.write_record(record, {
            "manifest_digest": manifest["manifest_digest"],
            "draw_id": item["draw_id"],
            "condition_id": item["condition_id"],
            "draw": body,
            "draw_digest": digest_json(body),
        })
        return draw

    return _parallel_draws(manifest, schedule, execute, progress, "proposal")


def _generate_proposal(
    store: ArtifactStore,
    state: dict[str, Any],
    item: dict[str, Any],
    provider: PatchProvider,
) -> ProposalDraw:
    question = store.get_bytes(state["task_files"]["question"]).decode("utf-8")
    base_source = store.get_bytes(state["base_source_digest"]).decode("utf-8")
    prompt = _proposal_prompt_template().format(
        question=question,
        base_source=base_source,
        mechanism_brief=CONDITIONS[item["condition_id"]]["brief"],
    )
    request = _request(provider, prompt, _proposal_prompt_template(), state, item, PROPOSAL_TOKEN_CEILING, "proposal")
    started = time.monotonic()
    mechanism = None
    compliant = False
    evaluable = False
    signature = (0.0,) * 5
    try:
        generated = provider.generate(request)
        parsed = json.loads(generated.raw_response)
        value = MechanismObject.from_payload(parsed, expected_condition=item["condition_id"])
        mechanism = value.canonical_payload
        signature = value.categorical_signature
        compliant = True
        evaluable = not generated.refused
        usage = generated.usage
        generation = _generation_success(request, generated, evaluable)
    except (GenerationProviderError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        usage = error.usage if isinstance(error, GenerationProviderError) and error.usage else ResourceUsage()
        generation = _generation_failure(request, error, usage, started)
    return ProposalDraw(
        state_id=state["state_id"],
        condition_id=item["condition_id"],
        draw_id=item["draw_id"],
        evaluable=evaluable,
        contract_compliant=compliant,
        mechanism=mechanism,
        mechanism_digest=digest_json(mechanism) if mechanism else None,
        categorical_signature=signature,
        token_cost=int(usage.tokens),
        wall_seconds=float(usage.wall_seconds),
        generation=generation,
    )


def _execute_implementations(
    workspace: Path,
    manifest: dict[str, Any],
    proposals: dict[str, ProposalDraw],
    provider: PatchProvider,
    progress: Callable[[str], None] | None,
) -> dict[str, ImplementationDraw]:
    states = {state["state_id"]: state for state in manifest["states"]}
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    result_store = ArtifactStore(workspace / "result-artifacts")

    def execute(item: dict[str, Any]) -> ImplementationDraw:
        record = _draw_record_path(manifest, "implementations", item["draw_id"])
        path = result_store.records / record
        if path.is_file():
            saved = _load_json(path)
            _verify_checkpoint(saved, manifest, item)
            return _implementation_from_json(saved["draw"])
        draw = _generate_implementation(
            protocol_store,
            result_store,
            states[item["state_id"]],
            item,
            proposals[item["draw_id"]],
            provider,
        )
        body = jsonable(draw)
        result_store.write_record(record, {
            "manifest_digest": manifest["manifest_digest"],
            "draw_id": item["draw_id"],
            "condition_id": item["condition_id"],
            "draw": body,
            "draw_digest": digest_json(body),
        })
        return draw

    return _parallel_draws(manifest, manifest["proposal_schedule"], execute, progress, "implementation")


def _generate_implementation(
    protocol_store: ArtifactStore,
    result_store: ArtifactStore,
    state: dict[str, Any],
    item: dict[str, Any],
    proposal: ProposalDraw,
    provider: PatchProvider,
) -> ImplementationDraw:
    if not proposal.contract_compliant or proposal.mechanism is None or proposal.mechanism_digest is None:
        raise RuntimeError("GCF-V2 cannot implement a non-compliant mechanism object")
    question = protocol_store.get_bytes(state["task_files"]["question"]).decode("utf-8")
    base_source = protocol_store.get_bytes(state["base_source_digest"]).decode("utf-8")
    mechanism_json = json.dumps(proposal.mechanism, sort_keys=True, separators=(",", ":"))
    prompt = _implementation_prompt_template().format(
        question=question,
        base_source=base_source,
        mechanism_object=mechanism_json,
    )
    request = _request(
        provider,
        prompt,
        _implementation_prompt_template(),
        state,
        {**item, "mechanism_digest": proposal.mechanism_digest},
        IMPLEMENTATION_TOKEN_CEILING,
        "implementation",
    )
    started = time.monotonic()
    source = ""
    evaluation = {"score": 0.0, "valid": False, "probe_scores": [0.0] * 6, "failure": "NOT_RUN"}
    evaluable = False
    try:
        generated = provider.generate(request)
        payload = json.loads(generated.raw_response)
        if set(payload) != {"implementation_source"} or not isinstance(payload["implementation_source"], str):
            raise ValueError("implementation response does not match frozen schema")
        source = payload["implementation_source"]
        evaluation = _evaluate_descendant(protocol_store, state, source)
        evaluable = not generated.refused
        usage = generated.usage
        generation = _generation_success(request, generated, evaluable)
    except (GenerationProviderError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        usage = error.usage if isinstance(error, GenerationProviderError) and error.usage else ResourceUsage()
        generation = _generation_failure(request, error, usage, started)
    valid = bool(evaluation["valid"])
    behavior = tuple([float(value) for value in evaluation["probe_scores"]] + [float(valid)])
    return ImplementationDraw(
        state_id=state["state_id"],
        condition_id=item["condition_id"],
        draw_id=item["draw_id"],
        mechanism_digest=proposal.mechanism_digest,
        evaluable=evaluable,
        valid=valid,
        source_signature=tuple(_source_signature(source)),
        behavior_signature=behavior,
        utility=float(evaluation["score"]),
        token_cost=int(usage.tokens),
        wall_seconds=float(usage.wall_seconds),
        generation=generation,
        source_sha256=digest_bytes(source.encode("utf-8")),
        source_artifact_digest=(
            result_store.put_bytes(source.encode("utf-8"), media_type="text/x-python") if source else None
        ),
        evaluation=evaluation,
    )


def _analyze_proposals(manifest: dict[str, Any], draws: dict[str, ProposalDraw]) -> dict[str, Any]:
    states = []
    observed_states = {draw.state_id for draw in draws.values()}
    for state in manifest["states"]:
        if state["state_id"] not in observed_states:
            continue
        left = [draw for draw in draws.values() if draw.state_id == state["state_id"] and draw.condition_id == CONDITION_A]
        right = [draw for draw in draws.values() if draw.state_id == state["state_id"] and draw.condition_id == CONDITION_B]
        within = _within_envelope(left, right, lambda draw: draw.categorical_signature)
        between = _between_median(left, right, lambda draw: draw.categorical_signature)
        detectable = all(draw.contract_compliant for draw in left + right) and between > within
        states.append({
            "state_id": state["state_id"],
            "task_category": state["task_category"],
            "within_condition_envelope": within,
            "between_condition_median": between,
            "detectable": detectable,
            "contract_compliant_draws": sum(draw.contract_compliant for draw in left + right),
            "total_draws": len(left) + len(right),
        })
    return {"detectable_states": sum(row["detectable"] for row in states), "states": states}


def _analyze_implementations(manifest: dict[str, Any], draws: dict[str, ImplementationDraw]) -> dict[str, Any]:
    states = []
    for state in manifest["states"]:
        left = [draw for draw in draws.values() if draw.state_id == state["state_id"] and draw.condition_id == CONDITION_A]
        right = [draw for draw in draws.values() if draw.state_id == state["state_id"] and draw.condition_id == CONDITION_B]
        source_within = _within_envelope(left, right, lambda draw: draw.source_signature)
        source_between = _between_median(left, right, lambda draw: draw.source_signature)
        behavior_within = _within_envelope(left, right, lambda draw: draw.behavior_signature)
        behavior_between = _between_median(left, right, lambda draw: draw.behavior_signature)
        states.append({
            "state_id": state["state_id"],
            "task_category": state["task_category"],
            "source": {
                "within_condition_envelope": source_within,
                "between_condition_median": source_between,
                "detectable": source_between > source_within + SOURCE_MARGIN,
            },
            "behavior": {
                "within_condition_envelope": behavior_within,
                "between_condition_median": behavior_between,
                "detectable": behavior_between > behavior_within + BEHAVIOR_MARGIN,
            },
            "utility_record_only": {
                CONDITION_A: statistics.median(draw.utility for draw in left),
                CONDITION_B: statistics.median(draw.utility for draw in right),
            },
        })
    return {
        "source_detectable_states": sum(row["source"]["detectable"] for row in states),
        "behavior_detectable_states": sum(row["behavior"]["detectable"] for row in states),
        "states": states,
    }


def _within_envelope(left: list[Any], right: list[Any], signature: Callable[[Any], tuple[float, ...]]) -> float:
    distances = [
        math.dist(signature(first), signature(second))
        for group in (left, right)
        for first, second in itertools.combinations(group, 2)
    ]
    return max(distances, default=0.0)


def _between_median(left: list[Any], right: list[Any], signature: Callable[[Any], tuple[float, ...]]) -> float:
    distances = [math.dist(signature(first), signature(second)) for first in left for second in right]
    return statistics.median(distances) if distances else 0.0


def _parallel_draws(
    manifest: dict[str, Any],
    schedule: list[dict[str, Any]],
    execute: Callable[[dict[str, Any]], Any],
    progress: Callable[[str], None] | None,
    stage: str,
) -> dict[str, Any]:
    draws = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(manifest["environment"]["max_workers"])) as executor:
        future_map = {executor.submit(execute, item): item for item in schedule}
        for completed, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            draw = future.result()
            draws[draw.draw_id] = draw
            if progress:
                progress(f"GCF-V2 {stage} draw {completed}/{len(schedule)} complete")
    return draws


def _request(
    provider: PatchProvider,
    prompt: str,
    template: str,
    state: dict[str, Any],
    item: dict[str, Any],
    token_ceiling: int,
    stage: str,
) -> GenerationRequest:
    return GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider=provider.provider_name,
        model=provider.model,
        provider_settings_digest=getattr(provider, "settings_digest", ""),
        prompt_template_digest=digest_json({"stage": stage, "template": template}),
        context_digest=digest_json({"state": state["state_digest"], "stage": stage, "draw": item}),
        prompt=prompt,
        token_ceiling=token_ceiling,
    )


def _proposal_prompt_template() -> str:
    return (
        "Create a machine-enforceable Mechanism Object for the requested algorithmic intervention. "
        "The categorical control-flow fields must describe the mechanism itself; explanatory text cannot "
        "substitute for them. Preserve feasibility, the public API, and input immutability.\n\n"
        "TASK:\n{question}\n\nBASE algorithm.py:\n```python\n{base_source}```\n\n"
        "MECHANISM BRIEF:\n{mechanism_brief}\n\nReturn only the structured object required by the schema."
    )


def _implementation_prompt_template() -> str:
    return (
        "Implement the supplied immutable Mechanism Object. It is the only mechanism authority available to "
        "you. Materially realize its expected control flow and forbidden fallbacks while preserving its "
        "invariants. Return a complete algorithm.py with no markdown fences.\n\nTASK:\n{question}\n\n"
        "BASE algorithm.py:\n```python\n{base_source}```\n\nCANONICAL MECHANISM OBJECT:\n{mechanism_object}"
    )


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


def _validate_provider_pair(proposal: PatchProvider, implementation: PatchProvider) -> None:
    if _provider_version(proposal) in {"", "unknown"} or _provider_version(implementation) in {"", "unknown"}:
        raise RuntimeError("GCF-V2 requires reportable provider versions")
    if getattr(proposal, "output_schema", None) != MECHANISM_OBJECT_SCHEMA:
        raise RuntimeError("GCF-V2 proposal provider must use the frozen Mechanism Object schema")
    if getattr(implementation, "output_schema", None) != IMPLEMENTATION_SCHEMA:
        raise RuntimeError("GCF-V2 implementation provider must use the frozen implementation schema")
    for field in ("provider_name", "model", "provider_version"):
        if getattr(proposal, field, None) != getattr(implementation, field, None):
            raise RuntimeError(f"GCF-V2 provider pair differs at {field}")


def _load_manifest(
    workspace: Path,
    expected_digest: str,
    proposal_provider: PatchProvider,
    implementation_provider: PatchProvider,
) -> dict[str, Any]:
    _validate_provider_pair(proposal_provider, implementation_provider)
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, expected_digest)
    if manifest.get("status") != "SEALED_PRE_MODEL_CALL":
        raise RuntimeError("GCF-V2 manifest was not sealed before model calls")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("GCF-V2 implementation binding drift")
    actual = {
        "proposal": _provider_binding(proposal_provider),
        "implementation": _provider_binding(implementation_provider),
    }
    if actual != manifest["providers"]:
        raise RuntimeError("GCF-V2 provider/model/settings differ from the sealed manifest")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("GCF-V2 repository commit differs from the sealed manifest")
    return manifest


def _draw_record_path(manifest: dict[str, Any], stage: str, draw_id: str) -> str:
    digest = digest_json({"manifest": manifest["manifest_digest"], "stage": stage, "draw": draw_id})
    return f"draws/{stage}/{digest}.json"


def _verify_checkpoint(saved: dict[str, Any], manifest: dict[str, Any], item: dict[str, Any]) -> None:
    if (
        saved.get("manifest_digest") != manifest["manifest_digest"]
        or saved.get("draw_id") != item["draw_id"]
        or saved.get("condition_id") != item["condition_id"]
        or saved.get("draw_digest") != digest_json(saved.get("draw"))
    ):
        raise RuntimeError("GCF-V2 draw checkpoint binding mismatch")


def _load_proposal_draws(workspace: Path, manifest: dict[str, Any]) -> dict[str, ProposalDraw]:
    root = workspace / "result-artifacts" / "records"
    result = {}
    for item in manifest["proposal_schedule"]:
        saved = _load_json(root / _draw_record_path(manifest, "proposals", item["draw_id"]))
        _verify_checkpoint(saved, manifest, item)
        result[item["draw_id"]] = _proposal_from_json(saved["draw"])
    return result


def _draw_bindings(
    workspace: Path,
    manifest: dict[str, Any],
    stage: str,
    schedule: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    root = workspace / "result-artifacts" / "records"
    result = []
    for item in schedule or manifest["proposal_schedule"]:
        path = root / _draw_record_path(manifest, stage, item["draw_id"])
        result.append({"draw_id": item["draw_id"], "path": str(path), "sha256": digest_bytes(path.read_bytes())})
    return result


def _proposal_from_json(value: dict[str, Any]) -> ProposalDraw:
    return ProposalDraw(**{**value, "categorical_signature": tuple(value["categorical_signature"])})


def _implementation_from_json(value: dict[str, Any]) -> ImplementationDraw:
    return ImplementationDraw(
        **{
            **value,
            "source_signature": tuple(value["source_signature"]),
            "behavior_signature": tuple(value["behavior_signature"]),
        }
    )


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
        raw = error.raw_response or ""
        transport = error.transport_log or ""
        record.update(
            {
                "raw_response_sha256": digest_bytes(raw.encode("utf-8")),
                "transport_log_sha256": digest_bytes(transport.encode("utf-8")),
                "transport_log_excerpt": transport[-2_000:],
            }
        )
    return record


def _usage(draws: Iterable[Any]) -> dict[str, Any]:
    values = list(draws)
    return {
        "model_calls": len(values),
        "tokens": sum(draw.token_cost for draw in values),
        "wall_seconds_sum": sum(draw.wall_seconds for draw in values),
    }


def _combine_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {key: first[key] + second[key] for key in ("model_calls", "tokens", "wall_seconds_sum")}


def _load_json(path: Path, expected_digest: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required GCF-V2 artifact missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if expected_digest is not None:
        payload = {key: item for key, item in value.items() if key != "manifest_digest"}
        if value.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
            raise RuntimeError("sealed GCF-V2 manifest digest mismatch")
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
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    status = subprocess.run(
        ("git", "status", "--short"),
        cwd=root,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if head.returncode != 0 or status.returncode != 0:
        raise RuntimeError("GCF-V2 requires a readable Git repository")
    return {"head_commit": head.stdout.strip(), "worktree_clean_at_observation": not bool(status.stdout.strip())}


def _implementation_bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("si2_tasks.py").resolve(),
        Path(__file__).with_name("parent_intervention_real.py").resolve(),
        Path(__file__).with_name("mechanism_brief_real.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
