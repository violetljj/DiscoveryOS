from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from discoveryos.contracts.models import ProblemContract
from discoveryos.evaluation.base import EvaluatorRegistry
from discoveryos.evaluation.gates import GateEngine
from discoveryos.graph.models import ResearchGraph
from discoveryos.operators.action_controller import (
    DeterministicActionController,
    SearchAction,
    SearchDecision,
    SearchState,
)
from discoveryos.operators.local_patch import LocalPatchOperator, PatchProvider
from discoveryos.operators.structural_rewrite import StructuralRewriteOperator
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ExperimentExecutor
from discoveryos.util import digest_bytes, digest_json

from .context import ResearchContext, ServiceKey
from .plugins import (
    HarnessEventSink,
    PluginActivation,
    PluginManifest,
    PluginSelection,
    ResearchPlugin,
    ResearchProfile,
)


CONTRACT = ServiceKey("contract", ProblemContract, authority=True)
LEDGER = ServiceKey("candidate_evidence_store", EvidenceLedger, authority=True)
ARTIFACTS = ServiceKey("artifact_store", ArtifactStore, authority=True)
EVALUATOR = ServiceKey("evaluator_registry", EvaluatorRegistry, authority=True)
BUDGET = ServiceKey("budget_authority", ExperimentExecutor, authority=True)
GATE_ENGINE = ServiceKey("gate_engine", GateEngine, authority=True)
RESEARCH_GRAPH = ServiceKey("research_graph", ResearchGraph, authority=True)
LOCAL_PATCH_PROVIDER = ServiceKey("local_patch_provider", object)
STRUCTURAL_PATCH_PROVIDER = ServiceKey("structural_patch_provider", object)
BASE_CONTROLLER = ServiceKey("base_action_controller", DeterministicActionController)


_IMPLEMENTATION_DIGEST = digest_bytes(Path(__file__).read_bytes())


def _plugin_manifest(
    plugin_id: str,
    *,
    source_system: str,
    requires: tuple[ServiceKey[Any], ...],
    provides: tuple[ServiceKey[Any], ...],
) -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        version="1",
        source_system=source_system,
        source_revision="discoveryos-internal-adapter-v1",
        license_id="UNSPECIFIED_REFERENCE_LICENSE_INTERNAL_IMPLEMENTATION",
        implementation_digest=_IMPLEMENTATION_DIGEST,
        authority_scope="SEARCH_PLANE_ONLY",
        failure_semantics="ACTIVATION_OR_GENERATION_FAIL_CLOSED",
        replay_contract="PROFILE_MANIFEST_AND_DECISION_DIGEST_V1",
        requires=requires,
        provides=provides,
    )


@dataclass(frozen=True, slots=True)
class StrategyDescriptor:
    strategy_id: str
    role: str
    operator_id: str
    source_system: str
    mechanism: str


class DirectLLMResearchOperator(LocalPatchOperator):
    operator_id = "direct_llm_research_v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strategy_id="direct_llm_strategy_v1", **kwargs)


class AdaLineageOperator(LocalPatchOperator):
    operator_id = "ada_lineage_refinement_v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strategy_id="ada_lineage_strategy_v1", **kwargs)


class EvoXMetaStrategyOperator(StructuralRewriteOperator):
    operator_id = "evox_meta_strategy_rewrite_v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strategy_id="evox_meta_strategy_v1", **kwargs)


