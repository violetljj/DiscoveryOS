from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.br_a_tasks import br_a_tasks
from discoveryos.benchmarks.local_patch_admission import (
    DEFAULT_ITERATIONS,
    DEFAULT_TOKEN_CEILING,
    MIN_SUMMED_IMPROVEMENT_MARGIN,
    MIN_SUCCESS_MARGIN,
    _initialize_arm,
    _run_arm,
)
from discoveryos.benchmarks.local_patch_reliability import (
    FRESH_READMISSION_POLICY,
    evaluate_fresh_reliability_gate,
)
from discoveryos.benchmarks.real_code_tasks import admission_tasks
from discoveryos.contracts.models import EvidenceValidity, FailureKind, Fidelity
from discoveryos.contracts.patch import GenerationStatus
from discoveryos.operators.local_patch import LOCAL_PATCH_PROMPT_TEMPLATE, PatchProvider
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_bytes, digest_json, jsonable


BR_A_TASK_COUNT = 8
BR_A_MANIFEST_RECORD = "sealed-br-a-admission-manifest.json"
BR_A_REPORT_RECORD = "local-patch-br-a-readmission-report.json"
HARNESS_PATHS = (
    "src/discoveryos/benchmarks/br_a_tasks.py",
    "src/discoveryos/benchmarks/local_patch_admission.py",
    "src/discoveryos/benchmarks/local_patch_readmission.py",
    "src/discoveryos/benchmarks/local_patch_reliability.py",
    "src/discoveryos/contracts/executable.py",
    "src/discoveryos/operators/local_patch.py",
    "src/discoveryos/providers/codex_exec.py",
    "src/discoveryos/runtime/repository_runner.py",
)


