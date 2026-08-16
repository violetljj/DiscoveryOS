from __future__ import annotations

import inspect
from typing import Protocol

from discoveryos.contracts.models import CandidateSpec, EvaluationOutput, ExperimentSpec
from discoveryos.util import digest_json


class Evaluator(Protocol):
    evaluator_id: str
    version: str

    def evaluate(self, candidate: CandidateSpec, experiment: ExperimentSpec, data: bytes | None) -> EvaluationOutput: ...


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        if evaluator.evaluator_id in self._evaluators:
            raise ValueError(f"duplicate evaluator: {evaluator.evaluator_id}")
        self._evaluators[evaluator.evaluator_id] = evaluator

    def get(self, evaluator_id: str) -> Evaluator:
        try:
            return self._evaluators[evaluator_id]
        except KeyError as error:
            raise KeyError(f"unknown evaluator: {evaluator_id}") from error

    def digest(self, evaluator_id: str) -> str:
        evaluator = self.get(evaluator_id)
        try:
            source = inspect.getsource(type(evaluator))
        except (OSError, TypeError):
            source = type(evaluator).__qualname__
        return digest_json({"id": evaluator.evaluator_id, "version": evaluator.version, "source": source})

    def contains(self, evaluator_id: str) -> bool:
        return evaluator_id in self._evaluators