@dataclass(frozen=True, slots=True)
class OperatorRegistry:
    operators: tuple[tuple[str, LocalPatchOperator], ...] = ()
    strategies: tuple[StrategyDescriptor, ...] = ()

    def __post_init__(self) -> None:
        ids = [operator_id for operator_id, _ in self.operators]
        if len(ids) != len(set(ids)):
            raise ValueError("operator registry ids must be unique")
        strategy_ids = [item.strategy_id for item in self.strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("strategy registry ids must be unique")

    def add(self, operator: LocalPatchOperator, descriptor: StrategyDescriptor) -> OperatorRegistry:
        if descriptor.operator_id != operator.operator_id:
            raise ValueError("strategy descriptor and operator id differ")
        if any(key == operator.operator_id for key, _ in self.operators):
            raise ValueError(f"operator is already registered: {operator.operator_id}")
        return OperatorRegistry(
            operators=(*self.operators, (operator.operator_id, operator)),
            strategies=(*self.strategies, descriptor),
        )

    def get(self, operator_id: str) -> LocalPatchOperator:
        try:
            return next(operator for key, operator in self.operators if key == operator_id)
        except StopIteration as error:
            raise KeyError(operator_id) from error


OPERATOR_REGISTRY = ServiceKey("research_operator_registry", OperatorRegistry)
ACTION_CONTROLLER = ServiceKey("research_action_controller", DeterministicActionController)


@dataclass(frozen=True, slots=True)
class HarnessRoutingConfig:
    direct_bootstrap_steps: int = 1
    ada_strategy_id: str = "ada_lineage_strategy_v1"
    ada_operator_id: str = AdaLineageOperator.operator_id
    evox_strategy_id: str = "evox_meta_strategy_v1"
    evox_operator_id: str = EvoXMetaStrategyOperator.operator_id
    direct_strategy_id: str = "direct_llm_strategy_v1"
    direct_operator_id: str = DirectLLMResearchOperator.operator_id

    def __post_init__(self) -> None:
        if self.direct_bootstrap_steps < 0:
            raise ValueError("direct bootstrap steps cannot be negative")


class HarnessResearchController(DeterministicActionController):
    """Drop-in controller that routes generation through profile strategies.

    Replication, fidelity promotion, affordability, parent eligibility and stop
    behavior remain delegated to the existing deterministic controller. The
    harness only selects a Search-plane generator for an already-authorized
    generative action.
    """

    def __init__(
        self,
        base: DeterministicActionController,
        registry: OperatorRegistry,
        routing: HarnessRoutingConfig | None = None,
    ) -> None:
        super().__init__(base.config, base.parent_policy)
        self.base = base
        self.registry = registry
        self.routing = routing or HarnessRoutingConfig()
        required = {
            self.routing.direct_operator_id,
            self.routing.ada_operator_id,
            self.routing.evox_operator_id,
        }
        registered = {operator_id for operator_id, _ in registry.operators}
        if not required.issubset(registered):
            raise ValueError("harness router requires Direct, Ada and EvoX operators")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "policy": "discoveryos_research_harness_router_v0",
                "base_controller": self.base.digest,
                "routing": self.routing,
                "strategies": self.registry.strategies,
            }
        )

    def decide(self, state: SearchState) -> SearchDecision:
        base = self.base.decide(state)
        strategy_id = base.strategy_id
        operator_id = base.operator_id
        reasons: tuple[str, ...] = ()
        if base.action is SearchAction.LOCAL_PATCH:
            source = self._candidate(state, base.candidate_id)
            if state.step < self.routing.direct_bootstrap_steps:
                strategy_id = self.routing.direct_strategy_id
                operator_id = self.routing.direct_operator_id
                reasons = ("HARNESS_DIRECT_BOOTSTRAP",)
            else:
                strategy_id = self.routing.ada_strategy_id
                operator_id = self.routing.ada_operator_id
                reasons = ("HARNESS_ADA_LINEAGE_REFINEMENT",)
                if source is not None and source.strategy_id == self.routing.evox_strategy_id:
                    reasons += ("CROSS_SEED_EVOX_TO_ADA",)
        elif base.action is SearchAction.STRUCTURAL_ESCAPE:
            source = self._candidate(state, base.candidate_id)
            strategy_id = self.routing.evox_strategy_id
            operator_id = self.routing.evox_operator_id
            reasons = ("HARNESS_EVOX_META_STRATEGY",)
            if source is not None and source.strategy_id in {
                self.routing.ada_strategy_id,
                self.routing.direct_strategy_id,
            }:
                reasons += ("CROSS_SEED_LINEAGE_TO_EVOX",)
        return self._copy_decision(
            base,
            state,
            operator_id=operator_id,
            strategy_id=strategy_id,
            extra_reasons=reasons,
        )

    @staticmethod
    def _candidate(state: SearchState, candidate_id: str | None):
        return next((item for item in state.candidates if item.candidate_id == candidate_id), None)

    def _copy_decision(
        self,
        decision: SearchDecision,
        state: SearchState,
        *,
        operator_id: str | None,
        strategy_id: str | None,
        extra_reasons: tuple[str, ...],
    ) -> SearchDecision:
        return SearchDecision.create(
            state=state,
            controller_digest=self.digest,
            action=decision.action,
            candidate_id=decision.candidate_id,
            branch_id=decision.branch_id,
            operator_id=operator_id,
            strategy_id=strategy_id,
            fidelity=decision.fidelity,
            reason_codes=(*extra_reasons, *decision.reason_codes),
            resource_floor=decision.resource_floor,
            generation_reserve=decision.generation_reserve,
            evaluation_reserve=decision.evaluation_reserve,
            settlement_reserve=decision.settlement_reserve,
            novelty_resample_reserve=decision.novelty_resample_reserve,
            reserved_downstream_budget=decision.reserved_downstream_budget,
            budget_reserved=decision.budget_reserved,
            preflight_affordable=decision.preflight_affordable,
            rejected_action=decision.rejected_action,
            parent_selection_receipt=decision.parent_selection_receipt,
            reusable_component_ids=decision.reusable_component_ids,
        )


class _OperatorPlugin(ResearchPlugin):
    operator_type: type[LocalPatchOperator]
    descriptor: StrategyDescriptor
    provider_key: ServiceKey[Any]

    def activate(self, context: ResearchContext, config: Mapping[str, Any]) -> PluginActivation:
        if config:
            unknown = ",".join(sorted(config))
            raise ValueError(f"{self.manifest.plugin_id} does not accept config: {unknown}")
        operator = self.operator_type(
            provider=context.get(self.provider_key),
            artifacts=context.get(ARTIFACTS),
            ledger=context.get(LEDGER),
            contract=context.get(CONTRACT),
        )
        registry = context.get(OPERATOR_REGISTRY) if context.has(OPERATOR_REGISTRY) else OperatorRegistry()
        return PluginActivation({OPERATOR_REGISTRY: registry.add(operator, self.descriptor)})


class DirectLLMPlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "direct_llm",
        source_system="DiscoveryOS Direct LLM",
        requires=(LOCAL_PATCH_PROVIDER, ARTIFACTS, LEDGER, CONTRACT),
        provides=(OPERATOR_REGISTRY,),
    )
    operator_type = DirectLLMResearchOperator
    provider_key = LOCAL_PATCH_PROVIDER
    descriptor = StrategyDescriptor(
        "direct_llm_strategy_v1",
        "bootstrap_proposer",
        DirectLLMResearchOperator.operator_id,
        "generic_llm",
        "direct bounded hypothesis and patch proposal",
    )


class AdaLineagePlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "ada_lineage",
        source_system="AdaEvolve mechanism role / DiscoveryOS implementation",
        requires=(LOCAL_PATCH_PROVIDER, ARTIFACTS, LEDGER, CONTRACT, OPERATOR_REGISTRY),
        provides=(OPERATOR_REGISTRY,),
    )
    operator_type = AdaLineageOperator
    provider_key = LOCAL_PATCH_PROVIDER
    descriptor = StrategyDescriptor(
        "ada_lineage_strategy_v1",
        "lineage",
        AdaLineageOperator.operator_id,
        "AdaEvolve",
        "lineage refinement and promising-route exploitation",
    )


class EvoXMetaStrategyPlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "evox_meta_strategy",
        source_system="EvoX mechanism role / DiscoveryOS implementation",
        requires=(STRUCTURAL_PATCH_PROVIDER, ARTIFACTS, LEDGER, CONTRACT, OPERATOR_REGISTRY),
        provides=(OPERATOR_REGISTRY,),
    )
    operator_type = EvoXMetaStrategyOperator
    provider_key = STRUCTURAL_PATCH_PROVIDER
    descriptor = StrategyDescriptor(
        "evox_meta_strategy_v1",
        "meta_strategy",
        EvoXMetaStrategyOperator.operator_id,
        "EvoX",
        "stagnation-triggered strategy revision and structural basin shift",
    )


class StateRouterPlugin(ResearchPlugin):
    manifest = _plugin_manifest(
        "state_router",
        source_system="DiscoveryOS deterministic router",
        requires=(BASE_CONTROLLER, OPERATOR_REGISTRY),
        provides=(ACTION_CONTROLLER,),
    )

    def activate(self, context: ResearchContext, config: Mapping[str, Any]) -> PluginActivation:
        routing = HarnessRoutingConfig(**dict(config))
        controller = HarnessResearchController(
            context.get(BASE_CONTROLLER),
            context.get(OPERATOR_REGISTRY),
            routing,
        )
        return PluginActivation({ACTION_CONTROLLER: controller})


def algorithm_discovery_v1_profile() -> ResearchProfile:
    return ResearchProfile(
        name="algorithm-discovery-v1",
        plugins=(
            PluginSelection.create("direct_llm", DirectLLMPlugin.manifest.digest),
            PluginSelection.create("ada_lineage", AdaLineagePlugin.manifest.digest),
            PluginSelection.create("evox_meta_strategy", EvoXMetaStrategyPlugin.manifest.digest),
            PluginSelection.create(
                "state_router",
                StateRouterPlugin.manifest.digest,
                {"direct_bootstrap_steps": 1},
            ),
        ),
    )


def standard_research_plugins() -> tuple[ResearchPlugin, ...]:
    return (DirectLLMPlugin(), AdaLineagePlugin(), EvoXMetaStrategyPlugin(), StateRouterPlugin())


def build_root_research_context(
    *,
    contract: ProblemContract,
    ledger: EvidenceLedger,
    artifacts: ArtifactStore,
    experiment_executor: ExperimentExecutor,
    local_provider: PatchProvider,
    structural_provider: PatchProvider,
    base_controller: DeterministicActionController,
) -> tuple[ResearchContext, HarnessEventSink]:
    if experiment_executor.contract.digest != contract.digest:
        raise ValueError("harness and experiment executor must share the frozen contract")
    if experiment_executor.ledger is not ledger or experiment_executor.artifacts is not artifacts:
        raise ValueError("harness and experiment executor must share ledger and artifact authorities")
    graph = ResearchGraph(ledger)
    gate = GateEngine()
    sink = HarnessEventSink(ledger)
    context = ResearchContext.root(
        {
            CONTRACT: contract,
            LEDGER: ledger,
            ARTIFACTS: artifacts,
            EVALUATOR: experiment_executor.registry,
            BUDGET: experiment_executor,
            GATE_ENGINE: gate,
            RESEARCH_GRAPH: graph,
            LOCAL_PATCH_PROVIDER: local_provider,
            STRUCTURAL_PATCH_PROVIDER: structural_provider,
            BASE_CONTROLLER: base_controller,
        }
    )
    return context, sink
