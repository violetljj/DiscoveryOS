from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from discoveryos.contracts.codec import contract_from_dict
from discoveryos.contracts.executable import ExecutableCandidateBundle
from discoveryos.contracts.models import EvidenceRecord, EvidenceValidity, FailureKind, Fidelity, GateDecision
from discoveryos.contracts.patch import GenerationKind, GenerationRecord, GenerationStatus
from discoveryos.evaluation import GateEngine
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_json


INVALID_TAXONOMY = (
    "proposal_schema_invalid",
    "patch_parse_failure",
    "patch_apply_failure",
    "forbidden_path",
    "mutable_path_violation",
    "environment_lock_violation",
    "syntax_error",
    "import_error",
    "build_failure",
    "unit_test_failure",
    "runtime_exception",
    "timeout",
    "malformed_evaluator_output",
    "repair_failed",
)

MAX_FRESH_INVALID_RATE = 0.40
MAX_ITERATIVE_INVALID_RATE_GAP = 0.10
FRESH_READMISSION_POLICY = {
    "corpus_role": "FRESH_REAL_CODE_READMISSION",
    "task_count_range": (6, 8),
    "token_ceiling_per_llm_arm_per_task": 90_000,
    "iterative_scientific_call_limit": 3,
    "mechanical_repairs_per_root_generation": 1,
    "one_shot_max_invalid_rate": MAX_FRESH_INVALID_RATE,
    "iterative_max_invalid_rate": MAX_FRESH_INVALID_RATE,
    "maximum_iterative_minus_one_shot_invalid_rate": MAX_ITERATIVE_INVALID_RATE_GAP,
    "minimum_success_task_margin": 2,
    "minimum_summed_improvement_margin": 0.25,
    "minimum_paired_wins": 2,
    "maximum_paired_losses": 0,
    "final_blind_receipts": 0,
    "all_accepted_candidate_evidence_replay": True,
}


def evaluate_fresh_reliability_gate(
    *,
    one_shot_invalid_rate: float,
    iterative_invalid_rate: float,
    final_blind_receipts: int,
    replay_complete: bool,
) -> dict[str, Any]:
    checks = {
        "one_shot_invalid_rate": one_shot_invalid_rate <= MAX_FRESH_INVALID_RATE,
        "iterative_invalid_rate": iterative_invalid_rate <= MAX_FRESH_INVALID_RATE,
        "iterative_invalid_rate_gap": (
            iterative_invalid_rate - one_shot_invalid_rate <= MAX_ITERATIVE_INVALID_RATE_GAP
        ),
        "no_final_blind": final_blind_receipts == 0,
        "replay_complete": replay_complete,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "policy": FRESH_READMISSION_POLICY,
        "policy_digest": digest_json(FRESH_READMISSION_POLICY),
    }


def audit_local_patch_invalids(workspace: Path) -> dict[str, Any]:
    """Autopsy frozen local-patch ledgers without model calls or scientific re-evaluation."""
    workspace = workspace.resolve()
    arm_reports: list[dict[str, Any]] = []
    total_categories: Counter[str] = Counter()
    total_recount_recoverable = 0
    scientific_parent_violations = 0
    parent_context_mismatches = 0

    for task_root in sorted((workspace / "arms").iterdir()):
        if not task_root.is_dir():
            continue
        for arm_name in ("one-shot", "iterative"):
            root = task_root / arm_name
            ledger_path = root / "ledger.sqlite3"
            if not ledger_path.is_file():
                continue
            ledger = EvidenceLedger(ledger_path)
            artifacts = ArtifactStore(root / "artifacts")
            with ledger.connect() as connection:
                contract_payload = json.loads(connection.execute("SELECT payload FROM contracts").fetchone()["payload"])
            contract = contract_from_dict(contract_payload)
            generations = ledger.generation_records()
            evidence_by_candidate = _evidence_by_candidate(ledger.evidence_records())
            categories: Counter[str] = Counter()
            failures: list[dict[str, Any]] = []
            cumulative_tokens = 0
            cumulative_generation_wall = 0.0
            proposal_index = 0

            for generation in generations:
                cumulative_tokens += generation.usage.tokens
                cumulative_generation_wall += generation.usage.wall_seconds
                if generation.kind is GenerationKind.PROPOSAL:
                    proposal_index += 1
                parent_valid = _scientific_candidate_valid(
                    generation.parent_candidate_id,
                    evidence_by_candidate,
                    contract,
                )
                context_mismatch = generation.kind is GenerationKind.PROPOSAL and _request_reuses_invalid_evidence(
                    artifacts,
                    generation,
                )
                if generation.kind is GenerationKind.PROPOSAL and not parent_valid:
                    scientific_parent_violations += 1
                if context_mismatch:
                    parent_context_mismatches += 1

                category, invalid_evidence = _failure_category(generation, evidence_by_candidate, artifacts)
                if category is None:
                    continue
                recount_recoverable = False
                patch_diagnostic = None
                if (
                    generation.candidate_id is not None
                    and invalid_evidence is not None
                    and invalid_evidence.failure_kind is FailureKind.PATCH_REJECTED
                ):
                    candidate = ledger.get_candidate(generation.candidate_id)
                    bundle = ExecutableCandidateBundle.from_artifact(artifacts, candidate.artifact_digest)
                    original_ok, patch_diagnostic = _check_patch_stack(bundle, recount=False)
                    recount_ok, _ = _check_patch_stack(bundle, recount=True)
                    recount_recoverable = not original_ok and recount_ok
                    if patch_diagnostic:
                        category = _patch_failure_category(patch_diagnostic["stderr"])
                categories[category] += 1
                if generation.kind is GenerationKind.MECHANICAL_REPAIR:
                    categories["repair_failed"] += 1
                total_recount_recoverable += int(recount_recoverable)
                evaluation_wall = sum(
                    item.resource_usage.wall_seconds
                    for item in evidence_by_candidate.get(generation.candidate_id or "", ())
                )
                failures.append(
                    {
                        "task": task_root.name,
                        "arm": arm_name,
                        "generation_kind": generation.kind.value,
                        "generation_index": proposal_index,
                        "generation_id": generation.generation_id,
                        "root_generation_id": generation.root_generation_id,
                        "candidate_id": generation.candidate_id,
                        "parent_candidate_id": generation.parent_candidate_id,
                        "parent_scientifically_valid": parent_valid,
                        "parent_context_mismatch": context_mismatch,
                        "category": category,
                        "repair_failed": generation.kind is GenerationKind.MECHANICAL_REPAIR,
                        "tokens_consumed": generation.usage.tokens,
                        "tokens_consumed_before_failure": cumulative_tokens,
                        "generation_wall_seconds": generation.usage.wall_seconds,
                        "evaluation_wall_seconds": evaluation_wall,
                        "generation_wall_before_failure": cumulative_generation_wall,
                        "failure_signature": (
                            invalid_evidence.failure_signature if invalid_evidence else generation.failure_signature
                        ),
                        "patch_diagnostic": patch_diagnostic,
                        "recount_recoverable": recount_recoverable,
                    }
                )

            generated = [item for item in generations if item.candidate_id is not None]
            invalid_candidates = sum(
                not _scientific_candidate_valid(item.candidate_id or "", evidence_by_candidate, contract)
                for item in generated
            )
            invalid_generations = len(failures)
            total_categories.update(categories)
            arm_reports.append(
                {
                    "task": task_root.name,
                    "arm": arm_name,
                    "generation_count": len(generations),
                    "materialized_candidate_count": len(generated),
                    "invalid_candidate_count": invalid_candidates,
                    "invalid_candidate_rate": invalid_candidates / len(generated) if generated else 0.0,
                    "invalid_generation_count": invalid_generations,
                    "invalid_generation_rate": invalid_generations / len(generations) if generations else 0.0,
                    "repair_count": sum(item.kind is GenerationKind.MECHANICAL_REPAIR for item in generations),
                    "failure_taxonomy": {name: categories[name] for name in INVALID_TAXONOMY},
                    "failures": failures,
                }
            )

    by_arm: dict[str, dict[str, Any]] = {}
    for arm_name in ("one-shot", "iterative"):
        selected = [item for item in arm_reports if item["arm"] == arm_name]
        generated = sum(item["materialized_candidate_count"] for item in selected)
        invalid = sum(item["invalid_candidate_count"] for item in selected)
        generations = sum(item["generation_count"] for item in selected)
        invalid_generations = sum(item["invalid_generation_count"] for item in selected)
        by_arm[arm_name] = {
            "generation_count": generations,
            "materialized_candidate_count": generated,
            "invalid_candidate_count": invalid,
            "invalid_candidate_rate": invalid / generated if generated else 0.0,
            "invalid_generation_count": invalid_generations,
            "invalid_generation_rate": invalid_generations / generations if generations else 0.0,
            "repair_count": sum(item["repair_count"] for item in selected),
        }

    report = {
        "audit_id": "r1_0_br_invalid_autopsy_v2",
        "workspace": str(workspace),
        "model_calls_repeated": False,
        "scientific_evaluation_repeated": False,
        "search_value_claim": False,
        "taxonomy": INVALID_TAXONOMY,
        "summary": {
            "by_arm": by_arm,
            "failure_taxonomy": {name: total_categories[name] for name in INVALID_TAXONOMY},
            "recount_recoverable_failures": total_recount_recoverable,
            "scientific_parent_violations": scientific_parent_violations,
            "parent_context_mismatches": parent_context_mismatches,
        },
        "arm_reports": arm_reports,
    }
    report["report_digest"] = digest_json(report)
    ArtifactStore(workspace / "admission-artifacts").write_record("local-patch-invalid-autopsy-v2.json", report)
    return report


