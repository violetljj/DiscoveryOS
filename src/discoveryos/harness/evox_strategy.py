from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from discoveryos.contracts.models import EvidenceRecord, EvidenceValidity, MetricDirection
from discoveryos.operators.action_controller import SearchDecision, SearchState
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import canonical_json, digest_json


class EvoXParentMode(str, Enum):
    CURRENT_PARENT = "CURRENT_PARENT"
    INCUMBENT = "INCUMBENT"


class EvoXVariationMode(str, Enum):
    STRUCTURAL_DIVERGE = "STRUCTURAL_DIVERGE"
    COMPONENT_TRANSFER = "COMPONENT_TRANSFER"
    CROSS_LINEAGE_RECOMBINE = "CROSS_LINEAGE_RECOMBINE"


class EvoXTerminalTransition(str, Enum):
    RETAIN = "RETAIN"
    SWITCH = "SWITCH"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class EvoXSearchStrategySpec:
    name: str
    parent_mode: EvoXParentMode
    variation_mode: EvoXVariationMode
    guidance: str

    def __post_init__(self) -> None:
        if not self.name or not self.guidance.strip():
            raise ValueError("EvoX strategy requires identity and variation guidance")

    @property
    def strategy_spec_id(self) -> str:
        return f"evox_spec_{digest_json(self)[:24]}"


def default_evox_strategy_space() -> tuple[EvoXSearchStrategySpec, ...]:
    return (
        EvoXSearchStrategySpec(
            "baseline-structural-diverge",
            EvoXParentMode.CURRENT_PARENT,
            EvoXVariationMode.STRUCTURAL_DIVERGE,
            "Seek a materially different algorithm family while preserving valid lineage.",
        ),
        EvoXSearchStrategySpec(
            "targeted-component-transfer",
            EvoXParentMode.CURRENT_PARENT,
            EvoXVariationMode.COMPONENT_TRANSFER,
            "Transfer only reusable components that address the frozen stagnation evidence.",
        ),
        EvoXSearchStrategySpec(
            "incumbent-cross-lineage-recombine",
            EvoXParentMode.INCUMBENT,
            EvoXVariationMode.CROSS_LINEAGE_RECOMBINE,
            "Recombine a strong incumbent lineage with a distinct structural family hypothesis.",
        ),
    )


@dataclass(frozen=True, slots=True)
class EvoXStrategyConfig:
    strategy_space: tuple[EvoXSearchStrategySpec, ...] = default_evox_strategy_space()
    retain_margin: float = 0.0

    def __post_init__(self) -> None:
        if len(self.strategy_space) < 2:
            raise ValueError("EvoX requires at least two frozen strategies")
        ids = tuple(item.strategy_spec_id for item in self.strategy_space)
        if len(ids) != len(set(ids)):
            raise ValueError("EvoX strategy specs must be unique")
        if not math.isfinite(self.retain_margin) or self.retain_margin < 0:
            raise ValueError("EvoX retain margin must be finite and non-negative")

    @property
    def digest(self) -> str:
        return digest_json(self)

    def get(self, strategy_spec_id: str) -> EvoXSearchStrategySpec:
        try:
            return next(
                item for item in self.strategy_space if item.strategy_spec_id == strategy_spec_id
            )
        except StopIteration as error:
            raise ValueError(f"unknown EvoX strategy spec: {strategy_spec_id}") from error

    def next_after(self, strategy_spec_id: str) -> EvoXSearchStrategySpec:
        index = next(
            index
            for index, item in enumerate(self.strategy_space)
            if item.strategy_spec_id == strategy_spec_id
        )
        return self.strategy_space[(index + 1) % len(self.strategy_space)]


@dataclass(frozen=True, slots=True)
class EvoXDeploymentPlan:
    run_id: str
    step: int
    state_digest: str
    strategy: EvoXSearchStrategySpec
    fallback_strategy_spec_id: str
    selected_parent_id: str
    config_digest: str

    @property
    def deployment_id(self) -> str:
        return f"evox_deploy_{digest_json(self)[:24]}"

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return (
            f"EVOX_DEPLOYMENT:{self.deployment_id}",
            f"EVOX_STRATEGY_SPEC:{self.strategy.strategy_spec_id}",
            f"EVOX_PARENT_MODE:{self.strategy.parent_mode.value}",
            f"EVOX_VARIATION_MODE:{self.strategy.variation_mode.value}",
        )


