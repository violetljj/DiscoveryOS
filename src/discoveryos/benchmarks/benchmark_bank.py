from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from discoveryos.benchmarks.algotune_dev import (
    ADAPTER_ID as ALGOTUNE_DEV_ADAPTER_ID,
    EVALUATOR_REGIME as ALGOTUNE_DEV_EVALUATOR_REGIME,
    UPSTREAM_BINDINGS as ALGOTUNE_DEV_UPSTREAM_BINDINGS,
    UPSTREAM_REVISION as ALGOTUNE_DEV_UPSTREAM_REVISION,
    materialize_algotune_dev,
)
from discoveryos.benchmarks.algotune_r2_dev import (
    ADAPTER_ID as ALGOTUNE_R2_DEV_ADAPTER_ID,
    EVALUATOR_REGIME as ALGOTUNE_R2_DEV_EVALUATOR_REGIME,
    UPSTREAM_BINDINGS as ALGOTUNE_R2_DEV_UPSTREAM_BINDINGS,
    materialize_r2_dev,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import normalized_source
from discoveryos.benchmarks.si2_tasks import si2_confirmation_tasks, si2_discovery_tasks
from discoveryos.util import digest_bytes, digest_json


BANK_SCHEMA_VERSION = 1
EXPECTED_TIER_COUNTS = {"R0": 8, "R1": 8, "R2": 10, "R3": 6, "R4": 5, "R5": 10}
PINNED_REVISION = re.compile(r"^[0-9a-f]{40}$")


class ShardRole(str, Enum):
    DEV = "DEV"
    SHADOW = "SHADOW"
    SEALED = "SEALED"


class ClaimPurpose(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    PERIODIC_REGRESSION = "PERIODIC_REGRESSION"
    FRESH_ADMISSION = "FRESH_ADMISSION"
    BLIND_CONFIRMATION = "BLIND_CONFIRMATION"


class IntegrationStatus(str, Enum):
    DEVELOPMENT_READY = "DEVELOPMENT_READY"
    CATALOGUED = "CATALOGUED"
    ADMITTED = "ADMITTED"


@dataclass(frozen=True, slots=True)
class BenchmarkResolution:
    family_id: str
    instance_id: str
    initial_program_path: str
    public_tests_path: str
    evaluator_path: str
    evaluator_digest: str
    instance_digest: str
    claim_ceiling: str
    adapter_id: str
    source_revision: str
    evaluator_regime: str
    task_contract_path: str | None = None


class BenchmarkAdapter(Protocol):
    adapter_id: str

    def materialize(self, family: dict[str, Any], instance_id: str, output_dir: Path) -> BenchmarkResolution:
        ...


def load_benchmark_bank(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    validate_benchmark_bank(registry)
    return registry


def validate_benchmark_bank(registry: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if registry.get("schema_version") != BANK_SCHEMA_VERSION:
        failures.append("SCHEMA_VERSION_MISMATCH")
    if registry.get("bank_id") != "DISCOVERYOS_BENCHMARK_BANK_V1":
        failures.append("BANK_ID_MISMATCH")

    sources = registry.get("sources")
    families = registry.get("families")
    if not isinstance(sources, dict) or not sources:
        failures.append("SOURCES_REQUIRED")
        sources = {}
    if not isinstance(families, list):
        failures.append("FAMILIES_REQUIRED")
        families = []

    for source_id, source in sources.items():
        if source_id == "discoveryos":
            continue
        if not PINNED_REVISION.fullmatch(str(source.get("revision", ""))):
            failures.append(f"SOURCE_NOT_COMMIT_PINNED:{source_id}")
        if not source.get("repository_url") or not source.get("license"):
            failures.append(f"SOURCE_PROVENANCE_INCOMPLETE:{source_id}")

    family_ids: set[str] = set()
    upstream_keys: set[tuple[str, str]] = set()
    tier_counts = {tier: 0 for tier in EXPECTED_TIER_COUNTS}
    development_ready = 0
    for family in families:
        family_id = family.get("family_id")
        if not isinstance(family_id, str) or not family_id or family_id in family_ids:
            failures.append(f"FAMILY_ID_INVALID_OR_DUPLICATE:{family_id}")
            continue
        family_ids.add(family_id)
        tier = family.get("difficulty_tier")
        if tier not in tier_counts:
            failures.append(f"DIFFICULTY_TIER_INVALID:{family_id}")
        else:
            tier_counts[tier] += 1
        source_id = family.get("source_id")
        if source_id not in sources:
            failures.append(f"SOURCE_UNKNOWN:{family_id}")
        upstream_task = family.get("upstream_task")
        upstream_key = (str(source_id), str(upstream_task))
        if upstream_key in upstream_keys:
            failures.append(f"UPSTREAM_TASK_DUPLICATED:{family_id}")
        upstream_keys.add(upstream_key)
        try:
            status = IntegrationStatus(family.get("integration_status"))
        except ValueError:
            failures.append(f"INTEGRATION_STATUS_INVALID:{family_id}")
            continue
        if source_id == "ale_bench":
            source = sources.get("ale_bench") or {}
            if not PINNED_REVISION.fullmatch(str(source.get("dataset_revision", ""))):
                failures.append(f"ALE_DATASET_NOT_COMMIT_PINNED:{family_id}")
            if source.get("dataset_license") != "CC-BY-ND-4.0":
                failures.append(f"ALE_DATASET_LICENSE_UNBOUND:{family_id}")
            if source.get("public_private_packaging") != "SAME_PROBLEM_ZIP":
                failures.append(f"ALE_PUBLIC_PRIVATE_PACKAGING_UNBOUND:{family_id}")
            audit = family.get("catalog_audit") or {}
            if not re.fullmatch(r"[0-9a-f]{64}", str(audit.get("dataset_lfs_sha256", ""))):
                failures.append(f"ALE_DATASET_LFS_DIGEST_INVALID:{family_id}")
            if not isinstance(audit.get("dataset_size_bytes"), int) or audit["dataset_size_bytes"] <= 0:
                failures.append(f"ALE_DATASET_SIZE_INVALID:{family_id}")
            if audit.get("private_content_cobundled") is not True:
                failures.append(f"ALE_PRIVATE_CONTENT_BOUNDARY_MISSING:{family_id}")
            required_blockers = {
                "PUBLIC_ONLY_EXTRACTION_NOT_IMPLEMENTED",
                "NATIVE_PROGRAM_BUNDLE_NOT_IMPLEMENTED",
                "DOCKER_JUDGE_PREFLIGHT_NOT_PASSED",
            }
            if status is IntegrationStatus.CATALOGUED and set(audit.get("execution_blockers", [])) != required_blockers:
                failures.append(f"ALE_CATALOG_BLOCKERS_INCOMPLETE:{family_id}")
            if status is not IntegrationStatus.CATALOGUED:
                admission = family.get("admission") or {}
                required_ale = (
                    "public_only_extraction_digest",
                    "native_program_bundle_digest",
                    "docker_judge_preflight_digest",
                )
                if any(not admission.get(key) for key in required_ale):
                    failures.append(f"ALE_EXECUTION_ADMISSION_INCOMPLETE:{family_id}")
        if status is IntegrationStatus.DEVELOPMENT_READY:
            development_ready += 1
            adapter_id = family.get("adapter_id")
            allowed_adapters = {
                InternalConsumedSi2Adapter.adapter_id,
                ALGOTUNE_DEV_ADAPTER_ID,
                ALGOTUNE_R2_DEV_ADAPTER_ID,
            }
            if adapter_id not in allowed_adapters or not family.get("instance_ids"):
                failures.append(f"DEVELOPMENT_ADAPTER_BINDING_INCOMPLETE:{family_id}")
            if adapter_id in {ALGOTUNE_DEV_ADAPTER_ID, ALGOTUNE_R2_DEV_ADAPTER_ID}:
                binding = family.get("development_binding") or {}
                evaluator_regime = (
                    ALGOTUNE_DEV_EVALUATOR_REGIME
                    if adapter_id == ALGOTUNE_DEV_ADAPTER_ID
                    else ALGOTUNE_R2_DEV_EVALUATOR_REGIME
                )
                required = (
                    "upstream_task_sha256",
                    "upstream_description_sha256",
                    "evaluator_regime",
                    "dependency_profile",
                )
                if any(not binding.get(key) for key in required):
                    failures.append(f"DEVELOPMENT_PROVENANCE_BINDING_INCOMPLETE:{family_id}")
                if binding.get("evaluator_regime") != evaluator_regime:
                    failures.append(f"DEVELOPMENT_EVALUATOR_REGIME_MISMATCH:{family_id}")
                if binding.get("upstream_evaluator_reused") is not False:
                    failures.append(f"UPSTREAM_EVALUATOR_REUSE_MUST_BE_EXPLICITLY_FALSE:{family_id}")
                source = sources.get(str(source_id), {})
                if source.get("revision") != ALGOTUNE_DEV_UPSTREAM_REVISION:
                    failures.append(f"DEVELOPMENT_SOURCE_REVISION_MISMATCH:{family_id}")
                for key in ("upstream_task_sha256", "upstream_description_sha256"):
                    if not re.fullmatch(r"[0-9a-f]{64}", str(binding.get(key, ""))):
                        failures.append(f"DEVELOPMENT_DIGEST_INVALID:{family_id}:{key}")
                    if adapter_id == ALGOTUNE_DEV_ADAPTER_ID:
                        expected_digest = (ALGOTUNE_DEV_UPSTREAM_BINDINGS.get(family_id) or {}).get(key)
                    else:
                        pair = ALGOTUNE_R2_DEV_UPSTREAM_BINDINGS.get(family_id)
                        expected_digest = pair[0 if key == "upstream_task_sha256" else 1] if pair else None
                    if re.fullmatch(r"[0-9a-f]{64}", str(binding.get(key, ""))) and binding.get(key) != expected_digest:
                        failures.append(f"DEVELOPMENT_DIGEST_BINDING_MISMATCH:{family_id}:{key}")
        if status is IntegrationStatus.ADMITTED:
            admission = family.get("admission") or {}
            required = ("adapter_digest", "evaluator_digest", "license_audit_digest", "preflight_receipt_digest")
            if any(not admission.get(key) for key in required):
                failures.append(f"ADMISSION_BINDING_INCOMPLETE:{family_id}")
        if family.get("fresh_generalization_claim_authorized") is not False:
            failures.append(f"CATALOG_CANNOT_AUTHORIZE_GENERALIZATION:{family_id}")

    if tier_counts != EXPECTED_TIER_COUNTS:
        failures.append(f"TIER_COUNTS_MISMATCH:{tier_counts}")
    if registry.get("expected_tier_counts") != EXPECTED_TIER_COUNTS:
        failures.append("DECLARED_TIER_COUNTS_MISMATCH")
    if development_ready < 2:
        failures.append("NO_EXECUTABLE_DEVELOPMENT_VERTICAL_SLICE")
    partitions = registry.get("partition_policy") or {}
    if set(partitions) != {role.value for role in ShardRole}:
        failures.append("PARTITION_POLICY_INCOMPLETE")
    elif partitions["SEALED"].get("consumption_unit") != "SEALED_INSTANCE_OR_SHARD":
        failures.append("SEALED_CONSUMPTION_UNIT_INVALID")

    if failures:
        raise ValueError("benchmark bank validation failed: " + "; ".join(failures))
    return {
        "status": "BENCHMARK_BANK_V1_REGISTRY_VALID",
        "bank_id": registry["bank_id"],
        "registry_digest": digest_json(registry),
        "family_count": len(families),
        "tier_counts": tier_counts,
        "development_ready_families": development_ready,
        "catalogued_families": sum(
            family["integration_status"] == IntegrationStatus.CATALOGUED.value for family in families
        ),
        "admitted_families": sum(
            family["integration_status"] == IntegrationStatus.ADMITTED.value for family in families
        ),
        "fresh_instances_consumed": 0,
        "claim_ceiling": "BANK_INFRASTRUCTURE_AND_CATALOG_ONLY",
    }


def assess_shard_access(
    *,
    role: ShardRole,
    purpose: ClaimPurpose,
    integration_status: IntegrationStatus,
    claim_upgrade_gate_passed: bool = False,
    winner_frozen: bool = False,
    blind_selection_isolated: bool = False,
) -> dict[str, Any]:
    failures: list[str] = []
    if integration_status is IntegrationStatus.CATALOGUED:
        failures.append("BENCHMARK_FAMILY_NOT_EXECUTION_ADMITTED")
    if role is ShardRole.SEALED and integration_status is not IntegrationStatus.ADMITTED:
        failures.append("BENCHMARK_FAMILY_NOT_SCIENTIFICALLY_ADMITTED")
    if purpose in {ClaimPurpose.DEVELOPMENT, ClaimPurpose.PERIODIC_REGRESSION} and role is ShardRole.SEALED:
        failures.append("NO_FRESH_TASK_FOR_DEBUGGING")
    if role is ShardRole.DEV and purpose is not ClaimPurpose.DEVELOPMENT:
        failures.append("DEV_SHARD_CANNOT_UPGRADE_CLAIM")
    if role is ShardRole.SHADOW and purpose is not ClaimPurpose.PERIODIC_REGRESSION:
        failures.append("SHADOW_SHARD_IS_NOT_ADMISSION_EVIDENCE")
    if role is ShardRole.SEALED and purpose not in {ClaimPurpose.FRESH_ADMISSION, ClaimPurpose.BLIND_CONFIRMATION}:
        failures.append("SEALED_SHARD_REQUIRES_CLAIM_UPGRADE_PURPOSE")
    if role is ShardRole.SEALED and not claim_upgrade_gate_passed:
        failures.append("CLAIM_UPGRADE_GATE_NOT_PASSED")
    if purpose is ClaimPurpose.BLIND_CONFIRMATION:
        if not winner_frozen:
            failures.append("WINNER_NOT_FROZEN")
        if not blind_selection_isolated:
            failures.append("BLIND_SELECTION_ISOLATION_NOT_ESTABLISHED")
    return {
        "authorized": not failures,
        "decision": "AUTHORIZED" if not failures else "DENIED_FAIL_CLOSED",
        "failures": failures,
        "role": role.value,
        "purpose": purpose.value,
        "consumption_unit": "SEALED_INSTANCE_OR_SHARD" if role is ShardRole.SEALED else "REUSABLE_INSTANCE",
        "scientific_verdict_authority": "ProblemContract+GateEngine",
    }


class InternalConsumedSi2Adapter:
    adapter_id = "discoveryos.internal_consumed_si2.v1"

    def materialize(self, family: dict[str, Any], instance_id: str, output_dir: Path) -> BenchmarkResolution:
        if family.get("integration_status") != IntegrationStatus.DEVELOPMENT_READY.value:
            raise RuntimeError("only DEVELOPMENT_READY internal families may be materialized")
        if instance_id not in family.get("instance_ids", []):
            raise ValueError(f"instance is not registered for family: {instance_id}")
        tasks = {
            task.task.task_id: task
            for task in (*si2_discovery_tasks(), *si2_confirmation_tasks())
        }
        task = tasks.get(instance_id)
        if task is None or task.task.category != family.get("upstream_task"):
            raise RuntimeError("registered internal instance binding drift")
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=False)
        initial = output_dir / "algorithm.py"
        public_tests = output_dir / "public_tests.py"
        evaluator = output_dir / "evaluate.py"
        initial.write_text(normalized_source(task.task.algorithm_source), encoding="utf-8")
        public_tests.write_text(normalized_source(task.task.public_tests_source), encoding="utf-8")
        evaluator.write_text(normalized_source(task.task.evaluator_source), encoding="utf-8")
        instance_payload = {
            "family_id": family["family_id"],
            "instance_id": instance_id,
            "task_payload_digest": task.payload_digest,
            "initial_program_sha256": digest_bytes(initial.read_bytes()),
            "public_tests_sha256": digest_bytes(public_tests.read_bytes()),
            "evaluator_sha256": digest_bytes(evaluator.read_bytes()),
        }
        (output_dir / "bank-instance.json").write_text(
            json.dumps(instance_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return BenchmarkResolution(
            family_id=family["family_id"],
            instance_id=instance_id,
            initial_program_path=str(initial),
            public_tests_path=str(public_tests),
            evaluator_path=str(evaluator),
            evaluator_digest=instance_payload["evaluator_sha256"],
            instance_digest=digest_json(instance_payload),
            claim_ceiling="CONSUMED_DEVELOPMENT_ONLY",
            adapter_id=self.adapter_id,
            source_revision="LOCAL_CONSUMED_SI2",
            evaluator_regime="SI2_FROZEN_CONSUMED_DEV",
        )


def materialize_bank_instance(
    registry_path: Path,
    *,
    family_id: str,
    instance_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    registry = load_benchmark_bank(registry_path.resolve())
    family = next((item for item in registry["families"] if item["family_id"] == family_id), None)
    if family is None:
        raise ValueError(f"unknown benchmark family: {family_id}")
    adapter_id = family.get("adapter_id")
    if adapter_id == InternalConsumedSi2Adapter.adapter_id:
        resolution = InternalConsumedSi2Adapter().materialize(family, instance_id, output_dir)
    elif adapter_id == ALGOTUNE_DEV_ADAPTER_ID:
        external = materialize_algotune_dev(family, instance_id, output_dir)
        resolution = BenchmarkResolution(**external)
    elif adapter_id == ALGOTUNE_R2_DEV_ADAPTER_ID:
        external = materialize_r2_dev(family, instance_id, output_dir)
        resolution = BenchmarkResolution(**external)
    else:
        raise RuntimeError(f"benchmark family is catalogued but has no admitted local adapter: {family_id}")
    return {
        "status": "BENCHMARK_DEV_INSTANCE_MATERIALIZED",
        "bank_id": registry["bank_id"],
        "registry_digest": digest_json(registry),
        "resolution": {
            "family_id": resolution.family_id,
            "instance_id": resolution.instance_id,
            "initial_program_path": resolution.initial_program_path,
            "public_tests_path": resolution.public_tests_path,
            "evaluator_path": resolution.evaluator_path,
            "evaluator_digest": resolution.evaluator_digest,
            "instance_digest": resolution.instance_digest,
            "claim_ceiling": resolution.claim_ceiling,
            "adapter_id": resolution.adapter_id,
            "source_revision": resolution.source_revision,
            "evaluator_regime": resolution.evaluator_regime,
            "task_contract_path": resolution.task_contract_path,
        },
        "fresh_instances_consumed": 0,
    }