def seal_local_patch_readmission(
    workspace: Path,
    *,
    provider: PatchProvider,
    token_ceiling: int = DEFAULT_TOKEN_CEILING,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict[str, Any]:
    """Create repositories and an immutable BR-A manifest without model calls."""

    if token_ceiling != FRESH_READMISSION_POLICY["token_ceiling_per_llm_arm_per_task"]:
        raise ValueError("BR-A token ceiling is frozen at 90000 per LLM arm per task")
    if iterations != FRESH_READMISSION_POLICY["iterative_scientific_call_limit"]:
        raise ValueError("BR-A iterative scientific call limit is frozen at three")
    tasks = br_a_tasks()
    if len(tasks) != BR_A_TASK_COUNT:
        raise RuntimeError("BR-A requires exactly eight tasks")
    _assert_fresh_task_surface(tasks)
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if (workspace / "arms").exists():
        raise RuntimeError("cannot seal BR-A after arm execution has started")

    task_set_hash = digest_json(tuple(jsonable(task) for task in tasks))
    task_records: list[dict[str, Any]] = []
    for task in tasks:
        repository, commit = task.initialize_repository(workspace / "protocol")
        task_records.append(
            {
                "task_id": task.task_id,
                "category": task.category,
                "target_file": task.entrypoint,
                "task_payload_digest": digest_json(task),
                "repo_commit": commit,
                "repo_tree": _git(repository, "rev-parse", f"{commit}^{{tree}}").strip(),
                "tracked_file_sha256": {
                    path: digest_bytes((repository / path).read_bytes())
                    for path in (task.entrypoint, "public_tests.py", "evaluate.py", "requirements.lock")
                },
                "baseline_profile": _baseline_profile(repository, task.entrypoint),
            }
        )

    provider_settings_digest = getattr(
        provider,
        "settings_digest",
        digest_json({"provider": provider.provider_name, "model": provider.model}),
    )
    repository_root = Path(__file__).resolve().parents[3]
    provider_version = getattr(provider, "provider_version", "unknown")
    if provider_version == "unknown":
        raise RuntimeError("BR-A seal requires an executable provider with a reportable version")
    manifest_payload = {
        "protocol": "R1.0-BR-A_FRESH_READMISSION_V1",
        "task_set_hash": task_set_hash,
        "repo_commit_per_task": {item["task_id"]: item["repo_commit"] for item in task_records},
        "tasks": task_records,
        "candidate_bundle_version": "executable-candidate-v3",
        "repair_policy": "recount_hunks",
        "token_budget": {
            "per_task_per_llm_arm": token_ceiling,
            "accounting": "actual_input_plus_output_tokens",
            "cache_tokens": "reported_separately",
            "model_repair_tokens": "included_in_arm_total",
            "deterministic_recount": "reported_as_mechanics_cost_without_model_tokens",
        },
        "model_config": {
            "provider": provider.provider_name,
            "model": provider.model,
            "provider_version": provider_version,
            "provider_settings_digest": provider_settings_digest,
        },
        "arm_definitions": {
            "baseline": {"scientific_calls": 0},
            "one_shot_llm": {"scientific_call_limit": 1},
            "iterative_local_patch": {"scientific_call_limit": iterations},
        },
        "reliability_gates": {
            "one_shot_max_invalid_rate": 0.40,
            "iterative_max_invalid_rate": 0.40,
            "maximum_iterative_minus_one_shot_invalid_rate": 0.10,
            "final_blind_receipts": 0,
            "all_accepted_candidate_evidence_replay": True,
        },
        "search_value_gates": {
            "minimum_success_task_margin": MIN_SUCCESS_MARGIN,
            "minimum_summed_improvement_margin": MIN_SUMMED_IMPROVEMENT_MARGIN,
            "minimum_paired_wins": 2,
            "maximum_paired_losses": 0,
        },
        "allowed_retry_count": {
            "mechanical_repairs_per_root_generation": 1,
            "task_replacement": 0,
            "threshold_relaxation": 0,
        },
        "stop_rule": {
            "per_arm": "stop at score 1.0, scientific call limit, or insufficient remaining measured-token reservation",
            "global": "evaluate all eight sealed tasks exactly once; no replacement or post-hoc rerun",
        },
        "frozen_implementation": {
            "prompt_template_digest": digest_bytes(LOCAL_PATCH_PROMPT_TEMPLATE.encode("utf-8")),
            "fresh_reliability_policy_digest": digest_json(FRESH_READMISSION_POLICY),
            "discoveryos_git_head": _git(repository_root, "rev-parse", "HEAD").strip(),
            "harness_file_sha256": {
                path: digest_bytes((repository_root / path).read_bytes()) for path in HARNESS_PATHS
            },
        },
        "freshness_assertions": {
            "consumed_task_id_overlap": 0,
            "consumed_category_overlap": 0,
            "consumed_target_file_overlap": 0,
            "consumed_algorithm_source_hash_overlap": 0,
        },
        "task_selection_constraints": {
            "mutable_files_per_task": 1,
            "stdlib_only": True,
            "public_tests_pass_before_seal": True,
            "baseline_g1_and_g2_headroom": True,
            "task_ids_categories_targets_and_source_hashes_disjoint_from_consumed_corpus": True,
        },
    }
    manifest = {
        **manifest_payload,
        "admission_manifest_digest": digest_json(manifest_payload),
    }
    store = ArtifactStore(workspace / "admission-artifacts")
    path = store.write_record(BR_A_MANIFEST_RECORD, manifest)
    return {
        "status": "SEALED",
        "model_calls": 0,
        "task_count": len(tasks),
        "task_set_hash": task_set_hash,
        "admission_manifest_digest": manifest["admission_manifest_digest"],
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "manifest_path": str(path),
    }


def run_local_patch_readmission(
    workspace: Path,
    *,
    provider: PatchProvider,
    manifest_digest: str,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute BR-A only after the immutable manifest has been verified."""

    workspace = workspace.resolve()
    store = ArtifactStore(workspace / "admission-artifacts")
    manifest_path = store.records / BR_A_MANIFEST_RECORD
    if not manifest_path.is_file():
        raise RuntimeError("BR-A must be sealed before execution")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_manifest(manifest, manifest_digest, provider, workspace)
    if (store.records / BR_A_REPORT_RECORD).exists():
        raise RuntimeError("BR-A report already exists; the sealed experiment cannot be rerun")
    if (workspace / "arms").exists():
        raise RuntimeError("BR-A arms already exist; refusing an ambiguous resume or second execution")

    tasks = br_a_tasks()
    task_reports: list[dict[str, Any]] = []
    arm_objects: dict[tuple[str, str], Any] = {}
    token_ceiling = int(manifest["token_budget"]["per_task_per_llm_arm"])
    iterations = int(manifest["arm_definitions"]["iterative_local_patch"]["scientific_call_limit"])
    for task in tasks:
        repository = workspace / "protocol" / task.task_id / "repo"
        base_commit = manifest["repo_commit_per_task"][task.task_id]
        baseline_arm = _initialize_arm(workspace / "arms" / task.task_id / "baseline", task, repository, base_commit, token_ceiling)
        one_shot_arm = _initialize_arm(workspace / "arms" / task.task_id / "one-shot", task, repository, base_commit, token_ceiling)
        iterative_arm = _initialize_arm(workspace / "arms" / task.task_id / "iterative", task, repository, base_commit, token_ceiling)
        arm_objects[(task.task_id, "one_shot_llm")] = one_shot_arm
        arm_objects[(task.task_id, "iterative_local_patch")] = iterative_arm

        baseline = asyncio.run(_run_arm(baseline_arm, task, provider=None, iterations=0, token_ceiling=token_ceiling))
        one_shot = asyncio.run(_run_arm(one_shot_arm, task, provider=provider, iterations=1, token_ceiling=token_ceiling))
        iterative = asyncio.run(_run_arm(iterative_arm, task, provider=provider, iterations=iterations, token_ceiling=token_ceiling))
        if not math.isclose(baseline["best_score"], one_shot["baseline_score"]) or not math.isclose(
            baseline["best_score"], iterative["baseline_score"]
        ):
            raise RuntimeError(f"baseline drift across arms for {task.task_id}")
        task_report = {
            "task_id": task.task_id,
            "category": task.category,
            "target_file": task.entrypoint,
            "base_commit": base_commit,
            "baseline": baseline,
            "one_shot_llm": one_shot,
            "iterative_local_patch": iterative,
            "paired_delta": round(iterative["best_score"] - one_shot["best_score"], 8),
        }
        task_reports.append(task_report)
        if progress:
            progress(
                f"completed {task.task_id}: baseline={baseline['best_score']:.4f} "
                f"one_shot={one_shot['best_score']:.4f} iterative={iterative['best_score']:.4f}"
            )

    one_shot_layer = _aggregate_candidate_layers(task_reports, arm_objects, "one_shot_llm")
    iterative_layer = _aggregate_candidate_layers(task_reports, arm_objects, "iterative_local_patch")
    final_blind_receipts = sum(
        report[arm]["final_blind_receipts"]
        for report in task_reports
        for arm in ("baseline", "one_shot_llm", "iterative_local_patch")
    )
    replay_complete = all(
        report[arm]["checks"]["evidence_replay_complete"]
        for report in task_reports
        for arm in ("baseline", "one_shot_llm", "iterative_local_patch")
    )
    reliability = evaluate_fresh_reliability_gate(
        one_shot_invalid_rate=one_shot_layer["invalid_rate"],
        iterative_invalid_rate=iterative_layer["invalid_rate"],
        final_blind_receipts=final_blind_receipts,
        replay_complete=replay_complete,
    )

    one_shot_successes = sum(report["one_shot_llm"]["improved"] for report in task_reports)
    iterative_successes = sum(report["iterative_local_patch"]["improved"] for report in task_reports)
    one_shot_improvement = sum(report["one_shot_llm"]["best_feasible_improvement"] for report in task_reports)
    iterative_improvement = sum(report["iterative_local_patch"]["best_feasible_improvement"] for report in task_reports)
    deltas = [float(report["paired_delta"]) for report in task_reports]
    wins = sum(delta > 0 for delta in deltas)
    ties = sum(delta == 0 for delta in deltas)
    losses = sum(delta < 0 for delta in deltas)
    search_checks = {
        "successful_tasks_margin": iterative_successes >= one_shot_successes + MIN_SUCCESS_MARGIN,
        "summed_improvement_margin": iterative_improvement >= one_shot_improvement + MIN_SUMMED_IMPROVEMENT_MARGIN,
        "minimum_paired_wins": wins >= 2,
        "maximum_paired_losses": losses == 0,
    }
    search_value_passed = all(search_checks.values())
    matched_token = all(
        report[arm]["actual_usage"]["tokens"] <= token_ceiling
        and report[arm]["checks"]["successful_generation_usage_reported"]
        for report in task_reports
        for arm in ("one_shot_llm", "iterative_local_patch")
    )
    all_mechanics_checks = all(
        all(report[arm]["checks"].values())
        for report in task_reports
        for arm in ("baseline", "one_shot_llm", "iterative_local_patch")
    )
    passed = reliability["passed"] and search_value_passed and matched_token and all_mechanics_checks
    report = {
        "benchmark_id": "matched_token_real_code_local_patch_br_a_readmission_v1",
        "status": "PASS" if passed else "FAIL",
        "verdict": "LLM_LOCAL_PATCH_ADMITTED" if passed else "LLM_LOCAL_PATCH_NOT_ADMITTED",
        "claim_ceiling": "REAL_CODE_READMISSION_ONLY" if passed else "FRESH_READMISSION_NEGATIVE_RESULT",
        "sealed_admission_manifest_digest": manifest_digest,
        "task_set_hash": manifest["task_set_hash"],
        "frozen_policy": manifest,
        "layers": {
            "patch_mechanics_valid": {
                "one_shot_llm": one_shot_layer["patch_mechanics"],
                "iterative_local_patch": iterative_layer["patch_mechanics"],
                "failure_taxonomy": {
                    "one_shot_llm": one_shot_layer["failure_taxonomy"],
                    "iterative_local_patch": iterative_layer["failure_taxonomy"],
                },
                "deterministic_recount_cost": {
                    "one_shot_llm": one_shot_layer["recount_cost"],
                    "iterative_local_patch": iterative_layer["recount_cost"],
                },
            },
            "candidate_executable_tests_valid": {
                "one_shot_llm": one_shot_layer["executable_tests"],
                "iterative_local_patch": iterative_layer["executable_tests"],
            },
            "search_value_improvement": {
                "one_shot_success_tasks": one_shot_successes,
                "iterative_success_tasks": iterative_successes,
                "one_shot_summed_improvement": round(one_shot_improvement, 8),
                "iterative_summed_improvement": round(iterative_improvement, 8),
                "paired_wins": wins,
                "ties": ties,
                "losses": losses,
                "median_paired_delta": statistics.median(deltas),
                "checks": search_checks,
                "passed": search_value_passed,
            },
        },
        "reliability_gate": reliability,
        "matched_token_passed": matched_token,
        "all_mechanics_checks_passed": all_mechanics_checks,
        "final_blind_receipts": final_blind_receipts,
        "task_reports": task_reports,
        "no_task_replacement": True,
        "no_threshold_relaxation": True,
        "not_authorized": [] if passed else ["LLM Local Patch in DiscoveryOS search kernel"],
    }
    path = store.write_record(BR_A_REPORT_RECORD, report)
    report["report_file_sha256"] = digest_bytes(path.read_bytes())
    report["report_path"] = str(path)
    return report


def _assert_fresh_task_surface(tasks: tuple[Any, ...]) -> None:
    consumed = admission_tasks()
    comparisons = (
        ({task.task_id for task in tasks}, {task.task_id for task in consumed}, "task id"),
        ({task.category for task in tasks}, {task.category for task in consumed}, "category"),
        ({task.entrypoint for task in tasks}, {task.entrypoint for task in consumed}, "target file"),
        ({digest_json(task.algorithm_source) for task in tasks}, {digest_json(task.algorithm_source) for task in consumed}, "algorithm source"),
    )
    for fresh_values, consumed_values, label in comparisons:
        overlap = fresh_values.intersection(consumed_values)
        if overlap:
            raise RuntimeError(f"BR-A {label} overlaps consumed corpus: {sorted(overlap)}")
    if len({task.task_id for task in tasks}) != len(tasks) or len({task.category for task in tasks}) != len(tasks):
        raise RuntimeError("BR-A task ids and categories must be unique")


def _verify_manifest(manifest: dict[str, Any], expected_digest: str, provider: PatchProvider, workspace: Path) -> None:
    recorded_digest = manifest.get("admission_manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "admission_manifest_digest"}
    if recorded_digest != digest_json(payload) or expected_digest != recorded_digest:
        raise RuntimeError("sealed BR-A manifest digest mismatch")
    tasks = br_a_tasks()
    if manifest.get("task_set_hash") != digest_json(tuple(jsonable(task) for task in tasks)):
        raise RuntimeError("sealed BR-A task payload has drifted")
    settings = getattr(
        provider,
        "settings_digest",
        digest_json({"provider": provider.provider_name, "model": provider.model}),
    )
    expected_model = manifest["model_config"]
    if provider.provider_name != expected_model["provider"] or provider.model != expected_model["model"] or settings != expected_model["provider_settings_digest"]:
        raise RuntimeError("provider/model/config differs from the sealed BR-A manifest")
    if getattr(provider, "provider_version", "unknown") != expected_model["provider_version"]:
        raise RuntimeError("provider version differs from the sealed BR-A manifest")
    repository_root = Path(__file__).resolve().parents[3]
    for path, expected_sha in manifest["frozen_implementation"]["harness_file_sha256"].items():
        if digest_bytes((repository_root / path).read_bytes()) != expected_sha:
            raise RuntimeError(f"sealed BR-A harness file has drifted: {path}")
    by_id = {item["task_id"]: item for item in manifest["tasks"]}
    for task in tasks:
        item = by_id.get(task.task_id)
        if item is None or item["task_payload_digest"] != digest_json(task):
            raise RuntimeError(f"sealed task definition mismatch: {task.task_id}")
        repository = workspace / "protocol" / task.task_id / "repo"
        if _git(repository, "status", "--porcelain").strip():
            raise RuntimeError(f"sealed task repository is dirty: {task.task_id}")
        if _git(repository, "rev-parse", "HEAD").strip() != item["repo_commit"]:
            raise RuntimeError(f"sealed task repository commit mismatch: {task.task_id}")
        for path, expected_sha in item["tracked_file_sha256"].items():
            if digest_bytes((repository / path).read_bytes()) != expected_sha:
                raise RuntimeError(f"sealed task file digest mismatch: {task.task_id}:{path}")


def _aggregate_candidate_layers(
    task_reports: list[dict[str, Any]],
    arm_objects: dict[tuple[str, str], Any],
    report_key: str,
) -> dict[str, Any]:
    candidate_count = 0
    invalid_count = 0
    patch_valid_count = 0
    executable_count = 0
    taxonomy: Counter[str] = Counter()
    recount_invocations = 0
    recount_wall_seconds = 0.0
    for task_report in task_reports:
        arm = arm_objects[(task_report["task_id"], report_key)]
        ledger = EvidenceLedger(arm.root / "ledger.sqlite3")
        generations = ledger.generation_records()
        generated_ids = {
            generation.candidate_id
            for generation in generations
            if generation.status is GenerationStatus.SUCCEEDED and generation.candidate_id is not None
        }
        evidence = ledger.evidence_records()
        for candidate_id in generated_ids:
            records = [item for item in evidence if item.candidate_id == candidate_id]
            candidate_count += 1
            g0 = next((item for item in records if item.fidelity is Fidelity.G0), None)
            executable = g0 is not None and g0.validity is EvidenceValidity.VALID
            executable_count += int(executable)
            g2 = next((item for item in records if item.fidelity is Fidelity.G2), None)
            invalid_count += int(g2 is None or g2.validity is not EvidenceValidity.VALID)
            failure = next((item for item in records if item.validity is not EvidenceValidity.VALID), None)
            patch_valid = failure is None or failure.failure_kind not in {FailureKind.PATCH_REJECTED, FailureKind.PATH_VIOLATION}
            patch_valid_count += int(patch_valid)
            if failure is not None:
                taxonomy[_failure_category(failure, arm.artifacts)] += 1
            if g0 is not None:
                for artifact_digest in g0.artifacts:
                    try:
                        payload = json.loads(arm.artifacts.get_bytes(artifact_digest))
                    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                        continue
                    if payload.get("step") == "patch_recount":
                        recount_invocations += 1
                        recount_wall_seconds += float(payload.get("wall_seconds", 0.0))
    invalid_rate = invalid_count / candidate_count if candidate_count else 0.0
    return {
        "candidate_count": candidate_count,
        "invalid_count": invalid_count,
        "invalid_rate": invalid_rate,
        "patch_mechanics": {
            "valid_candidates": patch_valid_count,
            "total_candidates": candidate_count,
            "valid_rate": patch_valid_count / candidate_count if candidate_count else 0.0,
        },
        "executable_tests": {
            "valid_candidates": executable_count,
            "total_candidates": candidate_count,
            "valid_rate": executable_count / candidate_count if candidate_count else 0.0,
            "invalid_rate": (candidate_count - executable_count) / candidate_count if candidate_count else 0.0,
        },
        "failure_taxonomy": dict(sorted(taxonomy.items())),
        "recount_cost": {
            "git_apply_recount_invocations_at_g0": recount_invocations,
            "wall_seconds_at_g0": recount_wall_seconds,
            "model_tokens": 0,
        },
    }


def _failure_category(evidence: Any, artifacts: ArtifactStore) -> str:
    signature = (evidence.failure_signature or "").lower()
    if evidence.failure_kind is FailureKind.PATCH_REJECTED:
        return "patch_parse_failure" if "patch_parse_failure" in signature else "patch_apply_failure"
    if evidence.failure_kind is FailureKind.PATH_VIOLATION:
        return "path_violation"
    if evidence.failure_kind is FailureKind.TEST_FAILED:
        return "unit_test_failure"
    if evidence.failure_kind is FailureKind.BUILD_FAILED:
        for digest in evidence.artifacts:
            try:
                payload = json.loads(artifacts.get_bytes(digest))
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                continue
            diagnostic = f"{payload.get('stdout', '')}\n{payload.get('stderr', '')}"
            if "SyntaxError" in diagnostic or "IndentationError" in diagnostic:
                return "syntax_error"
        return "build_failure"
    return evidence.failure_kind.value.lower() if evidence.failure_kind else "not_evaluable"


def _baseline_profile(repository: Path, entrypoint: str) -> dict[str, Any]:
    profile_environment = os.environ.copy()
    profile_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    public = subprocess.run(
        ("python", "public_tests.py"),
        cwd=repository,
        env=profile_environment,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if public.returncode != 0:
        raise RuntimeError(f"fresh task public tests fail before seal: {repository.name}:{public.stderr[-1000:]}")
    scores: dict[str, float] = {}
    for fidelity in ("G1_PROXY", "G2_DEVELOPMENT"):
        environment = profile_environment.copy()
        environment["DISCOVERYOS_FIDELITY"] = fidelity
        evaluated = subprocess.run(
            ("python", "evaluate.py"),
            cwd=repository,
            env=environment,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if evaluated.returncode != 0:
            raise RuntimeError(f"fresh task evaluator fails before seal: {repository.name}:{fidelity}:{evaluated.stderr[-1000:]}")
        payload = json.loads(evaluated.stdout)
        score = float(payload["metrics"]["score"])
        if not 0.0 <= score < 1.0 or float(payload["metrics"]["valid"]) != 1.0:
            raise RuntimeError(f"fresh task lacks valid baseline headroom: {repository.name}:{fidelity}:{score}")
        scores[fidelity] = score
    source = (repository / entrypoint).read_text(encoding="utf-8")
    public_source = (repository / "public_tests.py").read_text(encoding="utf-8")
    evaluator_source = (repository / "evaluate.py").read_text(encoding="utf-8")
    return {
        "mutable_loc": len(source.splitlines()),
        "public_test_assertions": public_source.count("assert "),
        "public_test_loc": len(public_source.splitlines()),
        "evaluator_loc": len(evaluator_source.splitlines()),
        "baseline_g1_score": scores["G1_PROXY"],
        "baseline_g2_score": scores["G2_DEVELOPMENT"],
    }


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout
