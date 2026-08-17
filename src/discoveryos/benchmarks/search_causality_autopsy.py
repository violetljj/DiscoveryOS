from __future__ import annotations

import ast
import json
import statistics
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.local_patch_admission import _materialize_files
from discoveryos.benchmarks.si2 import MANIFEST_RECORD, DISCOVERY_REPORT_RECORD
from discoveryos.benchmarks.si2_tasks import normalized_source
from discoveryos.contracts.executable import ExecutableCandidateBundle
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_bytes, digest_json


INTERNAL_ARMS = ("CORE", "CURRENT_DISCOVERYOS", "VANILLA_STRONG_AGENT")
AUTOPSY_RECORD = "si2-search-causality-autopsy.json"


class _StructuralNormalizer(ast.NodeTransformer):
    """Erase lexical choices while preserving Python control/data-flow shape."""

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Name(id="NAME", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.arg(arg="ARG", annotation=None, type_comment=None), node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        node.name = "FUNCTION"
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # noqa: N802
        node.name = "FUNCTION"
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:  # noqa: N802
        node.name = "CLASS"
        return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:  # noqa: N802
        return ast.copy_location(
            ast.Attribute(value=self.visit(node.value), attr="ATTR", ctx=node.ctx), node
        )

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        kind = type(node.value).__name__
        return ast.copy_location(ast.Constant(value=f"<{kind}>"), node)


def audit_si2_search_causality(
    source_workspace: Path,
    *,
    manifest_digest: str,
    output_workspace: Path,
) -> dict[str, Any]:
    """Diagnose consumed SI-2 traces without model calls or evaluator execution."""

    source_workspace = source_workspace.resolve()
    output_workspace = output_workspace.resolve()
    if output_workspace == source_workspace or source_workspace in output_workspace.parents:
        raise ValueError("autopsy output must remain outside the consumed SI-2 workspace")

    manifest_path = source_workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    report_path = source_workspace / "result-artifacts" / "records" / DISCOVERY_REPORT_RECORD
    manifest = _load_json(manifest_path)
    report = _load_json(report_path)
    manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != manifest_digest or digest_json(manifest_payload) != manifest_digest:
        raise RuntimeError("SI-2 manifest digest mismatch")
    if report.get("manifest_digest") != manifest_digest:
        raise RuntimeError("SI-2 discovery report is not bound to the requested manifest")
    if report.get("search_value_verdict") != "SI2_SEARCH_VALUE_NOT_ESTABLISHED":
        raise RuntimeError("autopsy requires the closed SI-2 search-value result")

    task_rows: list[dict[str, Any]] = []
    source_bindings: list[dict[str, str]] = [
        _binding("analysis_implementation", Path(__file__)),
        _binding("manifest", manifest_path),
        _binding("discovery_report", report_path),
    ]
    aggregate_mechanisms = {
        "parent_policy_invocations": 0,
        "multi_parent_opportunities": 0,
        "non_incumbent_parent_selections": 0,
        "novelty_checks": 0,
        "novelty_rejections": 0,
        "novelty_resample_attempts": 0,
    }

    for task in manifest["cohorts"]["discovery"]:
        task_id = task["task_id"]
        arms: dict[str, Any] = {}
        for arm in INTERNAL_ARMS:
            record_path = source_workspace / "result-artifacts" / "records" / "tasks" / task_id / f"{arm}.json"
            ledger_path = source_workspace / "arms" / "discovery" / task_id / arm / "ledger.sqlite3"
            record = _load_json(record_path)
            if record.get("task_id") != task_id or record.get("arm") != arm:
                raise RuntimeError(f"SI-2 task record identity mismatch: {task_id}:{arm}")
            source_bindings.extend((_binding(f"task_record:{task_id}:{arm}", record_path), _binding(f"ledger:{task_id}:{arm}", ledger_path)))
            arms[arm] = _arm_trace(source_workspace, task_id, arm, record, ledger_path)
            if arm == "CURRENT_DISCOVERYOS":
                for key in aggregate_mechanisms:
                    aggregate_mechanisms[key] += arms[arm]["observed_mechanisms"][key]

        pairwise = {}
        for left, right in (
            ("CURRENT_DISCOVERYOS", "CORE"),
            ("CURRENT_DISCOVERYOS", "VANILLA_STRONG_AGENT"),
            ("CORE", "VANILLA_STRONG_AGENT"),
        ):
            pairwise[f"{left}_vs_{right}"] = _compare_arm_traces(arms[left], arms[right])
        task_rows.append(
            {
                "task_id": task_id,
                "arms": arms,
                "pairwise": pairwise,
                "all_internal_final_improvements_equal": len(
                    {arms[arm]["final_improvement"] for arm in INTERNAL_ARMS}
                ) == 1,
            }
        )

    comparison_names = tuple(task_rows[0]["pairwise"]) if task_rows else ()
    comparisons = {
        name: {
            "tasks": len(task_rows),
            "tasks_with_exact_candidate_overlap": sum(
                row["pairwise"][name]["exact_candidate_overlap_count"] > 0 for row in task_rows
            ),
            "tasks_with_structural_candidate_overlap": sum(
                row["pairwise"][name]["structural_candidate_overlap_count"] > 0 for row in task_rows
            ),
            "identical_evaluation_trajectories": sum(
                row["pairwise"][name]["evaluation_trajectory_equal"] for row in task_rows
            ),
            "median_exact_jaccard": statistics.median(
                row["pairwise"][name]["exact_candidate_jaccard"] for row in task_rows
            ),
            "median_structural_jaccard": statistics.median(
                row["pairwise"][name]["structural_candidate_jaccard"] for row in task_rows
            ),
        }
        for name in comparison_names
    }

    result = {
        "status": "SI2_SEARCH_CAUSALITY_AUTOPSY_COMPLETE",
        "source_protocol": manifest.get("protocol_id"),
        "source_manifest_digest": manifest_digest,
        "source_search_value_verdict": report["search_value_verdict"],
        "claim_ceiling": "CONSUMED_TASK_DIAGNOSTIC_ONLY_NO_SUPERIORITY_CLAIM",
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
        "source_workspace_modified": False,
        "identifiability": {
            "materialized_candidate_exact_divergence": "IDENTIFIABLE",
            "python_ast_structural_divergence": "IDENTIFIABLE_COARSE_PROXY",
            "evaluation_trajectory_divergence": "IDENTIFIABLE",
            "parent_and_novelty_direct_control_flow_intervention": "IDENTIFIABLE",
            "algorithmic_root": "NOT_IDENTIFIABLE_NO_FROZEN_ALGORITHM_CLASSIFIER",
            "cross_arm_behavioral_signature": "NOT_IDENTIFIABLE_NO_PER_INPUT_OUTPUT_TRACE",
            "cross_arm_search_basin": "NOT_IDENTIFIABLE_ARM_SPECIFIC_OR_INHERITED_LABELS",
            "counterfactual_downstream_causal_effect": "NOT_IDENTIFIABLE_NO_PAIRED_COUNTERFACTUAL_GENERATION",
            "memory_injection_effect": "NOT_IDENTIFIABLE_NO_DEDICATED_INTERVENTION_RECEIPT",
        },
        "observed_current_mechanisms": aggregate_mechanisms,
        "candidate_materialization": {
            "candidate_records_excluding_baseline": sum(
                arm["candidate_records_excluding_baseline"]
                for row in task_rows
                for arm in row["arms"].values()
            ),
            "materialized_candidates": sum(
                arm["materialized_candidate_count"]
                for row in task_rows
                for arm in row["arms"].values()
            ),
            "materialization_failures": sum(
                len(arm["materialization_failures"])
                for row in task_rows
                for arm in row["arms"].values()
            ),
        },
        "comparisons": comparisons,
        "all_internal_final_improvements_equal_tasks": sum(
            row["all_internal_final_improvements_equal"] for row in task_rows
        ),
        "task_count": len(task_rows),
        "tasks": task_rows,
        "admission_decision": "DO_NOT_OPEN_SI3_FRESH_BUDGET",
        "required_before_next_fresh_trial": [
            "Freeze intervention receipts that bind invoked policy, default action, chosen action, and immediate control-flow change.",
            "Freeze a cross-arm algorithmic-root and behavioral-signature classifier before candidate generation.",
            "Demonstrate in a mechanics-only sandbox that an intervention changes proposal or basin and has a measurable cost or coverage effect.",
            "Pre-register Adaptive Discovery with STRONG_AGENT_DIRECT as the default operator and explicit escalation triggers.",
        ],
        "source_bindings": source_bindings,
    }
    path = ArtifactStore(output_workspace / "artifacts").write_record(AUTOPSY_RECORD, result)
    return {**result, "record_path": str(path), "record_sha256": digest_bytes(path.read_bytes())}


def _arm_trace(
    source_workspace: Path,
    task_id: str,
    arm: str,
    record: dict[str, Any],
    ledger_path: Path,
) -> dict[str, Any]:
    ledger = EvidenceLedger(ledger_path)
    artifacts = ArtifactStore(source_workspace / "arms" / "discovery" / task_id / arm / "artifacts")
    exact: set[str] = set()
    structural: set[str] = set()
    failures: list[dict[str, str]] = []
    candidates = [
        candidate
        for candidate in ledger.candidate_records()
        if candidate.operator_id != "frozen_baseline"
    ]
    for candidate in candidates:
        try:
            bundle = ExecutableCandidateBundle.from_artifact(artifacts, candidate.artifact_digest)
            source = normalized_source(_materialize_files(bundle, (bundle.entrypoint,))[bundle.entrypoint])
            exact.add(digest_bytes(source.encode("utf-8")))
            structural.add(_structural_digest(source))
        except (OSError, RuntimeError, ValueError, SyntaxError, KeyError) as error:
            failures.append({"candidate_id": candidate.candidate_id, "error": type(error).__name__})

    observed = {
        "parent_policy_invocations": 0,
        "multi_parent_opportunities": 0,
        "non_incumbent_parent_selections": 0,
        "novelty_checks": 0,
        "novelty_rejections": 0,
        "novelty_resample_attempts": 0,
    }
    run_ids = {payload["run_id"] for payload in _table_payloads(ledger_path, "search_runs")}
    for run_id in run_ids:
        parents = ledger.parent_selection_receipt_payloads(run_id)
        novelty = ledger.novelty_receipt_payloads(run_id)
        observed["parent_policy_invocations"] += len(parents)
        observed["multi_parent_opportunities"] += sum(
            int(item.get("eligible_parent_count", 0)) > 1 for item in parents
        )
        observed["non_incumbent_parent_selections"] += sum(
            item.get("selected_is_incumbent") is False for item in parents
        )
        observed["novelty_checks"] += len(novelty)
        observed["novelty_rejections"] += sum(
            item.get("assessment", {}).get("decision") != "ACCEPT" for item in novelty
        )
        observed["novelty_resample_attempts"] += sum(int(item.get("attempt", 1)) > 1 for item in novelty)

    trajectory = [
        {
            "valid": bool(item.get("valid")),
            "feasible": bool(item.get("feasible")),
            "score": item.get("score"),
        }
        for item in record.get("observations", [])
    ]
    return {
        "candidate_records_excluding_baseline": len(candidates),
        "materialized_candidate_count": len(exact),
        "exact_candidate_signatures": sorted(exact),
        "structural_candidate_signatures": sorted(structural),
        "materialization_failures": failures,
        "evaluation_trajectory": trajectory,
        "final_improvement": record["metrics"]["best_improvement"],
        "auc_over_token_budget": record["metrics"]["auc_over_token_budget"],
        "reported_basin_ids": sorted(
            {item["basin_id"] for item in record.get("observations", []) if item.get("basin_id")}
        ),
        "observed_mechanisms": observed,
    }


def _compare_arm_traces(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_exact, right_exact = set(left["exact_candidate_signatures"]), set(right["exact_candidate_signatures"])
    left_struct, right_struct = set(left["structural_candidate_signatures"]), set(right["structural_candidate_signatures"])
    return {
        "exact_candidate_overlap_count": len(left_exact & right_exact),
        "exact_candidate_jaccard": _jaccard(left_exact, right_exact),
        "structural_candidate_overlap_count": len(left_struct & right_struct),
        "structural_candidate_jaccard": _jaccard(left_struct, right_struct),
        "evaluation_trajectory_equal": left["evaluation_trajectory"] == right["evaluation_trajectory"],
    }


def _structural_digest(source: str) -> str:
    tree = _StructuralNormalizer().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return digest_bytes(ast.dump(tree, annotate_fields=True, include_attributes=False).encode("utf-8"))


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required SI-2 artifact missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"SI-2 artifact is not an object: {path}")
    return value


def _binding(role: str, path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"required SI-2 source missing: {path}")
    return {"role": role, "path": str(path.resolve()), "sha256": digest_bytes(path.read_bytes())}


def _table_payloads(path: Path, table: str) -> list[dict[str, Any]]:
    import sqlite3

    with sqlite3.connect(path) as connection:
        rows = connection.execute(f"SELECT payload FROM {table} ORDER BY created_at").fetchall()
    return [json.loads(row[0]) for row in rows]
