from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "GENERATOR_CONDITIONING_FIDELITY_V1"
MANIFEST_RECORD = "gcf-synthetic-manifest.json"
REPORT_RECORD = "gcf-synthetic-report.json"
CHANNELS = ("PARENT_SOURCE", "FAILURE_EVIDENCE", "MECHANISM_BRIEF")
STAGES = ("PROPOSAL", "IMPLEMENTATION", "REPAIR", "FINAL")
PAIR_KINDS = ("NULL", "INTERVENTION", "POSITIVE")


def parent_cib_r1_settlement() -> dict[str, Any]:
    """Return the narrow, machine-readable settlement implied by CIB-R1."""

    payload = {
        "settlement_id": "PARENT_CIB_R1_GENERATION_REGIME_SETTLEMENT_V1",
        "status": "CAUSALLY_INERT_IN_CURRENT_REAL_GENERATION_REGIME",
        "scope": {
            "mechanism": "CURRENT_PARENT_POLICY",
            "prompt_context_binding": "CIB_R1_FROZEN_BINDING",
            "generator": "THREE_STEP_BATCHED_STOCHASTIC_GENERATOR",
            "model_configuration": "CIB_R1_FROZEN_MODEL_CONFIG",
            "evaluation_surface": "CONSUMED_VALIDATION_STATES",
        },
        "scientific_decision": "NOT_ADMITTED",
        "budget_decision": "CLOSED",
        "differentiation_claim": "WITHDRAWN",
        "capabilities_retained": [
            "PARENT_IMPLEMENTATION",
            "PARENT_LINEAGE",
            "HISTORICAL_CONTROL_FLOW_RECEIPTS",
        ],
        "prohibited_retries": [
            "ADD_SEEDS_ON_SAME_CONSUMED_SURFACE",
            "RETUNE_PARENT_PROBABILITY_CAP",
            "CHANGE_MARGIN_AFTER_OBSERVING_RESULTS",
            "PROMPT_TUNING_TO_RECOVER_POSITIVE_RESULT",
            "REINTERPRET_TIES_AS_WEAK_POSITIVE_SIGNAL",
        ],
        "reopen_condition": {
            "all_required": [
                "NEW_VERSIONED_GENERATION_OR_INHERITANCE_CONTRACT",
                "NEW_HYPOTHESIS",
                "NEW_CALIBRATION",
                "INDEPENDENT_CIB_ADMISSION",
            ]
        },
        "evidence_binding": {
            "protocol_id": "CIB_R1_REAL_DOWNSTREAM_PARENT_V1",
            "manifest_digest": "f14902c185470fb9fcb71bf28a7eb4a3c9562d4109db742d9147f47112fc0b4e",
            "report_sha256": "7fbd3db909dc5d8da11bca9d12f164e0f0cb520333cf9aab012945d7afe74f72",
            "validation_behavioral_states": "0/3",
            "validation_beneficial_states": "0/3",
            "final_descendant_pairs": "0 positive / 9 tie / 0 negative",
        },
        "claim_ceiling": (
            "BUDGET_AND_GOVERNANCE_DECISION_FOR_THE_FROZEN_GENERATION_CONTRACT; "
            "NOT_A_UNIVERSAL_ZERO_EFFECT_CLAIM_ABOUT_PARENT_MECHANISMS"
        ),
        "fresh_budget_decision": "DO_NOT_OPEN_SI3_FRESH_BUDGET",
    }
    return {**payload, "settlement_digest": digest_json(payload)}


@dataclass(frozen=True, slots=True)
class ConditioningThresholds:
    null_replicates: int = 2
    intervention_replicates: int = 2
    positive_replicates: int = 2
    minimum_reproducible_states: int = 2
    stage_margin: float = 0.05
    behavior_margin: float = 0.05
    utility_margin: float = 0.01

    def __post_init__(self) -> None:
        if min(self.null_replicates, self.intervention_replicates, self.positive_replicates) < 2:
            raise ValueError("GCF requires at least two independent pairs of every kind")
        if self.minimum_reproducible_states < 2:
            raise ValueError("GCF transmission requires multiple independent states")
        if min(self.stage_margin, self.behavior_margin, self.utility_margin) <= 0:
            raise ValueError("GCF margins must be positive")


