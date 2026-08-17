from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CAUSAL_INTERVENTION_BENCH_V1"
MANIFEST_RECORD = "cib-synthetic-manifest.json"
REPORT_RECORD = "cib-synthetic-report.json"
PAIR_KINDS = ("NULL", "INTERVENTION", "POSITIVE")


@dataclass(frozen=True)
class InterventionThresholds:
    null_replicates: int = 4
    intervention_replicates: int = 3
    positive_replicates: int = 2
    minimum_validation_states: int = 3
    minimum_reproducible_states: int = 2
    behavioral_margin: float = 0.05
    utility_margin: float = 0.01
    efficiency_margin_tokens: int = 5

    def __post_init__(self) -> None:
        if min(
            self.null_replicates,
            self.intervention_replicates,
            self.positive_replicates,
        ) < 2:
            raise ValueError("every CIB pair kind requires at least two independent replicates")
        if self.minimum_validation_states < 2:
            raise ValueError("CIB requires more than one independent decision state")
        if not 2 <= self.minimum_reproducible_states <= self.minimum_validation_states:
            raise ValueError("minimum reproducible states must be between two and validation state count")
        if min(self.behavioral_margin, self.utility_margin) <= 0:
            raise ValueError("CIB effect margins must be positive")
        if self.efficiency_margin_tokens <= 0:
            raise ValueError("CIB efficiency margin must be positive")


@dataclass(frozen=True)
class FrozenDecisionState:
    state_id: str
    state_digest: str
    mechanism_id: str
    policy_id: str
    default_action_id: str
    intervention_action_id: str
    positive_action_id: str
    behavioral_probe_digest: str
    downstream_steps: int
    token_budget: int
    evaluator_call_budget: int

    def __post_init__(self) -> None:
        if len(self.state_digest) != 64 or len(self.behavioral_probe_digest) != 64:
            raise ValueError("state and behavioral probe digests must be SHA-256 values")
        if len(
            {self.default_action_id, self.intervention_action_id, self.positive_action_id}
        ) != 3:
            raise ValueError("default, intervention, and positive actions must be distinct")
        if self.downstream_steps < 2:
            raise ValueError("CIB must observe beyond the immediate child")
        if self.token_budget <= 0 or self.evaluator_call_budget <= 0:
            raise ValueError("CIB downstream budgets must be positive")


@dataclass(frozen=True)
class BranchTrace:
    state_id: str
    action_id: str
    draw_id: str
    proposal_semantics_digest: str
    behavioral_signature: tuple[float, ...]
    immediate_fitness: float
    descendant_best: tuple[float, ...]
    anytime_auc: float
    token_cost: int
    evaluator_cost: int

    def __post_init__(self) -> None:
        if not self.behavioral_signature:
            raise ValueError("behavioral signature cannot be empty")
        if len(self.proposal_semantics_digest) != 64:
            raise ValueError("proposal semantics digest must be SHA-256")
        if self.token_cost < 0 or self.evaluator_cost < 0:
            raise ValueError("branch costs cannot be negative")


@dataclass(frozen=True)
class InterventionPair:
    pair_id: str
    kind: str
    state: FrozenDecisionState
    control: BranchTrace
    treatment: BranchTrace

    def __post_init__(self) -> None:
        if self.kind not in PAIR_KINDS:
            raise ValueError(f"unsupported CIB pair kind: {self.kind}")
        if self.control.state_id != self.state.state_id or self.treatment.state_id != self.state.state_id:
            raise ValueError("pair branches must bind the frozen decision state")
        if self.control.action_id != self.state.default_action_id:
            raise ValueError("the control branch must use the frozen default action")
        expected = {
            "NULL": self.state.default_action_id,
            "INTERVENTION": self.state.intervention_action_id,
            "POSITIVE": self.state.positive_action_id,
        }[self.kind]
        if self.treatment.action_id != expected:
            raise ValueError("treatment action does not match the frozen pair kind")
        if self.control.draw_id == self.treatment.draw_id:
            raise ValueError("paired branches must use independent stochastic draws")
        if len(self.control.behavioral_signature) != len(self.treatment.behavioral_signature):
            raise ValueError("behavioral signatures must share a frozen shape")
        if len(self.control.descendant_best) != self.state.downstream_steps:
            raise ValueError("control trace does not cover the frozen downstream horizon")
        if len(self.treatment.descendant_best) != self.state.downstream_steps:
            raise ValueError("treatment trace does not cover the frozen downstream horizon")
        for branch in (self.control, self.treatment):
            if branch.token_cost > self.state.token_budget:
                raise ValueError("branch exceeds the frozen token budget")
            if branch.evaluator_cost > self.state.evaluator_call_budget:
                raise ValueError("branch exceeds the frozen evaluator-call budget")


