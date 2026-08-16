from __future__ import annotations

import random
from dataclasses import dataclass

from discoveryos.contracts.models import CandidateSpec
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_json


@dataclass(frozen=True, slots=True)
class ParameterRange:
    low: float
    high: float


class RandomSearchOperator:
    operator_id = "random_search_v1"

    def __init__(self, store: ArtifactStore, space: dict[str, ParameterRange], *, seed: int) -> None:
        self.store = store
        self.space = space
        self.seed = seed

    def generate(self, count: int, *, parent: CandidateSpec | None = None) -> list[CandidateSpec]:
        generator = random.Random(self.seed)
        candidates: list[CandidateSpec] = []
        seen: set[str] = set()
        while len(candidates) < count:
            parameters = {name: round(generator.uniform(bounds.low, bounds.high), 6) for name, bounds in sorted(self.space.items())}
            identity = digest_json(parameters)
            if identity in seen:
                continue
            seen.add(identity)
            artifact_digest = self.store.put_json(
                {"algorithm": "parameterized_clearance_rule", "parameters": parameters},
                metadata={"operator": self.operator_id},
            )
            candidate = CandidateSpec.create(
                artifact_digest=artifact_digest,
                parent_ids=(parent.candidate_id,) if parent else (),
                operator_id=self.operator_id,
                strategy_id="safe_racing_v1",
                parameters=parameters,
                semantic_delta="Sample a bounded parameter configuration; no code or evaluator changes.",
                environment_digest="python-stdlib-v1",
                hypothesis_id=None,
                expected_effects={"purpose": "explore feasible Pareto improvements"},
            )
            candidates.append(candidate)
        return candidates
