from __future__ import annotations

import ast
import itertools
import json
import statistics
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.causal_intervention_bench import (
    BranchTrace,
    FrozenDecisionState,
    InterventionPair,
    InterventionThresholds,
    _pair_receipt,
    evaluate_intervention_pairs,
)
from discoveryos.benchmarks.search_value_mvp0_tasks import (
    SearchValueTask,
    normalized_source,
    search_value_mvp0_tasks,
)
from discoveryos.contracts.models import MetricDirection
from discoveryos.operators.parent_selection import (
    ParentCandidate,
    ParentSelectionConfig,
    ParentSelectionContext,
    ShinkaWeightedParentSelectionPolicy,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CIB_PARENT_INTERVENTION_DEV_V1"
MANIFEST_RECORD = "cib-parent-dev-manifest.json"
REPORT_RECORD = "cib-parent-dev-report.json"
POLICY_CONFIG = ParentSelectionConfig(
    policy_version="shinka_weighted_dos_v2_capped",
    selection_lambda=10.0,
    base_seed=0,
    maximum_selection_probability=0.8,
)
TASK_SPECS = (
    (0, 0, 1),
    (3, 1, 14),
    (6, 1, 18),
)


def seal_parent_dev_cib_protocol(workspace: Path) -> dict[str, Any]:
    """Freeze three consumed development states before running paired probes."""

    thresholds = InterventionThresholds(
        null_replicates=2,
        intervention_replicates=2,
        positive_replicates=2,
        behavioral_margin=0.01,
        utility_margin=0.005,
    )
    tasks = search_value_mvp0_tasks()
    policy = ShinkaWeightedParentSelectionPolicy(POLICY_CONFIG)
    state_rows = []
    for task_index, intermediate_index, seed in TASK_SPECS:
        task = tasks[task_index]
        actions = _actions(task, intermediate_index)
        context = _parent_context(task, actions, seed)
        receipt = policy.select(context)
        selected = receipt.selected_parent_ids[0]
        intervention_action = _action_id(task, "alternative")
        if selected != intervention_action or receipt.selected_is_incumbent:
            raise RuntimeError("frozen parent development state did not select the alternative")
        probe_cases = _extract_cases(task.task.evaluator_source)
        state_payload = {
            "task_payload_digest": task.payload_digest,
            "context_digest": context.digest,
            "actions": actions,
            "probe_cases": probe_cases,
            "downstream_operator": "SEMANTICS_PRESERVING_REPLAY_V1",
        }
        state = FrozenDecisionState(
            state_id=f"parent-dev-{task.task.task_id}",
            state_digest=digest_json(state_payload),
            mechanism_id="SHINKA_WEIGHTED_PARENT_SELECTION",
            policy_id=POLICY_CONFIG.policy_version,
            default_action_id=_action_id(task, "incumbent"),
            intervention_action_id=intervention_action,
            positive_action_id=_action_id(task, "positive"),
            behavioral_probe_digest=digest_json(
                {
                    "task_id": task.task.task_id,
                    "cases": probe_cases,
                    "probe_version": "domain-output-trace-v1",
                }
            ),
            downstream_steps=3,
            token_budget=5000,
            evaluator_call_budget=4,
        )
        state_rows.append(
            {
                "state": jsonable(state),
                "task_id": task.task.task_id,
                "task_category": task.task.category,
                "context": jsonable(context),
                "selection_receipt": jsonable(receipt),
                "actions": actions,
                "probe_cases": probe_cases,
                "task_payload_digest": task.payload_digest,
            }
        )

    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_EXECUTION",
        "scope": "CONSUMED_DEVELOPMENT_TASK_PARENT_CAUSAL_TRACE",
        "claim_ceiling": "DEVELOPMENT_SIGNAL_ONLY_NO_SEARCH_VALUE_CLAIM",
        "model_calls_before_seal": 0,
        "fresh_task_budget_consumed": 0,
        "policy_config": jsonable(POLICY_CONFIG),
        "thresholds": jsonable(thresholds),
        "states": state_rows,
        "implementation_bindings": _implementation_bindings(),
        "downstream_operator": {
            "id": "SEMANTICS_PRESERVING_REPLAY_V1",
            "representative_candidate_model": False,
            "description": (
                "The same deterministic operator replays each selected parent across three descendant "
                "checkpoints without changing its semantics."
            ),
        },
        "not_authorized": [
            "real parent mechanism admission",
            "strong-agent stochastic variance claim",
            "fresh SI-3 budget",
            "DiscoveryOS search-value claim",
        ],
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace.resolve() / "protocol-artifacts").write_record(
        MANIFEST_RECORD, manifest
    )
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "manifest_file_sha256": digest_bytes(path.read_bytes()),
        "model_calls": 0,
        "fresh_task_budget_consumed": 0,
    }