def seal_synthetic_cib_protocol(
    workspace: Path,
    *,
    states: tuple[FrozenDecisionState, ...] | None = None,
    thresholds: InterventionThresholds | None = None,
) -> dict[str, Any]:
    """Freeze the no-model synthetic sensitivity fixture before trace generation."""

    states = states or synthetic_states()
    thresholds = thresholds or InterventionThresholds()
    if len(states) != thresholds.minimum_validation_states:
        raise ValueError("synthetic CIB must freeze exactly the configured validation state count")
    if len({state.state_id for state in states}) != len(states):
        raise ValueError("CIB state ids must be unique")
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_EXECUTION",
        "scope": "SYNTHETIC_MECHANICS_AND_BENCH_SENSITIVITY_ONLY",
        "claim_ceiling": "NO_REAL_MECHANISM_OR_SEARCH_VALUE_CLAIM",
        "model_calls_before_seal": 0,
        "evaluator_calls_before_seal": 0,
        "fresh_task_budget_consumed": 0,
        "protocol_implementation_sha256": digest_bytes(Path(__file__).read_bytes()),
        "states": [jsonable(state) for state in states],
        "thresholds": jsonable(thresholds),
        "controls": {
            "null": "same default action with independent stochastic draws",
            "positive": "deliberately behavior-distinct action used only to establish bench sensitivity",
        },
        "frozen_measurement_order": [
            "proposal_semantics",
            "behavioral_signature",
            "immediate_fitness",
            "descendant_best_of_k",
            "anytime_auc",
            "token_cost",
            "evaluator_cost",
        ],
        "admission_cascade": [
            "intervention_receipt_valid",
            "behavior_exceeds_state_null_envelope",
            "effect_persists_beyond_immediate_child",
            "benefit_appears_in_utility_or_efficiency",
            "effect_reproduces_across_multiple_states",
        ],
        "threshold_source": "PREDECLARED_SYNTHETIC_FIXTURE_NOT_FIT_TO_GENERATED_TRACES",
        "fresh_budget_authorized": False,
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
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
    }