def replay_local_patch_mechanics(workspace: Path) -> dict[str, Any]:
    """Run only patch/build/public-test mechanics on the consumed frozen candidates."""
    workspace = workspace.resolve()
    candidate_results: list[dict[str, Any]] = []
    for task_root in sorted((workspace / "arms").iterdir()):
        if not task_root.is_dir():
            continue
        for arm_name in ("one-shot", "iterative"):
            root = task_root / arm_name
            ledger_path = root / "ledger.sqlite3"
            if not ledger_path.is_file():
                continue
            ledger = EvidenceLedger(ledger_path)
            artifacts = ArtifactStore(root / "artifacts")
            for generation in ledger.generation_records():
                if generation.candidate_id is None:
                    continue
                candidate = ledger.get_candidate(generation.candidate_id)
                bundle = ExecutableCandidateBundle.from_artifact(artifacts, candidate.artifact_digest)
                mechanics = _run_bundle_mechanics(bundle)
                candidate_results.append(
                    {
                        "task": task_root.name,
                        "arm": arm_name,
                        "generation_kind": generation.kind.value,
                        "generation_id": generation.generation_id,
                        "root_generation_id": generation.root_generation_id,
                        "candidate_id": generation.candidate_id,
                        **mechanics,
                    }
                )

    by_arm: dict[str, dict[str, Any]] = {}
    for arm_name in ("one-shot", "iterative"):
        selected = [item for item in candidate_results if item["arm"] == arm_name]
        invalid = sum(not item["mechanically_valid"] for item in selected)
        by_arm[arm_name] = {
            "candidate_count": len(selected),
            "mechanically_invalid_count": invalid,
            "mechanically_invalid_rate": invalid / len(selected) if selected else 0.0,
            "mechanically_valid_count": len(selected) - invalid,
        }
    report = {
        "development_id": "r1_0_br_consumed_mechanics_replay_v1",
        "workspace": str(workspace),
        "corpus_role": "CONSUMED_RELIABILITY_DEVELOPMENT_ONLY",
        "model_calls_repeated": False,
        "scientific_evaluation_repeated": False,
        "scientific_metrics_read": False,
        "search_value_claim": False,
        "apply_policy": "git_apply_recount",
        "summary": {"by_arm": by_arm},
        "candidate_results": candidate_results,
    }
    report["report_digest"] = digest_json(report)
    ArtifactStore(workspace / "admission-artifacts").write_record("local-patch-brd-mechanics-replay.json", report)
    return report


def _evidence_by_candidate(evidence: list[EvidenceRecord]) -> dict[str, tuple[EvidenceRecord, ...]]:
    grouped: dict[str, list[EvidenceRecord]] = {}
    for item in evidence:
        grouped.setdefault(item.candidate_id, []).append(item)
    return {candidate_id: tuple(items) for candidate_id, items in grouped.items()}