@dataclass(frozen=True, slots=True)
class FrozenConditioningState:
    state_id: str
    state_digest: str
    channel: str
    baseline_condition_id: str
    intervention_condition_id: str
    positive_condition_id: str
    stage_probe_digest: str
    behavior_probe_digest: str
    utility_evaluator_digest: str

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f"unsupported conditioning channel: {self.channel}")
        if any(len(value) != 64 for value in (
            self.state_digest,
            self.stage_probe_digest,
            self.behavior_probe_digest,
            self.utility_evaluator_digest,
        )):
            raise ValueError("GCF state and probe bindings must be SHA-256 values")
        if len({self.baseline_condition_id, self.intervention_condition_id, self.positive_condition_id}) != 3:
            raise ValueError("GCF baseline, intervention, and positive conditions must be distinct")


@dataclass(frozen=True, slots=True)
class ConditioningTrace:
    state_id: str
    condition_id: str
    draw_id: str
    stage_signatures: tuple[tuple[str, tuple[float, ...]], ...]
    behavior_signature: tuple[float, ...]
    utility: float

    def __post_init__(self) -> None:
        if tuple(stage for stage, _ in self.stage_signatures) != STAGES:
            raise ValueError("GCF trace must bind every stage in frozen order")
        if any(not signature for _, signature in self.stage_signatures):
            raise ValueError("GCF stage signatures cannot be empty")
        if not self.behavior_signature:
            raise ValueError("GCF behavior signature cannot be empty")


@dataclass(frozen=True, slots=True)
class ConditioningPair:
    pair_id: str
    kind: str
    state: FrozenConditioningState
    control: ConditioningTrace
    treatment: ConditioningTrace

    def __post_init__(self) -> None:
        if self.kind not in PAIR_KINDS:
            raise ValueError(f"unsupported GCF pair kind: {self.kind}")
        if self.control.state_id != self.state.state_id or self.treatment.state_id != self.state.state_id:
            raise ValueError("GCF pair branches must bind the frozen state")
        if self.control.condition_id != self.state.baseline_condition_id:
            raise ValueError("GCF control must use the baseline condition")
        expected = {
            "NULL": self.state.baseline_condition_id,
            "INTERVENTION": self.state.intervention_condition_id,
            "POSITIVE": self.state.positive_condition_id,
        }[self.kind]
        if self.treatment.condition_id != expected:
            raise ValueError("GCF treatment does not match its pair kind")
        if self.control.draw_id == self.treatment.draw_id:
            raise ValueError("GCF paired traces require independent stochastic draws")
        for (_, control), (_, treatment) in zip(
            self.control.stage_signatures, self.treatment.stage_signatures, strict=True
        ):
            if len(control) != len(treatment):
                raise ValueError("GCF stage signatures must have frozen shapes")
        if len(self.control.behavior_signature) != len(self.treatment.behavior_signature):
            raise ValueError("GCF behavior signatures must have a frozen shape")


def seal_synthetic_gcf_protocol(
    workspace: Path,
    *,
    states: tuple[FrozenConditioningState, ...] | None = None,
    thresholds: ConditioningThresholds | None = None,
) -> dict[str, Any]:
    """Freeze a no-model fixture that calibrates the GCF decision cascade."""

    states = states or synthetic_conditioning_states()
    thresholds = thresholds or ConditioningThresholds()
    counts = {channel: sum(state.channel == channel for state in states) for channel in CHANNELS}
    if any(count != thresholds.minimum_reproducible_states for count in counts.values()):
        raise ValueError("synthetic GCF requires the frozen state count for every channel")
    if len({state.state_id for state in states}) != len(states):
        raise ValueError("GCF state ids must be unique")
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_EXECUTION",
        "scope": "SYNTHETIC_IDENTIFIABILITY_AND_GATE_CALIBRATION_ONLY",
        "claim_ceiling": "NO_REAL_CHANNEL_TRANSMISSION_OR_SEARCH_VALUE_CLAIM",
        "fresh_task_budget_consumed": 0,
        "model_calls_before_seal": 0,
        "protocol_implementation_sha256": digest_bytes(Path(__file__).read_bytes()),
        "channels": list(CHANNELS),
        "stages": list(STAGES),
        "states": [jsonable(state) for state in states],
        "thresholds": jsonable(thresholds),
        "single_variable_intervention": True,
        "controls": {
            "null": "same condition with independent draws",
            "positive": "preconstructed detectable semantic signal used only for GCF-0 sensitivity",
        },
        "gates": [
            "GCF_0_CALIBRATION",
            "GCF_1_STAGEWISE_DETECTABILITY",
            "GCF_2_SEMANTIC_TRANSMISSION",
            "GCF_3_DOWNSTREAM_CAUSAL_VALUE_ELIGIBILITY",
        ],
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
        "fresh_task_budget_consumed": 0,
    }


