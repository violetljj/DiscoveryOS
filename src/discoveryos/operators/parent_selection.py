from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from enum import Enum

from discoveryos.contracts.models import MetricDirection
from discoveryos.util import digest_json, utc_now


class ParentSelectionReason(str, Enum):
    SHINKA_WEIGHTED = "SHINKA_WEIGHTED"
    ONLY_ELIGIBLE_PARENT = "ONLY_ELIGIBLE_PARENT"


@dataclass(frozen=True, slots=True)
class ParentSelectionConfig:
    """DOS-native form of ShinkaEvolve's weighted parent sampler."""

    policy_version: str = "shinka_weighted_dos_v1"
    selection_lambda: float = 10.0
    base_seed: int = 0
    minimum_component: float = 1e-12
    maximum_selection_probability: float = 1.0

    def __post_init__(self) -> None:
        if not self.policy_version or self.selection_lambda <= 0:
            raise ValueError("parent policy version and positive selection lambda are required")
        if self.base_seed < 0 or not 0 < self.minimum_component < 1:
            raise ValueError("parent selection seed/component floor is invalid")
        if not 0 < self.maximum_selection_probability <= 1:
            raise ValueError("maximum parent selection probability must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class ParentCandidate:
    candidate_id: str
    fitness: float | None
    valid: bool
    generation: int
    parent_exposure_count: int
    improvement_history: tuple[float, ...] = ()
    archive: bool = False
    incumbent: bool = False
    lineage_root_id: str | None = None
    lineage_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id or self.generation < 0 or self.parent_exposure_count < 0:
            raise ValueError("parent candidate identity and counts are invalid")
        if self.fitness is not None and not math.isfinite(self.fitness):
            raise ValueError("parent fitness must be finite when present")


@dataclass(frozen=True, slots=True)
class ParentSelectionContext:
    run_id: str
    step: int
    metric_direction: MetricDirection
    candidates: tuple[ParentCandidate, ...]
    seed: int
    policy_version: str

    def __post_init__(self) -> None:
        if not self.run_id or self.step < 0 or self.seed < 0 or not self.policy_version:
            raise ValueError("parent selection context identity is invalid")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("parent candidates must be unique")

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class ParentSelectionComponent:
    candidate_id: str
    fitness: float
    normalized_fitness_delta: float
    exploitation_component: float
    exploration_component: float
    unnormalized_weight: float
    selection_probability: float


@dataclass(frozen=True, slots=True)
class ParentSelectionReceipt:
    receipt_id: str
    run_id: str
    step: int
    context_digest: str
    selected_parent_ids: tuple[str, ...]
    selection_reason: ParentSelectionReason
    components: tuple[ParentSelectionComponent, ...]
    random_seed: int
    random_draw: float
    policy_version: str
    candidate_pool_size: int
    eligible_parent_count: int
    candidate_ids: tuple[str, ...]
    candidate_scores: tuple[float | None, ...]
    candidate_lineages: tuple[tuple[str, ...], ...]
    candidate_generations: tuple[int, ...]
    candidate_exposure_counts: tuple[int, ...]
    selection_weights: tuple[float, ...]
    selection_probabilities: tuple[float, ...]
    incumbent_id: str | None
    selected_is_incumbent: bool
    unique_eligible_lineages: int
    unique_eligible_structural_roots: int | None
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        context: ParentSelectionContext,
        selected_parent_id: str,
        reason: ParentSelectionReason,
        components: tuple[ParentSelectionComponent, ...],
        random_draw: float,
    ) -> "ParentSelectionReceipt":
        identity = {
            "run_id": context.run_id,
            "step": context.step,
            "context_digest": context.digest,
            "selected_parent_ids": (selected_parent_id,),
            "selection_reason": reason,
            "components": components,
            "random_seed": context.seed,
            "random_draw": random_draw,
            "policy_version": context.policy_version,
            "candidate_pool_size": len(context.candidates),
            "eligible_parent_count": len(components),
            "candidate_ids": tuple(item.candidate_id for item in context.candidates),
            "candidate_scores": tuple(item.fitness for item in context.candidates),
            "candidate_lineages": tuple(item.lineage_ids for item in context.candidates),
            "candidate_generations": tuple(item.generation for item in context.candidates),
            "candidate_exposure_counts": tuple(
                item.parent_exposure_count for item in context.candidates
            ),
            "selection_weights": tuple(item.unnormalized_weight for item in components),
            "selection_probabilities": tuple(
                item.selection_probability for item in components
            ),
            "incumbent_id": next(
                (item.candidate_id for item in context.candidates if item.incumbent),
                None,
            ),
            "selected_is_incumbent": next(
                (item.incumbent for item in context.candidates if item.candidate_id == selected_parent_id),
                False,
            ),
            "unique_eligible_lineages": len(
                {item.lineage_ids for item in context.candidates if item.valid and item.fitness is not None}
            ),
            "unique_eligible_structural_roots": (
                len(
                    {
                        item.lineage_root_id
                        for item in context.candidates
                        if item.valid and item.fitness is not None
                    }
                )
                if all(
                    item.lineage_root_id is not None
                    for item in context.candidates
                    if item.valid and item.fitness is not None
                )
                else None
            ),
        }
        return cls(receipt_id=f"parent_{digest_json(identity)[:24]}", **identity)


