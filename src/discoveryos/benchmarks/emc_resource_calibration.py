from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.executable_mechanism_contract import (
    _implementation_prompt_template,
    _provider_binding,
    _repository_snapshot,
    _validate_provider,
)
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.provider_invocations import (
    DurableProviderInvoker,
    InvocationStateUnknown,
    assert_no_orphaned_invocations,
)
from discoveryos.util import digest_bytes, digest_json


PROTOCOL_ID = "EMC_RESOURCE_CALIBRATION_R1"
MANIFEST_RECORD = "emc-resource-calibration-r1-manifest.json"
RESULT_RECORD = "emc-resource-calibration-r1-result.json"
HISTORICAL_MAX_TOKENS = 61_681
HEADROOM_MULTIPLIER = 1.25
ROUNDING_QUANTUM = 1_000
MAX_SCIENTIFIC_CEILING = 100_000


def seal_emc_resource_calibration(workspace: Path, *, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    workspace = workspace.resolve()
    fixtures = _fixtures()
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_PROVIDER_CALL",
        "scope": "NON_SCIENTIFIC_RESOURCE_CALIBRATION_ONLY",
        "provider": _provider_binding(provider),
        "provider_calls_before_seal": 0,
        "fixtures": fixtures,
        "ceiling_rule": {
            "historical_max_tokens": HISTORICAL_MAX_TOKENS,
            "observed_statistic": "maximum exact tokens over all four fixtures",
            "headroom_multiplier": HEADROOM_MULTIPLIER,
            "rounding_quantum": ROUNDING_QUANTUM,
            "maximum_scientific_ceiling": MAX_SCIENTIFIC_CEILING,
            "formula": "ceil(max(historical_max, observed_max) * 1.25 / 1000) * 1000",
        },
        "scientific_outputs_inspected": False,
        "fresh_scientific_states_consumed": 0,
        "repository": _repository_snapshot(),
        "implementation_bindings": _bindings(),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_sha256": digest_bytes(path.read_bytes()),
        "planned_provider_calls": len(fixtures),
    }


def run_emc_resource_calibration(
    workspace: Path,
    *,
    manifest_digest: str,
    provider: PatchProvider,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest = _load_manifest(workspace, manifest_digest, provider)
    result_path = workspace / "result-artifacts" / "records" / RESULT_RECORD
    if result_path.is_file():
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        if saved.get("manifest_digest") != manifest_digest:
            raise RuntimeError("EMC resource calibration result binding mismatch")
        return {**saved, "record_path": str(result_path), "record_sha256": digest_bytes(result_path.read_bytes())}
    assert_no_orphaned_invocations(workspace / "result-artifacts")
    draws = []
    for index, fixture in enumerate(manifest["fixtures"], start=1):
        request = _request(fixture, provider)
        try:
            invocation = DurableProviderInvoker(
                workspace / "result-artifacts",
                namespace=f"{PROTOCOL_ID}:{fixture['fixture_id']}",
            ).invoke(provider, request)
            generated = invocation.generation
            value = json.loads(generated.raw_response)
            schema_valid = set(value) == {"implementation_source"} and isinstance(value["implementation_source"], str)
            draws.append({
                "fixture_id": fixture["fixture_id"],
                "status": "EVALUABLE" if schema_valid and not generated.refused else "NOT_EVALUABLE",
                "schema_valid": schema_valid,
                "refused": generated.refused,
                "tokens": int(generated.usage.tokens),
                "wall_seconds": float(generated.usage.wall_seconds),
                "provider_request_id": generated.provider_request_id,
                "provider_version": generated.provider_version,
                "recovered": invocation.recovered,
                "raw_response_sha256": digest_bytes(generated.raw_response.encode("utf-8")),
            })
        except (GenerationProviderError, InvocationStateUnknown, json.JSONDecodeError, TypeError, ValueError) as error:
            usage = error.usage if isinstance(error, GenerationProviderError) and error.usage else None
            draws.append({
                "fixture_id": fixture["fixture_id"],
                "status": "NOT_EVALUABLE",
                "failure": str(error),
                "tokens": int(usage.tokens) if usage else None,
                "wall_seconds": float(usage.wall_seconds) if usage else None,
            })
        if progress:
            progress(f"EMC resource calibration {index}/{len(manifest['fixtures'])} complete")
    exact = [item for item in draws if item["status"] == "EVALUABLE" and isinstance(item.get("tokens"), int)]
    observed_max = max((item["tokens"] for item in exact), default=0)
    derived = math.ceil(max(HISTORICAL_MAX_TOKENS, observed_max) * HEADROOM_MULTIPLIER / ROUNDING_QUANTUM) * ROUNDING_QUANTUM
    passed = len(exact) == len(draws) and derived <= MAX_SCIENTIFIC_CEILING
    record = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": "EMC_RESOURCE_CALIBRATION_PASSED" if passed else "EMC_RESOURCE_CALIBRATION_NOT_EVALUABLE",
        "passed": passed,
        "draws": draws,
        "distribution": {
            "count": len(exact),
            "tokens": [item["tokens"] for item in exact],
            "wall_seconds": [item["wall_seconds"] for item in exact],
            "observed_max_tokens": observed_max,
        },
        "derived_scientific_per_call_token_ceiling": derived if passed else None,
        "ceiling_rule": manifest["ceiling_rule"],
        "provider_calls": len(draws),
        "fresh_scientific_states_consumed": 0,
        "scientific_evidence": False,
    }
    path = ArtifactStore(workspace / "result-artifacts").write_record(RESULT_RECORD, record)
    return {**record, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def load_resource_authority(workspace: Path, record_sha256: str, provider: PatchProvider) -> dict[str, Any]:
    path = workspace.resolve() / "result-artifacts" / "records" / RESULT_RECORD
    if not path.is_file() or digest_bytes(path.read_bytes()) != record_sha256:
        raise RuntimeError("EMC resource calibration record binding mismatch")
    record = json.loads(path.read_text(encoding="utf-8"))
    manifest = _load_manifest(workspace.resolve(), record["manifest_digest"], provider)
    if not record.get("passed") or record.get("status") != "EMC_RESOURCE_CALIBRATION_PASSED":
        raise RuntimeError("EMC resource calibration did not pass")
    return {"record": record, "manifest": manifest, "record_path": path}


def _request(fixture: dict[str, Any], provider: PatchProvider) -> GenerationRequest:
    prompt = _implementation_prompt_template().format(
        question=fixture["question"],
        base_source=fixture["base_source"],
        mechanism_object=json.dumps(fixture["mechanism_object"], sort_keys=True, separators=(",", ":")),
        executable_contract=json.dumps(fixture["contract"], sort_keys=True, separators=(",", ":")),
    )
    return GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider=provider.provider_name,
        model=provider.model,
        provider_settings_digest=getattr(provider, "settings_digest", ""),
        prompt_template_digest=digest_json({"protocol": PROTOCOL_ID, "template": _implementation_prompt_template()}),
        context_digest=digest_json(fixture),
        prompt=prompt,
        token_ceiling=MAX_SCIENTIFIC_CEILING,
    )