def run_synthetic_gcf(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_manifest(manifest_path, manifest_digest)
    states = tuple(FrozenConditioningState(**item) for item in manifest["states"])
    thresholds = ConditioningThresholds(**manifest["thresholds"])
    pairs = tuple(_synthetic_pairs(states, thresholds))
    store = ArtifactStore(workspace / "result-artifacts")
    receipts = []
    for pair in pairs:
        receipt = _pair_receipt(pair)
        path = store.write_record(f"pairs/{pair.pair_id}.json", receipt)
        receipts.append({"pair_id": pair.pair_id, "path": str(path), "sha256": digest_bytes(path.read_bytes())})
    analysis = evaluate_conditioning_pairs(pairs, thresholds=thresholds)
    report = {
        "status": (
            "GENERATOR_CONDITIONING_FIDELITY_BENCH_MECHANICS_READY"
            if analysis["gcf_0_calibration_passed"]
            else "GCF_CALIBRATION_NOT_ESTABLISHED"
        ),
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "scope": manifest["scope"],
        "claim_ceiling": manifest["claim_ceiling"],
        "model_calls": 0,
        "fresh_task_budget_consumed": 0,
        "real_channels_admitted": [],
        "fresh_downstream_trial_authorized": False,
        "analysis": analysis,
        "pair_receipts": receipts,
        "source_bindings": [
            {"role": "sealed_manifest", "path": str(manifest_path), "sha256": digest_bytes(manifest_path.read_bytes())},
            {"role": "bench_implementation", "path": str(Path(__file__).resolve()), "sha256": digest_bytes(Path(__file__).read_bytes())},
        ],
    }
    path = store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def evaluate_conditioning_pairs(
    pairs: Iterable[ConditioningPair], *, thresholds: ConditioningThresholds
) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    for pair in pairs:
        grouped.setdefault(pair.state.channel, {}).setdefault(
            pair.state.state_id, {kind: [] for kind in PAIR_KINDS}
        )[pair.kind].append(_pair_effect(pair))

    channel_results = []
    for channel in CHANNELS:
        states = grouped.get(channel, {})
        if len(states) != thresholds.minimum_reproducible_states:
            raise ValueError(f"GCF state schedule mismatch for channel {channel}")
        state_results = []
        for state_id, by_kind in sorted(states.items()):
            required = {
                "NULL": thresholds.null_replicates,
                "INTERVENTION": thresholds.intervention_replicates,
                "POSITIVE": thresholds.positive_replicates,
            }
            if any(len(by_kind[kind]) != count for kind, count in required.items()):
                raise ValueError(f"GCF replicate schedule mismatch for state {state_id}")
            state_results.append(_evaluate_state(state_id, by_kind, thresholds))
        channel_results.append(_evaluate_channel(channel, state_results, thresholds))

    calibrated = all(item["gcf_0_calibration_passed"] for item in channel_results)
    return {
        "gcf_0_calibration_passed": calibrated,
        "condition_survival_curve": {
            item["channel"]: item["detectable_states_by_stage"] for item in channel_results
        },
        "channels": channel_results,
        "decision_boundary": (
            "GCF-2 admission only authorizes a separately preregistered GCF-3 causal-value trial; "
            "it does not establish search value"
        ),
    }


def synthetic_conditioning_states() -> tuple[FrozenConditioningState, ...]:
    states = []
    for channel in CHANNELS:
        for index in range(2):
            states.append(
                FrozenConditioningState(
                    state_id=f"synthetic-{channel.casefold().replace('_', '-')}-{index}",
                    state_digest=digest_json({"channel": channel, "state": index}),
                    channel=channel,
                    baseline_condition_id=f"{channel}-BASE-{index}",
                    intervention_condition_id=f"{channel}-INTERVENTION-{index}",
                    positive_condition_id=f"{channel}-POSITIVE-{index}",
                    stage_probe_digest=digest_json({"probe": "stage", "channel": channel, "version": 1}),
                    behavior_probe_digest=digest_json({"probe": "behavior", "channel": channel, "version": 1}),
                    utility_evaluator_digest=digest_json({"evaluator": "synthetic-utility-v1"}),
                )
            )
    return tuple(states)


def _synthetic_pairs(
    states: tuple[FrozenConditioningState, ...], thresholds: ConditioningThresholds
) -> Iterable[ConditioningPair]:
    schedule = (
        ("NULL", thresholds.null_replicates),
        ("INTERVENTION", thresholds.intervention_replicates),
        ("POSITIVE", thresholds.positive_replicates),
    )
    for state in states:
        for kind, count in schedule:
            for replicate in range(count):
                treatment_condition = {
                    "NULL": state.baseline_condition_id,
                    "INTERVENTION": state.intervention_condition_id,
                    "POSITIVE": state.positive_condition_id,
                }[kind]
                yield ConditioningPair(
                    pair_id=f"{state.state_id}-{kind.casefold()}-{replicate}",
                    kind=kind,
                    state=state,
                    control=_synthetic_trace(state, state.baseline_condition_id, f"{kind}-{replicate}-control"),
                    treatment=_synthetic_trace(state, treatment_condition, f"{kind}-{replicate}-treatment"),
                )


def _synthetic_trace(
    state: FrozenConditioningState, condition_id: str, draw_id: str
) -> ConditioningTrace:
    noise = ((int(digest_json({"state": state.state_id, "draw": draw_id})[:4], 16) % 7) - 3) * 0.001
    is_intervention = condition_id == state.intervention_condition_id
    is_positive = condition_id == state.positive_condition_id
    if is_positive:
        stage_shifts = (0.7, 0.65, 0.6, 0.55)
        behavior_shift, utility_shift = 0.5, 0.15
    elif not is_intervention:
        stage_shifts = (0.0, 0.0, 0.0, 0.0)
        behavior_shift, utility_shift = 0.0, 0.0
    elif state.channel == "PARENT_SOURCE":
        stage_shifts = (0.35, 0.25, 0.18, 0.12)
        behavior_shift, utility_shift = 0.0, 0.0
    elif state.channel == "FAILURE_EVIDENCE":
        stage_shifts = (0.35, 0.3, 0.25, 0.2)
        behavior_shift, utility_shift = 0.22, 0.0
    else:
        stage_shifts = (0.4, 0.38, 0.34, 0.3)
        behavior_shift, utility_shift = 0.28, 0.06
    return ConditioningTrace(
        state_id=state.state_id,
        condition_id=condition_id,
        draw_id=draw_id,
        stage_signatures=tuple(
            (stage, (round(0.2 + shift + noise, 8), round(0.8 - shift - noise, 8)))
            for stage, shift in zip(STAGES, stage_shifts, strict=True)
        ),
        behavior_signature=(round(0.3 + behavior_shift + noise, 8), round(0.7 - behavior_shift - noise, 8)),
        utility=round(0.5 + utility_shift + noise, 8),
    )


def _pair_effect(pair: ConditioningPair) -> dict[str, Any]:
    return {
        "stage_distance": {
            stage: math.dist(control, treatment)
            for (stage, control), (_, treatment) in zip(
                pair.control.stage_signatures, pair.treatment.stage_signatures, strict=True
            )
        },
        "behavior_distance": math.dist(
            pair.control.behavior_signature, pair.treatment.behavior_signature
        ),
        "utility_delta": pair.treatment.utility - pair.control.utility,
    }


def _pair_receipt(pair: ConditioningPair) -> dict[str, Any]:
    body = {
        "pair_id": pair.pair_id,
        "kind": pair.kind,
        "channel": pair.state.channel,
        "state_digest": pair.state.state_digest,
        "single_variable_intervention": pair.kind != "NULL",
        "independent_stochastic_draws": pair.control.draw_id != pair.treatment.draw_id,
        "probe_bindings": {
            "stage": pair.state.stage_probe_digest,
            "behavior": pair.state.behavior_probe_digest,
            "utility": pair.state.utility_evaluator_digest,
        },
        "control": jsonable(pair.control),
        "treatment": jsonable(pair.treatment),
        "effect": _pair_effect(pair),
    }
    return {"receipt_id": digest_json(body), **body}


def _evaluate_state(
    state_id: str,
    by_kind: dict[str, list[dict[str, Any]]],
    thresholds: ConditioningThresholds,
) -> dict[str, Any]:
    null_stage = {
        stage: max(effect["stage_distance"][stage] for effect in by_kind["NULL"])
        for stage in STAGES
    }
    null_behavior = max(effect["behavior_distance"] for effect in by_kind["NULL"])
    null_utility = max(abs(effect["utility_delta"]) for effect in by_kind["NULL"])

    def aggregate(kind: str) -> dict[str, Any]:
        effects = by_kind[kind]
        return {
            "stage_distance": {
                stage: statistics.median(effect["stage_distance"][stage] for effect in effects)
                for stage in STAGES
            },
            "behavior_distance": statistics.median(effect["behavior_distance"] for effect in effects),
            "utility_delta": statistics.median(effect["utility_delta"] for effect in effects),
        }

    intervention = aggregate("INTERVENTION")
    positive = aggregate("POSITIVE")
    detectable = {
        stage: intervention["stage_distance"][stage] > null_stage[stage] + thresholds.stage_margin
        for stage in STAGES
    }
    positive_detected = all(
        positive["stage_distance"][stage] > null_stage[stage] + thresholds.stage_margin
        for stage in STAGES
    ) and positive["behavior_distance"] > null_behavior + thresholds.behavior_margin
    behavior_changed = intervention["behavior_distance"] > null_behavior + thresholds.behavior_margin
    utility_improved = intervention["utility_delta"] > null_utility + thresholds.utility_margin
    return {
        "state_id": state_id,
        "null_envelope": {
            "stage_distance": null_stage,
            "behavior_distance": null_behavior,
            "utility_delta_abs": null_utility,
        },
        "intervention_effect": intervention,
        "positive_control_effect": positive,
        "positive_control_detected": positive_detected,
        "stage_detectable": detectable,
        "behavior_changed": behavior_changed,
        "utility_improved": utility_improved,
    }


def _evaluate_channel(
    channel: str,
    states: list[dict[str, Any]],
    thresholds: ConditioningThresholds,
) -> dict[str, Any]:
    required = thresholds.minimum_reproducible_states
    positive_count = sum(state["positive_control_detected"] for state in states)
    stage_counts = {
        stage: sum(state["stage_detectable"][stage] for state in states) for stage in STAGES
    }
    behavior_count = sum(state["behavior_changed"] for state in states)
    utility_count = sum(state["utility_improved"] for state in states)
    calibrated = positive_count >= required
    stagewise = calibrated and all(stage_counts[stage] >= required for stage in STAGES)
    semantic = stagewise and behavior_count >= required
    value = semantic and utility_count >= required
    if not calibrated:
        verdict = "GCF_CALIBRATION_NOT_ESTABLISHED"
    elif stage_counts["PROPOSAL"] < required:
        verdict = "CONDITION_NOT_DETECTABLE_AT_PROPOSAL"
    elif stage_counts["IMPLEMENTATION"] < required:
        verdict = "PROPOSAL_TO_IMPLEMENTATION_TRANSMISSION_FAILED"
    elif stage_counts["REPAIR"] < required:
        verdict = "REPAIR_HOMOGENIZATION_DETECTED"
    elif stage_counts["FINAL"] < required:
        verdict = "FINAL_CONDITION_SURVIVAL_NOT_ESTABLISHED"
    elif not semantic:
        verdict = "STRUCTURAL_RESPONSE_BEHAVIOR_NOT_TRANSMITTED"
    elif not value:
        verdict = "SEMANTIC_TRANSMISSION_ADMITTED_DOWNSTREAM_VALUE_NOT_ESTABLISHED"
    else:
        verdict = "SEMANTIC_TRANSMISSION_ADMITTED_DOWNSTREAM_VALUE_TRIAL_ELIGIBLE"
    return {
        "channel": channel,
        "verdict": verdict,
        "gcf_0_calibration_passed": calibrated,
        "gcf_1_stagewise_detectability_passed": stagewise,
        "gcf_2_semantic_transmission_admitted": semantic,
        "gcf_3_downstream_value_trial_eligible": value,
        "positive_control_detected_states": positive_count,
        "detectable_states_by_stage": stage_counts,
        "behavior_changed_states": behavior_count,
        "utility_improved_states": utility_count,
        "states": states,
    }


def _load_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    import json

    if not path.is_file():
        raise RuntimeError(f"GCF manifest missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if manifest.get("manifest_digest") != expected_digest or digest_json(payload) != expected_digest:
        raise RuntimeError("sealed GCF manifest digest mismatch")
    if manifest.get("status") != "SEALED_PRE_EXECUTION":
        raise RuntimeError("GCF manifest was not sealed before execution")
    if manifest.get("protocol_implementation_sha256") != digest_bytes(Path(__file__).read_bytes()):
        raise RuntimeError("GCF implementation drifted after protocol sealing")
    if manifest.get("model_calls_before_seal") != 0 or manifest.get("fresh_budget_authorized"):
        raise RuntimeError("GCF synthetic protocol violates the no-fresh-budget boundary")
    return manifest
