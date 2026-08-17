from __future__ import annotations

from dataclasses import dataclass
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
from discoveryos.util import digest_json

from .ada_adaptation import AdaTrajectoryPolicy, AdaTrajectoryReceipt
from .bindings import harness_code_bundle_digest
from .evox_strategy import EvoXDeploymentPlan, EvoXStrategyStateMachine
from .context import ResearchContext, ServiceKey
from .plugins import (
    HarnessEventSink,
    PluginActivation,
    PluginManifest,
    PluginSelection,
    ResearchCapability,
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


_IMPLEMENTATION_DIGEST = harness_code_bundle_digest()


def _plugin_manifest(
    plugin_id: str,
    *,
    source_system: str,
    capabilities: tuple[ResearchCapability, ...] = (),
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
        capabilities=capabilities,
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
    capabilities: tuple[ResearchCapability, ...]

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.operator_id or not self.capabilities:
            raise ValueError("strategy descriptors require identity and capabilities")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("strategy descriptors cannot repeat capabilities")


class DirectLLMResearchOperator(LocalPatchOperator):
    operator_id = "direct_llm_research_v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strategy_id="direct_llm_strategy_v1", **kwargs)


class AdaLineageOperator(LocalPatchOperator):
    operator_id = "ada_lineage_refinement_v1"

    def __init__(
        self,
        *,
        trajectory_policy: AdaTrajectoryPolicy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(strategy_id="ada_lineage_strategy_v1", **kwargs)
        self.trajectory_policy = trajectory_policy or AdaTrajectoryPolicy()

    def adaptation_receipt(
        self,
        state: SearchState,
        branch_id: str | None,
    ) -> AdaTrajectoryReceipt:
        return self.trajectory_policy.project(state, branch_id)

    def generation_guidance(
        self,
        *,
        state: SearchState,
        decision: SearchDecision,
    ) -> tuple[str, ...]:
        return self.trajectory_policy.verify_decision(state, decision).generation_guidance()


class EvoXMetaStrategyOperator(StructuralRewriteOperator):
    operator_id = "evox_meta_strategy_rewrite_v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(strategy_id="evox_meta_strategy_v1", **kwargs)
        self.strategy_machine = EvoXStrategyStateMachine(self.ledger)

    def strategy_plan(
        self,
        state: SearchState,
        decision_parent_id: str | None,
    ) -> EvoXDeploymentPlan:
        return self.strategy_machine.plan(state, decision_parent_id)

    def deploy_strategy(self, *, state: SearchState, decision: SearchDecision) -> None:
        self.strategy_machine.deploy(state, decision)

    def generation_guidance(
        self,
        *,
        state: SearchState,
        decision: SearchDecision,
    ) -> tuple[str, ...]:
        return self.strategy_machine.generation_guidance(state, decision)

    def settle_strategy(self, **kwargs: Any):
        return self.strategy_machine.settle(**kwargs)


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

    def descriptor_for_strategy(self, strategy_id: str | None) -> StrategyDescriptor | None:
        return next((item for item in self.strategies if item.strategy_id == strategy_id), None)

    def provider_for(self, capability: ResearchCapability) -> StrategyDescriptor | None:
        matches = tuple(item for item in self.strategies if capability in item.capabilities)
        if len(matches) > 1:
            raise ValueError(f"profile has ambiguous providers for capability: {capability.value}")
        return matches[0] if matches else None


OPERATOR_REGISTRY = ServiceKey("research_operator_registry", OperatorRegistry)
ACTION_CONTROLLER = ServiceKey("research_action_controller", DeterministicActionController)


@dataclass(frozen=True, slots=True)
class HarnessRoutingConfig:
    bootstrap_steps: int = 1
    allow_cross_seed: bool = True

    def __post_init__(self) -> None:
        if self.bootstrap_steps < 0:
            raise ValueError("bootstrap steps cannot be negative")


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
        if not registry.operators:
            raise ValueError("harness router requires at least one research operator")
        for capability in ResearchCapability:
            registry.provider_for(capability)

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "policy": "discoveryos_research_harness_router_v1_1_capability_contract",
                "base_controller": self.base.digest,
                "routing": self.routing,
                "strategies": self.registry.strategies,
            }
        )

    def decide(self, state: SearchState) -> SearchDecision:
        base = self.base.decide(state)
        strategy_id = base.strategy_id
        operator_id = base.operator_id
        selected_candidate_id: str | None = None
        reasons: tuple[str, ...] = ()
        if base.action is SearchAction.LOCAL_PATCH:
            source = self._candidate(state, base.candidate_id)
            bootstrap = self.registry.provider_for(ResearchCapability.BOOTSTRAP_PROPOSAL)
            refinement = self.registry.provider_for(ResearchCapability.LOCAL_REFINEMENT)
            if (
                state.step < self.routing.bootstrap_steps
                and bootstrap is not None
            ):
                strategy_id = bootstrap.strategy_id
                operator_id = bootstrap.operator_id
                reasons = ("HARNESS_BOOTSTRAP_PROPOSAL",)
            elif refinement is not None:
                strategy_id = refinement.strategy_id
                operator_id = refinement.operator_id
                reasons = ("HARNESS_LOCAL_REFINEMENT",)
                refinement_operator = self.registry.get(refinement.operator_id)
                adaptation_receipt = getattr(refinement_operator, "adaptation_receipt", None)
                if adaptation_receipt is not None:
                    reasons += adaptation_receipt(state, base.branch_id).reason_codes
                if (
                    self.routing.allow_cross_seed
                    and source is not None
                    and self._source_has_capability(
                        source.strategy_id,
                        ResearchCapability.STRUCTURAL_ESCAPE,
                        ResearchCapability.META_STRATEGY,
                    )
                ):
                    reasons += ("CROSS_SEED_STRUCTURAL_TO_LOCAL",)
            elif bootstrap is not None:
                strategy_id = bootstrap.strategy_id
                operator_id = bootstrap.operator_id
                reasons = ("HARNESS_BOOTSTRAP_ONLY",)
            else:
                raise ValueError("profile cannot execute a local refinement action")
        elif base.action is SearchAction.STRUCTURAL_ESCAPE:
            source = self._candidate(state, base.candidate_id)
            structural = self.registry.provider_for(ResearchCapability.STRUCTURAL_ESCAPE)
            if structural is None:
                raise ValueError("profile cannot execute a structural escape action")
            strategy_id = structural.strategy_id
            operator_id = structural.operator_id
            reasons = ("HARNESS_STRUCTURAL_ESCAPE",)
            if ResearchCapability.META_STRATEGY in structural.capabilities:
                reasons += ("HARNESS_META_STRATEGY",)
                structural_operator = self.registry.get(structural.operator_id)
                strategy_plan = getattr(structural_operator, "strategy_plan", None)
                if not callable(strategy_plan):
                    raise ValueError("meta-strategy capability lacks a typed strategy state machine")
                plan = strategy_plan(state, base.candidate_id)
                reasons += plan.reason_codes
                selected_candidate_id = plan.selected_parent_id
            if (
                self.routing.allow_cross_seed
                and source is not None
                and self._source_has_capability(
                    source.strategy_id,
                    ResearchCapability.BOOTSTRAP_PROPOSAL,
                    ResearchCapability.LOCAL_REFINEMENT,
                )
            ):
                reasons += ("CROSS_SEED_LOCAL_TO_STRUCTURAL",)
        return self._copy_decision(
            base,
            state,
            operator_id=operator_id,
            strategy_id=strategy_id,
            extra_reasons=reasons,
            candidate_id=selected_candidate_id,
        )

    @staticmethod
    def _candidate(state: SearchState, candidate_id: str | None):
        return next((item for item in state.candidates if item.candidate_id == candidate_id), None)

    def _source_has_capability(
        self,
        strategy_id: str | None,
        *capabilities: ResearchCapability,
    ) -> bool:
        descriptor = self.registry.descriptor_for_strategy(strategy_id)
        return descriptor is not None and any(
            capability in descriptor.capabilities for capability in capabilities
        )

    def _copy_decision(
        self,
        decision: SearchDecision,
        state: SearchState,
        *,
        operator_id: str | None,
        strategy_id: str | None,
        extra_reasons: tuple[str, ...],
        candidate_id: str | None = None,
    ) -> SearchDecision:
        resolved_candidate_id = candidate_id or decision.candidate_id
        return SearchDecision.create(
            state=state,
            controller_digest=self.digest,
            action=decision.action,
            candidate_id=resolved_candidate_id,
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
            parent_selection_receipt=(
                decision.parent_selection_receipt
                if resolved_candidate_id == decision.candidate_id
                else None
            ),
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
        if self.descriptor.capabilities != self.manifest.capabilities:
            raise ValueError(
                f"{self.manifest.plugin_id} descriptor capabilities differ from its manifest"
            )
        registry = context.get(OPERATOR_REGISTRY) if context.has(OPERATOR_REGISTRY) else OperatorRegistry()
        return PluginActivation(
            {OPERATOR_REGISTRY: registry.add(operator, self.descriptor)},
            capabilities=self.descriptor.capabilities,
        )


class DirectLLMPlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "direct_llm",
        source_system="DiscoveryOS Direct LLM",
        capabilities=(ResearchCapability.BOOTSTRAP_PROPOSAL,),
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
        (ResearchCapability.BOOTSTRAP_PROPOSAL,),
    )


class AdaLineagePlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "ada_lineage",
        source_system="AdaEvolve mechanism role / DiscoveryOS implementation",
        capabilities=(ResearchCapability.LOCAL_REFINEMENT,),
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
        (ResearchCapability.LOCAL_REFINEMENT,),
    )


