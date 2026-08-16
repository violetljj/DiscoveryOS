from __future__ import annotations

import math
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from discoveryos.contracts.executable import ExecutableCandidateBundle, path_is_within
from discoveryos.contracts.models import (
    CandidateSpec,
    DataRole,
    EvidenceRecord,
    EvidenceValidity,
    ExperimentSpec,
    Fidelity,
    GateDecision,
    MetricDirection,
    ProblemContract,
    ResourceBudget,
    ResourceUsage,
    RunMode,
)
from discoveryos.evaluation.gates import GateEngine
from discoveryos.operators.action_controller import (
    ActionControllerConfig,
    AnytimeTraceRecorder,
    DeterministicActionController,
    BranchSearchState,
    CandidateSearchState,
    SearchAction,
    SearchDecision,
    SearchState,
)
from discoveryos.operators.asha import ASHAOperator, RungDefinition
from discoveryos.operators.local_patch import CandidateBuildSpec, LocalPatchOperator
from discoveryos.operators.novelty import (
    NoveltyComparison,
    NoveltyConfig,
    NoveltyDecision,
    NoveltyExhaustion,
    NoveltyReceipt,
    ShinkaStyleNoveltyPolicy,
)
from discoveryos.operators.parent_selection import (
    ParentCandidate,
    ParentSelectionConfig,
    ParentSelectionContext,
)
from discoveryos.operators.structural_rewrite import (
    BasinEscapeBrief,
    LineageSnapshot,
    ReusableComponentReference,
    StructuralRewriteOperator,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ExperimentExecutor
from discoveryos.util import canonical_json, digest_json, jsonable, utc_now


GENERATIVE_ACTIONS = frozenset({SearchAction.LOCAL_PATCH, SearchAction.STRUCTURAL_ESCAPE})


@dataclass(frozen=True, slots=True)
class SearchRunSpec:
    """Frozen run policy. Scientific verdicts remain owned by GateEngine and the contract."""

    run_id: str
    contract_digest: str
    root_candidate_id: str
    branch_id: str
    initial_algorithm_family: str
    metric_name: str
    metric_direction: MetricDirection
    initial_fidelity: Fidelity
    budget: ResourceBudget
    rungs: tuple[RungDefinition, ...]
    eta: int
    initial_trials: int
    local_action_limit: int
    structural_action_limit: int
    max_steps: int
    mutable_file_paths: tuple[str, ...]
    seeds: tuple[int, ...]
    initial_population_candidate_ids: tuple[str, ...] = ()
    reusable_components: tuple[ReusableComponentReference, ...] = ()
    parent_selection: ParentSelectionConfig | None = None
    novelty: NoveltyConfig | None = None
    mode: RunMode = RunMode.DISCOVERY
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        required = (
            self.run_id,
            self.contract_digest,
            self.root_candidate_id,
            self.branch_id,
            self.initial_algorithm_family,
            self.metric_name,
        )
        if not all(required):
            raise ValueError("search run identity, family, and utility metric are required")
        if self.local_action_limit < 1 or self.structural_action_limit < 0 or self.max_steps < 1:
            raise ValueError("search action limits are invalid")
        if self.eta < 2 or self.initial_trials < self.eta:
            raise ValueError("search run requires a valid frozen ASHA capacity")
        if not self.mutable_file_paths or len(set(self.mutable_file_paths)) != len(self.mutable_file_paths):
            raise ValueError("search run requires unique visible mutable files")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or any(seed < 0 for seed in self.seeds):
            raise ValueError("search seeds must be unique non-negative integers")
        if len(self.rungs) < 2 or any(
            left.fidelity.rank >= right.fidelity.rank for left, right in zip(self.rungs, self.rungs[1:])
        ):
            raise ValueError("search rungs must contain increasing fidelities")
        if self.initial_fidelity not in {rung.fidelity for rung in self.rungs}:
            raise ValueError("initial fidelity must be an ASHA rung")
        if len(set(self.initial_population_candidate_ids)) != len(self.initial_population_candidate_ids):
            raise ValueError("initial population candidate ids must be unique")

    @property
    def digest(self) -> str:
        return digest_json(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SearchRunSpec":
        return cls(
            run_id=str(payload["run_id"]),
            contract_digest=str(payload["contract_digest"]),
            root_candidate_id=str(payload["root_candidate_id"]),
            branch_id=str(payload["branch_id"]),
            initial_algorithm_family=str(payload["initial_algorithm_family"]),
            metric_name=str(payload["metric_name"]),
            metric_direction=MetricDirection(str(payload["metric_direction"])),
            initial_fidelity=Fidelity(str(payload["initial_fidelity"])),
            budget=ResourceBudget(**dict(payload["budget"])),
            rungs=tuple(
                RungDefinition(
                    rung_id=str(item["rung_id"]),
                    fidelity=Fidelity(str(item["fidelity"])),
                    resources=ResourceBudget(**dict(item["resources"])),
                )
                for item in payload["rungs"]
            ),
            eta=int(payload["eta"]),
            initial_trials=int(payload["initial_trials"]),
            local_action_limit=int(payload["local_action_limit"]),
            structural_action_limit=int(payload["structural_action_limit"]),
            max_steps=int(payload["max_steps"]),
            mutable_file_paths=tuple(str(item) for item in payload["mutable_file_paths"]),
            seeds=tuple(int(item) for item in payload["seeds"]),
            initial_population_candidate_ids=tuple(
                str(item) for item in payload.get("initial_population_candidate_ids", ())
            ),
            reusable_components=tuple(
                ReusableComponentReference.from_dict(dict(item))
                for item in payload.get("reusable_components", ())
            ),
            parent_selection=(
                ParentSelectionConfig(**dict(payload["parent_selection"]))
                if payload.get("parent_selection")
                else None
            ),
            novelty=(
                NoveltyConfig(
                    **{
                        **dict(payload["novelty"]),
                        "exhaustion": NoveltyExhaustion(str(dict(payload["novelty"])["exhaustion"])),
                    }
                )
                if payload.get("novelty")
                else None
            ),
            mode=RunMode(str(payload["mode"])),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class SearchActionResult:
    decision_id: str
    run_id: str
    step: int
    state_digest: str
    action: SearchAction
    source_candidate_id: str
    result_candidate_id: str | None
    evidence_receipt_id: str | None
    generation_id: str | None
    actual_usage: ResourceUsage
    failure_signature: str | None = None
    generation_ids: tuple[str, ...] = ()
    novelty_receipt_ids: tuple[str, ...] = ()
    completed_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SearchActionResult":
        return cls(
            decision_id=str(payload["decision_id"]),
            run_id=str(payload["run_id"]),
            step=int(payload["step"]),
            state_digest=str(payload["state_digest"]),
            action=SearchAction(str(payload["action"])),
            source_candidate_id=str(payload["source_candidate_id"]),
            result_candidate_id=str(payload["result_candidate_id"]) if payload.get("result_candidate_id") else None,
            evidence_receipt_id=str(payload["evidence_receipt_id"]) if payload.get("evidence_receipt_id") else None,
            generation_id=str(payload["generation_id"]) if payload.get("generation_id") else None,
            actual_usage=ResourceUsage(**dict(payload["actual_usage"])),
            failure_signature=str(payload["failure_signature"]) if payload.get("failure_signature") else None,
            generation_ids=tuple(str(item) for item in payload.get("generation_ids", ())),
            novelty_receipt_ids=tuple(str(item) for item in payload.get("novelty_receipt_ids", ())),
            completed_at=str(payload["completed_at"]),
        )


@dataclass(frozen=True, slots=True)
class SearchLoopResult:
    run_id: str
    stop_decision: SearchDecision
    settled_steps: int
    incumbent_candidate_id: str
    incumbent_utility: float
    trace_ids: tuple[str, ...]


@dataclass(slots=True)
class _ProjectionFacts:
    results: tuple[SearchActionResult, ...]
    candidates: dict[str, CandidateSpec]
    evidence_by_candidate: dict[str, tuple[EvidenceRecord, ...]]
    family_by_candidate: dict[str, str]
    current_candidate_id: str
    local_results_since_escape: tuple[SearchActionResult, ...]


class LedgerBackedSearchStateProjector:
    """Builds controller state only from frozen run policy and ledger-bound facts."""

    def __init__(
        self,
        *,
        spec: SearchRunSpec,
        contract: ProblemContract,
        controller_config: ActionControllerConfig,
        ledger: EvidenceLedger,
        artifacts: ArtifactStore,
    ) -> None:
        if spec.contract_digest != contract.digest:
            raise ValueError("search run is not bound to the supplied problem contract")
        definitions = {metric.name: metric for metric in contract.metrics}
        if spec.metric_name not in definitions or definitions[spec.metric_name].direction is not spec.metric_direction:
            raise ValueError("scheduling utility is not bound to the frozen metric definition")
        if any(not path_is_within(path, contract.mutable_paths) for path in spec.mutable_file_paths):
            raise ValueError("visible search files must be within the mutable contract")
        if any(path_is_within(path, contract.forbidden_paths) for path in spec.mutable_file_paths):
            raise ValueError("visible search files overlap forbidden contract paths")
        self.spec = spec
        self.contract = contract
        self.controller_config = controller_config
        self.ledger = ledger
        self.artifacts = artifacts
        self.gate = GateEngine()
        self.ledger.get_candidate(spec.root_candidate_id)
        for candidate_id in spec.initial_population_candidate_ids:
            self.ledger.get_candidate(candidate_id)
        self.ledger.add_search_run(spec.run_id, jsonable(spec))

    def build(self) -> SearchState:
        if self.ledger.get_search_run(self.spec.run_id) != jsonable(self.spec):
            raise ValueError("stored search run differs from the frozen run specification")
        facts = self._facts()
        elapsed = ResourceUsage()
        remaining = self.spec.budget
        for result in facts.results:
            elapsed = _add_usage(elapsed, result.actual_usage)
            remaining = _consume(remaining, result.actual_usage)
        candidate_states = self._candidate_states(facts)
        utilities = {
            item.candidate_id: item.scheduling_utility
            for item in candidate_states
            if item.scheduling_utility is not None
        }
        if not utilities:
            raise ValueError("search state requires at least one ledger-backed scheduling utility")
        incumbent_id = min(
            utilities,
            key=lambda candidate_id: (
                -utilities[candidate_id]
                if self.spec.metric_direction is MetricDirection.MAXIMIZE
                else utilities[candidate_id],
                candidate_id,
            ),
        )
        recent_improvements = self._recent_improvements(facts)
        generations_since_improvement = 0
        for improvement in reversed(recent_improvements):
            if improvement > self.controller_config.improvement_epsilon:
                break
            generations_since_improvement += 1
        local_count = len(facts.local_results_since_escape)
        structural_count = sum(result.action is SearchAction.STRUCTURAL_ESCAPE for result in facts.results)
        failure_signatures = tuple(
            dict.fromkeys(
                result.failure_signature
                for result in facts.local_results_since_escape
                if result.failure_signature
            )
        )
        if generations_since_improvement >= self.controller_config.stagnation_generations:
            failure_signatures = tuple(dict.fromkeys((*failure_signatures, "LOCAL_BASIN_PLATEAU")))
        active = len(facts.results) < self.spec.max_steps and any(remaining.as_dict().values())
        branch = BranchSearchState(
            branch_id=self.spec.branch_id,
            lineage_root_id=self.spec.root_candidate_id,
            parent_candidate_id=facts.current_candidate_id,
            algorithm_family=facts.family_by_candidate[facts.current_candidate_id],
            generations_since_improvement=generations_since_improvement,
            recent_improvements=recent_improvements,
            recent_delta_similarity=self._recent_delta_similarity(facts),
            lineage_receipt_ids=tuple(
                evidence.receipt_id
                for candidate_id in facts.candidates
                for evidence in facts.evidence_by_candidate.get(candidate_id, ())
            ),
            failure_signatures=failure_signatures,
            local_actions_remaining=max(0, self.spec.local_action_limit - local_count),
            structural_actions_remaining=max(0, self.spec.structural_action_limit - structural_count),
            active=active,
        )
        return SearchState(
            run_id=self.spec.run_id,
            step=len(facts.results),
            incumbent_candidate_id=incumbent_id,
            incumbent_utility=utilities[incumbent_id],
            utility_metric_name=self.spec.metric_name,
            metric_direction=self.spec.metric_direction,
            candidates=tuple(candidate_states),
            branches=(branch,),
            reusable_component_ids=tuple(component.component_id for component in self.spec.reusable_components),
            remaining_budget=remaining,
            elapsed_usage=elapsed,
            parent_selection_context=self._parent_selection_context(
                facts,
                tuple(candidate_states),
                incumbent_id,
            ),
        )

    def _parent_selection_context(
        self,
        facts: _ProjectionFacts,
        states: tuple[CandidateSearchState, ...],
        incumbent_id: str,
    ) -> ParentSelectionContext | None:
        config = self.spec.parent_selection
        if config is None:
            return None
        exposures: dict[str, int] = {}
        for payload in self.ledger.parent_selection_receipt_payloads(self.spec.run_id):
            for candidate_id in payload.get("selected_parent_ids", ()):
                exposures[str(candidate_id)] = exposures.get(str(candidate_id), 0) + 1
        state_by_id = {item.candidate_id: item for item in states}
        improvements: dict[str, list[float]] = {candidate_id: [] for candidate_id in facts.candidates}
        for result in facts.results:
            if result.action not in GENERATIVE_ACTIONS or result.result_candidate_id is None:
                continue
            before = self._utility(facts.evidence_by_candidate.get(result.source_candidate_id, ()))
            after = self._utility(facts.evidence_by_candidate.get(result.result_candidate_id, ()))
            if before is None or after is None:
                delta = 0.0
            elif self.spec.metric_direction is MetricDirection.MAXIMIZE:
                delta = after - before
            else:
                delta = before - after
            improvements.setdefault(result.source_candidate_id, []).append(delta)
        return ParentSelectionContext(
            run_id=self.spec.run_id,
            step=len(facts.results),
            metric_direction=self.spec.metric_direction,
            candidates=tuple(
                ParentCandidate(
                    candidate_id=candidate_id,
                    fitness=state_by_id[candidate_id].scheduling_utility,
                    valid=state_by_id[candidate_id].feasible,
                    generation=self._candidate_generation(facts, candidate_id),
                    parent_exposure_count=exposures.get(candidate_id, 0),
                    improvement_history=tuple(improvements.get(candidate_id, ())),
                    archive=bool(facts.evidence_by_candidate.get(candidate_id)),
                    incumbent=candidate_id == incumbent_id,
                    lineage_root_id=None,
                    lineage_ids=self._candidate_lineage(facts, candidate_id),
                )
                for candidate_id in facts.candidates
            ),
            seed=config.base_seed + len(facts.results),
            policy_version=config.policy_version,
        )

    @staticmethod
    def _candidate_generation(facts: _ProjectionFacts, candidate_id: str) -> int:
        generation = 0
        current = candidate_id
        seen: set[str] = set()
        while current != next(iter(facts.candidates)):
            if current in seen:
                raise ValueError("candidate lineage contains a cycle")
            seen.add(current)
            parent = next(
                (item for item in facts.candidates[current].parent_ids if item in facts.candidates),
                None,
            )
            if parent is None:
                break
            generation += 1
            current = parent
        return generation

    @staticmethod
    def _candidate_lineage(facts: _ProjectionFacts, candidate_id: str) -> tuple[str, ...]:
        lineage = [candidate_id]
        current = candidate_id
        seen: set[str] = set()
        while True:
            if current in seen:
                raise ValueError("candidate lineage contains a cycle")
            seen.add(current)
            parent = next(
                (item for item in facts.candidates[current].parent_ids if item in facts.candidates),
                None,
            )
            if parent is None:
                break
            lineage.append(parent)
            current = parent
        return tuple(reversed(lineage))

    def novelty_comparisons(
        self,
        state: SearchState,
        selected_parent_id: str,
    ) -> tuple[NoveltyComparison, ...]:
        facts = self._facts()
        recent_ids = tuple(
            result.result_candidate_id
            for result in facts.results[-5:]
            if result.result_candidate_id is not None
        )
        comparisons: list[NoveltyComparison] = []
        for candidate_id, candidate in facts.candidates.items():
            scopes = {"archive"}
            if candidate_id == selected_parent_id:
                scopes.add("selected_parent")
            if candidate_id == state.incumbent_candidate_id:
                scopes.add("incumbent")
            if candidate_id in recent_ids:
                scopes.add("recent")
            try:
                code = self._candidate_mutable_code(candidate)
            except RuntimeError as error:
                self.ledger.record_event(
                    "NOVELTY_COMPARISON_SKIPPED_UNMATERIALIZABLE",
                    {
                        "run_id": self.spec.run_id,
                        "step": state.step,
                        "candidate_id": candidate_id,
                        "failure_signature": _materialization_failure_signature(
                            "NOVELTY_COMPARISON_MATERIALIZATION_FAILED",
                            error,
                        ),
                    },
                )
                continue
            comparisons.append(
                NoveltyComparison(
                    candidate_id=candidate_id,
                    scopes=tuple(sorted(scopes)),
                    code=code,
                )
            )
        return tuple(comparisons)

    def _candidate_mutable_code(self, candidate: CandidateSpec) -> str:
        bundle = ExecutableCandidateBundle.from_artifact(self.artifacts, candidate.artifact_digest)
        files = _materialize_files(bundle, self.spec.mutable_file_paths)
        return "\n".join(f"# FILE:{path}\n{files[path]}" for path in sorted(files))

    def evidence_summary(self, candidate_id: str) -> str:
        facts = self._facts()
        rows = [
            {
                "receipt_id": evidence.receipt_id,
                "fidelity": evidence.fidelity.value,
                "metrics": evidence.metric_dict(),
                "validity": evidence.validity.value,
                "failure_signature": evidence.failure_signature,
            }
            for evidence in facts.evidence_by_candidate.get(candidate_id, ())
        ]
        return canonical_json({"candidate_id": candidate_id, "development_evidence": rows})

    def semantic_memory(self) -> tuple[str, ...]:
        facts = self._facts()
        return tuple(candidate.semantic_delta for candidate in facts.candidates.values())

    def basin_escape_brief(self, state: SearchState, decision: SearchDecision) -> BasinEscapeBrief:
        if decision.action is not SearchAction.STRUCTURAL_ESCAPE or decision.candidate_id is None:
            raise ValueError("basin brief requires a structural decision")
        facts = self._facts()
        lineage_ids = self._lineage_ids(facts, decision.candidate_id)
        if len(lineage_ids) < 2:
            raise ValueError("structural escape requires a materialized parent lineage")
        lineage: list[LineageSnapshot] = []
        for candidate_id in lineage_ids:
            candidate = facts.candidates[candidate_id]
            family = facts.family_by_candidate[candidate_id]
            family_digest = self.artifacts.put_json(
                {"candidate_id": candidate_id, "algorithm_family": family},
                metadata={"kind": "algorithm-family-label-v1"},
            )
            receipts = tuple(
                evidence.receipt_id for evidence in facts.evidence_by_candidate.get(candidate_id, ())
            )
            if not receipts:
                raise ValueError(f"lineage candidate lacks ledger evidence: {candidate_id}")
            lineage.append(
                LineageSnapshot(
                    candidate_id=candidate_id,
                    algorithm_family=family,
                    family_label_digest=family_digest,
                    semantic_delta=candidate.semantic_delta,
                    evidence_receipt_ids=receipts,
                    evidence_summary=self.evidence_summary(candidate_id),
                )
            )
        rejected = tuple(
            facts.candidates[result.result_candidate_id].semantic_delta
            for result in facts.local_results_since_escape
            if result.result_candidate_id is not None
        )
        return BasinEscapeBrief(
            lineage=tuple(lineage),
            stagnation_reason=(
                f"{state.branches[0].generations_since_improvement} consecutive generative actions "
                "did not improve scheduling utility"
            ),
            failure_signatures=state.branches[0].failure_signatures,
            rejected_local_deltas=tuple(dict.fromkeys(rejected)),
            reusable_components=tuple(
                component
                for component in self.spec.reusable_components
                if component.component_id in set(decision.reusable_component_ids)
            ),
        )

    def _facts(self) -> _ProjectionFacts:
        stored_results = tuple(
            SearchActionResult.from_dict(payload)
            for payload in self.ledger.search_action_payloads(self.spec.run_id)
        )
        all_candidates = {candidate.candidate_id: candidate for candidate in self.ledger.candidate_records()}
        all_evidence = self.ledger.evidence_records()
        all_experiments = {item.experiment_id: item for item in self.ledger.experiment_records()}
        current = self.spec.root_candidate_id
        scoped_ids = [current]
        family_by_candidate = {current: self.spec.initial_algorithm_family}
        last_escape_index = -1
        for index, result in enumerate(stored_results):
            if result.run_id != self.spec.run_id or result.step != index:
                raise ValueError("search action history is not contiguous")
            if result.source_candidate_id not in scoped_ids:
                raise ValueError("search action source is outside the ledger-backed archive")
            if result.result_candidate_id is not None:
                candidate = all_candidates.get(result.result_candidate_id)
                if candidate is None:
                    raise ValueError("search action references an unknown result candidate")
                if result.action in GENERATIVE_ACTIONS:
                    if result.source_candidate_id not in candidate.parent_ids:
                        raise ValueError("generated candidate is not derived from the selected parent")
                    family = family_by_candidate[result.source_candidate_id]
                    if result.action is SearchAction.STRUCTURAL_ESCAPE:
                        family = str(candidate.parameter_dict().get("target_algorithm_family", "")).strip()
                        if not family:
                            raise ValueError("structural result lacks a frozen target family")
                        last_escape_index = index
                    family_by_candidate[candidate.candidate_id] = family
                    current = candidate.candidate_id
                    scoped_ids.append(current)
                elif result.result_candidate_id != current:
                    raise ValueError("evaluation-only action changed candidate identity")
            if result.evidence_receipt_id is not None:
                evidence = next(
                    (item for item in all_evidence if item.receipt_id == result.evidence_receipt_id),
                    None,
                )
                if evidence is None or evidence.candidate_id != (result.result_candidate_id or current):
                    raise ValueError("search action evidence is not bound to its result candidate")
                experiment = all_experiments[evidence.experiment_id]
                if experiment.contract_digest != self.contract.digest:
                    raise ValueError("search action evidence belongs to another contract")
        candidates = {candidate_id: all_candidates[candidate_id] for candidate_id in scoped_ids}
        evidence_by_candidate = {
            candidate_id: tuple(
                evidence
                for evidence in all_evidence
                if evidence.candidate_id == candidate_id
                and all_experiments[evidence.experiment_id].contract_digest == self.contract.digest
            )
            for candidate_id in scoped_ids
        }
        local_since_escape = tuple(
            result
            for result in stored_results[last_escape_index + 1 :]
            if result.action is SearchAction.LOCAL_PATCH
        )
        return _ProjectionFacts(
            results=stored_results,
            candidates=candidates,
            evidence_by_candidate=evidence_by_candidate,
            family_by_candidate=family_by_candidate,
            current_candidate_id=current,
            local_results_since_escape=local_since_escape,
        )

    def _candidate_states(self, facts: _ProjectionFacts) -> list[CandidateSearchState]:
        promotions = self._promotion_targets(facts)
        states: list[CandidateSearchState] = []
        for candidate_id in facts.candidates:
            evidence = facts.evidence_by_candidate.get(candidate_id, ())
            if evidence:
                fidelity = max((item.fidelity for item in evidence), key=lambda item: item.rank)
            else:
                fidelity = self.spec.initial_fidelity
            at_fidelity = tuple(item for item in evidence if item.fidelity is fidelity)
            feasible = tuple(
                item
                for item in at_fidelity
                if self.gate.evaluate(self.contract, item).decision is GateDecision.FEASIBLE
                and self.spec.metric_name in item.metric_dict()
            )
            values = tuple(item.metric_dict()[self.spec.metric_name] for item in feasible)
            utility = statistics.fmean(values) if values else None
            uncertainty = (
                1.0
                if len(values) < self.controller_config.minimum_replicates
                else (statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0)
            )
            target = promotions.get((candidate_id, fidelity))
            states.append(
                CandidateSearchState(
                    candidate_id=candidate_id,
                    branch_id=self.spec.branch_id,
                    fidelity=fidelity,
                    latest_evidence_receipt_id=at_fidelity[-1].receipt_id if at_fidelity else None,
                    scheduling_utility=utility,
                    resource_consumed=_sum_usage(item.resource_usage for item in evidence),
                    uncertainty=uncertainty,
                    replicate_count=len(values),
                    feasible=bool(values),
                    promotion_eligible=target is not None,
                    promotion_target=target,
                    active=candidate_id == facts.current_candidate_id,
                )
            )
        return states

    def _promotion_targets(self, facts: _ProjectionFacts) -> dict[tuple[str, Fidelity], Fidelity]:
        asha = ASHAOperator(
            run_id=self.spec.run_id,
            contract=self.contract,
            rungs=self.spec.rungs,
            metric_name=self.spec.metric_name,
            eta=self.spec.eta,
            initial_trials=self.spec.initial_trials,
        )
        scoped = set(facts.candidates) | set(self.spec.initial_population_candidate_ids)
        experiments = {item.experiment_id: item for item in self.ledger.experiment_records()}
        targets: dict[tuple[str, Fidelity], Fidelity] = {}
        rung_ids = {rung.rung_id for rung in self.spec.rungs}
        for evidence in self.ledger.evidence_records():
            experiment = experiments[evidence.experiment_id]
            if (
                evidence.candidate_id not in scoped
                or experiment.contract_digest != self.contract.digest
                or experiment.rung_id not in rung_ids
            ):
                continue
            for record in asha.observe(evidence, experiment):
                source = asha.rung_for(record.source_rung_id).fidelity
                target = asha.rung_for(record.target_rung_id).fidelity
                targets[(record.candidate_id, source)] = target
        return targets

    def _recent_improvements(self, facts: _ProjectionFacts) -> tuple[float, ...]:
        values: list[float] = []
        for result in facts.results:
            if result.action is SearchAction.STRUCTURAL_ESCAPE:
                values.clear()
            if result.action not in GENERATIVE_ACTIONS or result.result_candidate_id is None:
                continue
            before = self._utility(facts.evidence_by_candidate.get(result.source_candidate_id, ()))
            after = self._utility(facts.evidence_by_candidate.get(result.result_candidate_id, ()))
            if before is None or after is None:
                improvement = 0.0
            elif self.spec.metric_direction is MetricDirection.MAXIMIZE:
                improvement = after - before
            else:
                improvement = before - after
            values.append(improvement)
        return tuple(values)

    def _recent_delta_similarity(self, facts: _ProjectionFacts) -> float:
        deltas = [
            facts.candidates[result.result_candidate_id].semantic_delta
            for result in facts.local_results_since_escape
            if result.result_candidate_id is not None
        ]
        if len(deltas) < 2:
            return 0.0
        left = set(deltas[-2].casefold().split())
        right = set(deltas[-1].casefold().split())
        return len(left & right) / len(left | right) if left or right else 1.0

    def _utility(self, evidence: tuple[EvidenceRecord, ...]) -> float | None:
        if not evidence:
            return None
        fidelity = max((item.fidelity for item in evidence), key=lambda item: item.rank)
        values = [
            item.metric_dict()[self.spec.metric_name]
            for item in evidence
            if item.fidelity is fidelity
            and self.gate.evaluate(self.contract, item).decision is GateDecision.FEASIBLE
            and self.spec.metric_name in item.metric_dict()
        ]
        return statistics.fmean(values) if values else None

    @staticmethod
    def _lineage_ids(facts: _ProjectionFacts, candidate_id: str) -> tuple[str, ...]:
        lineage: list[str] = []
        current = candidate_id
        while True:
            lineage.append(current)
            if current == next(iter(facts.candidates)):
                break
            candidate = facts.candidates[current]
            parent = next((item for item in candidate.parent_ids if item in facts.candidates), None)
            if parent is None:
                raise ValueError("search lineage is not contiguous to the root")
            current = parent
        return tuple(lineage)


class UnifiedActionExecutor:
    """Executes controller decisions; it does not select actions or declare scientific winners."""

    def __init__(
        self,
        *,
        spec: SearchRunSpec,
        contract: ProblemContract,
        ledger: EvidenceLedger,
        artifacts: ArtifactStore,
        projector: LedgerBackedSearchStateProjector,
        local_operator: LocalPatchOperator,
        structural_operator: StructuralRewriteOperator,
        experiment_executor: ExperimentExecutor,
        novelty_policy: ShinkaStyleNoveltyPolicy | None = None,
    ) -> None:
        self.spec = spec
        self.contract = contract
        self.ledger = ledger
        self.artifacts = artifacts
        self.projector = projector
        self.local_operator = local_operator
        self.structural_operator = structural_operator
        self.experiment_executor = experiment_executor
        self.novelty_policy = novelty_policy
        if (self.spec.novelty is None) != (self.novelty_policy is None):
            raise ValueError("search spec and novelty policy enablement must match")
        if self.novelty_policy is not None:
            if self.novelty_policy.config != self.spec.novelty:
                raise ValueError("novelty policy differs from the frozen search spec")
            for action in GENERATIVE_ACTIONS:
                cost = self.projector.controller_config.cost_for(action)
                if cost is None:
                    raise ValueError(f"missing novelty action cost: {action.value}")
                required = _scale_budget(
                    cost.generation_reserve,
                    self.novelty_policy.config.max_novelty_attempts - 1,
                )
                if (
                    not self.novelty_policy.config.affordability_gate
                    and not _affords_budget(cost.novelty_resample_reserve, required)
                ):
                    raise ValueError(
                        f"{action.value} novelty retry reserve does not cover the frozen worst case"
                    )

    async def execute(self, decision: SearchDecision, state: SearchState) -> SearchActionResult:
        if decision.action is SearchAction.STOP:
            raise ValueError("STOP is finalized by SearchLoopRunner, not the action executor")
        if decision.state_digest != state.digest or decision.step != state.step or decision.run_id != self.spec.run_id:
            raise ValueError("action decision is not bound to the current projected state")
        if decision.candidate_id is None:
            raise ValueError("executable search action requires a candidate")
        if not decision.preflight_affordable:
            raise ValueError("an action rejected by budget preflight cannot be executed")
        source = self.ledger.get_candidate(decision.candidate_id)
        result_candidate: CandidateSpec | None = source
        evidence: EvidenceRecord | None = None
        generation_id: str | None = None
        generation_usages: list[ResourceUsage] = []
        novelty_usages: list[ResourceUsage] = []
        generation_ids: list[str] = []
        novelty_receipt_ids: list[str] = []
        failure_signature: str | None = None
        if decision.parent_selection_receipt is not None:
            receipt = decision.parent_selection_receipt
            self.ledger.add_parent_selection_receipt(
                receipt_id=receipt.receipt_id,
                run_id=receipt.run_id,
                step=receipt.step,
                payload=jsonable(receipt),
            )
        if decision.action in GENERATIVE_ACTIONS:
            result_candidate = None
            bundle = ExecutableCandidateBundle.from_artifact(self.artifacts, source.artifact_digest)
            build = _build_spec(bundle)
            try:
                mutable_files = _materialize_files(bundle, self.spec.mutable_file_paths)
            except RuntimeError as error:
                failure_signature = _materialization_failure_signature(
                    "SOURCE_CANDIDATE_MATERIALIZATION_FAILED",
                    error,
                )
                result = SearchActionResult(
                    decision_id=decision.decision_id,
                    run_id=decision.run_id,
                    step=decision.step,
                    state_digest=decision.state_digest,
                    action=decision.action,
                    source_candidate_id=source.candidate_id,
                    result_candidate_id=None,
                    evidence_receipt_id=None,
                    generation_id=None,
                    actual_usage=ResourceUsage(),
                    failure_signature=failure_signature,
                )
                self.ledger.add_search_action(
                    decision_id=result.decision_id,
                    run_id=result.run_id,
                    step=result.step,
                    payload=jsonable(result),
                )
                self.ledger.record_event("SEARCH_ACTION_EXECUTED", jsonable(result))
                return result
            generation_budget = (
                decision.generation_reserve
                if any(decision.generation_reserve.as_dict().values())
                else decision.resource_floor
            )
            max_attempts = (
                self.novelty_policy.config.max_novelty_attempts
                if self.novelty_policy is not None
                else 1
            )
            comparisons = (
                self.projector.novelty_comparisons(state, source.candidate_id)
                if self.novelty_policy is not None
                else ()
            )
            novelty_feedback: list[str] = []
            for attempt in range(1, max_attempts + 1):
                memory = (*self.projector.semantic_memory(), *novelty_feedback)
                if decision.action is SearchAction.LOCAL_PATCH:
                    generated = self.local_operator.propose(
                        parent=source,
                        mutable_files=mutable_files,
                        development_evidence_summary=self.projector.evidence_summary(source.candidate_id),
                        failure_signature=state.branches[0].failure_signatures[-1]
                        if state.branches[0].failure_signatures
                        else None,
                        semantic_delta_memory=memory,
                        remaining_budget=generation_budget,
                        build=build,
                        request_nonce=f"{self.spec.run_id}:{state.step}:{attempt}",
                    )
                else:
                    generated = self.structural_operator.propose(
                        parent=source,
                        mutable_files=mutable_files,
                        development_evidence_summary=self.projector.evidence_summary(source.candidate_id),
                        semantic_delta_memory=memory,
                        remaining_budget=generation_budget,
                        build=build,
                        brief=self.projector.basin_escape_brief(state, decision),
                        request_nonce=f"{self.spec.run_id}:{state.step}:{attempt}",
                    )
                generation_id = generated.record.generation_id
                generation_ids.append(generation_id)
                generation_usages.append(generated.record.usage)
                failure_signature = generated.record.failure_signature
                proposal = generated.candidate
                if proposal is None or self.novelty_policy is None:
                    result_candidate = proposal
                    break
                try:
                    proposal_code = self.projector._candidate_mutable_code(proposal)
                except RuntimeError as error:
                    failure_signature = _materialization_failure_signature(
                        "NOVELTY_PROPOSAL_MATERIALIZATION_FAILED",
                        error,
                    )
                    self.ledger.record_event(
                        "NOVELTY_PROPOSAL_MATERIALIZATION_FAILED",
                        {
                            "run_id": self.spec.run_id,
                            "step": state.step,
                            "attempt": attempt,
                            "generation_id": generation_id,
                            "proposal_candidate_id": proposal.candidate_id,
                            "failure_signature": failure_signature,
                        },
                    )
                    break
                wall_start = time.perf_counter()
                cpu_start = time.process_time()
                assessment = self.novelty_policy.assess(
                    proposal_code,
                    comparisons,
                    attempt=attempt,
                )
                assessment = self.novelty_policy.resolve_resampling(
                    assessment,
                    generation_reserve=decision.generation_reserve,
                    evaluation_reserve=decision.evaluation_reserve,
                    remaining_resample_budget=_sum_budgets(
                        decision.novelty_resample_reserve,
                        decision.evaluation_reserve,
                    ),
                )
                novelty_usage = ResourceUsage(
                    cpu_seconds=max(0.0, time.process_time() - cpu_start),
                    wall_seconds=max(0.0, time.perf_counter() - wall_start),
                )
                novelty_usages.append(novelty_usage)
                novelty_receipt = NoveltyReceipt.create(
                    run_id=self.spec.run_id,
                    step=state.step,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    source_candidate_id=source.candidate_id,
                    proposal_candidate_id=proposal.candidate_id,
                    proposal_code=proposal_code,
                    comparisons=comparisons,
                    assessment=assessment,
                    policy_version=self.novelty_policy.config.policy_version,
                    usage=novelty_usage,
                )
                self.ledger.add_novelty_receipt(
                    receipt_id=novelty_receipt.receipt_id,
                    run_id=self.spec.run_id,
                    step=state.step,
                    attempt=attempt,
                    payload=jsonable(novelty_receipt),
                )
                novelty_receipt_ids.append(novelty_receipt.receipt_id)
                if assessment.decision is NoveltyDecision.ACCEPT:
                    result_candidate = proposal
                    break
                failure_signature = (
                    "NOVELTY_ATTEMPTS_EXHAUSTED"
                    if assessment.decision is NoveltyDecision.REJECT_EXHAUSTED
                    else "NOVELTY_DUPLICATE_REJECTED"
                )
                if assessment.decision in {
                    NoveltyDecision.REJECT_EXHAUSTED,
                    NoveltyDecision.REJECT_STOP,
                }:
                    break
                novelty_feedback.append(
                    f"NOVELTY_REJECTED_ATTEMPT_{attempt}: avoid repeating proposal "
                    f"{proposal.candidate_id}; reasons={','.join(assessment.reason_codes)}"
                )
                comparisons = (
                    *comparisons,
                    NoveltyComparison(
                        candidate_id=proposal.candidate_id,
                        scopes=("rejected_in_action",),
                        code=proposal_code,
                    ),
                )
        if result_candidate is not None:
            fidelity = decision.fidelity or self.spec.initial_fidelity
            evidence = await self._evaluate(
                candidate=result_candidate,
                fidelity=fidelity,
                action=decision.action,
            )
            failure_signature = evidence.failure_signature or failure_signature
        actual_usage = _sum_usage(
            (
                *generation_usages,
                *novelty_usages,
                *((evidence.resource_usage,) if evidence is not None else ()),
            )
        )
        result = SearchActionResult(
            decision_id=decision.decision_id,
            run_id=decision.run_id,
            step=decision.step,
            state_digest=decision.state_digest,
            action=decision.action,
            source_candidate_id=source.candidate_id,
            result_candidate_id=result_candidate.candidate_id if result_candidate is not None else None,
            evidence_receipt_id=evidence.receipt_id if evidence is not None else None,
            generation_id=generation_id,
            actual_usage=actual_usage,
            failure_signature=failure_signature,
            generation_ids=tuple(generation_ids),
            novelty_receipt_ids=tuple(novelty_receipt_ids),
        )
        self.ledger.add_search_action(
            decision_id=result.decision_id,
            run_id=result.run_id,
            step=result.step,
            payload=jsonable(result),
        )
        self.ledger.record_event("SEARCH_ACTION_EXECUTED", jsonable(result))
        return result

    async def _evaluate(
        self,
        *,
        candidate: CandidateSpec,
        fidelity: Fidelity,
        action: SearchAction,
    ) -> EvidenceRecord:
        rung = next((item for item in self.spec.rungs if item.fidelity is fidelity), None)
        if rung is None:
            raise ValueError(f"no frozen search rung for fidelity {fidelity.value}")
        prior = [
            self.ledger.get_experiment(evidence.experiment_id)
            for evidence in self.ledger.evidence_records()
            if evidence.candidate_id == candidate.candidate_id and evidence.fidelity is fidelity
        ]
        if action is SearchAction.PROMOTE_FIDELITY:
            source_experiments = [
                self.ledger.get_experiment(evidence.experiment_id)
                for evidence in self.ledger.evidence_records()
                if evidence.candidate_id == candidate.candidate_id and evidence.fidelity.rank < fidelity.rank
            ]
            if not source_experiments:
                raise ValueError("promotion requires ledger-bound source evidence")
            source_experiment = max(source_experiments, key=lambda item: item.fidelity.rank)
            seed = source_experiment.seed
            trial_id = source_experiment.trial_id
            replicate_id = source_experiment.replicate_id
            parent_trial_id = source_experiment.trial_id
            promotion_reason = "ASHA-authorized controller promotion"
        else:
            used_seeds = {item.seed for item in prior}
            try:
                seed = next(seed for seed in self.spec.seeds if seed not in used_seeds)
            except StopIteration as error:
                raise ValueError("frozen replicate seeds are exhausted") from error
            trial_id = None
            replicate_id = f"seed-{seed}"
            parent_trial_id = None
            promotion_reason = None
        split_id, split_role = _split_for_fidelity(self.contract, fidelity)
        experiment = ExperimentSpec.create(
            candidate_id=candidate.candidate_id,
            evaluator_id=self.contract.evaluator_id_for(fidelity),
            fidelity=fidelity,
            split_id=split_id,
            split_role=split_role,
            seed=seed,
            resources=rung.resources,
            contract_digest=self.contract.digest,
            mode=self.spec.mode,
            trial_id=trial_id,
            replicate_id=replicate_id,
            rung_id=rung.rung_id,
            parent_trial_id=parent_trial_id,
            promotion_reason=promotion_reason,
        )
        return await self.experiment_executor.execute(candidate, experiment)


class SearchLoopRunner:
    def __init__(
        self,
        *,
        controller: DeterministicActionController,
        projector: LedgerBackedSearchStateProjector,
        executor: UnifiedActionExecutor,
        trace: AnytimeTraceRecorder,
    ) -> None:
        self.controller = controller
        self.projector = projector
        self.executor = executor
        self.trace = trace

    async def run(self) -> SearchLoopResult:
        trace_ids: list[str] = []
        while True:
            before = self.projector.build()
            decision = self.controller.decide(before)
            replayed, issues = self.controller.replay(decision, before)
            if not replayed:
                raise RuntimeError("controller decision failed replay: " + ",".join(issues))
            self.executor.ledger.record_event("ACTION_PLANNED", jsonable(decision))
            if decision.action is SearchAction.STOP:
                if decision.parent_selection_receipt is not None:
                    receipt = decision.parent_selection_receipt
                    self.executor.ledger.add_parent_selection_receipt(
                        receipt_id=receipt.receipt_id,
                        run_id=receipt.run_id,
                        step=receipt.step,
                        payload=jsonable(receipt),
                    )
                if decision.rejected_action is not None:
                    self.executor.ledger.record_event(
                        "ACTION_REJECTED_PREFLIGHT_BUDGET",
                        {
                            "run_id": before.run_id,
                            "step": before.step,
                            "decision_id": decision.decision_id,
                            "rejected_action": decision.rejected_action.value,
                            "remaining_budget": before.remaining_budget,
                            "estimated_min_start_budget": decision.resource_floor,
                            "reserved_downstream_budget": decision.reserved_downstream_budget,
                            "budget_reserved": decision.budget_reserved,
                        },
                    )
                self.executor.ledger.record_event(
                    "SEARCH_LOOP_STOPPED",
                    {
                        "run_id": before.run_id,
                        "step": before.step,
                        "decision_id": decision.decision_id,
                        "reason_codes": decision.reason_codes,
                        "state_digest": before.digest,
                    },
                )
                return SearchLoopResult(
                    run_id=before.run_id,
                    stop_decision=decision,
                    settled_steps=before.step,
                    incumbent_candidate_id=before.incumbent_candidate_id,
                    incumbent_utility=before.incumbent_utility,
                    trace_ids=tuple(trace_ids),
                )
            self.executor.ledger.record_event(
                "ACTION_STARTED",
                {
                    "run_id": before.run_id,
                    "step": before.step,
                    "decision_id": decision.decision_id,
                    "action": decision.action.value,
                    "budget_reserved": decision.budget_reserved,
                },
            )
            settled = await self.executor.execute(decision, before)
            self._record_execution_events(settled)
            after = self.projector.build()
            record = self.trace.record(
                decision=decision,
                state_before=before,
                state_after=after,
                actual_usage=settled.actual_usage,
            )
            trace_ids.append(record.trace_id)

    def _record_execution_events(self, result: SearchActionResult) -> None:
        emitted = result.action in GENERATIVE_ACTIONS and result.result_candidate_id is not None
        execution_failed = False
        evidence = next(
            (
                item
                for item in self.executor.ledger.evidence_records()
                if item.receipt_id == result.evidence_receipt_id
            ),
            None,
        )
        if emitted:
            self.executor.ledger.record_event(
                "CANDIDATE_EMITTED",
                {
                    "run_id": result.run_id,
                    "step": result.step,
                    "decision_id": result.decision_id,
                    "candidate_id": result.result_candidate_id,
                },
            )
            if evidence is None or evidence.validity is EvidenceValidity.NOT_EVALUABLE:
                execution_failed = True
            else:
                valid = evidence.validity is EvidenceValidity.VALID
                admitted = valid and self.executor.projector.gate.evaluate(
                    self.executor.contract,
                    evidence,
                ).decision is GateDecision.FEASIBLE
                self.executor.ledger.record_event(
                    "CANDIDATE_VALID" if valid else "CANDIDATE_INVALID",
                    {
                        "run_id": result.run_id,
                        "step": result.step,
                        "decision_id": result.decision_id,
                        "candidate_id": result.result_candidate_id,
                        "evidence_receipt_id": result.evidence_receipt_id,
                        "candidate_admitted": admitted,
                        "failure_signature": result.failure_signature,
                    },
                )
        for receipt_id in result.novelty_receipt_ids:
            payload = next(
                (
                    item
                    for item in self.executor.ledger.novelty_receipt_payloads(result.run_id)
                    if item["receipt_id"] == receipt_id
                ),
                None,
            )
            if payload is not None:
                self.executor.ledger.record_event(
                    "NOVELTY_ASSESSED",
                    {
                        "run_id": result.run_id,
                        "step": result.step,
                        "receipt_id": receipt_id,
                        "proposal_candidate_id": payload["proposal_candidate_id"],
                        "decision": payload["assessment"]["decision"],
                    },
                )
        execution_failed = execution_failed or (result.action in GENERATIVE_ACTIONS and not emitted) or (
            result.evidence_receipt_id is None and result.action not in GENERATIVE_ACTIONS
        )
        if execution_failed:
            self.executor.ledger.record_event(
                "ACTION_EXECUTION_FAILED",
                {
                    "run_id": result.run_id,
                    "step": result.step,
                    "decision_id": result.decision_id,
                    "action": result.action.value,
                    "failure_signature": result.failure_signature or "ACTION_DID_NOT_COMPLETE",
                },
            )


def _build_spec(bundle: ExecutableCandidateBundle) -> CandidateBuildSpec:
    return CandidateBuildSpec(
        base_repository=Path(bundle.base_repository),
        base_commit=bundle.base_commit,
        entrypoint=bundle.entrypoint,
        environment_lock=bundle.environment_lock,
        build_command=bundle.build_command,
        test_command=bundle.test_command,
        evaluation_command=bundle.evaluation_command,
        parent_patch_stack=bundle.effective_patch_stack,
        parent_touched_paths=bundle.touched_paths,
    )


def _materialize_files(bundle: ExecutableCandidateBundle, paths: tuple[str, ...]) -> dict[str, str]:
    repository = Path(bundle.base_repository)
    with tempfile.TemporaryDirectory(prefix="discoveryos-search-context-") as temporary:
        worktree = Path(temporary) / "repo"
        _git(repository, "worktree", "add", "--detach", "--force", str(worktree), bundle.base_commit)
        try:
            for patch in bundle.effective_patch_stack:
                recount = ("--recount",) if bundle.patch_apply_policy == "recount_hunks" else ()
                result = subprocess.run(
                    ("git", "-C", str(worktree), "apply", "--whitespace=nowarn", *recount, "-"),
                    input=patch,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "candidate patch failed to materialize")
            return {path: (worktree / path).read_text(encoding="utf-8") for path in paths}
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


def _materialization_failure_signature(prefix: str, error: RuntimeError) -> str:
    detail = " ".join(str(error).split())
    return f"{prefix}:{detail[:240]}"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout


def _split_for_fidelity(contract: ProblemContract, fidelity: Fidelity) -> tuple[str | None, DataRole | None]:
    role = None
    if fidelity in {Fidelity.G1, Fidelity.G2, Fidelity.G3, Fidelity.G4}:
        role = DataRole.DEVELOPMENT
    elif fidelity is Fidelity.G5:
        role = DataRole.CALIBRATION
    elif fidelity is Fidelity.G6:
        role = DataRole.SHADOW
    elif fidelity is Fidelity.G7:
        role = DataRole.FINAL_BLIND
    if role is None:
        return None, None
    split = next((item for item in contract.data_splits if item.role is role), None)
    return (split.split_id, role) if split is not None else (None, None)


def _sum_usage(items) -> ResourceUsage:
    total = ResourceUsage()
    for item in items:
        total = _add_usage(total, item)
    return total


def _add_usage(before: ResourceUsage, actual: ResourceUsage) -> ResourceUsage:
    exit_codes = [value for value in (before.exit_code, actual.exit_code) if value is not None]
    return ResourceUsage(
        llm_input_tokens=before.llm_input_tokens + actual.llm_input_tokens,
        llm_output_tokens=before.llm_output_tokens + actual.llm_output_tokens,
        llm_cache_tokens=before.llm_cache_tokens + actual.llm_cache_tokens,
        cpu_seconds=before.cpu_seconds + actual.cpu_seconds,
        gpu_seconds=before.gpu_seconds + actual.gpu_seconds,
        device_seconds=before.device_seconds + actual.device_seconds,
        wall_seconds=before.wall_seconds + actual.wall_seconds,
        peak_rss_bytes=max(before.peak_rss_bytes, actual.peak_rss_bytes),
        exit_code=max(exit_codes, default=None),
    )


def _consume(budget: ResourceBudget, usage: ResourceUsage) -> ResourceBudget:
    available = budget.as_dict()
    consumed = usage.as_budget_dict()
    exceeded = [name for name, value in consumed.items() if value > available[name]]
    if exceeded:
        raise ValueError("search usage exceeds frozen run budget: " + ",".join(exceeded))
    return ResourceBudget(
        tokens=int(available["tokens"] - consumed["tokens"]),
        cpu_seconds=available["cpu_seconds"] - consumed["cpu_seconds"],
        gpu_seconds=available["gpu_seconds"] - consumed["gpu_seconds"],
        device_seconds=available["device_seconds"] - consumed["device_seconds"],
        wall_seconds=available["wall_seconds"] - consumed["wall_seconds"],
    )


def _scale_budget(budget: ResourceBudget, multiplier: int) -> ResourceBudget:
    if multiplier < 0:
        raise ValueError("budget multiplier cannot be negative")
    return ResourceBudget(
        tokens=budget.tokens * multiplier,
        cpu_seconds=budget.cpu_seconds * multiplier,
        gpu_seconds=budget.gpu_seconds * multiplier,
        device_seconds=budget.device_seconds * multiplier,
        wall_seconds=budget.wall_seconds * multiplier,
    )


def _sum_budgets(*budgets: ResourceBudget) -> ResourceBudget:
    return ResourceBudget(
        tokens=sum(item.tokens for item in budgets),
        cpu_seconds=sum(item.cpu_seconds for item in budgets),
        gpu_seconds=sum(item.gpu_seconds for item in budgets),
        device_seconds=sum(item.device_seconds for item in budgets),
        wall_seconds=sum(item.wall_seconds for item in budgets),
    )


def _affords_budget(available: ResourceBudget, requested: ResourceBudget) -> bool:
    return all(
        requested.as_dict()[name] <= value
        for name, value in available.as_dict().items()
    )