def run_parent_dev_cib(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_manifest(manifest_path, manifest_digest)
    thresholds = InterventionThresholds(**manifest["thresholds"])
    policy = ShinkaWeightedParentSelectionPolicy(POLICY_CONFIG)
    pairs: list[InterventionPair] = []
    replay_rows = []
    for row in manifest["states"]:
        state = FrozenDecisionState(**row["state"])
        context = _context_from_json(row["context"])
        replayed = policy.select(context)
        recorded = row["selection_receipt"]
        replay_valid = all(
            (
                replayed.receipt_id == recorded["receipt_id"],
                list(replayed.selected_parent_ids) == recorded["selected_parent_ids"],
                replayed.context_digest == recorded["context_digest"],
                list(replayed.selection_probabilities) == recorded["selection_probabilities"],
                replayed.selected_is_incumbent is recorded["selected_is_incumbent"],
            )
        )
        if not replay_valid or replayed.selected_parent_ids[0] != state.intervention_action_id:
            raise RuntimeError("parent policy replay does not reproduce the frozen intervention")
        replay_rows.append(
            {
                "state_id": state.state_id,
                "policy_receipt_id": replayed.receipt_id,
                "selected_parent_id": replayed.selected_parent_ids[0],
                "selected_is_incumbent": replayed.selected_is_incumbent,
                "replay_valid": True,
            }
        )
        actions = row["actions"]
        cases = row["probe_cases"]
        for kind, count in (
            ("NULL", thresholds.null_replicates),
            ("INTERVENTION", thresholds.intervention_replicates),
            ("POSITIVE", thresholds.positive_replicates),
        ):
            treatment_action = {
                "NULL": state.default_action_id,
                "INTERVENTION": state.intervention_action_id,
                "POSITIVE": state.positive_action_id,
            }[kind]
            for replicate in range(count):
                pairs.append(
                    InterventionPair(
                        pair_id=f"{state.state_id}-{kind.lower()}-{replicate}",
                        kind=kind,
                        state=state,
                        control=_branch_trace(
                            state,
                            row["task_category"],
                            state.default_action_id,
                            actions[state.default_action_id],
                            cases,
                            f"{kind.lower()}-{replicate}-control",
                        ),
                        treatment=_branch_trace(
                            state,
                            row["task_category"],
                            treatment_action,
                            actions[treatment_action],
                            cases,
                            f"{kind.lower()}-{replicate}-treatment",
                        ),
                    )
                )

    result_store = ArtifactStore(workspace / "result-artifacts")
    pair_bindings = []
    for pair in pairs:
        path = result_store.write_record(f"pairs/{pair.pair_id}.json", _pair_receipt(pair))
        pair_bindings.append(
            {"pair_id": pair.pair_id, "path": str(path), "sha256": digest_bytes(path.read_bytes())}
        )
    analysis = evaluate_intervention_pairs(pairs, thresholds=thresholds)
    detected = analysis["intervention_verdict"] == "INTERVENTION_VALUE_ADMITTED"
    report = {
        "status": "PARENT_CIB_DEVELOPMENT_TRACE_COMPLETE",
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "scope": manifest["scope"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "real_task_evaluator_process_calls": 0,
        "fresh_task_budget_consumed": 0,
        "actual_parent_policy_invoked": True,
        "policy_replay": replay_rows,
        "paired_analysis": analysis,
        "development_signal": (
            "PARENT_VALUE_TRANSMISSION_DETECTED_ON_SEMANTICS_PRESERVING_DEV_REPLAY"
            if detected
            else "PARENT_VALUE_TRANSMISSION_NOT_DETECTED_ON_DEV_REPLAY"
        ),
        "real_parent_mechanism_admitted": False,
        "representative_strong_agent_downstream": False,
        "si3_fresh_budget_decision": "DO_NOT_OPEN_SI3_FRESH_BUDGET",
        "pair_receipts": pair_bindings,
        "source_bindings": [
            {
                "role": "sealed_manifest",
                "path": str(manifest_path),
                "sha256": digest_bytes(manifest_path.read_bytes()),
            },
            *manifest["implementation_bindings"],
        ],
    }
    path = result_store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def _actions(task: SearchValueTask, intermediate_index: int) -> dict[str, str]:
    return {
        _action_id(task, "incumbent"): normalized_source(task.task.algorithm_source),
        _action_id(task, "alternative"): normalized_source(
            task.intermediate_sources[intermediate_index]
        ),
        _action_id(task, "positive"): normalized_source(task.reference_source),
    }


def _action_id(task: SearchValueTask, role: str) -> str:
    return f"{task.task.task_id}:{role}"


def _parent_context(
    task: SearchValueTask, actions: dict[str, str], seed: int
) -> ParentSelectionContext:
    incumbent = _action_id(task, "incumbent")
    alternative = _action_id(task, "alternative")
    return ParentSelectionContext(
        run_id=f"cib-parent-dev:{task.task.task_id}",
        step=0,
        metric_direction=MetricDirection.MAXIMIZE,
        candidates=(
            ParentCandidate(
                candidate_id=alternative,
                fitness=0.80,
                valid=True,
                generation=1,
                parent_exposure_count=0,
                archive=True,
                incumbent=False,
                lineage_root_id=digest_json({"source": actions[alternative]}),
                lineage_ids=(alternative,),
            ),
            ParentCandidate(
                candidate_id=incumbent,
                fitness=0.60,
                valid=True,
                generation=2,
                parent_exposure_count=4,
                archive=True,
                incumbent=True,
                lineage_root_id=digest_json({"source": actions[incumbent]}),
                lineage_ids=(incumbent,),
            ),
        ),
        seed=seed,
        policy_version=POLICY_CONFIG.policy_version,
    )


def _context_from_json(value: dict[str, Any]) -> ParentSelectionContext:
    candidates = []
    for item in value["candidates"]:
        candidates.append(
            ParentCandidate(
                **{
                    **item,
                    "improvement_history": tuple(item["improvement_history"]),
                    "lineage_ids": tuple(item["lineage_ids"]),
                }
            )
        )
    return ParentSelectionContext(
        run_id=value["run_id"],
        step=int(value["step"]),
        metric_direction=MetricDirection(value["metric_direction"]),
        candidates=tuple(candidates),
        seed=int(value["seed"]),
        policy_version=value["policy_version"],
    )


def _branch_trace(
    state: FrozenDecisionState,
    category: str,
    action_id: str,
    source: str,
    cases: list[Any],
    draw_id: str,
) -> BranchTrace:
    behavior, fitness = _evaluate_source(category, source, cases)
    return BranchTrace(
        state_id=state.state_id,
        action_id=action_id,
        draw_id=draw_id,
        proposal_semantics_digest=digest_json({"source": normalized_source(source)}),
        behavioral_signature=behavior,
        immediate_fitness=fitness,
        descendant_best=tuple(fitness for _ in range(state.downstream_steps)),
        anytime_auc=fitness,
        token_cost=len(source.encode("utf-8")),
        evaluator_cost=state.downstream_steps + 1,
    )


def _evaluate_source(
    category: str, source: str, cases: list[Any]
) -> tuple[tuple[float, ...], float]:
    namespace: dict[str, Any] = {}
    exec(compile(normalized_source(source), "<cib-parent-source>", "exec"), namespace)
    if category == "combinatorial_subset_optimization":
        return _knapsack_trace(namespace["select_items"], cases)
    if category == "graph_conflict_optimization":
        return _color_trace(namespace["color_graph"], cases)
    if category == "parallel_load_optimization":
        return _balance_trace(namespace["assign_loads"], cases)
    raise ValueError(f"unsupported parent CIB task category: {category}")


def _knapsack_trace(
    function: Callable[..., Any], cases: list[Any]
) -> tuple[tuple[float, ...], float]:
    behavior: list[float] = []
    scores = []
    for frozen_items, capacity in cases:
        items = list(tuple(item) for item in frozen_items)
        chosen = function(items, capacity)
        if not isinstance(chosen, list) or len(chosen) != len(set(chosen)):
            chosen = []
        valid = all(isinstance(index, int) and 0 <= index < len(items) for index in chosen)
        valid = valid and sum(items[index][0] for index in chosen) <= capacity
        chosen = chosen if valid else []
        behavior.extend(float(index in chosen) for index in range(len(items)))
        value = sum(items[index][1] for index in chosen)
        optimum = max(
            sum(items[index][1] for index in range(len(items)) if mask >> index & 1)
            for mask in range(1 << len(items))
            if sum(items[index][0] for index in range(len(items)) if mask >> index & 1)
            <= capacity
        )
        scores.append(value / optimum)
    return tuple(behavior), statistics.fmean(scores)


def _color_trace(
    function: Callable[..., Any], cases: list[Any]
) -> tuple[tuple[float, ...], float]:
    behavior: list[float] = []
    scores = []
    for node_count, frozen_edges, color_count in cases:
        edges = list(tuple(edge) for edge in frozen_edges)
        colors = function(node_count, edges, color_count)
        valid = isinstance(colors, list) and len(colors) == node_count
        valid = valid and all(isinstance(color, int) and 0 <= color < color_count for color in colors)
        colors = colors if valid else [0] * node_count
        behavior.extend(float(color) / max(1, color_count - 1) for color in colors)
        scores.append(sum(colors[a] != colors[b] for a, b in edges) / len(edges))
    return tuple(behavior), statistics.fmean(scores)


def _balance_trace(
    function: Callable[..., Any], cases: list[Any]
) -> tuple[tuple[float, ...], float]:
    behavior: list[float] = []
    scores = []
    for frozen_weights, machine_count in cases:
        weights = list(frozen_weights)
        assignment = function(weights, machine_count)
        valid = isinstance(assignment, list) and len(assignment) == len(weights)
        valid = valid and all(
            isinstance(machine, int) and 0 <= machine < machine_count for machine in assignment
        )
        assignment = assignment if valid else [0] * len(weights)
        behavior.extend(float(machine) / max(1, machine_count - 1) for machine in assignment)
        loads = [0] * machine_count
        for weight, machine in zip(weights, assignment, strict=True):
            loads[machine] += weight
        actual = max(loads)
        optimum = min(
            max(
                sum(weights[index] for index, chosen in enumerate(candidate) if chosen == machine)
                for machine in range(machine_count)
            )
            for candidate in itertools.product(range(machine_count), repeat=len(weights))
        )
        scores.append(optimum / actual)
    return tuple(behavior), statistics.fmean(scores)


def _extract_cases(evaluator_source: str) -> list[Any]:
    tree = ast.parse(normalized_source(evaluator_source))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CASES" for target in node.targets
        ):
            return jsonable(ast.literal_eval(node.value))
    raise RuntimeError("frozen task evaluator does not define literal CASES")


def _implementation_bindings() -> list[dict[str, str]]:
    import discoveryos.benchmarks.causal_intervention_bench as causal_intervention_bench
    import discoveryos.benchmarks.search_value_mvp0_tasks as task_module
    import discoveryos.operators.parent_selection as parent_selection

    return [
        {
            "role": role,
            "path": str(path.resolve()),
            "sha256": digest_bytes(path.read_bytes()),
        }
        for role, path in (
            ("parent_dev_adapter", Path(__file__)),
            ("cib_core", Path(causal_intervention_bench.__file__)),
            ("parent_policy", Path(parent_selection.__file__)),
            ("consumed_dev_tasks", Path(task_module.__file__)),
        )
    ]


def _load_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"parent CIB manifest missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("sealed parent CIB manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_EXECUTION":
        raise RuntimeError("parent CIB manifest was not sealed before execution")
    current = {item["role"]: item["sha256"] for item in _implementation_bindings()}
    frozen = {item["role"]: item["sha256"] for item in manifest["implementation_bindings"]}
    if current != frozen:
        raise RuntimeError("parent CIB implementation binding drift")
    if manifest.get("model_calls_before_seal") != 0:
        raise RuntimeError("parent CIB violates the no-model pre-seal boundary")
    return manifest