class EvoXMetaStrategyPlugin(_OperatorPlugin):
    manifest = _plugin_manifest(
        "evox_meta_strategy",
        source_system="EvoX mechanism role / DiscoveryOS implementation",
        capabilities=(
            ResearchCapability.STRUCTURAL_ESCAPE,
            ResearchCapability.META_STRATEGY,
        ),
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
        (ResearchCapability.STRUCTURAL_ESCAPE, ResearchCapability.META_STRATEGY),
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
    return harness_static_v1_profile()


def lineage_static_v1_profile() -> ResearchProfile:
    return ResearchProfile(
        name="lineage-static-v1",
        plugins=(
            PluginSelection.create("direct_llm", DirectLLMPlugin.manifest.digest),
            PluginSelection.create("ada_lineage", AdaLineagePlugin.manifest.digest),
            PluginSelection.create(
                "state_router",
                StateRouterPlugin.manifest.digest,
                {"bootstrap_steps": 1, "allow_cross_seed": False},
            ),
        ),
    )


def structural_static_v1_profile() -> ResearchProfile:
    return ResearchProfile(
        name="structural-static-v1",
        plugins=(
            PluginSelection.create("direct_llm", DirectLLMPlugin.manifest.digest),
            PluginSelection.create("evox_meta_strategy", EvoXMetaStrategyPlugin.manifest.digest),
            PluginSelection.create(
                "state_router",
                StateRouterPlugin.manifest.digest,
                {"bootstrap_steps": 1, "allow_cross_seed": False},
            ),
        ),
    )


def naive_parallel_lineage_v1_profile() -> ResearchProfile:
    profile = lineage_static_v1_profile()
    return ResearchProfile(name="naive-parallel-lineage-v1", plugins=profile.plugins)


def naive_parallel_structural_v1_profile() -> ResearchProfile:
    profile = structural_static_v1_profile()
    return ResearchProfile(name="naive-parallel-structural-v1", plugins=profile.plugins)


def harness_static_v1_profile() -> ResearchProfile:
    return ResearchProfile(
        name="harness-static-v1",
        plugins=(
            PluginSelection.create("direct_llm", DirectLLMPlugin.manifest.digest),
            PluginSelection.create("ada_lineage", AdaLineagePlugin.manifest.digest),
            PluginSelection.create("evox_meta_strategy", EvoXMetaStrategyPlugin.manifest.digest),
            PluginSelection.create(
                "state_router",
                StateRouterPlugin.manifest.digest,
                {"bootstrap_steps": 1},
            ),
        ),
    )


def static_composition_profiles() -> dict[str, tuple[ResearchProfile, ...]]:
    """Frozen P2 arms; naive parallel is two isolated child runs with split budget."""

    return {
        "lineage_static_v1": (lineage_static_v1_profile(),),
        "structural_static_v1": (structural_static_v1_profile(),),
        "naive_parallel_v1": (
            naive_parallel_lineage_v1_profile(),
            naive_parallel_structural_v1_profile(),
        ),
        "harness_static_v1": (harness_static_v1_profile(),),
    }


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