def _fixtures() -> list[dict[str, Any]]:
    result = []
    sizes = (8, 24, 48, 72)
    for index, size in enumerate(sizes, start=1):
        entrypoint = f"solve_fixture_{index}"
        helper = f"emc_resource_path_{index}"
        base_lines = [f"def {entrypoint}(values):", "    return list(values)"] + [f"# representative line {i}" for i in range(size)]
        mechanism = {
            "mechanism_family": "resource_calibration_only",
            "required_intervention": f"route the entrypoint through {helper}",
            "forbidden_fallbacks": ["inherited_solver"],
            "invariants": ["api_preserved", "standard_library_only"],
        }
        contract = {
            "contract_version": "EMC_RESOURCE_FIXTURE_V1",
            "entrypoint": entrypoint,
            "required_functions": [helper],
            "forbidden_functions": ["inherited_solver"],
            "required_call_edges": [[entrypoint, helper]],
            "runtime_counters": {helper: {"minimum": 1, "maximum": None}},
            "invariants": mechanism["invariants"],
        }
        result.append({
            "fixture_id": f"resource-fixture-{index}",
            "question": "Return the same values through the required representative execution path.",
            "base_source": "\n".join(base_lines) + "\n",
            "mechanism_object": mechanism,
            "contract": {**contract, "contract_digest": digest_json(contract)},
        })
    return result


def _load_manifest(workspace: Path, expected_digest: str, provider: PatchProvider) -> dict[str, Any]:
    _validate_provider(provider)
    path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    if not path.is_file():
        raise RuntimeError("EMC resource calibration manifest missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("EMC resource calibration manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_PROVIDER_CALL":
        raise RuntimeError("EMC resource calibration was not sealed before calls")
    if manifest.get("provider") != _provider_binding(provider):
        raise RuntimeError("EMC resource calibration provider drift")
    if _repository_snapshot()["head_commit"] != manifest["repository"]["head_commit"]:
        raise RuntimeError("EMC resource calibration repository drift")
    for binding in manifest["implementation_bindings"]:
        path = Path(binding["path"])
        if not path.is_file() or digest_bytes(path.read_bytes()) != binding["sha256"]:
            raise RuntimeError("EMC resource calibration implementation binding drift")
    return manifest


def _bindings() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("executable_mechanism_contract.py").resolve(),
        (Path(__file__).resolve().parents[1] / "runtime" / "provider_invocations.py").resolve(),
    )
    return [{"path": str(path), "sha256": digest_bytes(path.read_bytes())} for path in paths]
