from __future__ import annotations

import concurrent.futures
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.cmi_probe_calibration import _behavior_signature, _calibrate_state, _freeze_state
from discoveryos.benchmarks.executable_mechanism_contract import (
    IMPLEMENTATION_SCHEMA,
    _evaluate_descendant,
    _load_json,
    _provider_binding,
    _repository_snapshot,
    _validate_provider,
)
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task
from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest
from discoveryos.mechanism_intelligence import (
    BottleneckHypothesis,
    Comparison,
    DiagnosticProbeResult,
    DiagnosticProbeSpec,
    FailurePhenotypeReceipt,
    MechanismDiagnosisSession,
    PhenotypeMetrics,
    ProbeValidity,
    ThresholdRule,
)
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.provider_invocations import DurableProviderInvoker, assert_no_orphaned_invocations
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CMI_R2_BOUNDED_REAL_DIAGNOSIS"
MANIFEST_RECORD = "cmi-r2-real-diagnosis-manifest.json"
CONTROLS_RECORD = "cmi-r2-real-diagnosis-controls.json"
REPORT_RECORD = "cmi-r2-real-diagnosis-report.json"
REPLICATES_PER_STATE = 3


def seal_cmi_real_diagnosis(
    workspace: Path,
    *,
    cmi_r1_workspace: Path,
    cmi_r1_report_sha256: str,
    resource_workspace: Path,
    resource_record_sha256: str,
    provider: PatchProvider,
    max_workers: int = 2,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("CMI-R2 workspace must be create-once and empty")
    _validate_provider(provider)
    repository = _repository_snapshot()
    if not repository["worktree_clean_at_observation"]:
        raise RuntimeError("CMI-R2 must be sealed from a clean worktree")
    r1_path = cmi_r1_workspace.resolve() / "result-artifacts" / "records" / "cmi-r1-probe-calibration-report.json"
    if not r1_path.is_file() or digest_bytes(r1_path.read_bytes()) != cmi_r1_report_sha256:
        raise RuntimeError("CMI-R1 probe authority hash mismatch")
    r1 = _load_json(r1_path)
    if not r1.get("passed") or not r1.get("bounded_real_diagnosis_preregistration_authorized"):
        raise RuntimeError("CMI-R1 did not authorize bounded real diagnosis preregistration")
    resource_path = resource_workspace.resolve() / "result-artifacts" / "records" / "emc-resource-calibration-r1-result.json"
    if not resource_path.is_file() or digest_bytes(resource_path.read_bytes()) != resource_record_sha256:
        raise RuntimeError("CMI-R2 resource authority hash mismatch")
    resource = _load_json(resource_path)
    resource_manifest_path = resource_workspace.resolve() / "protocol-artifacts" / "records" / "emc-resource-calibration-r1-manifest.json"
    resource_manifest = _load_json(resource_manifest_path, resource.get("manifest_digest"))
    ceiling = int(resource.get("derived_scientific_per_call_token_ceiling", 0))
    if (
        resource.get("status") != "EMC_RESOURCE_CALIBRATION_PASSED"
        or resource_manifest.get("provider") != _provider_binding(provider)
        or not 0 < ceiling <= 100_000
    ):
        raise RuntimeError("CMI-R2 resource authority is invalid")

    tasks = (
        _assignment_task("cmi_r2_assignment_diagnosis_beta", (25117, 25147, 25171, 25189, 25219, 25229)),
        _coverage_task("cmi_r2_coverage_diagnosis_beta", (26107, 26141, 26161, 26183, 26209, 26237)),
    )
    store = ArtifactStore(workspace / "protocol-artifacts")
    states = [_freeze_state(store, task, index) for index, task in enumerate(tasks)]
    hypotheses, probes = _hypotheses_and_probes()
    schedule = [
        {"state_id": state["state_id"], "draw_id": f"{state['state_id']}:direct:{replicate}", "replicate": replicate}
        for state in states
        for replicate in range(REPLICATES_PER_STATE)
    ]
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_MODEL_CALL",
        "scope": "TWO_STATE_DEVELOPMENT_BOTTLENECK_DIAGNOSIS",
        "claim_ceiling": "TWO_STATE_DEVELOPMENT_DIAGNOSIS_ONLY",
        "repository": repository,
        "provider": _provider_binding(provider),
        "resource_authority": {"path": str(resource_path), "record_sha256": resource_record_sha256, "manifest_digest": resource["manifest_digest"], "per_call_token_ceiling": ceiling},
        "cmi_r1_authority": {"path": str(r1_path), "report_sha256": cmi_r1_report_sha256},
        "states": states,
        "hypotheses": [jsonable(item) for item in hypotheses],
        "probes": [jsonable(item) for item in probes],
        "schedule": schedule,
        "max_workers": max(1, min(2, max_workers)),
        "total_call_ceiling": len(schedule),
        "model_calls_before_seal": 0,
        "fresh_search_value_tasks_consumed": 0,
        "fresh_search_value_budget_authorized": False,
        "implementation_bindings": _bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = store.write_record(MANIFEST_RECORD, manifest)
    return {"status": manifest["status"], "manifest_digest": manifest["manifest_digest"], "manifest_path": str(path), "total_call_ceiling": len(schedule)}


def run_cmi_real_controls(workspace: Path, *, manifest_digest: str, provider: PatchProvider) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, provider)
    store = ArtifactStore(workspace / "protocol-artifacts")
    thresholds = {
        "evaluator_ranked_control_recovery_minimum": 6 / 7,
        "same_source_functional_distance_maximum": 0.0,
        "baseline_reference_functional_distance_minimum": 0.10,
    }
    states = [_calibrate_state(store, state, thresholds) for state in manifest["states"]]
    passed = all(item["passed"] for item in states)
    record = {"protocol_id": PROTOCOL_ID, "manifest_digest": manifest_digest, "status": "CMI_R2_CONTROLS_PASSED" if passed else "CMI_R2_CONTROLS_FAILED", "passed": passed, "states": states, "model_calls": 0}
    path = ArtifactStore(workspace / "result-artifacts").write_record(CONTROLS_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def run_cmi_real_diagnosis(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, provider)
    controls_path = workspace / "result-artifacts" / "records" / CONTROLS_RECORD
    controls = _load_json(controls_path)
    if controls.get("manifest_digest") != manifest_digest or not controls.get("passed"):
        raise RuntimeError("CMI-R2 controls did not authorize provider calls")
    assert_no_orphaned_invocations(workspace / "result-artifacts")
    states = {item["state_id"]: item for item in manifest["states"]}
    result_store = ArtifactStore(workspace / "result-artifacts")

    def execute(item: dict[str, Any]) -> dict[str, Any]:
        name = f"draws/{digest_json({'manifest': manifest_digest, 'draw': item['draw_id']})}.json"
        path = result_store.records / name
        if path.is_file():
            saved = _load_json(path)
            if saved.get("manifest_digest") != manifest_digest or saved.get("draw_id") != item["draw_id"]:
                raise RuntimeError("CMI-R2 draw checkpoint binding mismatch")
            return saved["draw"]
        draw = _generate_draw(workspace, manifest, states[item["state_id"]], item, provider)
        result_store.write_record(name, {"manifest_digest": manifest_digest, "draw_id": item["draw_id"], "draw": draw, "draw_digest": digest_json(draw)})
        return draw

    draws = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(manifest["max_workers"])) as executor:
        futures = [executor.submit(execute, item) for item in manifest["schedule"]]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            draws.append(future.result())
            if progress:
                progress(f"CMI-R2 draw {index}/{len(futures)} complete")
    report = _diagnose(manifest, controls, draws)
    path = result_store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _generate_draw(workspace: Path, manifest: dict[str, Any], state: dict[str, Any], item: dict[str, Any], provider: PatchProvider) -> dict[str, Any]:
    protocol_store = ArtifactStore(workspace / "protocol-artifacts")
    result_store = ArtifactStore(workspace / "result-artifacts")
    question = protocol_store.get_bytes(state["task_files"]["question"]).decode("utf-8")
    base_entry = next(value for value in state["ranked_sources"] if value["label"] == "baseline")
    base = protocol_store.get_bytes(base_entry["digest"]).decode("utf-8")
    prompt = "Produce one independent strong direct solution. Return a complete algorithm.py, preserve the public API and inputs, use only the Python standard library, and do not describe the answer.\n\nTASK:\n" + question + "\n\nBASE algorithm.py:\n```python\n" + base + "```"
    request = GenerationRequest.create(kind=GenerationKind.PROPOSAL, root_generation_id=None, provider=provider.provider_name, model=provider.model, provider_settings_digest=getattr(provider, "settings_digest", ""), prompt_template_digest=digest_json({"stage": "cmi_r2_direct_v1"}), context_digest=digest_json({"state": state["state_digest"], "draw": item}), prompt=prompt, token_ceiling=int(manifest["resource_authority"]["per_call_token_ceiling"]))
    started = time.monotonic()
    usage = ResourceUsage()
    source = ""
    generation: dict[str, Any]
    try:
        invocation = DurableProviderInvoker(workspace / "result-artifacts", namespace=f"{PROTOCOL_ID}:{item['draw_id']}").invoke(provider, request)
        generated = invocation.generation
        payload = json.loads(generated.raw_response)
        if set(payload) != {"implementation_source"} or not isinstance(payload["implementation_source"], str):
            raise ValueError("CMI-R2 response schema mismatch")
        source = payload["implementation_source"]
        usage = generated.usage
        generation = {"status": "SUCCEEDED" if not generated.refused else "REFUSED", "provider_request_id": generated.provider_request_id, "provider_version": generated.provider_version, "recovered": invocation.recovered, "usage": jsonable(usage)}
    except (GenerationProviderError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, GenerationProviderError) and error.usage:
            usage = error.usage
        generation = {"status": "PROVIDER_OR_SCHEMA_FAILURE", "failure_signature": getattr(error, "signature", type(error).__name__), "usage": jsonable(usage), "wall_seconds": time.monotonic() - started}
    evaluation = _evaluate_descendant(protocol_store, state, source) if source else {"score": 0.0, "valid": False, "failure": "NOT_RUN", "source_sha256": digest_bytes(b"")}
    signature = _behavior_signature(protocol_store, state, source) if source and evaluation["valid"] else []
    return {"state_id": state["state_id"], "draw_id": item["draw_id"], "evaluable": generation["status"] == "SUCCEEDED" and int(usage.tokens) <= int(manifest["resource_authority"]["per_call_token_ceiling"]), "valid": bool(evaluation["valid"]), "score": float(evaluation["score"]), "behavior_signature": signature, "source_sha256": evaluation["source_sha256"], "source_artifact_digest": result_store.put_bytes(source.encode("utf-8"), media_type="text/x-python") if source else None, "tokens": int(usage.tokens), "generation": generation}


