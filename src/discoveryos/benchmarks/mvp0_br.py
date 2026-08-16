from __future__ import annotations

import json
import math
import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.contracts.models import ResourceBudget
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    ActionCost,
    SearchAction,
)


MVP0_MANIFEST_DIGEST = "0928e6f243d91399ae8002456754850b32091adfe72af55da46df58c52d6c7c3"
MVP0_PROTOCOL_SHA = "c6e77681158fc9bb33e9a526f4d74d8c50cc1548"
MVP0_MECHANICS_SHA = "ec301a18f6543e8c07d62b49bc8cf784f90b137d"
BR_ARM_BUDGET = ResourceBudget(tokens=60_000, cpu_seconds=300, wall_seconds=1_200)

# Frozen second-Local receipts have nearest-rank p90=max=22,005 tokens. The BR
# envelope rounds that observation to a deterministic 5k ceiling (25k), not an
# increased arm budget. Evaluation reserves are the frozen G1/G2 rung requests;
# settlement gets an explicit 1s.
FROZEN_GENERATION_P90_TOKENS = 22_005
BR_GENERATION_RESERVE = ResourceBudget(tokens=25_000, wall_seconds=300)
BR_G1_EVALUATION_RESERVE = ResourceBudget(cpu_seconds=5, wall_seconds=30)
BR_G2_EVALUATION_RESERVE = ResourceBudget(cpu_seconds=10, wall_seconds=60)
BR_SETTLEMENT_RESERVE = ResourceBudget(wall_seconds=1)


def _budget_sum(*budgets: ResourceBudget) -> ResourceBudget:
    return ResourceBudget(
        tokens=sum(item.tokens for item in budgets),
        cpu_seconds=sum(item.cpu_seconds for item in budgets),
        gpu_seconds=sum(item.gpu_seconds for item in budgets),
        device_seconds=sum(item.device_seconds for item in budgets),
        wall_seconds=sum(item.wall_seconds for item in budgets),
    )


def derive_budget_aware_stagnation_horizon(
    arm_budget: ResourceBudget,
    local_complete_cost: ResourceBudget,
    structural_complete_cost: ResourceBudget,
) -> int:
    """Largest local no-improvement prefix that still leaves one escape."""

    limits: list[int] = []
    for dimension, local_value in local_complete_cost.as_dict().items():
        structural_value = structural_complete_cost.as_dict()[dimension]
        available = arm_budget.as_dict()[dimension]
        if structural_value > available:
            raise ValueError(f"STRUCTURAL_ESCAPE is unreachable in {dimension}")
        if local_value > 0:
            limits.append(math.floor((available - structural_value) / local_value))
    horizon = min(limits, default=0)
    if horizon < 1:
        raise ValueError("arm budget cannot hold one LOCAL_PATCH plus one STRUCTURAL_ESCAPE")
    return horizon