def _scientific_candidate_valid(
    candidate_id: str,
    evidence_by_candidate: dict[str, tuple[EvidenceRecord, ...]],
    contract: Any,
) -> bool:
    evidence = evidence_by_candidate.get(candidate_id, ())
    g2 = next((item for item in evidence if item.fidelity is Fidelity.G2), None)
    return bool(
        g2 is not None
        and g2.validity is EvidenceValidity.VALID
        and GateEngine().evaluate(contract, g2).decision is GateDecision.FEASIBLE
    )


def _request_reuses_invalid_evidence(artifacts: ArtifactStore, generation: GenerationRecord) -> bool:
    try:
        request = json.loads(artifacts.get_bytes(generation.request_artifact_digest))
        context = json.loads(request["prompt"].split("FROZEN_CONTEXT_JSON\n", 1)[1])
        summary = json.loads(context["development_evidence_summary"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return False
    return any(item.get("validity") != EvidenceValidity.VALID.value for item in summary.get("parent_development_evidence", ()))


def _failure_category(
    generation: GenerationRecord,
    evidence_by_candidate: dict[str, tuple[EvidenceRecord, ...]],
    artifacts: ArtifactStore,
) -> tuple[str | None, EvidenceRecord | None]:
    if generation.candidate_id is None:
        if generation.status is GenerationStatus.INVALID_RESPONSE:
            signature = (generation.failure_signature or "").lower()
            return ("patch_parse_failure" if "patch" in signature else "proposal_schema_invalid"), None
        return None, None
    invalid = next(
        (
            item
            for item in evidence_by_candidate.get(generation.candidate_id, ())
            if item.validity is not EvidenceValidity.VALID
        ),
        None,
    )
    if invalid is None:
        return None, None
    signature = invalid.failure_signature or ""
    if invalid.failure_kind is FailureKind.PATH_VIOLATION:
        return ("forbidden_path" if "FORBIDDEN" in signature else "mutable_path_violation"), invalid
    if invalid.failure_kind is FailureKind.PATCH_REJECTED:
        if "ENVIRONMENT_LOCK" in signature:
            return "environment_lock_violation", invalid
        if "PATCH_PARSE_FAILURE" in signature:
            return "patch_parse_failure", invalid
        return "patch_apply_failure", invalid
    if invalid.failure_kind is FailureKind.BUILD_FAILED:
        diagnostic = _diagnostic_text(invalid, artifacts)
        if "SyntaxError" in diagnostic or "IndentationError" in diagnostic:
            return "syntax_error", invalid
        if "ImportError" in diagnostic or "ModuleNotFoundError" in diagnostic:
            return "import_error", invalid
        return "build_failure", invalid
    if invalid.failure_kind is FailureKind.TEST_FAILED:
        return "unit_test_failure", invalid
    if invalid.failure_kind is FailureKind.TIMEOUT:
        return "timeout", invalid
    if invalid.failure_kind is FailureKind.EVALUATION_FAILED and "EVALUATION_OUTPUT_INVALID" in signature:
        return "malformed_evaluator_output", invalid
    return "runtime_exception", invalid


def _diagnostic_text(evidence: EvidenceRecord, artifacts: ArtifactStore) -> str:
    blocks = [evidence.failure_signature or ""]
    for digest in evidence.artifacts:
        try:
            payload = json.loads(artifacts.get_bytes(digest))
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("step") in {"patch", "build", "test"}:
            blocks.extend((str(payload.get("stdout", "")), str(payload.get("stderr", ""))))
    return "\n".join(blocks)


def _patch_failure_category(stderr: str) -> str:
    lowered = stderr.lower()
    return (
        "patch_parse_failure"
        if any(marker in lowered for marker in ("corrupt patch", "patch fragment", "unrecognized input"))
        else "patch_apply_failure"
    )


def _check_patch_stack(bundle: ExecutableCandidateBundle, *, recount: bool) -> tuple[bool, dict[str, Any] | None]:
    repository = Path(bundle.base_repository).resolve()
    with tempfile.TemporaryDirectory(prefix="discoveryos-invalid-autopsy-") as temporary:
        worktree = Path(temporary) / "repo"
        added = subprocess.run(
            ("git", "-C", str(repository), "worktree", "add", "--detach", "--force", str(worktree), bundle.base_commit),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if added.returncode != 0:
            return False, {"patch_index": -1, "stderr": added.stderr.strip(), "phase": "worktree_setup"}
        try:
            for index, patch in enumerate(bundle.effective_patch_stack):
                flags = ("--check", "--recount") if recount else ("--check",)
                checked = subprocess.run(
                    ("git", "-C", str(worktree), "apply", *flags, "-"),
                    input=patch,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if checked.returncode != 0:
                    return False, {
                        "patch_index": index,
                        "stderr": checked.stderr.strip(),
                        "phase": "apply_check_recount" if recount else "apply_check",
                    }
                apply_flags = ("--whitespace=nowarn", "--recount") if recount else ("--whitespace=nowarn",)
                applied = subprocess.run(
                    ("git", "-C", str(worktree), "apply", *apply_flags, "-"),
                    input=patch,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if applied.returncode != 0:
                    return False, {
                        "patch_index": index,
                        "stderr": applied.stderr.strip(),
                        "phase": "apply_recount" if recount else "apply",
                    }
            return True, None
        finally:
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "remove", "--force", str(worktree)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "prune"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def _run_bundle_mechanics(bundle: ExecutableCandidateBundle) -> dict[str, Any]:
    repository = Path(bundle.base_repository).resolve()
    with tempfile.TemporaryDirectory(prefix="discoveryos-brd-mechanics-") as temporary:
        worktree = Path(temporary) / "repo"
        added = subprocess.run(
            ("git", "-C", str(repository), "worktree", "add", "--detach", "--force", str(worktree), bundle.base_commit),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if added.returncode != 0:
            return {"mechanically_valid": False, "failure_category": "runtime_exception", "diagnostic": added.stderr[-4000:]}
        try:
            for index, patch in enumerate(bundle.effective_patch_stack):
                applied = subprocess.run(
                    ("git", "-C", str(worktree), "apply", "--whitespace=nowarn", "--recount", "-"),
                    input=patch,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if applied.returncode != 0:
                    return {
                        "mechanically_valid": False,
                        "failure_category": _patch_failure_category(applied.stderr),
                        "diagnostic": applied.stderr[-4000:],
                        "patch_index": index,
                    }
            if not bundle.verify_environment_lock(worktree):
                return {
                    "mechanically_valid": False,
                    "failure_category": "environment_lock_violation",
                    "diagnostic": "frozen environment lock digest changed",
                }
            environment = os.environ.copy()
            environment.update(
                {
                    "DISCOVERYOS_DATA_PATH": "",
                    "DISCOVERYOS_ENTRYPOINT": bundle.entrypoint,
                    "DISCOVERYOS_FIDELITY": Fidelity.G0.value,
                    "DISCOVERYOS_SEED": "0",
                    "PYTHONHASHSEED": "0",
                }
            )
            for step, command in (("build", bundle.build_command), ("test", bundle.test_command)):
                completed = subprocess.run(
                    command.argv,
                    cwd=worktree,
                    env=environment,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=15,
                    check=False,
                )
                if completed.returncode != 0:
                    diagnostic = (completed.stdout + "\n" + completed.stderr)[-4000:]
                    if step == "build" and ("SyntaxError" in diagnostic or "IndentationError" in diagnostic):
                        category = "syntax_error"
                    elif step == "build" and ("ImportError" in diagnostic or "ModuleNotFoundError" in diagnostic):
                        category = "import_error"
                    else:
                        category = "build_failure" if step == "build" else "unit_test_failure"
                    return {
                        "mechanically_valid": False,
                        "failure_category": category,
                        "diagnostic": diagnostic,
                    }
            return {"mechanically_valid": True, "failure_category": None, "diagnostic": None}
        except subprocess.TimeoutExpired as error:
            return {"mechanically_valid": False, "failure_category": "timeout", "diagnostic": str(error)}
        finally:
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "remove", "--force", str(worktree)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "prune"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
