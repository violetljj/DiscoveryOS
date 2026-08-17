from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from discoveryos.operators.action_controller import SearchDecision, SearchState
from discoveryos.util import digest_json, jsonable

from .plugins import PluginSelection, ResearchProfile
from .runtime import HarnessSearchRuntime
from .strategies import (
    ARTIFACTS,
    BUDGET,
    CONTRACT,
    EVALUATOR,
    LEDGER,
    RESEARCH_GRAPH,
    static_composition_profiles,
)


P2_FACTORIAL_FLAGS: tuple[tuple[str, bool, bool], ...] = (
    ("neither", False, False),
    ("ada_only", True, False),
    ("evox_only", False, True),
    ("ada_evox", True, True),
)
_COMMON_PLUGIN_IDS = ("direct_llm", "state_router")
_VARIABLE_PLUGIN_IDS = (
    "local_refinement_control|ada_lineage",
    "structural_escape_control|evox_meta_strategy",
)


def _type_id(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


@dataclass(frozen=True, slots=True)
class P2FactorialProfileAudit:
    status: str
    arm_profile_ids: tuple[tuple[str, str], ...]
    factor_flags: tuple[tuple[str, bool, bool], ...]
    common_plugin_ids: tuple[str, ...]
    allowed_variable_plugin_ids: tuple[str, ...]

    @property
    def digest(self) -> str:
        return digest_json(self)


def audit_p2_factorial_profiles(
    arms: Mapping[str, tuple[ResearchProfile, ...]] | None = None,
) -> P2FactorialProfileAudit:
    resolved = dict(static_composition_profiles() if arms is None else arms)
    expected_arm_ids = tuple(item[0] for item in P2_FACTORIAL_FLAGS)
    if set(resolved) != set(expected_arm_ids):
        raise ValueError("P2 factorial arms must be exactly neither/Ada-only/EvoX-only/Ada+EvoX")

    common_selections: dict[str, PluginSelection] = {}
    profile_ids: list[tuple[str, str]] = []
    for arm_id, ada_enabled, evox_enabled in P2_FACTORIAL_FLAGS:
        profiles = resolved[arm_id]
        if len(profiles) != 1:
            raise ValueError(f"P2 factorial arm must use one unified runtime: {arm_id}")
        profile = profiles[0]
        if profile.adaptive:
            raise ValueError(f"P2 factorial profiles must remain static: {arm_id}")
        expected_plugins = [
            "direct_llm",
            "ada_lineage" if ada_enabled else "local_refinement_control",
            "evox_meta_strategy" if evox_enabled else "structural_escape_control",
        ]
        expected_plugins.append("state_router")
        actual_plugins = [selection.plugin_id for selection in profile.plugins]
        if actual_plugins != expected_plugins:
            raise ValueError(f"P2 factorial profile changes an unauthorized plugin surface: {arm_id}")
        for selection in profile.plugins:
            if selection.plugin_id in _COMMON_PLUGIN_IDS:
                prior = common_selections.setdefault(selection.plugin_id, selection)
                if prior != selection:
                    raise ValueError(
                        f"P2 factorial common plugin binding differs across arms: {selection.plugin_id}"
                    )
        profile_ids.append((arm_id, profile.profile_id))

    if len({profile_id for _, profile_id in profile_ids}) != len(profile_ids):
        raise ValueError("P2 factorial profiles must have distinct content-addressed identities")
    return P2FactorialProfileAudit(
        status="P2_FACTORIAL_PROFILES_REFROZEN",
        arm_profile_ids=tuple(profile_ids),
        factor_flags=P2_FACTORIAL_FLAGS,
        common_plugin_ids=_COMMON_PLUGIN_IDS,
        allowed_variable_plugin_ids=_VARIABLE_PLUGIN_IDS,
    )


@dataclass(frozen=True, slots=True)
class P2ZeroModelRuntimeSurface:
    arm_id: str
    profile_id: str
    ledger_path: str
    authority_topology_valid: bool
    runtime_types: tuple[str, ...]
    contract_digest: str
    evaluator_bindings: tuple[tuple[str, ...], ...]
    evaluator_registry_type: str
    frozen_resource_surface: object
    provider_surface: object
    reservation_surface: object

    @classmethod
    def capture(
        cls,
        *,
        arm_id: str,
        runtime: HarnessSearchRuntime,
        initial_state: SearchState,
    ) -> P2ZeroModelRuntimeSurface:
        decision = runtime.loop.controller.decide(initial_state)
        contract = runtime.session.context.get(CONTRACT)
        artifacts = runtime.session.context.get(ARTIFACTS)
        ledger = runtime.session.context.get(LEDGER)
        graph = runtime.session.context.get(RESEARCH_GRAPH)
        experiment_executor = runtime.session.context.get(BUDGET)
        evaluator_registry = runtime.session.context.get(EVALUATOR)
        authority_objects = [
            runtime.sink.ledger,
            ledger,
            graph.ledger,
            runtime.loop.projector.ledger,
            runtime.loop.executor.ledger,
            runtime.loop.executor.experiment_executor.ledger,
            runtime.loop.trace.ledger,
        ]
        for _, operator in runtime.operator_registry.operators:
            authority_objects.append(operator.ledger)
            strategy_machine = getattr(operator, "strategy_machine", None)
            if strategy_machine is not None:
                authority_objects.append(strategy_machine.ledger)
        authority_topology_valid = (
            len({id(item) for item in authority_objects}) == 1
            and experiment_executor is runtime.loop.executor.experiment_executor
            and evaluator_registry is experiment_executor.registry
            and contract is experiment_executor.contract
            and contract is runtime.loop.projector.contract
            and contract is runtime.loop.executor.contract
            and artifacts is experiment_executor.artifacts
            and artifacts is runtime.loop.projector.artifacts
            and artifacts is runtime.loop.executor.artifacts
            and artifacts is runtime.loop.trace.artifacts
        )
        spec = runtime.loop.projector.spec
        base_controller = runtime.loop.controller.base
        return cls(
            arm_id=arm_id,
            profile_id=runtime.profile.profile_id,
            ledger_path=str(ledger.path.resolve()),
            authority_topology_valid=authority_topology_valid,
            runtime_types=(
                _type_id(runtime),
                _type_id(runtime.loop),
                _type_id(runtime.loop.projector),
                _type_id(runtime.loop.executor),
                _type_id(experiment_executor),
                _type_id(ledger),
                _type_id(graph),
            ),
            contract_digest=runtime.manifest.contract_digest,
            evaluator_bindings=runtime.manifest.evaluator_bindings,
            evaluator_registry_type=_type_id(evaluator_registry),
            frozen_resource_surface=jsonable(
                {
                    "budget": spec.budget,
                    "rungs": spec.rungs,
                    "root_candidate_id": spec.root_candidate_id,
                    "initial_algorithm_family": spec.initial_algorithm_family,
                    "eta": spec.eta,
                    "initial_trials": spec.initial_trials,
                    "local_action_limit": spec.local_action_limit,
                    "structural_action_limit": spec.structural_action_limit,
                    "max_steps": spec.max_steps,
                    "initial_fidelity": spec.initial_fidelity,
                    "mutable_file_paths": spec.mutable_file_paths,
                    "seeds": spec.seeds,
                    "initial_population_candidate_ids": spec.initial_population_candidate_ids,
                    "reusable_components": spec.reusable_components,
                    "parent_selection": spec.parent_selection,
                    "novelty": spec.novelty,
                    "mode": spec.mode,
                    "controller_config": base_controller.config,
                    "task_instance_digest": runtime.manifest.task_instance_digest,
                    "environment_digest": runtime.manifest.environment_digest,
                    "winner_rule_digest": runtime.manifest.winner_rule_digest,
                    "claim_ceiling": runtime.manifest.claim_ceiling,
                }
            ),
            provider_surface=jsonable(
                {
                    "local": runtime.manifest.local_provider,
                    "structural": runtime.manifest.structural_provider,
                    "code_bundle_digest": runtime.manifest.code_bundle_digest,
                    "repository_commit": runtime.manifest.repository_commit,
                    "tracked_source_tree_digest": runtime.manifest.tracked_source_tree_digest,
                }
            ),
            reservation_surface=_reservation_surface(decision),
        )

    @property
    def comparison_digest(self) -> str:
        return digest_json(
            {
                "runtime_types": self.runtime_types,
                "contract_digest": self.contract_digest,
                "evaluator_bindings": self.evaluator_bindings,
                "evaluator_registry_type": self.evaluator_registry_type,
                "frozen_resource_surface": self.frozen_resource_surface,
                "provider_surface": self.provider_surface,
                "reservation_surface": self.reservation_surface,
            }
        )


def _reservation_surface(decision: SearchDecision) -> object:
    return jsonable(
        {
            "action": decision.action,
            "resource_floor": decision.resource_floor,
            "generation_reserve": decision.generation_reserve,
            "evaluation_reserve": decision.evaluation_reserve,
            "settlement_reserve": decision.settlement_reserve,
            "novelty_resample_reserve": decision.novelty_resample_reserve,
            "reserved_downstream_budget": decision.reserved_downstream_budget,
            "budget_reserved": decision.budget_reserved,
            "preflight_affordable": decision.preflight_affordable,
        }
    )


@dataclass(frozen=True, slots=True)
class P2ZeroModelFairnessAudit:
    status: str
    profile_audit_digest: str
    common_runtime_surface_digest: str
    arm_profile_ids: tuple[tuple[str, str], ...]
    ledger_paths: tuple[tuple[str, str], ...]

    @property
    def digest(self) -> str:
        return digest_json(self)


def audit_p2_zero_model_runtime_fairness(
    surfaces: tuple[P2ZeroModelRuntimeSurface, ...],
    *,
    profile_audit: P2FactorialProfileAudit | None = None,
) -> P2ZeroModelFairnessAudit:
    profiles = profile_audit or audit_p2_factorial_profiles()
    by_arm = {surface.arm_id: surface for surface in surfaces}
    expected_arms = tuple(item[0] for item in P2_FACTORIAL_FLAGS)
    if len(by_arm) != len(surfaces) or set(by_arm) != set(expected_arms):
        raise ValueError("zero-model fairness audit requires exactly one surface per factorial arm")
    if any(not surface.authority_topology_valid for surface in surfaces):
        raise ValueError("an arm created a second ledger, graph, evaluator or budget authority")
    if len({surface.ledger_path for surface in surfaces}) != len(surfaces):
        raise ValueError("factorial arms must use isolated job-scoped physical ledgers")
    expected_profile_ids = dict(profiles.arm_profile_ids)
    if any(surface.profile_id != expected_profile_ids[surface.arm_id] for surface in surfaces):
        raise ValueError("runtime surface is not bound to the re-frozen factorial Profile")
    comparison_digests = {surface.comparison_digest for surface in surfaces}
    if len(comparison_digests) != 1:
        raise ValueError("P2 runtime/evaluator/budget/reservation surface differs across arms")
    return P2ZeroModelFairnessAudit(
        status="P2_ZERO_MODEL_FACTORIAL_FAIRNESS_GATE_PASS",
        profile_audit_digest=profiles.digest,
        common_runtime_surface_digest=next(iter(comparison_digests)),
        arm_profile_ids=profiles.arm_profile_ids,
        ledger_paths=tuple((arm_id, by_arm[arm_id].ledger_path) for arm_id in expected_arms),
    )