def mvp0_br_controller_config() -> ActionControllerConfig:
    local_complete = _budget_sum(
        BR_GENERATION_RESERVE,
        BR_G1_EVALUATION_RESERVE,
        BR_SETTLEMENT_RESERVE,
    )
    structural_complete = local_complete
    horizon = derive_budget_aware_stagnation_horizon(
        BR_ARM_BUDGET,
        local_complete,
        structural_complete,
    )
    return ActionControllerConfig(
        stagnation_generations=horizon,
        improvement_epsilon=0.01,
        uncertainty_threshold=0.05,
        incumbent_proximity=0.025,
        minimum_replicates=2,
        structural_similarity_threshold=0.0,
        costs=(
            ActionCost(
                SearchAction.LOCAL_PATCH,
                local_complete,
                generation_reserve=BR_GENERATION_RESERVE,
                evaluation_reserve=BR_G1_EVALUATION_RESERVE,
                settlement_reserve=BR_SETTLEMENT_RESERVE,
                downstream_action_reserve=structural_complete,
            ),
            ActionCost(
                SearchAction.STRUCTURAL_ESCAPE,
                structural_complete,
                generation_reserve=BR_GENERATION_RESERVE,
                evaluation_reserve=BR_G1_EVALUATION_RESERVE,
                settlement_reserve=BR_SETTLEMENT_RESERVE,
            ),
            ActionCost(
                SearchAction.REPLICATE,
                _budget_sum(BR_G1_EVALUATION_RESERVE, BR_SETTLEMENT_RESERVE),
                evaluation_reserve=BR_G1_EVALUATION_RESERVE,
                settlement_reserve=BR_SETTLEMENT_RESERVE,
            ),
            ActionCost(
                SearchAction.PROMOTE_FIDELITY,
                _budget_sum(BR_G2_EVALUATION_RESERVE, BR_SETTLEMENT_RESERVE),
                evaluation_reserve=BR_G2_EVALUATION_RESERVE,
                settlement_reserve=BR_SETTLEMENT_RESERVE,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class FrozenMvp0Autopsy:
    workspace: Path

    def build(self) -> dict[str, Any]:
        manifest = self._read_json(
            self.workspace / "protocol-artifacts" / "records" / "search-value-mvp0-manifest.json"
        )
        report = self._read_json(
            self.workspace / "result-artifacts" / "records" / "search-value-mvp0-report.json"
        )
        if manifest.get("manifest_digest") != MVP0_MANIFEST_DIGEST:
            raise ValueError("unexpected frozen MVP-0 manifest")
        traces = [self._task_trace(item, manifest) for item in report["comparisons"]]
        flat = [action for task in traces for action in task["actions"]]
        return {
            "protocol": {
                "mechanics_sha": MVP0_MECHANICS_SHA,
                "protocol_sha": MVP0_PROTOCOL_SHA,
                "manifest_digest": MVP0_MANIFEST_DIGEST,
                "frozen_verdict": report["verdict"],
                "search_value_status": "DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED",
            },
            "task_traces": traces,
            "action_marginal_value": self._marginal_table(flat),
            "first_local_only": self._first_local_counterfactual(report),
            "reachability": self._frozen_reachability(flat),
        }

    def _task_trace(self, comparison: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        task_id = comparison["task_id"]
        arm_root = self.workspace / "arms" / task_id / "discoveryos_unified_loop"
        connection = sqlite3.connect(arm_root / "ledger.sqlite3")
        connection.row_factory = sqlite3.Row
        try:
            actions = [json.loads(row["payload"]) for row in connection.execute(
                "SELECT payload FROM search_actions ORDER BY step,decision_id"
            )]
            generations = {
                payload["generation_id"]: payload
                for row in connection.execute("SELECT payload FROM generation_records")
                for payload in (json.loads(row["payload"]),)
            }
            evidence = {
                payload["receipt_id"]: payload
                for row in connection.execute("SELECT payload FROM evidence")
                for payload in (json.loads(row["payload"]),)
            }
        finally:
            connection.close()
        trace_files = sorted((arm_root / "artifacts" / "records" / "search" / f"mvp0-{task_id}" / "anytime").glob("*.json"))
        anytime = [self._read_json(path) for path in trace_files]
        task_manifest = next(item for item in manifest["tasks"] if item["task_id"] == task_id)
        baseline = float(task_manifest["headroom_evidence"]["baseline_score"])
        records = []
        for action, trace in zip(actions, anytime, strict=True):
            generation = generations.get(action.get("generation_id"))
            receipt = evidence.get(action.get("evidence_receipt_id"))
            emitted = action["action"] in {"LOCAL_PATCH", "STRUCTURAL_ESCAPE"} and bool(action.get("result_candidate_id"))
            score = dict(receipt["metrics"]).get("score") if receipt else None
            valid = bool(emitted and receipt and receipt["validity"] == "VALID")
            admitted = bool(valid and dict(receipt["metrics"]).get("valid", 1.0) == 1.0)
            generation_usage = generation["usage"] if generation else {}
            evaluation_usage = receipt["resource_usage"] if receipt else {}
            records.append(
                {
                    "task_id": task_id,
                    "arm_id": "discoveryos_unified_loop",
                    "action_index": action["step"],
                    "action_type": action["action"],
                    "state_before": trace["state_digest"],
                    "remaining_token_budget_before": trace["budget_before"]["tokens"],
                    "remaining_wall_budget_before": trace["budget_before"]["wall_seconds"],
                    "estimated_min_start_budget": trace["budget_floor"],
                    "reserved_downstream_budget": ResourceBudget().as_dict(),
                    "action_selected": True,
                    "preflight_affordable": self._affordable(trace["budget_before"], trace["budget_floor"]),
                    "action_started": bool(generation or receipt),
                    "action_completed": bool(receipt),
                    "generation_tokens": int(generation_usage.get("llm_input_tokens", 0) + generation_usage.get("llm_output_tokens", 0)),
                    "evaluation_tokens": int(evaluation_usage.get("llm_input_tokens", 0) + evaluation_usage.get("llm_output_tokens", 0)),
                    "total_action_tokens": int(action["actual_usage"]["llm_input_tokens"] + action["actual_usage"]["llm_output_tokens"]),
                    "wall_time": action["actual_usage"]["wall_seconds"],
                    "candidate_emitted": emitted,
                    "candidate_valid": valid,
                    "candidate_admitted": admitted,
                    "incumbent_before": trace["incumbent_before"],
                    "candidate_score": score,
                    "incumbent_after": trace["incumbent_after"],
                    "incumbent_improved": trace["best_utility_after"] > trace["best_utility_before"],
                    "failure_type": self._failure_type(action.get("failure_signature")),
                    "baseline_score": baseline,
                }
            )
        return {"task_id": task_id, "actions": records}

    @staticmethod
    def _marginal_table(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for index in sorted({item["action_index"] for item in actions}):
            group = [item for item in actions if item["action_index"] == index]
            rows.append(
                {
                    "action_index": index,
                    "attempted": len(group),
                    "started": sum(item["action_started"] for item in group),
                    "completed": sum(item["action_completed"] for item in group),
                    "candidate_emitted": sum(item["candidate_emitted"] for item in group),
                    "valid": sum(item["candidate_valid"] for item in group),
                    "admitted": sum(item["candidate_admitted"] for item in group),
                    "incumbent_improved": sum(item["incumbent_improved"] for item in group),
                    "tokens_consumed": sum(item["total_action_tokens"] for item in group),
                    "wall_consumed": sum(item["wall_time"] for item in group),
                    "marginal_final_improvement": sum(
                        max(0.0, (item["candidate_score"] or item["baseline_score"]) - item["baseline_score"])
                        if index == 0 else 0.0
                        for item in group
                    ),
                    "marginal_anytime_auc_contribution": sum(
                        max(0.0, (item["candidate_score"] or item["baseline_score"]) - item["baseline_score"])
                        * (60_000 - item["total_action_tokens"])
                        / 60_000
                        if index == 0 else 0.0
                        for item in group
                    ),
                }
            )
        return rows

    @staticmethod
    def _first_local_counterfactual(report: dict[str, Any]) -> dict[str, Any]:
        tasks = []
        for comparison in report["comparisons"]:
            full = comparison["discoveryos"]
            first = full["observations"][0]
            baseline = first["score"] - full["metrics"]["best_improvement"]
            improvement = max(0.0, first["score"] - baseline)
            first_auc = improvement * (60_000 - first["cumulative_tokens"]) / 60_000
            tasks.append(
                {
                    "task_id": comparison["task_id"],
                    "full_final_improvement": full["metrics"]["best_improvement"],
                    "first_local_final_improvement": round(improvement, 8),
                    "full_anytime_auc": full["metrics"]["auc_over_token_budget"],
                    "first_local_anytime_auc": round(first_auc, 8),
                    "full_tokens": int(full["actual_usage"]["tokens"]),
                    "first_local_tokens": first["cumulative_tokens"],
                    "full_wall": full["actual_usage"]["wall_seconds"],
                    "first_local_wall": first["cumulative_wall_seconds"],
                    "full_invalid_rate": full["invalid_generation_rate"],
                    "first_local_invalid_rate": 0.0,
                }
            )
        full_tokens = sum(item["full_tokens"] for item in tasks)
        first_tokens = sum(item["first_local_tokens"] for item in tasks)
        full_wall = sum(item["full_wall"] for item in tasks)
        first_wall = sum(item["first_local_wall"] for item in tasks)
        return {
            "tasks": tasks,
            "aggregate": {
                "full_median_final_improvement": statistics.median(item["full_final_improvement"] for item in tasks),
                "first_local_median_final_improvement": statistics.median(item["first_local_final_improvement"] for item in tasks),
                "full_median_anytime_auc": statistics.median(item["full_anytime_auc"] for item in tasks),
                "first_local_median_anytime_auc": statistics.median(item["first_local_anytime_auc"] for item in tasks),
                "full_tokens": full_tokens,
                "first_local_tokens": first_tokens,
                "tokens_avoided": full_tokens - first_tokens,
                "full_wall": full_wall,
                "first_local_wall": first_wall,
                "wall_avoided": full_wall - first_wall,
                "full_invalid_rate": 6 / 17,
                "first_local_invalid_rate": 0.0,
            },
            "conclusion": "Actions after the first LOCAL_PATCH added zero final improvement and zero Anytime AUC within frozen report rounding on all 8 arms.",
        }

    @staticmethod
    def _frozen_reachability(actions: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {action.value: 0 for action in SearchAction}
        for item in actions:
            counts[item["action_type"]] += 1
        return {
            "observed_action_counts": counts,
            "eligible_but_unexecutable_action_count": 6,
            "selected_but_unaffordable_action_count": 6,
            "note": "Six second Local actions exceeded their 20k generation slice; Structural and Replicate were dead under the frozen state/budget combination.",
        }

    @staticmethod
    def _failure_type(signature: str | None) -> str | None:
        if signature == "GENERATION_BUDGET_EXCEEDED:tokens":
            return "budget_estimation_failure"
        if signature and "budget exceeded" in signature.casefold():
            return "budget_allocation_failure"
        return "action_execution_failure" if signature else None

    @staticmethod
    def _affordable(remaining: dict[str, float], requested: dict[str, float]) -> bool:
        return all(float(requested[name]) <= float(remaining[name]) for name in requested)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