def _diagnose(manifest: dict[str, Any], controls: dict[str, Any], draws: list[dict[str, Any]]) -> dict[str, Any]:
    if len(draws) != int(manifest["total_call_ceiling"]) or not all(item["evaluable"] for item in draws):
        return {
            "protocol_id": PROTOCOL_ID,
            "manifest_digest": manifest["manifest_digest"],
            "status": "CMI_R2_NOT_EVALUABLE_RESOURCE_OR_PROVIDER",
            "draws": draws,
            "usage": {"model_calls": len(draws), "tokens": sum(item["tokens"] for item in draws)},
            "real_bottleneck_established": False,
            "development_mechanism_brief_authorized": False,
            "new_operator_authorized": False,
            "fresh_search_value_budget_authorized": False,
        }
    hypotheses, probes = _hypotheses_and_probes()
    valid_rate = sum(item["valid"] for item in draws) / len(draws)
    recovery = statistics.fmean(item["ranked_control_recovery_rate"] for item in controls["states"])
    distances = []
    for state in manifest["states"]:
        selected = [item for item in draws if item["state_id"] == state["state_id"] and item["valid"]]
        for left in range(len(selected)):
            for right in range(left + 1, len(selected)):
                a, b = selected[left]["behavior_signature"], selected[right]["behavior_signature"]
                if a and len(a) == len(b):
                    distances.append(sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a))
    diversity_evaluable = len(distances) == 2 * 3
    diversity = statistics.median(distances) if distances else 0.0
    baseline = {item["state_id"]: item["baseline_score"] for item in controls["states"]}
    resolution = {item["state_id"]: float(item["score_resolution"]) for item in manifest["states"]}
    replacement = sum(item["valid"] and item["score"] > baseline[item["state_id"]] + resolution[item["state_id"]] for item in draws) / len(draws)
    phenotype = FailurePhenotypeReceipt(episode_id="cmi-r2-two-state-direct-generation", source_digest=digest_json([item["source_sha256"] for item in draws]), contract_digest=manifest["manifest_digest"], observed_failure="bounded direct generations require bottleneck attribution before operator selection", metrics=PhenotypeMetrics(headroom=statistics.fmean(item["reference_headroom"] for item in controls["states"]), validity_rate=valid_rate, replacement_rate=replacement, behavioral_diversity=diversity, structural_basin_diversity=diversity, parent_entropy=0.0, lineage_improvement=max((item["score"] - baseline[item["state_id"]] for item in draws if item["valid"]), default=0.0), budget_concentration=max((item["tokens"] for item in draws), default=0) / max(1, sum(item["tokens"] for item in draws)), evaluator_sensitivity=recovery))
    results = (
        DiagnosticProbeResult(probes[0].probe_id, probes[0].spec_digest, phenotype.receipt_id, recovery, ProbeValidity.VALID, "bound R1-style ranked controls"),
        DiagnosticProbeResult(probes[1].probe_id, probes[1].spec_digest, phenotype.receipt_id, valid_rate, ProbeValidity.VALID, "six frozen direct draws", model_calls=6),
        DiagnosticProbeResult(probes[2].probe_id, probes[2].spec_digest, phenotype.receipt_id, diversity if diversity_evaluable else None, ProbeValidity.VALID if diversity_evaluable else ProbeValidity.NOT_EVALUABLE, "within-state pairwise functional distance", model_calls=6),
    )
    session = MechanismDiagnosisSession(phenotype); session.freeze_hypotheses(hypotheses); session.freeze_probes(probes); session.diagnose(results); diagnosis = session.finalize()
    return {"protocol_id": PROTOCOL_ID, "manifest_digest": manifest["manifest_digest"], "status": "CMI_R2_REAL_DIAGNOSIS_COMPLETE", "phenotype": jsonable(phenotype), "probe_results": [jsonable(item) for item in results], "diagnosis": jsonable(diagnosis), "draws": draws, "usage": {"model_calls": len(draws), "tokens": sum(item["tokens"] for item in draws)}, "real_bottleneck_established": diagnosis.mechanism_brief_hypothesis_id is not None, "development_mechanism_brief_authorized": diagnosis.mechanism_brief_hypothesis_id is not None, "new_operator_authorized": False, "fresh_search_value_budget_authorized": False}