@dataclass(frozen=True, slots=True)
class EvoXDeploymentReceipt:
    plan: EvoXDeploymentPlan
    decision_id: str

    @property
    def receipt_id(self) -> str:
        return self.plan.deployment_id

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "EvoXDeploymentReceipt":
        plan_payload = dict(payload["plan"])
        strategy_payload = dict(plan_payload["strategy"])
        plan = EvoXDeploymentPlan(
            run_id=str(plan_payload["run_id"]),
            step=int(plan_payload["step"]),
            state_digest=str(plan_payload["state_digest"]),
            strategy=EvoXSearchStrategySpec(
                name=str(strategy_payload["name"]),
                parent_mode=EvoXParentMode(str(strategy_payload["parent_mode"])),
                variation_mode=EvoXVariationMode(str(strategy_payload["variation_mode"])),
                guidance=str(strategy_payload["guidance"]),
            ),
            fallback_strategy_spec_id=str(plan_payload["fallback_strategy_spec_id"]),
            selected_parent_id=str(plan_payload["selected_parent_id"]),
            config_digest=str(plan_payload["config_digest"]),
        )
        return cls(plan=plan, decision_id=str(payload["decision_id"]))


@dataclass(frozen=True, slots=True)
class EvoXStrategySettlement:
    run_id: str
    step: int
    deployment_id: str
    decision_id: str
    evidence_receipt_id: str | None
    result_candidate_id: str | None
    before_utility: float
    after_utility: float | None
    observed_delta: float | None
    transition: EvoXTerminalTransition
    deployed_strategy_spec_id: str
    active_strategy_spec_id: str
    fallback_strategy_spec_id: str
    reason: str

    @property
    def receipt_id(self) -> str:
        return f"evox_settle_{digest_json(self)[:24]}"

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "EvoXStrategySettlement":
        return cls(
            run_id=str(payload["run_id"]),
            step=int(payload["step"]),
            deployment_id=str(payload["deployment_id"]),
            decision_id=str(payload["decision_id"]),
            evidence_receipt_id=(
                str(payload["evidence_receipt_id"])
                if payload.get("evidence_receipt_id") is not None
                else None
            ),
            result_candidate_id=(
                str(payload["result_candidate_id"])
                if payload.get("result_candidate_id") is not None
                else None
            ),
            before_utility=float(payload["before_utility"]),
            after_utility=(
                float(payload["after_utility"])
                if payload.get("after_utility") is not None
                else None
            ),
            observed_delta=(
                float(payload["observed_delta"])
                if payload.get("observed_delta") is not None
                else None
            ),
            transition=EvoXTerminalTransition(str(payload["transition"])),
            deployed_strategy_spec_id=str(payload["deployed_strategy_spec_id"]),
            active_strategy_spec_id=str(payload["active_strategy_spec_id"]),
            fallback_strategy_spec_id=str(payload["fallback_strategy_spec_id"]),
            reason=str(payload["reason"]),
        )