@dataclass(frozen=True, slots=True)
class ParentSelectionDiagnostics:
    parent_entropy: float
    unique_parent_count: int
    effective_parent_count: float
    parent_exposure_gini: float
    incumbent_parent_fraction: float
    non_incumbent_parent_fraction: float
    unique_structural_root_parent_count: int | None


class ShinkaWeightedParentSelectionPolicy:
    """Quality sigmoid times inverse offspring/exposure, sampled with a frozen seed.

    The official implementation uses archive fitness relative to its median, a
    MAD scale normalization, and ``1 / (1 + children_count)``. DOS preserves
    those mechanics while reading candidates and exposure from its own ledger.
    """

    def __init__(self, config: ParentSelectionConfig) -> None:
        self.config = config

    def select(self, context: ParentSelectionContext) -> ParentSelectionReceipt:
        if context.policy_version != self.config.policy_version:
            raise ValueError("parent context is bound to another policy version")
        eligible = tuple(
            sorted(
                (
                    item
                    for item in context.candidates
                    if item.valid and item.fitness is not None
                ),
                key=lambda item: item.candidate_id,
            )
        )
        if not eligible:
            raise ValueError("no valid evidence-backed scientific parent is eligible")
        oriented_scores = [
            float(item.fitness)
            * (1.0 if context.metric_direction is MetricDirection.MAXIMIZE else -1.0)
            for item in eligible
        ]
        median = statistics.median(oriented_scores)
        deviations = [abs(score - median) for score in oriented_scores]
        scale = max(statistics.median(deviations), 1e-6)
        raw: list[tuple[ParentCandidate, float, float, float, float]] = []
        for item, score in zip(eligible, oriented_scores, strict=True):
            normalized = (score - median) / scale
            exploitation = max(
                self.config.minimum_component,
                _stable_sigmoid(self.config.selection_lambda * normalized),
            )
            exploration = 1.0 / (1.0 + item.parent_exposure_count)
            raw.append((item, normalized, exploitation, exploration, exploitation * exploration))
        total = sum(item[4] for item in raw)
        probabilities = _cap_probabilities(
            [item[4] / total for item in raw],
            self.config.maximum_selection_probability,
        )
        draw = random.Random(context.seed).random()
        cursor = 0.0
        selected = raw[-1][0]
        for item, probability in zip(raw, probabilities, strict=True):
            cursor += probability
            if draw < cursor:
                selected = item[0]
                break
        components = tuple(
            ParentSelectionComponent(
                candidate_id=item.candidate_id,
                fitness=float(item.fitness),
                normalized_fitness_delta=normalized,
                exploitation_component=exploitation,
                exploration_component=exploration,
                unnormalized_weight=weight,
                selection_probability=probability,
            )
            for (item, normalized, exploitation, exploration, weight), probability in zip(
                raw, probabilities, strict=True
            )
        )
        reason = (
            ParentSelectionReason.ONLY_ELIGIBLE_PARENT
            if len(eligible) == 1
            else ParentSelectionReason.SHINKA_WEIGHTED
        )
        return ParentSelectionReceipt.create(
            context=context,
            selected_parent_id=selected.candidate_id,
            reason=reason,
            components=components,
            random_draw=draw,
        )

    def replay(
        self,
        receipt: ParentSelectionReceipt,
        context: ParentSelectionContext,
    ) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []
        reconstructed = self.select(context)
        if receipt.context_digest != context.digest:
            issues.append("PARENT_CONTEXT_DIGEST_MISMATCH")
        comparable = (
            "receipt_id",
            "selected_parent_ids",
            "selection_reason",
            "components",
            "random_seed",
            "random_draw",
            "policy_version",
        )
        if any(getattr(receipt, name) != getattr(reconstructed, name) for name in comparable):
            issues.append("PARENT_SELECTION_REPLAY_MISMATCH")
        return not issues, tuple(issues)