def run_synthetic_cib(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    """Execute the frozen deterministic fixture and emit create-once paired receipts."""

    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_manifest(manifest_path, manifest_digest)
    states = tuple(FrozenDecisionState(**item) for item in manifest["states"])
    thresholds = InterventionThresholds(**manifest["thresholds"])
    pairs = tuple(_synthetic_pairs(states, thresholds))
    result_store = ArtifactStore(workspace / "result-artifacts")
    pair_bindings = []
    for pair in pairs:
        receipt = _pair_receipt(pair)
        path = result_store.write_record(f"pairs/{pair.pair_id}.json", receipt)
        pair_bindings.append(
            {"pair_id": pair.pair_id, "path": str(path), "sha256": digest_bytes(path.read_bytes())}
        )

    analysis = evaluate_intervention_pairs(pairs, thresholds=thresholds)
    report = {
        "status": (
            "CAUSAL_INTERVENTION_BENCH_MECHANICS_READY"
            if analysis["bench_sensitivity_established"]
            else "BENCH_SENSITIVITY_NOT_ESTABLISHED"
        ),
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "scope": manifest["scope"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
        "synthetic_fixture_intervention_verdict": analysis["intervention_verdict"],
        "real_mechanism_admitted": False,
        "si3_fresh_budget_decision": "DO_NOT_OPEN_SI3_FRESH_BUDGET",
        "analysis": analysis,
        "pair_receipts": pair_bindings,
        "source_bindings": [
            {
                "role": "sealed_manifest",
                "path": str(manifest_path),
                "sha256": digest_bytes(manifest_path.read_bytes()),
            },
            {
                "role": "bench_implementation",
                "path": str(Path(__file__).resolve()),
                "sha256": digest_bytes(Path(__file__).read_bytes()),
            },
        ],
    }
    path = result_store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def evaluate_intervention_pairs(
    pairs: Iterable[InterventionPair], *, thresholds: InterventionThresholds
) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for pair in pairs:
        grouped.setdefault(pair.state.state_id, {kind: [] for kind in PAIR_KINDS})[pair.kind].append(
            _pair_effect(pair)
        )
    if len(grouped) != thresholds.minimum_validation_states:
        raise ValueError("CIB pair set does not match the frozen validation state count")

    state_results = []
    for state_id, by_kind in sorted(grouped.items()):
        required = {
            "NULL": thresholds.null_replicates,
            "INTERVENTION": thresholds.intervention_replicates,
            "POSITIVE": thresholds.positive_replicates,
        }
        if any(len(by_kind[kind]) != count for kind, count in required.items()):
            raise ValueError(f"CIB replicate schedule mismatch for state {state_id}")
        null = _null_envelope(by_kind["NULL"])
        intervention = _aggregate_effect(by_kind["INTERVENTION"])
        positive = _aggregate_effect(by_kind["POSITIVE"])
        state_results.append(
            _evaluate_state(state_id, null, intervention, positive, thresholds)
        )

    sensitivity_count = sum(item["positive_control_detected"] for item in state_results)
    behavior_count = sum(item["intervention_behavior_changed"] for item in state_results)
    immediate_count = sum(item["intervention_immediate_effect"] for item in state_results)
    persistence_count = sum(item["intervention_persists"] for item in state_results)
    benefit_count = sum(item["intervention_beneficial"] for item in state_results)
    required = thresholds.minimum_reproducible_states
    sensitivity = sensitivity_count >= required
    if not sensitivity:
        verdict = "BENCH_SENSITIVITY_NOT_ESTABLISHED"
    elif behavior_count < required:
        verdict = "INTERVENTION_NOT_REALIZED"
    elif persistence_count < required:
        verdict = (
            "IMMEDIATE_EFFECT_NOT_TRANSMITTED"
            if immediate_count >= required
            else "BEHAVIOR_CHANGED_UTILITY_EQUIVALENT"
        )
    elif benefit_count < required:
        verdict = "BEHAVIOR_CHANGED_UTILITY_EQUIVALENT"
    else:
        verdict = "INTERVENTION_VALUE_ADMITTED"
    return {
        "bench_sensitivity_established": sensitivity,
        "intervention_verdict": verdict,
        "minimum_reproducible_states": required,
        "positive_control_detected_states": sensitivity_count,
        "intervention_behavior_changed_states": behavior_count,
        "intervention_immediate_effect_states": immediate_count,
        "intervention_persistent_states": persistence_count,
        "intervention_beneficial_states": benefit_count,
        "states": state_results,
    }


def synthetic_states() -> tuple[FrozenDecisionState, ...]:
    probe_digest = digest_json({"probe": "cib-synthetic-behavior-v1"})
    return tuple(
        FrozenDecisionState(
            state_id=f"synthetic-state-{index}",
            state_digest=digest_json({"synthetic_state": index}),
            mechanism_id="SYNTHETIC_PARENT_INTERVENTION_FIXTURE",
            policy_id="synthetic-parent-policy-v1",
            default_action_id=f"parent-incumbent-{index}",
            intervention_action_id=f"parent-alternative-{index}",
            positive_action_id=f"positive-control-{index}",
            behavioral_probe_digest=probe_digest,
            downstream_steps=3,
            token_budget=200,
            evaluator_call_budget=4,
        )
        for index in range(3)
    )


def _synthetic_pairs(
    states: tuple[FrozenDecisionState, ...], thresholds: InterventionThresholds
) -> Iterable[InterventionPair]:
    schedule = (
        ("NULL", thresholds.null_replicates),
        ("INTERVENTION", thresholds.intervention_replicates),
        ("POSITIVE", thresholds.positive_replicates),
    )
    for state_index, state in enumerate(states):
        for kind, count in schedule:
            for replicate in range(count):
                control_draw = f"{kind.lower()}-{replicate}-control"
                treatment_draw = f"{kind.lower()}-{replicate}-treatment"
                treatment_action = {
                    "NULL": state.default_action_id,
                    "INTERVENTION": state.intervention_action_id,
                    "POSITIVE": state.positive_action_id,
                }[kind]
                yield InterventionPair(
                    pair_id=f"{state.state_id}-{kind.lower()}-{replicate}",
                    kind=kind,
                    state=state,
                    control=_synthetic_branch(state, state_index, state.default_action_id, control_draw),
                    treatment=_synthetic_branch(state, state_index, treatment_action, treatment_draw),
                )


def _synthetic_branch(
    state: FrozenDecisionState, state_index: int, action_id: str, draw_id: str
) -> BranchTrace:
    noise_bucket = int(digest_json({"state": state.state_id, "draw": draw_id})[:4], 16) % 9 - 4
    noise = noise_bucket * 0.0005
    base = 0.40 + state_index * 0.02
    if action_id == state.default_action_id:
        behavior_shift, utility_shift = 0.0, 0.0
    elif action_id == state.intervention_action_id:
        behavior_shift, utility_shift = 0.20, 0.06
    else:
        behavior_shift, utility_shift = 0.55, 0.16
    immediate = base + utility_shift * 0.5 + noise
    descendants = tuple(
        immediate + 0.01 * (step + 1) + utility_shift * (step + 1) / state.downstream_steps
        for step in range(state.downstream_steps)
    )
    return BranchTrace(
        state_id=state.state_id,
        action_id=action_id,
        draw_id=draw_id,
        proposal_semantics_digest=digest_json(
            {"action": action_id, "draw": draw_id, "synthetic_semantics": True}
        ),
        behavioral_signature=(
            round(base + behavior_shift + noise, 8),
            round(0.75 - behavior_shift * 0.5 - noise, 8),
        ),
        immediate_fitness=round(immediate, 8),
        descendant_best=tuple(round(value, 8) for value in descendants),
        anytime_auc=round(statistics.fmean(descendants), 8),
        token_cost=100 + abs(noise_bucket) + (5 if utility_shift else 0),
        evaluator_cost=state.downstream_steps + 1,
    )


def _pair_receipt(pair: InterventionPair) -> dict[str, Any]:
    return {
        "receipt_id": digest_json(
            {
                "pair_id": pair.pair_id,
                "state_digest": pair.state.state_digest,
                "control": jsonable(pair.control),
                "treatment": jsonable(pair.treatment),
            }
        ),
        "pair_id": pair.pair_id,
        "kind": pair.kind,
        "policy_invoked": pair.state.policy_id,
        "mechanism_id": pair.state.mechanism_id,
        "frozen_state_digest": pair.state.state_digest,
        "frozen_default_action": pair.state.default_action_id,
        "actual_treatment_action": pair.treatment.action_id,
        "immediate_control_flow_changed": pair.kind != "NULL",
        "independent_stochastic_draws": pair.control.draw_id != pair.treatment.draw_id,
        "behavioral_probe_digest": pair.state.behavioral_probe_digest,
        "identical_downstream_budget": {
            "tokens": pair.state.token_budget,
            "evaluator_calls": pair.state.evaluator_call_budget,
            "steps": pair.state.downstream_steps,
        },
        "control": jsonable(pair.control),
        "treatment": jsonable(pair.treatment),
        "effect": _pair_effect(pair),
    }


def _pair_effect(pair: InterventionPair) -> dict[str, Any]:
    control = pair.control
    treatment = pair.treatment
    return {
        "proposal_semantics_changed": (
            control.proposal_semantics_digest != treatment.proposal_semantics_digest
        ),
        "behavior_distance": math.dist(
            control.behavioral_signature, treatment.behavioral_signature
        ),
        "immediate_fitness_delta": treatment.immediate_fitness - control.immediate_fitness,
        "descendant_final_delta": treatment.descendant_best[-1] - control.descendant_best[-1],
        "anytime_auc_delta": treatment.anytime_auc - control.anytime_auc,
        "token_cost_delta": treatment.token_cost - control.token_cost,
        "evaluator_cost_delta": treatment.evaluator_cost - control.evaluator_cost,
    }


def _null_envelope(effects: list[dict[str, Any]]) -> dict[str, float]:
    return {
        key: max(abs(float(effect[key])) for effect in effects)
        for key in (
            "behavior_distance",
            "immediate_fitness_delta",
            "descendant_final_delta",
            "anytime_auc_delta",
            "token_cost_delta",
            "evaluator_cost_delta",
        )
    }


def _aggregate_effect(effects: list[dict[str, Any]]) -> dict[str, float]:
    keys = (
        "behavior_distance",
        "immediate_fitness_delta",
        "descendant_final_delta",
        "anytime_auc_delta",
        "token_cost_delta",
        "evaluator_cost_delta",
    )
    return {key: statistics.median(float(effect[key]) for effect in effects) for key in keys}


def _evaluate_state(
    state_id: str,
    null: dict[str, float],
    intervention: dict[str, float],
    positive: dict[str, float],
    thresholds: InterventionThresholds,
) -> dict[str, Any]:
    positive_behavior = positive["behavior_distance"] > (
        null["behavior_distance"] + thresholds.behavioral_margin
    )
    # A positive control is a known, deliberately distinct intervention.  Its
    # purpose is sensitivity, so either utility direction is admissible; only
    # the real mechanism is required to improve utility in the positive
    # direction below.
    positive_utility = abs(positive["descendant_final_delta"]) > (
        null["descendant_final_delta"] + thresholds.utility_margin
    )
    behavior_changed = intervention["behavior_distance"] > (
        null["behavior_distance"] + thresholds.behavioral_margin
    )
    immediate_effect = abs(intervention["immediate_fitness_delta"]) > (
        null["immediate_fitness_delta"] + thresholds.utility_margin
    )
    persists = intervention["descendant_final_delta"] > (
        null["descendant_final_delta"] + thresholds.utility_margin
    ) and intervention["anytime_auc_delta"] > (
        null["anytime_auc_delta"] + thresholds.utility_margin
    )
    efficient = intervention["token_cost_delta"] < -(
        null["token_cost_delta"] + thresholds.efficiency_margin_tokens
    )
    beneficial = persists or efficient
    return {
        "state_id": state_id,
        "null_envelope": null,
        "intervention_effect": intervention,
        "positive_control_effect": positive,
        "positive_control_detected": positive_behavior and positive_utility,
        "intervention_behavior_changed": behavior_changed,
        "intervention_immediate_effect": immediate_effect,
        "intervention_persists": persists,
        "intervention_beneficial": beneficial,
    }


def _load_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    import json

    if not path.is_file():
        raise RuntimeError(f"CIB manifest missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("sealed CIB manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_EXECUTION":
        raise RuntimeError("CIB manifest was not sealed before execution")
    if manifest.get("protocol_implementation_sha256") != digest_bytes(Path(__file__).read_bytes()):
        raise RuntimeError("CIB implementation drifted after protocol sealing")
    if manifest.get("model_calls_before_seal") != 0 or manifest.get("fresh_budget_authorized"):
        raise RuntimeError("CIB synthetic protocol violates the no-fresh-budget boundary")
    return manifest