class EvoXStrategyStateMachine:
    DEPLOYMENT_NODE_TYPE = "evox_strategy_deployment"
    SETTLEMENT_NODE_TYPE = "evox_strategy_settlement"

    def __init__(
        self,
        ledger: EvidenceLedger,
        config: EvoXStrategyConfig | None = None,
    ) -> None:
        self.ledger = ledger
        self.config = config or EvoXStrategyConfig()

    def plan(
        self,
        state: SearchState,
        decision_parent_id: str | None,
    ) -> EvoXDeploymentPlan:
        if decision_parent_id is None:
            raise ValueError("EvoX strategy deployment requires a decision parent")
        pending = self._pending_deployment(state.run_id)
        if pending is not None:
            raise ValueError(f"EvoX deployment lacks terminal settlement: {pending.receipt_id}")
        latest = self._latest_settlement(state.run_id)
        if latest is None:
            strategy = self.config.strategy_space[1]
            fallback = self.config.strategy_space[0].strategy_spec_id
        else:
            strategy = self.config.get(latest.active_strategy_spec_id)
            fallback = latest.fallback_strategy_spec_id
        selected_parent = (
            state.incumbent_candidate_id
            if strategy.parent_mode is EvoXParentMode.INCUMBENT
            else decision_parent_id
        )
        candidate = next(
            (item for item in state.candidates if item.candidate_id == selected_parent),
            None,
        )
        if candidate is None or not candidate.active:
            raise ValueError("EvoX selected parent is not an active candidate")
        return EvoXDeploymentPlan(
            run_id=state.run_id,
            step=state.step,
            state_digest=state.digest,
            strategy=strategy,
            fallback_strategy_spec_id=fallback,
            selected_parent_id=selected_parent,
            config_digest=self.config.digest,
        )

    def deploy(
        self,
        state: SearchState,
        decision: SearchDecision,
    ) -> EvoXDeploymentReceipt:
        plan = self.plan(state, decision.candidate_id)
        self._verify_reason_codes(decision, plan)
        receipt = EvoXDeploymentReceipt(plan=plan, decision_id=decision.decision_id)
        for strategy in self.config.strategy_space:
            self.ledger.add_node(
                strategy.strategy_spec_id,
                "evox_search_strategy_spec",
                strategy,
            )
        self.ledger.add_node(receipt.receipt_id, self.DEPLOYMENT_NODE_TYPE, receipt)
        self.ledger.add_edge(
            plan.strategy.strategy_spec_id,
            receipt.receipt_id,
            "EVOX_STRATEGY_DEPLOYED",
            {"run_id": state.run_id, "step": state.step, "decision_id": decision.decision_id},
        )
        return receipt

    def generation_guidance(
        self,
        state: SearchState,
        decision: SearchDecision,
    ) -> tuple[str, ...]:
        deployment_id = self._reason_value(decision, "EVOX_DEPLOYMENT:")
        payload = self.ledger.node_payload(deployment_id, self.DEPLOYMENT_NODE_TYPE)
        if payload is None:
            raise ValueError("EvoX strategy was not deployed before generation")
        receipt = EvoXDeploymentReceipt.from_dict(payload)
        plan = receipt.plan
        if (
            receipt.decision_id != decision.decision_id
            or plan.run_id != state.run_id
            or plan.step != state.step
            or plan.state_digest != state.digest
            or plan.selected_parent_id != decision.candidate_id
        ):
            raise ValueError("EvoX deployed strategy does not match the bound decision")
        self._verify_reason_codes(decision, plan)
        return (
            "EVOX_STRATEGY_DEPLOYMENT_V1=" + canonical_json(receipt),
            f"EVOX_VARIATION_MODE:{plan.strategy.variation_mode.value};"
            f"PARENT_MODE:{plan.strategy.parent_mode.value};"
            "GUIDANCE="
            + plan.strategy.guidance,
        )

    def settle(
        self,
        *,
        state: SearchState,
        decision: SearchDecision,
        result_candidate_id: str | None,
        evidence: EvidenceRecord | None,
        metric_name: str,
        metric_direction: MetricDirection,
    ) -> EvoXStrategySettlement:
        deployment_id = self._reason_value(decision, "EVOX_DEPLOYMENT:")
        payload = self.ledger.node_payload(deployment_id, self.DEPLOYMENT_NODE_TYPE)
        if payload is None:
            raise ValueError("EvoX settlement requires a deployed strategy")
        receipt = EvoXDeploymentReceipt.from_dict(payload)
        existing = self._settlement_for(deployment_id)
        before = state.incumbent_utility
        after = self._observed_utility(evidence, metric_name)
        valid = (
            evidence is not None
            and evidence.validity is EvidenceValidity.VALID
            and result_candidate_id is not None
            and after is not None
        )
        delta = None
        if valid:
            delta = after - before if metric_direction is MetricDirection.MAXIMIZE else before - after
        if not valid:
            transition = EvoXTerminalTransition.ROLLBACK
            active = receipt.plan.fallback_strategy_spec_id
            fallback = self.config.strategy_space[0].strategy_spec_id
            reason = "DEPLOYMENT_OR_EVALUATION_FAILED"
        elif delta is not None and delta > self.config.retain_margin:
            transition = EvoXTerminalTransition.RETAIN
            active = receipt.plan.strategy.strategy_spec_id
            fallback = receipt.plan.fallback_strategy_spec_id
            reason = "OBSERVED_IMPROVEMENT_EXCEEDED_RETAIN_MARGIN"
        else:
            transition = EvoXTerminalTransition.SWITCH
            active = self.config.next_after(receipt.plan.strategy.strategy_spec_id).strategy_spec_id
            fallback = receipt.plan.strategy.strategy_spec_id
            reason = "NO_IMPROVEMENT_SWITCH_TO_NEXT_FROZEN_STRATEGY"
        settlement = EvoXStrategySettlement(
            run_id=state.run_id,
            step=state.step,
            deployment_id=deployment_id,
            decision_id=decision.decision_id,
            evidence_receipt_id=evidence.receipt_id if evidence is not None else None,
            result_candidate_id=result_candidate_id,
            before_utility=before,
            after_utility=after,
            observed_delta=delta,
            transition=transition,
            deployed_strategy_spec_id=receipt.plan.strategy.strategy_spec_id,
            active_strategy_spec_id=active,
            fallback_strategy_spec_id=fallback,
            reason=reason,
        )
        if existing is not None and existing != settlement:
            raise ValueError("EvoX deployment settlement collision")
        self.ledger.add_node(settlement.receipt_id, self.SETTLEMENT_NODE_TYPE, settlement)
        self.ledger.add_edge(
            deployment_id,
            settlement.receipt_id,
            "EVOX_STRATEGY_OBSERVED",
            {
                "evidence_receipt_id": settlement.evidence_receipt_id,
                "result_candidate_id": result_candidate_id,
                "after_utility": after,
            },
        )
        self.ledger.add_edge(
            deployment_id,
            settlement.receipt_id,
            "EVOX_STRATEGY_SCORED",
            {"before_utility": before, "observed_delta": delta},
        )
        self.ledger.add_edge(
            deployment_id,
            settlement.receipt_id,
            f"EVOX_STRATEGY_{transition.value}",
            {"run_id": state.run_id, "step": state.step, "observed_delta": delta},
        )
        self.ledger.add_edge(
            settlement.receipt_id,
            active,
            "EVOX_ACTIVE_STRATEGY",
            {"transition": transition.value},
        )
        return settlement

    def _latest_settlement(self, run_id: str) -> EvoXStrategySettlement | None:
        records = tuple(
            EvoXStrategySettlement.from_dict(payload)
            for payload in self.ledger.node_payloads(self.SETTLEMENT_NODE_TYPE)
            if payload.get("run_id") == run_id
        )
        return max(records, key=lambda item: (item.step, item.receipt_id), default=None)

    def _pending_deployment(self, run_id: str) -> EvoXDeploymentReceipt | None:
        deployments = tuple(
            EvoXDeploymentReceipt.from_dict(payload)
            for payload in self.ledger.node_payloads(self.DEPLOYMENT_NODE_TYPE)
            if dict(payload["plan"]).get("run_id") == run_id
        )
        settled_ids = {
            str(payload["deployment_id"])
            for payload in self.ledger.node_payloads(self.SETTLEMENT_NODE_TYPE)
            if payload.get("run_id") == run_id
        }
        pending = tuple(item for item in deployments if item.receipt_id not in settled_ids)
        if len(pending) > 1:
            raise ValueError("multiple pending EvoX deployments violate the state machine")
        return pending[0] if pending else None

    def _settlement_for(self, deployment_id: str) -> EvoXStrategySettlement | None:
        matches = tuple(
            EvoXStrategySettlement.from_dict(payload)
            for payload in self.ledger.node_payloads(self.SETTLEMENT_NODE_TYPE)
            if payload.get("deployment_id") == deployment_id
        )
        if len(matches) > 1:
            raise ValueError("multiple settlements exist for one EvoX deployment")
        return matches[0] if matches else None

    @staticmethod
    def _observed_utility(evidence: EvidenceRecord | None, metric_name: str) -> float | None:
        if evidence is None or evidence.validity is not EvidenceValidity.VALID:
            return None
        value = evidence.metric_dict().get(metric_name)
        if value is None or not math.isfinite(value):
            return None
        return float(value)

    @staticmethod
    def _reason_value(decision: SearchDecision, prefix: str) -> str:
        matches = tuple(code[len(prefix) :] for code in decision.reason_codes if code.startswith(prefix))
        if len(matches) != 1 or not matches[0]:
            raise ValueError(f"EvoX decision requires exactly one {prefix} binding")
        return matches[0]

    @staticmethod
    def _verify_reason_codes(decision: SearchDecision, plan: EvoXDeploymentPlan) -> None:
        prefixes = (
            "EVOX_DEPLOYMENT:",
            "EVOX_STRATEGY_SPEC:",
            "EVOX_PARENT_MODE:",
            "EVOX_VARIATION_MODE:",
        )
        bound = tuple(code for code in decision.reason_codes if code.startswith(prefixes))
        if bound != plan.reason_codes:
            raise ValueError("EvoX decision is not bound to the frozen deployment plan")