def parent_selection_diagnostics(
    receipts: tuple[ParentSelectionReceipt, ...],
    contexts: tuple[ParentSelectionContext, ...],
) -> ParentSelectionDiagnostics:
    if len(receipts) != len(contexts):
        raise ValueError("parent receipts and contexts must align")
    selected = [receipt.selected_parent_ids[0] for receipt in receipts]
    counts = {candidate_id: selected.count(candidate_id) for candidate_id in set(selected)}
    total = len(selected)
    probabilities = [count / total for count in counts.values()] if total else []
    entropy = -sum(p * math.log(p) for p in probabilities if p > 0)
    effective = math.exp(entropy) if probabilities else 0.0
    incumbent_count = 0
    roots: set[str] = set()
    root_available = True
    for candidate_id, context in zip(selected, contexts, strict=True):
        candidate = next(item for item in context.candidates if item.candidate_id == candidate_id)
        incumbent_count += int(candidate.incumbent)
        if candidate.lineage_root_id is None:
            root_available = False
        else:
            roots.add(candidate.lineage_root_id)
    incumbent_fraction = incumbent_count / total if total else 0.0
    return ParentSelectionDiagnostics(
        parent_entropy=entropy,
        unique_parent_count=len(counts),
        effective_parent_count=effective,
        parent_exposure_gini=_gini(tuple(counts.values())),
        incumbent_parent_fraction=incumbent_fraction,
        non_incumbent_parent_fraction=(1.0 - incumbent_fraction) if total else 0.0,
        unique_structural_root_parent_count=len(roots) if root_available else None,
    )


def _stable_sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _cap_probabilities(probabilities: list[float], maximum: float) -> list[float]:
    """Cap monopoly probability and redistribute mass without changing rank order."""
    if len(probabilities) < 2 or maximum >= 1.0:
        return probabilities
    if maximum < 1.0 / len(probabilities):
        raise ValueError("maximum selection probability is infeasible for this parent pool")
    result = list(probabilities)
    fixed: set[int] = set()
    while True:
        over = [index for index, value in enumerate(result) if value > maximum + 1e-15]
        if not over:
            break
        for index in over:
            result[index] = maximum
            fixed.add(index)
        remaining = 1.0 - sum(result[index] for index in fixed)
        open_indices = [index for index in range(len(result)) if index not in fixed]
        if not open_indices:
            break
        open_total = sum(probabilities[index] for index in open_indices)
        if open_total <= 0:
            share = remaining / len(open_indices)
            for index in open_indices:
                result[index] = share
        else:
            for index in open_indices:
                result[index] = remaining * probabilities[index] / open_total
    return result


def _gini(values: tuple[int, ...]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    ordered = sorted(values)
    count = len(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2.0 * weighted) / (count * sum(ordered)) - (count + 1.0) / count