def _hypotheses_and_probes() -> tuple[tuple[BottleneckHypothesis, ...], tuple[DiagnosticProbeSpec, ...]]:
    hypotheses = (
        BottleneckHypothesis("H3_EVALUATOR_INSENSITIVITY", "evaluator cannot distinguish value-bearing changes", "evaluator sensitivity", ("ranked controls exist",), ("low recovery",), ("at least 6/7 recovered",), ("P3_RANKED_CONTROL_RECOVERY",)),
        BottleneckHypothesis("H4_IMPLEMENTATION_BOTTLENECK", "generation failures prevent evaluation", "evaluation eligibility", ("complete-source schema is executable",), ("low valid rate",), ("at least 5/6 valid",), ("P4_DIRECT_VALID_RATE",)),
        BottleneckHypothesis("H5_STRUCTURAL_BASIN_LOCK", "valid generations remain in one functional basin", "functional output diversity", ("functional probe is sensitive",), ("low within-state distance",), ("large within-state distance",), ("P5_FUNCTIONAL_DIVERSITY",)),
    )
    probes = (
        DiagnosticProbeSpec("P3_RANKED_CONTROL_RECOVERY", hypotheses[0].hypothesis_id, "ranked recovery", ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.5), ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 6 / 7)),
        DiagnosticProbeSpec("P4_DIRECT_VALID_RATE", hypotheses[1].hypothesis_id, "valid source rate", ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.5), ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 5 / 6), max_model_calls=6),
        DiagnosticProbeSpec("P5_FUNCTIONAL_DIVERSITY", hypotheses[2].hypothesis_id, "median pairwise functional distance", ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.10), ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 0.30), max_model_calls=6),
    )
    return hypotheses, probes


def _load_manifest(workspace: Path, digest: str, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    manifest = _load_json(workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD, digest)
    if manifest.get("provider") != _provider_binding(provider) or manifest.get("status") != "SEALED_PRE_MODEL_CALL":
        raise RuntimeError("CMI-R2 provider or manifest drift")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("CMI-R2 repository drift")
    for item in manifest["implementation_bindings"]:
        path = Path(item["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != item["sha256"]:
            raise RuntimeError("CMI-R2 implementation binding drift")
    return manifest


def _bindings() -> list[dict[str, str]]:
    paths = (Path(__file__).resolve(), Path(__file__).with_name("cmi_probe_calibration.py").resolve(), (Path(__file__).resolve().parents[1] / "mechanism_intelligence.py").resolve(), (Path(__file__).resolve().parents[1] / "runtime" / "provider_invocations.py").resolve())
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
